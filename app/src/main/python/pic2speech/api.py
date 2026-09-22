# -*- coding: utf-8 -*-
"""Kotlin 调用的唯一入口。

约定：所有函数都返回 **JSON 字符串**，绝不把异常抛到 Java 侧 ——
出错时返回 {"ok": false, "error": "中文提示"}，界面直接显示即可。

★ 2026-09-21 第一轮修复「翻译朗读失败」：
   根因是 edge-tts 用「非中文音色」念中文文本时可能硬报
   `No audio was received. Please verify that your parameters are correct.`
   而 GLM-4V-Flash 又经常不按要求翻译、直接吐回中文原文 ⇒ 两者一撞就报错。

★ 2026-09-21 第二轮修复（多语言实测 26 种语言后发现的新问题）：
   1) **静默空音频**：音色与文字不匹配时，edge-tts **不一定报错** ——
      实测英文音色念阿拉伯文/泰文/俄文会「成功」产出恒定 0.9 秒 / 10.7KB 的静音；
      念希腊文则按拉丁字母硬读出 3 倍长的错音（46.6s vs 正常 12.9s）。
      旧逻辑只捕获异常，这两种都会静默放过 ⇒ 现在合成后校验音频体积/时长。
   2) **翻译服从率低**：26 种语言里 5 种要靠补译纠正、1 种（俄语）补译也失败。
      ⇒ 「翻译朗读」改为：视觉模型只 OCR 原文 → 文本模型 glm-4-flash 翻译。
   3) 音色匹配从"只看中日韩"扩展到全部文字系统（西里尔/阿拉伯/天城文/泰文…）。
"""
import json
import os
import re

from . import config, tts, vision

_VOICES_PATH = os.path.join(os.path.dirname(__file__), "voices.json")

_cache = {}

FALLBACK_LANG = {"code": "en-US", "label": "English",
                 "prompt_name": "English", "voices": []}

# edge-tts 输出 24kHz/48kbps 单声道 MP3 ≈ 6.2 KB/s（实测各语言一致）
_BYTES_PER_SEC = 6200.0

# 音色读不出文字时，edge-tts 静默产出的"空音频"恒定在这个量级
_EMPTY_AUDIO_BYTES = 13000

# 这些属于"重试也没用"的网络类错误，直接抛出，不要逐个换音色浪费时间
_FATAL_NET = ("无法连接", "getaddrinfo", "Name or service", "timed out",
              "timeout", "403", "SSL", "Connection", "ProxyError")


def voices_json():
    """内置音色表（原样返回 JSON 文本，供界面填充语言/音色下拉框）"""
    with open(_VOICES_PATH, encoding="utf-8") as f:
        return f.read()


