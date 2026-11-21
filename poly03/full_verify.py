"""Package small actual outputs or independently audit full-mask decoded pixels and identities."""
import argparse
import csv
import hashlib
import io
import itertools
import json
import struct
import zipfile
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
import cv2
import numpy as np
from scipy import ndimage
from .maskcodec import extract,Polygon,decode,length,Unsupported
from .allocation import hierarchy
from .repair import ordered_allocations
from .full_data import ROOT,OUT,LOCAL,MANIFEST,REC
from poly02.data import rows,read_mask

ARCHIVE=OUT/"outputs.zip"
cv2.setNumThreads(1)


def read_records():
    yield from (("main",r) for r in rows(OUT/"per_image.csv"))
    yield from (("repair",r) for r in rows(ROOT/"results/poly03/feasibility/per_image.csv"))
    yield from (("repeat",r) for r in rows(ROOT/"results/poly03/repetition/per_image.csv"))
    yield from (("phase",r) for r in rows(ROOT/"results/poly03/phase/per_image.csv"))
    for version in ("time_full","time_fair"):
        yield from ((version,r) for r in rows(ROOT/f"results/poly03/{version}/checkpoints.csv"))


def location(stage,row):
    if stage in ("time_full","time_fair"):
        name=row["blob_sha256"]+".pm3"
        return "timed/"+name,LOCAL/"timed"/name,row["blob_sha256"]
    name=row.get("blob","")
    if name and stage=="repeat":
        # Distinct names only for official CGAL process repeats, which may break ties differently.
        key=("repeat/" if row["method"].startswith("cgal_") else "results/")+name
        return key,ROOT/"local/poly03/full-accounted-repeat/blobs"/name,row["sha256"]
    if name:return "results/"+name,LOCAL/"blobs"/name,row["sha256"]
    return None,None,None


def pack_outputs():
    seen={}
    with zipfile.ZipFile(ARCHIVE,"w") as z:
        for stage,row in read_records():
            name,p,digest=location(stage,row)
            if name is None:continue
            if name in seen:
                assert seen[name]==digest
                continue
            raw=p.read_bytes()
            assert hashlib.sha256(raw).hexdigest()==digest
            z.writestr(zipfile.ZipInfo(name,(2020,1,1,0,0,0)),raw,compress_type=zipfile.ZIP_DEFLATED)
            seen[name]=digest
    print(len(seen),"unique file paths; sha256",hashlib.sha256(ARCHIVE.read_bytes()).hexdigest())


def parse(blob):
    magic,w,h,n=struct.unpack_from("<4sHHH",blob)
    assert magic==b"PM31" and 0<h<=16382 and 0<w<=16382
    pos=10;rings=[];par=[]
    for i in range(n):
        parent,k=struct.unpack_from("<hH",blob,pos);pos+=4
        assert -1<=parent<i and k>=3
        v=np.frombuffer(blob,"<u2",count=2*k,offset=pos).reshape(-1,2).astype(np.int32);pos+=4*k
        assert np.all(v<=[4*w+4,4*h+4])
        rings.append(v);par.append(parent)
    assert pos==len(blob)
    return (h,w),rings,par


def paint(shape,p):
    h,w=shape
    expanded=np.zeros((h*4+5,w*4+5),np.uint8)
    cv2.drawContours(expanded,[p],0,1,cv2.FILLED,lineType=cv2.LINE_8)
    return np.ascontiguousarray(expanded[4:4*h+1:4,4:4*w+1:4])


def expected_tree(rings,par):
    shapes=[Polygon(p) for p in rings]
    if not all(q.is_valid and q.area>0 for q in shapes):return False
    parent=[-1]*len(shapes)
    for i,q in enumerate(shapes):
        outer=[]
        for j,p in enumerate(shapes):
            if i==j:continue
            if q.boundary.intersects(p.boundary):return False
            if p.area>q.area and p.contains(q.representative_point()):outer.append(j)
        if outer:parent[i]=min(outer,key=lambda j:shapes[j].area)
    return parent==list(par)


CROSS=ndimage.generate_binary_structure(2,1)
EIGHT=np.ones((3,3),bool)


def components(mask):
    pad=np.pad(mask.astype(bool),1)
    a,na=ndimage.label(pad,EIGHT);b,nb=ndimage.label(~pad,CROSS)
    edges=set()
    for i in range(1,na+1):
        edges.update((i,int(j)) for j in np.unique(b[ndimage.binary_dilation(a==i,structure=CROSS)]) if j)
    return a,b,na,nb-1,edges


def label_matches(a,b,src,dst):
    inv={}
    for i in src:
        ys,xs=np.nonzero(a==i)
        ids,counts=np.unique(b[ys,xs],return_counts=True)
        hits=[(int(j),int(c)) for j,c in zip(ids,counts) if j in dst]
        if len(hits)!=1:return None
        j,c=hits[0]
        if j in inv.values() or 2*c<min(len(xs),np.count_nonzero(b==j)):return None
        inv[i]=j
    return inv if set(inv.values())==set(dst) else None


