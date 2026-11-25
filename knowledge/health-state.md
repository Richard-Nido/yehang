# 夜航的身体恢复度与日级生理压力

这两个 0–100 分描述测量值相对本人的变化。恢复度越高，睡眠和心血管信号越有利。日级生理压力越高，当天的静息心率和 HRV 组合提示的生理负担越大。尚无针对夜航分数的前瞻验证，不能解读为恢复百分比、压力发生概率、心理测评或适岗结论。

## 使用的数据

* 主睡眠按分析时区的醒来日归属，夜班后的白天睡眠也可以成为主段。选择已睡时间最长的段，只接纳完整落在实际已睡区间中的 SDNN 样本，排除明确清醒、段内空档、其他来源和手动排除记录。
* 恢复计算使用主睡眠内 SDNN 中位数、当日已睡总分钟、当日静息心率中位数。压力计算使用当日全部 SDNN 的中位数和当日静息心率中位数。后者仍受采样时段、活动和呼吸等影响。当前导入器读取 SDNN 摘要。
* 每个 HRV 输入至少需 2 条样本。睡眠及睡眠内 HRV 沿用项目的导入边界检查。每个输入独立回看之前 28 个本地日，至少 14 个有效日。同排班情境满 7 日时优先采用该组。必需输入缺失时相应分数显示「资料不足」。同一指标只使用一个来源，优先沿用既有来源设置，缺少设置时选择有效记录较多的来源。

## 计算与计划

SDNN 先取自然对数；其他指标使用原单位。各指标与所选参照的中位数比较，以 1.4826 × MAD 作尺度。为避免平坦历史放大微小差值，尺度下限分别为 0.15 对数单位、3 bpm、60 分钟。标准化差值 z 截断到 [−3, 3]。这些下限、样本门槛和决策阈值均为工程参数。

```text
sigmoid(x) = 1 / (1 + exp(-x))
恢复组合 = (0.55 × z主睡眠SDNN − 0.25 × z静息心率 + 0.15 × min(z睡眠分钟, 0)) / 0.95
恢复度 = round(100 × sigmoid(1.25 × 恢复组合 + 0.35))
日级生理压力 = round(100 × sigmoid((z静息心率 − z全天SDNN) / 2))
```

恢复度借鉴 Pulsr 的权重和映射，改用个人稳健基线和睡眠相对时长。睡得超过本人习惯时长不额外加分；长期习惯性睡眠不足也可能得到接近基线的分数。日级压力为本项目的探索性公式。两项共用静息心率，不能作为两个独立证据累加。

休息推荐使用截至规划时刻已经结束的样本。睡眠时长和当天恢复度参与短休时长与优先级计算，随后与工作、通勤及已保存计划一起选择候选。观察日可回看。反馈中的疲劳用于复盘，算法与参照依据详见[休息时间如何计算](rest.md)。

## 开源实现与验证证据

| 参考 | 对夜航的意义 |
|---|---|
| Grow | 开发者公开列出 HRV 压力和恢复度，公开说明未给出可复现的评分公式。[App Store](https://apps.apple.com/cn/app/id1560604814) |
| Pulsr（MIT） | 可审查的 Swift 恢复算法使用睡眠内 SDNN、静息心率等。其日内压力处理另需逐次心率和运动区间。本次检索未发现最终分数的独立验证。[固定版本源码](https://github.com/0xCodez/pulsr/blob/4341fde6abf9cd16a84703a97feba939bfee5e34/Shared/ScoreEngine.swift) · [许可声明](Pulsr-LICENSE.txt) |
| cStress（BSD-2-Clause） | 有独立实验室和实地验证，依赖 ECG、呼吸等信号及活动过滤。研究报告实地瞬时自评预测准确率约 72%，该表现不能外推至夜航。[代码](https://github.com/MD2Korg/cStress-model) · [验证研究](https://pubmed.ncbi.nlm.nih.gov/26543926/) |
| NeuroKit2、pyHRV、HeartPy | 有可读的信号处理代码，适用于相应波形、峰值或逐搏间期。有 SDNN 摘要时无法从中反推原始间期或 RMSSD。[NeuroKit2](https://neuropsychology.github.io/NeuroKit/functions/hrv.html) · [pyHRV](https://github.com/PGomes92/pyhrv) · [HeartPy](https://github.com/paulvangentcom/heartrate_analysis_python) · [Apple SDNN 定义](https://developer.apple.com/documentation/healthkit/hkquantitytypeidentifier/heartratevariabilitysdnn) |
| Push/Pause、WESAD | 前者的方法文档说明权重未经验证，所核版本的引擎文件只有导入语句。后者是 15 人的实验室多模态数据集，可用于研究压力分类。[Push/Pause 源码](https://github.com/pushorpause/algorithm/blob/2ea3e8095f77c8643cd7993282af2852f446f677/ReadinessEngine.swift) · [WESAD](https://archive.ics.uci.edu/dataset/465/wesad) |

关于实际有效性，HRV 指导训练的试验多采用标准化静息测量，无法直接验证这里的权重。Apple Watch 日常环境研究发现 HRV 与主观压力关联较弱。需要用独立时间段的自评及实际休息结果检验本项目分数，软件回归仅验证实现是否按规则运行。[训练研究综述](https://pubmed.ncbi.nlm.nih.gov/34489178/) · [Apple Watch 实地研究](https://pubmed.ncbi.nlm.nih.gov/37475772/)