def default_key():
    """App 里是否内置了默认 API Key（界面启动时预填输入框用）。

    自 v1.6 起**恒为「未内置」**：Key 改由用户在界面上自行粘贴，只存手机本机。
    （早期做法是 CI 从仓库 Secret 生成 _secret.py 打进包，但 APK 内的任何凭据
      都能被零门槛提取出来，那条路已废弃，详见 README「安全设计」。）
    """
    try:
        return json.dumps({
            "ok": config.has_builtin_key(),
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


def _voice_for_script(script):
    """找一把"能读这套文字"的音色：在音色表里挑语言前缀匹配的第一种语言"""
    wants = vision.SCRIPT_VOICE_PREFIXES.get(script, ())
    if not wants:
        return ""
    for L in _languages():
        code = str(L.get("code") or "")
        if code.split("-")[0].lower() in wants:
            return _default_voice(code)
    return ""


def detect_lang(text):
    """按字符粗略判断文本语言（朗读原文时用来自动挑音色）"""
    sc = vision.script_of(text)
    if sc in ("zh", "ja", "ko"):
        return {"zh": "zh-CN", "ja": "ja-JP", "ko": "ko-KR"}[sc]
    if sc == "latin":
        return "en-US"
    return None


def _voice_lang(voice):
    """从音色 id 取语言前缀：zh-CN-XiaoxiaoNeural → zh"""
    return str(voice or "").split("-")[0].lower()


def _pick_voice(mode, text, voice, lang):
    """★ 关键：让音色与文本实际用的文字对得上。

    edge-tts 的音色**不能**跨文字系统乱读，而且不匹配时常常**不报错**
    （静默空音频）。所以合成前先检查：文本是某套文字、音色却不是那套文字
    的音色 ⇒ 提前换成匹配的。带 Multilingual 的音色能读任意语言，直接放行。
    """
    voice = str(voice or "")
    sc = vision.script_of(text)
    if sc in ("", "latin"):                    # 拉丁字母，绝大多数音色都能读
        return voice, ""
    if "Multilingual" in voice:
        return voice, ""
    if _voice_lang(voice) in vision.SCRIPT_VOICE_PREFIXES.get(sc, ()):
        return voice, ""

    v2 = _voice_for_script(sc)
    if v2 and v2 != voice:
        return v2, "文本为%s，已自动切换对应音色" % vision.SCRIPT_NAME.get(sc, sc)
    return voice, ""


def _fallback_voices(text, voice, lang):
    """合成失败后的换音色候选（按优先级）

    顺序很重要：以前把"英文音色"排在"目标语言默认音色"之前，
    结果英文音色读阿拉伯文/泰文只能产出空音频、白试一轮。
    """
    seen = {str(voice or "")}
    cands = []

    ml = _multilingual_voice(lang)                      # 1. 多语音色（万能）
    if ml:
        cands.append((ml, "已自动改用多语音色"))

    sc = vision.script_of(text)                         # 2. 与文字匹配的音色
    if sc in vision.SCRIPT_VOICE_PREFIXES:
        v2 = _voice_for_script(sc)
        if v2:
            cands.append((v2, "已自动改用%s音色"
                          % vision.SCRIPT_NAME.get(sc, sc)))

    if lang.get("code"):                                # 3. 目标语言自己的音色
        cands.append((_default_voice(lang.get("code")), "已改用该语言默认音色"))

    cands.append((_default_voice("en-US"), "已自动改用英文音色"))   # 4. 兜底

    out = []
    for v, note in cands:
        if v and v not in seen:
            seen.add(v)
            out.append((v, note))
    return out


def _audio_size_ok(size, n):
    """按"音频体积 vs 文字个数"判断是否静默失败。

    edge-tts 读不出文字时不会报错，只会产出恒定 ≈0.9s / 10.7KB 的静音；
    反过来把不认识的字母表硬按拉丁读，会长出正常 3 倍的长度。
    两条都拦下，交给上层换音色重试。
    """
    if n <= 0:
        return True
    if size <= 0:
        return False
    if size < _EMPTY_AUDIO_BYTES and n >= 6:            # 空音频
        return False
    if n >= 12 and size / float(n) < 320.0:             # 明显偏小
        return False
    if n >= 20 and size / float(n) > 4200.0:            # 硬按错误字母表乱念
        return False
    return True


def _audio_ok(mp3_path, text):
    """合成结果是不是"静默失败"（读文件大小后判断）"""
    n = len(re.sub(r"\s+", "", text or ""))
    try:
        size = os.path.getsize(mp3_path)
    except OSError:
        return False
    return _audio_size_ok(size, n)


def _synthesize_safe(text, voice, rate, out_dir, tag, lang):
    """合成；读不出就逐级换音色重试。

    返回 (mp3, srt, 实际使用的音色, 补充说明)
    """
    chain = [(voice, "")] + _fallback_voices(text, voice, lang)
    last = None
    for v, note in chain:
        if not v:
            continue
        try:
            mp3, srt = tts.synthesize(text, v, rate, out_dir, tag)
        except Exception as e:                            # noqa: BLE001
            if any(k in str(e) for k in _FATAL_NET):
                raise                                     # 网络问题，换音色没用
            last = e
            continue
        if _audio_ok(mp3, text):
            return mp3, srt, v, note
        last = RuntimeError("音色 %s 读不出这段文字（产出了空音频）" % v)
        try:
            os.remove(mp3)                                # 空音频别留在手机里
        except OSError:
            pass

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
        mode = str(mode)
        notes = []

        if mode == vision.MODE_TRANS:
            text = _translate_flow(paths, lang_name, detail, key, lc, notes)
        else:
            text = vision.understand(paths, mode, lang_name,
                                     str(detail), key, lc)
            # 视觉模型没按要求用目标语言输出（含"看图解说"）→ 补译
            if mode == vision.MODE_TALK and vision.needs_translate(text, lc):
                fixed = _try_translate(text, lang_name, key, lc)
                if fixed:
                    text = fixed
                    notes.append("视觉模型未按目标语言输出，已用翻译模型补译")

        if not text:
            return _err("模型没有返回内容，请重试")

        use_voice, vnote = _pick_voice(mode, text, str(voice), lang)
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


def _try_translate(text, lang_name, key, lc):
    """把 text 翻译成目标语言，合格才返回，否则返回 ""。

    最多试 3 次 —— 实测 glm-4-flash 偶尔会把原文和译文一起吐出来
    （strip_cjk_fragments 会把译文捞回来），对冷门语言（如古吉拉特语）
    更会**偶发**偷懒直接返回中文（完整链路连跑 3 次只有 1 次成功）。
    所以第 2 次起改用强指令（strict=True）重试，显著降低失败率。
    """
    # 目标语言本身用汉字（中文/日文）时不能禁用汉字 —— 否则译文会被当"夹带原文"删掉
    forbid = not str(lc or "").lower().startswith(("ja", "zh"))
    for i in range(3):
        try:
            fixed = vision.translate_text(text, lang_name, key,
                                          forbid_cjk=forbid, strict=(i > 0))
        except Exception:                                 # noqa: BLE001
            fixed = ""
        if fixed and not vision.needs_translate(fixed, lc):
            return fixed
    return ""


def _already_target(src, lc):
    """原文本身就是目标语言的文字吗？（是就不用再翻一遍）

    只看非拉丁文字系统：拉丁字母之间（英/法/德…）无法靠字符区分，
    一律当作"需要翻译"，否则「英文图 → 法语」会被误判成已达标、直接读英文。
    """
    sc = vision.script_of(src)
    if sc in ("", "latin"):
        return False
    pref = str(lc or "").lower().split("-")[0]
    if pref not in vision.SCRIPT_VOICE_PREFIXES.get(sc, ()):
        return False
    if pref == "ja" and not re.search(r"[\u3040-\u30ff]", src or ""):
        return False                           # 纯汉字的"日文"其实没翻译
    return True


def _translate_flow(paths, lang_name, detail, key, lc, notes):
    """「翻译朗读」：视觉模型只负责读出图中文字，翻译交给文本模型。

    为什么这么拆：实测 GLM-4V-Flash 识字很稳（同一张图每次稳定读出 54 字），
    但"翻译成 X 语言"这条指令服从率很低（26 种语言里 5 种要补译、1 种补译也失败）。
    拆开之后 5/5 全部达标。
    """
    src = vision.understand(paths, vision.MODE_READ, lang_name, detail, key, lc)
    if vision.is_no_text(src):
        # 图里没有文字 → 退回"看图解说"，直接用目标语言描述画面
        notes.append("图中未识别到文字，已改为描述画面")
        return vision.understand(paths, vision.MODE_TALK, lang_name,
                                 detail, key, lc)
    if _already_target(src, lc):
        return src                             # 原文即目标语言，无需翻译
    fixed = _try_translate(src, lang_name, key, lc)
    if fixed:
        return fixed
    notes.append("翻译模型未返回合格译文，已按原文朗读")
    return src


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
