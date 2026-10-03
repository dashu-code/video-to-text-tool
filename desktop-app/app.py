# -*- coding: utf-8 -*-
"""
视频转文字工具 - 桌面 GUI
用户自选模型档位 -> 下载该模型 -> 选视频 -> 转写 -> 出 transcript.srt
可选：转写后用大模型 API 做「去口水词」校对，生成 transcript_clean.srt

机密信息说明（重要）：
  本文件不含任何 API Key，也不应出现。Key 的读取优先级为
  1) 环境变量 VIDEOTOTEXT_API_KEY / DEEPSEEK_API_KEY / OPENAI_API_KEY
  2) 程序目录下的 config.json（从 config.example.json 复制后填写）
  config.json 已列入 .gitignore，请勿提交到版本库。
"""
import os
import sys
import json
import shutil
import subprocess
import threading
import urllib.request
import urllib.error

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# 模型档位定义：显示名 / 本地文件名 / 下载地址
MODELS = {
    "fast": {
        "label": "快速 (tiny, 最快/精度低)",
        "file": "m_fast.bin",
        "url": "https://hf-mirror.com/ggerganov/whisper.cpp/resolve/main/ggml-tiny-q8_0.bin",
    },
    "mid": {
        "label": "标准 (small, 均衡) [默认]",
        "file": "m_mid.bin",
        "url": "https://hf-mirror.com/ggerganov/whisper.cpp/resolve/main/ggml-small-q8_0.bin",
    },
    "large": {
        "label": "精确 (large-v3, 最慢/最准)",
        "file": "m_large.bin",
        "url": "https://hf-mirror.com/ggerganov/whisper.cpp/resolve/main/ggml-large-v3.bin",
    },
}

# API Key 可用的环境变量名（按顺序取第一个非空的）
API_KEY_ENVS = ("VIDEOTOTEXT_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY")

# 各配置项可用的环境变量，用于不落盘地提供配置
CONFIG_ENVS = {
    "base_url": ("VIDEOTOTEXT_BASE_URL",),
    "model": ("VIDEOTOTEXT_MODEL",),
}

# AI 校对系统提示词
PROOF_SYSTEM = (
    "你是一名中文语音稿校对助手。下面是一段带时间码的 SRT 字幕。"
    "请只做最小化修改，并保持 SRT 结构（序号、时间码、每段行数）完全不变：\n"
    "1) 删除中文口语口水词（如 嗯、呃、那个、这个、就是、然后、其实、对吧、"
    "你知道吧、怎么说呢、可能、应该、好像、的话、一个 等）；\n"
    "2) 合并因结巴造成的重复字词；\n"
    "3) 修正明显的同音错别字。\n"
    "不要改写句子意思，不要增删内容，不要添加任何解释或代码块标记。"
    "只返回修改后的 SRT 文本。"
)


def app_dir():
    """程序所在目录（引擎文件 1.exe/2.exe/dlls 放在这里）。
    --onefile 模式下 sys.executable 是临时解压目录，用 sys.argv[0] 取真实 exe 路径。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.argv[0]))
    return os.path.dirname(os.path.abspath(__file__))


def models_dir():
    d = os.path.join(app_dir(), "models")
    os.makedirs(d, exist_ok=True)
    return d


DEFAULT_CONFIG = {
    "base_url": "https://api.deepseek.com/v1",
    "api_key": "",
    "model": "deepseek-chat",
    "auto_proof": False,
}


def load_config(base_dir):
    """读取配置。密钥优先级：环境变量 > config.json。

    仓库内不保存任何 Key；config.json 已在 .gitignore 中，仅存在于本机。
    base_dir 单独传参，便于不启动 GUI 地测试。"""
    cfg = dict(DEFAULT_CONFIG)
    p = os.path.join(base_dir, "config.json")
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    # 环境变量优先，缺失则回落到 config.json
    for env_name in API_KEY_ENVS:
        if os.environ.get(env_name, "").strip():
            cfg["api_key"] = os.environ[env_name].strip()
            break
    for key, env_names in CONFIG_ENVS.items():
        for env_name in env_names:
            if os.environ.get(env_name, "").strip():
                cfg[key] = os.environ[env_name].strip()
                break
    return cfg


def parse_srt(text):
    """把 SRT 文本解析成 [{idx, time, txt}, ...]。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = []
    for b in text.split("\n\n"):
        b = b.strip()
        if not b:
            continue
        lines = b.split("\n")
        ti = next((i for i, l in enumerate(lines) if "-->" in l), None)
        if ti is None:
            continue
        idx = lines[0].strip() if ti > 0 else ""
        time = lines[ti].strip()
        txt = "\n".join(lines[ti + 1:]).strip()
        blocks.append({"idx": idx, "time": time, "txt": txt})
    return blocks


