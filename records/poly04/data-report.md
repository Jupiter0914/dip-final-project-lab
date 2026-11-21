# POLY04 输入与隔离审计

**清单包含 200 张新 Oxford 官方 test 照片和 100 个 LEMS 排重文件族代表。** 输入政策固定在提交 956cc05e6e249b9a276f5b75c899a8cd6837290d。主控允许后才读取候选像素作分层和家族筛查，选样脚本没有导入 PM31 编码方法或读取其结果。[输入政策](data-protocol.md) · [完整样本清单](samples.csv)

| 项目 | 实际数量或范围 |
|---|---|
| 旧源清单 | 336 个 Oxford 原照，70 个已评 MPEG 和 3 个预留格式实例，2 个 UPF 实例和 2 条同名 LEMS 归档对照，另有 29 个旧论文视觉示例。442 条登记含同源别名与排除探针 |
| 旧源派生视图 | 407 个已评分的最大外圈目标及 36 个明确的二倍最近邻诊断输入，共 443 条，记录其来源 ID、变换和像素哈希 |
| Oxford | 官方 test 的 3669 张均检查原始标注。除这批图外，还纳入 36 张已用 trainval 同源排查；3705 张对应 RGB 全部可用。去旧及排重后，简单 / 孔 / 多部件 / 近接层各有 2002 / 408 / 606 / 248 个可用代表，按固定规则各取 50 |
| LEMS | 作者 RAR 中 1462 个编号 GIF。整类排除 Fish-a 与 Building 的 343 个文件，7 个可用类别编号中只保留跨数据集/跨类别排重簇的一名代表，并使用同类编号间隔。最终各取 Container 13、FruitorVegetable 17、MiscAnml 17、Person 17、Robot 17、Toddler 15、Turtle 4 |
| 图去重 | 5714 条原始/派生/示意输入登记，经 2057 条关联形成 4944 个连通簇。原字节、原生像素、裁边八方向、尺度与近似轮廓、已知来源链和 Oxford 全照指纹分别检查。RGB 比较产生 8 条关联。若簇中包含已知材料或排除前缀，全簇排除 |
| 最终子组 | Oxford 的完整输入标号对应 150 张多环、50 张单环。LEMS 为 10 个多环、90 个单环，多环只分布在 Robot 5、Person 2、MiscAnml 2、FruitorVegetable 1。补充分析每个来源预选 24 张。外域主增量的人数还可能因方法/截止时点共同成功而进一步减少 |

独立审计从已记录的边重建稀疏无向连通分量，重新计算家族 ID、排除覆盖、配额与编号间隔，逐一重读 300 份原标注核对文件 SHA、规范原尺寸像素 SHA、裁边等价类、结构层及环数。完整重选与冻结清单 ID、顺序一致；已知原始或派生文件与入选清单的原字节/规范像素交集均为 0，选中簇没有重复。20 个旧论文视觉探针落入含其他文件的排除簇，如论文图中两幅龟形对应同一个 Turtle002；其余无原始 ID 的图示按事先阈值排查。原论文示意图和原始评分源在 known.csv 中分别标记。[阶段和源哈希](known.csv) · [派生视图](known-views.csv) · [全部输入去向](data-screening.csv) · [关联依据](data-links.csv) · [复核记录](data-audit.json)

数据源提供的是编号、类别和形状，未提供完整拍摄会话或实物身份。LEMS 的“文件族”指明确同源关系和变换/近重复边的传递闭包；一个物体的大幅形变有可能超出识别范围。七个类别和类别内编号的间隔减少可疑连续片段被多计的风险，不能当成 100 个经数据所有者认证的不同物体。相似轮廓也可能被保守合并。Oxford 为结构均衡评测分布，各层的 50 张并非自然频率。LEMS 未抽新 MPEG 文件或加载器输出补齐人数；不同来源分别汇报。

## 输入恢复

若审核包已包含 data/poly04/sources/，可直接对实际文件执行下列指令。独立核对图所需 screening 与 links 表均在普通 Git。

```powershell
python -X utf8 -m poly04.data_audit
```

在普通检出中，先按已有入口获得原始标注归档和作者 RAR，再只恢复被冻结的 300 个文件。复算方法得分无需 RGB 归档。重新做完整输入去重时才使用 791,918,971 字节的官方原照归档，其 SHA-256 为 67195c5e1c01f1ab5f9b6a5d22b8c27a580d896ece458917e61d459337fa318d。

```powershell
python -X utf8 scripts/prepare_data.py --check
python -X utf8 -m poly02.resources
python -X utf8 -m poly04.data restore
python -X utf8 -m poly04.data_audit
```

选中清单的 SHA-256 为 `775eb508815110ad4fb648c00688aed3b646ee47cd9b14a4fabd90d982600549`。原始照片仅供防泄漏筛查，生产方法不接收 RGB。代码、论文和原数据署名沿用仓库的 Oxford 和 UPF 记录。[Oxford 数据来源](https://www.robots.ox.ac.uk/~vgg/data/pets/) · [UPF 作者资料](https://sites.google.com/site/costaspanagiotakis/research/unconstrained-polygonal-fitting)
