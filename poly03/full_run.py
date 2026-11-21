"""Complete-mask study. Time shared deterministic prefixes once and charge each consuming path."""
import argparse
import csv
import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
import cv2
import numpy as np
from .maskcodec import score_mask as metrics
from poly02.data import rows,read_mask,save_rows
from .allocation import hierarchy,perimeter_counts,curves,optimal,candidates
from .cgal_bridge import simplify
from .exchange import optimize
from poly04.prepare import prepare_input, SUCCESS
from .full_data import ROOT,REC,OUT,LOCAL,MANIFEST
from .maskcodec import digital,correspondence,Renderer,extract,vector_ok,pack,decode,length,Unsupported

METHODS=("perimeter","independent_dp","feasible_add","allocation_whole","cgal_squared","cgal_scaled",
         "exchange_within","exchange_cross","exchange_add","exchange_whole")
cv2.setNumThreads(1)


@dataclass
class Work:
    ms:float=0.
    isolated:int=0
    combined:int=0
    def __add__(self,other):
        return Work(self.ms+other.ms,self.isolated+other.isolated,self.combined+other.combined)


def tick(render):
    return time.perf_counter_ns(),render.isolated_calls,render.combined_calls


def elapsed(start,render):
    return Work((time.perf_counter_ns()-start[0])/1e6,render.isolated_calls-start[1],render.combined_calls-start[2])


