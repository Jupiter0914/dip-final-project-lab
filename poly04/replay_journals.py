"""Independently reconstruct observable PM31 deadlines from raw receiver clocks and archived bytes."""
import argparse
import csv
from collections import Counter
from contextlib import ExitStack
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import struct
import zipfile
import numpy as np

from poly02.data import ROOT
from poly03.maskcodec import extract, decode

DEAD_STATES={"success","below_proved_lower_bound","search_no_valid_output","unsupported_representation"}
BASE_FIELDS=("dataset","id","group","stratum","session","rep","budget","method")
EVENT_FIELDS=("round","serialized_ms","dispatch_ms","delivered_ms","received_ns","proposed_pairs","accepted_moves",
              "cross_moves","triangle_moves","sha256","actual_bytes")
QUALITY=("xor","fp","fn","iou","bf1","bf2","bf3","decode_ms","min_region_recall","min_region_precision","min_area_ratio","shrunken_regions")


def sha(data): return hashlib.sha256(data).hexdigest()


def file_sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()


def normalized_sha(p): return sha(p.read_bytes().replace(b"\r\n",b"\n"))


def read_json(path): return json.loads(path.read_text(encoding="utf-8-sig"))


def require(condition,reason):
    if not condition:raise ValueError(reason)


def expect(record,key,value):
    """CSV writer leaves None blank, round-trips integer, double and string values."""
    actual=record[key]
    if value is None:value=""
    match=(actual==str(value))
    if not match and isinstance(value,(int,float)) and actual!="":
        match=(float(actual)==value)
    require(match,f"{key}: table {actual!r} vs journal {value!r}")


def check_plan(cfg,inputs,session):
    """Reconstruct the declared attempt order directly from conditions and manifest."""
    sid=cfg["session_ids"].index(session)
    for ri,rep in enumerate(cfg["rep_ids"]):
        requests={}
        for source in inputs.values():
            rowkey=(source["dataset"],source["id"])
            for cond in cfg["conditions"]:
                if session not in cond.get("session_ids",cfg["session_ids"]) or rep not in cond.get("rep_ids",cfg["rep_ids"]):
                    continue
                if "datasets" in cond and rowkey[0] not in cond["datasets"]:continue
                if "source_ids" in cond and not({rowkey[1],"/".join(rowkey)}&set(cond["source_ids"])):continue
                key=(*rowkey,int(cond["budget"]))
                methods=requests.setdefault(key,{})
                for method in cond["methods"]:
                    require(method not in methods,("duplicate frozen condition",key,method))
                    methods[method]=sorted(cond["deadlines_ms"])
        salt=cfg["order_salt"]
        case_rank=lambda key:sha(f"{salt}|{session}|{rep}|{key}".encode())
        for key in sorted(requests,key=case_rank):
            options=requests[key]
            sequence=sorted(options,key=lambda m:sha(f"{salt}|{key}|{m}".encode()))
            offset=(sid*len(cfg["rep_ids"])+ri)%len(sequence)
            ordered=sequence[offset:]+sequence[:offset]
            for pos,method in enumerate(ordered):
                yield (rep,*key,method,pos,options[method])


def parse_native(blob):
    require(len(blob)>=10,"Truncated PM31 stream")
    magic,w,h,n=struct.unpack_from("<4sHHH",blob)
    require(magic==b"PM31" and 0<w<=16382 and 0<h<=16382,"Invalid PM31 header")
    pos=10;parent=[];rings=[]
    for i in range(n):
        require(pos+4<=len(blob),"Truncated ring header")
        par,count=struct.unpack_from("<hH",blob,pos);pos+=4
        require(-1<=par<i and count>=3 and pos+4*count<=len(blob),"Invalid ring header/count")
        coords=np.frombuffer(blob,dtype="<u2",count=2*count,offset=pos).reshape(-1,2).astype(np.int32)
        require(bool(np.all(coords<=[4*(w+1),4*(h+1)])),"Coordinate exceeds canvas")
        pos+=4*count;parent.append(par);rings.append(coords)
    require(pos==len(blob),"Trailing bytes")
    return (h,w),parent,rings


