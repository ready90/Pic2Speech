# -*- coding: utf-8 -*-
"""语音合成：edge-tts（微软神经网络语音，免费、无需 API Key）

输出 MP3 + 同步 SRT 字幕。
分块、字幕拼装等逻辑与电脑版 core.py 完全一致（那套已调通并修过两个 bug）。

★ 2026-09-21 多语言实测后加固：
   个别语言（实测印地语出现过）的 WordBoundary 时间戳会整体偏大百倍，
   导致 SRT 显示成 12 分钟、而音频其实只有 5 秒。这里用音频体积反推
   真实时长做校正 —— 音频本身不受影响，只是让字幕/进度条别再乱跳。
"""
import asyncio
import os
import re
import threading
import time

import edge_tts

_SUB_PUNCT = "。！？；，、,.!?;…:：'\"“”‘’()【】（）"
_MAX_LEN = 1200

# edge-tts 输出 24kHz/48kbps 单声道 MP3 ≈ 6.2 KB/s（各语言实测一致），
# 用它由音频体积反推"这段音频大概多长"，用于校正异常的 SRT 时间轴。
_BYTES_PER_SEC = 6200.0


# --------------------------------------------------------------------------- #
# 文本清洗 + 切分
# --------------------------------------------------------------------------- #
def clean_for_speech(text):
    """去掉模型稿里可能残留的 Markdown 符号，让朗读更自然"""
    if not text:
        return ""
    text = re.sub(r"\[([^\]\n]*)\]\([^)\n]*\)", r"\1", text)          # 链接
    text = re.sub(r"[#*_`>|~]", "", text)                              # 常见 md 符号
    text = re.sub(r"^\s*(?:[-•·]|\d+[.、)])\s*", "", text, flags=re.M)  # 行首编号
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def split_text(text, max_len=_MAX_LEN):
    """超长文本按句切分，避免单次合成超限"""
    text = (text or "").strip()
    if len(text) <= max_len:
        return [text] if text else []
    units = re.split(r"(?<=[。！？；.!?;])\s*|\n+", text)
    parts, cur = [], ""
    for u in units:
        u = u.strip()
        if not u:
            continue
        if cur and len(cur) + len(u) > max_len:
            parts.append(cur)
            cur = u
        else:
            cur += u
    if cur:
        parts.append(cur)
    return parts or [text]


# --------------------------------------------------------------------------- #
# 字幕时间轴
# --------------------------------------------------------------------------- #
def _to_sec(v):
    """edge-tts 边界事件的时间单位随版本变化，三种情况都兼容"""
    v = float(v or 0)
    if v < 1e6:
        return v / 1e3        # 毫秒
    if v < 1e10:
        return v / 1e7        # 100 纳秒（edge-tts 实际使用）
    return v / 1e9            # 纳秒


