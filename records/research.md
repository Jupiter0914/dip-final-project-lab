# 查新与资源核验

查询围绕固定顶点数曲线简化、轮廓邻域重定位、基于区域的多边形、二值蒙版矢量化、像素重建以及近期学习方法。检索在项目执行日期进行。查新支持定位课程扩展，未作全球首创认定。

| 原始资料、核对深度 | 已有方法 | 本轮实际取得与操作 | 与本题关系 |
|---|---|---|---|
| [psimpl 作者文档，Douglas–Peucker N](https://psimpl.sourceforge.net/douglas-peucker.html)，阅读该算法一节 | 固定点数，优先拆分点至线段距离最大的边 | 阅读 API 说明，独立实现闭环版，未编译作者 C++ 库 | RDP 基线以两个远端锚点初始化，使用同一整数顶点预算 |
| [Pérez 与 Vidal 1994，出版者摘要](https://doi.org/10.1016/0167-8655(94)90002-7)；[Kolesnikov 与 Fränti，作者论文 PDF](https://cs.uef.fi/pub/franti/papers/Kolesnikov/Kolesnikov_Paper5.pdf)，核读公式与算法段 | 顺序折线的固定段数最优化，后者还讨论通过限制搜索区域降低计算 | 自行实现固定切点最短路径及本实验指定的垂线平方误差。全点 DP 和限定候选网格两套均运行；穷举小环核对最优值。未使用作者程序 | 全点结果只对已定切点和本误差定义在未触发简单性回退时全局最优；无全局闭环最优声明。8K 网格沿轮廓索引均匀抽样，保留 RDP 建议点 |
| [Parvez 2015，出版者提供的摘要与亮点](https://doi.org/10.1016/j.imavis.2014.10.012) | 允许顶点离开原轮廓，在自适应邻域移动并进一步减少既有近似的误差 | 未取得作者代码，未完整复现其邻域算法。另实现固定步长、优化轮廓距离的可控对照 | 顶点移动、点数不变已有先例。本实验新检查的是实际整数解码器的误填损失在同一起点与搜索程序下值不值得计算 |
| [Li、Lafarge、Marlet，CVPR 2020 论文](https://openaccess.thecvf.com/content_CVPR_2020/papers/Li_Approximating_shapes_in_images_with_low-complexity_polygons_CVPR_2020_paper.pdf)，核读正文方法、能量、比较表 | 凸单元划分后合并与分拆，联合考虑输入数据保真和多边形复杂度；评测包括光栅化输出 IoU | 打开公开全文，未下载其实现或复跑。论文包含概率图和影像等不同输入设置 | 重建一致性和精度/复杂度权衡早有研究。本题固定已有二值外形、整数编码器、严格 K 与字节数，执行局部离散搜索 |
| [Lazarow 等，CVPR 2022 BoundaryFormer](https://openaccess.thecvf.com/content/CVPR2022/papers/Lazarow_Instance_Segmentation_With_Mask-Supervised_Polygonal_Boundary_Transformers_CVPR_2022_paper.pdf)，核读正文 §3.3 | 对预测多边形进行可微光栅化，用掩膜损失训练实例分割网络 | 论文全文可读，未取得权重、未运行检测网络 | 区域反馈已有先例。本题没有图像识别、网络或训练，在导出每张已知蒙版时按精确二值回填计数 |
| [Wang 等，ICCV 2025 HoliTracer](https://openaccess.thecvf.com/content/ICCV2025/papers/Wang_HoliTracer_Holistic_Vectorization_of_Geographic_Objects_from_Large-Size_Remote_Sensing_ICCV_2025_paper.pdf)，核读正文 §3.2–3.3 | 从分割轮廓作 TC89、Douglas–Peucker 和插值，再学习顶点/偏移，用于遥感矢量化 | 打开公开全文，未下载遥感原图或权重，未作横向数值排名 | 应用输入与监督不同。本文目标是无训练、输出字节数固定的单圈编辑格式 |
| [区域驱动的固定顶点多边形，作者 PDF](https://lccv.ece.gatech.edu/docs/tim_Optical_Flow_Active_Polygons.pdf)，核对区域项与固定顶点运动公式 | 固定数量的顶点可由区域能量的梯度流移动，并用于跟踪 | 正文段落可读，本轮未运行光流或跟踪 | 区域信息驱动顶点本身也早已存在。本项目比较离散解码误差与距离误差，不宣称发明这种思想 |
| [Castaño，alpha 覆盖率](https://www.ludicon.com/castano/blog/2026/02/runtime-mipmap-generation/)，阅读覆盖校正段 | 保持 alpha 测试的覆盖面积已用于 mipmap | 实现并测试按格前景比例排序的二值变体，无外部权重 | 面积好转，IoU 未优于固定阈值，候选 B 退出 |

## 已取得的数据

Oxford-IIIT Pet 的 19,173,078 字节标注包从作者主机下载。原始归档 SHA-256、官方 trainval/test 列表哈希见 data.json。MD5 与 torchvision 的官方数据加载器一致。包内 README 明确 1 为前景、2 为背景、3 为未分类。图像编号与品种作为现有分组，可重建分组和每个 PNG 的哈希。仅使用实际标注，不使用网络生成图片，无合成退化。网页目前列出 CC BY-SA 4.0，旧归档 README 另有研究用途说明；本私有课程审核包标明两处说明、作者与来源，仅附本实验所用标注。[Oxford 数据页](https://www.robots.ox.ac.uk/~vgg/data/pets/) · [官方标注包](https://thor.robots.ox.ac.uk/datasets/pets/annotations.tar.gz) · [torchvision 官方代码](https://github.com/pytorch/vision/blob/main/torchvision/datasets/oxford_iiit_pet.py)

本次可验证的差异是整数坐标、同一个非抗锯齿回填器、严格字节预算和逐次计算实际异或损失，在已知单个外形上联合使用。现有文献已分别使用离轮廓重定位、区域能量及光栅监督。待验证事项包括对多洞、多部件、另一种光栅化规则和其他物体的泛化，以及人工编辑是否省时。