def blocks_to_srt(blocks):
    out = []
    for i, b in enumerate(blocks, 1):
        out.append(str(i))
        out.append(b["time"])
        out.append(b["txt"])
        out.append("")
    return "\n".join(out).rstrip() + "\n"


class App:
    def __init__(self, root):
        self.root = root
        self.video_path = ""
        self.tier = tk.StringVar(value="mid")
        self.has_transcript = False
        self.srt_path = ""
        self.config = self.load_config()

        root.title("视频转文字工具")
        root.geometry("580x720")
        root.resizable(False, False)

        # 选择视频
        f1 = tk.LabelFrame(root, text="1. 选择视频", padx=10, pady=8)
        f1.pack(fill="x", padx=12, pady=6)
        tk.Button(f1, text="选择视频文件", command=self.pick_video).pack(side="left")
        self.video_label = tk.Label(f1, text="（未选择）", anchor="w", wraplength=380)
        self.video_label.pack(side="left", fill="x", padx=10)

        # 选择模型
        f2 = tk.LabelFrame(root, text="2. 选择模型（自行下载）", padx=10, pady=8)
        f2.pack(fill="x", padx=12, pady=6)
        for key in ("fast", "mid", "large"):
            tk.Radiobutton(
                f2, text=MODELS[key]["label"], variable=self.tier,
                value=key, command=self.on_tier_change
            ).pack(anchor="w")
        self.model_status = tk.Label(f2, text="", anchor="w", fg="#555555")
        self.model_status.pack(anchor="w", pady=(2, 0))
        tk.Button(f2, text="下载所选模型", command=self.download_model).pack(anchor="w", pady=(4, 0))

        # 开始转换
        f3 = tk.LabelFrame(root, text="3. 转换", padx=10, pady=8)
        f3.pack(fill="x", padx=12, pady=6)
        tk.Button(f3, text="开始转换", command=self.start, bg="#222222", fg="white").pack()

        # 完成后操作（先禁用，转写完成后启用）
        f3b = tk.Frame(f3)
        f3b.pack(pady=(6, 0))
        self.btn_open_file = tk.Button(
            f3b, text="打开文件", command=self.open_file, state="disabled", width=14
        )
        self.btn_open_file.pack(side="left", padx=(0, 8))
        self.btn_open_folder = tk.Button(
            f3b, text="打开文件位置", command=self.open_folder, state="disabled", width=14
        )
        self.btn_open_folder.pack(side="left")

        # AI 校对（去口水词）
        f5 = tk.LabelFrame(root, text="4. AI 校对（去口水词）", padx=10, pady=8)
        f5.pack(fill="x", padx=12, pady=6)
        tk.Label(
            f5, text="接入大模型，自动删除口水词、理顺语句、修正错别字。",
            anchor="w"
        ).pack(anchor="w")
        tk.Button(f5, text="API 设置", command=self.open_settings).pack(anchor="w", pady=(4, 0))
        self.proof_status = tk.Label(f5, text="", anchor="w", fg="#555555")
        self.proof_status.pack(anchor="w")
        self.btn_manual_proof = tk.Button(
            f5, text="立即 AI 校对当前字幕", command=self.manual_proofread, state="disabled"
        )
        self.btn_manual_proof.pack(anchor="w", pady=(4, 0))

        # 日志
        f4 = tk.LabelFrame(root, text="日志", padx=10, pady=8)
        f4.pack(fill="both", expand=True, padx=12, pady=6)
        self.log = tk.Text(f4, height=10, wrap="word", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True)
        self.log.insert("end", "就绪。请先选择视频与模型。\n")

        self.refresh_model_status()
        self.refresh_proof_status()

    # ---- 配置 ----
    def load_config(self):
        """实例方法：等价于模块级 load_config(app_dir())。"""
        return load_config(app_dir())

    def save_config(self):
        p = os.path.join(app_dir(), "config.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)

    def refresh_proof_status(self):
        if self.config.get("api_key"):
            mode = "开启（转写后自动校对）" if self.config.get("auto_proof") else "未开启自动校对"
            self.proof_status.config(
                text="状态：已配置 Key，%s" % mode, fg="#228822"
            )
        else:
            self.proof_status.config(
                text="状态：未配置 API Key，点「API 设置」填写或用环境变量 VIDEOTOTEXT_API_KEY",
                fg="#aa2222",
            )

    # ---- UI 辅助 ----
    def log_line(self, text):
        self.log.insert("end", text + "\n")
        self.log.see("end")

    def pick_video(self):
        path = filedialog.askopenfilename(
            title="选择视频/音频文件",
            filetypes=[("音视频", "*.mp4 *.mkv *.mov *.avi *.mp3 *.wav *.m4a *.flac"), ("全部", "*.*")],
        )
        if path:
            self.video_path = path
            self.video_label.config(text=os.path.basename(path))

    def on_tier_change(self):
        self.refresh_model_status()

    def refresh_model_status(self):
        key = self.tier.get()
        fpath = os.path.join(models_dir(), MODELS[key]["file"])
        if os.path.exists(fpath):
            self.model_status.config(text="状态：已下载 (%s)" % MODELS[key]["file"], fg="#228822")
        else:
            self.model_status.config(text="状态：未下载，需点击「下载所选模型」", fg="#aa2222")

    # ---- API 设置窗口 ----
    def open_settings(self):
        top = tk.Toplevel(self.root)
        top.title("AI 校对 API 设置")
        top.geometry("480x280")
        top.resizable(False, False)
        fields = [
            ("API 地址 (Base URL)", "base_url"),
            ("API Key", "api_key"),
            ("模型名", "model"),
        ]
        entries = {}
        for i, (label, key) in enumerate(fields):
            tk.Label(top, text=label).grid(row=i, column=0, sticky="w", padx=10, pady=6)
            e = tk.Entry(top, width=42)
            e.grid(row=i, column=1, padx=10, pady=6)
            e.insert(0, self.config.get(key, ""))
            if key == "api_key":
                e.config(show="*")
            entries[key] = e
        auto_var = tk.BooleanVar(value=bool(self.config.get("auto_proof", False)))
        tk.Checkbutton(top, text="转写完成后自动校对", variable=auto_var).grid(
            row=3, column=0, columnspan=2, sticky="w", padx=10, pady=6
        )

        def save():
            self.config["base_url"] = entries["base_url"].get().strip()
            self.config["api_key"] = entries["api_key"].get().strip()
            self.config["model"] = entries["model"].get().strip()
            self.config["auto_proof"] = auto_var.get()
            self.save_config()
            top.destroy()
            self.refresh_proof_status()

        tk.Button(top, text="保存", command=save, bg="#222222", fg="white").grid(
            row=4, column=0, columnspan=2, pady=12
        )

    # ---- 模型下载 ----
    def download_model(self):
        key = self.tier.get()
        info = MODELS[key]

        def worker():
            try:
                self.log_line("开始下载模型：%s" % info["label"])
                dest = os.path.join(models_dir(), info["file"])
                req = urllib.request.Request(info["url"], headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req) as resp:
                    total = int(resp.headers.get("Content-Length", 0))
                    downloaded = 0
                    chunk = 1024 * 1024
                    with open(dest, "wb") as f:
                        while True:
                            buf = resp.read(chunk)
                            if not buf:
                                break
                            f.write(buf)
                            downloaded += len(buf)
                            if total:
                                pct = downloaded * 100 // total
                                self.log_line("下载中... %d%%" % pct)
                self.log_line("模型下载完成：%s" % info["file"])
                self.refresh_model_status()
            except Exception as e:
                self.log_line("下载失败：%s" % e)
                messagebox.showerror("下载失败", str(e))

        threading.Thread(target=worker, daemon=True).start()

    # ---- 大模型调用 ----
    def call_llm(self, user_content):
        """调用 OpenAI 兼容接口，返回模型文本。"""
        cfg = self.config
        url = cfg["base_url"].rstrip("/") + "/chat/completions"
        data = {
            "model": cfg["model"],
            "messages": [
                {"role": "system", "content": PROOF_SYSTEM},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.2,
            "stream": False,
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + cfg["api_key"],
            },
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            obj = json.loads(resp.read().decode("utf-8"))
        return obj["choices"][0]["message"]["content"]

    def proofread_srt(self, srt_path):
        """读取 SRT，分块送大模型校对，写出 transcript_clean.srt。返回清洗后路径或 None。"""
        cfg = self.config
        if not cfg.get("api_key"):
            self.log_line(
                "未配置 API Key，跳过 AI 校对。请在「AI 校对」区点 API 设置，"
                "或设置环境变量 VIDEOTOTEXT_API_KEY。"
            )
            return None
        try:
            raw = open(srt_path, encoding="utf-8").read()
        except Exception as e:
            self.log_line("读取字幕失败：%s" % e)
            return None
        blocks = parse_srt(raw)
        if not blocks:
            self.log_line("字幕为空，无需校对。")
            return None

        chunk_size = 60
        out_blocks = []
        total = (len(blocks) + chunk_size - 1) // chunk_size
        for ci in range(total):
            chunk = blocks[ci * chunk_size:(ci + 1) * chunk_size]
            chunk_srt = blocks_to_srt(chunk)
            try:
                self.log_line("校对第 %d/%d 段..." % (ci + 1, total))
                resp = self.call_llm(chunk_srt)
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "ignore")[:200]
                self.log_line("校对请求失败（HTTP %s）：%s" % (e.code, detail))
                out_blocks.extend(chunk)
                continue
            except Exception as e:
                self.log_line("校对请求失败：%s" % e)
                out_blocks.extend(chunk)
                continue
            cleaned = parse_srt(resp)
            if len(cleaned) == len(chunk):
                out_blocks.extend(cleaned)
            else:
                self.log_line("第 %d 段返回格式异常，保留原稿。" % (ci + 1))
                out_blocks.extend(chunk)

        clean_path = os.path.join(app_dir(), "transcript_clean.srt")
        with open(clean_path, "w", encoding="utf-8") as f:
            f.write(blocks_to_srt(out_blocks))
        return clean_path

    # ---- 转换 ----
    def start(self):
        if not self.video_path:
            messagebox.showwarning("提示", "请先选择视频文件")
            return
        key = self.tier.get()
        info = MODELS[key]
        model_path = os.path.join(models_dir(), info["file"])
        if not os.path.exists(model_path):
            messagebox.showwarning("提示", "请先下载所选模型")
            return

        base = app_dir()
        exe1 = os.path.join(base, "1.exe")  # ffmpeg
        exe2 = os.path.join(base, "2.exe")  # whisper-cli
        for f in (exe1, exe2):
            if not os.path.exists(f):
                messagebox.showerror("缺少程序", "未找到 %s，请确认程序完整。" % f)
                return

        threading.Thread(target=self.run_pipeline, args=(model_path,), daemon=True).start()

    def run_pipeline(self, model_path):
        base = app_dir()
        exe1 = os.path.join(base, "1.exe")
        exe2 = os.path.join(base, "2.exe")
        video = self.video_path
        audio = os.path.join(base, "audio.wav")
        srt = os.path.join(base, "transcript.srt")

        try:
            # 1) 抽音频
            self.log_line("[1/2] 提取音频...")
            subprocess.run(
                [exe1, "-y", "-i", video, "-ar", "16000", "-ac", "1", audio],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            if not os.path.exists(audio):
                self.log_line("音频提取失败")
                return

            # 2) 识别（复制到纯英文临时目录，避免中文路径问题）
            tmp = os.path.join(os.environ.get("TEMP", base), "whisper_run")
            os.makedirs(tmp, exist_ok=True)
            shutil.copy(model_path, os.path.join(tmp, "model.bin"))
            shutil.copy(audio, os.path.join(tmp, "audio.wav"))
            for dep in ("2.exe", "whisper.dll", "ggml.dll", "ggml-base.dll", "ggml-cpu-haswell.dll"):
                src = os.path.join(base, dep)
                if os.path.exists(src):
                    shutil.copy(src, os.path.join(tmp, dep))
            whisper = os.path.join(tmp, "2.exe")

            self.log_line("[2/2] 识别中（可能需要几分钟）...")
            proc = subprocess.Popen(
                [whisper, "-m", "model.bin", "-f", "audio.wav", "-l", "zh",
                 "-t", "8", "-osrt", "-oj", "-of", "transcript"],
                cwd=tmp, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            )
            for line in proc.stdout:
                try:
                    self.log_line(line.decode("utf-8", "ignore").rstrip())
                except Exception:
                    pass
            proc.wait()

            srt_tmp = os.path.join(tmp, "transcript.srt")
            if not os.path.exists(srt_tmp):
                self.log_line("未生成字幕，识别可能失败，请查看上方日志。")
                return

            shutil.copy(srt_tmp, srt)
            self.log_line("完成！字幕已生成：%s" % srt)
            self.has_transcript = True
            self.root.after(0, lambda: self.btn_manual_proof.config(state="normal"))

            # 可选：AI 校对
            final = srt
            if self.config.get("auto_proof"):
                self.log_line("正在 AI 校对（去口水词）...")
                clean = self.proofread_srt(srt)
                if clean:
                    self.log_line("校对完成，已生成：%s" % clean)
                    final = clean
                else:
                    self.log_line("校对未产出，将打开原始字幕。")

            self.root.after(0, self.on_complete, final)
        except Exception as e:
            self.log_line("转换出错：%s" % e)
            messagebox.showerror("错误", str(e))
        finally:
            if os.path.exists(audio):
                try:
                    os.remove(audio)
                except Exception:
                    pass

    # ---- 校对按钮 ----
    def manual_proofread(self):
        srt = os.path.join(app_dir(), "transcript.srt")
        if not os.path.exists(srt):
            messagebox.showwarning("提示", "请先转写生成 transcript.srt")
            return
        if not self.config.get("api_key"):
            messagebox.showwarning("提示", "请先在「AI 校对」区点 API 设置，填写 Key")
            return
        threading.Thread(target=self._proofread_thread, args=(srt,), daemon=True).start()

    def _proofread_thread(self, srt):
        self.log_line("手动 AI 校对开始...")
        clean = self.proofread_srt(srt)
        if clean:
            self.log_line("校对完成：%s" % clean)
            self.root.after(0, self.on_complete, clean)
        else:
            self.root.after(
                0, lambda: messagebox.showinfo("提示", "校对未生成（可能未配置 Key 或请求失败）。")
            )

    # ---- 完成 / 打开 ----
    def open_file(self):
        """用系统默认程序打开生成的字幕文件。"""
        if getattr(self, "srt_path", ""):
            os.startfile(self.srt_path)

    def open_folder(self):
        """在资源管理器中打开字幕所在文件夹，并选中该文件。"""
        if getattr(self, "srt_path", ""):
            subprocess.run(["explorer", "/select,", self.srt_path])

    def on_complete(self, srt_path):
        """转写/校对完成后：记录路径、启用按钮、弹窗提示。"""
        self.srt_path = srt_path
        self.btn_open_file.config(state="normal")
        self.btn_open_folder.config(state="normal")
        self.log_line("提示：点击下方「打开文件」查看字幕，或「打开文件位置」进入所在文件夹。")
        messagebox.showinfo("完成", "字幕已生成：\n%s" % srt_path)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
