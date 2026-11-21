
# 本轮勘误与计时字典

取数版本为 POLY04 审核提交 `9c8ce11143dfb30e310965136616fe0addb5c1ef`，科学协议固定于 `ff70458c06a8fd36e68f546a9b350510968dcddf`。新正文、图注和回放采用下列口径。旧文保留在原提交。

| 核对项 | 本轮采用的口径 | 原始依据 |
|---|---|---|
| Oxford 输入 | 200 张中，空前景 1、单环 49、多环 150。Egyptian_Mau_20 的前景为空，属于 simple 层。simple 层有 50 张。此前 data-report.md 的“50 张单环”应读作“50 张 simple 层输入”。 | [冻结清单](../../records/poly04/samples.csv) |
| 共同成功 | 在主预算、主时点和同次同字节条件下，至少一次共同成功的 Oxford 源有 195 个，按上述顺序为 1、48、146。200 个输入均进入覆盖分母。空图可以交付 10 字节 PM31。 | [逐源配对的 rings、common 字段](../../results/poly04/confirm/analysis/source_pairs.csv) |
| 对照名称 | 增强圈内基线（within_full）从现有删除、插入规则允许的同圈组合中按同一预评分取前 24 对。每条边的插点有限，限时搜索最多八轮。旧 within_old 先截全局短表再筛同圈。 | [开发对照](../poly04/development.md) |
| 相对改善 | 0.29188289784830224% 是 Oxford 多环共同源的平均相对少错。每一对先算相对差，在源内平均重复和会话，最后源等权。平均绝对差与平均基线错分的商是另一个统计量。 | [事实表](facts.csv) 中 O.256.100.within_full.relative_xor_saved_pct |
| 及时交付 | Oxford 全输入，跨圈 1165/1200，增强圈内基线 1166/1200。多环分别 871/900、872/900。LEMS 全输入两法均 528/600，多环均 42/60。分数的分子分母按调用计。主效应中 Oxford 有 871 对、146 源，LEMS 有 42 对、7 源。 | [逐次观察](../../results/poly04/confirm/per_run.csv) |
| 三个比较 | Oxford 256 B、100 ms，下列都是各自共同成功的配对结果。完整方法对原版 CGAL 少错 105.76 像素（全环数，190 源），对 CGAL 加同一圈内后处理少错 14.70（全环数，191 源），同一起点的跨圈对增强圈内基线少错 2.26（多环，146 源）。人群与起点各异，分开解释。 | [逐项区间、分母与比较名称](../../results/poly04/confirm/analysis/paired_summary.csv) |

## 从数组到文件的时钟

计时从已在内存中的 0/1 二值数组开始。输入结构提取、初始化、候选生成和排序、回填、结构验收、序列化和同步交付都在计时范围内。实验为每次调用保留多个合法检查点。100 ms 的观察选择接收器在该时点及以前实际收到的最后一份字节。

| 发生的事 | 正式结果字段 | 如何使用 |
|---|---|---|
| PM31 序列化完成 | checkpoints.serialized_ms | 此刻已有字节，随后才进入回调 |
| 引擎即将调用接收器 | checkpoints.dispatch_ms | 引擎事件原名 delivered_ms，汇总时改列名以区分实收 |
| 调用方实际收到 | checkpoints.received_ns 与 runs.clock_start_ns 之差。毫秒列 checkpoints.delivered_ms | 接收器首条取时决定是否赶上观察点 |
| 内部搜索结束 | runs.search_end_ms | 来自引擎返回字典中的 end_ms，在组装归档材料之前取时 |
| 完整 encode 函数返回到调用方 | runs.end_ms，亦见 per_run.end_ms | 按 caller_return_ns 减 clock_start_ns 计算。引擎自己在 return 前的 return_ms 又是一个内部时间戳 |
| 写盘或界面展示 | runs.blob_io_and_hash_ms 单列了试验保存及哈希。无当时的界面呈现时间 | 原单图命令先等 encode 返回，再选取截止前检查点并写盘。本轮网页离线读取保存结果。 |

原审核说明的约 **209.96 / 230.99 ms** 取自 runs.csv。筛选 Oxford、cross、256 B 的全部 **1200 次调用**，含失败，对 search_end_ms 取中位数及线性第 95 百分位，得到 **209.96485 / 230.99264 ms**。旧 tables.md 的 **210.24 / 231.29 ms** 取自 coverage.csv 的 end_ms_median / end_ms_p95。该行筛选 Oxford、cross、256 B、100 ms、scope=all，对应 per_run.csv 的全部 **1200 个截止观察**，对完整返回 end_ms 取同样分位，得到 **210.24165 / 231.291785 ms**。200 ms 表使用同一批调用的另一行截止观察。两档分别汇总，未重复加权。源读取与解码、冷启动、落盘及回放页刷新各有独立时间边界。[原调用](../../results/poly04/confirm/runs.csv) · [正式覆盖表](../../results/poly04/confirm/analysis/coverage.csv)

keeshond_55、S1、重复 2 的增强圈内基线第 3 轮在 **99.9987 ms** 完成序列化，实收却为 **100.0016 ms**，因此计入 100 ms 的是第 2 轮。三个会话的 Oxford 多环平均差均为正，第三会话自己的 95% 区间包含零。总体区间、会话区间和删除任一源后的均值范围在事实表中分别列项。[检查点](../../results/poly04/confirm/checkpoints.csv) · [会话统计](../../results/poly04/confirm/analysis/stability.csv)
