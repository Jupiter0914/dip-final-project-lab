# 上一个项目的交接

旧库为 [Jupiter0914/dip-screen-restoration-study](https://github.com/Jupiter0914/dip-screen-restoration-study)，归档时 API 返回 private。原两个审核标签保持原值。阶段一的稳定性选模规则未超过按已知域采用匹配配置。阶段二四次与两次平移推理相比，等域平均 PSNR 变化约 −0.0013 dB，耗时从 103.57 ms 增至 205.97 ms。追加推理的开发门槛未通过，正式门控没有启动。

归档位于 `E:/dip-project-archives/screen-restoration-20261120-223945/`，与旧工作树分开，位于同一 E 盘。阶段一提交 673439cdc245433275ae39d7801656d575f70e41，阶段二 cc8ba6ad7f1098facfa2be9a041aafad6e26e500。本地原来只有第一阶段标签。核对第二阶段远程标签后，在制作归档的临时镜像中补齐该标签。旧仓库、分支和远程标签均保持原状。[阶段一 Release](https://github.com/Jupiter0914/dip-screen-restoration-study/releases/tag/stage1-review) · [阶段二 Release](https://github.com/Jupiter0914/dip-screen-restoration-study/releases/tag/stage2-review)

归档内 `all-refs.bundle` 包含两支及标签，经 verify、独立还原和 fsck。三个作者仓库另有 bundle。两个完整 Release ZIP 与 GitHub 的附件 SHA-256 一致。完整预测目录 files/runs/stage2 包含 624 个 512×512×3（含轴序排列）的 FP32 数组，共 1,963,014,144 字节；逐个核对旧阶段清单、归档字节、形状与 dtype。实际输入样本、权重、适配代码、运行日志、候选输入、数据来源和环境一并保留。大体积公共归档前缀采用来源、范围、哈希及已选数据恢复。metadata/source-inventory.csv 记录逐文件处置，RESTORE.md 说明克隆与覆盖路径。SHA256SUMS.csv 的 SHA-256 为 `64984a0afdf412fd3e874d8ef19b5a7ec4a30586e17b7a997c30ce712235a668`。

清理前逐级拒绝重解析点、核对十个绝对路径和每项文件的哈希，检查旧路径进程。实删逻辑字节 8,466,009,785。清理前 E 盘可用 308,813,488,128 字节，清理后 317,288,108,032 字节，实测增加 8,474,619,904 字节（7.89 GiB）。旧根目录保留已跟踪的小型材料、.git、ARCHIVE-INDEX.md、CLEANUP.json。精确清单见 old-cleanup.json。