# 实验结果与离线回放

解压完整的 `poly05-replay.zip`，双击 `report/poly05/replay/index.html`。选择 Ragdoll_32，展开“查看这个源的真实跨圈动作”，即可对照同一条编码轨迹里转移顶点前后交付的两份 PM31 文件。八个案例的图像和数据都随包提供。[下载回放包](https://github.com/Jupiter0914/dip-final-project-lab/releases/tag/poly05-replay-v1)

| 想核对什么 | 查哪里 |
|---|---|
| 两种方法怎样分配同一组顶点 | [代码导读](code_guide.md) · [六幅图及原始文件](figures.md) |
| 一项结果按多少个来源、多少次调用计算 | [事实表](facts.csv) · [配对和计时口径](corrections.md) |
| 某个案例的源图、实际交付字节、裁片及时间 | [案例清单](replay/index.json) |
| 初始协议、所有运行与科学环境 | [冻结协议](../../records/poly04/freeze.md) · [POLY04 完整审核包](https://github.com/Jupiter0914/dip-final-project-lab/releases/tag/poly04-confirm-review-v1) |

## 在本地复算

在克隆或解压后的根目录使用 Python 3.12、NumPy 2.4.4、OpenCV 5.0.0.93 和 Pillow 12.2.0。下列命令重新统计原始逐次观察，解码样例，并检查图片与文件链接。解压包中还会比对逐文件 SHA-256 清单。

```shell
python -B -X utf8 scripts/poly05/verify.py
```

已有证据可以重新绘图。安装 Matplotlib 3.11.0 后运行下列命令。图中的中文和数字分别采用宋体和 Times New Roman，可通过 `POLY05_SIMSUN` 和 `POLY05_TIMES` 指定字体文件。重建请使用单独的解压副本，方便与发布时的原始文件校验值核对。

```shell
python -B -X utf8 scripts/poly05/build.py
python -B -X utf8 scripts/poly05/build.py --figure 2
```

配好 Node.js 和 Playwright 后，可运行 `node scripts/poly05/browser_check.cjs` 检查断网浏览、案例切换及误差图显示。环境变量 `POLY05_CHROMIUM` 可指定本地 Chromium 程序。[核验记录](verification.json)

图形与数据来自 Oxford-IIIT Pet 和 LEMS。原始统计对应提交 `9c8ce11`，冻结协议对应 `ff70458`。回放图展示历史运行实际交付的字节。[Oxford 标注署名](../../records/attribution.md) · [LEMS 来源记录](../../records/poly02/research.md) · [项目首页](../../README.md)
