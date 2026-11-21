"""Exact site guard versus aggregate skeleton recall, both above the same geometric BF2 floor."""
import argparse
import json
from pathlib import Path
from time import perf_counter_ns
import zipfile

import cv2
import numpy as np
from poly02.core import BoundaryScore,RasterLoss,exterior,fit,disk
from poly02.data import ROOT,CFG,save_rows,sha
from src.codec import encode,decode,paint,simple
from src.method import DIRECTIONS
from .detail_probe import BASE,DetailReference,compare,known_sources,thinning,legacy_blob,read_mask

METHODS=("geometry","post_xor","post_guard","global_skeleton","site_skeleton")
cv2.setNumThreads(1)


def guarded(mask,start,steps,mode):
    begin=perf_counter_ns()
    skeleton=thinning(mask)
    loss=RasterLoss(mask)
    p=start.copy()
    cost=loss.score(p,"xor")
    keep_bf2=mode in ("global_skeleton","site_skeleton")
    floor_score=BoundaryScore(mask,2) if keep_bf2 else None
    bf_floor=floor_score.exact(loss.render) if keep_bf2 else None
    all_sites=np.flatnonzero(skeleton)
    initial=all_sites[loss.render.ravel()[all_sites]!=0]
    stats=dict(accepted=0,proposals=0,invalid=0,boundary_rejected=0,skeleton_rejected=0,
               candidate_skeleton_checks=0,skeleton_points=len(all_sites),protected_points=len(initial),
               setup_ms=(perf_counter_ns()-begin)/1e6,floor_bf2=float(bf_floor) if keep_bf2 else "")
    h,w=mask.shape
    for sweep,step in enumerate(steps):
        order=range(len(p)) if sweep%2==0 else reversed(range(len(p)))
        for j in order:
            origin=p[j].copy()
            trials=[]
            for offset in DIRECTIONS:
                xy=origin+offset*step
                if 0<=xy[0]<w and 0<=xy[1]<h:
                    p[j]=xy
                    trials.append((loss.score(p,"xor"),xy))
            p[j]=origin
            stats["proposals"]+=len(trials)
            for candidate,xy in sorted(trials,key=lambda t:t[0]):
                if candidate>=cost: break
                p[j]=xy
                if not simple(p):
                    stats["invalid"]+=1
                    p[j]=origin
                    continue
                out=paint(mask.shape,p)
                if keep_bf2 and floor_score.exact(out)<bf_floor:
                    stats["boundary_rejected"]+=1
                    p[j]=origin
                    continue
                stats["candidate_skeleton_checks"]+=1
                flat=out.ravel()
                if mode in ("global_skeleton","global_only"):
                    valid=int(np.count_nonzero(flat[all_sites]))>=len(initial)
                else:
                    valid=bool(flat[initial].all())
                if not valid:
                    stats["skeleton_rejected"]+=1
                    p[j]=origin
                    continue
                cost=candidate
                stats["accepted"]+=1
                break
    return p,stats


def execute(raw,k,method,cfg):
    start=perf_counter_ns()
    mask,c=exterior(raw,k)
    if method in ("global_skeleton","site_skeleton","global_only","site_only"):
        origin,first=fit(mask,c,k,"geometry",cfg)
        p,extra=guarded(mask,origin,cfg["radii"],method)
        info={**first,**extra}
    else:
        p,info=fit(mask,c,k,method,cfg)
    blob=encode(mask.shape,p)
    a=perf_counter_ns()
    out=decode(blob)
    b=perf_counter_ns()
    return blob,out,dict(**info,encode_ms=(a-start)/1e6,decode_ms=(b-a)/1e6,bytes=len(blob),sha256=sha(blob))


def run(folder,standalone=False,local=None):
    cfg=json.loads(CFG.read_text(encoding="utf-8"))
    result=[]
    paths={}
    local=local or ROOT/"local/poly03/detail"
    for i,s in enumerate(known_sources(),1):
        raw=read_mask(s)
        mask,_=exterior(raw,16)
        ref=DetailReference(mask)
        flank=(cv2.dilate(ref.terminal.astype(np.uint8),disk(2))!=0)&(mask!=0)&~ref.skeleton
        for k in (16,32):
            geo=decode(legacy_blob(s["id"],k,"geometry"))
            gv,gn,gd=ref.measurements(geo)
            methods=("global_only","site_only") if standalone else METHODS
            for method in sorted(methods,key=lambda m:sha(f"{s['id']}|{k}|{m}".encode())):
                blob,out,stat=execute(raw,k,method,cfg)
                if method in METHODS[:3]:
                    assert blob==legacy_blob(s["id"],k,method)
                row,parts=compare(ref,geo,out,gv,gn,gd)
                if method in ("post_guard","global_skeleton","site_skeleton"):
                    assert row["delta_bf2"]>=-1e-12 and row["delta_xor"]<=0
                if method in ("global_skeleton","global_only"): assert row["delta_skel_hit"]>=0
                if method in ("site_skeleton","site_only"): assert row["skeleton_lost"]==0
                fn=int((flank & (out==0)).sum())
                base_fn=int((flank & (geo==0)).sum())
                old=np.asarray(geo!=0); new=np.asarray(out!=0)
                row.update(flank_pixels=int(flank.sum()),flank_fn=fn,flank_fn_change=fn-base_fn,
                           flank_lost=int((flank & old & ~new).sum()),flank_gained=int((flank & new & ~old).sum()),
                           geo_xor=gv["xor"],relative_xor_saved=(gv["xor"]-row["xor"])/max(gv["xor"],1),
                           zero_change=int(np.array_equal(geo,out)),zero_move=int(stat.get("accepted",0)==0))
                out_file=local/s["id"]/f"{k}-{method}.poly"
                out_file.parent.mkdir(exist_ok=True,parents=True)
                out_file.write_bytes(blob)
                paths[out_file.relative_to(local).as_posix()]=blob
                result.append(dict(id=s["id"],group=s["group"],k=k,method=method,**row,**stat))
        if i%12==0: print("guard trials",i,flush=True)
    save_rows(folder/"guards.csv",result)
    with zipfile.ZipFile(folder/"polygons.zip","w") as z:
        for name,blob in sorted(paths.items()):
            z.writestr(zipfile.ZipInfo(name,(2020,1,1,0,0,0)),blob,compress_type=zipfile.ZIP_DEFLATED)
    print("Guard outputs",len(result))


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--out",type=Path,default=BASE)
    p.add_argument("--standalone",action="store_true",help="Run just the two skeleton-only controls without the BF2 floor")
    args=p.parse_args()
    folder=args.out/"standalone" if args.standalone else args.out
    folder.mkdir(exist_ok=True,parents=True)
    run(folder,args.standalone,None if args.out.resolve()==BASE.resolve() else folder/"encoded")
