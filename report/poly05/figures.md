# 核心图的图注与来源

六幅图均提供 320 dpi PNG 和字形转路径的 SVG。按约 16 cm 宽度插入 Word 可以保留中文标注及误差图的原像素色块。英文和数字用 Times New Roman，中文用宋体，数学符号用 STIX。单图命令在项目或素材包根目录执行。

## 图 1　完整蒙版怎样交付

输入为内存中的完整二值数组。高精度核对与码长约束先决定可用点数，整图少错且结构合格才发布新的 PM31。底部时间轴是 Ragdoll_32，S1／重复 1 的跨圈轨迹，竖虚线为 100 ms。点取自 [checkpoints.csv](../../results/poly04/confirm/checkpoints.csv) 的 delivered_ms。观察点前最后可用的是第 1 轮。输入为[原始标注](replay/evidence/Ragdoll_32.png)。

[PNG](../../results/poly05/figures/01-encoding.png) · [SVG](../../results/poly05/figures/01-encoding.svg) · 运行 `python -B -X utf8 scripts/poly05/build.py --figure 1`。

## 图 2　一个点如何从一圈转到另一圈

Ragdoll_32，S1／重复 1，跨圈方法的第 0 → 1 轮。点集来自[动作前](replay/evidence/26afe570887013b86b8e3b6a1e9d7777a33e87aa84d4db5ec86fa9bc4cdf07bb.pm3)和[动作后](replay/evidence/284d379d6396980002a7dd1cee05ec58632c883a332cc9e86984175d65658d90.pm3)。供体环 1 从 7 点减到 6 点（叉号），接收环 0 从 29 点增到 30 点（加号）。每处均取相同的 53 × 53 像素窗口，叠画真实顶点与边。两份文件均为 254 字节，整图错分 1827 → 1735，实收 45.5401 → 82.8973 ms。动作索引记录在 [rounds.csv](../../results/poly04/confirm/rounds.csv)。同次圈内交付为 1789 错，因此该重复的跨方法差为 54 像素。

[PNG](../../results/poly05/figures/02-exchange.png) · [SVG](../../results/poly05/figures/02-exchange.svg) · 运行 `python -B -X utf8 scripts/poly05/build.py --figure 2`。

## 图 3　多环源差与会话区间

256 B、实收 100 ms。每个点为一个原始多环源，纵轴为增强圈内基线错分减去允许跨圈错分。Oxford 146 源、871 对，LEMS 7 源、42 对。三个会话各两次重复，先在源内平均。右侧总体与会话均值用源级 95% 区间，外域另列四类别整簇重抽。横零线标出两法持平，左侧蓝色虚线为该域平均差。 [逐源差](../../results/poly04/confirm/analysis/source_pairs.csv) · [会话](../../results/poly04/confirm/analysis/stability.csv) · [类别重抽](../../results/poly04/confirm/analysis/cluster.csv)

[PNG](../../results/poly05/figures/03-source-effects.png) · [SVG](../../results/poly05/figures/03-source-effects.svg) · 运行 `python -B -X utf8 scripts/poly05/build.py --figure 3`。

## 图 4　交付覆盖与不同对照的配对差

左表为每种方法成功的调用数／全部预定调用数，含全部三会话各两次重复。右图为 Oxford 的三个独立配对估计，几何原版 n=190、加后处理 n=191、同起点多环机制 n=146。点为均值，线为 95% 源级区间，三行分别取各自共同成功人群。 [覆盖](../../results/poly04/confirm/analysis/coverage.csv) · [比较条件](../../results/poly04/confirm/analysis/paired_summary.csv)

[PNG](../../results/poly05/figures/04-coverage-comparators.png) · [SVG](../../results/poly05/figures/04-coverage-comparators.svg) · 运行 `python -B -X utf8 scripts/poly05/build.py --figure 4`。

## 图 5　结构验收与匹配孔的面积

左图为 256 B 初始化的九个恢复源，按 legal_xor−unconstrained_xor 排序。虚线表示只对该九源求均值 128.89 像素。这个初始化反事实按源固定，不分计时会话。右图为 British_Shorthair_38，S2／重复 2，实收 100 ms，取景 (348, 88, 28)。两种方法交付了字节相同的文件，故共用一幅解码图。参考孔 2 为 271 像素，解码和交集面积均为 96 像素。 [初始化明细](../../results/poly04/confirm/structural_cost.csv) · [逐身份面积](../../results/poly04/confirm/regions.csv) · [圈内字节](replay/evidence/5d7ebcb85d096bee5f5db7d4246c53b0d3a0ec2dfe6f118961a31dd11fc539c5.pm3)、[跨圈字节](replay/evidence/5d7ebcb85d096bee5f5db7d4246c53b0d3a0ec2dfe6f118961a31dd11fc539c5.pm3)。

[PNG](../../results/poly05/figures/05-structure.png) · [SVG](../../results/poly05/figures/05-structure.svg) · 运行 `python -B -X utf8 scripts/poly05/build.py --figure 5`。

## 图 6　典型源、持平源和最差源

三行沿用预先规定的正改善中位附近、最接近零、源均差最小的选择。每源取已登记的实际配对重复。在完整原图用方框标出取景，同行两幅错分图取相同像素窗口。橙色是多填 FP，蓝色是漏填 FN。[逐次观察](../../results/poly04/confirm/per_run.csv) · [源与裁片](../../results/poly04/confirm/figures/figure-cases.csv)

- Egyptian_Mau_46，S1／重复 1。源均差 4.5 像素，图示文件 313 → 313 错。取景 (x, y, 边长) = (376, 131, 128)。[圈内字节](replay/evidence/2ca3f3f3b6e8b57ed7ca5bd026a1d7d495530dcd0a35d32647a9a651feae8455.pm3)、[跨圈字节](replay/evidence/2ca3f3f3b6e8b57ed7ca5bd026a1d7d495530dcd0a35d32647a9a651feae8455.pm3)。
- Abyssinian_3，S1／重复 1。源均差 0 像素，图示文件 1237 → 1237 错。取景 (x, y, 边长) = (205, 120, 200)。[圈内字节](replay/evidence/13617c5144b70fa743a4d82612bfa4de194e93311c20abaa03b53fd41bc9b499.pm3)、[跨圈字节](replay/evidence/13617c5144b70fa743a4d82612bfa4de194e93311c20abaa03b53fd41bc9b499.pm3)。
- miniature_pinscher_61，S1／重复 1。源均差 -27.5 像素，图示文件 1369 → 1402 错。取景 (x, y, 边长) = (94, 328, 125)。[圈内字节](replay/evidence/a9985027c21b5d9de6be31e67ee432c2a548471a5d12149c15637cf648b3c7f7.pm3)、[跨圈字节](replay/evidence/a17c35fd15ae4dc4ea562637fed45c2430c95f1da6e9d08244a19306e4106729.pm3)。

[PNG](../../results/poly05/figures/06-cases.png) · [SVG](../../results/poly05/figures/06-cases.svg) · 运行 `python -B -X utf8 scripts/poly05/build.py --figure 6`。
