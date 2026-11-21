"""Source-level and stratum-level comparisons, including all four encoding outcomes."""
from collections import Counter,defaultdict
import itertools
import json
import numpy as np
from poly02.data import rows,save_rows
from .full_data import ROOT,OUT,REC
from .full_run import METHODS

PAIRS=[("independent_dp","perimeter"),("feasible_add","independent_dp"),("allocation_whole","feasible_add"),
       ("exchange_whole","exchange_add"),("exchange_whole","exchange_within"),("exchange_cross","feasible_add"),
       ("exchange_within","feasible_add"),("exchange_whole","feasible_add"),("exchange_whole","cgal_squared"),
       ("exchange_whole","cgal_scaled"),("feasible_add","cgal_squared"),("feasible_add","cgal_scaled")]
STRATA=("simple","components","holes","near")


def grouped_records():
    rr=rows(OUT/"per_image.csv")
    table={(r["id"],r["budget"],r["method"]):r for r in rr}
    assert len(rr)==len(table)
    return rr,table


def ci(v):
    v=np.array(v,float)
    if not len(v):return ("","")
    rng=np.random.default_rng(30621)
    idx=rng.integers(len(v),size=(5000,len(v)))
    return np.quantile(v[idx].mean(axis=1),[.025,.975]).tolist()


def scores(rr,table):
    summary=[];paired=[];by_source=[]
    keys=sorted({(r["id"],r["budget"],r["stratum"]) for r in rr})
    for budget in ("primary","128","256","512","1024"):
        for stratum in ("all",*STRATA):
            kk=[(name,b) for name,b,s in keys if (stratum=="all" or s==stratum) and
                (b!="1024" if budget=="primary" else budget==b)]
            if not kk:continue
            for method in METHODS:
                selected=[table[*x,method] for x in kk]
                counts=Counter(r["status"] for r in selected)
                ok=[r for r in selected if r["status"]=="success"]
                item=dict(budget=budget,stratum=stratum,method=method,settings=len(kk),sources=len({x[0] for x in kk}),
                     success=counts["success"],below_bound=counts["below_proved_lower_bound"],
                     search_failure=counts["search_no_valid_output"],unsupported=counts["unsupported_representation"])
                for key in ("file_bytes","xor","fp","fn","iou","bf2","encode_ms","decode_ms","isolated_draws","full_draws"):
                    v=[float(r[key]) for r in ok]
                    item[key]=np.mean(v) if v else ""
                item["all_attempt_mean_ms"]=np.mean([float(r["encode_ms"]) for r in selected])
                summary.append(item)
            for a,b in PAIRS:
                paired_src=defaultdict(list);avail=Counter()
                for key in kk:
                    u,v=table[*key,a],table[*key,b]
                    valid=(u["status"]=="success",v["status"]=="success")
                    avail[valid]+=1
                    if not all(valid):continue
                    assert u["file_bytes"]==v["file_bytes"]
                    diff=int(v["xor"])-int(u["xor"])
                    paired_src[key[0]].append([diff,diff/max(int(v["xor"]),1),100*(float(u["iou"])-float(v["iou"])),
                        100*(float(u["bf2"])-float(v["bf2"])),float(u["encode_ms"])-float(v["encode_ms"])])
                if not paired_src:continue
                names=list(sorted(paired_src))
                vv=np.array([np.mean(paired_src[n],axis=0) for n in names])
                for j,metric in enumerate(("xor_saved","relative_saved","iou_gain_pp","bf2_gain_pp","extra_ms")):
                    vals=vv[:,j];lo,hi=ci(vals)
                    paired.append(dict(budget=budget,stratum=stratum,method=a,baseline=b,metric=metric,sources=len(vals),
                         both_ok=avail[True,True],only_method=avail[True,False],only_baseline=avail[False,True],
                         neither=avail[False,False],mean=vals.mean(),median=np.median(vals),lo=lo,hi=hi,
                         up=int((vals>1e-12).sum()),ties=int((abs(vals)<=1e-12).sum()),down=int((vals< -1e-12).sum()),
                         worst_id=names[vals.argmin()],worst=float(vals.min())))
                if stratum=="all":
                    for n,v in zip(names,vv):
                        by_source.append(dict(budget=budget,id=n,method=a,baseline=b,matched_budgets=len(paired_src[n]),
                                xor_saved=v[0],relative_saved=v[1],iou_gain_pp=v[2],bf2_gain_pp=v[3],extra_ms=v[4]))
    save_rows(OUT/"summary.csv",summary);save_rows(OUT/"paired_summary.csv",paired);save_rows(OUT/"paired_sources.csv",by_source)


