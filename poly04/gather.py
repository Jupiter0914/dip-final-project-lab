"""Score actual PM31 streams after timing. Store receipts separately from decoded quality."""
import argparse
import csv
import hashlib
import json
import time
import zipfile
from collections import defaultdict
from pathlib import Path
import numpy as np

from poly03.maskcodec import decode,unpack,score_mask
from .study import ROOT,WORK,RESULTS,CFG,REC,config,manifest,build_jobs,load_input,canonical,encode_json
from poly02.data import rows,sha

BASE=["dataset","id","group","stratum","session","rep","budget","method"]
TIMES=["round","serialized_ms","dispatch_ms","delivered_ms","received_ns","proposed_pairs","accepted_moves",
       "cross_moves","triangle_moves","sha256","actual_bytes"]
QUALITY=["xor","fp","fn","iou","bf1","bf2","bf3","decode_ms","min_region_recall","min_region_precision","min_area_ratio","shrunken_regions"]
END_FIELDS=BASE+["rings","deadline_ms","status","reason","final_status","search_end_ms","end_ms","seed_ms",
                 "raw_cgal_sha256",*TIMES]
RUN_FIELDS=BASE+["position","clock_start_ns","caller_return_ns","rings","lower_bound","target_vertices","high_vertices",
                 "status","reason","seed_ms","search_end_ms","end_ms","rounds","proposed_pairs","accepted_moves",
                 "cross_moves","triangle_moves","events","raw_cgal_status","raw_cgal_sha256","worker_startup_ms",
                 "worker_native_ms","input_read_ms","raw_hash_ms","input_decode_ms","blob_io_and_hash_ms"]
EVENT_FIELDS=BASE+["rings",*TIMES]
ROUND_FIELDS=BASE+["round","donors","receivers","eligible_pairs","proposed_pairs","proposed_cross","proposed_triangles",
                   "ranked_improving","full_checks","structural_rejects","accepted","cross","triangle",
                   "xor_before","xor_after","donor","donor_vertex","receiver","receiver_edge","insert"]
REGION_FIELDS=["dataset","id","sha256","kind","reference_id","decoded_id","reference_area","decoded_area",
               "intersection","recall","precision","area_ratio","iou"]


class Table:
    def __init__(self,path,fields):
        self.file=path.open("w",encoding="utf-8",newline="")
        self.writer=csv.DictWriter(self.file,fieldnames=fields,extrasaction="ignore",lineterminator="\n")
        self.writer.writeheader()
    def row(self,record):self.writer.writerow(record)
    def close(self):self.file.close()


def score_file(raw,reference,blob):
    t=time.perf_counter_ns()
    pred=decode(blob)
    decode_ms=(time.perf_counter_ns()-t)/1e6
    if pred.shape!=raw.shape:raise ValueError("Canvas mismatch")
    q=score_mask(raw,pred)
    region=reference.evaluate(pred)
    if region["status"]!="success":raise ValueError(("Delivered illegal digital structure",region["reason"]))
    reg=region["components"]
    return dict(**q,decode_ms=decode_ms,min_region_recall=min((r["recall"] for r in reg),default=1.),
                min_region_precision=min((r["precision"] for r in reg),default=1.),
                min_area_ratio=min((r["area_ratio"] for r in reg),default=1.),
                shrunken_regions=sum(r["area_ratio"]<.5 for r in reg)),reg