class Payloads:
    def __init__(self,root,stack,receipt):
        self.root=root
        p=root/"outputs.zip"
        self.z=stack.enter_context(zipfile.ZipFile(p)) if p.exists() else None
        if self.z is not None:
            require(file_sha(p)==receipt["outputs_sha256"],"Output ZIP digest mismatch")
            self.members=set(self.z.namelist())
            require(len(self.members)==len(self.z.namelist()),"Duplicate output ZIP members")
        self.data={}

    def get(self,digest):
        require(bool(re.fullmatch(r"[0-9a-f]{64}",digest)),"Invalid output hash")
        if digest not in self.data:
            name=digest+".pm3"
            raw=self.z.read(name) if self.z else (self.root/"blobs"/digest[:2]/name).read_bytes()
            require(sha(raw)==digest,"Blob digest mismatch")
            self.data[digest]=(raw,parse_native(raw))
        return self.data[digest]

    def complete(self,count):
        require(len(self.data)==count,"Receipt blob count mismatch")
        if self.z:require({d+".pm3" for d in self.data}==self.members,"Missing/extra archived payload")


class NativeStarts:
    def __init__(self,stage,catalog,payloads):
        self.stage=stage;self.catalog=catalog;self.payloads=payloads
        self.dense={};self.mask_equal=set();self.count=0;self.normalized=0;self.rejected=0;self.reversals=0

    def source(self,key):
        if key not in self.dense:
            if self.stage=="dev":
                from poly02.data import read_mask
            else:
                from .data import read_binary as read_mask
            mask=read_mask(self.catalog[key])
            points,parents=extract(mask)
            self.dense[key]=(mask.shape,points,parents)
        return self.dense[key]

    def check(self,key,method,res,events):
        digest=res.get("raw_cgal_sha256","")
        if method not in ("cgal","cgal_within"):
            require(not digest and not res["mapping"] and "raw_cgal_rings" not in res,"Unexpected CGAL for DP method")
            return
        if "raw_cgal_rings" not in res:
            require(res["status"] in ("below_proved_lower_bound","unsupported_representation") and not events and not digest,
                    "CGAL start omitted for supported feasible-rate input")
            return
        self.count+=1
        native=[np.asarray(p,np.int32).reshape(-1,2) for p in res["raw_cgal_rings"]]
        require(res["cgal_worker"]["status"]==res["raw_cgal_status"],"CGAL worker status mismatch")
        archivable=(len(native)==res["rings"] and all(len(r)>=3 for r in native))
        require(bool(digest)==archivable,"Missing/extra raw CGAL PM31")
        if digest:
            raw, (shape,parent,parsed)=self.payloads.get(digest)
            vshape,dense,vparent=self.source(key)
            require(shape==vshape and parent==vparent and len(parsed)==len(native) and all(np.array_equal(a,b) for a,b in zip(native,parsed)),
                    "Raw native arrays differ from stored CGAL file/source identity")
        if res["status"]!="success":
            self.rejected+=1
            require(not events,"CGAL rejection silently produced an alternative PM31")
            return
        require(res["raw_cgal_status"]=="ok" and digest and events,"CGAL success lacks native valid seed")
        require(sum(map(len,native))==res["target_vertices"],"CGAL silently changed the requested vertex count")
        first=events[0]["sha256"]
        _,(sh,pp,mapped)=self.payloads.get(first)
        require(sh==shape and pp==parent and len(mapped)==len(native),"Changed CGAL seed topology metadata")
        if method=="cgal":
            require(first==digest and not res["mapping"] and len(events)==1,"Raw CGAL replaced by another seed")
            return
        self.normalized+=1
        mapping=res["mapping"]
        require(len(mapping)==len(dense),"Missing cyclic correspondence")
        for native_ring,mapped_ring,source,mapinfo in zip(native,mapped,dense,mapping):
            ids=mapinfo["dense_indices"]
            require(len(ids)==len(native_ring)==len(set(ids)) and all(0<=i<len(source) for i in ids),"Bad dense indices")
            self.reversals+=bool(mapinfo["reversed"])
            expected=native_ring if not mapinfo["reversed"] else np.concatenate((native_ring[:1],native_ring[:0:-1]))
            require(np.array_equal(source[ids],mapped_ring) and np.array_equal(mapped_ring,expected),"CGAL mapping altered vertices")
            require(sum((b-a)%len(source) for a,b in zip(ids,ids[1:]+ids[:1]))==len(source),"CGAL mapping is not one forward cycle")
        if digest!=first and (digest,first) not in self.mask_equal:
            require(np.array_equal(decode(raw),decode(self.payloads.get(first)[0])),"CGAL orientation changed a pixel")
            self.mask_equal.add((digest,first))


