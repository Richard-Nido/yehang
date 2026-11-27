# macOS Apple Silicon 打包

适用 Apple M 系列芯片、macOS 13+。beta.3 包含健康同步、可休息窗口、目标入睡时间与本机行动建议。业务更新来自 0647b32721322e5891ece975c9e2aa204c2ad91b，构建使用当前提交的完整源码；应用 `Contents/Resources/build-info.json` 记录版本和实际源码提交。

## 构建

在仓库根目录使用 Python 3.11 arm64：

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt pyinstaller==6.22.3
.venv/bin/python -m unittest discover -s tests -v
bash packaging/build-macos.sh
```

应用在 `.build/macos/dist/Yehang.app`，ZIP 和校验值在 `.build/release/`。也可以用 `PYTHON=/绝对路径/python bash packaging/build-macos.sh` 指定已有环境。

`launch_macos.py` 沿用 Windows 启动流程，调整 macOS 图标处理、字体、Command-Q 退出及数据目录。`macos.spec` 收集网页、知识依据、夹具、时区、PDF 引擎、XML 解析器及 macOS Keychain 后端。Python、Tcl/Tk、Pulsr、PulsHealth 及依赖许可在应用 `Contents/Resources/licenses`。

## 使用

解压后将 `Yehang.app` 拖到“应用程序”，双击启动。程序自动打开本机浏览器；关闭启动窗口或 Command-Q 退出服务。用户无需安装 Python 或本地模型。

数据保存在 `~/Library/Application Support/Yehang/`，替换应用会保留该目录。与源码脚本 `.local/puls-preview/` 相互独立。行动建议默认本机生成；排班识别和自然语言反馈整理所用模型服务由用户自行配置 API，本包不含凭据。Office 转换对应 Windows 标准版：Mac 需安装 LibreOffice 到 `/Applications/LibreOffice.app`，或先将文档转为 PDF。

本配置仅作 ad-hoc 签名，未做 Developer ID 签名和 Apple 公证。如 macOS 阻止启动，核对下载来源后在“系统设置 → 隐私与安全性”选择“仍要打开”。Intel Mac 不在本次交付范围。

## 验证与发布

2026-11-27，macOS 26.7.2、Python 3.11.15 arm64：当前业务源码 46/46 测试通过。发布前另检查打包应用的启动、静态网页、知识依据、目标睡眠、计划反馈保留和合成同步接口；结果与适用范围随 Release 提供。Mac Office 转页及在线 API 未在本次验证范围。ZIP 只包含应用，不包含测试数据库、真实健康记录或连接口令。
