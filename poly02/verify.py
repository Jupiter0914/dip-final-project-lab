"""Independent pixel scorer and targeted mechanism checks; replay original POL1 files offline."""
import argparse
import csv
import hashlib
import json
import struct
from fractions import Fraction
from pathlib import Path
import cv2
import numpy as np
from src.codec import simple,encode,decode
from src.baselines import root_contour
from .data import ROOT,REC,OUT,CFG,read_mask,rows,sha,DATA,binary_from_bytes
from .core import exterior,initial,fit,local_search,sequential_iou

cv2.setNumThreads(1)


def reference(raw):
    shapes,_=cv2.findContours(np.uint8(raw!=0),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    out=np.zeros(raw.shape,np.uint8)
    cv2.fillPoly(out,[max(shapes,key=cv2.contourArea)],1,lineType=cv2.LINE_8)
    return out


def surface(mask):
    pad=np.pad(mask.astype(bool),1)
    h,w=mask.shape
    inside=np.logical_and.reduce([pad[i:i+h,j:j+w] for i in range(3) for j in range(3)])
    return (mask.astype(bool)&~inside)


class IndependentScore:
    def __init__(self,target):
        self.target=target.astype(bool)
        self.edge=surface(target)
        self.distance=cv2.distanceTransform(np.uint8(~self.edge),cv2.DIST_L2,cv2.DIST_MASK_PRECISE)

    def measure(self,pred):
        p=pred.astype(bool)
        fp=np.count_nonzero(p & ~self.target)
        fn=np.count_nonzero(self.target & ~p)
        iou=np.count_nonzero(p & self.target)/np.count_nonzero(p | self.target)
        edge=surface(p)
        distance=cv2.distanceTransform(np.uint8(~edge),cv2.DIST_L2,cv2.DIST_MASK_PRECISE)
        out=dict(xor=fp+fn,fp=fp,fn=fn,iou=iou)
        near_ref=self.distance[edge]
        near_pred=distance[self.edge]
        for rad in (1,2,3):
            a=np.count_nonzero(near_ref<=rad)/len(near_ref)
            b=np.count_nonzero(near_pred<=rad)/len(near_pred)
            out[f"bf{rad}"]=2*a*b/(a+b) if a+b else 0
        return out


def draw(mask,vertices):
    cv2.fillPoly(mask,[np.asarray(vertices,np.int32)],1,lineType=cv2.LINE_8)
    return mask


def audit_development():
    v1={(r["id"],r["k"],r["method"]):r for r in rows(ROOT/"results/dev/per_image.csv")}
    checked=0
    for r in rows(OUT/"dev/per_image.csv"):
        key=r["method"] if r["method"]!="grid_dp" else "dp"
        if (r["id"],r["k"],key) in v1:
            assert r["blob_sha256"]==v1[r["id"],r["k"],key]["blob_sha256"]
            checked+=1
    assert checked==36*2*5
    src=next(r for r in rows(REC/"samples.csv") if r["stage"]=="dev")
    mask,c=exterior(read_mask(src),16)
    cfg=json.loads(CFG.read_text())
    audit=IndependentScore(mask)
    moves=[]
    result,_=fit(mask,c,16,"post_guard",cfg,trace=moves)
    assert moves
    rejected=0
    for move in moves:
        old=audit.measure(draw(np.zeros_like(mask),move["before"]))
        trial=audit.measure(draw(np.zeros_like(mask),move["after"]))
        assert move["before_cost"]==old["xor"] and move["trial_cost"]==trial["xor"]<old["xor"]
        assert simple(move["after"]) and abs(move["bf2"]-trial["bf2"])<1e-12
        assert move["accepted"]==(trial["bf2"]>=move["floor"]-1e-12)
        rejected+=not move["accepted"]
    assert np.array_equal(decode(encode(mask.shape,result)),draw(np.zeros_like(mask),result))
    p=root_contour(c)
    ids,_=initial(p,50,0,rdp=True)
    poly=p[ids]
    for _ in (1,2):
        options=[]
        for j in range(len(poly)):
            v=np.delete(poly,j,0)
            if not simple(v): continue
            render=draw(np.zeros_like(mask),v)
            a=int(np.count_nonzero(mask&render))
            b=int(np.count_nonzero(mask|render))
            options.append((-Fraction(a,b),j))
        poly=np.delete(poly,min(options)[1],0)
    actual,_=sequential_iou(mask,p,48,50)
    assert np.array_equal(poly,actual)
    little=np.zeros((12,12),np.uint8)
    little[3:9,3:9]=1
    _,small=exterior(little,8)
    assert len(small)<32
    try: exterior(little,len(small)+1)
    except ValueError: pass
    else: raise AssertionError("Expected K-aware failure")
    exact=np.array([[3,3],[8,3],[8,8],[3,8]],np.int32)
    out,details=local_search(little,exact,[1],"xor",guard=True)
    assert np.array_equal(out,exact) and details["accepted"]==0
    report=dict(v1_byte_identical=checked,real_moves_verified=len(moves),boundary_rejections=rejected,
                sm_exhaustive_deletions=2,short_contour_k8=True,zero_move_allowed=True)
    print(json.dumps(report))
    return report


def replay(stage):
    source={r["id"]:r for r in rows(REC/"samples.csv") if r["stage"]==("new" if stage=="curve" else "dev" if stage=="dev_curve" else stage)}
    table=rows(OUT/stage/"per_image.csv")
    cfg=json.loads(CFG.read_text())
    by_id={}
    for r in table: by_id.setdefault(r["id"],[]).append(r)
    count=0
    per_source=[]
    for name,items in sorted(by_id.items()):
        raw=read_mask(source[name])
        mask=reference(raw)
        score=IndependentScore(mask)
        scores={}
        for r in items:
            k=int(r["k"])
            method=r["method"]
            b=(ROOT/"local/poly02"/stage/name/f"{k}-{method}.poly").read_bytes()
            assert len(b)==int(r["bytes"])==10+4*k and sha(b)==r["blob_sha256"]
            magic,w,h,n=struct.unpack("<4sHHH",b[:10])
            points=np.frombuffer(b,offset=10,dtype="<u2").reshape(-1,2).astype(np.int32)
            assert (magic,h,w,n)==(b"POL1",*mask.shape,k) and simple(points) and ((points>=[0,0])&(points<[w,h])).all()
            values=score.measure(draw(np.zeros_like(mask),points))
            for key,v in values.items():
                assert abs(float(r[key])-v)<1e-12,(stage,name,k,method,key)
            scores[k,method]=values
            count+=1
        gains=[]
        for k in sorted({int(r["k"]) for r in items}):
            if not all((k,m) in scores for m in ("geometry","post_xor","post_guard")): continue
            g=scores[k,"geometry"]
            u=scores[k,"post_xor"]
            p=scores[k,"post_guard"]
            assert p["xor"]<=g["xor"] and u["xor"]<=g["xor"] and p["bf2"]>=g["bf2"]-1e-12
            gains.append((g["xor"]-p["xor"])/max(1,g["xor"]))
        if gains: per_source.append(np.mean(gains))
    v=np.asarray(per_source)
    idx=np.random.default_rng(cfg["bootstrap_seed"]).integers(len(v),size=(cfg["bootstrap_draws"],len(v)))
    lo,hi=np.quantile(v[idx].mean(axis=1),[.025,.975])
    row=next(r for r in rows(OUT/stage/"paired_summary.csv") if r["k"]=="all" and r["method"]=="post_guard" and r["baseline"]=="geometry" and r["metric"]=="relative_xor")
    assert np.allclose([lo,v.mean(),hi],[float(row[t]) for t in ("lo","mean","hi")],atol=1e-12,rtol=0)
    return dict(sources=len(by_id),polygons=count,gain=float(v.mean()),ci=[float(lo),float(hi)])


def replay_pso():
    records=rows(OUT/"pso/trials.csv")
    src={r["id"]:r for r in rows(REC/"samples.csv") if r["stage"]=="dev"}
    coords={(r["id"],r["k"],r["seed"]):r for r in json.loads((OUT/"pso/vertices.json").read_text())}
    checked=0
    for r in records+rows(OUT/"pso/controls.csv"):
        name,k=r["id"],int(r["k"])
        raw=read_mask(src[name]) if name in src else binary_from_bytes((DATA/"upf/Fish-a100.gif").read_bytes(),"MPEG7")
        mask=reference(raw)
        if "seed" in r:
            p=np.array(coords[name,k,int(r["seed"])]["matlab_xy_1based"])-1
            v=np.clip(np.floor(p+.5),[0,0],[mask.shape[1]-1,mask.shape[0]-1]).astype(np.int32)
            if r["status"]!="ok":
                assert not simple(v)
                continue
            file=ROOT/"local/poly02/pso/polygons"/name/f"{k}-{r['seed']}.poly"
            assert encode(mask.shape,v)==file.read_bytes()
        else:
            file=ROOT/"local/poly02/pso/control-polygons"/name/f"{k}-{r['method']}.poly"
        blob=file.read_bytes()
        assert sha(blob)==r["blob_sha256"]
        values=IndependentScore(mask).measure(decode(blob))
        assert all(abs(v-float(r[key]))<1e-12 for key,v in values.items())
        checked+=1
    return checked


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--dev-check",action="store_true")
    args=p.parse_args()
    if args.dev_check:
        audit_development()
    else:
        manifest=ROOT/"POLY02-SHA256.csv"
        if manifest.exists():
            for r in rows(manifest):
                data=(ROOT/r["path"]).read_bytes()
                assert len(data)==int(r["bytes"]) and sha(data)==r["sha256"]
        from .lock import verify
        verify(offline=True)
        print(json.dumps({**{s:replay(s) for s in ["dev","dev_curve","new","cross","curve"]},"pso_and_controls":replay_pso()},indent=2))
