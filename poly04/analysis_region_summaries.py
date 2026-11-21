"""Descriptive structure costs. Every per-region record remains tied to one source identity."""
from collections import defaultdict
import numpy as np
from .analysis import read_rows, write_rows, average_sessions

KINDS=("foreground","hole")


def area_band(area):
    for ceiling in (16,64,256):
        if area<=ceiling:return {16:"1-16",64:"17-64",256:"65-256"}[ceiling]
    return "257+"


def region_index(path):
    blobs=defaultdict(dict)
    ref_areas={}
    for r in read_rows(path):
        key=r["dataset"],r["id"],r["sha256"]
        region=(r["kind"],int(r["reference_id"]))
        if region[0] not in KINDS or region in blobs[key]:raise ValueError(f"Repeated or unknown region: {key}, {region}")
        a,b,h=(int(r[k]) for k in ("reference_area","decoded_area","intersection"))
        if not(0<h<=min(a,b) and 2*h>=min(a,b)):raise ValueError(f"Impossible region/overlap: {key}, {region}")
        if ref_areas.setdefault((*key[:2],*region),a)!=a:raise ValueError(f"Reference area changes: {key}, {region}")
        exact=(h/a,h/b,b/a,h/(a+b-h))
        if any(abs(float(r[k])-v)>1e-12 for k,v in zip(("recall","precision","area_ratio","iou"),exact)):
            raise ValueError(f"Region score inconsistent with its counts: {key}, {region}")
        blobs[key][region]=dict(area=a,size=b,hit=h,recall=exact[0],precision=exact[1],ratio=exact[2],iou=exact[3])
    expected=defaultdict(set)
    for ds,name,kind,ri in ref_areas:expected[ds,name].add((kind,ri))
    for key,records in blobs.items():
        if set(records)!=expected[key[:2]]:raise ValueError(f"Region identity missing for blob {key}")
    return blobs


def score_one(regions):
    result={}
    for kind in KINDS:
        kept=[(i,r) for (k,i),r in regions.items() if k==kind]
        if not kept:continue
        lowest=min(kept,key=lambda x:(x[1]["recall"],x[0]))
        smallest=min(kept,key=lambda x:(x[1]["ratio"],x[0]))
        result[kind]=dict(n_regions=len(kept),min_recall=lowest[1]["recall"],
                min_precision=min(r["precision"] for _,r in kept),min_area_ratio=smallest[1]["ratio"],
                any_severe_shrink=int(any(r["ratio"]<.5 for _,r in kept)),
                any_severe_coverage=int(any(r["recall"]<.5 for _,r in kept)),
                worst_recall_id=lowest[0],worst_recall_ref_area=lowest[1]["area"],
                worst_ratio_id=smallest[0],worst_ratio_ref_area=smallest[1]["area"])
    return result


def diagnostic_case(row,reason):
    return dict(reason=reason,**row)


