"""Serialized timing sessions with caller-observed immutable PM31 delivery checkpoints."""
import argparse
import csv
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import time
import sys

import cv2
import numpy as np
import psutil

from poly02.data import ROOT,rows,read_mask,sha
from poly04.engine import encode

cv2.setNumThreads(1)
WORK=ROOT/"local/poly04"
RESULTS=ROOT/"results/poly04"
CFG=ROOT/"configs/poly04"
REC=ROOT/"records/poly04"


def config(stage):
    return json.loads((CFG/(stage+".json")).read_text(encoding="utf-8"))


def manifest(cfg):
    data=rows(ROOT/cfg["manifest"])
    if len(data)!=len({(r["dataset"],r["id"]) for r in data}):
        raise ValueError("Duplicate dataset/source identity")
    return data


def encode_json(value):
    if isinstance(value,np.generic): return value.item()
    if isinstance(value,np.ndarray): return value.tolist()
    raise TypeError(type(value).__name__)


def canonical(obj):
    return json.dumps(obj,ensure_ascii=False,default=encode_json,separators=(",",":"),sort_keys=True)


def eligible(row,condition):
    if "datasets" in condition and row["dataset"] not in condition["datasets"]:return False
    if "source_ids" in condition:
        ids=condition["source_ids"]
        return row["id"] in ids or row["dataset"]+"/"+row["id"] in ids
    return True


def build_jobs(cfg,sources,sid,rep):
    cases={}
    for cond in cfg["conditions"]:
        if sid not in cond.get("session_ids",cfg["session_ids"]) or rep not in cond.get("rep_ids",cfg["rep_ids"]): continue
        for row in sources:
            if not eligible(row,cond):continue
            key=(row["dataset"],row["id"],int(cond["budget"]))
            case=cases.setdefault(key,dict(row=row,budget=key[2],methods={}))
            for method in cond["methods"]:
                if method in case["methods"]:raise ValueError(("Duplicate condition",key,method))
                case["methods"][method]=sorted(cond["deadlines_ms"])
    rank=lambda s:sha(s.encode("utf-8"))
    order=sorted(cases,key=lambda k:rank(f"{cfg['order_salt']}|{sid}|{rep}|{k}"))
    session_idx=cfg["session_ids"].index(sid)
    rep_idx=cfg["rep_ids"].index(rep)
    for key in order:
        c=cases[key]
        base=sorted(c["methods"],key=lambda m:rank(f"{cfg['order_salt']}|{key}|{m}"))
        shift=(session_idx*len(cfg["rep_ids"])+rep_idx)%len(base)
        yield c,base[shift:]+base[:shift]


def load_input(row,stage):
    # Separately record file acquisition, byte integrity and decoding. All precede encode().
    start=time.perf_counter_ns()
    payload=(ROOT/row["file"]).read_bytes()
    read=time.perf_counter_ns()
    digest=sha(payload)
    if digest!=(row.get("raw_sha256") or row.get("sha256")):raise ValueError("Input byte digest mismatch "+row["id"])
    hashing=time.perf_counter_ns()
    if stage=="dev":
        from poly02.data import binary_from_bytes
        raw=binary_from_bytes(payload,row["dataset"])
    else:
        from .data import decode_binary_bytes
        raw=decode_binary_bytes(payload,row)
    end=time.perf_counter_ns()
    return np.ascontiguousarray(raw,np.uint8),dict(input_read_ms=(read-start)/1e6,raw_hash_ms=(hashing-read)/1e6,
                                                   input_decode_ms=(end-hashing)/1e6)


def store_blob(root,blob):
    digest=hashlib.sha256(blob).hexdigest()
    folder=root/"blobs"/digest[:2]
    file=folder/(digest+".pm3")
    if not file.exists():
        folder.mkdir(parents=True,exist_ok=True)
        # Temporary output prevents a partial blob being mistaken for a completed one.
        tmp=file.with_suffix(".part")
        tmp.write_bytes(blob)
        tmp.replace(file)
    return digest


def measure(raw,budget,method,maximum,round_cap,root):
    delivered=[]
    def receive(blob,event):
        now=time.perf_counter_ns()  # First operation inside the consumer.
        delivered.append((blob,event.copy(),now))
    result=encode(raw,budget,method,receive,max_ms=maximum,max_rounds=round_cap)
    returned=time.perf_counter_ns()
    t0=result.pop("start_ns")
    result["clock_start_ns"]=t0
    result["caller_return_ns"]=returned
    result["search_end_ms"]=result["end_ms"]
    result["end_ms"]=(returned-t0)/1e6
    disk_start=time.perf_counter_ns()
    ev=[]
    for blob,e,received in delivered:
        assert e.pop("start_ns")==t0
        dispatch=e.pop("delivered_ms",None)
        elapsed=(received-t0)/1e6
        if not (e["serialized_ms"]<=elapsed<=result["end_ms"]):
            raise ValueError("Delivery clock inversion")
        ev.append(dict(**e,dispatch_ms=dispatch,delivered_ms=elapsed,received_ns=received,sha256=store_blob(root,blob)))
    if any(a["delivered_ms"]>b["delivered_ms"] for a,b in zip(ev,ev[1:])):raise ValueError("Event order")
    native=result.pop("raw_cgal_blob",None)
    if native is not None:
        d=store_blob(root,native)
        if d!=result["raw_cgal_sha256"]:raise ValueError("Author data changed")
    result["blob_io_and_hash_ms"]=(time.perf_counter_ns()-disk_start)/1e6
    if (result["status"]=="success")!=bool(ev):raise ValueError("Invalid terminal state")
    return result,ev


