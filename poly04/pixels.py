"""Independent offline scoring of every distinct delivered output and every matched region."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import struct
import zipfile
import cv2
import numpy as np
from poly03.full_verify import parse,paint,expected_tree
from poly03.maskcodec import extract,Unsupported
from poly02.verify import IndependentScore
from poly02.data import rows,sha
from .study import WORK,RESULTS,config,manifest,load_input

cv2.setNumThreads(1)


class LabelMap:
    """SAUF orders labels by first raster occurrence. The padded exterior is background label 1."""
    def __init__(self,mask):
        padded=np.pad(mask.astype(np.uint8),1)
        self.pairs=[]
        for plane,neigh,first in [(padded,8,1),(1-padded,4,2)]:
            n,lab,stats,_=cv2.connectedComponentsWithStatsWithAlgorithm(plane,neigh,cv2.CV_32S,cv2.CCL_WU)
            self.pairs.append((lab,stats[:,cv2.CC_STAT_AREA].astype(np.int64),first,n))
        fg=self.pairs[0][0];bg=self.pairs[1][0]
        assert bg[0,0]==1
        nb=self.pairs[1][3];links=[]
        for a,b in [(fg[1:],bg[:-1]),(fg[:-1],bg[1:]),(fg[:,1:],bg[:,:-1]),(fg[:,:-1],bg[:,1:])]:
            connected=(a>0)&(b>0)
            links.append(a[connected].astype(np.int64)*nb+b[connected])
        self.adjacency={(int(k//nb),int(k%nb)) for k in np.unique(np.concatenate(links))}


def region_table(ref,pred):
    other=LabelMap(pred)
    out={};mappings=[]
    for kind,a,b in zip(("foreground","hole"),ref.pairs,other.pairs):
        original,ar,first,n=a
        candidate,ap,_,m=b
        if n!=m:raise AssertionError("Changed digital region count")
        # Combine native label maps into one dense contingency table.
        hits=np.bincount((original*m+candidate).ravel(),minlength=n*m).reshape(n,m)
        mapping={}
        for i in range(first,n):
            ids=np.flatnonzero(hits[i,first:])+first
            if len(ids)!=1:raise AssertionError("Missing or multiple matches")
            j=int(ids[0]);inter=int(hits[i,j]);ra=int(ar[i]);pa=int(ap[j])
            assert 2*inter>=min(ra,pa) and j not in mapping.values()
            mapping[i]=j
            out[kind,i]=dict(decoded_id=j,reference_area=ra,decoded_area=pa,intersection=inter,
                  recall=inter/ra,precision=inter/pa,area_ratio=pa/ra,iou=inter/(ra+pa-inter))
        mappings.append(mapping)
    f,b=mappings;b[1]=1
    assert {(f[i],b[j]) for i,j in ref.adjacency}==other.adjacency
    return out


def check_stage(stage):
    cfg=config(stage)
    sources={(s["dataset"],s["id"]):s for s in manifest(cfg)}
    folder=RESULTS/stage
    stored=defaultdict(list)
    for r in rows(folder/"blob_metrics.csv"):stored[r["dataset"],r["id"]].append(r)
    details=defaultdict(dict)
    for r in rows(folder/"regions.csv"):
        key=(r["dataset"],r["id"],r["sha256"]);rid=(r["kind"],int(r["reference_id"]))
        assert rid not in details[key];details[key][rid]=r
    receipt=json.loads((folder/"receipt.json").read_text(encoding="utf-8"))
    archive=WORK/stage/"outputs.zip"
    assert sha(archive.read_bytes())==receipt["outputs_sha256"]
    total=parts=0
    by_digest={}
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None and len(z.namelist())==len(set(z.namelist()))==receipt["stored_blobs"]
        for source,records in sorted(stored.items()):
            raw,_=load_input(sources[source],stage)
            _,parent=extract(raw)
            reference=IndependentScore(raw) if raw.any() else None
            labels=LabelMap(raw)
            for r in records:
                digest=r["sha256"];b=z.read(digest+".pm3")
                assert sha(b)==digest and len(b)==int(r["actual_bytes"])
                shape,ps,h= parse(b)
                assert raw.shape==shape and h==parent and expected_tree(ps,h)
                pred=np.zeros(shape,np.uint8)
                for p in ps: pred^=paint(shape,p)
                values=reference.measure(pred) if reference is not None else dict(xor=0,fp=0,fn=0,iou=1.,bf1=1.,bf2=1.,bf3=1.)
                assert reference is not None or not pred.any()
                for name,val in values.items():
                    if abs(float(r[name])-val)>1e-12: raise AssertionError((source,digest,name))
                components=region_table(labels,pred)
                logged=details[*source,digest]
                assert set(components)==set(logged)
                for rid,nums in components.items():
                    for name,val in nums.items():
                        if abs(val-float(logged[rid][name]))>1e-12:raise AssertionError((source,rid,name))
                    parts+=1
                for name,field in [("min_region_recall","recall"),("min_region_precision","precision"),("min_area_ratio","area_ratio")]:
                    assert abs(min((v[field] for v in components.values()),default=1.)-float(r[name]))<1e-12
                assert sum(v["area_ratio"]<.5 for v in components.values())==int(r["shrunken_regions"])
                by_digest[*source,digest]=(values,len(b));total+=1
    obs=0
    for r in rows(folder/"per_run.csv"):
        if r["status"]!="success":
            assert not r["xor"] and not r["iou"] and not r["sha256"]
            continue
        values,size=by_digest[r["dataset"],r["id"],r["sha256"]]
        assert size==int(r["actual_bytes"])
        assert all(abs(values[name]-float(r[name]))<=1e-12 for name in values)
        obs+=1
    return dict(stage=stage,source_outputs=total,matched_foreground_and_holes=parts,verified_success_observations=obs,
                input_sources=len(sources),independent_boundary="Euclidean distance transform at 1/2/3 pixels",
                independent_regions="SAUF label contingency table and edge adjacency")


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("stage",choices=["dev","confirm"])
    print(json.dumps(check_stage(p.parse_args().stage),indent=2))
