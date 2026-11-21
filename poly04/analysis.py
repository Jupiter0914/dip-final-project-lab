"""Frozen POLY04 paired-source analysis. All timing observations are caller delivery events."""
import argparse
import csv
import itertools
import json
import math
import re
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OBSERVED = ("success","not_ready","below_proved_lower_bound","search_no_valid_output","unsupported_representation")
FINALS = tuple(s for s in OBSERVED if s != "not_ready")
DEFAULT_PAIRS = [
    ("cross","within_full"), ("cross","seed"), ("within_full","seed"),
    ("cross","cgal_within"), ("cross","cgal"), ("within_full","cgal_within"),
    ("cgal_within","cgal"), ("within_full_oldtri","within_old"), ("within_full","within_old"),
    ("within_full","within_full_oldtri"), ("cross","cross_oldtri"), ("cross","cross_full_oldtri"),
    ("cross_full_oldtri","cross_oldtri"), ("cross_full_oldtri","within_full_oldtri"), ("exact","cross")]
QUALITY = ("xor_saved","relative_xor_saved_pct","iou_gain_pp","fp_saved","fn_saved",
           "bf1_gain_pp","bf2_gain_pp","bf3_gain_pp")
SEED = 40121
DRAWS = 10000


def read_rows(path):
    with Path(path).open(encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))