def report_regions(folder,table,sources,primary_pair,output=None):
    cache=region_index(folder/"regions.csv")
    computed={k:score_one(v) for k,v in cache.items()}
    vals=defaultdict(list)
    # Do not count polygons, duplicate timed checkpoints or holes as independent sources.
    for (ds,name,session,rep,budget,deadline,method),r in table.items():
        if r["status"]!="success":continue
        key=ds,name,r["sha256"]
        if key not in computed:
            if int(sources[ds,name].get("rings",-1))==0: continue
            raise ValueError(f"Missing region records for delivered output {key}")
        for kind,stats in computed[key].items():
            vals[ds,name,budget,deadline,method,kind].append((session,rep,r["sha256"],stats))
    source_rows=[]
    for (ds,name,b,t,m,kind),series in sorted(vals.items()):
        payload_keys=("min_recall","min_precision","min_area_ratio","any_severe_shrink","any_severe_coverage")
        vector=average_sessions([(s,[v[q] for q in payload_keys]) for s,_,_,v in series])
        low=min(series,key=lambda x:(x[3]["min_recall"],x[0],x[1]))
        small=min(series,key=lambda x:(x[3]["min_area_ratio"],x[0],x[1]))
        source_rows.append(dict(dataset=ds,id=name,budget=b,deadline_ms=t,method=m,kind=kind,
            n_regions=series[0][3]["n_regions"],valid_runs=len(series),**dict(zip(payload_keys,vector)),
            worst_observed_recall=low[3]["min_recall"],worst_recall_id=low[3]["worst_recall_id"],
            recall_reference_area=low[3]["worst_recall_ref_area"],worst_recall_file=low[2],
            worst_observed_ratio=small[3]["min_area_ratio"],worst_ratio_id=small[3]["worst_ratio_id"],
            ratio_reference_area=small[3]["worst_ratio_ref_area"],worst_ratio_file=small[2]))
    grouped=defaultdict(list)
    for row in source_rows:
        key=tuple(row[k] for k in ("dataset","budget","deadline_ms","method","kind"))
        grouped[key].append(row)
    summaries=[]
    for key,group in sorted(grouped.items()):
        ds,b,t,m,kind=key
        bad=min(group,key=lambda x:(x["worst_observed_recall"],x["id"],x["worst_recall_id"]))
        small=min(group,key=lambda x:(x["worst_observed_ratio"],x["id"],x["worst_ratio_id"]))
        summaries.append(dict(dataset=ds,budget=b,deadline_ms=t,method=m,kind=kind,
            sources_with_region=len(group),distinct_reference_regions=sum(q["n_regions"] for q in group),
            photo_mean_min_recall=np.mean([q["min_recall"] for q in group]),
            photo_mean_min_precision=np.mean([q["min_precision"] for q in group]),
            photo_mean_min_area_ratio=np.mean([q["min_area_ratio"] for q in group]),
            sources_ever_shrink_lt_half=sum(q["any_severe_shrink"]>0 for q in group),
            sources_ever_recall_lt_half=sum(q["any_severe_coverage"]>0 for q in group),
            worst_observed_recall=bad["worst_observed_recall"],worst_recall_source=bad["id"],
            worst_recall_id=bad["worst_recall_id"],worst_recall_reference_area=bad["recall_reference_area"],
            worst_observed_area_ratio=small["worst_observed_ratio"],worst_ratio_source=small["id"],
            worst_ratio_id=small["worst_ratio_id"],worst_ratio_reference_area=small["ratio_reference_area"]))
    a_method,b_method=primary_pair
    paired=defaultdict(list)
    for (ds,name,sess,rep,b,t,m),a in table.items():
        if (b,t,m)!=(256,100,a_method) or a["status"]!="success" or int(sources[ds,name].get("rings",-1))<2:continue
        other=table.get((ds,name,sess,rep,b,t,b_method))
        if other is None or other["status"]!="success":continue
        x=cache[ds,name,a["sha256"]]; y=cache[ds,name,other["sha256"]]
        if x.keys()!=y.keys():raise ValueError(f"Output identity mismatch for {ds}/{name}")
        for (kind,ri),ma in x.items():
            mb=y[kind,ri]
            sz=ma["area"]
            if mb["area"]!=sz:raise ValueError("Unequal reference area")
            delta=int(other["xor"])-int(a["xor"])
            paired[ds,name,kind,ri].append(dict(dataset=ds,id=name,budget=b,deadline_ms=t,session=sess,rep=rep,
                 kind=kind,reference_id=ri,area_band=area_band(sz),reference_area=sz,
                 method=a_method,baseline=b_method,global_xor_gain=delta,method_xor=int(a["xor"]),baseline_xor=int(other["xor"]),
                 method_sha256=a["sha256"],baseline_sha256=other["sha256"],
                 method_area=ma["size"],baseline_area=mb["size"],method_hit=ma["hit"],baseline_hit=mb["hit"],
                 method_recall=ma["recall"],baseline_recall=mb["recall"],recall_gain_pp=100*(ma["recall"]-mb["recall"]),
                 precision_gain_pp=100*(ma["precision"]-mb["precision"]),
                 method_area_ratio=ma["ratio"],baseline_area_ratio=mb["ratio"],area_ratio_change=ma["ratio"]-mb["ratio"],
                 severe_abs=int(ma["ratio"]<.5),new_severe=int(ma["ratio"]<.5<=mb["ratio"]),
                 half_baseline=int(ma["size"]*2<mb["size"])))
    paired_source=[]
    conflict=defaultdict(list)
    for (ds,name,kind,ri),items in sorted(paired.items()):
        metrics=("global_xor_gain","method_recall","baseline_recall","recall_gain_pp","precision_gain_pp","method_area_ratio","baseline_area_ratio","area_ratio_change","severe_abs","new_severe","half_baseline")
        avg=average_sessions([(r["session"],[r[k] for k in metrics]) for r in items])
        ref=items[0]
        summary=dict(dataset=ds,id=name,kind=kind,reference_id=ri,reference_area=ref["reference_area"],area_band=ref["area_band"],
                     source_common_runs=len(items),method=a_method,baseline=b_method,**dict(zip(metrics,avg)))
        paired_source.append(summary)
        if summary["global_xor_gain"]>0:
            for r in items:
                if r["global_xor_gain"]>0 and r["recall_gain_pp"]<0:
                    conflict[ds].append(r)
    cases=[]
    for ds in sorted({key[0] for key in table}):
        candidates=conflict[ds]
        kinds=[("severe_new_small_and_lower_coverage",[r for r in candidates if r["reference_area"]<=64 and r["new_severe"]]),
               ("lower_small_region_coverage",[r for r in candidates if r["reference_area"]<=64]),
               ("lower_region_coverage",candidates)]
        for reason,items in kinds:
            if not items:continue
            winner=min(items,key=lambda r:(r["recall_gain_pp"],r["area_ratio_change"],r["id"],r["kind"],r["reference_id"],r["session"],r["rep"]))
            cases.append(diagnostic_case(winner,reason))
        for kind in KINDS:
            worst=[s for s in summaries if s["dataset"]==ds and (s["budget"],s["deadline_ms"],s["method"],s["kind"])==(256,100,a_method,kind)]
            if worst:
                r=worst[0]
                cases.append(dict(reason="worst_observed_reference_area_ratio",dataset=ds,kind=kind,id=r["worst_ratio_source"],reference_id=r["worst_ratio_id"],
                                  reference_area=r["worst_ratio_reference_area"],method=a_method,method_area_ratio=r["worst_observed_area_ratio"]))
    out=output if output is not None else folder/"analysis"
    write_rows(out/"regions_by_source.csv",source_rows)
    write_rows(out/"regions_summary.csv",summaries)
    write_rows(out/"regions_paired.csv",paired_source)
    write_rows(out/"regions_cases.csv",cases)
