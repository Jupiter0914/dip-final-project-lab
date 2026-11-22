
"""Generate the figures, captions and replay strictly from existing files."""
import argparse
import json
import os
from pathlib import Path
from facts import MAT, csv_bytes, build as make_facts
import evidence
import figures

os.environ.setdefault("SOURCE_DATE_EPOCH","946684800")  # Stable SVG metadata.

def caption_book(data):
    a=data["action"];before,after=a["before"],a["after"]
    cases=data["cases"]
    def files(c):
        return "、".join(f"[{label}字节](replay/{c['methods'][m]['pm31']})" for label,m in [("圈内","within_full"),("跨圈","cross")])
    def run_ids(c):
        return f"{c['id']}，{c['session']}／重复 {c['rep']}"
    r=next(c for c in cases if c["id"]==a["id"])
    hole=next(c for c in cases if c["reason"]=="absolute_structure")
    cases3=[c for c in cases if c["dataset"]=="Oxford" and c["reason"] in ("typical_positive","nearest_zero","worst")]
    case_lines="\n".join(f"- {run_ids(c)}。源均差 {c['source_mean']:g} 像素，图示文件 {c['methods']['within_full']['xor']} → {c['methods']['cross']['xor']} 错。"
                         f"取景 (x, y, 边长) = {tuple(c['crop'])}。{files(c)}。" for c in cases3)
    repeat_file="[逐次观察](../../results/poly04/confirm/per_run.csv)"
    texts=[
        ("完整蒙版怎样交付",f"输入为内存中的完整二值数组。高精度核对与码长约束先决定可用点数，整图少错且结构合格才发布新的 PM31。底部时间轴是 {run_ids(r)} 的跨圈轨迹，竖虚线为 100 ms。点取自 [checkpoints.csv](../../results/poly04/confirm/checkpoints.csv) 的 delivered_ms。观察点前最后可用的是第 1 轮。输入为[原始标注](replay/{r['source_file']})。"),
        ("一个点如何从一圈转到另一圈",f"{run_ids(r)}，跨圈方法的第 0 → 1 轮。点集来自[动作前](replay/evidence/{before['sha256']}.pm3)和[动作后](replay/evidence/{after['sha256']}.pm3)。供体环 {a['donor']} 从 7 点减到 6 点（叉号），接收环 {a['receiver']} 从 29 点增到 30 点（加号）。"
         f"每处均取相同的 53 × 53 像素窗口，叠画真实顶点与边。两份文件均为 {before['size']} 字节，整图错分 {before['xor']} → {after['xor']}，实收 {before['received_ms']:.4f} → {after['received_ms']:.4f} ms。动作索引记录在 [rounds.csv](../../results/poly04/confirm/rounds.csv)。同次圈内交付为 1789 错，因此该重复的跨方法差为 54 像素。"),
        ("多环源差与会话区间","256 B、实收 100 ms。每个点为一个原始多环源，纵轴为增强圈内基线错分减去允许跨圈错分。Oxford 146 源、871 对，LEMS 7 源、42 对。三个会话各两次重复，先在源内平均。右侧总体与会话均值用源级 95% 区间，外域另列四类别整簇重抽。横零线标出两法持平，左侧蓝色虚线为该域平均差。"
         " [逐源差](../../results/poly04/confirm/analysis/source_pairs.csv) · [会话](../../results/poly04/confirm/analysis/stability.csv) · [类别重抽](../../results/poly04/confirm/analysis/cluster.csv)"),
        ("交付覆盖与不同对照的配对差","左表为每种方法成功的调用数／全部预定调用数，含全部三会话各两次重复。右图为 Oxford 的三个独立配对估计，几何原版 n=190、加后处理 n=191、同起点多环机制 n=146。点为均值，线为 95% 源级区间，三行分别取各自共同成功人群。"
         " [覆盖](../../results/poly04/confirm/analysis/coverage.csv) · [比较条件](../../results/poly04/confirm/analysis/paired_summary.csv)"),
        ("结构验收与匹配孔的面积",f"左图为 256 B 初始化的九个恢复源，按 legal_xor−unconstrained_xor 排序。虚线表示只对该九源求均值 128.89 像素。这个初始化反事实按源固定，不分计时会话。右图为 {run_ids(hole)}，实收 100 ms，取景 {tuple(hole['crop'])}。两种方法交付了字节相同的文件，故共用一幅解码图。参考孔 2 为 271 像素，解码和交集面积均为 96 像素。"
         f" [初始化明细](../../results/poly04/confirm/structural_cost.csv) · [逐身份面积](../../results/poly04/confirm/regions.csv) · {files(hole)}。"),
        ("典型源、持平源和最差源",f"三行沿用预先规定的正改善中位附近、最接近零、源均差最小的选择。每源取已登记的实际配对重复。在完整原图用方框标出取景，同行两幅错分图取相同像素窗口。橙色是多填 FP，蓝色是漏填 FN。{repeat_file} · [源与裁片](../../results/poly04/confirm/figures/figure-cases.csv)\n\n"+case_lines)
    ]
    sections=["# 核心图的图注与来源",
              "六幅图均提供 320 dpi PNG 和字形转路径的 SVG。按约 16 cm 宽度插入 Word 可以保留中文标注及误差图的原像素色块。英文和数字用 Times New Roman，中文用宋体，数学符号用 STIX。单图命令在项目或素材包根目录执行。"]
    for i,((title,caption),name) in enumerate(zip(texts,figures.LABELS),1):
        sections.append(f"## 图 {i}　{title}\n\n{caption}\n\n[PNG](../../results/poly05/figures/{name}.png) · [SVG](../../results/poly05/figures/{name}.svg) · "
                        f"运行 \x60python -B -X utf8 scripts/poly05/build.py --figure {i}\x60。")
    (MAT/"figures.md").write_text("\n\n".join(sections)+"\n",encoding="utf-8",newline="\n")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--figure",type=int,choices=range(1,7),help="Render one numbered plate only.")
    a=parser.parse_args()
    figures.style()
    if a.figure:
        data=json.loads((evidence.REPLAY/"index.json").read_text(encoding="utf-8"))
        functions=[figures.flow,figures.action_figure,figures.effects,figures.delivery,figures.structure,figures.cases]
        functions[a.figure-1](data)
        return
    data=evidence.build()
    ledger=make_facts()
    (MAT/"facts.csv").write_bytes(csv_bytes(ledger))
    figures.generate()
    caption_book(data)
    template=Path(__file__).with_name("replay-template.html").read_text(encoding="utf-8")
    encoded=json.dumps(data,ensure_ascii=False,separators=(",",":")).replace("<",r"\u003c")
    (evidence.REPLAY/"index.html").write_text(template.replace("__SAVED_DATA__",encoded),encoding="utf-8",newline="\n")
    print(f"Generated {len(ledger)} sourced facts, six plates, {len(data['cases'])} decoded pairs.")


if __name__=="__main__":
    main()
