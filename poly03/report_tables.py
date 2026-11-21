"""Compact audit tables with equal-source estimates and separate coverage denominators."""
from collections import Counter
import numpy as np
from .full_data import ROOT,OUT
from .full_summary import ci
from poly02.data import rows,save_rows

NAMES={"perimeter":"按周长","independent_dp":"独立 DP","feasible_add":"可加排序后试配","allocation_whole":"整图排序分配",
       "cgal_squared":"CGAL squared","cgal_scaled":"CGAL scaled","exchange_within":"仅圈内删插","exchange_cross":"仅跨圈转移",
       "exchange_add":"可加评分删插","exchange_whole":"整图评分删插"}
ST={"simple":"简单","components":"分离部件","holes":"孔","near":"近接边界"}


def main():
    first=rows(OUT/"per_image.csv")
    second=rows(ROOT/"results/poly03/repetition/per_image.csv")
    sections=["# 完整蒙版开发数据表","","每格以原图为统计单位。覆盖率列保留所有原始预算尝试；平均质量和实际字节只在该方法成功交付的原生文件上计算。不同成功集的均值需配合后面的相同文件长度配对表阅读。时间列为独立复跑从原始二值数组到内存 PM31 的完整路径计费（共享前缀按实测计入各消费者），解码包括几何合法性检查和原尺寸回填。",""]
    for budget in ("128","256","512","1024"):
        sections+=["## "+budget+" 字节上限","","| 方法 | 成功 / 全部 | 低于下界 / 未找到 / 不支持 | 成功文件字节范围 | FP / FN 均值 | XOR | IoU | BF2 | 复跑编码中位 / p95 ms | 复跑解码中位 ms |",
                   "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for method,display in NAMES.items():
            source=[r for r in first if r["budget"]==budget and r["method"]==method]
            a=[r for r in source if r["status"]=="success"]
            b=[r for r in second if r["budget"]==budget and r["method"]==method and r["status"]=="success"]
            cnt=Counter(r["status"] for r in source)
            cell=lambda key:f"{np.mean([float(r[key]) for r in a]):.4f}" if a else "—"
            sizes=[int(r["file_bytes"]) for r in a]
            cost=[float(r["encode_ms"]) for r in b]
            dec=[float(r["decode_ms"]) for r in b]
            sizes=f"{min(sizes)}–{max(sizes)}" if sizes else "—"
            sections.append(f"| {display} | {len(a)}/{len(source)} | {cnt['below_proved_lower_bound']}/{cnt['search_no_valid_output']}/{cnt['unsupported_representation']} | {sizes} | {cell('fp')} / {cell('fn')} | {cell('xor')} | {cell('iou')} | {cell('bf2')} | {np.median(cost):.2f} / {np.quantile(cost,.95):.2f} | {np.median(dec):.2f} |")
        sections.append("")
    sections+=["## 输入结构分层","","三个主预算合计每层 8 张、24 个设置。分方法成功数和配对质量单列。改善是整图评分删插相对可行 DP 的变化，同一源图先平均共同成功的预算。","",
               "| 输入层 | 周长 | 独立 DP | 可行 DP | CGAL squared | 删插 | 配对原图数 | 平均少错像素及 95% 区间 | IoU 变化（百分点） |",
               "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    agg=rows(OUT/"paired_summary.csv")
    for s,display in ST.items():
        counts=[sum(r["status"]=="success" for r in first if r["method"]==m and r["stratum"]==s and r["budget"]!="1024")
                for m in ("perimeter","independent_dp","feasible_add","cgal_squared","exchange_whole")]
        group={r["metric"]:r for r in agg if r["budget"]=="primary" and r["stratum"]==s and r["method"]=="exchange_whole" and r["baseline"]=="feasible_add"}
        er=group["xor_saved"];q=group["iou_gain_pp"]
        sections.append("| "+" | ".join([display,*map(str,counts),er["sources"],f"{float(er['mean']):.2f} [{float(er['lo']):.2f}, {float(er['hi']):.2f}]",f"{float(q['mean']):+.4f}"])+" |")
    lookup=lambda table:{(r["id"],r["budget"],r["method"]):r for r in table}
    cg_comp=[]
    for rep,table in enumerate((first,second),1):
        index=lookup(table)
        for m in ("feasible_add","exchange_whole"):
            for base in ("cgal_squared","cgal_scaled"):
                per={}
                for r in table:
                    if r["method"]!=m or r["budget"]=="1024":continue
                    b=index[r["id"],r["budget"],base]
                    if r["status"]==b["status"]=="success":
                        assert r["file_bytes"]==b["file_bytes"]
                        per.setdefault(r["id"],[]).append(100*(float(r["iou"])-float(b["iou"])))
                vals=[np.mean(per[n]) for n in sorted(per)]
                lo,hi=ci(vals)
                cg_comp.append(dict(run=rep,method=m,baseline=base,n=len(vals),matched_settings=sum(map(len,per.values())),
                    iou_gain_pp=np.mean(vals),lo=lo,hi=hi))
    save_rows(ROOT/"results/poly03/repetition/paired_cgal.csv",cg_comp)
    sections+=["","[原始逐图表](../../results/poly03/full/per_image.csv) · [独立复跑逐图表](../../results/poly03/repetition/per_image.csv) · [完整源级配对区间](../../results/poly03/full/paired_summary.csv) · [CGAL 双次配对](../../results/poly03/repetition/paired_cgal.csv)"]
    (ROOT/"report/poly03/full-tables.md").write_text("\n".join(sections)+"\n",encoding="utf-8")


if __name__=="__main__":main()
