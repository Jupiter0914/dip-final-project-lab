# 第一轮候选与事前淘汰规则

## A　单对象外轮廓的定长多边形编码

标注编辑器可以用少量可拖动的拐点保存一块已有前景。输入是完整单目标二值外形，输出是固定数量的整数顶点。按偏离直线的距离选点，常把一长段弧整体切掉，或用一条线跨过凹口。拟从几何简化结果出发，移动整数顶点，在真正的回填图上数错分像素。每次接受误差降低的移动，顶点预算不变。对应边界表示、二值形态学、有损编码的率失真。传统基线用定点数 Douglas–Peucker，强基线用限定候选位置的最小平方轮廓误差动态规划，并补用相同搜索次数的几何细调。记录 IoU、异或面积、边界 F、字节数和编码时间。在 Oxford-IIIT Pet 的实际标注上用 16、32 点先做开发试验，预计 60–120 分钟。若以强几何基线为参照没有可见的面积损失改善，或只有逐图挑参才能改善，淘汰。已有资料包括顶点重定位以及栅格一致性矢量化，拟验证的区别是固定整数输出与具体离散回填器的结合。[顶点重定位](https://doi.org/10.1016/j.imavis.2014.10.012) · [CVPR 2020](https://openaccess.thecvf.com/content_CVPR_2020/html/Li_Approximating_shapes_in_images_with_low-complexity_polygons_CVPR_2020_paper.html) · [数据](https://www.robots.ox.ac.uk/~vgg/data/pets/)

## B　缩小单色轮廓预览时保持覆盖面积

把原蒙版缩为每格一位的预览。有少量前景的边格经过平均再阈值化时可能消失。拟按每格前景比例排序，取最接近原前景面积的格数。对应空间平均、采样、二值阈值。以原蒙版、最近邻和开发集选定的固定阈值为对照，去掉排序校正即固定阈值。公开真实前景沿用 Pet 开发照片，考察 4 倍和 8 倍缩小再原尺寸回显的 IoU 及面积偏差。预计 15–30 分钟。若面积守恒未带来轮廓 IoU 的实际改善，或核心思想已有成熟实现，淘汰。已有纹理工具以 alpha test coverage 为目标校正各级阈值，需正面比较。[作者说明](https://www.ludicon.com/castano/blog/2026/02/runtime-mipmap-generation/) · [数据](https://www.robots.ox.ac.uk/~vgg/data/pets/)

## C　裁切视野下的平移配准

从同一公开源图裁出部分重叠的两个视野，输出横纵位移。小重叠或重复纹理可能产生异常高的归一化相关峰。尝试用有效重叠量给相关峰扣除不确定度，比较开发集调好的最小重叠阈值、普通相位相关与加权分数。对应傅里叶互相关与几何配准。BSDS500 官方 train/val/test 提供源图，生成有已知位移的裁切，按源图计算像素误差、成功率和时间。预计 1–2 小时。若真实常见重叠范围内原基线几乎总是正确，或无法校正像素空间相关造成的有效样本数偏差，淘汰。图像和代码本轮初筛时未下载。[Padfield](https://doi.org/10.1109/TIP.2011.2181402) · [现有实现](https://scikit-image.org/docs/stable/api/skimage.registration.html) · [BSDS500](https://www2.eecs.berkeley.edu/Research/Projects/CS/vision/grouping/resources.html)

## D　按笔画宽度选择历史文档局部二值化窗口

输入灰度扫描页，输出文字二值图。单一窗口遇到细笔画与宽阴影共存时会断字或保留底纹。拟由粗分割的笔画宽度估计一个窗口，比较开发集最佳固定 Sauvola、多窗口方法和去估计对照。对应灰度统计、空间滤波、阈值分割与形态学距离。DIBCO 有扫描页和二值真值，按文档计算 F 值、伪 F 与 DRD。预计 1–2 小时。若方法仅重述已有多窗口选择、缺少可分离的文档来源或效果依赖挑页，淘汰。初筛核查了作者说明，未取得扫描页或权重。[Sauvola 与 Pietikäinen](https://doi.org/10.1016/S0031-3203(99)00055-2) · [SauvolaNet 作者代码与数据源](https://github.com/Leedeng/SauvolaNet) · [DIBCO](https://vc.ee.duth.gr/dibco2017/)

优先运行 A 与 B。C、D 为备选，两者均需额外分离数据依赖或与成熟方法的差异。各候选的实际结果追加在 decisions.md。
