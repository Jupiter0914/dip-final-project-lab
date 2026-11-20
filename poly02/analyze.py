"""Pair sources within each K first. The two primary budgets are averaged inside each source."""
import argparse
import json
from pathlib import Path
import numpy as np
from .data import OUT,CFG,rows,save_rows

PAIRS=[("raster","geometry"),("local_iou","geometry"),("raster","local_iou"),("raster","sm_iou"),
       ("local_iou","sm_iou"),("post_xor","geometry"),("post_xor","raster"),
       ("post_guard","geometry"),("post_guard","post_xor"),("post_guard","local_iou"),
       ("post_guard","raster"),("post_guard","sm_iou")]
FIELDS=["saved_xor","saved_fp","saved_fn","relative_xor","iou_pp","bf1_pp","bf2_pp","bf3_pp","extra_ms"]


def analyze(folder):
    records=rows(folder/"per_image.csv")
    cfg=json.loads(CFG.read_text())
    tab={(r["id"],int(r["k"]),r["method"]):r for r in records}
    if len(tab)!=len(records): raise ValueError("Duplicate image/method/budget")
    ks=sorted({int(r["k"]) for r in records})
    ids=sorted({r["id"] for r in records})
    methods=sorted({r["method"] for r in records})
    aggs=[]
    pairs=[]
    summary=[]
    for case in [*ks,"all"]:
        budgets=ks if case=="all" else [case]
        for method in methods:
            selected=[r for r in records if r["method"]==method and int(r["k"]) in budgets]
            if not selected: continue
            stats=dict(k=case,method=method,rows=len(selected),sources=len({r["id"] for r in selected}))
            for key in ("xor","fp","fn","iou","bf1","bf2","bf3","bytes","encode_ms","decode_ms"):
                v=np.array([float(r[key]) for r in selected])
                stats[key]=float(v.mean())
                if key.endswith("_ms"):
                    stats["median_"+key]=np.median(v)
                    stats["p95_"+key]=np.quantile(v,.95)
            area=sum(int(r["area"]) for r in selected)
            fn=sum(int(r["fn"]) for r in selected)
            fp=sum(int(r["fp"]) for r in selected)
            stats.update(pooled_iou=(area-fn)/(area+fp),pooled_xor_per_ref=(fn+fp)/area,
                         fallback_rows=sum(int(r["fallback"])>0 for r in selected))
            summary.append(stats)
        for method,baseline in PAIRS:
            if method not in methods or baseline not in methods: continue
            subjects=[]
            for name in ids:
                if not all((name,k,method) in tab and (name,k,baseline) in tab for k in budgets): continue
                observations=[]
                for k in budgets:
                    a,b=tab[name,k,method],tab[name,k,baseline]
                    diffs=[int(b[t])-int(a[t]) for t in ("xor","fp","fn")]
                    observations.append(diffs+[diffs[0]/max(int(b["xor"]),1)]+
                                        [100*(float(a[key])-float(b[key])) for key in ("iou","bf1","bf2","bf3")]+
                                        [float(a["encode_ms"])-float(b["encode_ms"])])
                values=np.mean(observations,axis=0)
                subjects.append((name,values))
                pairs.append(dict(id=name,k=case,method=method,baseline=baseline,**dict(zip(FIELDS,values))))
            if not subjects: continue
            names,vals=zip(*subjects)
            array=np.stack(vals)
            rng=np.random.default_rng(cfg["bootstrap_seed"])
            boot=rng.integers(len(names),size=(cfg["bootstrap_draws"],len(names)))
            for j,key in enumerate(FIELDS):
                v=array[:,j]
                lo,hi=np.quantile(v[boot].mean(axis=1),[.025,.975])
                aggs.append(dict(k=case,method=method,baseline=baseline,metric=key,n=len(v),mean=v.mean(),median=np.median(v),
                                 lo=lo,hi=hi,up=int((v>1e-12).sum()),tie=int((abs(v)<=1e-12).sum()),down=int((v< -1e-12).sum()),
                                 worst_id=names[v.argmin()],worst=v.min(),best_id=names[v.argmax()],best=v.max()))
    save_rows(folder/"summary.csv",summary)
    save_rows(folder/"paired.csv",pairs)
    save_rows(folder/"paired_summary.csv",aggs)


def decide(folder):
    from .data import ROOT
    prot=json.loads((ROOT/"configs/poly02/protocol.json").read_text(encoding="utf-8"))
    agg={(r["method"],r["baseline"],r["metric"],r["k"]):r for r in rows(folder/"paired_summary.csv")}
    def get(m,b,metric,k="all",field="mean"): return float(agg[m,b,metric,str(k)][field])
    run=json.loads((folder/"run.json").read_text())
    p=prot["thresholds"]
    ret=get("post_guard","geometry","relative_xor")/get("post_xor","geometry","relative_xor")
    time95=float(next(r["p95_encode_ms"] for r in rows(folder/"summary.csv") if r["method"]=="post_guard" and r["k"]=="all"))
    count=run["sources"]
    checks=dict(complete=(not run["failures"] and count==prot["oxford_n"] and run["rows"]==count*2*len(json.loads(CFG.read_text())["methods"])),
      xor_gain=get("post_guard","geometry","relative_xor")>=p["mean_xor_gain"],
      positive_ci=get("post_guard","geometry","relative_xor",field="lo")>0,
      no_individual_loss=all(get("post_guard","geometry",metric,k,"down")==0 for metric in ("bf2_pp","saved_xor") for k in (16,32)),
      both_k=all(get("post_guard","geometry","relative_xor",k)>0 for k in (16,32)),
      retained=ret>=p["retained"],near_local_iou=get("post_guard","local_iou","iou_pp",field="lo")>=-p["iou_margin_pp"],
      guard_needed=sum(get("post_xor","geometry","bf2_pp",k,"down") for k in (16,32))>0,
      latency=time95<=p["p95_ms"])
    equiv=all(get("raster","local_iou",met,field="lo")>=-margin and get("raster","local_iou",met,field="hi")<=margin
              for met,margin in [("relative_xor",p["direct_relative_margin"]),("iou_pp",p["iou_margin_pp"])])
    decision=dict(primary="new Oxford",checks=checks,passes_all=all(checks.values()),retained_gain=ret,
                  p95_encode_ms=time95,direct_xor_and_iou_within_practical_margins=equiv)
    (folder/"decision.json").write_text(json.dumps(decision,indent=2),encoding="utf-8")
    print(json.dumps(decision))


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("stage",choices=["dev","dev_curve","new","cross","curve"])
    p.add_argument("--decision",action="store_true")
    a=p.parse_args()
    analyze(OUT/a.stage)
    if a.decision: decide(OUT/a.stage)
