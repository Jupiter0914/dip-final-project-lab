# 直接相关工作与本轮复现

Panagiotakis 已经把固定点数、允许顶点离开轮廓、直接以区域重合度拟合已知二值形状写成同一问题。v1 的查新遗漏了这项直接先例。对照现在拆成同搜索换目标、逐点删除、作者的粒子群程序和同几何起点有无边界保护四项。课程扩展的证据来自这些实测比较。[Algorithms 17(1), 25](https://www.mdpi.com/1999-4893/17/1/25)

| 研究或方法 | 输入 | 顶点数 / 能否离开原轮廓 | 目标与搜索 | 训练 | 取得的实现与实际范围 |
|---|---|---|---|---|---|
| Panagiotakis 2024，UPF-PSO | 已知二值形状 | 固定 N / 可离开 | 区域 IoU，20 粒子的连续 2N 维搜索，按质心极角排序；另有等面积变体 | 无 | 读全文 §3–4、核对图表；从公开查看器定位 File Exchange 1.0.0 原始 ZIP，15 个成员。原封 MATLAB 函数在本机运行，EA 关闭。作者鱼形例 N=4；3 张固定 Oxford 开发图每张 K=8/16/32、3 个种子。所有浮点解及转换后文件保留。[项目页](https://sites.google.com/site/costaspanagiotakis/research/unconstrained-polygonal-fitting) · [作者程序](https://www.mathworks.com/matlabcentral/fileexchange/156966-unconstrained-polygonal-fitting) |
| 同论文 SM | 同一二值形状 | 固定终点数 / 保留初始轮廓的点 | 先密集 RDP，再反复枚举删除一个顶点，最大化区域 IoU | 无 | 作者 ZIP 未提供 SM 入口；按 §4 独立实现。50 点初始化、合法性及并列规则见冻结，所有确定性主实验同机运行。[论文 §4](https://www.mdpi.com/1999-4893/17/1/25) |
| 本轮 local_iou | 同一二值形状 | 固定 K / 可离开 | 准确整数解码 IoU，固定八方向局部搜索 | 无 | 和 v1 同一几何起点、试探顺序与合法性；用于识别区域目标带来的收益。与 SM 的候选空间不同 |
| Parvez 2015 | 数字平面曲线 | 保持既有近似点数 / 可在轮廓邻域移动 | 适应性邻域重定位、几何近似误差 | 无 | 出版者摘要与亮点，未取得作者程序。本库 geometry 是固定弧段、固定步长的可控基线。[论文](https://doi.org/10.1016/j.imavis.2014.10.012) |
| Li 等，CVPR 2020 | 输入图像、类概率等 | 复杂度进入能量 / 顶点由单元几何确定 | 区域保真与复杂度，分裂和合并多边形单元 | 优化阶段无需训练，上游可用学习预测 | 已核读方法与比较表；未取得并运行该框架。[论文](https://openaccess.thecvf.com/content_CVPR_2020/papers/Li_Approximating_shapes_in_images_with_low-complexity_polygons_CVPR_2020_paper.pdf) |
| BoundaryFormer，CVPR 2022 | 图像特征与实例掩模监督 | 预测的多边形顶点序列 / 可离开标签边界 | 可微光栅化后的区域损失，迭代预测顶点 | 有 | 核读 §3.3；未取得权重、未运行。[论文](https://openaccess.thecvf.com/content/CVPR2022/papers/Lazarow_Instance_Segmentation_With_Mask-Supervised_Polygonal_Boundary_Transformers_CVPR_2022_paper.pdf) |
| v1 及本轮后处理 | 已知单个整数外圈 | 固定 K / 可离开 | 几何平方垂距或实际回填 XOR；本轮在几何解上继续搜索，可加逐源 BF2 下限 | 无 | 本地完整确定性实测，原始基线和原发布记录单独保留。[v1 查新](../research.md) |

论文实验覆盖 K=3–10、每个随机方法执行 10 次。论文写 100 代上限，发布函数实际 MaxIt=200，迭代超过 50 后可因连续 50 代最佳值不变提前停止。论文介绍等面积初始化；源码在 useEA=0 时跳过 getRandomSolCoords 的面积缩放。getDICE_IOU 的交集使用 poly2mask 计数，但并集分母中的多边形面积取 polyarea 连续面积。保留作者原生 IoU/Dice 供追溯，主比较用同一原尺寸整数 POL1 解码重算。转换将 MATLAB 一基坐标减一，取最近整数并裁到画布；逐例记录裁边点数、无效环及全部浮点坐标。论文机器和计时口径只作背景。固定系数、种子及完整端到端和求解器时间均可从脚本核对。

数据包是作者发布的 Datasets_LEMS_MPEG7.rar。MPEG 文件夹含 70×20 个编号形状与两个工具用 GIF，LEMS 文件夹含 1,462 个 GIF。新外域只抽 MPEG，每类一张。初次误判 ZIP 签名和未命中的下载地址保留在 acquisition.json，成功来源和逐成员哈希在 resources.json。普通 Git 保留来源和哈希；原版程序在本地 data/poly02/upf，可从原始 ZIP 恢复。作者程序附 BSD 三条款许可及署名。作者提供的研究数据及 Oxford 标注分别标注出处。[作者数据入口](https://sites.google.com/site/costaspanagiotakis/research/unconstrained-polygonal-fitting) · [Oxford](https://www.robots.ox.ac.uk/~vgg/data/pets/)

固定顶点表示、移动顶点和区域反馈已有直接先例，整数坐标与 POL1 是实验约束及演示载体。本轮检验的具体改动是以已有几何解为起点，在严格减少错分时逐步守住初始 BF2，并量化其代价。