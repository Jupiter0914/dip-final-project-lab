# 环境与工具辅助

Windows 11 build 26100，Intel Core Ultra 9 275HX，24 个逻辑 CPU，物理内存 16,489,648,128 字节，首次 psutil 观测可用 3,176,960,000 字节。nvidia-smi 报 RTX 5060 Laptop，显存 8151 MiB，开始时可用 6280 MiB、利用率 5%。MATLAB 程序可定位；本项目全部数值实验用 CPU，OpenCV 配为一个线程。NumPy 2.4.4、OpenCV Python 5.0.0.93、Pillow 12.2.0、psutil 7.2.2、Matplotlib 3.11.0。原运行解释器 E:/Miniconda/envs/pytorch_cv/python.exe，Python 3.12.13。实验使用 perf_counter_ns 墙钟，peak_working_set_bytes 是 Windows 进程运行期峰值，包含评价及全点 DP 对照。图像解码与写盘不计入编码时间，提取公共外形、编码及实际字节序列化计入。解码时间含合法性检查与回填。

由 Codex 在用户授权下查阅课程 PDF 与其目录、查询论文及数据、编写和执行 Python、比较开发结果、提交冻结、控制实验和制作审核材料。GitHub 由用户已有 gh 登录状态操作。没有模型训练、付费调用、人工拍摄、人工标注或人工用户研究。最终课程报告仍需用户审核。