def _fmt_ts(sec):
    h = int(sec // 3600)
    m = int(sec % 3600 // 60)
    s = int(sec % 60)
    ms = int(round((sec - int(sec)) * 1000))
    if ms >= 1000:
        ms = 0
        s += 1
    if s >= 60:
        s -= 60
        m += 1
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def _glue_word(buf, w):
    """中文之间不加空格，英文词之间加空格，标点紧跟"""
    if not buf:
        return w
    if w in _SUB_PUNCT:
        return buf + w
    p = buf[-1]
    pcjk = 0x4E00 <= ord(p) <= 0x9FFF
    wcjk = w and 0x4E00 <= ord(w[0]) <= 0x9FFF
    if pcjk and wcjk:
        return buf + w
    if p.isalnum() and w[0].isalnum():
        return buf + " " + w
    return buf + w


def _rescale_subs(subs, nbytes):
    """时间轴异常时按音频真实体积整体缩放。

    某些语言的时间戳会整体偏大百倍（出现 12 分钟的字幕配 5 秒音频），
    这里用体积反推时长，偏差超过 2.5 倍才动手，正常情况原样返回。
    """
    if not subs:
        return subs
    guess = (nbytes or 0) / _BYTES_PER_SEC
    if guess <= 0:
        return subs
    last = subs[-1][1]
    if last <= 0:
        return subs
    if last > guess * 2.5 or last < guess * 0.2:
        k = guess / last
        return [(s * k, e * k, t) for s, e, t in subs]
    return subs


def _write_srt(subs, srt_path):
    lines = []
    for i, (s, e, t) in enumerate(subs, 1):
        lines.append("%d\n%s --> %s\n%s\n" % (i, _fmt_ts(s), _fmt_ts(e), t))
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# --------------------------------------------------------------------------- #
# 合成
# --------------------------------------------------------------------------- #
async def _synth_one(text, voice, rate, fp):
    """合成一段音频写入 fp，返回该段相对时间轴的字幕 [(start, end, phrase)]"""
    try:
        communicate = edge_tts.Communicate(text, voice=voice,
                                           rate="%+d%%" % rate,
                                           boundary="WordBoundary")
        words = []
        with open(fp, "wb") as f:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    st = _to_sec(chunk.get("offset"))
                    du = _to_sec(chunk.get("duration"))
                    words.append((st, st + du, chunk.get("text", "")))
    except Exception as e:                                    # noqa: BLE001
        msg = str(e)
        if "403" in msg or "Invalid response status" in msg:
            raise RuntimeError(
                "语音服务拒绝了请求（403）：最常见原因是手机系统时间不准，"
                "请在系统设置中开启“自动设置时间”后重试。原始信息：" + msg[:160])
        if "getaddrinfo" in msg or "Name or service" in msg or "timed out" in msg:
            raise RuntimeError("无法连接语音服务，请检查手机网络后重试。原始信息："
                               + msg[:160])
        raise RuntimeError("语音合成失败：" + msg[:200])

    subs = []
    buf, s0, e0, toks = "", None, None, 0
    for st, en, w in words:
        if s0 is None:
            s0 = st
        e0 = en
        buf = _glue_word(buf, w)
        toks += 1
        if (w and w[-1] in _SUB_PUNCT) or toks >= 16 or len(buf) >= 80:
            if buf.strip():
                subs.append((s0, e0, buf.strip()))
            buf, s0, toks = "", None, 0
    if buf.strip():
        subs.append((s0 if s0 is not None else 0.0,
                     e0 if e0 is not None else 0.0, buf.strip()))
    return subs


async def _run_all(chunks, voice, rate, tmp_dir):
    audio = bytearray()
    subs, offset = [], 0.0
    for i, part in enumerate(chunks):
        tmp = os.path.join(tmp_dir, "_tmp_%d.mp3" % i)
        parts = await _synth_one(part, voice, rate, tmp)
        with open(tmp, "rb") as f:
            audio += f.read()
        try:
            os.remove(tmp)
        except OSError:
            pass
        for s, e, t in parts:
            subs.append((s + offset, e + offset, t))
        if parts:
            offset += parts[-1][1]
    return bytes(audio), subs


# 安卓上没有现成的事件循环，这里自己维护一个，避免反复创建开销
_loop = None
_loop_lock = threading.Lock()


def _run_async(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        running = False
    else:
        running = True

    if running:
        # 调用方已经在事件循环里，另起线程承载
        box = {}

        def _worker():
            box["r"] = _run_async(coro)

        t = threading.Thread(target=_worker)
        t.start()
        t.join()
        return box["r"]

    global _loop
    with _loop_lock:
        if _loop is None or _loop.is_closed():
            _loop = asyncio.new_event_loop()
            asyncio.set_event_loop(_loop)
        return _loop.run_until_complete(coro)


_seq = 0
_seq_lock = threading.Lock()


def synthesize(text, voice, rate, out_dir, tag="audio"):
    """文本 -> (MP3 路径, SRT 路径或 None)"""
    global _seq
    text = clean_for_speech(text)
    if not text:
        raise RuntimeError("要朗读的文本为空。")

    out_dir = str(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    chunks = split_text(text)

    audio, subs = _run_async(_run_all(chunks, voice, int(rate), out_dir))
    subs = _rescale_subs(subs, len(audio))

    with _seq_lock:
        _seq += 1
        seq = _seq
    base = "%s_%s_%02d" % (tag, time.strftime("%Y%m%d_%H%M%S"), seq)

    mp3_path = os.path.join(out_dir, base + ".mp3")
    with open(mp3_path, "wb") as f:
        f.write(audio)

    srt_path = None
    if subs:
        srt_path = os.path.join(out_dir, base + ".srt")
        _write_srt(subs, srt_path)

    return mp3_path, srt_path
