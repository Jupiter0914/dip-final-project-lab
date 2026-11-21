"""Development trial for atomic same-ring transfers on known POLY02 dev sources only."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from functools import lru_cache
from time import perf_counter
import zipfile
import cv2
import numpy as np
from poly02.data import ROOT,REC,CFG,rows,save_rows,read_mask,sha
from poly02.core import metrics
from src.codec import encode,decode,paint
from .single_search import prepare,Work,State,coordinate,multi,exchange

cv2.setNumThreads(1)
OUT=ROOT/"results/poly03/single"
LOCAL=ROOT/"local/poly03/single"
SEEDS=(1703,2909,4231)
METHODS=("keep","point","multi","random_pair","geometry_pair","raster_pair")


@lru_cache(maxsize=1)
def base_hashes():
    return {(r["id"],int(r["k"])):r["blob_sha256"] for r in rows(ROOT/"results/poly02/dev/per_image.csv")
            if r["method"]=="post_guard"}


def source_set():
    data=[r for r in rows(REC/"samples.csv") if r["stage"]=="dev"]
    assert len(data)==36 and len({r["id"] for r in data})==36
    chosen={}
    for r in sorted(data,key=lambda row:sha(("poly03-single|"+row["id"]).encode())):
        chosen.setdefault(r["group"],r["id"])
    return sorted(data,key=lambda r:r["id"]),set(chosen.values())


def save_poly(stage,name,k,method,seed,blob):
    rel=f"{stage}/{name}/{k}-{method}-{seed}.poly"
    path=LOCAL/rel
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(blob)
    return rel


def measure(raw,src,k,method,seed,mode,cfg):
    started=perf_counter()
    mask,contour,base,bf,floor,common=prepare(raw,k,cfg)
    rng=np.random.default_rng(int(sha((src["id"]+"|"+str(k)+"|"+str(seed)).encode())[:16],16))
    begin=perf_counter()
    extra_s={16:.120,32:.220}[k]
    limit=64*k if mode=="quota" else float("inf")
    deadline=float("inf") if mode=="quota" else begin+extra_s
    work=Work(mask,bf,floor,limit,deadline)
    state=base
    if method=="point": state,_,_=coordinate(state,work)
    elif method=="multi": state=multi(state,work,rng)
    elif method!="keep": state=exchange(contour,state,work,method,rng)
    after=perf_counter()
    blob=encode(mask.shape,state.p)
    end=perf_counter()
    predicted=decode(blob)
    decoded=perf_counter()
    score=metrics(mask,predicted)
    initial_blob=encode(mask.shape,base.p)
    assert sha(initial_blob)==base_hashes()[src["id"],k]
    assert score["xor"]==state.xor<=base.xor and bf.exact(predicted)>=floor
    if mode=="quota": assert work.count<=64*k
    name=save_poly(mode,src["id"],k,method,seed,blob)
    return dict(id=src["id"],breed=src["group"],mode=mode,k=k,method=method,seed=seed,
                full_ms=1000*(end-started),common_ms=1000*(begin-started),extra_ms=1000*(after-begin),
                decode_ms=1000*(decoded-end),quota=64*k if mode=="quota" else "",time_cap_ms=extra_s*1000 if mode=="time" else "",
                xor_evals=work.count,rank_xor=work.ranking,joint_evals=work.pair_seen,
                extra_geometric_guide_evals=work.geometric_guide_evals,association_distances=work.association_distances,
                bf_tests=work.bf_evals,geometry_tests=work.tests,invalid=work.illegal,bf_rejected=work.bf_rejects,
                raw_accepts=work.accepted,restarts=work.restarts,guide_rounds=work.rounds,
                complete_xor_evals=work.count+common["initial_xor_evals"],
                complete_bf_evals=work.bf_evals+common["initial_bf_evals"],**common,
                start_xor=base.xor,start_sha=sha(initial_blob),bf2_floor=float(floor),
                saved=base.xor-state.xor,actual_bytes=len(blob),file=name,sha256=sha(blob),**score)


def race(mode):
    out=OUT/mode
    out.mkdir(parents=True,exist_ok=False)
    data,subset=source_set()
    cfg=json.loads(CFG.read_text())
    records=[]
    failures=[]
    wall=perf_counter()
    for source in data:
        if mode=="time" and source["id"] not in subset: continue
        raw=read_mask(source)
        jobs=[(k,m,s) for k in (16,32) for m in METHODS for s in (SEEDS if m in ("multi","random_pair") else (0,))]
        jobs.sort(key=lambda j:sha(f"POLY03|{source['id']}|{j}".encode()))
        for k,m,s in jobs:
            try: records.append(measure(raw,source,k,m,s,mode,cfg))
            except (ValueError,IndexError) as exc:
                failures.append(dict(id=source["id"],k=k,method=m,seed=s,error=str(exc)))
        save_rows(out/"per_image.csv",records)
        print(mode,source["id"],len(records),len(failures),flush=True)
    (out/"run.json").write_text(json.dumps(dict(sources=len(data) if mode=="quota" else len(subset),
                                 records=len(records),failures=failures,elapsed=perf_counter()-wall),indent=2),encoding="utf-8")


def stagnation():
    out=OUT/"stagnation"
    out.mkdir(parents=True,exist_ok=False)
    data,subset=source_set()
    cfg=json.loads(CFG.read_text())
    records=[]
    witness=None
    neutral=None
    for src in data:
        if src["id"] not in subset: continue
        raw=read_mask(src)
        for k in (16,32):
            t0=perf_counter()
            mask,contour,base,bf,floor,common=prepare(raw,k,cfg)
            start_time=perf_counter()
            mover=Work(mask,bf,floor,float("inf"))
            stationary,certified,cycles=coordinate(base,mover,max_cycles=20)
            middle=perf_counter()
            pair=Work(mask,bf,floor,64*k)
            if certified:
                after=exchange(contour,stationary,pair,"raster_pair",np.random.default_rng(0),trace=True)
            else: after=stationary
            blob=encode(mask.shape,after.p)
            end=perf_counter()
            score=metrics(mask,decode(blob))
            assert score["xor"]==after.xor and bf.exact(decode(blob))>=floor
            rel=save_poly("stagnation",src["id"],k,"escaped",0,blob)
            sb=encode(mask.shape,stationary.p)
            srel=save_poly("stagnation",src["id"],k,"stationary",0,sb)
            item=dict(id=src["id"],breed=src["group"],k=k,certified=int(certified),cycles=cycles,
                      start_xor=base.xor,stationary_xor=stationary.xor,final_xor=after.xor,
                      saved_after_plateau=stationary.xor-after.xor,point_evals=mover.count,pair_evals=pair.count,
                      pair_rank_evals=pair.ranking,point_bf_tests=mover.bf_evals,pair_bf_tests=pair.bf_evals,
                      pair_accepted=pair.accepted,full_ms=(end-t0)*1000,initial_ms=(start_time-t0)*1000,
                      point_ms=(middle-start_time)*1000,pair_ms=(end-middle)*1000,bf2_floor=float(floor),
                      stationary_file=srel,stationary_sha=sha(sb),file=rel,sha256=sha(blob),actual_bytes=len(blob),**score)
            records.append(item)
            if certified and pair.events and witness is None:
                e=pair.events[0]
                pp=np.array(e["before"],np.int32)
                removed=np.delete(pp,e["donor"],axis=0)
                mask_d=paint(mask.shape,removed)
                probe=dict(id=src["id"],k=k,start_sha=sha(encode(mask.shape,base.p)),floor_num=floor.numerator,
                           floor_den=floor.denominator,stationary_sha=sha(sb),stationary=pp.tolist(),
                           deletion_only_xor=int(np.count_nonzero(mask_d!=mask)),first_exchange=e,
                           first_exchange_bf2=float(bf.exact(paint(mask.shape,np.array(e["after"],np.int32)))))
                witness=probe
            if certified and after.xor==stationary.xor and neutral is None:
                neutral=dict(id=src["id"],k=k,stationary_xor=stationary.xor,quota=64*k)
        save_rows(out/"per_image.csv",records)
        print("stagnation",src["id"],len(records),flush=True)
    (out/"witness.json").write_text(json.dumps(dict(first_escape=witness,first_no_gain=neutral),indent=2),encoding="utf-8")


def archive_output():
    with zipfile.ZipFile(OUT/"polygons.zip","w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as zipout:
        for path in sorted(LOCAL.rglob("*.poly")):
            zi=zipfile.ZipInfo(path.relative_to(LOCAL).as_posix(),(2020,1,1,0,0,0))
            zipout.writestr(zi,path.read_bytes(),compress_type=zipfile.ZIP_DEFLATED)
    print(sha((OUT/"polygons.zip").read_bytes()))


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("mode",choices=["quota","time","stagnation","pack"])
    parser.add_argument("--output",type=Path,help="Fresh output root shared by this reproduction's stages")
    args=parser.parse_args()
    if args.output:
        OUT=args.output.resolve()
        LOCAL=OUT/"polygons"
    if args.mode=="stagnation": stagnation()
    elif args.mode=="pack": archive_output()
    else: race(args.mode)