class CsvStreams:
    def __init__(self,folder,stack):
        self.tables={name:csv.DictReader(stack.enter_context((folder/(name+".csv")).open(encoding="utf-8-sig",newline="")))
                     for name in ("per_run","runs","checkpoints","rounds")}

    def take(self,table,identity):
        r=next(self.tables[table],None)
        require(r is not None,f"Missing row from {table}")
        for k,v in identity.items():expect(r,k,v)
        return r

    def finish(self):
        for t,it in self.tables.items():require(next(it,None) is None,f"Extra rows in {t}")


def audit(stage):
    if stage not in ("dev","confirm"):raise ValueError(stage)
    cfgpath=ROOT/"configs/poly04"/(stage+".json")
    cfg=read_json(cfgpath)
    sourcepath=ROOT/cfg["manifest"]
    with sourcepath.open(encoding="utf-8-sig",newline="") as f: sources=list(csv.DictReader(f))
    catalog={(s["dataset"],s["id"]):s for s in sources}
    require(len(catalog)==len(sources),"Duplicate source key")
    rawroot=ROOT/"local/poly04"/stage
    folder=ROOT/"results/poly04"/stage
    receipt=read_json(folder/"receipt.json");sessions=read_json(folder/"sessions.json")
    require(receipt["stage"]==stage and receipt["sources"]==len(sources),"Wrong receipt/source count")
    require([s["session"] for s in sessions]==cfg["session_ids"] and len({s["pid"] for s in sessions})==len(sessions),
            "Session IDs or fresh process IDs differ")
    previous=None
    for s in sessions:
        t=datetime.fromisoformat(s["start_utc"]);u=datetime.fromisoformat(s["end_utc"])
        require(t<=u and (previous is None or t>=previous),"Overlapping or reversed session records")
        previous=u
    with (folder/"blob_metrics.csv").open(encoding="utf-8-sig",newline="") as f:
        scored={(r["dataset"],r["id"],r["sha256"]):r for r in csv.DictReader(f)}
    require(len(scored)==receipt["scored_source_outputs"],"Blob metric census differs")
    n_trials=n_events=n_rounds=n_endpoints=n_late=n_pre_serial_late=0
    status_counts=Counter();terminal_counts=Counter();seen_scored=set()
    recorded_worker_hashes=0
    with ExitStack() as stack:
        tabs=CsvStreams(folder,stack)
        blobs=Payloads(rawroot,stack,receipt)
        native=NativeStarts(stage,catalog,blobs)
        jpath=rawroot/"journals.zip"
        ziplog=stack.enter_context(zipfile.ZipFile(jpath)) if jpath.exists() else None
        if ziplog:
            require(file_sha(jpath)==receipt["journal_zip_sha256"],"Journal ZIP hash differs")
            expect_paths={sid+"/"+f for sid in cfg["session_ids"] for f in ("start.json","complete.json","trials.jsonl")}
            require(sorted(ziplog.namelist())==sorted(expect_paths),"Unexpected journal archive membership")
        for meta in sessions:
            sid=meta["session"]
            def get_json(filename):
                loose=rawroot/"sessions"/sid/filename
                data=ziplog.read(sid+"/"+filename) if ziplog else loose.read_bytes()
                if ziplog and loose.exists():require(data==loose.read_bytes(),"ZIP and loose session metadata differ")
                return json.loads(data)
            begun,complete=get_json("start.json"),get_json("complete.json")
            require(complete==meta and all(complete[k]==v for k,v in begun.items()),"Session metadata differs")
            require(meta["raw_manifest_sha"]==normalized_sha(sourcepath) and meta["settings_sha"]==normalized_sha(cfgpath),
                    "Sampling manifest or session configuration differs")
            worker=read_json(ROOT/"records/poly03/cgal_build.json")["binary_sha256"]
            if stage=="confirm" or "cgal_worker_sha256" in meta:
                require(meta.get("cgal_worker_sha256")==worker,"Unexpected or missing CGAL worker digest")
                recorded_worker_hashes+=1
            journal=rawroot/"sessions"/sid/"trials.jsonl"
            if ziplog and journal.exists():require(file_sha(journal)==meta["journal_sha256"],"Loose journal differs from ZIP/receipt")
            line_source=ziplog.open(sid+"/trials.jsonl") if ziplog else journal.open("rb")
            digest=hashlib.sha256();process_end=None;nt=0
            with line_source as stream:
                for plan in check_plan(cfg,catalog,sid):
                    line=stream.readline()
                    require(bool(line),"Planned trial is missing")
                    digest.update(line);trial=json.loads(line);nt+=1;n_trials+=1
                    rep,dataset,name,budget,method,position,deadlines=plan
                    identity=dict(dataset=dataset,id=name,group=catalog[dataset,name].get("group") or catalog[dataset,name].get("family") or catalog[dataset,name].get("breed") or name,
                                  stratum=catalog[dataset,name]["stratum"],session=sid,rep=rep,budget=budget,method=method)
                    require(trial["sid"]==sid and trial["position"]==position and trial["deadlines"]==deadlines and
                            all(trial[k]==v for k,v in identity.items() if k!="session"),("Unexpected trial/order",plan))
                    res,evs=trial["result"],trial["events"]
                    t0,t1=res["clock_start_ns"],res["caller_return_ns"]
                    require(t1>=t0 and (process_end is None or t0>=process_end),"Calls overlap on the monotonic clock")
                    process_end=t1
                    require(res["method"]==method and 0<=res["search_end_ms"]<=res["return_ms"]<=res["end_ms"]
                            and res["end_ms"]==(t1-t0)/1e6,"Inconsistent search/return timing")
                    require(res["status"] in DEAD_STATES and bool(evs)==(res["status"]=="success"),"Invalid terminal state")
                    terminal_counts[res["status"]]+=1
                    run=tabs.take("runs",identity)
                    for k in ("clock_start_ns","caller_return_ns","rings","lower_bound","target_vertices","high_vertices","status","reason",
                              "seed_ms","search_end_ms","end_ms","rounds","proposed_pairs","accepted_moves","cross_moves","triangle_moves",
                              "raw_cgal_status","raw_cgal_sha256","blob_io_and_hash_ms"):
                        expect(run,k,res.get(k))
                    expect(run,"events",len(evs));expect(run,"position",position)
                    for k in ("input_read_ms","raw_hash_ms","input_decode_ms"):expect(run,k,trial[k])
                    for k,origin in [("worker_native_ms","native_ms"),("worker_startup_ms","startup_ms")]:
                        expect(run,k,res.get("cgal_worker",{}).get(origin))
                    rounds=res["round_log"]
                    require(len(rounds)==res["rounds"]<=cfg["max_rounds"],"Bad round count")
                    require(res["accepted_moves"]==max(len(evs)-1,0) and
                            [e["round"] for e in evs]==list(range(len(evs))),"Accepted/checkpoint count differs")
                    counts=dict(proposed_pairs=0,accepted_moves=0,cross_moves=0,triangle_moves=0)
                    for j,round_ in enumerate(rounds,1):
                        n_rounds+=1;rr=tabs.take("rounds",identity)
                        require(j==round_["round"] and 0<=round_["proposed_pairs"]<=24 and
                                0<=round_["ranked_improving"]<=round_["proposed_pairs"] and
                                0<=round_["structural_rejects"]<=round_["full_checks"],"Invalid proposal accounting")
                        for f in ("round","donors","receivers","eligible_pairs","proposed_pairs","proposed_cross","proposed_triangles",
                                  "ranked_improving","full_checks","structural_rejects","accepted","cross","triangle","xor_before",
                                  "xor_after","donor","donor_vertex","receiver","receiver_edge","insert"):
                            val=round_.get(f)
                            if f=="insert" and val is not None:
                                # csv.DictWriter receives a JSON-loaded list.
                                val=str(val)
                            expect(rr,f,val)
                        counts["proposed_pairs"]+=round_["proposed_pairs"]
                        if round_["accepted"]:
                            counts["accepted_moves"]+=1;counts["triangle_moves"]+=round_["triangle"];counts["cross_moves"]+=round_["cross"]
                            require(j<len(evs) and all(evs[j][k]==v for k,v in counts.items()),"Accumulated accepted counters differ")
                            old=scored[dataset,name,evs[j-1]["sha256"]];new=scored[dataset,name,evs[j]["sha256"]]
                            require(int(old["xor"])==round_["xor_before"]>round_["xor_after"]==int(new["xor"]),"XOR at accepted move differs")
                        else:require(j==len(rounds),"Rejected round followed by further search")
                    require(all(res[k]==v for k,v in counts.items()),"End counters differ")
                    native.check((dataset,name),method,res,evs)
                    previous_event=t0
                    for j,e in enumerate(evs):
                        n_events+=1
                        delta=e["received_ns"]-t0
                        require(previous_event<=e["received_ns"]<=t1 and delta>=0 and
                                e["delivered_ms"]==delta/1e6 and 0<=e["serialized_ms"]<=e["dispatch_ms"]<=e["delivered_ms"]<=res["search_end_ms"],
                                "Checkpoint receipt/dispatch/serialization clocks differ")
                        if j==0:
                            require(e["serialized_ms"]>=res["seed_ms"]>=0 and
                                    all(e[k]==0 for k in ("proposed_pairs","accepted_moves","cross_moves","triangle_moves")),"Bad first checkpoint")
                        else:require(e["serialized_ms"]>=(previous_event-t0)/1e6,"Serialization precedes prior receipt")
                        previous_event=e["received_ns"]
                        raw,(shape,parent,coordinates)=blobs.get(e["sha256"])
                        require(len(raw)==e["payload_bytes"]==10+4*res["rings"]+4*res["target_vertices"]<=budget and
                                len(parent)==res["rings"] and sum(map(len,coordinates))==res["target_vertices"],"Actual serialized bytes differ")
                        seen_scored.add((dataset,name,e["sha256"]))
                        eventrow=tabs.take("checkpoints",identity)
                        expect(eventrow,"rings",res["rings"])
                        for f in EVENT_FIELDS:expect(eventrow,f,e["payload_bytes"] if f=="actual_bytes" else e[f])
                    for deadline in deadlines:
                        edge=t0+int(deadline)*1_000_000
                        selected=None
                        for e in evs:
                            if e["received_ns"]<=edge:selected=e
                        first_late=bool(evs and evs[-1]["received_ns"]>edge)
                        n_late+=int(first_late)
                        n_pre_serial_late+=sum(e["serialized_ms"]<=deadline and e["received_ns"]>edge for e in evs)
                        if selected:state,reason="success","ok"
                        elif res["status"]!="success" and t1<=edge:state,reason=res["status"],res["reason"]
                        else:state,reason="not_ready","no_callback_received_by_deadline"
                        status_counts[state]+=1;n_endpoints+=1
                        end=tabs.take("per_run",identity)
                        for f,v in (("deadline_ms",deadline),("status",state),("reason",reason),("final_status",res["status"]),("rings",res["rings"]),
                                    ("seed_ms",res["seed_ms"]),("search_end_ms",res["search_end_ms"]),("end_ms",res["end_ms"]),
                                    ("raw_cgal_sha256",res.get("raw_cgal_sha256"))):expect(end,f,v)
                        for f in EVENT_FIELDS:
                            v=None if selected is None else selected["payload_bytes"] if f=="actual_bytes" else selected[f]
                            expect(end,f,v)
                        for f in QUALITY:
                            expect(end,f,scored[dataset,name,selected["sha256"]][f] if selected else None)
                require(not stream.readline(),"Unplanned trailing trials")
            require(nt==complete["trials"] and digest.hexdigest()==complete["journal_sha256"],"Incomplete/different raw journal")
        tabs.finish()
        blobs.complete(receipt["stored_blobs"])
        require(n_trials==receipt["trials"] and len(sessions)==receipt["sessions"] and seen_scored==set(scored),"Incorrect aggregate census")
        return dict(stage=stage,planned_and_observed_trials=n_trials,receiver_events=n_events,search_rounds=n_rounds,endpoint_rows=n_endpoints,
                    sessions=len(sessions),worker_digest_recorded_sessions=recorded_worker_hashes,fresh_pids=[s["pid"] for s in sessions],source_count=len(sources),unique_pm31=len(blobs.data),
                    scored_source_outputs=len(seen_scored),terminal_counts=dict(terminal_counts),endpoint_counts=dict(status_counts),
                    deadlines_with_later_deliveries=n_late,serialized_before_but_received_after=n_pre_serial_late,
                    cgal_native_calls=native.count,cgal_rejected_without_fallback=native.rejected,cgal_forward_normalized=native.normalized,
                    reversed_mapping_rings=native.reversals,pixel_checked_nonidentical_cgal_mappings=len(native.mask_equal),
                    journal_source="ZIP" if ziplog else "loose",payload_source="ZIP" if blobs.z else "loose")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage",choices=["dev","confirm"])
    args=parser.parse_args()
    print(json.dumps(audit(args.stage),ensure_ascii=False,indent=2))
