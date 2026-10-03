# Desktop GUI（Tkinter）

图形界面的「视频转文字」工具，等价于 `4.bat` 的操作，但把流程做成了窗口。

## 运行

需要 Python 3.8+（标准库自带 tkinter），并且程序目录里已有引擎文件：

```
1.exe                                  # FFmpeg（抽音频）
2.exe                                  # whisper-cli（识别）
whisper.dll ggml.dll ggml-base.dll ggml-cpu-haswell.dll
models/m_fast.bin  m_mid.bin  m_large.bin   # 可由界面「下载所选模型」生成
```

```bat
python app.py
```

## 打包

```bat
pip install pyinstaller
pyinstaller VideoToTextApp.spec
```

`--onefile` + `console=False`：产物是单个 `dist/VideoToTextApp.exe`（不含引擎文件与模型，需与它们放在同一目录）。

> 注意：`app.py` 用 `sys.argv[0]` 而不是 `sys.executable` 定位程序目录，因为 onefile 模式下后者指向临时解压目录。

## API Key 与脱敏约定

本目录**不包含任何密钥**，提交前请确认：

- `app.py` 里没有硬编码 key（当前实现从环境变量或 `config.json` 读取）。
- `config.json` 不提交（根目录 `.gitignore` 已忽略；本目录另有一份 `.gitignore` 兜底）。
- 需要密钥时优先用环境变量：

  | 环境变量 | 用途 |
  |----------|------|
  | `VIDEOTOTEXT_API_KEY`（也认 `DEEPSEEK_API_KEY` / `OPENAI_API_KEY`） | API Key |
  | `VIDEOTOTEXT_BASE_URL` | OpenAI 兼容接口地址，默认 `https://api.deepseek.com/v1` |
  | `VIDEOTOTEXT_MODEL` | 模型名，默认 `deepseek-chat` |

  优先级：环境变量 > `config.json`。这样 CI 或临时会话里可以完全不落盘。

## 自检

```bat
python tests\test_sanitize.py
```

校验 SRT 解析/回写往返一致，并扫描仓库文件确认没有 `sk-` 形式的密钥残留。