def gather(stage,root=None,out=None):
    from .analysis_regions import RegionReference
    cfg=config(stage)
    root=Path(root) if root else WORK/stage
    folder=Path(out) if out else RESULTS/stage
    folder.mkdir(parents=True,exist_ok=False)
    src=manifest(cfg)
    catalog={(r["dataset"],r["id"]):r for r in src}
    session_meta=[]
    unique=defaultdict(set)
    endpoint_tmp=folder/"endpoints.tmp"
    runs=Table(folder/"runs.csv",RUN_FIELDS)
    events=Table(folder/"checkpoints.csv",EVENT_FIELDS)
    rounds=Table(folder/"rounds.csv",ROUND_FIELDS)
    endpoints=Table(endpoint_tmp,END_FIELDS)
    all_digests=set()
    for sid in cfg["session_ids"]:
        session=root/"sessions"/sid
        meta=json.loads((session/"complete.json").read_text(encoding="utf-8"))
        trail=session/"trials.jsonl"
        if sha(trail.read_bytes())!=meta["journal_sha256"]:raise ValueError("Incomplete journal")
        session_meta.append(meta)
        expected={(r,case["row"]["dataset"],case["row"]["id"],case["budget"],m) for r in cfg["rep_ids"]
                  for case,order in build_jobs(cfg,src,sid,r) for m in order}
        seen=set()
        with trail.open(encoding="utf-8") as f:
            for line in f:
                trial=json.loads(line)
                key=(trial["rep"],trial["dataset"],trial["id"],trial["budget"],trial["method"])
                if key in seen or key not in expected:raise ValueError(("Unexpected trial",sid,key))
                seen.add(key)
                source=(trial["dataset"],trial["id"])
                res=trial["result"];evs=trial["events"]
                common={k:trial[k] for k in ("dataset","id","group","stratum","rep","budget","method")}
                common["session"]=sid
                wrapper={k:v for k,v in res.items() if k not in ("round_log","mapping","raw_cgal_rings","cgal_worker")}
                native=res.get("cgal_worker",{})
                runs.row({**{k:v for k,v in trial.items() if k not in ("result","events","sid")},"session":sid,
                          **wrapper,"events":len(evs),"worker_native_ms":native.get("native_ms"),
                          "worker_startup_ms":native.get("startup_ms")})
                raw_sha=res.get("raw_cgal_sha256")
                if raw_sha:all_digests.add(raw_sha)
                for item in res["round_log"]:
                    rounds.row({**common,**item})
                for ev in evs:
                    if ev["payload_bytes"]!=10+4*res["rings"]+4*res["target_vertices"] or ev["payload_bytes"]>trial["budget"]:
                        raise ValueError(("Rate mismatch",key))
                    unique[source].add(ev["sha256"]);all_digests.add(ev["sha256"])
                    events.row(dict(**common,**ev,rings=res["rings"],actual_bytes=ev["payload_bytes"]))
                if [e["round"] for e in evs] != list(range(len(evs))):raise ValueError("Nonconsecutive delivered improvements")
                for deadline in trial["deadlines"]:
                    ready=[ev for ev in evs if ev["delivered_ms"]<=deadline]
                    if ready:
                        ev=ready[-1];state="success";reason="ok"
                    else:
                        ev={}
                        state=res["status"] if res["end_ms"]<=deadline and res["status"]!="success" else "not_ready"
                        reason=res["reason"] if state!="not_ready" else "no_callback_received_by_deadline"
                    endpoints.row(dict(**common,**ev,deadline_ms=deadline,status=state,reason=reason,
                        rings=res["rings"],actual_bytes=ev.get("payload_bytes"),seed_ms=res["seed_ms"],
                        raw_cgal_sha256=raw_sha,final_status=res["status"],search_end_ms=res["search_end_ms"],end_ms=res["end_ms"]))
        if seen!=expected or len(seen)!=meta["trials"]:raise ValueError(("Missing planned trials",sid,len(expected-seen)))
    for table in (runs,events,rounds,endpoints):table.close()
    (folder/"sessions.json").write_text(json.dumps(session_meta,indent=2,ensure_ascii=False),encoding="utf-8")
    regtable=Table(folder/"regions.csv",REGION_FIELDS)
    blobtable=Table(folder/"blob_metrics.csv",["dataset","id","sha256","actual_bytes",*QUALITY])
    scores={}
    for key,digests in sorted(unique.items()):
        raw,_=load_input(catalog[key],stage)
        ref=RegionReference(raw)
        for d in sorted(digests):
            blob=(root/"blobs"/d[:2]/(d+".pm3")).read_bytes()
            if sha(blob)!=d:raise ValueError(d)
            q,regions=score_file(raw,ref,blob)
            base=dict(dataset=key[0],id=key[1],sha256=d)
            blobtable.row(dict(**base,actual_bytes=len(blob),**q))
            for r in regions:regtable.row({**base,**r})
            scores[key,d]=q
    blobtable.close();regtable.close()
    ready=Table(folder/"per_run.csv",END_FIELDS+QUALITY)
    with endpoint_tmp.open(encoding="utf-8",newline="") as f:
        for r in csv.DictReader(f):
            q=scores[(r["dataset"],r["id"]),r["sha256"]] if r["status"]=="success" else {}
            ready.row({**r,**q})
    ready.close()
    endpoint_tmp.unlink()
    # Reusable real bytes and compact raw call/CGAL mapping journals, excluded from ordinary Git.
    with zipfile.ZipFile(root/"outputs.zip","w",zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for d in sorted(all_digests):
            payload=(root/"blobs"/d[:2]/(d+".pm3")).read_bytes()
            if sha(payload)!=d:raise ValueError("Blob changed")
            archive.writestr(d+".pm3",payload)
    with zipfile.ZipFile(root/"journals.zip","w",zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for sid in cfg["session_ids"]:
            for name in ("trials.jsonl","start.json","complete.json"):
                archive.write(root/"sessions"/sid/name,sid+"/"+name)
    receipt=dict(stage=stage,sources=len(src),sessions=len(session_meta),trials=sum(m["trials"] for m in session_meta),
                 scored_source_outputs=len(scores),stored_blobs=len(all_digests),
                 outputs_sha256=sha((root/"outputs.zip").read_bytes()),journal_zip_sha256=sha((root/"journals.zip").read_bytes()))
    (folder/"receipt.json").write_text(json.dumps(receipt,indent=2),encoding="utf-8")
    print(json.dumps(receipt),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("stage",choices=["dev","confirm"])
    p.add_argument("--raw",type=Path)
    p.add_argument("--output",type=Path)
    a=p.parse_args()
    gather(a.stage,a.raw,a.output)
