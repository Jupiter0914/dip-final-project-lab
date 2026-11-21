"""Separable proposal ordering with a full actual acceptance test, and measured output checkpoints."""
import argparse
import hashlib
import json
import time
from pathlib import Path
import numpy as np
import cv2
from .allocation import curves,optimal,candidates,perimeter_counts
from .atomic import replace_vertex
from .exchange import proposals,optimize
from .maskcodec import Renderer,extract,vector_ok,digital,correspondence,length,pack,decode
from .full_data import ROOT,LOCAL,OUT,MANIFEST
from poly02.data import rows,read_mask,save_rows
from poly02.core import metrics

cv2.setNumThreads(1)
CFG=json.loads((ROOT/"configs/poly03/full.json").read_text())
from .matched import full_step
METHODS=("global","global_cached","additive","within_additive")


def init(raw,budget):
    rings,par=extract(raw)
    if budget<length(par,3*len(par)): return None,"below_proved_lower_bound"
    render=Renderer(raw.shape)
    if not np.array_equal(render.combined(rings),raw):return None,"unsupported_representation"
    ref=digital(raw)
    refs=[render.ring(p) for p in rings]
    k=min(sum(map(len,rings)),(budget-length(par,0))//4)
    bank=curves(rings,refs,render,k)
    dp=optimal(bank,k)
    per=perimeter_counts(rings,k)
    for c in candidates(bank,dp,per,k,CFG):
        seed=[b[v].points for b,v in zip(bank,c)]
        if vector_ok(seed,par)=="ok" and correspondence(ref,digital(render.combined(seed)))=="ok":
            return (rings,par,render,ref,refs,seed),"success"
    return None,"search_no_valid_output"


def lazy_step(raw,dense,par,render,ref,refs,state,within=False,audit=False):
    mode="within" if within else "all"
    items=proposals(dense,refs,state,render,mode,CFG)
    losses=[int(np.count_nonzero(render.ring(p)!=r)) for p,r in zip(state,refs)]
    base_add=sum(losses)
    current=int(np.count_nonzero(render.combined(state)!=raw))
    ranked=[]
    for item_num,(_,di,dj,ri,rj,xy) in enumerate(items):
        candidate=replace_vertex(state,di,dj,ri,rj,xy)
        added=base_add
        for i in {di,ri}:
            added+=int(np.count_nonzero(render.ring(candidate[i])!=refs[i]))-losses[i]
        if audit:
            slow=sum(int(np.count_nonzero(render.ring(p)!=r)) for p,r in zip(candidate,refs))
            if added!=slow: raise AssertionError("Isolated error mismatch")
        if added<base_add: ranked.append((added,item_num,candidate,(di,dj,ri,rj,xy)))
    attempts=0
    for added,_,candidate,move in sorted(ranked,key=lambda x:(x[0],x[1])):
        pred=render.combined(candidate)
        attempts+=1
        err=int(np.count_nonzero(pred!=raw))
        if err>=current:continue
        if vector_ok(candidate,par)!="ok" or correspondence(ref,digital(pred))!="ok":continue
        di,dj,ri,rj,xy=move
        return candidate,dict(donor=di,donor_vertex=dj,receiver=ri,receiver_edge=rj,insert=list(xy),
                              before=current,after=err,add_before=base_add,add_after=added),len(items),attempts
    return state,None,len(items),attempts


def test_trace():
    t=time.perf_counter()
    before=rows(OUT/"per_image.csv")
    records=[r for r in before if r["method"]=="exchange_add" and r["status"]=="success"]
    sources={r["id"]:r for r in rows(MANIFEST)}
    moves=json.loads((OUT/"moves.json").read_text())
    total=kept=global_total=global_kept=0
    for r in records:
        name=r["id"];b=int(r["budget"]);raw=read_mask(sources[name])
        init_state,status=init(raw,b)
        dense,par,ren,ref,refs,state=init_state
        trace=[]
        for _ in range(CFG["exchange_rounds"]):
            state,record,n,_=lazy_step(raw,dense,par,ren,ref,refs,state,audit=True)
            total+=n
            if record is None:break
            trace.append(record)
        expected=[x for x in moves if x["method"]=="exchange_add" and x["id"]==name and x["budget"]==b]
        assert len(trace)==len(expected)
        for a,o in zip(trace,expected):
            assert all(v==o[k] for k,v in a.items())
            kept+=1
        assert hashlib.sha256(pack(raw.shape,state,par)).hexdigest()==r["sha256"]
        state=init_state[-1]
        gt=[]
        for _ in range(CFG["exchange_rounds"]):
            state,record,n=full_step(raw,dense,par,ren,ref,refs,state,True,CFG,audit=True)
            global_total+=n
            if record is None:break
            gt.append(record)
        golden=[x for x in moves if x["method"]=="exchange_whole" and x["id"]==name and x["budget"]==b]
        assert len(gt)==len(golden)
        for a,o in zip(gt,golden):
            assert all(v==o[k] for k,v in a.items())
            global_kept+=1
        other=next(z for z in before if z["id"]==name and int(z["budget"])==b and z["method"]=="exchange_whole")
        assert hashlib.sha256(pack(raw.shape,state,par)).hexdigest()==other["sha256"]
    return dict(success_settings=len(records),all_candidate_separable_scores=total,accepted_steps=kept,
                trace_and_bytes_matched=True,full_parity_candidate_pixel_maps_checked=global_total,
                full_parity_accepted_steps=global_kept,full_parity_files_checked=len(records),wall_s=time.perf_counter()-t)


def checkpoints(raw,b,method,max_ms=200,instrumented=False):
    t=time.perf_counter_ns()
    elapsed=lambda:(time.perf_counter_ns()-t)/1e6
    start,status=init(raw,b)
    if start is None:return status,[],elapsed()
    dense,par,ren,ref,refs,p=start
    values=[];n=0;validations=0
    def snapshot(round_id):
        blob=pack(raw.shape,p,par)
        now=elapsed()
        # Store bytes now; compute evaluation after the timed search has finished.
        values.append(dict(round=round_id,ready_ms=now,payload=blob,pair_evals=n,
                           finalist_draws=validations,ring_draws=ren.isolated_calls,combined_draws=ren.combined_calls))
    snapshot(0)
    for round_id in range(1,9):
        if elapsed()>max_ms:break
        if method=="global" and instrumented:
            p,details,tr=optimize(raw,ref,dense,par,refs,p,ren,"all",{**CFG,"exchange_rounds":1})
            n+=details["pair_evals"];validations+=details["pair_evals"]
            if not tr:break
        elif method in ("global","global_cached"):
            p,move,num=full_step(raw,dense,par,ren,ref,refs,p,method=="global_cached",CFG)
            n+=num;validations+=num
            if move is None:break
        else:
            p,move,num,num_valid=lazy_step(raw,dense,par,ren,ref,refs,p,within=method=="within_additive")
            n+=num;validations+=num_valid
            if move is None:break
        snapshot(round_id)
    return status,values,elapsed()


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path,default=ROOT/"results/poly03/time_fair")
    p.add_argument("--instrumented",action="store_true",help="Reproduce the exploratory double-scoring comparator")
    args=p.parse_args()
    methods=("global","additive","within_additive") if args.instrumented else METHODS
    folder=args.output
    folder.mkdir(exist_ok=False,parents=True)
    check=test_trace()
    (folder/"trace_check.json").write_text(json.dumps(check,indent=2),encoding="utf-8")
    result=[];events=[]
    src=rows(MANIFEST)
    for m in methods:checkpoints(read_mask(src[0]),256,m,instrumented=args.instrumented)
    blobs=LOCAL/"timed" if folder==ROOT/"results/poly03/time_fair" else folder/"blobs"
    for ix,s in enumerate(src):
        raw=read_mask(s)
        for rep in range(3):
            order=sorted(methods,key=lambda m:hashlib.sha256(f"{s['id']}|{m}|{rep}".encode()).digest())
            for m in order:
                status,values,wall=checkpoints(raw,256,m,instrumented=args.instrumented)
                for v in values:
                    blob=v.pop("payload");digest=hashlib.sha256(blob).hexdigest()
                    dest=blobs/(digest+".pm3")
                    dest.parent.mkdir(parents=True,exist_ok=True)
                    if not dest.exists():dest.write_bytes(blob)
                    scored=metrics(raw,decode(blob))
                    v.update(xor=scored["xor"],iou=scored["iou"],bf2=scored["bf2"],blob_sha256=digest,file_bytes=len(blob))
                    events.append(dict(id=s["id"],rep=rep,method=m,**v))
                for deadline in (100,200):
                    ready=[v for v in values if v["ready_ms"]<=deadline]
                    result.append(dict(id=s["id"],stratum=s["stratum"],budget=256,rep=rep,method=m,deadline_ms=deadline,
                        status="success" if ready else "not_ready" if status=="success" else status,
                        measured_search_wall_ms=wall,**(ready[-1] if ready else {})))
        if (ix+1)%8==0:print("Timing",ix+1,flush=True)
    save_rows(folder/"per_image.csv",result)
    save_rows(folder/"checkpoints.csv",events)
    print(check,len(result))


if __name__=="__main__":main()
