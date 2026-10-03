# -*- coding: utf-8 -*-
"""脱敏 / 自检脚本。

作用：
1) 校验 app.py 的 SRT 解析与回写往返一致（防止改动引入回归）；
2) 校验 load_config 的密钥优先级：环境变量 > config.json，且默认值为空；
3) 扫描本仓库所有文本文件，确认没有 `sk-` 形式的密钥或已填写的 api_key 残留；
4) 校验 .bat 换行符为 CRLF（LF 会让 cmd.exe 解析批处理出错）。

用法（在仓库根目录或任意位置均可）：
    python tests/test_sanitize.py
退出码 0 = 全部通过；1 = 有失败项。
"""
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
APP = os.path.join(REPO, "desktop-app", "app.py")

# 扫描时跳过的目录（体积大或与源码无关）
SKIP_DIRS = {".git", "__pycache__", "build", "dist", "models", "node_modules"}
# 只扫描这些文本后缀
TEXT_EXT = {".py", ".md", ".json", ".bat", ".txt", ".spec", ".gitignore", ".yml", ".yaml", ""}

SAMPLE_SRT = """1
00:00:00,000 --> 00:00:02,500
嗯 那个 大家好

2
00:00:02,500 --> 00:00:05,000
今天讲一下 这个 问题

3
00:00:05,000 --> 00:00:08,000
谢谢
"""

failures = []


def check(cond, msg):
    if cond:
        print("  [OK]   %s" % msg)
    else:
        print("  [FAIL] %s" % msg)
        failures.append(msg)


def load_app_module():
    """以模块方式加载 desktop-app/app.py（导入时不会启动 GUI）。"""
    spec = importlib.util.spec_from_file_location("vtt_app", APP)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_srt_roundtrip(mod):
    print("\n[1] SRT 解析 / 回写往返")
    blocks = mod.parse_srt(SAMPLE_SRT)
    check(len(blocks) == 3, "解析出 3 个字幕块，实际 %d" % len(blocks))
    check(blocks[0]["txt"] == "嗯 那个 大家好", "首块文本正确")
    check(blocks[2]["time"] == "00:00:05,000 --> 00:00:08,000", "时间码保留正确")

    out = mod.blocks_to_srt(blocks)
    check(out.startswith("1\n00:00:00,000 --> 00:00:02,500\n"), "回写以序号+时间码开头")
    check(mod.blocks_to_srt(mod.parse_srt(out)) == out, "二次往返结果稳定")

    check(mod.parse_srt("") == [], "空文本解析为空列表")
    check(mod.parse_srt("没有时间码的垃圾文本") == [], "无时间码文本被忽略")


def test_key_priority(mod):
    print("\n[2] API Key 来源与优先级")
    env_name = "VIDEOTOTEXT_API_KEY"
    saved = os.environ.get(env_name)
    tmpdir = tempfile.mkdtemp(prefix="vtt_cfg_")
    try:
        os.environ.pop(env_name, None)
        cfg = mod.load_config(tmpdir)
        check(cfg["api_key"] == "", "无环境变量、无 config.json 时 api_key 为空（无硬编码密钥）")
        check(cfg["base_url"].startswith("https://"), "默认 base_url 存在")

        with io.open(os.path.join(tmpdir, "config.json"), "w", encoding="utf-8") as f:
            json.dump({"api_key": "from-config-file", "model": "m-from-file"}, f)
        cfg = mod.load_config(tmpdir)
        check(cfg["api_key"] == "from-config-file", "config.json 可提供 api_key")
        check(cfg["model"] == "m-from-file", "config.json 的 model 生效")

        os.environ[env_name] = "from-env-var"
        cfg = mod.load_config(tmpdir)
        check(cfg["api_key"] == "from-env-var", "环境变量优先于 config.json")

        os.environ.pop(env_name, None)
        os.environ["DEEPSEEK_API_KEY"] = "from-deepseek-env"
        cfg = mod.load_config(tmpdir)
        check(cfg["api_key"] == "from-deepseek-env", "兼容 DEEPSEEK_API_KEY")
        os.environ.pop("DEEPSEEK_API_KEY", None)

        os.environ["VIDEOTOTEXT_BASE_URL"] = "https://example.invalid/v1"
        cfg = mod.load_config(tmpdir)
        check(cfg["base_url"] == "https://example.invalid/v1", "VIDEOTOTEXT_BASE_URL 覆盖配置文件")
        os.environ.pop("VIDEOTOTEXT_BASE_URL", None)

        check(mod.API_KEY_ENVS[0] == env_name, "优先读取 VIDEOTOTEXT_API_KEY")
    finally:
        if saved is None:
            os.environ.pop(env_name, None)
        else:
            os.environ[env_name] = saved
        for name in os.listdir(tmpdir):
            os.remove(os.path.join(tmpdir, name))
        os.rmdir(tmpdir)


