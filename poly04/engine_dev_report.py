"""Summarize the immutable POLY04 development CSVs; this module never opens a new input mask."""
from collections import Counter, defaultdict
import csv
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
TIMED=ROOT/"results/poly04/dev"
FIXED=ROOT/"results/poly04/dev_fixed"
REPORT=ROOT/"report/poly04/development.md"
METHODS=("seed","within_old","within_full_oldtri","within_full","cross_oldtri","cross_full_oldtri","cross","exact","cgal","cgal_within")
NAMES=dict(seed="可行 DP 起点",within_old="历史圈内",within_full_oldtri="充分圈内·禁三角",within_full="充分圈内·准三角",
           cross_oldtri="历史跨圈",cross_full_oldtri="充分跨圈·禁三角",cross="充分跨圈·准三角",exact="精确整图",cgal="原版 CGAL",cgal_within="CGAL 后充分圈内")
CONDITIONS=("fixed2","100","200")
PAIRS=(("within_full_oldtri","within_old"),("within_full","within_full_oldtri"),("within_full","within_old"),
       ("cross_full_oldtri","cross_oldtri"),("cross","cross_full_oldtri"),("cross_oldtri","within_old"),
       ("cross_full_oldtri","within_full_oldtri"),("cross","within_full"),("cgal_within","cgal"),
       ("within_full","cgal_within"),("cross","cgal_within"),("exact","cross"))
SCOPES=("all","R2+","R1","Oxford_R2+","MPEG7_R2+")


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def save(path, records):
    with path.open("w",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in records for k in r)),lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


def source_key(r):
    return r["dataset"],r["id"]


def run_key(r):
    return r["dataset"],r["id"],r.get("session","fixed"),str(r.get("rep","1")),r["method"]


def scopes(r):
    ring=r.get("rings","")
    return ["all"] + (["R1"] if ring=="1" else ["R2+",r["dataset"]+"_R2+"] if ring and int(ring)>=2 else [])


def mean(nums):
    return float(np.mean(nums)) if len(nums) else None


def macro(records,key):
    by=defaultdict(list)
    for r in records:
        if r.get(key) not in (None,""):
            by[source_key(r)].append(float(r[key]))
    return mean([mean(v) for v in by.values()])


def rows_for_summary():
    fixed=read(FIXED/"per_image.csv")
    metrics={(r["dataset"],r["id"],r["sha256"]):r for r in read(TIMED/"blob_metrics.csv")}
    first={run_key(r):metrics[r["dataset"],r["id"],r["sha256"]] for r in read(TIMED/"checkpoints.csv") if r["round"]=="0"}
    runs={run_key(r):r for r in read(TIMED/"runs.csv")}
    exams=[]
    for data in fixed:
        r=dict(data,condition="fixed2",session="fixed",rep="1",full_pairs=data["proposed_pairs"],full_accept=data["accepted_moves"])
        if r["status"]=="success":
            r["gain_from_own_seed"]=int(r["initial_xor"])-int(r["xor"])
        exams.append(r)
    for data in read(TIMED/"per_run.csv"):
        meta=runs[run_key(data)]
        r=dict(data,condition=data["deadline_ms"],full_pairs=meta["proposed_pairs"],full_accept=meta["accepted_moves"])
        if r["status"]=="success":
            initial=first[run_key(r)]
            r["initial_xor"]=initial["xor"]
            r["gain_from_own_seed"]=int(initial["xor"])-int(r["xor"])
            r["iou_gain_from_own_seed_pp"]=100*(float(r["iou"])-float(initial["iou"]))
        exams.append(r)
    return exams,list(runs.values())


def method_summary(exams):
    groups=defaultdict(list)
    for r in exams:
        for scope in scopes(r):
            groups[r["condition"],scope,r["method"]].append(r)
    output=[]
    for (condition,scope,method),group in sorted(groups.items()):
        good=[r for r in group if r["status"]=="success"]
        count=Counter(r["status"] for r in group)
        row=dict(condition=condition,scope=scope,method=method,source_count=len({source_key(r) for r in group}),runs=len(group),
                 delivered_sources=len({source_key(r) for r in good}),delivered_runs=len(good),
                 success_pct=100*len(good)/len(group),below=count["below_proved_lower_bound"],search_fail=count["search_no_valid_output"],
                 unsupported=count["unsupported_representation"],not_ready=count["not_ready"])
        for field in ("xor","iou","fp","fn","bf1","bf2","bf3","initial_xor","gain_from_own_seed","iou_gain_from_own_seed_pp",
                      "proposed_pairs","accepted_moves","triangle_moves","cross_moves","delivered_ms"):
            row[field]=macro(good,field)
        for field in ("search_end_ms","full_pairs","full_accept"):
            row[field]=macro(group,field)
        row["search_end_median_ms"]=float(np.median([float(r["search_end_ms"]) for r in group]))
        row["search_end_p95_ms"]=float(np.quantile([float(r["search_end_ms"]) for r in group],.95))
        output.append(row)
    return output


