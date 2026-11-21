# 怎样核对 POLY04 的增量、覆盖与结构代价

分析入口以源清单和配置重建所有应有的来源、照片/文件族、会话、重复、预算、时点与方法组合。缺少预定观察、相同源预算的实际字节不一致、已收到的检查点消失、应为晚到的文件被记成成功，都会使分析停止。失败的误差列为空。正式设置中每个源必须参与 256 字节 / 100 ms 的全部预定会话和重复。

**唯一主表行**是 Oxford、预算 256、时点 100、scope=R2+、method=cross、baseline=within_full、metric=xor_saved。正值为每个共同成功源平均少错的像素。coverage 使用所有预定 Oxford 源，含 R=1 和不可交付者。每一方法在自己成功集上的平均质量可能受选择影响；公平的绝对均值在 paired_coverage.csv 的 common_method_xor、common_baseline_xor、common_method_iou、common_baseline_iou 列。relative_xor_saved_pct 在源内平均相对变化。pooled_relative_xor_saved_pct 先汇总共同源的平均错分数，再求总比例，两者权重不同。

| 文件（各阶段结果的 analysis 子目录） | 阅读方式 |
|---|---|
| decision.json | Oxford 主判定与来源分开报告的稳定性。开发输出标为开发依据。若外域仅源级稳健而按整类重抽或留一类不稳，则标记类别敏感。|
| coverage.csv、paired_coverage.csv | 所有预定源的交付率、各自独有成功、共同成功、均未成功、源层覆盖差区间、成功输出的完整/实际接收耗时。obs_ 前缀是截止状态，end_ 前缀是搜索最终状态。|
| paired_summary.csv、source_pairs.csv | 每种条件/输入范围的绝对及相对误差差、IoU/BF 百分点差、胜平负及最差源；逐源表中的 common 是共同成功的实际重复数。|
| stability.csv、session_coverage.csv、leave_one_source.csv | 每个独立会话的源加权效应与覆盖、全重复都成功的敏感性、依次删除一个源后的主效应。|
| category_sensitivity.csv、cluster.csv、r1_negative_control.csv | 各类别与去掉该类别的均值、按整个类别重抽的区间、单圈负对照在相同已交付轮数时的字节差异数量。|
| regions.csv（阶段结果根目录） | 每个实际被评分的唯一编码文件、每个对应前景部件和有限孔的原面积、解码面积、交集、参考覆盖率/解码精确率/面积比/局部 IoU。外部背景不作为一个孔。|
| regions_summary.csv、regions_by_source.csv | 先在每份输出内找最差区域，再在源内平均重复与会话。全体观察到的最差值和相应参考身份另有独立列。|
| regions_paired.csv、regions_cases.csv、cases.csv | 同一源的同一参考身份在匹配重复中的面积及覆盖变化；代表性改善、最接近零、最差来源，以及全图少错却有具体小区域退化的实际结果和文件指纹。|

观察态为 success 时，必须有真实的 PM31 字节，实际接收时刻处于截止值之内。若截止前只完成序列化而调用方尚未收到，该文件不计为当时的成果。两方法都没有及时交付的源保留在覆盖分母；只有相同会话、重复中双方及时交付的源进入质量配对。另列全重复共同成功子集以显示缺失敏感性。抽样方法、阈值及成功原则见 [分析预登记](../../records/poly04/analysis-protocol.md)。

使用相应 stage 和运行设置进行复算。--output 可选择新的分析输出目录。--verify-only 会在临时目录中重算并核对发布的 CSV 与决定，不改动实验目录。对同一构建环境保留完整浮点精度；审核的浮点尾差容限为 1e-10 绝对或 1e-12 相对，源身份、文件哈希和离散决定按原值核对。

```powershell
python -X utf8 -m poly04.analysis results/poly04/dev --stage dev --settings configs/poly04/dev.json --verify-only
python -X utf8 -m poly04.analysis results/poly04/confirm --stage confirm --settings configs/poly04/confirm.json --verify-only
```