def run_one(row,budget,folder,blobdir,cfg):
    raw=read_mask(row)
    started=time.perf_counter_ns()
    prep=prepare_input(raw,budget)
    render=prep.render
    start=(started,0,0)
    context=dict(id=row["id"],dataset=row["dataset"],stratum=row["stratum"],budget=budget,
                 reference_fg=row.get("components",""),reference_holes=row.get("holes",""))
    records=[]; combos=[]; traces=[]
    dense,par,ref,masks,target=prep.dense,prep.parents,prep.ref,prep.ref_masks,prep.target
    if prep.dense is not None:
        context.update(rings=prep.rings,high_vertices=prep.high_vertices,lower_bound=prep.lower_bound,
                       target_vertices=target,ref_area=int(raw.sum()),expected_bytes=length(par,target) if target is not None else "")
    if prep.status!=SUCCESS:
        elapsed_ms=(time.perf_counter_ns()-started)/1e6
        for m in METHODS:
            records.append(dict(**context,method=m,status=prep.status,reason=prep.reason,encode_ms=elapsed_ms,structure_pass=0))
        return records,combos,traces
    common=elapsed(start,render)

    def assess(rings):
        if rings is None:
            return dict(reason="no_candidate",vector="not_available",digital="not_available")
        pred=render.combined(rings)
        vec=vector_ok(rings,par)
        decoded=digital(pred)
        match=correspondence(ref,decoded)
        actual=sum(map(len,rings))
        reason=("wrong_vertex_count" if actual!=target else vec if vec!="ok" else match)
        return dict(reason=reason,vector=vec,digital=match,xor=int(np.count_nonzero(pred!=raw)),
                    decoded_fg=decoded.nf,decoded_holes=decoded.nh,actual_vertices=actual)

    def emit(name,rings,assessment,work,extra=None):
        data=dict(**context,method=name,**(extra or {}),reason=assessment["reason"],vector_check=assessment["vector"],
                  digital_check=assessment["digital"],decoded_fg=assessment.get("decoded_fg",""),
                  decoded_holes=assessment.get("decoded_holes",""),attempt_xor=assessment.get("xor",""),
                  isolated_draws=work.isolated,full_draws=work.combined)
        t=time.perf_counter_ns()
        blob=pack(raw.shape,rings,par) if rings is not None and all(len(p)>=3 for p in rings) else None
        data["encode_ms"]=work.ms+(time.perf_counter_ns()-t)/1e6
        data["attempt_bytes"]=len(blob) if blob else ""
        valid=assessment["reason"]=="ok"
        data.update(status="success" if valid else "search_no_valid_output",structure_pass=int(valid))
        if blob is not None:
            suffix=".pm3" if valid else ".rejected.pm3"
            rel=Path(row["id"])/str(budget)/(name+suffix)
            dest=blobdir/rel
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(blob)
            data.update(blob=rel.as_posix(),sha256=hashlib.sha256(blob).hexdigest())
        if valid:
            assert blob and len(blob)==length(par,target)<=budget
            t=time.perf_counter_ns();pred=decode(blob)
            data["decode_ms"]=(time.perf_counter_ns()-t)/1e6
            metric=metrics(raw,pred)
            assert metric["xor"]==assessment["xor"]
            data.update(file_bytes=len(blob),**metric)
        records.append(data)

    # Perimeter baseline builds only the required levels and performs no DP.
    t=tick(render)
    per=perimeter_counts(dense,target)
    per_rings=[next(p for k,p in hierarchy(src,limit) if k==limit) for src,limit in zip(dense,per)]
    check=assess(per_rings)
    emit("perimeter",per_rings,check,common+elapsed(t,render))

    for cost in ("squared","scaled"):
        t=tick(render)
        if not dense: cg,info=[],dict(status="ok")
        else: cg,info=simplify(dense,target,cost=cost)
        got=assess(cg if cg or not dense else None)
        if info["status"]!="ok": got["reason"]=info["status"]
        emit("cgal_"+cost,cg if cg or not dense else None,got,common+elapsed(t,render),
             {"cgal_"+k:v for k,v in info.items() if k in ("status","startup_ms","triangulation_ms","native_ms","output_vertices")})

    t=tick(render)
    bank=curves(dense,masks,render,target)
    dp=optimal(bank,target)
    dp_prefix=common+elapsed(t,render)
    get=lambda c:[b[k].points for b,k in zip(bank,c)] if c is not None else None
    t=tick(render)
    dp_ring=get(dp)
    dp_check=assess(dp_ring)
    emit("independent_dp",dp_ring,dp_check,dp_prefix+elapsed(t,render))

    t=tick(render)
    pool=candidates(bank,dp,per,target,cfg)
    pref=dp_prefix+elapsed(t,render)
    additive=None;full=None;first_work=None
    total=Work()
    for c in pool:
        t=tick(render)
        rings=get(c)
        a=assess(rings)
        summed=sum(b[k].error for b,k in zip(bank,c))
        total=total+elapsed(t,render)
        combos.append(dict(id=row["id"],stratum=row["stratum"],budget=budget,counts=",".join(map(str,c)),
                           is_dp=int(c==dp),is_perimeter=int(c==per),additive_xor=summed,whole_xor=a["xor"],
                           cancellation=summed-a["xor"],vector=a["vector"],digital=a["digital"],valid=int(a["reason"]=="ok")))
        assert summed>=a["xor"]
        if a["reason"]!="ok": continue
        if additive is None:
            additive=(c,rings,a)
            first_work=pref+total
        if full is None or (a["xor"],c)<(full[2]["xor"],full[0]): full=(c,rings,a)
    if additive is None:
        empty=assess(None)
        empty["reason"]="no_valid_allocation_in_pool"
        for method in ("feasible_add","allocation_whole","exchange_within","exchange_cross","exchange_add","exchange_whole"):
            emit(method,None,empty,pref+total)
        return records,combos,traces
    emit("feasible_add",additive[1],additive[2],first_work,dict(pool_size=len(pool)))
    emit("allocation_whole",full[1],full[2],pref+total,dict(pool_size=len(pool)))

    for name,mode in [("exchange_within","within"),("exchange_cross","cross"),("exchange_add","add"),("exchange_whole","all")]:
        t=tick(render)
        if mode=="cross" and len(par)<2:
            moved,stats,trace=additive[1],dict(pair_evals=0,accepted=0,accepted_cross=0,invalid_improving=0),[]
        else:
            moved,stats,trace=optimize(raw,ref,dense,par,masks,additive[1],render,mode,cfg)
        a=assess(moved)
        assert a["reason"]=="ok" and a["xor"]<=additive[2]["xor"]
        emit(name,moved,a,first_work+elapsed(t,render),stats)
        for record in trace: traces.append(dict(id=row["id"],budget=budget,method=name,**record))
    return records,combos,traces


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path,default=OUT)
    p.add_argument("--limit",type=int)
    p.add_argument("--source")
    p.add_argument("--budget",type=int,nargs="+")
    args=p.parse_args()
    cfg=json.loads((ROOT/"configs/poly03/full.json").read_text())
    inputs=rows(MANIFEST)
    if args.source: inputs=[r for r in inputs if r["id"]==args.source]
    if args.limit: inputs=inputs[:args.limit]
    if not inputs: raise ValueError("Unknown or empty selection")
    folder=args.output
    folder.mkdir(parents=True,exist_ok=False)
    blobs=LOCAL/"blobs" if folder==OUT else folder/"blobs"
    all_rows=[]; candidates_log=[]; moves=[]
    t=time.perf_counter()
    for i,s in enumerate(inputs):
        planned=list(cfg["budgets"])
        if int(s["components"])+int(s["holes"])>=cfg["rich_min_regions"]:
            planned.append(cfg["extra_rich_budget"])
        for budget in args.budget or planned:
            r,c,m=run_one(s,budget,folder,blobs,cfg)
            all_rows.extend(r);candidates_log.extend(c);moves.extend(m)
        save_rows(folder/"per_image.csv",all_rows)
        if candidates_log: save_rows(folder/"allocation_candidates.csv",candidates_log)
        (folder/"moves.json").write_text(json.dumps(moves,separators=(",",":")),encoding="utf-8")
        print(i+1,len(inputs),s["id"],round(time.perf_counter()-t,2),flush=True)
    (folder/"run.json").write_text(json.dumps(dict(sources=len(inputs),rows=len(all_rows),wall_s=time.perf_counter()-t,
        budgets=args.budget or cfg["budgets"],extra_rich_budget=cfg["extra_rich_budget"] if not args.budget else None,
        rich_min_regions=cfg["rich_min_regions"],methods=METHODS,pool_evaluations=len(candidates_log)),indent=2),encoding="utf-8")


if __name__=="__main__": main()