def identity(ref,mask):
    a,b,n,h,edges=ref
    u,v,m,g,other=components(mask)
    if (n,h)!=(m,g):return "digital_counts"
    f=label_matches(a,u,range(1,n+1),range(1,m+1))
    holes=label_matches(b,v,range(2,h+2),range(2,g+2))
    if f is None or holes is None:return "digital_overlap"
    holes[1]=1
    return "ok" if {(f[i],holes[j]) for i,j in edges}==other else "digital_adjacency"


def check():
    masks={s["id"]:read_mask(s) for s in rows(MANIFEST)}
    labels={k:components(m) for k,m in masks.items()}
    dense={k:extract(m) for k,m in masks.items()}
    for version in ("time_full","time_fair"):
        ch=rows(ROOT/f"results/poly03/{version}/checkpoints.csv")
        lut=defaultdict(list)
        for r in ch:lut[r["id"],r["rep"],r["method"]].append(r)
        for r in rows(ROOT/f"results/poly03/{version}/per_image.csv"):
            eligible=[v for v in lut[r["id"],r["rep"],r["method"]] if float(v["ready_ms"])<=int(r["deadline_ms"])]
            if eligible:assert r["status"]=="success" and r["blob_sha256"]==eligible[-1]["blob_sha256"]
            else:assert r["status"]!="success"
    count=0;files=set();cache={}
    with zipfile.ZipFile(ARCHIVE) as z:
        assert z.testzip() is None
        for stage,r in read_records():
            name,_,digest=location(stage,r)
            raw=masks[r["id"]]
            rings0,parent=dense[r["id"]]
            if name is None:
                if r["status"]=="below_proved_lower_bound":assert int(r["budget"])<10+16*len(parent)
                else:assert r["status"] in ("search_no_valid_output","unsupported_representation")
                continue
            blob=z.read(name);files.add(name)
            assert hashlib.sha256(blob).hexdigest()==digest
            cachekey=(r["id"],digest)
            if cachekey not in cache:
                shape,ps,par=parse(blob)
                assert raw.shape==shape and par==parent
                pred=np.zeros(shape,np.uint8)
                for q in ps:pred=np.logical_xor(pred,paint(shape,q))
                vector=expected_tree(ps,par)
                struct_result=identity(labels[r["id"]],pred)
                f=int(np.count_nonzero(pred&~raw.astype(bool)));h=int(np.count_nonzero(raw&~pred.astype(bool)))
                hit=int(np.count_nonzero(raw&pred))
                iou=hit/(hit+f+h) if hit+f+h else 1.
                cache[cachekey]=(vector,struct_result,f+h,f,h,iou)
            vector,structure,xor,fp,fn,iou=cache[cachekey]
            if r.get("attempt_xor"):assert xor==int(r["attempt_xor"])
            if r.get("digital_check"):assert structure==r["digital_check"]
            if r.get("vector_check"):assert vector==(r["vector_check"]=="ok")
            if not r.get("status") or r.get("status")=="success":
                assert vector and structure=="ok" and len(blob)==int(r["file_bytes"])
                assert xor==int(r["xor"]) and abs(iou-float(r["iou"]))<1e-12
                if r.get("fp"): assert fp==int(r["fp"]) and fn==int(r["fn"])
            count+=1
        assert files==set(z.namelist())
    candidate_count=0
    by=defaultdict(list)
    for log in rows(OUT/"allocation_candidates.csv"): by[log["id"]].append(log)
    for name,group in by.items():
        mask=masks[name];rings,par=dense[name]
        full_masks=[paint(mask.shape,p) for p in rings]
        counts=[tuple(map(int,r["counts"].split(","))) for r in group]
        wanted=[set(c[i] for c in counts) for i in range(len(rings))]
        banks=[{n:(p,paint(mask.shape,p)) for n,p in hierarchy(src,max(needed)) if n in needed}
               for src,needed in zip(rings,wanted)]
        for r,c in zip(group,counts):
            opts=[b[k] for b,k in zip(banks,c)]
            refsum=sum(int(np.count_nonzero(pred!=gold)) for (_,pred),gold in zip(opts,full_masks))
            whole=np.logical_xor.reduce([p for _,p in opts],axis=0)
            assert refsum==int(r["additive_xor"]) and int(np.count_nonzero(whole!=mask))==int(r["whole_xor"])
            assert expected_tree([v for v,_ in opts],par)==(r["vector"]=="ok")
            assert identity(labels[name],whole)==r["digital"]
            candidate_count+=1
    banks=[{k:SimpleNamespace(error=int((k*k+i)%7)) for k in [3,4,5,6]} for i in range(4)]
    brute=sorted([c for c in itertools.product(*banks) if sum(c)==18],key=lambda c:(sum(b[k].error for b,k in zip(banks,c)),c))
    assert list(ordered_allocations(banks,18))==brute
    return dict(sources=len(masks),scored_rows=count,unique_paths=len(files),unique_source_and_bytes=len(cache),
                independent_allocation_candidates=candidate_count,exhaustive_k_best_fixture=len(brute))


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=["pack","audit"])
    a=p.parse_args()
    if a.action=="pack":pack_outputs()
    else:print(json.dumps(check(),indent=2))
