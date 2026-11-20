"""Offline cross-check using all shipped trimaps, polygon bytes and a separate pixel scorer."""
import csv
import hashlib
import json
import struct
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.codec import silhouette, encode, simple
from src.method import fit


def rows(path):
    with path.open(encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def as_reference(raw):
    binary=(raw==1).astype(np.uint8)
    contours,_=cv2.findContours(binary,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    reference=np.zeros(binary.shape,np.uint8)
    cv2.fillPoly(reference,[max(contours,key=cv2.contourArea)],1,lineType=cv2.LINE_8)
    return reference


def boundary(mask):
    padded=np.pad(mask.astype(bool),1)
    interior=np.logical_and.reduce([padded[y:y+mask.shape[0],x:x+mask.shape[1]]
        for y in range(3) for x in range(3)])
    return (mask.astype(bool) & ~interior).astype(np.uint8)


def independent_metrics(target, out):
    fp=int(np.count_nonzero((target==0)&(out==1)))
    fn=int(np.count_nonzero((target==1)&(out==0)))
    inside=int(np.count_nonzero(target))-fn
    iou=inside/(inside+fp+fn)
    a,b=boundary(target),boundary(out)
    # Integer disk dilation is equivalent to Euclidean matching within two pixels.
    yy,xx=np.ogrid[-2:3,-2:3]
    footprint=np.asarray(xx*xx+yy*yy<=4,np.uint8)
    recall=np.count_nonzero(a & cv2.dilate(b,footprint))/max(int(a.sum()),1)
    precision=np.count_nonzero(b & cv2.dilate(a,footprint))/max(int(b.sum()),1)
    return fp,fn,iou,2*recall*precision/max(recall+precision,1e-20)


def main():
    cv2.setNumThreads(1)
    manifest=ROOT/"REVIEW-SHA256.csv"
    if manifest.exists():
        for entry in rows(manifest):
            raw=(ROOT/entry["path"]).read_bytes()
            assert len(raw)==int(entry["bytes"]) and sha(raw)==entry["sha256"],entry["path"]
    for path,expected in json.loads((ROOT/"records/freeze-lock.json").read_text(encoding="utf-8")).items():
        assert sha((ROOT/path).read_bytes().replace(b"\r\n",b"\n"))==expected,path
    cfg=json.loads((ROOT/"configs/fixed.json").read_text(encoding="utf-8"))
    protocol=json.loads((ROOT/"configs/protocol.json").read_text(encoding="utf-8"))
    source={r["id"]:r for r in rows(ROOT/"records/samples.csv")}
    exemplar={r["id"] for r in rows(ROOT/"results/cases.csv")}
    counts=defaultdict(int)
    output={}
    for stage in ("dev","confirm"):
        table=rows(ROOT/"results"/stage/"per_image.csv")
        by_name=defaultdict(list)
        for r in table:
            by_name[r["id"]].append(r)
        per_source=[]
        for name,records in sorted(by_name.items()):
            path=ROOT/"data/trimaps"/(name+".png")
            assert sha(path.read_bytes())==source[name]["sha256"]
            with Image.open(path) as im:
                raw=np.asarray(im)
            target=as_reference(raw)
            errors={}
            counts["sources"]+=1
            for r in records:
                method,k=r["method"],int(r["k"])
                if method=="input":
                    assert float(r["iou"])==1.0 and int(r["xor_pixels"])==0
                    continue
                blob=(ROOT/"local"/stage/name/f"{k}-{method}.poly").read_bytes()
                assert sha(blob)==r["blob_sha256"] and len(blob)==int(r["bytes"])==10+4*k
                magic,w,h,n=struct.unpack("<4sHHH",blob[:10])
                assert magic==b"POL1" and (h,w)==target.shape and n==k
                points=np.frombuffer(blob[10:],dtype="<u2").reshape((-1,2)).astype(np.int32)
                assert simple(points) and np.all(points>=0) and np.all(points<[w,h])
                out=np.zeros_like(target)
                cv2.fillPoly(out,[points],1,lineType=cv2.LINE_8)
                fp,fn,iou,f=independent_metrics(target,out)
                assert fp==int(r["fp"]) and fn==int(r["fn"]) and fp+fn==int(r["xor_pixels"]),(name,k,method)
                assert abs(iou-float(r["iou"]))<1e-12 and abs(f-float(r["boundary_f2"]))<1e-12,(name,k,method)
                counts["polygons"]+=1
                errors[k,method]=(fp+fn,iou)
                if stage=="confirm" and name in exemplar and method in ("raster",protocol["primary_baseline"]):
                    mask,c,_=silhouette(raw)
                    v,_=fit(mask,c,k,method,**cfg["methods"][method])
                    assert encode(mask.shape,v)==blob,(name,k,method)
                    counts["refitted"]+=1
            gains=[]
            for k in cfg["budgets"]:
                before=errors[k,protocol["primary_baseline"]][0]
                after=errors[k,"raster"][0]
                gains.append((before-after)/max(before,1))
            per_source.append(float(np.mean(gains)))
        values=np.array(per_source)
        rng=np.random.default_rng(cfg["bootstrap_seed"])
        means=values[rng.integers(len(values),size=(cfg["bootstrap_draws"],len(values)))].mean(axis=1)
        low,high=np.quantile(means,[.025,.975])
        summary=next(r for r in rows(ROOT/"results"/stage/"paired_summary.csv") if r["k"]=="all" and
                     r["baseline"]==protocol["primary_baseline"] and r["metric"]=="relative_xor_saved")
        for expected,actual in [(summary["mean"],values.mean()),(summary["ci_low"],low),(summary["ci_high"],high)]:
            assert abs(float(expected)-actual)<1e-12
        output[stage]={"sources":len(values),"mean_relative_xor_saved":values.mean(),"ci95":[low,high],
                       "improved":int(np.count_nonzero(values>0))}
    assert counts["sources"]==136 and counts["polygons"]==1632
    print(json.dumps(dict(verified=dict(counts),statistics=output),indent=2))


if __name__=="__main__":
    main()
