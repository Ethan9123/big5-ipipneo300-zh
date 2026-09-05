# 大五人格测评 · IPIP-NEO-300 中文版

线上：<https://big5.try-board-game.uk/>

一个单文件、离线可用的 IPIP-NEO-300 中文实现。300 道题，5 个维度 + 30 个子面向，
作答与计分全部在浏览器里完成，不上传任何数据。

本仓库除了站点本身，还包含用 Johnson 的 **145,388 份常模样本**做的一整套验证与改造工具。

---

## 这一版做了什么

### 1. 用经验百分位表替换三次多项式近似

原版（five-factor-e / Johnson 的 CGI 脚本）把 T 分经一条三次多项式转成百分位，
并在 `T<32` / `T>73` 处硬截断为 1 和 99。在常模样本上实测，这条映射：

- 平均偏 **2.94** 个百分位，最大 17.2
- **4.47%** 的分数被截断压平（53.2% 的人至少有一个量表被压平）
- 误差主要不来自截断，而来自真实分数分布并不服从正态

改为直接查同一样本算出的经验百分位表（14,610 格，单调、无空洞）：

| | 原版 | 本版 |
|---|---|---|
| 平均绝对误差 | 2.9900 | **0.0576** |
| 最大误差 | 17.175 | **0.125**（量化上限） |
| 被截断的值 | 4.64% | **0** |

体积代价：+8.6 KB brotli。表的构建与压缩编码见 [`tools/build_tables.py`](tools/build_tables.py)，
浏览器端解码器 4 行核心逻辑，无依赖。

### 2. 常模同步刷新

原版内置的 6 组常模向量与该样本对不上：平均每人 35 个量表里有 28.5 个会移动 ≥1 个百分位，
83.5% 的人至少有一档 低/中等/高 会变。现已换成同一样本重算的均值/标准差，
T 分与百分位从此自洽。

### 3. 低 / 中等 / 高 的分界

原版用 45/55——那是 **T 分**的惯用分界，套在百分位上是单位错误，会把 88% 的量表推向两端。
改为 30/70，与页面正文一致；经验百分位在样本内均匀分布，这恰好切出 30% / 40% / 30%。

### 4. 243 个组合画像

5 个维度各切三档 → 3⁵ = 243 种组合，每种一篇（生活 / 交友 / 恋爱 / 工作 / 优点 / 缺点 / 可练习的动作）。

**243 格在样本里全部有人落入**，最稀有的一格也有 24 人。项目的测量误差模拟中，**组合档位保持率约为 47.2%**（`tools/cells_243.py`），这不是真实重复施测得到的重测一致率，也不是个人下次测验的预测概率。
66.8% 的人至少有一个维度落在离 30/70 分界 5 分以内。因此文案一律写成倾向描述而非类型断言，
页面会主动标出贴近边界的维度并展示邻格。

质量以**判别性**衡量（遮住维度名，只看文字盲猜档位，随机基线 33.3%）：

```
O 开放性 94.7%   C 尽责性 97.1%   E 外向性 98.8%   A 宜人性 96.7%   N 神经质 98.8%
五维全对率 209/243 = 86.0%
```

### 5. 修了一个线上 bug

`saveCard()` 调用了从未定义的 `levelWord`，「保存分享卡片」一直抛 `ReferenceError`，
点了什么都不会发生。

### 6. 部署加固

`_headers` 里的 `connect-src 'none'` 把「作答不上传」从一句承诺变成浏览器强制执行的规则——
实测 fetch / XHR / WebSocket / sendBeacon / EventSource / 动态 script / 图片信标 七条外泄通道
全部被拦，`transferSize` 均为 0。同时移除了 Cloudflare Web Analytics beacon。

---

## 计分正确性

- 面向聚合与 T 分与 `five-factor-e` **逐值等价**：145,388 × 35 = **5,088,580 个百分位精确复现**（误差 0.0000000000）
- 148 道反向计分题的清单与 **IPIP 官方公布的 NEO Facets Key** 按题目文本逐条比对：
  **300/300 匹配，键控与面向归属各 0 处不符**（[`tools/verify_keying.py`](tools/verify_keying.py)）

第二条尤其重要：Johnson 发布的数据集里反向题**已经预先重编码**，所以用它验证反向表是循环论证。
必须回到 IPIP 官网的原始计分键才算数。

---

## 复现

```bash
pip install kagglehub pandas numpy brotli
python tools/fetch_dataset.py     # 下载 Kaggle 数据集（无需凭证）
python tools/prep.py              # 计分并缓存
python tools/build_tables.py      # 生成经验百分位表
python tools/patch_site.py        # site/index.html -> site/index.optimized.html
python tools/make_dist.py         # 组装 dist/（含验收门禁）
```

验证：

```bash
python tools/verify_keying.py     # 反向表 vs IPIP 官方键
python tools/verify_corpus.py     # 243 篇画像的验收门禁
python tools/discriminability.py  # 判别性测试
node   tools/verify_patch.js      # 计分回归（对着真实被试）
```

`dist/` 已提交，可直接部署，无需构建步骤。

---

## 来源与许可

- **题目**：[International Personality Item Pool](https://ipip.ori.org/)，公有领域。量表为 Johnson (2014) IPIP-NEO-300。
- **维度与面向释义**：原作者 John A. Johnson，已置于公有领域。
- **计分算法与原始常模**：移植自 [five-factor-e](https://github.com/NeuroQuestAi/five-factor-e)（MIT，© 2022-2025 NeuroQuest AI），
  该项目又基于 Dhiru Kholia 对 Johnson 原始 CGI 脚本的移植。
- **常模样本**：[IPIP-NEO Big Five Personality 300 item version](https://www.kaggle.com/datasets/edersoncorbari/ipip-neo-big-five-personality-300-item-version)（n=145,388）。
- **中文翻译、243 篇画像、以及本仓库的分析与改造**：由 Claude (Anthropic) 完成，**未经跨文化信效度验证**。

本测评仅供教育与自我了解用途，不是心理或医学建议，不能用于临床诊断或人事甄选。
IPIP-NEO-300 是商业量表 NEO PI-R™ 的公有领域替代品，两者并不等同；本项目与 PAR 及 NEO PI-R™ 无关。

## 已知局限

1. **分档受测量误差影响** —— 47.2% 是根据内部一致性和噪声假设得到的组合档位保持率模拟值，不是实测重测信度。页面用边界提示和相邻画像帮助阅读，不用这个数字预测个人结果。
2. **常模不是中国人群常模** —— 样本 69.2% 来自美国、86.3% 来自英语圈，中港台新合计仅 1.46%（2,117 人）；
   中位年龄 22 岁、58.3% 女性。百分位请当作粗略参考刻度。
3. **详解模式的影响尚未验证**。情境说明可能影响判断，但本站没有验证影响的方向和幅度。比较两次结果时应尽量保持模式一致。
4. **解读文案不等于效度证据**。维度解读显示本次分数、子面向位置与生活核对问题；组合画像提供参考情境。文案区分度、主观认同感和计分正确性，都不能替代中文版本的效度验证。
