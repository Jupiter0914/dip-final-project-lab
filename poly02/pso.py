"""Representative real MATLAB trials. One persistent, headless worker; all seeds retained."""
import json
import os
import subprocess
import time
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from scipy.io import savemat,loadmat
from src.codec import encode,decode
from .data import ROOT,DATA,REC,OUT,CFG,rows,save_rows,binary_from_bytes,read_mask,sha
from .core import exterior,metrics
from .run import execute


def wait_file(p,proc,timeout):
    deadline=time.perf_counter()+timeout
    while not p.exists():
        if proc.poll() is not None: raise RuntimeError(f"MATLAB exit {proc.returncode}")
        if time.perf_counter()>deadline: raise TimeoutError(str(p))
        time.sleep(.005)


def representatives():
    rows_v1=[r for r in rows(ROOT/"results/dev/per_image.csv") if r["k"]=="16" and r["method"]=="geometry"]
    ordered=sorted(rows_v1,key=lambda r:(int(r["n_contour"])/int(r["reference_pixels"])**.5,r["id"]))
    return [ordered[int(len(ordered)*p)]["id"] for p in (1/6,1/2,5/6)]


def main():
    cfg=json.loads(CFG.read_text())
    root=OUT/"pso"
    root.mkdir(parents=True,exist_ok=False)
    spool=ROOT/"local/poly02/pso"
    spool.mkdir(parents=True,exist_ok=False)
    sets={r["id"]:r for r in rows(REC/"samples.csv") if r["stage"]=="dev"}
    ids=representatives()
    selections=[(i,k,seed) for i in ids for k in (8,16,32) for seed in cfg["seeds"]]
    info={}
    author=DATA/"upf"
    example=binary_from_bytes((author/"Fish-a100.gif").read_bytes(),"MPEG7")
    cases=[("author_Fish-a100",4,cfg["seeds"][0])]+selections
    records=[]
    witnesses=[]
    log=(root/"matlab.log").open("w",encoding="utf-8")
    command=f"addpath('{(ROOT/'poly02').as_posix()}'); pso_worker('{ROOT.as_posix()}','{spool.as_posix()}')"
    t0=time.perf_counter()
    proc=subprocess.Popen(["matlab","-batch",command],stdout=log,stderr=subprocess.STDOUT,
                          creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    try:
        wait_file(spool/"ready.txt",proc,130)
        info["startup_s"]=time.perf_counter()-t0
        info["matlab"]= (spool/"ready.txt").read_text(encoding="utf-8",errors="replace").splitlines()
        for idx,(name,k,seed) in enumerate(cases,1):
            raw=example if name=="author_Fish-a100" else read_mask(sets[name])
            t=time.perf_counter_ns()
            mask,_=exterior(raw,k)
            req=spool/f"in_{idx:03d}.mat"
            tmp=req.with_suffix(".part")
            savemat(tmp,dict(mask=mask,k=k,seed=seed),appendmat=False)
            tmp.replace(req)
            reply=spool/f"out_{idx:03d}.mat"
            wait_file(reply,proc,180)
            result=loadmat(reply,squeeze_me=True)
            err=str(result["message"]) if np.size(result["message"]) else ""
            p=np.asarray(result["p"],float)
            r=dict(id=name,k=k,seed=seed,solver_ms=float(result["solver_s"])*1000,
                   author_iou=float(result["author_iou"]),author_dice=float(result["dice"]))
            if not err:
                raw_xy=p-1
                integer=np.floor(raw_xy+.5).astype(np.int32)
                clipped=np.clip(integer,[0,0],[mask.shape[1]-1,mask.shape[0]-1]).astype(np.int32)
                r["clipped_vertices"]=int((integer!=clipped).any(axis=1).sum())
                try:
                    blob=encode(mask.shape,clipped)
                except ValueError as exc:
                    err=str(exc)
            enc=time.perf_counter_ns()
            if not err:
                pred=decode(blob)
                dec=time.perf_counter_ns()
                r.update(bytes=len(blob),blob_sha256=sha(blob),decode_ms=(dec-enc)/1e6,**metrics(mask,pred))
                dest=spool/"polygons"/name/f"{k}-{seed}.poly"
                dest.parent.mkdir(parents=True,exist_ok=True)
                dest.write_bytes(blob)
            r.update(status="rejected" if err else "ok",reason=err,encode_ms=(enc-t)/1e6)
            records.append(r)
            witnesses.append(dict(id=name,k=k,seed=seed,matlab_xy_1based=p.tolist()))
            save_rows(root/"trials.csv",records)
            (root/"vertices.json").write_text(json.dumps(witnesses,separators=(",",":")),encoding="utf-8")
            print(idx,len(cases),name,k,seed,r["status"],round(r["encode_ms"]),flush=True)
    finally:
        (spool/"stop").touch()
        try: proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.terminate()
            proc.wait(timeout=15)
        log.close()
    info["matlab"]=(spool/"ready.txt").read_text(encoding="utf-8",errors="replace").splitlines()
    info.update(ids=ids,seeds=cfg["seeds"],total_wall_s=time.perf_counter()-t0,matlab_exit=proc.returncode)
    (root/"run.json").write_text(json.dumps(info,indent=2),encoding="utf-8")
    controls=[]
    for name,k in sorted(set((i,k) for i,k,_ in cases)):
        raw=example if name=="author_Fish-a100" else read_mask(sets[name])
        for method in ["geometry","raster","local_iou","sm_iou","post_xor","post_guard"]:
            blob,result=execute(raw,k,method,cfg)
            dest=spool/"control-polygons"/name/f"{k}-{method}.poly"
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(blob)
            controls.append(dict(id=name,k=k,method=method,**result))
    save_rows(root/"controls.csv",controls)


if __name__=="__main__":
    main()
