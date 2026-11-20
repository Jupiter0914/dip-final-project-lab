"""Paired photo-level statistics, frozen decision and machine-readable evidence."""
import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from study import ROOT, read_csv, save_csv


def bootstrap(x, index):
    return [float(v) for v in np.quantile(x[index].mean(axis=1),[.025,.975])]


def summarize(folder, config, protocol):
    rows=read_csv(folder/"per_image.csv")
    run=json.loads((folder/"run.json").read_text())
    by={(r["id"],int(r["k"]),r["method"]):r for r in rows}
    assert len(by)==len(rows)
    names=sorted({r["id"] for r in rows})
    ks=config["budgets"]
    methods=list(config["methods"])
    assert not run["failures"] and len(names)==run["photos"] and len(rows)==len(names)*len(ks)*(1+len(methods))
    for name in names:
        for k in ks:
            for method in methods:
                assert int(by[name,k,method]["bytes"])==10+4*k
            assert float(by[name,k,"input"]["iou"])==1
    average=[]
    for method in ["input"]+methods:
        for group in ["all"]+ks:
            subset=[r for r in rows if r["method"]==method and (group=="all" or int(r["k"])==group)]
            item=dict(method=method,k=group,n=len(names))
            for key in ["iou","xor_pixels","boundary_f2","bytes","encode_ms","decode_ms"]:
                values=np.array([float(r[key]) for r in subset])
                item[key]=float(values.mean())
                if key in ["encode_ms","decode_ms"]:
                    item["p95_"+key]=float(np.quantile(values,.95))
            average.append(item)
    save_csv(folder/"summary.csv",average)
    source_rows=[]
    aggregates=[]
    for baseline in [m for m in methods if m!="raster"]:
        for group in ["all"]+ks:
            budgets=ks if group=="all" else [group]
            selected=[]
            for name in names:
                pair=defaultdict(list)
                for k in budgets:
                    a,b=by[name,k,"raster"],by[name,k,baseline]
                    wrong_a,wrong_b=int(a["xor_pixels"]),int(b["xor_pixels"])
                    pair["relative_xor_saved"].append((wrong_b-wrong_a)/max(1,wrong_b))
                    pair["pixels_saved"].append(wrong_b-wrong_a)
                    for output,metric in [("iou_gain","iou"),("boundary_gain","boundary_f2"),("extra_ms","encode_ms")]:
                        pair[output].append(float(a[metric])-float(b[metric]))
                item=dict(id=name,breed=by[name,budgets[0],"raster"]["breed"],baseline=baseline,k=group)
                item.update({key:float(np.mean(values)) for key,values in pair.items()})
                selected.append(item)
            source_rows.extend(selected)
            rng=np.random.default_rng(config["bootstrap_seed"])
            index=rng.integers(len(names),size=(config["bootstrap_draws"],len(names)))
            clusters=sorted(set(s["breed"] for s in selected))
            cluster_index=rng.integers(len(clusters),size=(config["bootstrap_draws"],len(clusters)))
            for metric in pair:
                values=np.array([r[metric] for r in selected])
                cluster_means=np.array([np.mean([r[metric] for r in selected if r["breed"]==c]) for c in clusters])
                lo,hi=bootstrap(values,index)
                blo,bhi=bootstrap(cluster_means,cluster_index)
                aggregates.append(dict(baseline=baseline,k=group,metric=metric,n=len(names),
                                       mean=values.mean(),median=np.median(values),ci_low=lo,ci_high=hi,
                                       breed_ci_low=blo,breed_ci_high=bhi,positive=int((values>0).sum()),
                                       tied=int((values==0).sum()),negative=int((values<0).sum()),
                                       worst_id=names[values.argmin()],worst=values.min(),best_id=names[values.argmax()],best=values.max()))
    save_csv(folder/"paired_by_source.csv",source_rows)
    save_csv(folder/"paired_summary.csv",aggregates)
    if not protocol:
        return
    ref=protocol["primary_baseline"]
    cond=protocol["gates"]
    def stat(metric,k="all",base=ref):
        return next(r for r in aggregates if (r["baseline"],r["metric"],r["k"])==(base,metric,k))
    sub=stat("relative_xor_saved")
    timing=next(r for r in average if (r["method"],r["k"])==("raster","all"))
    checks={
        "all_sources_and_bytes":len(names)==protocol["confirmation_n"],
        "mean_relative_xor":sub["mean"]>=cond["mean_relative_xor_min"],
        "paired_ci_positive":sub["ci_low"]>0,
        "iou_effect":stat("iou_gain")["mean"]>=cond["iou_gain_min"],
        "win_fraction":sub["positive"]/len(names)>=cond["win_fraction_min"],
        "both_budgets":all(stat("iou_gain",k)["mean"]>0 for k in ks),
        "other_comparators":all(stat("iou_gain",base=m)["mean"]>0 for m in methods if m not in ("raster",ref)),
        "boundary_tolerance":stat("boundary_gain")["mean"]>=cond["boundary_gain_min"],
        "worst_iou":stat("iou_gain")["worst"]>=cond["worst_iou_min"],
        "encoder_p95":timing["p95_encode_ms"]<=cond["encode_p95_max_ms"],
        "peak_memory":run["peak_working_set_bytes"]<=cond["peak_run_bytes_max"],
    }
    (folder/"decision.json").write_text(json.dumps(dict(passed=bool(all(checks.values())),
        checks={key:bool(v) for key,v in checks.items()},primary_baseline=ref),indent=2),encoding="utf-8")


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("folder",type=Path)
    parser.add_argument("--decision",action="store_true",help="Apply the frozen confirmation thresholds")
    args=parser.parse_args()
    cfg=json.loads((ROOT/"configs/fixed.json").read_text())
    prot=json.loads((ROOT/"configs/protocol.json").read_text()) if args.decision else None
    summarize(args.folder,cfg,prot)
