"""Standalone single-thread timing and isolated peak-RSS probes for dense contour DP."""
import argparse
import json
import subprocess
import sys
import time
import numpy as np
import psutil
from .data import ROOT,REC,CFG,OUT,rows,save_rows,read_mask,sha
from .run import execute,memory_info


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--one",nargs=3,metavar=("ID","K","METHOD"))
    args=p.parse_args()
    cfg=json.loads(CFG.read_text())
    src={r["id"]:r for r in rows(REC/"samples.csv") if r["stage"]=="dev"}
    if args.one:
        name,k,method=args.one
        raw=read_mask(src[name])
        before=memory_info()
        _,r=execute(raw,int(k),method,cfg)
        after=memory_info()
        print(json.dumps(dict(id=name,k=int(k),method=method,n_contour=r["n_contour"],encode_ms=r["encode_ms"],
                              before_rss=before["end_rss_bytes"],peak_before=before["peak_bytes"],**after)))
        return
    root=OUT/"timing"
    root.mkdir(exist_ok=False,parents=True)
    base=sorted([r for r in rows(OUT/"dev/per_image.csv") if r["k"]=="16" and r["method"]=="geometry"],
                key=lambda r:(int(r["n_contour"]),r["id"]))
    selection=[base[i]["id"] for i in [2,8,14,20,26,32]]
    samples=[]
    methods=["geometry","raster","local_iou","sm_iou","post_xor","post_guard"]
    for name in selection:
        raw=read_mask(src[name])
        for k in cfg["main_k"]:
            for rep in range(6):
                for method in sorted(methods,key=lambda m:sha(f"{name}|{k}|{rep}|{m}".encode())):
                    _,r=execute(raw,k,method,cfg)
                    samples.append(dict(id=name,k=k,method=method,rep=rep,warmup=int(rep==0),
                                        encode_ms=r["encode_ms"],decode_ms=r["decode_ms"],sha256=r["blob_sha256"]))
    save_rows(root/"repeats.csv",samples)
    summary=[]
    for k in cfg["main_k"]:
        for method in methods:
            subset=[r for r in samples if r["k"]==k and r["method"]==method and not r["warmup"]]
            row=dict(k=k,method=method,photos=len(selection),timed_calls=len(subset))
            for key in ("encode_ms","decode_ms"):
                v=[r[key] for r in subset]
                row["median_"+key]=np.median(v)
                row["p95_"+key]=np.quantile(v,.95)
            summary.append(row)
    save_rows(root/"summary.csv",summary)
    isolated=[]
    for name in [base[0]["id"],base[len(base)//2]["id"],base[-1]["id"]]:
        for method in ("grid_dp","full_dp"):
            for k in cfg["main_k"]:
                output=subprocess.check_output([sys.executable,"-X","utf8","-m","poly02.timing","--one",name,str(k),method],cwd=ROOT)
                isolated.append(json.loads(output))
    save_rows(root/"dp_memory.csv",isolated)
    print(len(samples),"timing trials and",len(isolated),"fresh-process density measurements")


if __name__=="__main__":
    main()
