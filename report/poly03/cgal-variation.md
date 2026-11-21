# CGAL 5.4 相等代价的复核

**原版 CGAL 的同一幅输入可得到不同的几何简化结果。解决等代价顺序后，可加误差预排删插相对 CGAL 的开发集比较仍保持原方向。** 原版两个完整实验留作原始数据。本文另列坐标次级键的敏感性结果，未用它替换原表。

## 在哪一步分叉

在两次已有的完整实验中，每种代价都有 98 个“输入 × 预算”条件（96 个主预算条件，加 2 个 1024 B 补充条件）。每种代价有 95 对实际输出文件，3 个低于表示下界。平方距离 `squared` 有 41/95 对字节不同，邻距归一化 `scaled` 有 44/95 对不同。85 对差异全部来自多环，单环的 48 对全部一致。差异中 75 对两次都满足结构约束，9 对两次都失败，1 对从成功变为数字结构失败。两次成功数分别为 88/98 与 87/98（squared），89/98 与 89/98（scaled）。[逐条件文件哈希、状态和错分](../../results/poly03/cgal_variation/paired-full-runs.csv)

以近接开发图 scottish_terrier_199 为见证。原始全精度有 3 个环、618 个顶点，128 B 预算最多允许 26 个顶点。对不改动的生产 worker 使用四个新进程，前两个从空历史开始，另两个预热既有清单中前一或前三张源图，每次在同一进程反复输入完全相同的环。两种成本各做 24 次。squared 得到 5 种文件，错分 4,450–4,896，数字结构有时通过、有时失败。scaled 得到 5 种文件，错分 8,330–8,779，这张图上均未通过数字结构。单个进程内连续调用也可以不同。[未经修改的原版重复实验](../../results/poly03/cgal_variation/unmodified-worker.csv)

