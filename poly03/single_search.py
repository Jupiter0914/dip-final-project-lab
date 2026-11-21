"""Fixed-K, full-canvas atomic and point search for the POLY03 development trial."""
from dataclasses import dataclass
from fractions import Fraction
from time import perf_counter
import cv2
import numpy as np
from poly02.core import BoundaryScore, RasterLoss, DIRECTIONS, exterior, initial, local_search
from src.baselines import root_contour
from src.codec import paint, simple
from src.method import refine as geometry_search
from .atomic import replace_vertex

RADII=(1,2,4,8)


@dataclass
class State:
    p: np.ndarray
    xor: int


def prepare(raw,k,cfg):
    """Recompute the original encoder. Do not use an old polygon as a free input."""
    mask,contour=exterior(raw,k)
    rooted=root_contour(contour)
    ids,fall=initial(rooted,k,cfg["grid"])
    geo,gd=geometry_search(mask,rooted,ids,cfg["radii"],"geometry")
    protected,rd=local_search(mask,geo,cfg["radii"],"xor",guard=True)
    bf=BoundaryScore(mask,2)
    floor=bf.exact(paint(mask.shape,geo))
    common=dict(initial_xor_evals=1+rd["proposals"],initial_geometric_evals=gd["proposals"]+k*len(cfg["radii"]),
                initial_bf_evals=2+rd["accepted"]+rd["boundary_rejected"],fallback=fall)
    return mask,contour,State(protected,int(rd["final_cost"])),bf,floor,common


class Work:
    def __init__(self,mask,scorer,floor,limit,deadline=float("inf")):
        self.loss=RasterLoss(mask)
        self.mask=mask
        self.scorer=scorer
        self.floor=floor
        self.limit=limit
        self.deadline=deadline
        self.count=0
        self.ranking=0
        self.geometric_guide_evals=0
        self.association_distances=0
        self.tests=0
        self.illegal=0
        self.bf_evals=0
        self.bf_rejects=0
        self.accepted=0
        self.rounds=0
        self.restarts=0
        self.pair_seen=0
        self.events=[]

    def open(self):
        return self.count<self.limit and perf_counter()<self.deadline

    def score(self,p,rank=False):
        self.count+=1
        self.ranking+=int(rank)
        return self.loss.score(p,"xor")

    def valid(self,p):
        self.tests+=1
        if not simple(p):
            self.illegal+=1
            return False
        self.bf_evals+=1
        observed=self.scorer.exact(paint(self.mask.shape,p))
        if observed<self.floor:
            self.bf_rejects+=1
            return False
        return True


def segment_distance(points,a,b):
    delta=points-a
    direction=b-a
    t=np.clip((delta@direction)/max(float(direction@direction),1),0,1)
    distance=((delta-t[:,None]*direction)**2).sum(1)
    return t,distance


def pool(contour,p,geometric=False):
    curve=contour.astype(float)
    pts=p.astype(float)
    k=len(p)
    t=np.empty((len(curve),k))
    d=np.empty_like(t)
    for j in range(k):
        t[:,j],d[:,j]=segment_distance(curve,pts[j],pts[(j+1)%k])
    owners=d.argmin(1)
    target=[]
    g_remove=np.zeros(k)
    for j in range(k):
        b=(j+1)%k
        assigned=np.flatnonzero(owners==j)
        for lo,hi in ((0,.25),(.25,.5),(.5,.75),(.75,1.)):
            ix=assigned[(t[assigned,j]>lo)&(t[assigned,j]<=hi)&(t[assigned,j]<1.)]
            if not len(ix):
                continue
            n=ix[np.argmax(d[ix,j])]
            xy=contour[n]
            if np.any(np.all(p==xy,axis=1)):
                continue
            value=0.
            if geometric:
                a1=segment_distance(curve[assigned],pts[j],xy)[1]
                a2=segment_distance(curve[assigned],xy,pts[b])[1]
                value=float(np.minimum(a1,a2).sum()-d[assigned,j].sum())
            target.append((j,xy.copy(),value))
        if geometric:
            prev=(j-1)%k
            indices=np.flatnonzero((owners==prev)|(owners==j))
            value=segment_distance(curve[indices],pts[prev],pts[b])[1].sum()
            g_remove[j]=value-d[indices,owners[indices]].sum()
    return target,g_remove


