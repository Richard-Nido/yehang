# macOS Apple Silicon 打包

适用 Apple M 系列芯片、macOS 13+。业务代码和网页资源来自 v0.1.0-beta.2（07e695dfdf6d6a870612c2297438f84cd7bc71ce），无需为 Mac 修改算法或 API。

## 构建

在仓库根目录使用 Python 3.11 arm64：

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt pyinstaller==6.22.3
.venv/bin/python -m unittest discover -s tests -v
bash packaging/build-macos.sh
```

应用在 `.build/macos/dist/Yehang.app`，ZIP 和校验值在 `.build/release/`。也可以用 `PYTHON=/绝对路径/python bash packaging/build-macos.sh` 指定已有环境。

`launch_macos.py` 沿用 Windows 启动流程，调整 macOS 图标处理、字体、Command-Q 退出及数据目录。`macos.spec` 收集网页、夹具、时区、PDF 引擎、XML 解析器及 macOS Keychain 后端。许可证在应用 `Contents/Resources/licenses`。

## 使用

解压后将 `Yehang.app` 拖到“应用程序”，双击启动。程序自动打开本机浏览器；关闭启动窗口或 Command-Q 退出服务。用户无需安装 Python 或本地模型。

数据保存在 `~/Library/Application Support/Yehang/`。模型服务由用户自行配置 API，本包不含凭据。Office 转换对应 Windows 标准版：Mac 需安装 LibreOffice 到 `/Applications/LibreOffice.app`，或先将文档转为 PDF。

本配置仅作 ad-hoc 签名，未做 Developer ID 签名和 Apple 公证。如 macOS 阻止启动，核对下载来源后在“系统设置 → 隐私与安全性”选择“仍要打开”。Intel Mac 不在本次交付范围。

## 已发布包的验证

2026-11-26，macOS 26.7.2、Python 3.11.15 arm64：源码 26/26 测试通过；beta.2 Mac 包验证了静态网页、示例恢复/压力指标、应用窗口启动、保存计划、保存反馈以及同库重启后反馈保留。未实测 Mac Office 转页（测试机未安装 LibreOffice）及在线 API。发布包见仓库 v0.1.0-beta.2 Release。

本 PR 将当时仓库外的打包文件整理为仓库相对路径；启动行为与已发布包一致。ZIP 只包含应用，不包含测试数据库。
