
# 报告素材与复核入口

推荐先读[排版阅读版](manuscript_materials.html)，在讨论顶点分配时打开[本地回放](replay/index.html)并选择 Ragdoll_32。展开“查看这个源的真实跨圈动作”可以看到同一条轨迹的两次交付，原文件可直接下载。写作使用[中文 Markdown 材料](manuscript_materials.md)，取数使用[事实表](facts.csv)，插图从[图注与原文件](figures.md)选择 PNG 或 SVG。阅读版的表格采用三线表，正文公式已排成 STIX 矢量字形。PNG 与 SVG 中的英文和数字用 Times New Roman，中文用宋体。网页正文和表格调用读者系统上的相应字体。

| 要核对的内容 | 入口 |
|---|---|
| 输入构成、同次配对与返回时间 | [数字勘误及字段对照](corrections.md) |
| 每个结论的分母、原精度、置信区间、来源与筛选规则 | [facts.csv](facts.csv)。value 保留源表精度，ci95_low / ci95_high 空白表示该条未给区间。调用或配对计数的含义见 aggregation |
| 研究函数与阅读顺序 | [代码导读](code_guide.md) |
| 案例原始标注、实际字节、裁片和时间 | [回放清单](replay/index.json)及其中的 evidence 路径。不同方法交付相同字节时可指向同一个文件 |
| 原有科学协议与完整审计 | [确认冻结](../../records/poly04/freeze.md) · [固定 POLY04 审核包](https://github.com/Jupiter0914/dip-final-project-lab/releases/tag/poly04-confirm-review-v1) |

## 不联网使用

解压整个 `poly05-report-materials.zip`，保留目录层级。双击阅读版或回放即可，无须服务、模型及在线字体。为材料复算安装依赖时，原机版本为 Python 3.12.13、NumPy 2.4.4、OpenCV 5.0.0.93、Pillow 12.2.0、Matplotlib 3.11.0、Markdown 3.10.2。包内提供生成所需的原表与八个案例的输入和真实编码，运行以下命令不会启动编码器计时。

```powershell
python -B -X utf8 scripts/poly05/verify.py
python -B -X utf8 scripts/poly05/build.py
python -B -X utf8 scripts/poly05/build.py --figure 2
```

第一条读取现有材料，独立从原始逐次表复算配对与区间，并从文件检查像素、时间、区域和文中数字。包内还会逐项比对 `POLY05-SHA256.csv`。第二条从已有证据重建素材。重复生成时，排版库及系统字体版本可能影响图像字节，请把用于重建的解压副本与原包分开。第三条只重画一个指定图号。字体从 Windows Fonts 自动发现，其他机器可设置 `POLY05_TIMES` 和 `POLY05_SIMSUN` 指向有权限使用的 Times New Roman 和宋体文件。

浏览器交互核对使用真实 Chromium 的断网 file 模式。在可加载 Node Playwright 的环境中运行 `node scripts/poly05/browser_check.cjs`。可用 `POLY05_CHROMIUM` 指定本地浏览器。正文课程表已核对本机《Chapter 8 Image Compression》《Chapter 9 Morphological Image Processing》与课程教材电子版文件夹中的《1 Digital Image Processing Using Matlab（英文）》。审核包提供页码、实际页脚及本项目推导。

数据署名见 [Oxford-IIIT Pet](../../records/attribution.md) 和 [LEMS 作者分发记录](../../records/poly02/research.md)。包中八份原标注均按历史 SHA-256 保存，示意彩图是对这些输入和 PM31 结果的派生展示。

## 审核版本

[本轮核对回执](verification.json)记载逐次配对重算、实际像素回放、浏览器选用的字体和冻结锁比对。

取数基准为 `9c8ce11143dfb30e310965136616fe0addb5c1ef`，科学冻结为 `ff70458c06a8fd36e68f546a9b350510968dcddf`。当前材料位于独立分支 `codex/poly05-closeout`。包根的 `POLY05-INFO.json` 对应本轮固定提交。本轮仅复算既有表与解码实例，沿用 POLY04 干净解压后完成的 12168 次调用日志审计回执。历史阶段的完整目录和科学环境见原审核包。[本轮固定 Release](https://github.com/Jupiter0914/dip-final-project-lab/releases/tag/poly05-report-materials-v1) · [原始完整审核提交](https://github.com/Jupiter0914/dip-final-project-lab/commit/9c8ce11143dfb30e310965136616fe0addb5c1ef)

**POLY05_REPORT_MATERIALS_READY_PENDING_MAIN_REVIEW**