def coupling():
    by=defaultdict(list)
    for r in rows(OUT/"allocation_candidates.csv"):by[r["id"],r["budget"],r["stratum"]].append(r)
    out=[]
    for (name,budget,s),group in by.items():
        for scope in ("all","valid"):
            values=[r for r in group if scope=="all" or r["valid"]=="1"]
            count=ties=rev=unequal=0
            for x,y in itertools.combinations(values,2):
                da=np.sign(int(x["additive_xor"])-int(y["additive_xor"]))
                df=np.sign(int(x["whole_xor"])-int(y["whole_xor"]))
                unequal+=da!=df
                rev+=da*df<0
                ties+=(da==0)!=(df==0)
                count+=1
            cancel=[int(r["cancellation"]) for r in values]
            assert all(i>=0 and i%2==0 for i in cancel)
            out.append(dict(id=name,budget=budget,stratum=s,scope=scope,candidates=len(values),
                  nonadditive=sum(v>0 for v in cancel),max_gap=max(cancel,default=0),sum_gap=sum(cancel),
                  invalid_candidates=sum(r["valid"]=="0" for r in values),pairs=count,strict_reversals=int(rev),
                  tie_changes=int(ties),rank_changes=int(unequal),rank_change_rate=unequal/count if count else ""))
    save_rows(OUT/"coupling_by_source.csv",out)


def timing():
    path=ROOT/"results/poly03/time_fair"
    records=rows(path/"per_image.csv")
    avg=[]
    pairs=[]
    for deadline in (100,200):
        sub=[r for r in records if int(r["deadline_ms"])==deadline]
        idx={(r["id"],r["rep"],r["method"]):r for r in sub}
        for m in ("global","global_cached","additive","within_additive"):
            sel=[r for r in sub if r["method"]==m]
            for stat,n in Counter(r["status"] for r in sel).items():
                v=[r for r in sel if r["status"]==stat]
                avg.append(dict(deadline_ms=deadline,method=m,status=stat,source_repetitions=n,distinct_sources=len({r["id"] for r in v}),
                    median_round=np.median([int(r["round"]) for r in v]) if stat=="success" else "",
                    median_ready_ms=np.median([float(r["ready_ms"]) for r in v]) if stat=="success" else ""))
        for a,b in (("global","additive"),("global_cached","additive"),("global_cached","global"),("global_cached","within_additive"),("global","within_additive"),("additive","within_additive")):
            groups=defaultdict(list)
            for key,v in idx.items():
                name,rep,m=key
                if m!=a:continue
                base=idx[name,rep,b]
                if v["status"]==base["status"]=="success":
                    assert v["file_bytes"]==base["file_bytes"]
                    groups[name].append((int(base["xor"])-int(v["xor"]),100*(float(v["iou"])-float(base["iou"])),
                                         100*(float(v["bf2"])-float(base["bf2"]))))
            vals=np.array([np.mean(v,axis=0) for v in groups.values()])
            for j,metric in enumerate(("xor_saved","iou_gain_pp","bf2_gain_pp")):
                scores=vals[:,j];lo,hi=ci(scores)
                pairs.append(dict(deadline_ms=deadline,method=a,baseline=b,metric=metric,n_sources=len(scores),
                    common_runs=sum(map(len,groups.values())),mean=scores.mean(),lo=lo,hi=hi,
                    up=int((scores>1e-12).sum()),tie=int((abs(scores)<=1e-12).sum()),down=int((scores< -1e-12).sum())))
    save_rows(path/"availability.csv",avg);save_rows(path/"paired_summary.csv",pairs)


if __name__=="__main__":
    scores(*grouped_records())
    coupling()
    if (ROOT/"results/poly03/time_fair/per_image.csv").exists():timing()
