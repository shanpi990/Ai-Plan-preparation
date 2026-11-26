# 施工方案 AI 审查客户端 v5

这个项目用于审查施工方案、在原 Word 段落上挂批注，并将人工采纳的整改写入 Word。下载源码后，可以先用随附的脱敏节选和历史审查记录演示，查看结果和导出 Word 均可在本地完成。

## 下载 Windows 客户端

到 [Releases](https://github.com/shanpi990/Ai-Plan-preparation/releases) 下载 `AI-Plan-Review-v5.0.0-Windows-x64.zip`，完整解压到本地可写文件夹，双击根目录的 `施工方案AI审查.exe`。客户端自带 Python。桌面窗口使用 [Microsoft Edge WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/)。

## 从源码启动

在 64 位 Windows 上安装 Python 3.12。在仓库根目录打开 PowerShell，依次执行以下命令。桌面窗口使用 Microsoft Edge WebView2 Runtime。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -B -X utf8 ".\程序文件\桌面客户端_v4.py"
```

也可以从源码运行本地网页服务。另开浏览器访问 `http://127.0.0.1:8876`。该端口被占用时，程序会依次使用 8877 至 8895 中的首个空闲端口。按 Ctrl+C 停止服务。

```powershell
.\.venv\Scripts\python.exe -B -X utf8 ".\程序文件\复审对照服务_v25.py"
```

## 演示数据

| 记录 | 在客户端查看 |
| --- | --- |
| 深基坑审查 | 216 条意见，可按引文定位到配套节选中的原文和表格，也可直接导出 Word 批注 |
| SMW 工法桩首审 | 21 条意见，记录含人工复核状态，整改对照表含 24 项采纳修改 |
| SMW 工法桩复审 | 20 条意见，可在复审对照页查看两轮结果与对应原文 |

桌面启动默认打开深基坑记录。切换样例时，在「AI诊断 → 更多操作」中导入 `审查记录` 中相应的 JSON。Word 原件在 `参考文件` 下，程序按文件指纹关联。现成的批注版、修订版、清洁版和供编制助手导入的参数 JSON 在 `审查结果` 下。深基坑的意见数来自整份方案的历史审查，随仓库提供的原文是保留表格和原段落版式的脱敏节选。

## 审查新方案和读图

进行新的模型审查时，在「模型设置」中填写自己的模型接口和密钥。「规范库」中可以导入自己的规范文件，逐条校对后入库。随仓库提供的规范索引包含目录、条号和来源链接，规范正文库由本地导入建立。

图纸 OCR、扫描页和矢量图转换使用独立的运行组件。如需直接演示这些功能，可使用配套文件夹版客户端。源码与文件夹版的角色相同，开发时使用 Python，文件夹版通过根目录 EXE 启动。

- 图纸识别使用 `程序文件/读图引擎/运行库/python.exe`。部署时可从对应文件夹版复制整个读图运行库。引擎调用方式见同目录的接入说明。
- Word 页面转换使用 `程序文件/native/LibreOffice`。PDF 页面转换使用当前 Python 可执行文件上两级目录下的 `native/poppler/Library/bin/pdftoppm.exe`；上述虚拟环境启动方式对应 `.venv/native/poppler`。
- 通过 `pip` 安装的 pywebview 调用 Windows 上的 WebView2。已完整解压的文件夹版自带 Python，也使用系统的 WebView2。
