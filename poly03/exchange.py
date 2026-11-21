"""Shortlist by individual moves; score final fixed-size proposals on complete canvases."""
import itertools
import numpy as np
from .atomic import replace_vertex
from .maskcodec import vector_ok,digital,correspondence


def proposals(dense,refs,current,render,mode,cfg):
    donors=[]
    receivers=[]
    for ri,(raw,src,p) in enumerate(zip(refs,dense,current)):
        old=int(np.count_nonzero(render.ring(p)!=raw))
        lookup={tuple(x):i for i,x in enumerate(src.tolist())}
        for j,v in enumerate(p):
            if len(p)>3:
                cut=np.delete(p,j,axis=0)
                delta=int(np.count_nonzero(render.ring(cut)!=raw))-old
                donors.append((delta,ri,j))
            right=(j+1)%len(p)
            i0,i1=lookup[tuple(v)],lookup[tuple(p[right])]
            count=(i1-i0-1)%len(src)
            # Initial rings are cyclic subsequences of the exact original. CGAL can return
            # the opposite orientation; that case is never used as a proposal seed here.
            if not count: continue
            arc=src[(i0+np.arange(1,count+1))%len(src)]
            chord=(p[right]-v).astype(float)
            off=arc-v
            scale=np.clip(off@chord/max(1.,chord@chord),0,1)
            dist=np.sum((off-scale[:,None]*chord)**2,axis=1)
            for q in sorted({int(dist.argmax()),len(arc)//2}):
                xy=tuple(map(int,arc[q]))
                trial=np.insert(p,j+1,xy,axis=0)
                delta=int(np.count_nonzero(render.ring(trial)!=raw))-old
                receivers.append((delta,ri,j,xy))
    def short(items,n):
        items=sorted(items)
        by_ring={}
        for item in items: by_ring.setdefault(item[1],item)
        return sorted(set(items[:n]+list(by_ring.values())))
    d=short(donors,cfg["donor_shortlist"])
    r=short(receivers,cfg["receiver_shortlist"])
    ranked=[]
    for (loss,di,dj),(gain,ri,rj,xy) in itertools.product(d,r):
        same=di==ri
        if (mode=="cross" and same) or (mode=="within" and not same): continue
        if same and (dj==rj or dj==(rj+1)%len(current[ri])): continue
        ranked.append((loss+gain,di,dj,ri,rj,xy))
    return sorted(ranked)[:cfg["final_pairs_per_round"]]


def optimize(raw,ref_structure,dense,parents,refs,seed,render,mode,cfg):
    current=list(seed)
    trace=[]
    total=0
    accepted_cross=0
    invalid=0
    for round_id in range(cfg["exchange_rounds"]):
        before=render.combined(current)
        base=int(np.count_nonzero(before!=raw))
        base_add=sum(int(np.count_nonzero(render.ring(p)!=r)) for p,r in zip(current,refs))
        moves=proposals(dense,refs,current,render,mode,cfg)
        ranked=[]
        for order,(_,di,dj,ri,rj,xy) in enumerate(moves):
            cand=replace_vertex(current,di,dj,ri,rj,xy)
            total+=1
            # All rings are filled on the full canvas. Isolated deltas only shortlist moves.
            pred=render.combined(cand)
            full=int(np.count_nonzero(pred!=raw))
            added=sum(int(np.count_nonzero(render.ring(p)!=r)) for p,r in zip(cand,refs))
            if full>=base or (mode=="add" and added>=base_add): continue
            ranked.append((added if mode=="add" else full,order,full,added,cand,(di,dj,ri,rj,xy)))
        choice=None
        for _,_,full,added,cand,move in sorted(ranked,key=lambda q:(q[0],q[1])):
            why=vector_ok(cand,parents)
            if why=="ok": why=correspondence(ref_structure,digital(render.combined(cand)))
            if why=="ok":
                choice=(full,added,cand,move)
                break
            invalid+=1
        if choice is None: break
        full,added,current,move=choice
        di,dj,ri,rj,xy=move
        accepted_cross+=di!=ri
        trace.append(dict(round=round_id,donor=di,donor_vertex=dj,receiver=ri,receiver_edge=rj,insert=xy,
                          before=base,after=full,add_before=base_add,add_after=added))
    return current,dict(pair_evals=total,accepted=len(trace),accepted_cross=accepted_cross,invalid_improving=invalid),trace
