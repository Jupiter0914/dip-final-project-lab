# POLY03 开发包的运行与复核

本轮是独立分支上的开发研究。原始样本均为已见资料。[四个问题与结论](review.md) · [直接先例](../../records/poly03/related.md) · [格式与结构规则](format.md) · [总体和分层结果](full-tables.md) · [后续确认方案](../../records/poly03/next-confirmation.md)

## 运行一个真实编码

在项目根目录使用 Python 3.12。本机已具备计算环境，原解释器为 E:/Miniconda/envs/pytorch_cv/python.exe。下列命令默认采用可加预排并检查完整组合，返回实际字节数、顶点转移、XOR、FP/FN、IoU 及 BF1/2/3。另可用 --input 输入自己的单通道二值 PNG，非零为前景。预算或表示失败会给出状态并以退出码 2 结束。

```powershell
python -X utf8 -m poly03.export encode --source-id havanese_26 --budget 256 --method additive --output local/poly03-example.pm3
python -X utf8 -m poly03.export decode local/poly03-example.pm3 local/poly03-example.png
```

已用该入口验证上述实例输出为 254 字节，实际错分 465 像素，与批量实验编码完全同字节。空蒙版在 10 字节上限生成合法空图。身份验证需比较原图与解码，解码器本身不需要原图。

## 从干净检出恢复输入

普通 Git 只包含小型表格、代码、图件和实际编码的紧凑归档。全量原图及构建依赖位于忽略目录。已拥有 POLY02 审核包时无须再次下载原图。当前已知包 SHA-256 为 9c3e998bd3c464a42db840349f9ca6e5c63418e65c51ec6f319ad83a37413d79，恢复命令先验哈希，再只写入缺少的已登记文件，遇到不同字节会停止。

```powershell
python -m pip install -r configs/poly03/requirements.txt
gh release download poly02-review-v1 --repo Jupiter0914/dip-final-project-lab --pattern poly02-review.zip --dir local/poly03-bootstrap
python -X utf8 -m poly03.restore local/poly03-bootstrap/poly02-review.zip
```

原版 CGAL 的第二次完整进程输出与确定性平局适配分别保存在 [重复对照](../../results/poly03/repetition/summary.csv) 与 [单独的敏感性材料](../../results/poly03/cgal_variation/exchange-comparison.csv)。

本机沿用已有 NumPy 2.4.4、OpenCV Python 5.0.0.93、SciPy 1.18.1、Pillow 12.2、Matplotlib 3.11、ContourPy 1.3.3。Shapely 2.1.2 / GEOS 3.13.1 单独安装在 local/poly03/deps，全局环境未改。原始脚本也可从牛津大学公开标注及 Panagiotakis 分发的原包按 POLY02 README 重建资料。先前数据署名、原 SHA 和许可说明继续适用。[Oxford 署名](../../records/attribution.md) · [既有外形原始来源](../../records/poly02/research.md)

## 在离线环境核验已发布结果

以下四条命令用已归档的真实文件复算，无需启动 WSL、CGAL 或 MATLAB。完整蒙版审计另行解析 PM31，用另一种 OpenCV 绘图入口按协议生成环掩模，使用 SciPy 重新标记前景/背景、核对重叠身份和邻接图。它检查归档里的成功与可序列化的拒绝尝试、两轮官方 CGAL 的实际输出、2,132 个分配的两个误差、完整与否的候选排名依据，以及截止时刻所取的文件。单圈和细部使用各自的 POL1 实际编码归档。

```powershell
python -X utf8 -m poly03.full_verify audit
python -X utf8 -m poly03.single_analyze audit
python -X utf8 -m poly03.detail_analysis --verify-only
python -X utf8 -m poly03.cgal_xy_sensitivity --verify
```

若要重做单圈强负例的全部 1,244,760 次完整画布评分，可运行 `python -X utf8 -m poly03.single_replay_full`。完整蒙版编码归档在 results/poly03/full/outputs.zip，逐行 SHA 在各分表中。复算实际输出与从新进程重新调用 CGAL 是两项检查，后者可能因同代价打破顺序而输出其他合法的顶点序列。[CGAL 构建与差异说明](cgal.md)

## 重做实验

完整同场基线需要官方 CGAL 包。默认 Windows 使用 WSL2 Ubuntu-22.04，将受校验的 5.4 官方头文件解包到专用目录，编译自己的桥接程序。命令、构建依赖版本、官方包哈希及 Linux 运行条件见 CGAL 说明。普通编码和已存文件复核可独立进行。为保留原记录，重跑指定新的输出路径。

```powershell
python -X utf8 -m poly03.cgal_build
python -X utf8 -m poly03.cgal_check
python -X utf8 -m poly03.full_run --output local/repro03-full
python -X utf8 -m poly03.repair --output local/repro03-repair
python -X utf8 -m poly03.phase_control --output local/repro03-phase
python -X utf8 -m poly03.anytime --output local/repro03-time
```

最后一项计时先核实时空缓存的候选评分、行动和整幅像素，再在 256 字节上限比较 100/200 ms 时实际可用的同码长文件。当时超时的文件保存在检查点时间序列中，不能倒计成较早的成绩。初测的双重评分额外开销可用 --instrumented 单列再现。单圈与局部结构试验的重运行命令和随机种子分别见 [单圈报告](single.md) 和 [细部报告](details.md)。

## 证据入口

| 项目 | 结果 |
|---|---|
| 输入清单、完整渲染、四类状态与真实 PM31 | [源清单](../../records/poly03/full-sources.csv) · [主逐图表](../../results/poly03/full/per_image.csv) · [独立进程逐图表](../../results/poly03/repetition/per_image.csv) · [编码文件](../../results/poly03/full/outputs.zip) |
| 排序耦合、交换与可行性 | [每个分配候选](../../results/poly03/full/allocation_candidates.csv) · [配对差和区间](../../results/poly03/full/paired_summary.csv) · [每一步原子移动](../../results/poly03/full/moves.json) · [搜索失败的原始尝试](../../results/poly03/feasibility/triggered.json) |
| 相同可用时间、未用于接受的指标 | [实际截止文件](../../results/poly03/time_fair/per_image.csv) · [全部时间检查点](../../results/poly03/time_fair/checkpoints.csv) · [源级比较](../../results/poly03/time_fair/paired_summary.csv) |
| 成功、无收益与失败 | [多圈案例](../../results/poly03/full/figures/full-cases.png) · [真实跨圈转移](../../results/poly03/full/figures/vertex-transfer.png) · [合法误差抵消实例](../../results/poly03/full/figures/cancellation.png) |
| 单圈停滞及所有对照 | [逐图表](../../results/poly03/single/all_outputs.csv) · [七个真实逃逸](../../results/poly03/single/mpeg/winners.csv) · [原图移动放大](../../results/poly03/single/mpeg/device5-move.png) |
| 骨架与局部诊断 | [输入特征](../../results/poly03/detail/features.csv) · [七种编码的复核](../../results/poly03/detail/verification.json) · [局部案例](../../results/poly03/detail/examples.png) |

POLY02 稳定提交为 cc2e60175acc1b2c07906551b71eb0905f8b1c7b；POLY03 分支不改写旧标签或旧实验数据。文献核对、程序编写、实验运行、案例图及独立复算均有 Codex 工具辅助，未进行人工编辑效率测试。