def ordered_pairs(curve,state,work,mode,rng):
    p=state.p
    targets,donors=pool(curve,p,geometric=mode=="geometry_pair")
    work.association_distances+=len(curve)*len(p)
    if mode=="geometry_pair":
        work.geometric_guide_evals+=len(p)+len(targets)
    insert_rank=np.asarray([t[2] for t in targets])
    if mode=="raster_pair":
        for i in range(len(p)):
            if not work.open(): return [],targets
            donors[i]=work.score(np.delete(p,i,0),rank=True)-state.xor
        for j,(edge,xy,_) in enumerate(targets):
            if not work.open(): return [],targets
            insert_rank[j]=work.score(np.insert(p,edge+1,xy,axis=0),rank=True)-state.xor
    pairs=[(i,z) for i in range(len(p)) for z,(e,_,_) in enumerate(targets) if i not in (e,(e+1)%len(p))]
    if mode=="random_pair":
        rng.shuffle(pairs)
    else:
        pairs.sort(key=lambda iz:donors[iz[0]]+insert_rank[iz[1]])
    return pairs,targets


def exchange(curve,state,work,mode,rng,trace=False):
    k=len(state.p)
    while work.open():
        before=work.count
        pairs,targets=ordered_pairs(curve,state,work,mode,rng)
        work.rounds+=1
        if not pairs or not work.open(): break
        pos=0
        while pos<len(pairs) and work.open():
            # Enumerate a batch against one fixed state. Across batches without a
            # winner, continue through its remaining pool without recomputing scores.
            cutoff=min(work.limit,before+16*k)
            best=state
            choice=None
            while pos<len(pairs) and work.count<cutoff and work.open():
                i,z=pairs[pos]
                pos+=1
                edge,xy,_=targets[z]
                trial=replace_vertex([state.p],0,i,0,edge,xy)[0]
                cost=work.score(trial)
                work.pair_seen+=1
                if cost<best.xor and work.valid(trial):
                    best=State(trial,cost)
                    choice=(i,edge,xy)
            if choice is not None:
                if trace:
                    i,edge,xy=choice
                    work.events.append(dict(donor=int(i),edge=int(edge),xy=xy.tolist(),before=state.p.tolist(),
                                            after=best.p.tolist(),before_xor=state.xor,after_xor=best.xor))
                work.accepted+=1
                state=best
                break
            before=work.count
        else:
            break
    return state


def coordinate(state,work,rng=None,max_cycles=1000):
    k=len(state.p)
    h,w=work.mask.shape
    stopped=False
    cycles=0
    for cycle in range(max_cycles):
        if not work.open(): break
        cycles+=1
        initial_count=work.accepted
        for s,radius in enumerate(RADII):
            indices=np.arange(k)
            if rng is not None: rng.shuffle(indices)
            elif (cycle+s)%2: indices=indices[::-1]
            for j in indices:
                options=[]
                for direction in DIRECTIONS:
                    if not work.open(): break
                    xy=state.p[j]+radius*direction
                    if 0<=xy[0]<w and 0<=xy[1]<h:
                        trial=state.p.copy()
                        trial[j]=xy
                        options.append((work.score(trial),trial))
                for cost,trial in sorted(options,key=lambda a:a[0]):
                    if cost>=state.xor: break
                    if work.valid(trial):
                        state=State(trial,cost)
                        work.accepted+=1
                        break
                if not work.open(): return state,False,cycles
        if initial_count==work.accepted:
            stopped=True
            break
    return state,stopped,cycles


def restart(state,work,rng):
    h,w=work.mask.shape
    for _ in range(6):
        if not work.open(): return state
        trial=state.p.copy()
        idx=rng.choice(len(trial),max(1,len(trial)//6),replace=False)
        for j in idx:
            step=int(rng.choice([1,2,4]))
            trial[j]=np.clip(trial[j]+step*DIRECTIONS[rng.integers(8)],[0,0],[w-1,h-1])
        changed=not np.array_equal(trial,state.p)
        value=work.score(trial)
        if changed and work.valid(trial):
            work.restarts+=1
            return State(trial,value)
    return state


def multi(state,work,rng):
    maximum,deadline=work.limit,work.deadline
    start=perf_counter()
    initial_state=state
    for rep in range(3):
        fraction=(rep+1)/3
        work.limit=int(maximum*fraction) if np.isfinite(maximum) else maximum
        work.deadline=start+(deadline-start)*fraction if np.isfinite(deadline) else deadline
        alternate=initial_state if rep==0 else restart(state,work,rng)
        alt,_,_=coordinate(alternate,work,rng)
        if alt.xor<state.xor: state=alt
    work.limit,work.deadline=maximum,deadline
    return state
