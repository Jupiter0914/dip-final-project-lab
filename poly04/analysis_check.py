"""Small contract checks for identity matching, paired inference, late delivery and roster auditing."""
from pathlib import Path
import hashlib
import json
import numpy as np

from .analysis import analyze,read_rows,write_rows
from .analysis_regions import RegionReference
from .prepare import prepare_input
from poly03.maskcodec import pack


def regions():
    raw=np.zeros((18,24),np.uint8)
    raw[1:14,1:14]=1
    raw[4:8,4:8]=0
    raw[6:10,17:22]=1
    changed=raw.copy()
    changed[6:10,18:22]=0
    changed[4:8,4:8]=1
    changed[5:7,5:7]=0
    reference=RegionReference(raw)
    diagnosis=reference.evaluate(changed)
    assert diagnosis["status"]=="success"
    tiny=next(r for r in diagnosis["components"] if r["kind"]=="foreground" and r["reference_area"]==20)
    assert (tiny["decoded_area"],tiny["intersection"],tiny["recall"],tiny["precision"])==(4,4,.2,1.)
    hole=next(r for r in diagnosis["components"] if r["kind"]=="hole")
    assert (hole["reference_area"],hole["decoded_area"],hole["recall"],hole["area_ratio"])==(16,4,.25,.25)
    displaced=raw.copy()
    displaced[6:10,17:22]=0
    displaced[14:17,17:22]=1
    assert reference.evaluate(displaced)["reason"]=="digital_overlap"
    prep=prepare_input(raw)
    blob=pack(raw.shape,prep.dense,prep.parents)
    perfect=reference.evaluate_blob(blob)
    assert perfect["status"]=="success" and all(r["recall"]==r["precision"]==1 for r in perfect["components"])
    unsupported=RegionReference(np.zeros((1,16383),np.uint8)).evaluate(None)
    assert unsupported["status"]=="unsupported_representation"
    assert RegionReference(np.zeros((1,1),np.uint8)).evaluate(np.zeros((1,1),np.uint8))["components"]==[]
    return dict(foreground_coverage=tiny["recall"],hole_coverage=hole["recall"],perfect_regions=len(perfect["components"]),
                swapped_rejected=True,empty_and_unsupported_handled=True)


