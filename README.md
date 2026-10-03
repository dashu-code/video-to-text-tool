# 视频转文字工具（Video to Text Tool）

把直播回放、会议录音、课程视频等**音视频文件**一键转换成**带时间戳的文字稿（SRT）**。

基于开源语音识别模型 [Whisper](https://github.com/openai/whisper)（GGML / whisper.cpp 推理框架），**识别全程在本机离线运行，不上传任何数据**。

仓库提供两种用法：

| 版本 | 入口 | 说明 |
|------|------|------|
| **命令行版**（轻量） | 把视频拖到 `4.bat` | 最少依赖，黑窗口交互，选档位后直接出字幕 |
| **桌面 GUI 版** | `desktop-app/app.py` | 图形界面 + 内置模型下载 + 可选「AI 校对（去口水词）」 |

## 功能

- 支持任意常见音视频格式（mp4 / mkv / mov / wav / mp3 ...）
- 输出 `transcript.srt`（带时间戳字幕）+ `transcript.json`
- 三档识别精度可选，按需权衡速度与准确度
- 纯本地识别，无需联网（模型下载一次后即可离线使用）
- （GUI 版，可选）转写后调用大模型 API 去口水词、修错别字，输出 `transcript_clean.srt`

## 三档模型

| 档位 | 模型 | 速度 | 准确度 | 适合场景 |
|------|------|------|--------|----------|
| 1 快速 | tiny (q8_0, ~41 MB) | 最快 | 较低 | 粗看内容、时效性优先 |
| 2 标准 | small (q8_0, ~252 MB) | 中等 | 良好 | 日常转换（默认） |
| 3 精确 | large-v3 (~2.9 GB) | 最慢 | 最高 | 正式稿、需高准确度 |

## 快速开始（命令行版）

1. **下载模型和依赖**（仅首次）：双击运行 `get_models.bat`，按提示选择要下载的档位，再自动下载解压 FFmpeg（生成 `1.exe`）。可重复运行以续传。

   ```
   1 = tiny 仅        ~41 MB   想先快速试一下
   2 = small 仅       ~252 MB  日常使用推荐
   3 = tiny+small     ~293 MB  [默认]
   4 = 全部三档       ~3.2 GB  含 large-v3，国内可能要好几个小时
   0 = 跳过模型只装 ffmpeg
   ```

   > **只想先试一下？选 1**，41 MB 就能跑通全流程；`large-v3` 有 2.9 GB，别一上来就下它。
2. **转换视频**：把视频文件直接拖到 `4.bat` 上，松手。
3. 黑窗口会让你选档位（直接回车 = 标准档），选好后等待。
4. 结束后同文件夹内生成 `transcript.srt`，用记事本打开即为带时间戳的文字稿。

> 提示：识别阶段需要几分钟，请耐心等待窗口跑完，不要提前关闭。

> **默认档位 2（标准/small）需要 `m_mid.bin`。** 如果你想省流量只下 tiny，第 1 步请选 `1`，
> 第 2 步菜单里也要选 `1`（快速），两边对不上会提示 `model file not found`。
> 最省事的做法：第 1 步选 `3`（默认，tiny+small 都下），第 2 步直接回车。

## 桌面 GUI 版

`desktop-app/app.py` 是 Tkinter 图形界面，把「选视频 → 选档位 → 下载模型 → 转换 → 打开结果」串成一个窗口。

```bat
:: 依赖：Python 3.8+（自带 tkinter），且同目录已放好 1.exe / 2.exe / whisper.dll / ggml*.dll
python desktop-app\app.py
```

想打包成单文件 exe（需先 `pip install pyinstaller`）：

```bat
cd desktop-app
pyinstaller VideoToTextApp.spec
```

打包产物 `dist/VideoToTextApp.exe` 要放到含 `1.exe`、`2.exe`、`whisper.dll`、`ggml*.dll` 的目录里运行；模型下载到同级 `models/` 目录。

### AI 校对（可选，需要自己的 API Key）

GUI 的第 4 区可调用任意 **OpenAI 兼容**接口，对 SRT 做最小化校对：删口水词、合并结巴重复、修同音错别字。

配置方式二选一：

1. **环境变量（推荐，密钥不落盘）**

   ```bat
   set VIDEOTOTEXT_API_KEY=你的Key
   set VIDEOTOTEXT_BASE_URL=https://api.deepseek.com/v1
   set VIDEOTOTEXT_MODEL=deepseek-chat
   python desktop-app\app.py
   ```

   也兼容 `DEEPSEEK_API_KEY` / `OPENAI_API_KEY`。

2. **`config.json`**：从 `config.example.json` 复制成 `config.json`，填好 `api_key` 等字段，放在 `app.py` 同级目录。

> **不要把 `config.json` 提交到仓库。** 根目录 `.gitignore` 已忽略它；本仓库的文件与历史中均不含任何密钥。

## 文件清单

| 文件 | 说明 |
|------|------|
| `1.exe` | FFmpeg，负责抽取音轨（由 `get_models.bat` 自动下载，不入库） |
| `2.exe` | Whisper-CLI，语音识别引擎（不入库，见下方「获取二进制」） |
| `4.bat` | 命令行版一键脚本（把视频拖到它上面） |
| `get_models.bat` | 一键下载三个模型 + FFmpeg |
| `whisper.dll` / `ggml.dll` / `ggml-base.dll` / `ggml-cpu-haswell.dll` | 运行依赖库 |
| `m_fast.bin` / `m_mid.bin` / `m_large.bin` | 三个模型（由 `get_models.bat` 下载） |
| `desktop-app/app.py` | 桌面 GUI 主体 |
| `desktop-app/VideoToTextApp.spec` | PyInstaller 打包配置 |
| `config.example.json` | GUI 的 API 配置模板（复制为 `config.json` 后填写） |

### 获取二进制

`1.exe`、`2.exe` 与 `whisper.dll` / `ggml*.dll` 体积较大，不放进仓库（GitHub 单文件 100 MB 限制）：

- `1.exe`（FFmpeg）：运行 `get_models.bat` 自动下载。
- `2.exe` + dll：从 [whisper.cpp releases](https://github.com/ggml-org/whisper.cpp/releases) 下载 Windows x64 版，把 `whisper-cli.exe` 改名成 `2.exe`，并把同目录的 `whisper.dll`、`ggml*.dll` 一起放到根目录。

## 说明

- 识别结果由机器学习模型生成，可能存在同音错别字或时间戳误差，正式用途请人工校对。
- 命令行版只做「机器初稿」，校对环节建议人工完成。
- AI 校对只是「机器二稿」，它会按提示词删除口水词，涉及原意的改动请自行复核。
- 核心识别能力来自 [whisper.cpp](https://github.com/ggml-org/whisper.cpp)，本仓库是其 Windows 一键封装。

## 开源协议

[MIT License](LICENSE)
