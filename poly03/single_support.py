"""Pre-registered wider proposal support on certified point-neighborhood stalls."""
import argparse
import json
from time import perf_counter
import numpy as np
from src.codec import encode,decode,paint,simple
from poly02.core import metrics
from poly02.data import CFG,save_rows,rows,read_mask,sha
from .atomic import replace_vertex
from .single import source_set,OUT,LOCAL,save_poly
from .single_search import Work,State,prepare,coordinate,segment_distance


def nearest(points,poly):
    a=np.asarray(points,float)
    seg=np.roll(poly,-1,axis=0).astype(float)-poly
    t=np.empty((len(points),len(poly)))
    dist=np.empty_like(t)
    for i in range(len(poly)):
        t[:,i],dist[:,i]=segment_distance(a,poly[i].astype(float),poly[i]+seg[i])
    return t,dist.argmin(1),dist


def expanded(mask,contour,state,work,donor_count=6,edge_count=6):
    p=state.p
    k=len(p)
    t,owner,_=nearest(contour,p)
    ys,xs=np.nonzero(paint(mask.shape,p)!=mask)
    if not len(xs): return [],[],0
    _,err_owner,_=nearest(np.c_[xs,ys],p)
    edge_order=np.argsort(-np.bincount(err_owner,minlength=k),kind="stable")[:edge_count]
    dcost=[work.score(np.delete(p,i,axis=0),rank=True) for i in range(k)]
    donors=np.argsort(dcost,kind="stable")[:donor_count]
    targets=[]
    vertices={tuple(x) for x in p}
    for j in edge_order:
        a=p[j]; v=p[(j+1)%k]-a
        n=np.array([-v[1],v[0]],float)/np.linalg.norm(v)
        indices=np.flatnonzero((owner==j)&(t[:,j]>0)&(t[:,j]<1))
        src=contour[indices]
        projection=a+t[indices,j,None]*v
        points=[src,.5*(projection+src)]
        shifts=np.array([q*s for q in (1,2,3,4,6,8,12,16,24,32) for s in (-1,1)])
        points.extend(a+u*v+shifts[:,None]*n for u in np.arange(1,8)/8.)
        candidates=np.unique(np.rint(np.concatenate(points)).astype(np.int32),axis=0)
        for xy in candidates:
            if np.all(xy>=0) and xy[0]<mask.shape[1] and xy[1]<mask.shape[0] and tuple(xy) not in vertices:
                targets.append((int(j),xy))
    return donors,targets,int(min(dcost)-state.xor)


def run(supplement=False):
    cfg=json.loads(CFG.read_text())
    sources,subset=source_set()
    name="support_rest" if supplement else "support"
    folder=OUT/name
    folder.mkdir(parents=True,exist_ok=False)
    first=None
    rows_out=[]
    for src in sources:
        if (src["id"] in subset)==supplement: continue
        raw=read_mask(src)
        for k in (16,32):
            t0=perf_counter()
            mask,curve,base,bf,floor,common=prepare(raw,k,cfg)
            work=Work(mask,bf,floor,float("inf"))
            stall,certified,cycles=coordinate(base,work,max_cycles=20)
            mid=perf_counter()
            choose=Work(mask,bf,floor,float("inf"))
            donors,targets,del_loss=expanded(mask,curve,stall,choose)
            best=stall
            unguarded_best=stall.xor
            desc=None
            improving=0
            good=0
            for i in donors if certified else []:
                for e,xy in targets:
                    if i in (e,(e+1)%k): continue
                    joint=replace_vertex([stall.p],0,int(i),0,e,xy)[0]
                    cost=choose.score(joint)
                    choose.pair_seen+=1
                    unguarded_best=min(unguarded_best,cost)
                    if cost>=stall.xor: continue
                    improving+=1
                    if choose.valid(joint):
                        good+=1
                        if cost<best.xor:
                            best=State(joint,cost)
                            desc=dict(donor=int(i),edge=e,xy=xy.tolist())
            blob=encode(mask.shape,best.p)
            end=perf_counter()
            score=metrics(mask,decode(blob))
            assert best.xor==score["xor"] and bf.exact(decode(blob))>=floor
            rel=save_poly(name,src["id"],k,"best",0,blob)
            sb=encode(mask.shape,stall.p)
            srel=save_poly(name,src["id"],k,"stationary",0,sb)
            detail=dict(id=src["id"],breed=src["group"],k=k,certified=int(certified),cycles=cycles,
                        start_xor=base.xor,stationary_xor=stall.xor,final_xor=best.xor,saved=stall.xor-best.xor,
                        min_deletion_cost=del_loss,best_unconstrained_xor=unguarded_best,improving_raw=improving,
                        improved_legal_guarded=good,invalid=choose.illegal,bf_rejected=choose.bf_rejects,
                        donors=len(donors),receivers=len(targets),joint_evals=choose.pair_seen,rank_evals=choose.ranking,
                        point_evals=work.count,bf_evals=work.bf_evals+choose.bf_evals,complete_xor_evals=common["initial_xor_evals"]+work.count+choose.count,
                        full_ms=1000*(end-t0),extra_ms=1000*(end-mid),bf2_floor=float(floor),
                        actual_bytes=len(blob),stationary_file=srel,stationary_sha=sha(sb),file=rel,sha256=sha(blob),**score)
            rows_out.append(detail)
            if desc is not None and first is None:
                removed=np.delete(stall.p,desc["donor"],0)
                first=dict(id=src["id"],k=k,floor_num=floor.numerator,floor_den=floor.denominator,
                           start_sha=sha(encode(mask.shape,base.p)),stationary=stall.p.tolist(),stationary_sha=sha(sb),
                           stationary_xor=stall.xor,first_exchange={**desc,"before":stall.p.tolist(),"after":best.p.tolist(),"before_xor":stall.xor,"after_xor":best.xor},
                           deletion_only_xor=int(np.count_nonzero(paint(mask.shape,removed)!=mask)),first_exchange_bf2=score["bf2"])
        save_rows(folder/"per_image.csv",rows_out)
        print(name,src["id"],len(rows_out),sum(r["saved"]>0 for r in rows_out),flush=True)
    (folder/"witness.json").write_text(json.dumps({"first_escape":first},indent=2),encoding="utf-8")


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--rest",action="store_true")
    from pathlib import Path
    from . import single as study
    p.add_argument("--output",type=Path)
    a=p.parse_args()
    if a.output:
        OUT=a.output.resolve(); study.LOCAL=OUT/"polygons"
    run(a.rest)
