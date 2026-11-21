"""Measure effective reproduction of the unchanged upstream worker on one known multi-ring image."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
from poly02.data import rows,read_mask
from .cgal_bridge import close,simplify
from .full_data import MANIFEST,ROOT
from .maskcodec import extract,pack,decode,digital,correspondence,vector_ok,Renderer,length


def prepare(name):
    row=next(r for r in rows(MANIFEST) if r["id"]==name)
    raw=read_mask(row)
    ring,par=extract(raw)
    return raw,ring,par


def quality(raw,out,par):
    blob=pack(raw.shape,out,par)
    render=Renderer(raw.shape)
    pred=render.combined(out)
    return dict(digest=hashlib.sha256(blob).hexdigest(),xor=int(np.count_nonzero(raw!=pred)),
                vector=vector_ok(out,par),digital=correspondence(digital(raw),digital(pred)))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=ROOT/"local/poly03/cgal_variation/rerun-upstream")
    dest=parser.parse_args().output
    dest.mkdir(parents=True,exist_ok=False)
    name="scottish_terrier_199"
    raw,ring,par=prepare(name)
    target=(128-length(par,0))//4
    results=[]
    cases=rows(MANIFEST)
    for binary_process,offset in [(0,0),(1,0),(2,1),(3,3)]:
        close()
        for warmup in cases[:offset]:
            r,start,pp=prepare(warmup["id"])
            for b in (128,256,512):
                kk=min(sum(map(len,start)),(b-length(pp,0))//4)
                if kk>=3*len(pp): simplify(start,kk)
        for trial in range(6):
            for cost in ("squared","scaled"):
                res,meta=simplify(ring,target,cost=cost)
                results.append(dict(process=binary_process,warmup_sources=offset,repeat=trial,cost=cost,**quality(raw,res,par)))
    close()
    with (dest/"unmodified-worker.csv").open("w",encoding="utf-8",newline="") as f:
        out=csv.DictWriter(f,fieldnames=list(results[0]),lineterminator="\n")
        out.writeheader();out.writerows(results)
    print(name,"K",target,"size",sum(map(len,ring)))
    for cost in ("squared","scaled"):
        r=[v for v in results if v["cost"]==cost]
        print(cost,len(set(v["digest"] for v in r)),sorted(set(v["xor"] for v in r)), sorted(set(v["digital"] for v in r)))


if __name__=="__main__":main()
