
# 从一个像素读到一个配对差值

建议先用回放打开 Ragdoll_32 的“真实跨圈动作”，看清一个点从哪个圈转到了哪个圈。随后按下表阅读固定版本的函数名。在解压素材包中，[固定代码树](https://github.com/Jupiter0914/dip-final-project-lab/tree/9c8ce11143dfb30e310965136616fe0addb5c1ef) 可补查上下文。完整本地克隆可以直接点击下列文件。

| 从哪里读 | 输入与输出 | 核心动作 |
|---|---|---|
| [poly04/prepare.py](../../poly04/prepare.py) 的 prepare_input → [poly03/maskcodec.py](../../poly03/maskcodec.py) 的 extract | 原尺寸二值数组、字节上限 → 有序高精度环、父编号、目标总点数或终态 | 补零、取等值线，逐圈回填检验高精度像素相等，再算预算下界。 |
| [poly03/maskcodec.py](../../poly03/maskcodec.py) 的 pack、unpack、Renderer.ring、Renderer.combined、decode | 圈记录 ↔ PM31 字节 → 原尺寸二值数组 | 查看小端头、父圈、点数与四分之一格坐标。各圈单独画，原中心取样后异或。 |
| [poly03/allocation.py](../../poly03/allocation.py) 的 hierarchy、curves、optimal、candidates → [poly04/prepare.py](../../poly04/prepare.py) 的 allocation_seed | 各圈原弧段、共同点数 → 各点数的候选层级与误差 → 首份合格点集 | RDP 按最大偏离分裂，DP 在这些层级上记下到每种总点数的最低代价和分配，有限池按顺序调用 validate_rings。 |
| [poly04/proposals.py](../../poly04/proposals.py) 的 individual_scores、sorted_pairs、candidates_for_method | 当前各圈、原高精度弧段 → 预排后的至多 24 对删插 | 单删和单插预评分，用有序归并取合法组合前列。方法标记控制能否转圈，三角形只可给本圈对边替点。 |
| [poly03/atomic.py](../../poly03/atomic.py) 的 replace_vertex 与 [poly04/engine.py](../../poly04/engine.py) 的 exchange_step | 供体、原顶点下标、接收边、新坐标 → 最终点数守恒的候选及实际动作日志 | 依据操作前的下标一次构造最终环，先查可加下降，再实际合成整图并要求 XOR 严格下降。 |
| [poly03/maskcodec.py](../../poly03/maskcodec.py) 的 vector_ok、digital、overlap_map、correspondence | 原父圈与候选环、参考与解码标签 → 接受或具体拒绝原因 | 检查几何与嵌套，建立部件和有限孔的双向唯一空间对应，再核对邻接。 |
| [poly04/engine.py](../../poly04/engine.py) 的 encode 内部 deliver → [poly04/study.py](../../poly04/study.py) 的 measure → [poly04/gather.py](../../poly04/gather.py) 的 gather | 内存中的源与回调 → 带时刻的字节轨迹 → 给定时点可选的最后一份文件 | 接受种子或新动作立即 pack 并同步回调，接收器首行读时钟。gather 只选实收到时的检查点。命令行 [run_one.py](../../poly04/run_one.py) 等函数返回后才落盘。 |
| [poly04/analysis.py](../../poly04/analysis.py) 的 pair_data、gain_vector、average_sessions、intervals、method_coverage | 同源同会话同重复的截止记录 → 等权源均值、区间和覆盖 | 同实际码长且双方及时才算质量差，每源先均会话内重复，再均有效会话。全部输入单列交付覆盖。 |

## 沿主路径读一遍

```text
记录起始时刻，检查原尺寸二值数组、高精度回填与 PM31 下界
在逐圈层级上分配总点数，从有限候选池取第一份通过结构验收的解
准备或分配失败时，返回相应终态和原因
把合法起点打包，立即调用接收器交付第 0 轮
至多尝试八轮，在每轮开始前检查搜索时间上限
    按本方法允许的圈内或跨圈关系预排，保留至多 24 对
    一起删插，只保留逐圈总误差严格下降的候选并排序
    找第一个整图 XOR 严格下降、矢量和数字结构同时合格的候选
    找不到就停止，找到就更新当前状态、打包并立即交付
记录内部结束，再返回给调用方
观察端只选指定时刻前已实际收到的最后一份合法字节
```

搜索默认最多工作到每轮开始时检查的 200 ms 上限，独立确认另在同一轨迹读取 100 ms 和 200 ms 两个检查点。统计记录中的 **delivered_ms** 是调用方实收。内核事件的同名字段在汇总时写入 **dispatch_ms**。完整返回和最后一轮交付各自留痕。[时钟及跨截止实例](corrections.md)

## 实际入口

在仓库根目录运行。单图示例的输入是普通单通道二值 PNG（非零为前景）。下列已知源模式自动读取 Oxford 的索引标注。命令会实际编码，受当前机器负载影响，不能替代原确认时钟。

```powershell
python -B -X utf8 -m poly04.run_one --id Ragdoll_32 --budget 256 --deadline 100 --method cross --output local/poly05-example.pm3
python -B -X utf8 -m poly03.export decode local/poly05-example.pm3 local/poly05-example.png
```

审阅保存的结果无需重新搜索。双击 [离线回放](replay/index.html)，或在本地检查材料的统计和字节。完整的确认审计在旧 Release 解压根目录另行运行。

```powershell
python -B -X utf8 scripts/poly05/verify.py
python -B -X utf8 scripts/poly05/build.py
```

第一条只读校验。第二条从既有表和案例文件重建本轮事实表、图、回放。生成依赖及原始审核包见 [回放说明](README.md)。
