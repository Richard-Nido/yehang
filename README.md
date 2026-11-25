# 夜航

**0.1.0-beta.1** · 本机运行的轮班休息助手

把 Apple 健康记录和未来七天的日程放在一起，找到可以休息的时段。保存计划后，可用实际记录和自己的感受回看这次休息。应用统一按上海时间展示。

## 启动

Windows 安装 Python 3.11 或更新版本，双击 `start-interactive.cmd`。首次启动会创建虚拟环境并安装依赖，然后打开本机浏览器。使用 macOS 或 Linux 时，在仓库目录运行以下命令。

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python launch_studio.py
```

服务默认监听 127.0.0.1 的 8518 端口，端口已占用时会选择空闲端口并打印地址。终端按 Ctrl+C 退出。Linux 保存密钥需要可用的系统凭据服务，例如 Secret Service。

## 首次体验

- 总览的「切换」可进入示例档案，手机上点页首档案名。示例使用虚构记录和固定时钟，可直接体验推荐、调整和保存。
- 在「我的档案 → 数据输入」选择解压后的 Apple 健康 export.xml，或符合互动版 v1 格式、mode 为 personal 的 JSON。单文件上限 1 GiB（1,073,741,824 字节）。文件在本机分块处理，重复导入会合并已有记录。
- 在「模型设置」填写 Base URL、接口协议、API Key、模型名称。可从服务获取模型列表，也可直接输入模型 ID。支持 OpenAI Chat Completions、OpenAI Responses、Anthropic Messages、Google Gemini。配置方式参考 [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI/blob/main/config.example.yaml)。
- 「生理解读」自动向文字模型发送最近七天的指标汇总。失败时提示「模型调用失败」并显示本机规则解释，可直接重试。「排班识别」默认复用该服务，也可单独指定支持图像输入的 Base URL、协议、密钥及模型。
- 「七日安排」上传图片或 PDF 时，页面会说明所选文件将发送给视觉模型。PDF 分页转成图像；模型提取人员、日期和班次。多人表先选择本人，勾选确认后保存。不明确的班次可手动补充。手动输入支持多选日期、跨夜班和小时/分钟滚轮。
- 「休息计划」综合近期睡眠、个人基线和工作空档给出推荐。拖动时间轴色块移动开始时间、拖动右端调整时长，也可分别选择开始和结束日期。日程冲突会提示，仍可保存。算法与适用条件见[推荐依据](knowledge/rest.md)。
- 「复盘」点选完成、部分完成或跳过，可补选休息后的感受。再次导入健康记录后，复盘会显示计划时段内的设备睡眠记录，以及前后各 24 小时静息心率和 SDNN 的变化。

## 数据与维护

健康记录、日程和反馈保存在本机 `.local/interactive.sqlite3`。供应商设置保存在同目录，密钥使用操作系统凭据库。每台电脑使用自己的档案与模型配置。备份旧互动版时，先退出旧应用，将其 SQLite 数据库备份到新目录的 `.local/interactive.sqlite3`；也可通过 `YEHANG_DB_PATH` 指定已有数据库的独立副本。

- `studio.py` 和 `launch_studio.py` 为 HTTP 服务与启动入口，`web/` 为浏览器界面，无需 Node 构建。
- `adapters/`、`core/` 和 `storage/` 沿用互动版的单位换算、睡眠分段、个人基线与 SQLite 结构。`beta/` 提供流式导入、推荐、复盘和模型服务适配。
- `yehang-week/fixtures/` 仅包含合成数据。`tests/` 可用 `python -m unittest discover -s tests -v` 复跑，无需供应商密钥。
- [健康评分方法](knowledge/health-state.md) 和 [Pulsr 许可](knowledge/Pulsr-LICENSE.txt) 随代码保留。应用侧的推荐阈值和候选排序尚未经过临床验证。