def inference(folder):
    folder=Path(folder)
    folder.mkdir(parents=True,exist_ok=False)
    roster=[dict(dataset="Oxford",id=n,stratum=s,rings=k,group=n,category=n) for n,s,k in
            [("a","holes",2),("b","components",2),("c","simple",1),("d","holes",3)]]
    methods=("within_full","cross")
    settings=dict(samples=roster,session_ids=["S1","S2","S3"],rep_ids=[1,2],
                  conditions=[dict(budget=256,methods=list(methods),deadlines_ms=[100,200])],comparisons=[["cross","within_full"]])
    records=[]
    for source in roster:
        name=source["id"]
        for sess in settings["session_ids"]:
            for rep in settings["rep_ids"]:
                for m in methods:
                    complete=name!="d"
                    delay=140 if (m=="cross" and name=="a" and (sess!="S1" or rep==2)) else 55
                    for deadline in (100,200):
                        st=("success" if delay<=deadline else "not_ready") if complete else ("not_ready" if deadline<120 else "search_no_valid_output")
                        r=dict(**source,session=sess,rep=rep,budget=256,deadline_ms=deadline,method=m,status=st,
                               final_status="success" if complete else "search_no_valid_output",end_ms=215 if complete else 120)
                        if st=="success":
                            wrong=12 if m=="within_full" else {"a":8,"b":14,"c":12}[name]
                            blob=hashlib.sha256(f"{name}{wrong}".encode()).hexdigest()
                            r.update(xor=wrong,fp=wrong,fn=0,iou=.9,bf1=.80,bf2=.85,bf3=.9,serialized_ms=delay-1,delivered_ms=delay,
                                     sha256=blob,actual_bytes=74,round=2,proposed_pairs=48,accepted_moves=2,cross_moves=int(m=="cross"))
                        records.append(r)
    region_rows=[]
    hashes={}
    for row in records:
        if row["status"]!="success" or (row["id"],row["sha256"]) in hashes:continue
        n,m=row["id"],row["method"]
        hashes[(n,row["sha256"])]=True
        # Analytic counts: source a's smaller object loses three covered pixels while global XOR improves.
        areas=[(100,100+int(row["xor"]),100)]
        if n in ("a","b"):
            if n=="a" and m=="cross": areas=[(100,105,100),(4,1,1)]
            else: areas.append((4,4,4))
        for ri,(ref,decoded,hit) in enumerate(areas,1):
            region_rows.append(dict(dataset="Oxford",id=n,sha256=row["sha256"],kind="foreground",reference_id=ri,
                      decoded_id=ri,reference_area=ref,decoded_area=decoded,intersection=hit,recall=hit/ref,
                      precision=hit/decoded,area_ratio=decoded/ref,iou=hit/(ref+decoded-hit)))
    for row in records:
        if row["id"]=="a" and row["method"]=="cross" and row["status"]=="success":
            row.update(fp=5,fn=3)
    write_rows(folder/"regions.csv",region_rows)
    write_rows(folder/"per_run.csv",records)
    report=analyze(folder,"synthetic_check",settings)
    decision=report["decision"][0]
    assert report["validated_rows"]==96 and decision["n_primary"]==2
    assert abs(decision["primary_mean_xor"]-1)<1e-12
    assert abs(decision["overall_coverage_gain_pp"]-(-100*5/6/4))<1e-12
    assert decision["decision"]=="increment_not_established"
    cov=next(r for r in read_rows(folder/"analysis/paired_coverage.csv") if r["scope"]=="all" and r["deadline_ms"]=="100")
    assert int(cov["n_baseline_only"])==5 and int(cov["n_neither"])==6 and int(cov["n_common_runs"])==13
    loo=[r for r in read_rows(folder/"analysis/leave_one_source.csv") if r["dataset"]=="Oxford"]
    assert {r["removed"]:float(r["mean_without"]) for r in loo}=={"a":-2.0,"b":4.0}
    paired={r["analysis"]:float(r["mean"]) for r in read_rows(folder/"analysis/stability.csv") if r["mean"]}
    assert paired["fully_paired_repeats"]==-2 and paired["session/S1"]==1 and paired["session/S2"]==-2
    conflicts=read_rows(folder/"analysis/regions_cases.csv")
    match=next(r for r in conflicts if r["reason"]=="severe_new_small_and_lower_coverage")
    assert match["id"]=="a" and float(match["method_area_ratio"])==.25 and int(match["global_xor_gain"])==4
    write_rows(folder/"per_run.csv",records[:-1])
    try:analyze(folder,"synthetic_check",settings)
    except ValueError as exc:assert "Missing" in str(exc)
    else:raise AssertionError("Incomplete grid accepted")
    bad=[r.copy() for r in records]
    row=next(r for r in bad if r["status"]=="success" and r["deadline_ms"]==100)
    row["delivered_ms"]=101
    write_rows(folder/"per_run.csv",bad)
    try:analyze(folder,"synthetic_check",settings)
    except ValueError as exc:assert "Late" in str(exc)
    else:raise AssertionError("Late draw accepted")
    write_rows(folder/"per_run.csv",records)
    return dict(raw_timing_rows=report["validated_rows"],r2_source_weighted_xor=decision["primary_mean_xor"],
                all_ring_common_runs=int(cov["n_common_runs"]),paired_structure_conflict_verified=True,full_repeat_sensitivity=paired["fully_paired_repeats"],
                late_observation_rejected=True,missing_repeat_rejected=True)


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path,required=True,help="Fresh scratch directory for synthetic-only tables")
    args=p.parse_args()
    print(json.dumps(dict(region_fixture=regions(),aggregation_fixture=inference(args.output)),indent=2))
