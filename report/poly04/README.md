# POLY04 审核与复现入口

先读[主控审核说明](review.md)、[按方法及预算的数据表](tables.md)和[已知 32 源开发补查](development.md)。所有结论对应科学冻结 ff70458c06a8fd36e68f546a9b350510968dcddf，抽样规则先行固定于 956cc05e6e249b9a276f5b75c899a8cd6837290d。旧探索提交 8e05ef79dc8f4e15e54fdb57ad576a0dd86ed88f 保留在原分支。

## 只复算固定结果

[私有审核 Release](https://github.com/Jupiter0914/dip-final-project-lab/releases/tag/poly04-confirm-review-v1) 包含实际源掩模、所有交付及原生可编码尝试、原始计时日志、逐区域测量、冻结源码与统计。独立附件给出整个 ZIP 的 SHA-256。解压后进入含 POLY04-INFO.json 的目录。有相应 Python 环境时此步骤可全程离线，原版 CGAL 的已存输出复核无需 WSL 或 C++ 编译。

```powershell
python -X utf8 -m poly04.review audit
```

核验覆盖输入家族与分层、每次调用方实际收到的字节和时钟、每份交付文件的 FP/FN/XOR/IoU/BF1/BF2/BF3、逐一匹配的孔及前景区域、源级配对区间、会话及留一源/类别稳定性。审核程序用另一绘图入口和像素统计，边界评分用欧氏距离变换独立计算，区域覆盖另用 OpenCV SAUF 与列联表核对。包内 POLY04-SHA256.csv 是按文件的完整性清单。机器与系统负载会改变再次运行的计时，离线审核复算的是原始回调的真实时点。

## 查看实际交付或编码一个自己的输入

```powershell
python -X utf8 -m poly04.run_one --file input-binary.png --budget 256 --deadline 100 --method cross --output local/my-selection.pm3
python -X utf8 -m poly03.export decode local/my-selection.pm3 local/my-selection.png
```

输入为单通道、非零代表前景的 PNG。命令在搜索过程中通过调用方接收 PM31，记录序列化、收到和搜索终止的毫秒时刻，结束后才将截止时已经收到的最后一个文件写盘。可用 --id 代替 --file 选择清单中的源，或选择 within_full、cgal、cgal_within、exact 等方法。结构失败或截止前无可用文件会明确报告。

## 从 Git 重跑

使用带标签的正常私有克隆。固定环境为 Python 3.12.13、NumPy 2.4.4、OpenCV 5.0.0.93、SciPy 1.18.1、ContourPy 1.3.3、Shapely 2.1.2 / GEOS 3.13.1。原机解释器为 E:/Miniconda/envs/pytorch_cv/python.exe。原生 CGAL 实验用单个热 worker，本机既有 WSL2 Ubuntu 22.04、CGAL 5.4、g++ 11.4、Boost、GMP 与 MPFR。平台、依赖、编译参数和官方库的平局变异记录见 [CGAL 说明](../poly03/cgal.md)。

```powershell
python -m pip install -r configs/poly03/requirements.txt
python -X utf8 scripts/prepare_data.py --check
python -X utf8 -m poly02.resources
python -X utf8 -m poly02.data
python -X utf8 -m poly04.data restore
python -X utf8 -m poly04.data_audit
python -X utf8 -m poly03.cgal_build
python -X utf8 -m poly04.freeze verify
python -X utf8 -m poly04.study serial confirm --output local/poly04-my-replay
python -X utf8 -m poly04.gather confirm --raw local/poly04-my-replay --output local/poly04-my-tables
python -X utf8 -m poly04.analysis local/poly04-my-tables --stage confirm --settings configs/poly04/confirm.json
```

重跑需新的输出路径，三个会话串行启动各自的 Python 和 CGAL worker。各次算法从已在内存中的单通道原图独立启动。原版 CGAL 的平局可能随进程内建网历史改变，结果报告保留每次原生点序列和两方法独自起点，禁止按源挑最好运行。确认会话入口核对已验证的原生 ELF；其他平台可用单图接口做探索，不能冒用原机冻结的时间对照。

## 记录导航

| 内容 | 文件 |
|---|---|
| 输入、采样与严格排除 | [原始已见项](../../records/poly04/known.csv)、[旧派生视图](../../records/poly04/known-views.csv)、[300 个新源](../../records/poly04/samples.csv)、[输入审计与元数据限制](../../records/poly04/data-report.md) |
| 主条件及冻结选择 | [科学协议](../../records/poly04/freeze.md)、[精确方法、全体与补充 ID](../../configs/poly04/confirm.json)、[分析与失败政策](../../records/poly04/analysis-protocol.md) |
| 真实计时与字节 | [逐次截止文件/缺失](../../results/poly04/confirm/per_run.csv)、[每次真实接收](../../results/poly04/confirm/checkpoints.csv)、[每轮候选与动作](../../results/poly04/confirm/rounds.csv)、[会话环境/冷启动](../../results/poly04/confirm/sessions.json) |
| 主统计 | [冻结判定](../../results/poly04/confirm/analysis/decision.json)、[源级差](../../results/poly04/confirm/analysis/source_pairs.csv)、[总体及独有交付](../../results/poly04/confirm/analysis/paired_coverage.csv)、[会话与删一源](../../results/poly04/confirm/analysis/stability.csv) |
| 结构、筛选与原生对照 | [逐匹配区域](../../results/poly04/confirm/regions.csv)、[启用结构判据的代价](../../results/poly04/confirm/structural_cost.csv)、[精确整图筛选审计](../../results/poly04/confirm/exact_screen.csv)、[CGAL 同调用起点](../../results/poly04/confirm/cgal_own_start.csv) |
| 可视化 | [案例与图的使用说明](analysis-figures.md)、[统计表使用说明](analysis-methods.md) |

文章所使用的 Oxford 标注及 LEMS 研究数据仅作为已知蒙版的编码输入。[Oxford 署名](../../records/attribution.md) · [原作者数据分发说明](../../records/poly02/research.md)