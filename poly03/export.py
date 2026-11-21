"""Encode a known or user-supplied binary PNG to PM31, or decode PM31 to native PNG."""
import argparse
import json
import time
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from .maskcodec import Renderer,extract,pack,decode,digital,correspondence,vector_ok,length,score_mask,Unsupported
from .allocation import hierarchy,perimeter_counts,curves,optimal,candidates
from .exchange import optimize
from .anytime import lazy_step
from .matched import full_step
from poly04.prepare import prepare_input, validate_rings, SUCCESS
from .cgal_bridge import simplify
from .full_data import ROOT,MANIFEST
from poly02.data import rows,read_mask

OPTIONS=("perimeter","independent_dp","feasible_add","allocation_whole","cgal_squared","cgal_scaled","additive","whole","whole_cached","within")


def encode_one(raw,budget,method="additive",rounds=2):
    start=time.perf_counter_ns()
    if method not in OPTIONS or budget<0 or rounds<0: raise ValueError("unknown method or invalid budget")
    cfg=json.loads((ROOT/"configs/poly03/full.json").read_text())
    prep=prepare_input(raw,budget)
    if prep.status!=SUCCESS:
        return None,dict(status=prep.status,reason=prep.reason,lower_bound=prep.lower_bound)
    dense,par,ren,ref,lb,target=prep.dense,prep.parents,prep.render,prep.ref,prep.lower_bound,prep.target
    def validate(ps):
        return validate_rings(prep,ps)
    trace=[]
    if not dense:p=[]
    elif method.startswith("cgal_"):
        p,meta=simplify(dense,target,cost=method.split("_")[1])
        if meta["status"]!="ok":
            return None,dict(status="search_no_valid_output",reason=meta["status"],lower_bound=lb)
    elif method=="perimeter":
        counts=perimeter_counts(dense,target)
        p=[next(v for k,v in hierarchy(r,lim) if k==lim) for r,lim in zip(dense,counts)]
    else:
        refs=prep.ref_masks
        banks=curves(dense,refs,ren,target)
        dp=optimal(banks,target)
        if dp is None:return None,dict(status="search_no_valid_output",reason="empty_exact_allocation",lower_bound=lb)
        p=[b[k].points for b,k in zip(banks,dp)]
        if method!="independent_dp":
            best=None
            for c in candidates(banks,dp,perimeter_counts(dense,target),target,cfg):
                v=[b[k].points for b,k in zip(banks,c)]
                if validate(v)!="ok":continue
                score=int(np.count_nonzero(ren.combined(v)!=raw))
                if best is None or (score,c)<best[:2]:best=(score,c,v)
                if method!="allocation_whole":break
            if best is None:return None,dict(status="search_no_valid_output",reason="no_valid_allocation_in_pool",lower_bound=lb)
            p=best[2]
            if method in ("additive","within","whole","whole_cached"):
                for _ in range(rounds):
                    if method in ("additive","within"):
                        p,action,_,_=lazy_step(raw,dense,par,ren,ref,refs,p,within=(method=="within"))
                    else:
                        p,action,_=full_step(raw,dense,par,ren,ref,refs,p,method=="whole_cached",cfg)
                    if action is None:break
                    trace.append(action)
    why=validate(p)
    if why!="ok":return None,dict(status="search_no_valid_output",reason=why,lower_bound=lb)
    blob=pack(raw.shape,p,par)
    end=time.perf_counter_ns()
    prediction=decode(blob)
    decoded=time.perf_counter_ns()
    info=dict(status="success",actual_bytes=len(blob),lower_bound=lb,vertices=sum(map(len,p)),
              encode_ms=(end-start)/1e6,decode_ms=(decoded-end)/1e6,moves=trace,**score_mask(raw,prediction))
    return blob,info


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="mode",required=True)
    enc=sub.add_parser("encode")
    src=enc.add_mutually_exclusive_group(required=True)
    src.add_argument("--input",type=Path)
    src.add_argument("--source-id")
    enc.add_argument("--budget",type=int,required=True)
    enc.add_argument("--method",choices=OPTIONS,default="additive")
    enc.add_argument("--rounds",type=int,default=2)
    enc.add_argument("--output",type=Path,required=True)
    dec=sub.add_parser("decode")
    dec.add_argument("input",type=Path);dec.add_argument("output",type=Path)
    a=parser.parse_args()
    if a.mode=="decode":
        if a.input.resolve()==a.output.resolve():parser.error("Choose a separate output")
        raw=decode(a.input.read_bytes())
        a.output.parent.mkdir(parents=True,exist_ok=True)
        Image.fromarray(raw*255).save(a.output)
        return
    if a.source_id:
        source=next((s for s in rows(MANIFEST) if s["id"]==a.source_id),None)
        if source is None:parser.error("Unknown development source")
        raw=read_mask(source)
    else:
        if a.input.resolve()==a.output.resolve():parser.error("Choose a separate output")
        with Image.open(a.input) as im:
            v=np.asarray(im)
        if v.ndim!=2:parser.error("Expected single-channel PNG; nonzero is foreground")
        raw=np.asarray(v!=0,np.uint8)
    blob,info=encode_one(raw,a.budget,a.method,a.rounds)
    print(json.dumps(info,ensure_ascii=False))
    if blob is None:raise SystemExit(2)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_bytes(blob)


if __name__=="__main__":main()