def iter_repo_text_files():
    for root, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            ext = os.path.splitext(fn)[1].lower()
            if ext in TEXT_EXT:
                yield os.path.join(root, fn)


def test_no_secrets_on_disk():
    print("\n[3] 仓库文件密钥残留扫描")
    key_pat = re.compile(r"sk-[A-Za-z0-9_\-]{16,}")
    filled_pat = re.compile(r'"api_key"\s*:\s*"([^"]{8,})"')
    hits = []
    scanned = 0
    for path in iter_repo_text_files():
        if os.path.abspath(path).startswith(HERE):
            continue  # 跳过测试自身（里面必然含有匹配串的正则）
        try:
            with io.open(path, encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except OSError:
            continue
        scanned += 1
        for m in key_pat.finditer(text):
            hits.append("%s: sk-...(%d chars)" % (os.path.relpath(path, REPO), len(m.group(0))))
        for m in filled_pat.finditer(text):
            if m.group(1).strip():
                hits.append("%s: api_key 已填写" % os.path.relpath(path, REPO))

    check(scanned > 0, "扫描了 %d 个文本文件" % scanned)
    check(not hits, "未发现密钥残留%s" % ("" if not hits else "：" + "; ".join(hits)))
    check(not os.path.exists(os.path.join(REPO, "config.json")), "仓库根目录没有 config.json（只有 config.example.json）")
    check(not os.path.exists(os.path.join(REPO, "desktop-app", "config.json")), "desktop-app 目录没有 config.json")

    gi = ""
    gi_path = os.path.join(REPO, ".gitignore")
    if os.path.exists(gi_path):
        with io.open(gi_path, encoding="utf-8") as f:
            gi = f.read()
    check("config.json" in gi, ".gitignore 忽略 config.json")


def test_bat_crlf():
    """Windows 批处理必须 CRLF。校验工作区与 git 对象里的内容都是 CRLF。

    回归背景：LF 换行的 .bat 会让 cmd.exe 解析错乱——4.bat 选 1（tiny）
    却报 'm_mid.bin not found'，新用户会以为工具坏了。
    """
    print("\n[4] 批处理换行符（必须 CRLF）")
    bats = sorted(f for f in os.listdir(REPO) if f.lower().endswith((".bat", ".cmd")))
    if not bats:
        check(False, "仓库根目录找不到 .bat 文件")
        return
    for name in bats:
        data = open(os.path.join(REPO, name), "rb").read()
        crlf = data.count(b"\r\n")
        lf_only = data.count(b"\n") - crlf
        check(crlf > 0 and lf_only == 0,
              "%s 工作区为 CRLF（CRLF=%d, LF-only=%d）" % (name, crlf, lf_only))

    # git 对象里的版本决定 clone / Download ZIP 拿到什么，必须也是 CRLF
    if os.path.isdir(os.path.join(REPO, ".git")):
        for name in bats:
            r = subprocess.run(["git", "show", ":" + name], cwd=REPO,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if r.returncode != 0:
                print("  [SKIP] %s 尚未纳入 git 索引" % name)
                continue
            data = r.stdout
            crlf = data.count(b"\r\n")
            lf_only = data.count(b"\n") - crlf
            check(crlf > 0 and lf_only == 0,
                  "git 对象里 %s 也是 CRLF（CRLF=%d, LF-only=%d）" % (name, crlf, lf_only))


def test_gui_smoke(mod):
    """真正把窗口建起来再关掉，确认改动没破坏 GUI 初始化。无图形环境时跳过。"""
    print("\n[5] GUI 冒烟测试")
    try:
        import tkinter as tk
    except ImportError:
        print("  [SKIP] 当前 Python 没有 tkinter")
        return
    try:
        root = tk.Tk()
    except Exception as e:
        print("  [SKIP] 无法创建窗口（无图形环境）：%s" % e)
        return
    try:
        root.withdraw()
        app = mod.App(root)
        root.update()
        check(app.config.get("base_url", "").startswith("https://"), "配置加载正常")
        check(app.tier.get() == "mid", "默认档位为 mid")
        check(app.proof_status.cget("text") != "", "AI 校对状态栏有提示文本")
        status = app.proof_status.cget("text")
        check("未配置" in status or "已配置" in status, "状态栏文案符合预期")
        root.destroy()
    except Exception as e:
        root.destroy()
        check(False, "GUI 初始化抛异常：%r" % (e,))


def main():
    print("仓库位置：%s" % REPO)
    mod = load_app_module()
    test_srt_roundtrip(mod)
    test_key_priority(mod)
    test_no_secrets_on_disk()
    test_bat_crlf()
    test_gui_smoke(mod)

    print("\n" + "=" * 46)
    if failures:
        print("失败 %d 项：" % len(failures))
        for f in failures:
            print("  - %s" % f)
        return 1
    print("全部通过：脱敏与功能自检 OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
