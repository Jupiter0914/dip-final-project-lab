"""Tabulate the frozen conditions without pooling domains, budgets, timepoints, or repetitions."""
from collections import Counter,defaultdict
from pathlib import Path
import numpy as np
from poly02.data import rows,save_rows
from .study import ROOT,RESULTS

LABEL={"seed":"合法分配起点","within_full":"充分圈内","cross":"允许跨圈","cgal":"原版 CGAL","cgal_within":"CGAL + 充分圈内","exact":"精确整图排序"}
METHODS=["seed","within_full","cross","cgal_within","cgal"]
def decimal(v,d=2): return "—" if v is None or v=="" else f"{float(v):.{d}f}"


def extra_tables(folder):
    calls=rows(folder/"runs.csv")
    checkpoints=rows(folder/"checkpoints.csv")
    quality={(r["dataset"],r["id"],r["sha256"]):r for r in rows(folder/"blob_metrics.csv")}
    obs=rows(folder/"per_run.csv")
    initial={(r["dataset"],r["id"],r["session"],r["rep"],r["budget"]):r for r in checkpoints if r["method"]=="cgal_within" and r["round"]=="0"}
    results=[]
    for ds in sorted({r["dataset"] for r in obs}):
        groups={m:{(r["id"],r["session"],r["rep"]):r for r in calls if r["method"]==m and r["dataset"]==ds and r["budget"]=="256"} for m in ("cgal","cgal_within")}
        comparable=[(a,b) for key,a in groups["cgal"].items() if (b:=groups["cgal_within"][key]) and a["raw_cgal_sha256"] and b["raw_cgal_sha256"]]
        for t in ("100","200"):
            by=defaultdict(list)
            for r in obs:
                if (r["dataset"],r["method"],r["budget"],r["deadline_ms"],r["status"])!=(ds,"cgal_within","256",t,"success"):continue
                seed=initial[ds,r["id"],r["session"],r["rep"],"256"]
                start=quality[ds,r["id"],seed["sha256"]]
                by[r["id"],r["session"]].append(int(start["xor"])-int(r["xor"]))
            source=defaultdict(list)
            for (name,_),vals in by.items():source[name].append(np.mean(vals))
            v=np.array([np.mean(x) for x in source.values()])
            results.append(dict(dataset=ds,budget=256,deadline_ms=t,sources=len(v),own_start_xor_saved_mean=float(v.mean()) if len(v) else "",
                source_wins=int((v>0).sum()),source_ties=int((v==0).sum()),source_losses=int((v<0).sum()),
                independent_raw_pairs=len(comparable),different_native_blobs=sum(a["raw_cgal_sha256"]!=b["raw_cgal_sha256"] for a,b in comparable)))
    save_rows(folder/"cgal_own_start.csv",results)
    struct=rows(folder/"structural_cost.csv")
    values=[]
    for ds in sorted({r["dataset"] for r in struct}):
        for budget in (128,256,512):
            sample=[r for r in struct if r["dataset"]==ds and int(r["budget"])==budget]
            ok=[r for r in sample if r.get("validity_cost_xor","")!=""]
            changed=[r for r in ok if r["raw_reason"]!="ok"]
            def effect(group):
                return np.mean([int(r["validity_cost_xor"]) for r in group]) if group else ""
            values.append(dict(dataset=ds,budget=budget,n=len(sample),raw_valid=sum(r["raw_reason"]=="ok" for r in sample),
                 raw_invalid=sum(bool(r["raw_reason"]) and r["raw_reason"]!="ok" for r in sample),
                 final_valid=len(ok),recovered_after_invalid=len(changed),
                 below_bound=sum(r["status"]=="below_proved_lower_bound" for r in sample),
                 search_failed=sum(r["status"]=="search_no_valid_output" for r in sample),
                 unsupported=sum(r["status"]=="unsupported_representation" for r in sample),
                 mean_extra_xor_valid=effect(ok),mean_extra_xor_recovered=effect(changed),
                 max_extra_xor=max((int(r["validity_cost_xor"]) for r in ok),default=""),
                 max_source=max(ok,key=lambda r:int(r["validity_cost_xor"]))["id"] if ok else ""))
    save_rows(folder/"structure_summary.csv",values)
    eng=rows(folder/"exact_screen.csv");exact=[]
    for ds in sorted({r["dataset"] for r in eng}):
        v=[r for r in eng if r["dataset"]==ds]
        exact.append(dict(dataset=ds,actual_sources=len({r["id"] for r in v}),states=len(v),
            proposals=sum(int(r["proposed_pairs"]) for r in v),raw_xor_improving=sum(int(r["xor_improving"]) for r in v),
            screened_raw_improvements=sum(int(r["skipped_by_add"]) for r in v),
            screened_valid_improvements=sum(int(r["valid_skipped_by_add"]) for r in v),
            different_first_choice=sum(r["choices_differ"]=="True" for r in v)))
    save_rows(folder/"screen_summary.csv",exact)