def paired(exams):
    idx={(r["condition"],*run_key(r)):r for r in exams}
    output=[]
    units=[]
    for cond in CONDITIONS:
        for m,b in PAIRS:
            for scope in SCOPES:
                observations=defaultdict(list)
                cov=Counter()
                for r in exams:
                    if r["condition"]!=cond or r["method"]!=m or scope not in scopes(r):
                        continue
                    base=idx[cond,r["dataset"],r["id"],r["session"],r["rep"],b]
                    matched=(r["status"]=="success",base["status"]=="success")
                    cov[matched]+=1
                    if not all(matched):continue
                    assert r["actual_bytes"]==base["actual_bytes"]
                    observations[source_key(r)].append((int(base["xor"])-int(r["xor"]),100*(float(r["iou"])-float(base["iou"])),
                                                       float(r["delivered_ms"])-float(base["delivered_ms"])))
                if not observations:continue
                names=sorted(observations)
                values=np.array([np.mean(observations[n],axis=0) for n in names])
                z=values[:,0]
                boot=np.random.default_rng(40121).integers(len(z),size=(10000,len(z)))
                lo,hi=np.quantile(z[boot].mean(axis=1),[.025,.975])
                output.append(dict(condition=cond,scope=scope,method=m,baseline=b,sources=len(names),common_runs=cov[1,1],
                     only_method=cov[1,0],only_baseline=cov[0,1],neither=cov[0,0],mean_xor_saved=mean(z),lo=lo,hi=hi,
                     win=int((z>1e-12).sum()),tie=int((abs(z)<=1e-12).sum()),loss=int((z< -1e-12).sum()),
                     iou_gain_pp=mean(values[:,1]),delivery_change_ms=mean(values[:,2]),
                     worst=names[int(z.argmin())][1],worst_xor=float(z.min())))
                if scope=="all":
                    for (dataset,name),v in zip(names,values):
                        units.append(dict(condition=cond,dataset=dataset,id=name,method=m,baseline=b,repeats=len(observations[dataset,name]),
                                          xor_saved=v[0],iou_gain_pp=v[1],delivery_change_ms=v[2]))
    return output,units


def proposal_stats():
    out=[]
    for segment,path in [("fixed2",FIXED/"rounds.csv"),("time_run",TIMED/"rounds.csv")]:
        table=read(path)
        for m in METHODS:
            sub=[r for r in table if r["method"]==m]
            if not sub:continue
            c=np.array([int(r["proposed_pairs"]) for r in sub])
            out.append(dict(condition=segment,method=m,rounds=len(sub),median=float(np.median(c)),min=int(c.min()),
                    max=int(c.max()),under_24=int((c<24).sum()),under_24_nonzero=int(((c>0)&(c<24)).sum()),
                    none=int((c==0).sum()),proposed=int(c.sum()),accepted=sum(int(r["accepted"]) for r in sub),
                    proposed_triangles=sum(int(r["proposed_triangles"]) for r in sub),
                    accepted_triangles=sum(int(r["triangle"] or 0) for r in sub),
                    accepted_cross=sum(int(r["cross"] or 0) for r in sub)))
    return out


def tie_variation(runs):
    table=[r for r in runs if r["method"] in ("cgal","cgal_within")]
    by_source=defaultdict(list)
    pairs=defaultdict(dict)
    for r in table:
        by_source[r["dataset"],r["id"],r["method"]].append(r)
        pairs[r["dataset"],r["id"],r["session"],r["rep"]][r["method"]]=r
    out=[]
    for (dataset,name,m),rs in sorted(by_source.items()):
        outputs={r["raw_cgal_sha256"] for r in rs if r["raw_cgal_sha256"]}
        out.append(dict(dataset=dataset,id=name,method=m,runs=len(rs),native_attempts=sum(bool(r["raw_cgal_sha256"]) for r in rs),
                        distinct_native_pm31=len(outputs),status_variants=len(set(r["status"] for r in rs)),successes=sum(r["status"]=="success" for r in rs)))
    match=[(v["cgal"],v["cgal_within"]) for v in pairs.values() if "cgal" in v and "cgal_within" in v]
    both=[(a,b) for a,b in match if a["raw_cgal_sha256"] and b["raw_cgal_sha256"]]
    return out,dict(paired_calls=len(match),both_native=len(both),native_byte_diff=sum(a["raw_cgal_sha256"]!=b["raw_cgal_sha256"] for a,b in both),
                    status_diff=sum(a["status"]!=b["status"] for a,b in match))


def fmt(x,k=2):
    return "—" if x is None else f"{float(x):.{k}f}"


