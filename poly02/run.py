"""Evaluate source photos serially; all costs include common preprocessing, initialization and POL1 serialization."""
import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import cv2
import numpy as np
import psutil
from src.codec import encode,decode
from .core import exterior,shape_info,fit,metrics
from .data import ROOT,REC,OUT,CFG,rows,save_rows,read_mask,sha

cv2.setNumThreads(1)


def memory_info():
    mi=psutil.Process().memory_info()
    data={"end_rss_bytes":mi.rss,"os":platform.system()}
    if hasattr(mi,"peak_wset"):
        data.update(peak_bytes=mi.peak_wset,peak_source="Windows peak working set")
    elif sys.platform in ("linux","darwin"):
        import resource
        data.update(peak_bytes=int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)*(1 if sys.platform=="darwin" else 1024),
                    peak_source="getrusage RUSAGE_SELF ru_maxrss")
    else:
        data.update(peak_bytes=None,peak_source="unavailable")
    return data


def execute(raw,k,method,cfg,trace=None):
    t=time.perf_counter_ns()
    mask,c=exterior(raw,k)
    poly,diag=fit(mask,c,k,method,cfg,trace)
    blob=encode(mask.shape,poly)
    enc=time.perf_counter_ns()
    pred=decode(blob)
    dec=time.perf_counter_ns()
    return blob,dict(**metrics(mask,pred),**diag,encode_ms=(enc-t)/1e6,decode_ms=(dec-enc)/1e6,
                     n_contour=len(c),h=mask.shape[0],w=mask.shape[1],bytes=len(blob),blob_sha256=sha(blob))


def run(stage,out=None):
    cfg=json.loads(CFG.read_text())
    samples=rows(REC/"samples.csv")
    is_curve=stage in ("curve","dev_curve")
    if stage not in ("dev","dev_curve"):
        from .lock import verify
        verify()
    subset=[r for r in samples if r["stage"]==("new" if stage=="curve" else stage) and (stage!="curve" or r["curve"]=="1")]
    if stage=="dev_curve":
        groups={}
        for row in samples:
            if row["stage"]=="dev":
                groups.setdefault(row["group"],row)
        subset=list(groups.values())
    folder=out or OUT/stage
    folder.mkdir(parents=True,exist_ok=False)
    poly_dir=folder/"polygons" if out else ROOT/"local/poly02"/stage
    result=[]
    failed=[]
    started=time.perf_counter()
    for idx,row in enumerate(subset):
        raw=read_mask(row)
        for k in cfg["extra_k"] if is_curve else cfg["main_k"]:
            try:
                normalized,_=exterior(raw,k)
                info=shape_info(raw,normalized)
            except ValueError as exc:
                failed.append(dict(id=row["id"],k=k,method="input",error=str(exc)))
                continue
            methods=cfg["curve_methods"] if is_curve else cfg["methods"]
            methods=sorted(methods,key=lambda m:sha(f"poly02|{row['id']}|{k}|{m}".encode()))
            for method in methods:
                try:
                    blob,details=execute(raw,k,method,cfg)
                except (ValueError,IndexError,MemoryError) as exc:
                    failed.append(dict(id=row["id"],k=k,method=method,error=str(exc)))
                    continue
                dest=poly_dir/row["id"]/f"{k}-{method}.poly"
                dest.parent.mkdir(parents=True,exist_ok=True)
                dest.write_bytes(blob)
                result.append(dict(dataset=row["dataset"],stage=stage,id=row["id"],group=row["group"],k=k,method=method,**info,**details))
        if (idx+1)%20==0: print(stage,idx+1,len(subset),flush=True)
    save_rows(folder/"per_image.csv",result)
    report=dict(sources=len(subset),rows=len(result),failures=failed,wall_s=time.perf_counter()-started,**memory_info())
    (folder/"run.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report),flush=True)


if __name__=="__main__":
    from pathlib import Path
    p=argparse.ArgumentParser()
    p.add_argument("stage",choices=["dev","dev_curve","new","cross","curve"])
    p.add_argument("--output",type=Path,help="Fresh reproduction directory")
    a=p.parse_args()
    run(a.stage,a.output)
