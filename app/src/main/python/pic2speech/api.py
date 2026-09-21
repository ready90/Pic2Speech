# -*- coding: utf-8 -*-
"""Kotlin 调用的唯一入口。

约定：所有函数都返回 **JSON 字符串**，绝不把异常抛到 Java 侧 ——
出错时返回 {"ok": false, "error": "中文提示"}，界面直接显示即可。
"""
import json
import os
import re

from . import config, tts, vision

_VOICES_PATH = os.path.join(os.path.dirname(__file__), "voices.json")

_cache = {}


def voices_json():
    """内置音色表（原样返回 JSON 文本，供界面填充语言/音色下拉框）"""
    with open(_VOICES_PATH, encoding="utf-8") as f:
        return f.read()


def default_key():
    """App 内置的默认 API Key（界面启动时预填输入框用）。

    内置 Key 由 CI 从仓库 Secret 生成到 _secret.py，不进代码仓库；
    没有配置时返回 builtin=False，界面会提示手动填写。
    """
    try:
        return json.dumps({
            "ok": True,
            "key": config.DEFAULT_API_KEY,
            "masked": config.masked(),
            "builtin": config.has_builtin_key(),
        }, ensure_ascii=False)
    except Exception as e:                                    # noqa: BLE001
        return _err(e)


def _load_voices():
    if "data" not in _cache:
        _cache["data"] = json.loads(voices_json())
    return _cache["data"]


def _languages():
    return _load_voices().get("languages", [])


def _find_lang(code):
    items = _languages()
    for item in items:
        if item.get("code") == code:
            return item
    return items[0] if items else {"code": "en-US", "label": "English",
                                   "prompt_name": "English", "voices": []}


def _default_voice(code):
    voices = _find_lang(code).get("voices", [])
    if not voices:
        return "en-US-AriaNeural"
    for v in voices:
        if v.get("gender") == "女":
            return v["id"]
    return voices[0]["id"]


def detect_lang(text):
    """按字符占比粗略判断文本语言（朗读原文时用来自动挑音色）"""
    cjk = len(re.findall(r"[\u4e00-\u9fff\u3400-\u4dbf]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if cjk + latin == 0:
        return None
    return "zh-CN" if cjk * 3 >= latin else "en-US"


def _pick_voice(mode, text, voice, lang):
    """朗读原文模式：文中语言与所选音色不一致时，自动换成同语言默认音色"""
    if mode != vision.MODE_READ:
        return voice, ""
    detected = detect_lang(text)
    if not detected or detected == lang.get("code"):
        return voice, ""
    if not str(voice).startswith(detected):
        return _default_voice(detected), "原文语言为 %s，已自动切换音色" % detected
    return voice, ""


def _err(msg):
    return json.dumps({"ok": False, "error": str(msg)}, ensure_ascii=False)


def _ok(text, mp3, srt, note="", voice=""):
    return json.dumps({
        "ok": True,
        "text": text,
        "mp3": mp3,
        "srt": srt or "",
        "note": note,
        "voice": voice,
    }, ensure_ascii=False)


# --------------------------------------------------------------------------- #
# 对外接口
# --------------------------------------------------------------------------- #
def generate(image_paths, lang_code, voice, rate, mode, detail, api_key, out_dir):
    """完整流程：图片理解 -> 语音合成"""
    try:
        paths = [str(p) for p in image_paths]
        if not paths:
            return _err("没有收到图片")

        key = str(api_key or "").strip()
        if len(key) < 20:
            # 界面没填就退回 App 内置的 Key
            key = config.DEFAULT_API_KEY
        if len(key) < 20:
            return _err("请先填写智谱 API Key（免费申请 open.bigmodel.cn）")

        lang = _find_lang(str(lang_code))
        lang_name = lang.get("prompt_name") or lang.get("label") or "English"

        text = vision.understand(paths, str(mode), lang_name,
                                 str(detail), key)
        if not text:
            return _err("模型没有返回内容，请重试")

        use_voice, note = _pick_voice(str(mode), text, str(voice), lang)
        mp3, srt = tts.synthesize(text, use_voice, int(rate), out_dir,
                                  tag="pic2speech_" + str(lang_code).replace("-", ""))
        return _ok(text, mp3, srt, note, use_voice)
    except Exception as e:                                    # noqa: BLE001
        return _err(e)


def resynth(text, voice, rate, out_dir):
    """用界面上编辑过的文字重新合成（不重新识别图片）"""
    try:
        text = str(text or "").strip()
        if not text:
            return _err("文字稿为空，无法合成")
        mp3, srt = tts.synthesize(text, str(voice), int(rate), out_dir,
                                  tag="resynth")
        return _ok(text, mp3, srt, "", str(voice))
    except Exception as e:                                    # noqa: BLE001
        return _err(e)