def run_session(stage,sid,destination=None):
    cfg=config(stage)
    if sid not in cfg["session_ids"]: raise ValueError("Unregistered session")
    if stage!="dev":
        from .freeze import verify
        verify()
    sources=manifest(cfg)
    root=Path(destination) if destination else WORK/stage
    folder=root/"sessions"/str(sid)
    folder.mkdir(parents=True,exist_ok=False)
    trial_path=folder/"trials.jsonl"
    meta=dict(pid=os.getpid(),session=sid,start_utc=datetime.now(timezone.utc).isoformat(),
              monotonic=time.get_clock_info("perf_counter").implementation,platform=platform.platform(),python=sys.version,
              raw_manifest_sha=sha((ROOT/cfg["manifest"]).read_bytes().replace(b"\r\n",b"\n")),
              settings_sha=sha((CFG/(stage+".json")).read_bytes().replace(b"\r\n",b"\n")),
              available_memory=psutil.virtual_memory().available,start_load=psutil.cpu_percent(interval=.1),
              opencv_threads=cv2.getNumThreads(),worker_policy=cfg["worker_policy"],warmup=[])
    from poly03.cgal_build import TARGET
    expected_worker=json.loads((ROOT/"records/poly03/cgal_build.json").read_text(encoding="utf-8"))["binary_sha256"]
    worker_sha=sha(TARGET.read_bytes())
    if worker_sha!=expected_worker:
        raise ValueError("Native worker does not match the previously verified official build")
    import shapely
    meta.update(cgal_worker_sha256=worker_sha,numpy=np.__version__,opencv=cv2.__version__,
                geos=shapely.geos_version_string,shapely=shapely.__version__,machine_cpu_threads=psutil.cpu_count())
    launch_ns=os.environ.get("POLY04_LAUNCH_NS")
    if launch_ns:meta["process_launch_to_initialized_ms"]=(time.perf_counter_ns()-int(launch_ns))/1e6
    known=rows(ROOT/"records/poly03/full-sources.csv")
    warm_row=next(s for s in known if s["id"]==cfg["warm_id"])
    warm=read_mask(warm_row)
    for method in sorted({m for co in cfg["conditions"] for m in co["methods"]},key=lambda m:(m!="cgal",m)):
        result=encode(warm,256,method,lambda b,e:None,max_ms=40,max_rounds=1)
        meta["warmup"].append(dict(id=warm_row["id"],method=method,ms=result["end_ms"],
            worker_cold_ms=result.get("cgal_worker",{}).get("startup_ms",0),status=result["status"]))
    (folder/"start.json").write_text(json.dumps(meta,indent=2,ensure_ascii=False),encoding="utf-8")
    wall=time.perf_counter()
    recorded=0
    with trial_path.open("x",encoding="utf-8",newline="\n") as log:
        for rep in cfg["rep_ids"]:
            for ix,(case,methods) in enumerate(build_jobs(cfg,sources,sid,rep)):
                row=case["row"]
                raw,read_times=load_input(row,stage)
                for position,method in enumerate(methods):
                    deadlines=case["methods"][method]
                    result,events=measure(raw,case["budget"],method,max(deadlines),cfg["max_rounds"],root)
                    trial=dict(dataset=row["dataset"],id=row["id"],group=row.get("group") or row.get("family") or row.get("breed") or row["id"],
                        stratum=row["stratum"],sid=sid,rep=rep,budget=case["budget"],method=method,
                        deadlines=deadlines,position=position,**read_times,events=events,result=result)
                    log.write(canonical(trial)+"\n")
                    log.flush()
                    recorded+=1
                if (ix+1)%100==0:print(stage,sid,rep,ix+1,"source-budget blocks",round(time.perf_counter()-wall,1),flush=True)
    meta.update(trials=recorded,wall_s=time.perf_counter()-wall,end_utc=datetime.now(timezone.utc).isoformat(),
                journal_sha256=sha(trial_path.read_bytes()),end_rss=psutil.Process().memory_info().rss)
    (folder/"complete.json").write_text(json.dumps(meta,indent=2,ensure_ascii=False),encoding="utf-8")
    print("SESSION COMPLETE",stage,sid,recorded,round(meta["wall_s"],2),flush=True)


def serial(stage,output=None):
    import subprocess
    cfg=config(stage)
    for sid in cfg["session_ids"]:
        args=[sys.executable,"-X","utf8","-m","poly04.study","session",stage,"--session",str(sid)]
        if output:args+=["--output",str(output)]
        env=os.environ.copy()
        env.update(OMP_NUM_THREADS="1",OPENBLAS_NUM_THREADS="1",MKL_NUM_THREADS="1",
                   NUMEXPR_NUM_THREADS="1",POLY04_LAUNCH_NS=str(time.perf_counter_ns()))
        subprocess.run(args,cwd=ROOT,env=env,check=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("mode",choices=["serial","session"])
    p.add_argument("stage",choices=["dev","confirm"])
    p.add_argument("--session")
    p.add_argument("--output",type=Path)
    a=p.parse_args()
    if a.mode=="serial":serial(a.stage,a.output)
    else:run_session(a.stage,a.session,a.output)
