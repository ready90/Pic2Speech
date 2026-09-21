# -*- coding: utf-8 -*-
"""Kotlin 调用的唯一入口。

约定：所有函数都返回 **JSON 字符串**，绝不把异常抛到 Java 侧 ——
出错时返回 {"ok": false, "error": "中文提示"}，界面直接显示即可。

★ 2026-09-21 修复「翻译朗读失败」：
   根因是 edge-tts 用「非中文音色」念中文文本时会硬报
   `No audio was received. Please verify that your parameters are correct.`
   而 GLM-4V-Flash 又经常不按要求翻译、直接吐回中文原文 ⇒ 两者一撞就报错。
   这里加第三道防线：合成前让音色与文本语言对得上；万一仍失败，
   自动逐级换音色重试，而不是直接把报错甩给用户。
"""
import json
import os
import re

from . import config, tts, vision

_VOICES_PATH = os.path.join(os.path.dirname(__file__), "voices.json")

_cache = {}

FALLBACK_LANG = {"code": "en-US", "label": "English",
                 "prompt_name": "English", "voices": []}


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
    return items[0] if items else dict(FALLBACK_LANG)


def _default_voice(code):
    voices = _find_lang(code).get("voices", [])
    if not voices:
        return "en-US-AriaNeural"
    for v in voices:
        if v.get("gender") == "女":
            return v["id"]
    return voices[0]["id"]


def _multilingual_voice(lang):
    """该语言里带 Multilingual 的音色 —— 它能念任意语言，是最好的兜底"""
    for v in (lang or {}).get("voices", []):
        if "Multilingual" in str(v.get("id", "")):
            return v["id"]
    return ""


def detect_lang(text):
    """按字符粗略判断文本语言（朗读原文时用来自动挑音色）"""
    if vision.has_cjk(text):
        return "zh-CN"
    if re.search(r"[A-Za-z]", text or ""):
        return "en-US"
    return None


_SCRIPT_LANG = {"zh": "zh-CN", "ja": "ja-JP", "ko": "ko-KR"}
_SCRIPT_NAME = {"zh": "中文", "ja": "日文", "ko": "韩文"}


def _voice_lang(voice):
    """从音色 id 取语言前缀：zh-CN-XiaoxiaoNeural → zh"""
    return str(voice or "").split("-")[0].lower()


def _pick_voice(mode, text, voice, lang):
    """★ 关键：让音色与文本实际用的文字对得上。

    edge-tts 的音色**不能**跨语系乱读：拿法语音色念中文会直接报
    `No audio was received`。所以文本用的是中/日/韩文字而音色不同语系时，
    提前换掉，别等报错。带 Multilingual 的音色能读任意语言，直接放行。
    """
    voice = str(voice or "")
    sc = vision.script_of(text)
    if sc not in _SCRIPT_LANG:                 # 拉丁字母等，绝大多数音色都能读
        return voice, ""
    if _voice_lang(voice) == sc or "Multilingual" in voice:
        return voice, ""
    return (_default_voice(_SCRIPT_LANG[sc]),
            "文本为%s，已自动切换对应音色" % _SCRIPT_NAME[sc])


def _fallback_voices(text, voice, lang):
    """合成报错后的换音色候选（按优先级）"""
    seen = {str(voice or "")}
    cands = []
    ml = _multilingual_voice(lang)
    if ml:
        cands.append((ml, "已自动改用多语音色"))
    sc = vision.script_of(text)
    if sc in _SCRIPT_LANG:
        cands.append((_default_voice(_SCRIPT_LANG[sc]),
                      "已自动改用%s音色朗读原文" % _SCRIPT_NAME[sc]))
    else:
        cands.append((_default_voice("en-US"), "已自动改用英文音色"))
    cands.append((_default_voice(lang.get("code")), "已改用该语言默认音色"))
    out = []
    for v, note in cands:
        if v and v not in seen:
            seen.add(v)
            out.append((v, note))
    return out


def _synthesize_safe(text, voice, rate, out_dir, tag, lang):
    """合成；万一报 No audio was received 就逐级换音色重试。

    返回 (mp3, srt, 实际使用的音色, 补充说明)
    """
    try:
        mp3, srt = tts.synthesize(text, voice, rate, out_dir, tag)
        return mp3, srt, voice, ""
    except Exception as e:                                    # noqa: BLE001
        if "No audio was received" not in str(e):
            raise
        last = e
        for v2, note in _fallback_voices(text, voice, lang):
            try:
                mp3, srt = tts.synthesize(text, v2, rate, out_dir, tag)
                return mp3, srt, v2, note
            except Exception as e2:                           # noqa: BLE001
                last = e2
                continue
        raise RuntimeError(
            "语音合成失败：所选音色读不出这段文字（通常是音色语言与文字语言不一致）。"
            "请改选与目标语言一致的音色，或选带 Multilingual 的音色后重试。原始信息："
            + str(last)[:160])


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
        lc = str(lang.get("code") or lang_code or "en-US")
        lang_name = lang.get("prompt_name") or lang.get("label") or "English"

        text = vision.understand(paths, str(mode), lang_name,
                                 str(detail), key, lc)
        if not text:
            return _err("模型没有返回内容，请重试")

        notes = []

        # ★ 第二道防线：模型没按要求翻译成目标语言（仍是中文原文）→ 用文本模型补译
        if (str(mode) in (vision.MODE_TRANS, vision.MODE_TALK)
                and vision.needs_translate(text, lc)):
            try:
                fixed = vision.translate_text(text, lang_name, key,
                                              forbid_cjk=True)
                if fixed and not vision.needs_translate(fixed, lc):
                    text = fixed
                    notes.append("视觉模型未按目标语言输出，已用翻译模型补译")
            except Exception:                                 # noqa: BLE001
                pass        # 补译失败不致命，下面还有音色兜底

        use_voice, vnote = _pick_voice(str(mode), text, str(voice), lang)
        if vnote:
            notes.append(vnote)

        tag = "pic2speech_" + lc.replace("-", "")
        mp3, srt, use_voice, snote = _synthesize_safe(
            text, use_voice, int(rate), out_dir, tag, lang)
        if snote:
            notes.append(snote)

        return _ok(text, mp3, srt, "；".join(notes), use_voice)
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