def write_rows(path, rows, fields=()):
    names = list(dict.fromkeys([*fields,*(k for row in rows for k in row)]))
    with Path(path).open("w",encoding="utf-8",newline="") as f:
        writer = csv.DictWriter(f,fieldnames=names,lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def resolve_file(path, folder):
    path = Path(path)
    if path.is_absolute():
        return path
    return ROOT/path if (ROOT/path).exists() else folder/path


def normalize_grid(settings, folder):
    """A frozen roster, not the observed rows, defines the expected source/run keys."""
    roster = settings.get("samples")
    if roster is None:
        roster = read_rows(resolve_file(settings["manifest"],folder))
    sources = {}
    for entry in roster:
        key = (str(entry["dataset"]),str(entry["id"]))
        if key in sources:
            raise ValueError(f"Duplicate manifest key {key}")
        sources[key] = entry.copy()
    offered = set()
    for cond in settings["conditions"]:
        datasets = set(map(str,cond.get("datasets",{k[0] for k in sources})))
        ids = cond.get("source_ids")
        if ids is not None:
            filter_ids = {str(i) for i in ids if not isinstance(i,(dict,list,tuple))}
            filter_keys = {tuple(map(str,i)) for i in ids if isinstance(i,(list,tuple))}
            filter_keys.update((str(i["dataset"]),str(i["id"])) for i in ids if isinstance(i,dict))
        chosen = [k for k in sources if k[0] in datasets and
                  (ids is None or k[1] in filter_ids or "/".join(k) in filter_ids or k in filter_keys)]
        if not chosen:
            raise ValueError("Planned condition has no source")
        if ids is not None:
            visible={part for key in chosen for part in (key[1],"/".join(key))}
            if filter_ids-visible or filter_keys-set(chosen):
                raise ValueError("Predeclared supplemental source missing from the roster")
        selected_sessions = cond.get("session_ids",settings.get("session_ids",[]))
        selected_reps = cond.get("rep_ids",settings.get("rep_ids",[]))
        if not selected_sessions or not selected_reps:
            raise ValueError("Explicit session_ids and rep_ids required")
        for key,session,rep,deadline,method in itertools.product(chosen,selected_sessions,selected_reps,cond["deadlines_ms"],cond["methods"]):
            planned=(*key,str(session),str(rep),int(cond["budget"]),int(deadline),str(method))
            if planned in offered:
                raise ValueError(f"Duplicate planned observation {planned}")
            offered.add(planned)
    if not offered:
        raise ValueError("Empty expected scientific grid")
    return sources,offered


def finite(row,key):
    v = float(row[key])
    if not math.isfinite(v):
        raise ValueError(f"Nonfinite {key} in {row['id']}")
    return v


def checked_table(records, sources, offered):
    actual = {}
    rates,finish,meta = {},{},{}
    for r in records:
        dataset,name=r["dataset"],r["id"]
        key=(dataset,name,str(r["session"]),str(r["rep"]),int(r["budget"]),int(r["deadline_ms"]),r["method"])
        if key in actual or key not in offered:
            raise ValueError(f"Duplicate or unplanned observation {key}")
        if (dataset,name) not in sources: raise ValueError(f"Unexpected source {key}")
        manifest=sources[dataset,name]
        ring_value=r.get("rings","")
        ring=int(ring_value) if str(ring_value).strip() else -1
        if ring>=0:
            if manifest.get("rings","") not in ("",None) and int(manifest["rings"])>=0 and int(manifest["rings"])!=ring:
                raise ValueError(f"Ring metadata differs {key}")
            current=meta.setdefault((dataset,name),ring)
            if current!=ring:raise ValueError(f"Inconsistent original ring count {key}")
        if manifest.get("stratum","") and r.get("stratum","")!=manifest["stratum"]:
            raise ValueError(f"Inconsistent input stratum {key}")
        method,status,final=key[-1],r["status"],r["final_status"]
        budget,deadline=key[4:6]
        end=finite(r,"end_ms")
        if end<0 or status not in OBSERVED or final not in FINALS:
            raise ValueError(f"Invalid status/clock {key}: {status}/{final}")
        run=(*key[:5],method)
        old=finish.setdefault(run,(end,final))
        if old!=(end,final): raise ValueError(f"Inconsistent final state across deadlines {run}")
        if status=="success":
            received=finite(r,"delivered_ms")
            serialized=finite(r,"serialized_ms")
            if final!="success" or not (0<=serialized<=received<=deadline+1e-9 and received<=end+1e-8):
                raise ValueError(f"Late or impossible delivery marked successful {key}")
            n=int(r["actual_bytes"])
            if not (0<n<=budget) or not re.fullmatch("[0-9a-fA-F]{64}",r["sha256"]):
                raise ValueError(f"Invalid byte count or fingerprint {key}")
            if ring>=0 and (n<10+16*ring or (n-10-4*ring)%4):
                raise ValueError(f"Illegal PM31 length {key}")
            if rates.setdefault((dataset,name,budget),n)!=n:
                raise ValueError(f"Source not compared at equal actual bytes {key}")
            if int(r["xor"])!=int(r["fp"])+int(r["fn"]) or min(int(r["fp"]),int(r["fn"]))<0:
                raise ValueError(f"FP/FN mismatch {key}")
            if any(not 0<=finite(r,f)<=1+1e-12 for f in ("iou","bf1","bf2","bf3")):
                raise ValueError(f"Invalid rate {key}")
        else:
            if any(str(r.get(f,"") or "").strip() for f in ("xor","fp","fn","iou","bf1","bf2","bf3","sha256")):
                raise ValueError(f"Absent output carries quality or hash {key}")
            if status=="not_ready":
                if end<=deadline+1e-9:raise ValueError(f"Finished observation as not_ready {key}")
            elif status!=final or end>deadline+1e-9:
                raise ValueError(f"Final failure reported before it was observable {key}")
        actual[key]=r
    if len(offered)!=len(actual):
        raise ValueError(f"Missing {len(offered)-len(actual)} predeclared observations; example {next(iter(offered-set(actual)))}")
    # A later deadline for the same run must preserve any already delivered valid output.
    previous={}
    order=lambda k:(k[0],k[1],k[2],k[3],k[4],k[6],k[5])
    for key in sorted(actual,key=order):
        ds,name,sess,rep,b,_,method=key
        run=(ds,name,sess,rep,b,method)
        current=actual[key]
        earlier=previous.get(run)
        if earlier is not None and earlier["status"]=="success":
            if current["status"]!="success" or finite(current,"delivered_ms")<finite(earlier,"delivered_ms"):
                raise ValueError(f"Delivered checkpoint vanished or moved earlier: {run}")
            if int(current["xor"])>int(earlier["xor"]):
                raise ValueError(f"Checkpoint regressed in strict XOR search: {run}")
            if earlier["sha256"]!=current["sha256"] and int(current["xor"])>=int(earlier["xor"]):
                raise ValueError(f"Different later output without strict XOR reduction: {run}")
        previous[run]=current
    for source,r in sources.items():
        if source in meta:
            r["rings"]=meta[source]
        elif r.get("rings") in ("",None):
            r["rings"]=-1
    return actual


@lru_cache(maxsize=6)
def weights(n):
    """Bootstrap frequencies for sorted source records; one source keeps all its observations."""
    draws=np.random.default_rng(SEED).integers(n,size=(DRAWS,n),dtype=np.int32)
    offsets=n*np.arange(DRAWS,dtype=np.int64)[:,None]
    return np.bincount((draws+offsets).ravel(),minlength=DRAWS*n).reshape(DRAWS,n).astype(np.float32)


def intervals(values):
    values=np.asarray(values,np.float64)
    if values.ndim==1:values=values[:,None]
    means=(weights(len(values))@values)/len(values)
    return np.quantile(means,[.025,.975],axis=0)


def groupflag(info, scope):
    ring=int(info.get("rings",-1))
    if scope=="all":return True
    if scope=="R2+":return ring>=2
    if scope=="R1":return ring==1
    return str(info.get("stratum"))==scope.removeprefix("stratum/")


def average_sessions(items):
    """Input pairs (session, vector); equal-weight repeats then observed sessions in one source."""
    by=defaultdict(list)
    for session,vector in items:by[session].append(vector)
    return np.mean([np.mean(by[s],axis=0) for s in sorted(by)],axis=0)


def gain_vector(a,b):
    xa,xb=int(a["xor"]),int(b["xor"])
    return np.asarray([xb-xa,100*(xb-xa)/max(1,xb),100*(float(a["iou"])-float(b["iou"])),
                       int(b["fp"])-int(a["fp"]),int(b["fn"])-int(a["fn"]),
                       *[100*(float(a[f])-float(b[f])) for f in ("bf1","bf2","bf3")]],float)


def pair_data(left,right,sources):
    """left/right map (dataset,id,session,rep) to an observation on one timing condition."""
    out={}
    for key in sorted(left.keys()&right.keys()):
        a,b=left[key],right[key]
        source=key[:2]
        v=out.setdefault(source,dict(presence=[],matched=[],cases=[],sessions=defaultdict(list),zero_rhs=0))
        ok_a=a["status"]=="success";ok_b=b["status"]=="success"
        both=ok_a and ok_b
        v["presence"].append((key[2],np.array([ok_a,ok_b,both,ok_a and not ok_b,ok_b and not ok_a,not(ok_a or ok_b)],float)))
        if both:
            if a["actual_bytes"]!=b["actual_bytes"]:raise ValueError(f"Unequal exact pair bytes {key}")
            delta=gain_vector(a,b)
            v["matched"].append((key[2],delta))
            v["sessions"][key[2]].append(delta)
            v["cases"].append((key,a,b,delta))
            v["zero_rhs"]+=int(int(b["xor"])==0)
    for v in out.values():
        v["coverage"]=average_sessions(v["presence"])
        v["quality"]=average_sessions(v["matched"]) if v["matched"] else None
        if v["quality"] is not None:
            v["absolute"]=average_sessions([(key[2],[int(a["xor"]),int(b["xor"]),float(a["iou"]),float(b["iou"])])
                for key,a,b,_ in v["cases"]])
    return out


def get_scopes(dataset,budget,time):
    # Full per-stratum estimates focus on the registered primary condition.
    return ["all","R2+","R1"]


def source_meta(info):
    return dict(group=info.get("group",""),category=info.get("category",info.get("group","")),
                stratum=info.get("stratum",""),rings=int(info.get("rings",-1)))


def method_coverage(context, table,sources):
    by_source=defaultdict(list)
    for key,r in table.items():by_source[key[:2]].append((key[2],r))
    out=[]
    scopes=get_scopes(context["dataset"],context["budget"],context["deadline_ms"])
    for scope in scopes:
        ids=[n for n in sorted(by_source) if groupflag(sources[n],scope)]
        if not ids:continue
        observed=Counter();final=Counter();rates=[];rows=[]
        for name in ids:
            group=by_source[name]
            rates.append(float(average_sessions([(sess,1. if r["status"]=="success" else 0.) for sess,r in group])))
            for sess,r in group:
                observed[r["status"]]+=1;final[r["final_status"]]+=1;rows.append(r)
        good=[r for r in rows if r["status"]=="success"]
        entry=dict(**context,scope=scope,sources=len(ids),source_ever_delivered=sum(v>0 for v in rates),
                   source_always_delivered=sum(v==1 for v in rates),runs=len(rows),coverage_pct=100*np.mean(rates))
        for st in OBSERVED:entry["obs_"+st]=observed[st]
        for st in FINALS:entry["end_"+st]=final[st]
        for key in ("serialized_ms","delivered_ms","actual_bytes","round","proposed_pairs","accepted_moves","cross_moves"):
            vals=[finite(r,key) for r in good if r.get(key) not in ("",None)]
            entry[key+"_median"]=np.median(vals) if vals else ""
            entry[key+"_p95"]=np.quantile(vals,.95) if vals else ""
        quality_keys=("xor","fp","fn","iou","bf1","bf2","bf3")
        available=[]
        for name in ids:
            items=[(sess,[float(r[k]) for k in quality_keys]) for sess,r in by_source[name] if r["status"]=="success"]
            if items:available.append(average_sessions(items))
        for j,key in enumerate(quality_keys):
            entry["success_source_mean_"+key]=np.mean([q[j] for q in available]) if available else ""
        entry["end_ms_median"]=np.median([float(r["end_ms"]) for r in rows])
        entry["end_ms_p95"]=np.quantile([float(r["end_ms"]) for r in rows],.95)
        out.append(entry)
    return out


def brief_quality(context, sources, data,scope):
    ids=[n for n in sorted(data) if groupflag(sources[n],scope)]
    if not ids:return [],None
    all_cov=100*np.stack([data[n]["coverage"] for n in ids]);cov_delta=all_cov[:,0]-all_cov[:,1]
    cov_ci=intervals(cov_delta).ravel()
    common=[n for n in ids if data[n]["quality"] is not None]
    counts=np.stack([np.sum([a for _,a in data[n]["presence"]],axis=0) for n in ids]).sum(axis=0).astype(int)
    coverage=dict(**context,scope=scope,sources=len(ids),n_ever_common=len(common),
        n_all_repeats_common=sum(len(data[n]["presence"])==len(data[n]["matched"]) for n in ids),
        method_ever_source=sum(data[n]["coverage"][0]>0 for n in ids),baseline_ever_source=sum(data[n]["coverage"][1]>0 for n in ids),
        n_common_runs=int(counts[2]),n_method_only=int(counts[3]),n_baseline_only=int(counts[4]),n_neither=int(counts[5]),
        method_coverage_pct=all_cov[:,0].mean(),baseline_coverage_pct=all_cov[:,1].mean(),coverage_gain_pp=cov_delta.mean(),
        coverage_lo_pp=cov_ci[0],coverage_hi_pp=cov_ci[1])
    if not common:return [],coverage
    ab=np.stack([data[n]["absolute"] for n in common])
    coverage.update(common_method_xor=ab[:,0].mean(),common_baseline_xor=ab[:,1].mean(),
                    common_method_iou=ab[:,2].mean(),common_baseline_iou=ab[:,3].mean(),
                    pooled_relative_xor_saved_pct=100*(ab[:,1].sum()-ab[:,0].sum())/max(1,ab[:,1].sum()))
    v=np.stack([data[s]["quality"] for s in common])
    ci=intervals(v)
    summaries=[]
    for j,key in enumerate(QUALITY):
        scores=v[:,j]
        summaries.append(dict(**context,scope=scope,metric=key,n_sources=len(common),n_target=len(ids),n_common_runs=int(counts[2]),
            baseline_xor_zero_observations=sum(data[s]["zero_rhs"] for s in common),
            mean=scores.mean(),median=np.median(scores),lo=ci[0,j],hi=ci[1,j],
            wins=int((scores>1e-12).sum()),ties=int((abs(scores)<=1e-12).sum()),losses=int((scores< -1e-12).sum()),
            worst_id=common[int(scores.argmin())][1],worst=scores.min(),best_id=common[int(scores.argmax())][1],best=scores.max()))
    return summaries,coverage


def detailed_effects(context,sources,data,session_ids):
    common=[s for s in sorted(data) if groupflag(sources[s],"R2+") and data[s]["quality"] is not None]
    complete=[s for s in common if len(data[s]["matched"])==len(data[s]["presence"])]
    results=[];loo=[];categories=[];cases=[];cluster=[]
    def add(label,names,values):
        if not names:
            results.append(dict(**context,analysis=label,n=0,mean="",lo="",hi=""))
            return
        lo,hi=intervals(values).ravel()
        results.append(dict(**context,analysis=label,n=len(names),mean=np.mean(values),lo=lo,hi=hi))
    add("all_common",common,[data[s]["quality"][0] for s in common])
    add("fully_paired_repeats",complete,[data[s]["quality"][0] for s in complete])
    for sess in sorted(session_ids):
        names=[s for s in common if data[s]["sessions"].get(sess)]
        add("session/"+sess,names,[np.mean([v[0] for v in data[s]["sessions"][sess]]) for s in names])
    if not common:return results,loo,categories,cases,cluster
    values=np.array([data[s]["quality"][0] for s in common])
    if len(common)>1:
        for s,value in zip(common,values):
            loo.append(dict(**context,removed=s[1],n=len(values)-1,mean_without=(values.sum()-value)/(len(values)-1)))
    by_category=defaultdict(list)
    for s,score in zip(common,values):
        info=source_meta(sources[s])
        by_category[str(info["category"])].append(score)
    for cat,vals in sorted(by_category.items()):
        others=[v for c,vs in by_category.items() if c!=cat for v in vs]
        categories.append(dict(**context,category=cat,category_sources=len(vals),category_mean=np.mean(vals),
                               n_without=len(others),mean_without_category=np.mean(others) if others else ""))
    if len(by_category)>1:
        named=sorted(by_category);sums=np.array([sum(by_category[c]) for c in named]);sizes=np.array([len(by_category[c]) for c in named])
        freq=weights(len(named))
        draws=(freq@sums)/(freq@sizes)
        lo,hi=np.quantile(draws,[.025,.975])
        cluster.append(dict(**context,categories=len(named),sources=len(common),mean=values.mean(),lo=lo,hi=hi))
    positive=[s for s in common if data[s]["quality"][0]>1e-12]
    selected=[]
    if positive:
        median=np.median([data[s]["quality"][0] for s in positive])
        selected.append(("typical_positive",min(positive,key=lambda s:abs(data[s]["quality"][0]-median))))
    selected.append(("nearest_zero",min(common,key=lambda s:abs(data[s]["quality"][0]))))
    selected.append(("worst",min(common,key=lambda s:data[s]["quality"][0])))
    for why,s in selected:
        score=data[s]["quality"][0]
        key,a,b,d=min(data[s]["cases"],key=lambda item:abs(item[3][0]-score))
        cases.append(dict(**context,reason=why,id=s[1],**source_meta(sources[s]),source_mean_xor_gain=score,
            session=key[2],rep=key[3],matched_run_xor_gain=d[0],method_xor=a["xor"],baseline_xor=b["xor"],
            method_sha256=a["sha256"],baseline_sha256=b["sha256"],actual_bytes=a["actual_bytes"]))
    return results,loo,categories,cases,cluster


def analyze(folder,stage,settings,output=None):
    folder=Path(folder)
    if not isinstance(settings,dict):
        settings=json.loads(Path(settings).read_text(encoding="utf-8-sig"))
    if int(settings.get("bootstrap_seed",SEED))!=SEED or int(settings.get("bootstrap_draws",DRAWS))!=DRAWS:
        raise ValueError("Analysis bootstrap differs from frozen settings")
    sources,grid=normalize_grid(settings,folder)
    if stage in ("confirm","confirmation"):
        primary=(settings.get("primary_method","cross"),settings.get("primary_baseline","within_full"))
        for ds,name in sources:
            for sess,rep,m in itertools.product(settings["session_ids"],settings["rep_ids"],primary):
                if (ds,name,str(sess),str(rep),256,100,m) not in grid:
                    raise ValueError(f"Manifest source omitted from the primary coverage plan: {ds}/{name}")
        counts=Counter(ds for ds,_ in sources)
        if counts["Oxford"]!=200:raise ValueError(f"Expected 200 frozen Oxford sources, got {counts['Oxford']}")
        for ds,n in settings.get("expected_counts",{}).items():
            if counts[ds]!=int(n):raise ValueError(f"Expected {n} sources in {ds}, got {counts[ds]}")
        for (ds,name),src in sources.items():
            if ds!="Oxford" and not src.get("category"):
                raise ValueError(f"Missing external category for cluster sensitivity: {ds}/{name}")
    inputs=read_rows(folder/"per_run.csv")
    table=checked_table(inputs,sources,grid)
    conditions=defaultdict(lambda:defaultdict(dict))
    for key,r in table.items():
        ds,name,sess,rep,b,t,m=key
        conditions[ds,b,t][m][ds,name,sess,rep]=r
    coverage=[];paired_cov=[];summary=[];source_rows=[];sessions=[];loo=[];category=[];cases=[];cluster=[]
    session_coverage=[];negative_control=[]
    comparisons=[tuple(x) for x in settings.get("comparisons",DEFAULT_PAIRS)]
    primary_pair=(settings.get("primary_method","cross"),settings.get("primary_baseline","within_full"))
    if primary_pair not in comparisons:comparisons=[primary_pair,*comparisons]
    for (ds,b,t),methods in sorted(conditions.items()):
        context=dict(dataset=ds,budget=b,deadline_ms=t)
        for m,group in methods.items():
            coverage.extend(method_coverage(dict(**context,method=m),group,sources))
        for method,baseline in comparisons:
            if not(method in methods and baseline in methods):continue
            data=pair_data(methods[method],methods[baseline],sources)
            if not data:continue
            ctx=dict(**context,method=method,baseline=baseline)
            scopes=get_scopes(ds,b,t)
            if (method,baseline)==primary_pair and (b,t)==(256,100):
                scopes=scopes+["stratum/"+s for s in sorted({str(sources[n].get("stratum","")) for n in data}) if s]
            for scope in scopes:
                part,cv=brief_quality(ctx,sources,data,scope)
                summary.extend(part)
                if cv is not None:paired_cov.append(cv)
            for s,v in sorted(data.items()):
                quality=v["quality"]
                src=dict(**ctx,id=s[1],**source_meta(sources[s]),offered=len(v["presence"]),common=len(v["matched"]),
                         used_sessions=len(v["sessions"]),method_coverage_pct=100*v["coverage"][0],
                         baseline_coverage_pct=100*v["coverage"][1])
                src.update({metric:(quality[i] if quality is not None else "") for i,metric in enumerate(QUALITY)})
                source_rows.append(src)
            if (method,baseline)==primary_pair and (b,t)==(256,100):
                sessids={key[2] for key in methods[method].keys()&methods[baseline].keys()}
                for sess in sorted(sessids):
                    for sc in ("all","R2+","R1"):
                        selected=[n for n in sorted(data) if groupflag(sources[n],sc)]
                        votes=[]
                        for n in selected:
                            vv=[z for ss_,z in data[n]["presence"] if ss_==sess]
                            if vv:votes.append(np.mean(vv,axis=0))
                        if votes:
                            rates=100*np.mean(votes,axis=0)
                            session_coverage.append(dict(**ctx,session=sess,scope=sc,n_sources=len(votes),
                                   method_coverage_pct=rates[0],baseline_coverage_pct=rates[1],both_coverage_pct=rates[2],
                                   method_only_pct=rates[3],baseline_only_pct=rates[4],neither_pct=rates[5]))
                lone=[p for n,v in data.items() if groupflag(sources[n],"R1") for p in v["cases"]]
                eq_round=[p for p in lone if p[1]["round"]==p[2]["round"]]
                negative_control.append(dict(**ctx,scope="R1",valid_run_pairs=len(lone),
                    identical_bytes=sum(p[1]["sha256"]==p[2]["sha256"] for p in lone),equal_round_pairs=len(eq_round),
                    different_bytes_same_round=sum(p[1]["sha256"]!=p[2]["sha256"] for p in eq_round)))
                ss,ll,kk,cc,gg=detailed_effects(ctx,sources,data,sessids)
                sessions.extend(ss);loo.extend(ll);category.extend(kk);cases.extend(cc);cluster.extend(gg)
    decision=[]
    for ds in sorted({key[0] for key in conditions}):
        use=lambda r:r["dataset"]==ds and r["budget"]==256 and r["deadline_ms"]==100 and (r["method"],r["baseline"])==primary_pair
        effect=next((r for r in summary if use(r) and r["metric"]=="xor_saved" and r["scope"]=="R2+"),None)
        cv=next((r for r in paired_cov if use(r) and r["scope"]=="all"),None)
        independent=[r for r in sessions if use(r) and r["analysis"].startswith("session/")]
        without=[r["mean_without"] for r in loo if use(r)]
        if not independent or effect is None or cv is None:
            decision.append(dict(dataset=ds,decision="insufficient_common_primary_data"))
            continue
        threshold=float(settings.get("coverage_margin_pp",2))
        checks=dict(positive_xor_lower=bool(effect["lo"]>0),
                    all_sessions_positive=all(r["n"]>0 and r["mean"]>0 for r in independent),
                    all_leave_one_source_positive=bool(without and min(without)>0),
                    overall_coverage_lower=bool(cv["coverage_lo_pp"]>=-threshold))
        good=all(checks.values())
        status="stable_positive_increment" if good else ("within_baseline_quality_favored" if effect["hi"]<0 else "increment_not_established")
        category_check=next((r for r in cluster if use(r)),None)
        omit_category=[r["mean_without_category"] for r in category if use(r) and r["mean_without_category"]!=""]
        external="primary_domain" if ds=="Oxford" else "unresolved_or_opposite"
        if ds!="Oxford" and good:
            external=("same_direction_across_sources_and_categories" if category_check and category_check["lo"]>0
                      and omit_category and min(omit_category)>0 else "source_level_only_category_sensitive")
        decision.append(dict(dataset=ds,decision=status,checks=checks,external_replication=external,n_primary=effect["n_sources"],
            primary_mean_xor=effect["mean"],primary_ci95=[effect["lo"],effect["hi"]],n_all_sources=cv["sources"],
            overall_coverage_gain_pp=cv["coverage_gain_pp"],coverage_gain_ci95_pp=[cv["coverage_lo_pp"],cv["coverage_hi_pp"]],
            minimum_leave_one_xor=min(without) if without else None,maximum_leave_one_xor=max(without) if without else None))
    outputs={"coverage":coverage,"paired_coverage":paired_cov,"paired_summary":summary,"source_pairs":source_rows,
             "stability":sessions,"session_coverage":session_coverage,"r1_negative_control":negative_control,"leave_one_source":loo,"category_sensitivity":category,"cases":cases,"cluster":cluster}
    out=Path(output) if output is not None else folder/"analysis"
    out.mkdir(parents=True,exist_ok=True)
    for label,content in outputs.items():write_rows(out/(label+".csv"),content)
    report=dict(stage=stage,evidence="independent_confirmation" if stage in ("confirm","confirmation") else "development_or_fixture",
                roster_sources=len(sources),validated_rows=len(table),bootstrap_draws=DRAWS,bootstrap_seed=SEED,
                primary_budget=256,primary_deadline_ms=100,primary_domain="Oxford",primary_scope="R2+",decision=decision)
    (out/"decision.json").write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
    if (folder/"regions.csv").exists():
        from .analysis_region_summaries import report_regions
        report_regions(folder,table,sources,primary_pair,out)
    return report


def verify_analysis(folder,stage,settings):
    """Reaggregate in temp. Discrete metadata is exact and float columns tolerate machine tail variance."""
    import math
    import tempfile
    folder=Path(folder)
    origin=folder/"analysis"
    metadata={"dataset","id","group","category","stratum","method","baseline","metric","scope","analysis",
              "removed","session","rep","reason","reference_id","kind","area_band"}
    def equivalent(x,y,column):
        if x==y:return True
        if column in metadata or column.endswith(("_sha256","_file","_id","_source")):return False
        try:return math.isclose(float(x),float(y),abs_tol=1e-10,rel_tol=1e-12)
        except (TypeError,ValueError):return False
    with tempfile.TemporaryDirectory(prefix="poly04-pairs-") as temp:
        dest=Path(temp)
        report=analyze(folder,stage,settings,output=dest)
        produced={p.name for p in dest.iterdir() if p.is_file()}
        for name in sorted(produced):
            stored=origin/name
            if not stored.is_file():raise ValueError("Missing analysis output "+name)
            if name.endswith(".csv"):
                a,b=read_rows(stored),read_rows(dest/name)
                if len(a)!=len(b):raise ValueError("Row count mismatch "+name)
                for i,(old,new) in enumerate(zip(a,b)):
                    if old.keys()!=new.keys() or any(not equivalent(old[k],new[k],k) for k in old):
                        raise ValueError(f"Numeric analysis replay mismatch: {name} row {i}")
            elif name.endswith(".json"):
                # Freeze metadata, decisions and continuous primary estimates.
                old=json.loads(stored.read_text(encoding="utf-8-sig"))
                def check(a,b):
                    if isinstance(a,dict) and isinstance(b,dict):
                        return a.keys()==b.keys() and all(check(a[k],b[k]) for k in a)
                    if isinstance(a,list) and isinstance(b,list):return len(a)==len(b) and all(check(x,y) for x,y in zip(a,b))
                    if type(a) in (int,float) and type(b) in (int,float):return math.isclose(a,b,abs_tol=1e-10,rel_tol=1e-12)
                    return a==b
                if not check(old,report):raise ValueError("Frozen decision replay mismatch")
    return dict(verified_tables=len(produced),validated_observations=report["validated_rows"],stage=stage)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("folder",type=Path)
    parser.add_argument("--stage",required=True)
    parser.add_argument("--settings",required=True,type=Path)
    parser.add_argument("--output",type=Path,help="Alternate directory for the generated analysis tables")
    parser.add_argument("--verify-only",action="store_true",help="Recompute and compare to the published analysis without changing it")
    args=parser.parse_args()
    if args.verify_only and args.output:parser.error("Choose either --output or --verify-only")
    report=(verify_analysis(args.folder,args.stage,args.settings) if args.verify_only
            else analyze(args.folder,args.stage,args.settings,output=args.output))
    print(json.dumps(report,ensure_ascii=False,indent=2))
