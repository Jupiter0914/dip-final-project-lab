"""Compare exact cost-order feasible allocation with local high-precision-context hints."""
import heapq
import json
import time
import hashlib
from pathlib import Path
import numpy as np
from .allocation import curves,optimal
from .maskcodec import Renderer,extract,digital,correspondence,vector_ok,length,pack,decode
from .full_data import ROOT,REC,OUT,LOCAL,MANIFEST
from poly02.data import read_mask,rows,save_rows
from .maskcodec import score_mask as metrics
from poly04.prepare import prepare_input, SUCCESS


def ordered_allocations(banks,total):
    """Lawler partition of allocations using a fixed-sum suffix DP for each subproblem."""
    n=len(banks)
    best=[{} for _ in range(n+1)]
    best[n][0]=(0,())
    for i in reversed(range(n)):
        for k,level in banks[i].items():
            for spent,(cost,suffix) in best[i+1].items():
                s=k+spent
                if s>total: continue
                item=(cost+level.error,(k,)+suffix)
                prev=best[i].get(s)
                if prev is None or item<prev: best[i][s]=item
    if total not in best[0]: return
    if not n:
        yield ()
        return
    heap=[]
    def enqueue(prefix,forbidden):
        i=len(prefix)
        left=total-sum(prefix)
        prior=sum(banks[j][k].error for j,k in enumerate(prefix))
        winner=None
        for k,lev in banks[i].items():
            tail=best[i+1].get(left-k)
            if tail is None or k in forbidden: continue
            val=(prior+lev.error+tail[0],prefix+(k,)+tail[1])
            if winner is None or val<winner: winner=val
        if winner is not None: heapq.heappush(heap,(*winner,prefix,tuple(sorted(forbidden))))
    enqueue((),set())
    while heap:
        _,solution,prefix,blocked=heapq.heappop(heap)
        yield solution
        i=len(prefix)
        enqueue(prefix,set(blocked)|{solution[i]})
        for j in range(i+1,n): enqueue(solution[:j],{solution[j]})


def solve(raw,budget,policy,limit=64):
    t=time.perf_counter_ns()
    prep=prepare_input(raw,budget)
    if prep.status!=SUCCESS:
        return dict(status=prep.status,reason=prep.reason,encode_ms=(time.perf_counter_ns()-t)/1e6,checks=0),None,[]
    dense,par,ren,ref,refs,total=prep.dense,prep.parents,prep.render,prep.ref,prep.ref_masks,prep.target
    banks=curves(dense,refs,ren,total)
    seed=optimal(banks,total)
    log=[]; checked={};blocked=set()
    def inspect(rings,kind,counts):
        pred=ren.combined(rings)
        geom=vector_ok(rings,par)
        pix=correspondence(ref,digital(pred))
        status=geom if geom!="ok" else pix
        log.append(dict(kind=kind,counts=list(counts),reason=status,xor=int((raw!=pred).sum())))
        return status
    def evaluate(c):
        if c in checked: return checked[c]
        rings=[b[k].points for b,k in zip(banks,c)]
        checked[c]=inspect(rings,"output",c)
        return checked[c]
    winner=None
    if seed is not None:
        if evaluate(seed)=="ok":winner=seed
        if policy=="context" and winner is None:
            candidate=seed
            for _ in range(4):
                previous=len(blocked)
                offenders=sorted(range(len(dense)),key=lambda i:(-banks[i][candidate[i]].error/max(1,int(refs[i].sum())),i))
                for i in offenders:
                    if len(log)>=limit-1: break
                    if candidate[i]==len(dense[i]): continue
                    rings=list(dense)
                    rings[i]=banks[i][candidate[i]].points
                    c=[len(p) for p in rings]
                    if inspect(rings,"one_ring_in_exact_context",c)!="ok":blocked.add((i,candidate[i]))
                if len(blocked)==previous or len(log)>=limit:break
                filtered=[{k:v for k,v in bank.items() if (i,k) not in blocked} for i,bank in enumerate(banks)]
                candidate=optimal(filtered,total)
                if candidate is None: break
                if evaluate(candidate)=="ok":
                    winner=candidate
                    break
        if winner is None and len(log)<limit:
            for candidate in ordered_allocations(banks,total):
                if candidate in checked: continue
                if len(log)>=limit: break
                if evaluate(candidate)=="ok":
                    winner=candidate
                    break
    blob=pack(raw.shape,[b[k].points for b,k in zip(banks,winner)],par) if winner is not None else None
    stop=time.perf_counter_ns()
    out=dict(status="success" if blob is not None else "search_no_valid_output",
             reason="ok" if blob is not None else "no_valid_within_checked_candidates",encode_ms=(stop-t)/1e6,
             checks=len(log),joint_checks=len(checked),context_checks=sum(r["kind"]!="output" for r in log),
             banned_choices=len(blocked),counts=",".join(map(str,winner)) if winner else "",isolated_draws=ren.isolated_calls)
    if blob is not None:
        pred=decode(blob);finished=time.perf_counter_ns()
        assert len(blob)==length(par,total) and correspondence(ref,digital(pred))=="ok"
        out.update(file_bytes=len(blob),sha256=hashlib.sha256(blob).hexdigest(),decode_ms=(finished-stop)/1e6,**metrics(raw,pred))
    return out,blob,log


def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,default=ROOT/"results/poly03/feasibility")
    args=parser.parse_args()
    folder=args.output
    blobroot=LOCAL/"blobs" if folder==ROOT/"results/poly03/feasibility" else folder/"blobs"
    folder.mkdir(exist_ok=False,parents=True)
    base=rows(OUT/"per_image.csv")
    inputs={r["id"]:r for r in rows(MANIFEST)}
    report=[];logs=[]
    for record in base:
        if record["method"]!="independent_dp":continue
        i,b=record["id"],int(record["budget"])
        for policy in ("cost_order","context"):
            r,blob,steps=solve(read_mask(inputs[i]),b,policy)
            dest=None
            if blob is not None:
                rel=Path(i)/str(b)/(policy+".pm3")
                dest=blobroot/rel
                dest.parent.mkdir(exist_ok=True,parents=True);dest.write_bytes(blob)
                r["blob"]=rel.as_posix()
            report.append(dict(id=i,budget=b,policy=policy,raw_dp_status=record["status"],**r))
            if record["status"]=="search_no_valid_output":logs.append(dict(id=i,budget=b,policy=policy,steps=steps))
    save_rows(folder/"per_image.csv",report)
    (folder/"triggered.json").write_text(json.dumps(logs,separators=(",",":")),encoding="utf-8")
    print("Decisions",len(report),"triggered policies",len(logs))


if __name__=="__main__": main()
