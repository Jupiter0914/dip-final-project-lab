
# 限时交付下保持部件与孔对应的二值蒙版多边形编码

把已有的**完整二值蒙版**存成一份小文件时，几个前景部件和孔要共享顶点。本项目输出可独立解码的 PM31，实际记录宽高、环层级及所有坐标。在保证原部件与孔位置对应的条件下，比较只在圈内重新放点与允许把点转给另一圈两种做法。

**当前结论**　在 256 字节上限、调用方 100 ms 内实收条件下，结构均衡 Oxford 的 146 个共同及时成功多环源上，允许跨圈相对**增强圈内基线（within_full）**平均少错 **2.26 像素**，95% 源级区间 **[0.64, 4.01]**，中位数为零。Oxford 全部 200 张含 1 张空前景、49 张单环、150 张多环。跨圈与增强圈内在全部调用上分别及时交付 1165/1200、1166/1200，在多环上分别为 871/900、872/900。LEMS 的 7 个共同多环源平均少错 0.43 像素，区间 [0.00, 1.29]，尚未建立稳定外域增量。LEMS 全部输入两法均及时交付 528/600 次，多环均为 42/60 次。一个孔能保持对应，面积仍可能从 271 像素缩到 96 像素。

## 从这里开始

- **读报告素材**　[带宋体、Times New Roman 和 STIX 公式的阅读版](report/poly05/manuscript_materials.html) · [中文 Markdown 稿](report/poly05/manuscript_materials.md) · [事实表](report/poly05/facts.csv)
- **看真实结果**　[离线回放](report/poly05/replay/index.html) 可选八个固定案例，切换解码、错分和相同局部放大，下载各次交付的实际 PM31。[六幅核心图及图注](report/poly05/figures.md)
- **读实现与审计**　[核心代码导读](report/poly05/code_guide.md) · [输入构成、分母和时钟勘误](report/poly05/corrections.md) · [素材包与生成入口](report/poly05/README.md) · [POLY04 原始审核包](https://github.com/Jupiter0914/dip-final-project-lab/releases/tag/poly04-confirm-review-v1)

下载 ZIP 后解压，双击 `report/poly05/replay/index.html` 即可使用。GitHub 网页显示 HTML 源码时使用私有 Release 附件。[本轮报告素材包](https://github.com/Jupiter0914/dip-final-project-lab/releases/tag/poly05-report-materials-v1)

## 运行入口

只复核报告统计、固定案例解码与字体，在项目或素材包根目录运行第一条。后两条在配好科学依赖与项目数据的仓库克隆中实际编码、解码一张图。原图也可用 `--file` 传入单通道二值 PNG。

```powershell
python -B -X utf8 scripts/poly05/verify.py
python -B -X utf8 -m poly04.run_one --id Ragdoll_32 --method cross --budget 256 --deadline 100 --output local/poly05-demo.pm3
python -B -X utf8 -m poly03.export decode local/poly05-demo.pm3 local/poly05-demo.png
```

从内存中的二值数组进入编码器开始计时，100 ms 是观察截止。只计接收器届时已经收到的最后一份合格字节。单图命令等待搜索结束，再把选中的检查点写盘。回放页读取原实验保存的文件。源读取和页面显示时间在主计时之外。

## 历史导航

| 研究范围 | 保留的记录与入口 |
|---|---|
| 完整多环独立确认 | [冻结协议](records/poly04/freeze.md) · [原审核说明](report/poly04/review.md) · [原始逐次数据](results/poly04/confirm/per_run.csv) · [复现实验与环境](report/poly04/README.md) |
| 完整蒙版开发探索 | [开发结果与决定](report/poly03/review.md) · [开发复算](report/poly03/README.md) · [PM31 格式](report/poly03/format.md) · [直接先例](records/poly03/related.md) |
| 单一外轮廓、16/32 点、填孔 | [POLY02 的 BF2 保护、作者程序和独立演示](report/poly02/README.md) · [初次选题与确认结果](report/findings.md) · [初次审核包](https://github.com/Jupiter0914/dip-final-project-lab/releases/tag/topic-confirmation-v1) |
| 早期命令和旧项目交接 | [旧 README 及其全部链接](https://github.com/Jupiter0914/dip-final-project-lab/blob/9c8ce11143dfb30e310965136616fe0addb5c1ef/README.md) · [历次进度](records/progress.md) · [去摩尔纹项目归档索引](records/old-project.md) |

科学冻结提交为 `ff70458c06a8fd36e68f546a9b350510968dcddf`，报告取数基准为 `9c8ce11143dfb30e310965136616fe0addb5c1ef`。本分支交付中文报告素材与回放，等待主控审阅。
