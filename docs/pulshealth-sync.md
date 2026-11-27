# PulsHealth 局域网同步试运行

本次源码更新基于 beta.2，尚未替换正式 Release 的安装包。个人基线算法沿用原实现，新增 Puls Sync Protocol v1 适配。先按 README 创建 `.venv` 并安装 `requirements.txt`，Mac 再双击 `start-puls-mac.command`，进入 `http://127.0.0.1:8521/#data`。脚本优先使用本仓库 `.venv`，开发机也可使用同级 `macos-build-env`。

本次脚本独立使用 `.local/puls-preview/interactive.sqlite3`，不读取原有个人健康库，也不继承原模型配置。局域网接收默认关闭；在“数据输入”点“开启临时局域网同步”后才监听 8520。主网页仍仅监听本机 8521。

## iPhone

1. Mac 和 iPhone 连接可信的同一 Wi-Fi，保持夜航运行。此原型为 HTTP（未加密），只用于本次短期验证，不用于公共网络或公网。正式发行前应补齐适合手机客户端的 HTTPS／可信网络方案。
2. PulsHealth → Connections → ＋ → Your database。Database URL 填 `http://电脑局域网IP:8520`；Token 从夜航数据输入页复制。填写的是 Mac 的 Wi-Fi 地址，不是 127.0.0.1。
3. Test Connection，Save & Apply。在 Raw Samples 中选择 Sleep Analysis、Resting Heart Rate、Heart Rate Variability SDNN。免费版先三项；不要以 Aggregates（日汇总）替代原始样本。
4. 允许所选健康读取权限，并让手机解锁、App 保持前台完成首次同步。记录同步状态和夜航接收计数，然后再次同步，检查总量未翻倍。
5. 夜航个人档案总览自动使用收到的记录。点“停止同步”关闭临时接收端。关闭启动终端也会结束两项服务。

## 支持范围

- 六类原始样本：睡眠、心率、静息心率、HRV-SDNN、步数、活动能量；保留分期，单位统一，按上海时间分析。
- gzip NDJSON、毫秒时间戳（含小数）、UUID 大小写统一、整批事务、批次重传去重、删除标记和迟到样本保护。
- 一套试运行库只绑定一个 PulsHealth 用户；授权连接的首批完成绑定。来源以摘要映射为匿名别名，不保存姓名、设备名或个人资料。
- 其他原始类型、聚合、活动环、轨迹和个人资料不保存；协议允许接收端只存所需数据，页面计入“未用于分析”。不向 App 宣称支持 profile、stats、digest 或 reconcile。
- HTTP 接收端只提供 `/healthz`、`/v1/capabilities`、`/v1/batches`，鉴权口令存试运行库同目录，不开放模型配置、计划编辑或历史清除接口。
- 没有加入 Bonjour、扫码、HTTPS、手机远程唤醒或后台时效保证。后续 Pulso 只需另写协议适配，共用标准化记录和存储语义。

## 历史 XML 与同步

本次用全新试运行库，不混合旧 XML。XML 和 HealthKit 的来源身份格式不同，跨入口来源合并及旧 XML 副本在健康删除后的归属仍待后续迁移设计。现有库请保留；不要手动复制到试运行目录。

## 验证

`python -m unittest discover -s tests -v`：46 项通过（原有 26 项＋同步 8 项＋行动建议 12 项）。合成用例覆盖鉴权与接口隔离、跨夜 105 分钟、单位换算、重复上传、失败回滚、删除及迟到重传、相同内容多身份保护、同库重启和用户绑定。

2026-11-27 已在本机完成 iPhone 同 Wi-Fi 连接和心率、静息心率、HRV 原始样本上传，页面可读取同步记录。本机没有用于真机验证的睡眠记录，睡眠清洗由合成用例验证；其他设备和网络环境需另行验证。健康原始数据与连接口令不随仓库交付。上游协议和解析代码许可见 `third_party/pulshealth/`。