def write_report(stats,diff,prop,variation,integrity):
    method={(r["condition"],r["scope"],r["method"]):r for r in stats}
    pair={(r["condition"],r["scope"],r["method"],r["baseline"]):r for r in diff}
    rounds={(r["condition"],r["method"]):r for r in prop}
    f=lambda cond,scope,m,b:pair[cond,scope,m,b]
    m=lambda cond,code:method[cond,"all",code]
    b100=f("100","R2+","cross","within_full");b200=f("200","R2+","cross","within_full")
    fixed=f("fixed2","R2+","cross","within_full")
    strong=f("100","R2+","within_full","within_old")
    words=["# POLY04 已知资料的基线补查","",
    f"开发样本为 POLY03 已查看的 32 张完整蒙版，26 张 Oxford 与 6 张 MPEG-7。固定 256 字节上限，先运行固定两轮，再以三个独立会话、每源每法每会话两次测量比较 100/200 ms 实际交付。每个源的同次对照先平均重复，再对源等权。所有成功比较均核对实际 PM31 长度相等。本页只使用开发 CSV。",
    "",f"在原始 R≥2 的共同成功开发源上，跨圈相对充分圈内在两轮后平均少错 {fmt(fixed['mean_xor_saved'])} 像素，100 ms 和 200 ms 时分别少错 **{fmt(b100['mean_xor_saved'])}** 和 **{fmt(b200['mean_xor_saved'])}** 像素。100 ms 配对区间为 [{fmt(b100['lo'])}, {fmt(b100['hi'])}]，胜/平/负为 {b100['win']}/{b100['tie']}/{b100['loss']}，共 {b100['sources']} 个共同源。它只提供进入新确认的动机。跨域结论需另看各来源。","",
    "## 一　已计算的圈内组合原来用掉多少","",
    "两轮表中的轮数包括尝试后没有改善的最后一轮。所提议的候选数按真正进入联合评分的组合计。为凑足 24 对而进行的构造和排序包含在时间中。","",
    "| 方法 | 实际轮数 | 候选总数 | 每轮最少 / 中位 / 最多 | 1–23 对轮次 | 0 对轮次 | 接受总数 | 三角替点 / 跨圈接受 |","|---|---:|---:|---:|---:|---:|---:|---:|"]
    for code in METHODS:
        r=rounds.get(("fixed2",code))
        if r:
            words.append(f"| {NAMES[code]} | {r['rounds']} | {r['proposed']} | {r['min']} / {fmt(r['median'],0)} / {r['max']} | {r['under_24_nonzero']} | {r['none']} | {r['accepted']} | {r['accepted_triangles']} / {r['accepted_cross']} |")
    words+=["","充分同圈在构造全部可允许的组合后才取前 24 对；若原环没有可插入的原始采样点或缺少非相邻组合，可以少于 24。跨圈与充分圈内共享同圈动作的几何/结构规则。修正版只允许三角在本圈对边接收替点。真实三角夹具在保持 26 字节时由 126 错降至 56。[候选与三角自检](../../records/poly04/engine-check.json) · [完整规则](../../records/poly04/engine-methods.md)","","## 二　固定两轮与限时内交付的质量分开核算","",
    "XOR 是 FP+FN，数值越小越好。每个时间格仅取实际已接收的最后一份文件。表中“搜索结束”来自独立完整运行，含初始化、提案、合法性、序列化及回调；限时的尾部不会回填到早先的结果。","",
    "| 方法 | 两轮合格源 | 两轮均值 XOR | 两轮实际结束中位 / p95 ms | 100 ms 均值 XOR | 200 ms 均值 XOR | 100 / 200 ms 合格调用 |","|---|---:|---:|---:|---:|---:|---:|"]
    for code in METHODS:
        r,a,b=m("fixed2",code),m("100",code),m("200",code)
        words.append(f"| {NAMES[code]} | {r['delivered_sources']}/{r['source_count']} | {fmt(r['xor'])} | {fmt(r['search_end_median_ms'])} / {fmt(r['search_end_p95_ms'])} | {fmt(a['xor'])} | {fmt(b['xor'])} | {a['delivered_runs']}/{a['runs']} · {b['delivered_runs']}/{b['runs']} |")
    words+=["","不同方法的成功集可能不同，不能用该表的两行均值相减代替配对。下表仅对 R≥2、同次共同成功且文件字节完全相等的来源计算。正值表示左侧方法少错，每格括号内为源图胜/平/负。","",
    "| 试验方法相对基线 | 固定两轮，平均少错 | 100 ms，平均少错 | 200 ms，平均少错 |","|---|---:|---:|---:|"]
    def fcell(t):
        return f"{fmt(t['mean_xor_saved'])}（{t['win']}/{t['tie']}/{t['loss']}）"
    for left,right in PAIRS:
        cells=[fcell(f(c,"R2+",left,right)) for c in CONDITIONS]
        words.append("| "+NAMES[left]+" / "+NAMES[right]+" | "+" | ".join(cells)+" |")
    q=rounds["fixed2","within_full"]; o=rounds["fixed2","within_old"]
    words+=["",f"固定两轮实际候选总量从旧圈内的 {o['proposed']} 增至充分圈内的 {q['proposed']}。充分圈内相对历史圈内在 100 ms 的 R≥2 开发源平均变化 {fmt(strong['mean_xor_saved'])} 像素，胜/平/负 {strong['win']}/{strong['tie']}/{strong['loss']}。候选池更完整保证同圈比较的充分性；构造和评分都有成本，不能保证限时结果总是更好。",
    "", "固定三角规则的两个横向比较（历史双方、充分禁三角双方），以及固定范围只改三角规则的两个纵向比较都在同表呈现。扩大供受点组合会改变提案名次和后续搜索路径；各差值不应简单相加。R=1 的相同行动路径字节和不同完成轮次另有负对照。[单圈负对照](../../results/poly04/dev/analysis/r1_negative_control.csv) · [基线补查逐源差](../../results/poly04/dev_fixed/summary-source-pairs.csv)","","## 三　原版 CGAL 与共同后处理","",
    "CGAL squared 使用原版 worker，每次独立建网求解。原环必须与源环的顺序对应，确认方向和像素后才允许圈内区域移动。原始 CGAL 的最终输出和 cgal_within 在自己该次的第 0 检查点在表中分开。","",
    "| 阶段 | CGAL 原版独立行均值 XOR | CGAL 后处理自己的第 0 轮 XOR | 后处理截止 XOR | 相对本次起点平均少错 | CGAL / 后处理源覆盖 | 后处理已交付动作均数 |","|---|---:|---:|---:|---:|---:|---:|"]
    for c in CONDITIONS:
        a,b=m(c,"cgal"),m(c,"cgal_within")
        words.append(f"| {c} | {fmt(a['xor'])} | {fmt(b['initial_xor'])} | {fmt(b['xor'])} | {fmt(b['gain_from_own_seed'])} | {a['delivered_sources']}/{a['source_count']} · {b['delivered_sources']}/{b['source_count']} | {fmt(b['accepted_moves'])} |")
    multi={m:sum(r["method"]==m and r["distinct_native_pm31"]>1 for r in variation) for m in ("cgal","cgal_within")}
    words+=["",f"同一来源、会话和重复下，两条 CGAL 路径共有 {integrity['both_native']} 对都返回原生可打包尝试，其中 {integrity['native_byte_diff']} 对原生字节不同。集合内求多次也会打破等代价平局：原 CGAL 有 {multi['cgal']} 个源在六次调用中的原生字节出现多种结果，CGAL 后处理有 {multi['cgal_within']} 个。没有按图挑选更好的起点。",
    "","CGAL 后处理是完整方法对照。其成品相对自己本次初始化的收益衡量后处理本身。DP 强圈内与 DP 跨圈才共享同一起点，用于辨认跨圈机制。各方法实际完整结束耗时、交付耗时、候选数和失败类别见汇总，各次 worker 原生时间和独立启动记录保留在原运行表。[原生产出差异](../../results/poly04/dev_fixed/summary-cgal-variation.csv) · [每个试验运行](../../results/poly04/dev/runs.csv) · [原生起点及检查点](../../results/poly04/dev/checkpoints.csv)",
    "", "## 可复算入口","", "所有下表可直接由开发证据重建，无需重跑计时或读取确认资料。","",
    "```powershell","python -X utf8 -m poly04.engine_dev_report","```","",
    "[固定两轮逐图](../../results/poly04/dev_fixed/per_image.csv) · [完整轮次提案](../../results/poly04/dev_fixed/summary-rounds.csv) · [方法汇总](../../results/poly04/dev_fixed/summary-methods.csv) · [配对区间与胜平负](../../results/poly04/dev_fixed/summary-pairs.csv) · [确切整图评分审计](../../results/poly04/dev/exact_screen.csv)"]
    REPORT.parent.mkdir(parents=True,exist_ok=True)
    REPORT.write_text("\n".join(words)+"\n",encoding="utf-8")


def main():
    exams,runs=rows_for_summary()
    methods=method_summary(exams)
    contrasts,units=paired(exams)
    detail=proposal_stats()
    variance,integrity=tie_variation(runs)
    for name,data in [("methods",methods),("pairs",contrasts),("source-pairs",units),("rounds",detail),("cgal-variation",variance)]:
        save(FIXED/("summary-"+name+".csv"),data)
    write_report(methods,contrasts,detail,variance,integrity)
    print(REPORT.relative_to(ROOT),len(exams),"development rows",len(contrasts),"paired contrasts")


if __name__=="__main__":
    main()
