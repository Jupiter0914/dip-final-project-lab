# POLY02 交付与复现

从 [主控审核说明](review.md) 开始。结论、完整比较与局限分别链接到逐图证据。主预算每个源图只有一份 16 点及一份 32 点观测，各自保留所有方法的编码。[按 K 展开的指标与胜平负](metrics.md) · [最接近文献与实现核查](../../records/poly02/research.md) · [冻结协议](../../records/poly02/freeze.md) · [样本清单](../../records/poly02/samples.csv)

## 打开演示

可直接双击 results/poly02/demo/demo.html 查看带孔输入的真实示例，切换 K=16/32、六种方法、获准或被拒绝的移动，并下载实际 POL1。实时版支持选择库中 306 个输入，或上传自己的单通道二值 PNG（非零表示前景），选择六种 K。进入仓库或审核包根目录运行下列命令，关闭终端即可停止本机服务。默认端口 8072；显式传 --port 0 可自动选择可用端口。

```powershell
python -X utf8 -m poly02.demo --open
```

两种模式均显示标准化前景、完整轮廓、实际编码点、FP/FN 与完整编码时间。前景范围和移动端点可视化为放大显示；所有误差均在整幅原尺寸图统计。离线 HTML、JSON 和 PNG 是演示材料；74/138 字节是两个预算的 POL1 文件大小。表格的时间来自那次真实调用。实时页会缓存已计算的内置样本与 K；下载文件的字节已与确认实验核对。[离线演示](../../results/poly02/demo/demo.html) · [预览](../../results/poly02/demo/preview.png) · [真实移动记录](../../results/poly02/demo/witness.json)

## 全量离线审核

从 [POLY02 私有 Release](https://github.com/Jupiter0914/dip-final-project-lab/releases/tag/poly02-review-v1) 下载 ZIP 与 .sha256，核对外部哈希后解压。以下命令核对内部清单、冻结代码、306 个独立输入、五组确定性实验的 6,396 个文件、88 个作者试验与本机配对对照文件，重新计算区域、三档容差的边界指标、保护单调性和主要配对区间。选中的 5 个案例另从源掩模重新编码 10 次，并从示例移动前后字节独立验证接受/拒绝。无需联网、MATLAB 或 GPU。安装科学 Python 依赖后在包根目录运行。

```powershell
python -X utf8 -m poly02.review audit
```

确认前冻结提交为 12d337b5e8a38e73dc10bf45913e1790eff611d5。POLY02-INFO.json 标明最终提交；POLY02-SHA256.csv 列逐文件哈希。v1 的旧代码、原始判定与旧标签均保留，完整 v1 离线包仍从 topic-confirmation-v1 Release 获取。

## 从 Git 重新获取并运行

本机为 Windows 11、Python 3.12.13、OpenCV 5.0、NumPy 2.4.4、Pillow 12.2、psutil 7.2.2、Matplotlib 3.11，作者适配另用 SciPy 1.18.1、MATLAB R2024a 与 Image Processing Toolbox。原运行解释器 E:/Miniconda/envs/pytorch_cv/python.exe，OpenCV 单线程。数据抽取需要支持 RAR5 的 libarchive tar，Windows 11 自带的 tar.exe 已实测。普通 Git 存逐图表和小图，原标注与实际批量 .poly 位于 data/poly02、local/poly02，审核 ZIP 内含所需样本。获取源码时使用带标签的正常克隆。

```powershell
python -m pip install -r configs/poly02/requirements.txt
python -X utf8 scripts/prepare_data.py --check
python -X utf8 -m poly02.resources
python -X utf8 -m poly02.data
python -X utf8 -m poly02.lock
python -X utf8 -m poly02.run dev --output local/repro02-dev
python -X utf8 -m poly02.run new --output local/repro02-new
python -X utf8 -m poly02.run cross --output local/repro02-cross
python -X utf8 -m poly02.run curve --output local/repro02-curve
```

--output 需要全新目录；自定义目录下的 polygons/ 对应该次运行的实际编码。可对新目录单独复算统计，保持已提交表格原样。

```powershell
python -X utf8 -c "from pathlib import Path; from poly02.analyze import analyze,decide; f=Path('local/repro02-new'); analyze(f); decide(f)"
```

MATLAB 三种子复现为可选项，使用 fresh 输出根，自动复制最小输入、原版作者文件及冻结包装器，再逐次比较种子、输出状态与 POL1 字节。启动 MATLAB 的成本、求解器时间和完整编码时间分别保留。用户提供的其他图片只支持二值外圈的任务定义。

```powershell
python -X utf8 -m poly02.repeat_pso --output local/repro02-matlab
```

## 证据定位

| 内容 | 入口 |
|---|---|
| 开发数据及首次实现检查 | [主开发 CSV](../../results/poly02/dev/per_image.csv)、[追加 K 开发 CSV](../../results/poly02/dev_curve/per_image.csv)、[360 项 v1 字节对照与移动核查](../../records/poly02/mechanism-check.json) |
| 200 张 Oxford 新确认 | [逐图与计时](../../results/poly02/new/per_image.csv)、[配对](../../results/poly02/new/paired_summary.csv)、[冻结判定](../../results/poly02/new/decision.json) |
| 70 类 MPEG 独立外域 | [逐图](../../results/poly02/cross/per_image.csv)、[配对](../../results/poly02/cross/paired_summary.csv) |
| 同 25 张照片的多预算质量 | [曲线 CSV](../../results/poly02/quality-by-k.csv)、[质量图](../../results/poly02/figures/quality-by-k.png)、[质量与耗时图](../../results/poly02/figures/quality-time.png) |
| PSO 与计算开销 | [作者逐种子试验](../../results/poly02/pso/trials.csv)、[原始坐标](../../results/poly02/pso/vertices.json)、[同图确定性对照](../../results/poly02/pso/controls.csv)、[预热重复](../../results/poly02/timing/repeats.csv)、[全点 DP 独立进程内存](../../results/poly02/timing/dp_memory.csv) |
| 来源、程序和工具 | [原包与成员校验](../../records/poly02/resources.json)、[Oxford 署名](../../records/attribution.md)、[工具辅助与环境记录](../../records/poly02/execution.md) |