def main():
    f=RESULTS/"confirm";a=f/"analysis"
    extra_tables(f)
    cov=rows(a/"coverage.csv");paired=rows(a/"paired_summary.csv");pc=rows(a/"paired_coverage.csv")
    decisions=__import__("json").loads((a/"decision.json").read_text(encoding="utf-8"))["decision"]
    text=["# 冻结条件结果表","","覆盖先按源内重复、会话等权，再对源平均。表内“成功数”等为实际调用次数，每个主预算源有六次。各法的条件均值因成功样本可能不同，质量结论使用另表的同源同次配对。"]
    for ds in ("Oxford","LEMS"):
        text+=["","## "+ds,"","### 256 字节的全体交付","","| 截止 ms | 方法 | 源数 | 成功 / 调用 | 覆盖 % | 仅当前搜索失败 | 低于下界 | 不支持 | 尚未收到 | 成功源平均 XOR | 接收时间中位 / p95 ms | 搜索返回中位 / p95 ms |",
               "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for t in (100,200):
            for m in METHODS:
                r=next(z for z in cov if (z["dataset"],z["budget"],z["deadline_ms"],z["method"],z["scope"])==(ds,"256",str(t),m,"all"))
                text.append(f"| {t} | {LABEL[m]} | {r['sources']} | {r['obs_success']} / {r['runs']} | {decimal(r['coverage_pct'])} | {r['obs_search_no_valid_output']} | {r['obs_below_proved_lower_bound']} | {r['obs_unsupported_representation']} | {r['obs_not_ready']} | {decimal(r['success_source_mean_xor'])} | {decimal(r['delivered_ms_median'])} / {decimal(r['delivered_ms_p95'])} | {decimal(r['end_ms_median'])} / {decimal(r['end_ms_p95'])} |")
        text+=["","### 同时成功且实际同码长的配对差","","正值代表前一方法少错或质量较高。主比较为 256 B、100 ms、R≥2。其他条件分别列出。","",
              "| B | ms | 参考集合 | 方法 / 对照 | 共同源 | 少错像素 [95% 区间] | 逐源胜/平/负 | 相对少错 % | IoU 变化 pp | BF2 变化 pp |",
              "|---:|---:|---|---|---:|---:|---:|---:|---:|---:|"]
        for budget in (256,128,512):
            for t in (100,200):
                pairs=[("cross","within_full","R2+")]
                if budget==256 and t==100:
                    pairs += [("cross","within_full","R1"),("cross","within_full","all"),("cross","cgal_within","all"),
                              ("cross","cgal","all"),("cgal_within","cgal","all"),("within_full","seed","all"),("exact","cross","all")]
                for m,b,scope in pairs:
                    subset={r["metric"]:r for r in paired if (r["dataset"],r["budget"],r["deadline_ms"],r["method"],r["baseline"],r["scope"])==(ds,str(budget),str(t),m,b,scope)}
                    if "xor_saved" not in subset:continue
                    q=subset["xor_saved"];g=lambda key:decimal(subset[key]["mean"],4)
                    text.append(f"| {budget} | {t} | {scope} | {LABEL[m]} / {LABEL[b]} | {q['n_sources']} | {decimal(q['mean'])} [{decimal(q['lo'])}, {decimal(q['hi'])}] | {q['wins']}/{q['ties']}/{q['losses']} | {g('relative_xor_saved_pct')} | {g('iou_gain_pp')} | {g('bf2_gain_pp')} |")
        text+=["","### 观察配对与独有交付","","| ms | 方法 / 对照 | 均成功 | 仅方法成功 | 仅对照成功 | 均未成功 | 全源覆盖差 pp [95% 区间] |","|---:|---|---:|---:|---:|---:|---:|"]
        for t in (100,200):
            for m,b in [("cross","within_full"),("cross","cgal_within"),("cgal_within","cgal")]:
                r=next(x for x in pc if (x["dataset"],x["budget"],x["deadline_ms"],x["method"],x["baseline"],x["scope"])==(ds,"256",str(t),m,b,"all"))
                text.append(f"| {t} | {LABEL[m]} / {LABEL[b]} | {r['n_common_runs']} | {r['n_method_only']} | {r['n_baseline_only']} | {r['n_neither']} | {decimal(r['coverage_gain_pp'])} [{decimal(r['coverage_lo_pp'])}, {decimal(r['coverage_hi_pp'])}] |")
    text+=["","### 阅读原始材料","","[逐次截止文件](../../results/poly04/confirm/per_run.csv) · [全部配对与区间](../../results/poly04/confirm/analysis/paired_summary.csv) · [按源配对分布](../../results/poly04/confirm/analysis/source_pairs.csv) · [会话效应](../../results/poly04/confirm/analysis/stability.csv) · [删除单个源](../../results/poly04/confirm/analysis/leave_one_source.csv) · [不同类别](../../results/poly04/confirm/analysis/category_sensitivity.csv) · [结构代价](../../results/poly04/confirm/structure_summary.csv) · [CGAL 自身起点](../../results/poly04/confirm/cgal_own_start.csv)"]
    p=ROOT/"report/poly04/tables.md"
    p.parent.mkdir(exist_ok=True,parents=True)
    p.write_text("\n".join(text)+"\n",encoding="utf-8")


if __name__=="__main__": main()
