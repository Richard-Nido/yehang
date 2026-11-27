# 夜航

**0.1.0-beta.2** · 本机运行的轮班休息助手

把 Apple 健康记录和未来七天的日程放在一起，找到可以休息的时段。保存计划后，可用实际记录和自己的感受回看这次休息。应用统一按上海时间展示。

当前源码已包含 2026-11-27 更新：PulsHealth 局域网同步试运行、可休息时段展示、目标入睡时间与本机行动建议。已有 beta.2 安装包保持原版本；体验这些更新请按下方从源码启动。手机连接说明见 [PulsHealth 同步](docs/pulshealth-sync.md)。

## Windows 安装

从 [GitHub Release](https://github.com/Richard-Nido/yehang/releases/tag/v0.1.0-beta.2) 下载适合的 x64 安装包，双击安装后打开「夜航」。两个安装包都内置 Python 环境。启动器会打开本机浏览器，关闭启动器可结束服务。

| 安装包 | 适用场景 |
|---|---|
| `Windows-x64-Setup.exe`（标准版） | 导入图片和 PDF。电脑已安装 LibreOffice 时也可以读取 Office 排班。 |
| `Windows-x64-Office-Setup.exe`（含组件版） | 安装时可勾选应用专用的 LibreOffice 转换组件，无需另外安装 Office。转换在本机进行，排班识别需要配置的模型服务。 |

安装版的记录和供应商配置存放在 `%LOCALAPPDATA%\Yehang\data`，可执行文件和程序资源位于用户程序目录。升级沿用安装版数据目录。初次安装可在「设置 → 配置文字与排班模型」填写供应商信息。发布资产另附 SHA-256 校验文件。

## 从源码启动

Windows 安装 Python 3.11 或更新版本，双击 `start-interactive.cmd`。首次启动会创建虚拟环境并安装依赖。使用 macOS 或 Linux 时，在仓库目录运行以下命令。

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
- 在「设置 → 配置文字与排班模型」填写 Base URL、接口协议、API Key、模型名称。可从服务获取模型列表，也可直接输入模型 ID。支持 OpenAI Chat Completions、OpenAI Responses、Anthropic Messages、Google Gemini。配置方式参考 [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI/blob/main/config.example.yaml)。
- 「身体解读」默认在本机生成，只解释达到个人参照提示门槛的变化，并结合班次、疲劳反馈和目标入睡时间安排短休与咖啡因提醒。无需本地大模型或 API Key，依据与适用条件在底部统一展开；另保留 API 可选文字补充接口。「排班识别」仍需配置支持图像输入的模型服务。
- 「七日安排」上传图片、PDF 或 Office 文件时，页面会说明所选文件将发送给视觉模型。Word、Excel、PowerPoint 在本机转为 PDF 后逐页转成图像。模型提取人员、日期和班次。多人表先选择本人，勾选确认后保存。不明确的班次可手动补充。手动输入支持多选日期、跨夜班和小时/分钟滚轮。
- 「休息计划」展示可休息时段的起止与时长，综合近期睡眠、个人基线和工作空档给出推荐；填写目标入睡时间后，候选限定在主要睡眠之前。拖动时间轴色块移动开始时间、拖动右端调整时长，也可分别选择开始和结束日期。日程冲突会提示，仍可保存。算法与适用条件见[推荐依据](knowledge/rest.md)和[行动建议](knowledge/actions.md)。
- 「复盘」可随时点选完成、部分完成或跳过，未来计划也可从「休息计划 → 反馈」进入。点击「用自己的话复盘」将自述交给文字模型整理，可修改执行情况、疲劳等级及备注，确认后才保存。再次导入健康记录后，复盘会显示计划时段内的设备睡眠记录，以及前后各 24 小时静息心率和 SDNN 的变化。

## 显示、历史与文件格式

总览有八个指标。身体恢复度和日级生理压力显示「自研算法估算」，由当前档案的睡眠、静息心率及 SDNN 计算。示例档案使用合成测量值和同一算法，含可直接复盘的短休计划。点选卡片和日期可查看单日读数，缺测日保留空缺。身体解读只提示值得留意的偏离，建议卡片统一使用浅绿色。

「设置」支持字号、总览指标和减少动态效果。解读缓存可单独清理。清除健康导入、日程、休息计划或复盘反馈时，会先显示当前档案及影响范围，确认后执行。清除计划会同时删除关联反馈。

| Office 家族 | 支持的 Microsoft 文件扩展名 |
|---|---|
| Word | `doc`、`docx`、`docm`、`dot`、`dotx`、`dotm` |
| Excel | `xls`、`xlsx`、`xlsm`、`xlsb`、`xlt`、`xltx`、`xltm` |
| PowerPoint | `ppt`、`pptx`、`pptm`、`pps`、`ppsx`、`ppsm`、`pot`、`potx`、`potm` |

识别保留 Office 文档的打印布局，包括表格和嵌入的图片。文档须可直接打开，宏不会运行。多人表勾选本人后确认写入；需要部件的源码安装可使用系统 LibreOffice。

## 数据与维护

源码版的健康记录、日程和反馈保存在本机 `.local/interactive.sqlite3`。供应商设置保存在同目录，密钥使用操作系统凭据库。每台电脑使用自己的档案与模型配置。备份旧互动版时，先退出旧应用，将其 SQLite 数据库备份到新目录的 `.local/interactive.sqlite3`；也可通过 `YEHANG_DB_PATH` 指定已有数据库的独立副本。

- `studio.py` 和 `launch_studio.py` 为 HTTP 服务与启动入口，`web/` 为浏览器界面，无需 Node 构建。
- `adapters/`、`core/` 和 `storage/` 沿用互动版的单位换算、睡眠分段、个人基线与 SQLite 结构。`beta/` 提供流式导入、推荐、复盘和模型服务适配。
- `yehang-week/fixtures/` 仅包含合成数据。`tests/` 可用 `python -m unittest discover -s tests -v` 复跑，无需供应商密钥。
- [健康评分方法](knowledge/health-state.md) 和 [Pulsr 许可](knowledge/Pulsr-LICENSE.txt) 随代码保留。应用侧的推荐阈值和候选排序尚未经过临床验证。

## Windows 维护者构建

在 Windows x64 使用 Python 3.11、PyInstaller 6 和 Inno Setup 7。安装项目依赖及 `pyinstaller` 后，执行下面命令。`-OfficeDir` 可省略，此时只生成标准安装包。输出在 `.build/release`。

```powershell
./packaging/build.ps1 -Compiler "C:/工具/Inno Setup/ISCC.exe" -OfficeDir "C:/构建/SourceDir/LibreOffice"
```

含组件版使用官方 LibreOffice 26.8.3 Windows x64 MSI 中的转换程序及同包的 System64 运行库，保留许可声明，省略离线帮助和拼写词典。在临时目录解开 MSI 后传入含 `program/soffice.com` 的目录，与 `System64` 同级。[上游源码及许可](https://www.libreoffice.org/about-us/licenses/) · [本版 MSI 的 URL 和散列](https://github.com/microsoft/winget-pkgs/blob/master/manifests/t/TheDocumentFoundation/LibreOffice/26.8.3.1/TheDocumentFoundation.LibreOffice.installer.yaml)

界面采用本机供应的 Noto Sans SC Variable（Fontsource 5.3.1，SIL OFL），字体和字体许可随程序分发。[字体许可](web/fonts/LICENSE) · [Apple 材质设计参考](https://developer.apple.com/design/human-interface-guidelines/materials)
