"""Input-only, stratified development selection from POLY02 material already seen."""
import hashlib
import itertools
from pathlib import Path
import cv2
import numpy as np
from scipy.spatial import cKDTree
from poly02.data import ROOT,read_mask,rows,save_rows

REC=ROOT/"records/poly03"
OUT=ROOT/"results/poly03/full"
LOCAL=ROOT/"local/poly03/full"
MANIFEST=REC/"full-sources.csv"
def rank(s): return hashlib.sha256(("POLY03-full-dev|"+s).encode()).hexdigest()


def descriptor(raw):
    padded=np.pad(raw,1)
    nf=cv2.connectedComponents(padded,connectivity=8)[0]-1
    nh=cv2.connectedComponents(1-padded,connectivity=4)[0]-2
    rings,_=cv2.findContours(raw,cv2.RETR_TREE,cv2.CHAIN_APPROX_NONE)
    points=[p.reshape(-1,2) for p in rings]
    near=False
    for a,b in itertools.combinations(points,2):
        sep=np.maximum(a.min(0)-b.max(0),b.min(0)-a.max(0))
        if np.any(sep>3): continue
        if np.min(cKDTree(a).query(b,k=1)[0])<=3:
            near=True
            break
    stratum="near" if near else "holes" if nh else "components" if nf>1 else "simple"
    return dict(components=nf,holes=nh,near=int(near),stratum=stratum)


def main():
    pool=[]
    for r in rows(ROOT/"records/poly02/samples.csv"):
        raw=read_mask(r)
        pool.append({**r,**descriptor(raw),"selection_hash":rank(r["dataset"]+"/"+r["id"])})
    chosen=[]
    for s in ("near","holes","components","simple"):
        group=sorted((r for r in pool if r["stratum"]==s),key=lambda r:r["selection_hash"])
        # Aim for five Oxford and three MPEG in each stratum. Fill shortages by hash.
        take=[r for r in group if r["dataset"]=="Oxford"][:5]+[r for r in group if r["dataset"]=="MPEG7"][:3]
        take.extend([r for r in group if r not in take][:8-len(take)])
        chosen.extend(take)
    if len(chosen)<32:
        chosen.extend(sorted((r for r in pool if r not in chosen),key=lambda r:r["selection_hash"])[:32-len(chosen)])
    assert len(chosen)==32 and len({r["sha256"] for r in chosen})==32
    REC.mkdir(parents=True,exist_ok=True)
    save_rows(REC/"known-pool.csv",pool)
    save_rows(MANIFEST,chosen)
    print([(s,len([r for r in group if r["stratum"]==s])) for group in (pool,chosen) for s in ("near","holes","components","simple")])
    print([(r["id"],r["components"],r["holes"]) for r in chosen])


if __name__=="__main__": main()
