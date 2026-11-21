"""One nested RDP approximator, perimeter allocation and separable pixel-error budget DP."""
from dataclasses import dataclass
import heapq
import itertools
import numpy as np
from .maskcodec import Polygon


def hierarchy(points,maximum):
    """Yield the identical closed-ring RDP hierarchy used by both allocators."""
    f=points.astype(float)
    a=int(np.argmax(np.sum((f-f[0])**2,axis=1)))
    p=np.roll(points,-a,axis=0)
    path=np.vstack([p,p[0]]).astype(float)
    n=len(p)
    b=int(np.argmax(np.sum((path-path[0])**2,axis=1)))
    heap=[]
    def split(i,j):
        if j-i<2: return
        v=path[j]-path[i]
        gap=path[i+1:j]-path[i]
        scale=np.clip(gap@v/max(1.,v@v),0.,1.)
        d=np.sum((gap-scale[:,None]*v)**2,axis=1)
        idx=int(d.argmax())
        heapq.heappush(heap,(-d[idx],i,j,i+1+idx))
    split(0,b);split(b,n)
    ids=[0,b]
    for k in range(3,min(n,maximum)+1):
        _,i,j,m=heapq.heappop(heap)
        ids.append(m)
        split(i,m);split(m,j)
        yield k,p[sorted(ids)]


def perimeter_counts(dense,target):
    if not dense: return ()
    cap=np.array(list(map(len,dense)))
    per=np.array([np.linalg.norm(p-np.roll(p,1,axis=0),axis=1).sum() for p in dense])
    lo,hi=0.,max(cap/per)+1
    for _ in range(50):
        mid=(lo+hi)/2
        if np.clip(mid*per,3,cap).sum()<target: lo=mid
        else: hi=mid
    ideals=np.clip((lo+hi)*.5*per,3,cap)
    counts=np.minimum(cap,np.maximum(3,np.floor(ideals+1e-10).astype(int)))
    for j in np.argsort(-(ideals-counts),kind="stable"):
        if counts.sum()>=target: break
        if counts[j]<cap[j]: counts[j]+=1
    assert sum(counts)==target
    return tuple(map(int,counts))


@dataclass
class Level:
    points:np.ndarray
    error:int


def curves(dense,ref_masks,render,target):
    result=[]
    cap=target-3*(len(dense)-1)
    for ring,mask in zip(dense,ref_masks):
        bank={}
        for k,p in hierarchy(ring,cap):
            geom=Polygon(p)
            if not geom.is_valid or not geom.area: continue
            e=int(np.count_nonzero(render.ring(p)!=mask))
            bank[k]=Level(p,e)
        result.append(bank)
    return result


def optimal(banks,target):
    """Exact integer resource allocation over the computed single-ring curves."""
    partial={0:(0,())}
    for i,bank in enumerate(banks):
        nxt={}
        upper=target-3*(len(banks)-1-i)
        for spent,(error,counts) in partial.items():
            for k,lev in bank.items():
                new=spent+k
                if new>upper: break
                val=(error+lev.error,counts+(k,))
                if new not in nxt or val<nxt[new]: nxt[new]=val
        partial=nxt
    return partial.get(target,(None,None))[1]


def candidates(banks,dp,per,target,cfg):
    def admissible(c):
        return c is not None and sum(c)==target and all(k in b for b,k in zip(banks,c))
    bases=[tuple(c) for c in (dp,per) if admissible(c)]
    pool=set(bases)
    if len(banks)==2:
        pool.update((k,target-k) for k in banks[0] if target-k in banks[1])
    else:
        for counts in bases:
            for donor,receiver in itertools.permutations(range(len(banks)),2):
                for step in cfg["transfer_steps"]:
                    trial=list(counts)
                    trial[donor]-=step;trial[receiver]+=step
                    if admissible(trial): pool.add(tuple(trial))
    score=lambda c:sum(b[k].error for b,k in zip(banks,c))
    ordered=sorted(pool,key=lambda c:(score(c),c))
    limit=cfg["allocation_pool"]
    if len(ordered)>limit:
        keep=set(bases+ordered[:limit//2])
        for j in np.linspace(0,len(ordered)-1,limit-len(keep),dtype=int): keep.add(ordered[j])
        # Fill any duplicate indices from the deterministic stratified sample.
        for c in ordered:
            if len(keep)>=limit: break
            keep.add(c)
        ordered=sorted(keep,key=lambda c:(score(c),c))
    return ordered
