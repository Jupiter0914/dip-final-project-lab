# 同时简化多环的 CGAL 对照

所有闭合环插入同一张约束 Delaunay 三角网，再在全部可删顶点中按代价选择最小者。每一步尝试用一条弦替代两条相邻边。三角网用于检查新边能否保持曲线间的拓扑关系，因此靠近其他部件或孔的顶点可受到邻近环约束。项目调用的是 CGAL 官方模板，C++ 包装器只负责构网、指定停止和代价函数，以及按原环身份提取结果。固定整数坐标、指定总点数、共同编码文件都属于比较条件。

## 查新与可替代性

| 已有内容与阅读范围 | 当前问题与差异 | 可检验的替代解释 |
|---|---|---|
| Dyken、Dæhlen、Sevaldrud 在平面线网中联合删点，检验替换弦与顶点周围三角形邻域的几何关系，并比较绝对、相对邻距与混合误差。核对期刊摘要，阅读作者学位论文所收同名方法稿第 III 篇，重点核对拓扑条件、删点测试、代价定义及地形/线网实验。 | 论文保持已有交点、避免引入新交点，并防止曲线退化。实验中的首要对象是连续平面线网。完整蒙版还要求在离散像素上逐部件、逐孔保持对应。 | 共同回填与结构检验之后，如果几何联合简化已经达到相近质量与可行率，则额外的整数点交换缺少独立收益。[期刊论文](https://link.springer.com/article/10.1007/s10109-009-0078-8) · [作者方法稿，第 III 篇](https://dyken.no/pdf/phd_thesis.pdf) |
| CGAL 的 2D Polyline Simplification 用户手册列出共享三角网、曲线嵌套、代价策略和停止条件。阅读当前手册与例程，并检查实际编译的 5.4 源码。手册说明官方实现简化了局部拓扑判定。 | 本轮使用该实现的两个现成代价，各自同时处理全部环。以共同解码器判定二值错分与数字连通对应。 | `squared` 衡量原弧段各点（包括当前候选点）到拟替换弦的最大平方距离。`scaled` 在本机锁定的 5.4 实现中，以待删点 q 到三角网相邻顶点的最小平方距离作分母，排除两个弧段邻点与无穷顶点；无合格邻点时不返回该候选代价。代码中的这项距离与在线手册公式的写法有差别，近接曲线会影响删点顺序。两种优先级均属于已有方法。[官方手册](https://doc.cgal.org/latest/Polyline_simplification_2/index.html) · [方法论文索引](https://doc.cgal.org/latest/Polyline_simplification_2/citelist.html) |
| de Berg、van Kreveld、Schirra 的 bandwidth 简化同时考虑近似误差、给定附加点留在原侧以及无自交。核读作者机构存档的摘要。 | 点对折线的相对位置早已用作几何约束。本轮保存输入掩模的部件和孔的位置对应，接受与否由实际离散输出来确定。 | 向量边的距离、嵌套及有限的栅格误差应分别计量，单凭名称“拓扑保持”无法推断末梢像素保真。[作者机构的研究记录](https://research.tue.nl/en/publications/topologically-correct-subdivision-simplification-using-the-bandwi/) |

## 实际版本与复现

在 Windows 11 上从 PowerShell 执行以下命令，工作目录为仓库根目录。Python 使用项目既有 NumPy、OpenCV；本机解释器为 `E:/Miniconda/envs/pytorch_cv/python.exe`。编译与原生进程运行在同机 WSL2 的 Ubuntu-22.04 x86-64 实例中。本轮读取了现有编译工具及库，CGAL 包单独解包于 WSL 临时目录，未进行系统级安装。

```powershell
wsl -l -v
wsl -d Ubuntu-22.04 --exec dpkg-query -W g++ dpkg libboost-dev libgmp-dev libmpfr-dev
python -X utf8 -m poly03.cgal_build
python -X utf8 -m poly03.cgal_check
```

若发行版使用另一个名称，可在当前 PowerShell 会话设置 `$env:POLY03_CGAL_WSL='实际名称'`。默认要求 WSL 将当前 Windows 盘挂载于 `/mnt/<盘符>`。新机器须具备上述编译依赖，x86-64 原生 Ubuntu 也可从项目目录直接运行同两个 Python 模块。实际同机验证的是 Windows/WSL2 组合。若新建专用 Ubuntu 22.04 构建实例，可在该实例内用以下命令准备开发依赖。

```bash
sudo apt-get update
sudo apt-get install --no-install-recommends g++ dpkg libboost-dev libgmp-dev libmpfr-dev
```

- CGAL 发行包为 Ubuntu Jammy 的 `libcgal-dev_5.4-1_amd64.deb`，大小 4,783,820 字节。SHA-256 为 `bd5df93cf2bee4be40899890f70fd37c2e04cdc0541aaa4952bd1d6258db5726`。该值与 WSL 的 Ubuntu 软件包索引相符。下载器检查完整字节哈希；本机从清华 Ubuntu 镜像取得，另外多条公开 Ubuntu 镜像返回同一哈希。[Ubuntu 包页](https://packages.ubuntu.com/jammy/libcgal-dev) · [本次成功的公开镜像](https://mirrors.tuna.tsinghua.edu.cn/ubuntu/pool/universe/c/cgal/libcgal-dev_5.4-1_amd64.deb) · [Ubuntu 原始归档地址](https://archive.ubuntu.com/ubuntu/pool/universe/c/cgal/libcgal-dev_5.4-1_amd64.deb)
- 下载缓存为 `data/poly03/cgal/libcgal-dev_5.4-1_amd64.deb`。缓存已备好时可执行 `python -X utf8 -m poly03.cgal_build --offline`。头文件解包于 WSL 的 `/tmp/dip-poly03-cgal-5.4-bd5df93c/usr/include`。编译器为 g++ 11.4.0，Boost 1.74.0、GMP 6.2.1、MPFR 4.1.0。完整 apt 版本、编译参数、源文件及本机二进制哈希见构建记录。[实测构建记录](../../records/poly03/cgal_build.json)
- 编译产物为 `local/poly03/cgal/cgal_worker`。再次构建写出本地的 `local/poly03/cgal/build.json`。普通 Git 保存 C++ 源码、构建器、Python 接口与夹具，原始包和 ELF 可按上述命令重建。运行服务通过标准输入与输出传递整数数组，随调用它的 Python 进程退出。WSL 的启动信息写入 `local/poly03/cgal/worker.log`。[官方函数调用](../../poly03/cgal_worker.cpp) · [Windows / Linux 构建器](../../poly03/cgal_build.py) · [Python 接口](../../poly03/cgal_bridge.py)

## 调用与停止判据

```python
from poly03.cgal_bridge import simplify

out_rings, info = simplify(rings, target_vertices, cost="squared")
# cost="scaled" 使用同一份 CGAL 的邻距归一化策略。
```

输入为按环排列的整数 XY 数组。每圈省略末尾重复的起点，要求简单、各环在矢量空间无交叉或公共顶点。适配器直接在传入的整数晶格上调用官方实现，输出新环按输入顺序返回，坐标取自相应输入点列。保留每个约束的 ID，回传时只去掉 CGAL 自身的重复闭合点。两种代价均使用 `Stop_below_count_threshold(target_vertices)`。原始点集已满足上限时直接返回构网得到的原约束。输入满足上述前提时，三角网的不同顶点计数等于所有环顶点之和。

`info` 给出实际输入与输出点数、目标数、状态、含启动/进程往返的 `elapsed_ms`、单列的 `startup_ms`、原生建网耗时 `triangulation_ms` 以及包含建网及简化的 `native_ms`。`ok` 表示顶点上限通过。上层实验还须序列化、解码并核对完整掩模结构，记录端到端时间。几何简化可能因进一步删点将破坏拓扑而停在预算之上，`stopped_above_target` 记录了该结果。若目标少于每圈三点之和，适配器直接报 `below_ring_count_bound`。本对照单独不能给出所有共同编码格式的数学可行性结论。

## 夹具结果

四环夹具包括外环、孔、孔中岛和独立小部件；另一夹具是在凹口旁放置另一条边界。两种成本各验证原始、部分缩减及极低预算，16 次原生调用中包含 4 次原样预算。独立检验了同环简单性、跨环线段交叉、全部环对的包含矩阵、整数坐标及原圈归属。原样预算回传字节坐标逐项相等。

四环初始 32 点，目标 16 点时两种成本都达到 16 点。目标 12 点时两者停在 14 点，低于 12 点的目标直接触发四圈下界。近接凹口两环初始 16 点，两种成本均可到 6 点。首次原生调用总计约 2.033 秒，其中 WSL 和服务启动占 2.031 秒；其余允许预算的两组小夹具热调用约 0.16–0.31 ms。此处计时只说明适配器工作方式，完整蒙版的计时须使用真实输入。重新运行夹具默认保存到 `local/poly03/cgal/fixture-replay.json`。[首次实际夹具记录](../../results/poly03/cgal_fixtures/checks.json) · [夹具和校验实现](../../poly03/cgal_check.py)

独立重建也已实测。临时项目从六个源文件开始，重新下载软件包并编译，生成的 ELF SHA-256 与原构建逐字节一致，全部 20 条夹具预算记录再次通过。[干净重建证据](../../results/poly03/cgal_fixtures/clean-rebuild.json)

## 多环等代价与跨进程复算

CGAL 5.4 按内部列表指针排列 Constraint_id。简化器按这个顺序将各环顶点送入堆，原版比较器只比较几何代价。不同进程或同一进程不同的内存分配历史，会改变相等代价候选的先后，并可能改变真实输出。即使将随机种子固定为 7，这个现象仍然存在。对照原表与复跑表，平方代价 41/95、邻距代价 44/95 对已有文件字节不同，一项数字结构状态也发生变化。[5.4 scaled 代码](https://github.com/CGAL/cgal/blob/v5.4/Polyline_simplification_2/include/CGAL/Polyline_simplification_2/Scaled_squared_distance_cost.h) · [原版首次不同出堆的相同代价见证](../../results/poly03/cgal_variation/first-divergence.json)

主实验保留了官方原版输出。另一个独立诊断程序仅在数值代价精确相等时用输入整数坐标 (x,y) 作为次级键。在 190 个可运行条件、两个种子各重复三次的 1,140 次适配试验中，逐案轨迹和文件全部一致。相对可加预排删插的质量结论保持原方向。主三档与含两项 1024 字节补充档的计算口径分别给出。[详细方法、配对比较与重建命令](cgal-variation.md)

190 份实际 PM31 文件按逐图表的 blob 字段归档。对原数据已就绪的检出或审核包，以下命令直接从 ZIP 逐个核对文件名、长度、SHA-256、预算、整图 XOR、矢量及数字结构结果。此步使用项目 Python 解码环境。[190 份编码](../../results/poly03/cgal_variation/encoded.zip) · [逐项清单](../../results/poly03/cgal_variation/xy-primary.csv) · [归档校验值](../../results/poly03/cgal_variation/xy-audit.json)

```powershell
python -X utf8 -m poly03.cgal_xy_sensitivity --verify
```
