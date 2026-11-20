"""Descriptive checks for the rejected thumbnail and the scope of outer-mask encoding."""
from collections import defaultdict
import numpy as np
from PIL import Image
from study import ROOT,read_csv,save_csv,inputs
from src.codec import decode,silhouette


def thumbnail():
    folder=ROOT/"results/thumbnail"
    rows=read_csv(folder/"per_image.csv")
    vals={(r["id"],r["scale"],r["method"]):r for r in rows}
    ids=sorted({r["id"] for r in rows})
    scales=sorted({r["scale"] for r in rows})
    fixed=sorted({r["method"] for r in rows if r["method"].startswith("fixed_")})
    best=max(fixed,key=lambda m:np.mean([float(r["iou"]) for r in rows if r["method"]==m]))
    paired=[]
    for name in ids:
        def mean(method,key):
            return np.mean([abs(float(vals[name,k,method][key])) for k in scales])
        paired.append(dict(id=name,baseline=best,iou_gain=mean("area_matched","iou")-mean(best,"iou"),
                           abs_area_bias_reduction=mean(best,"area_bias")-mean("area_matched","area_bias")))
    save_csv(folder/"paired_by_source.csv",paired)
    agg=[]
    for metric in ("iou_gain","abs_area_bias_reduction"):
        v=np.array([p[metric] for p in paired])
        idx=np.random.default_rng(37129).integers(len(v),size=(10000,len(v)))
        lo,hi=np.quantile(v[idx].mean(axis=1),[.025,.975])
        agg.append(dict(metric=metric,n=len(v),mean=v.mean(),ci_low=lo,ci_high=hi,
                        improved=int((v>0).sum()),worst_id=ids[v.argmin()],worst=v.min()))
    save_csv(folder/"paired_summary.csv",agg)


def scope():
    folder=ROOT/"results/confirm"
    raw_rows=[]
    for src in read_csv(ROOT/"records/samples.csv"):
        if src["partition"]!="confirm":
            continue
        raw=inputs(src)
        mask,_,meta=silhouette(raw)
        raw=np.asarray(raw==1,np.uint8)
        for k in (16,32):
            for method in ("geometry","raster"):
                out=decode((ROOT/"local/confirm"/src["id"]/f"{k}-{method}.poly").read_bytes())
                overlap=int((raw & out).sum())
                union=int((raw | out).sum())
                raw_rows.append(dict(id=src["id"],k=k,method=method,**meta,
                                     original_iou=overlap/union,original_xor=union-overlap,
                                     exterior_iou=int((mask & out).sum())/int((mask | out).sum())))
    save_csv(folder/"scope_sensitivity.csv",raw_rows)


if __name__=="__main__":
    thumbnail()
    scope()
