# 执行与核查说明

本包在 E:/dip-final-project-lab 的主线普通提交上完成。Codex 使用本机 Python、MATLAB、PDF 文本和页面渲染、Git、gh，以及无头浏览器核查公开作者程序和本地演示。采集、实现、试验、统计及制图均为本次工具辅助操作。没有人工标注、用户编辑工时测试、模型训练、付费算力或 Word 终稿。

起始提交 9e9af734e61a4ead37ecda48d25196452d253dc2，v1 冻结 ed8c4ede27f1e4a28b0d4c6d48cf5d569593dac7。POLY02 冻结 12d337b5e8a38e73dc10bf45913e1790eff611d5，先推送并回读该标签，随后依序执行 Oxford 新样本、MPEG 和固定子集附加预算。新旧样本身份和字节排重已核实。外部 70 个形状每类一张，组内没有重复观测。原 Oxford 缺少个体、主人和会话标识，结论按原图统计。

采用 Intel Core Ultra 9 275HX 的 CPU 路径；总内存实测 16,489,648,128 字节，本轮初查可用 3,456,073,728 字节。MATLAB 返回 24.1.0.2537033 (R2024a)。主程序调用作者 getPSO_EA_Coords，未改其内部函数。第一次握手在文件关闭前读取到空版本字段，随后以同次已关闭的 ready.txt 回填版本与函数路径，并将后续包装器改为原子握手。该变更只涉及版本记录。另在隔离工程重跑全部 28 组相同种子，原始浮点顶点和 POL1 完全一致，证据见 pso-reproduction.json。浏览器的公开文件树显示了真实 ZIP 地址，其展示的 15 个成员 SHA-256 均与实际下载 ZIP 内容逐一吻合；最初猜测的下载地址失败，Windows curl 一次 TLS 失败，标准 HTTPS 客户端随后取得相同公开 URL 的原始文件。RAR 分发中 confusions.gif、shapedata.gif 是两个非类别索引文件。所有这些问题均在独立确认前处理。

记录单进程实际工作集峰值、结束 RSS 与操作系统取得方式。全点 DP 的短、中、长轮廓各在新进程中测 K16/32，记录启动基线和峰值。额外测速使用 6 张按开发轮廓长度分散选取的图，各方法/预算先预热 1 次，再独立计时 5 次，实验次序使用稳定哈希打散。除已注明的 MATLAB 消息传输外，常规确定性比较从公共预处理到内存字节完成计编码时间，从已编码字节校验到回填计解码时间；源文件读取、磁盘写入及对预测计分不在编码计时内。开发、主确认、外域及补充曲线的 wall_s、failures、peak_bytes 与 end_rss_bytes 分阶段保存。

数据署名：Oxford-IIIT Pet，Parkhi、Vedaldi、Zisserman、Jawahar；MPEG-7 CE-Shape-1，Latecki、Lakamper、Eckhardt，经 Panagiotakis 论文项目所分发的研究用 GIF；UPF-PSO 源码版权 Costas Panagiotakis 2024、BSD 三条款，原 license.txt 保留在审核包。论文、作者页、文件交换页面及其他文献的阅读/复现范围参见 research.md。本轮不将采样后的 MPEG 外圈与原论文全库指标直接比较。