5.4 的 `Constraint_id::operator<` 按内部顶点列表指针比较，所有约束保存在 `std::set<Constraint_id>` 中。简化器在 `initialize_costs()` 中按该集合的遍历顺序将各环顶点加入可变优先队列。其 `Compare_cost` 只比较数值代价；顶点 ID 用于堆元素的位置索引。因而同一组环的分配历史可以改变遍历顺序，完全相同的几何代价也可能选中不同的顶点。这里的证据来自所用版本源码与实际出堆日志。通用随机种子不足以固定本次现象。[约束标识和集合](https://github.com/CGAL/cgal/blob/v5.4/Triangulation_2/include/CGAL/Triangulation_2/internal/Polyline_constraint_hierarchy_2.h) · [简化器、队列比较与初始化](https://github.com/CGAL/cgal/blob/v5.4/Polyline_simplification_2/include/CGAL/Polyline_simplification_2/simplify.h)

将 `CGAL::get_default_random()` 每次重置为种子 7 仍能复现分叉。squared 的两次环遍历顺序为 `0,2,1`、`1,2,0`，第一次出堆分别选 (1328,951) 和 (971,564)，当前点数均为 618，代价均为 **2.4827586206896552**，最终错分为 4,450 和 4,896。scaled 的两条轨迹在第 23 次出堆首次不同，当前点数同为 596，代价均为 **0.0067186240257995165**，最终错分为 8,392 和 8,779。[首次分叉见证](../../results/poly03/cgal_variation/first-divergence.json) · [默认种子与固定种子 7、47 的逐次结果](../../results/poly03/cgal_variation/trace-runs.csv)

## 次级键敏感性实验

在私有临时头文件副本中加一个**独立改编**。数值代价不同时仍按原规则比较，只有数值精确相等时才按原整数点的 (x,y) 字典序打破平局，无数值扰动。适配器输入的环间无共用顶点，因此该坐标键能区分这些候选点。原版数据、源包、生产 worker 的字节都未更换。见证图对每种代价、每种策略做 30 次，用默认种子、7 和 47，每个种子两个新进程、每进程 5 次。启用坐标键后每种代价分别只有一条出堆轨迹和一份 PM31。该图的 squared 错分为 4,359，scaled 为 9,415。次级键改变了具体结果，没有为质量选择有利顺序。[按种子与策略汇总](../../results/poly03/cgal_variation/seed-and-tie-summary.csv)

再在全部 32 个既有开发源上使用两种代价。对 190 个有实际候选的条件，各用 7、47 两个种子独立启动、各重复 3 次，共 1,140 次。142 个条件中环遍历顺序实际发生变化，190/190 个条件的全部出堆轨迹、每个条件的最终 PM31 均逐一一致。此结论限于本次版本和样本。[逐次轨迹及文件哈希](../../results/poly03/cgal_variation/xy-all-trials.csv) · [逐图预算与结构检验](../../results/poly03/cgal_variation/xy-primary.csv)

下表只在同一码长且两边都满足公共矢量与数字结构要求的输出中计像素差，先在每个源内平均可配对预算，再赋予每个源相同权重。正值表示 `exchange_add` 比几何对照少错。全部预算的可行性仍另列；下列百分比不代表未成功输入。

| 预算口径 | CGAL 代价 | 原表 / 原版重跑 / 坐标适配，exchange_add 相对少错 | 坐标适配共同成功 / 只 exchange / 只 CGAL / 均未成功 | 有共同结果源数 |
|---|---|---:|---:|---:|
| 主三档共 96 条，128/256/512 B | squared | 20.56% / 20.44% / **20.70%** | 85 / 6 / 0 / 5 | 30 |
| 主三档共 96 条 | scaled | 68.52% / 68.20% / **69.75%** | 85 / 6 / 0 / 5 | 31 |
| 含两项 1024 B 补充档，共 98 条 | squared | 24.03% / 23.79% / **24.09%** | 87 / 6 / 0 / 5 | 32 |
| 含两项 1024 B 补充档，共 98 条 | scaled | 69.35% / 69.04% / **70.63%** | 87 / 6 / 0 / 5 | 32 |

主三档的坐标适配 squared 源配对 95% 区间为 **18.31%–23.07%**；含 pocket-14 和 turtle-3 各一项 1024 B 补充档时为 **19.60%–30.48%**。区间用 10,000 次整源 bootstrap，种子 3417。各比较的可配对源图上，平均错误像素差方向均有利于 exchange_add。此表回答质量与可行性的排序敏感性，采集完整出堆轨迹的计时不用于速度比较。[主三档](../../results/poly03/cgal_variation/exchange-main-budgets.csv) · [含两项补充档](../../results/poly03/cgal_variation/exchange-comparison.csv)

## 存档与复算

190 个实际 PM31 已按 `xy-primary.csv` 的 `blob` 字段原名包含在 [encoded.zip](../../results/poly03/cgal_variation/encoded.zip)。6 个低于已证下界的条件在 CSV 保留独立状态。包内同时保留成功输出和达到目标点数但数字结构不合格的尝试。直接从 ZIP 校验每个成员长度及 SHA-256，再从共同原始蒙版重算矢量环关系、数字部件/孔对应和整图 XOR。该检查需要已记载的 32 份源输入和项目的 Python 像素解码依赖。[文件/构建哈希与复核计数](../../results/poly03/cgal_variation/xy-audit.json)

```powershell
python -X utf8 -m poly03.cgal_xy_sensitivity --verify
```

重新观察未经修改的 CGAL 行为使用第一条命令。后两条使用单独的诊断程序，仅在 WSL 临时目录拷贝并修改 `simplify.h` 的两个比较器重载；编译前验证上游头文件 SHA-256。需先按 [CGAL 构建说明](cgal.md) 准备已锁定的包和 WSL 依赖。每条命令写入自己的新目录；已记录的对照结果仍可单独审阅。

```powershell
python -X utf8 -m poly03.cgal_recheck --output local/poly03/replay-cgal-upstream
python -X utf8 -m poly03.cgal_variation --output local/poly03/replay-cgal-traces
python -X utf8 -m poly03.cgal_xy_sensitivity --output local/poly03/replay-cgal-cohort
```

在复现原版数值时应允许上面实测到的等价决策分歧。稳定适配使用不同的策略名称；官方库原输出、稳定适配输出与两套原版复跑表分开保存。
