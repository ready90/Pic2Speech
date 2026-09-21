# -*- coding: utf-8 -*-
"""图片理解：智谱 GLM-4V-Flash（免费视觉大模型）

刻意只用标准库 urllib 发请求，不用 openai SDK ——
SDK 的依赖链里有 pydantic-core（Rust 编写），在安卓上几乎装不上。

★ 2026-09-21 第一轮修复「翻译朗读失败」：
   GLM-4V-Flash 经常**不理会"翻译成 X 语言"的指令**，直接吐回原文（中文）；
   而 edge-tts 用非中文音色念中文时会报 `No audio was received` ⇒ 界面显示"合成失败"。

★ 2026-09-21 第二轮修复（多语言实测后加严）：
   实测 26 种语言发现，GLM-4V-Flash 的「翻译服从率」很低 —— 26 种里有 5 种
   要靠补译才纠正、1 种补译也失败（俄语最终读的还是中文）。
   但它**识字（OCR）能力非常稳**：同一张图每次都能稳定读出 54 字原文。
   ⇒ 因此把"翻译"整件事从视觉模型手里拿走：
        「翻译朗读」= 视觉模型只读出图中文字 → 文本模型 glm-4-flash 负责翻译。
      实测 5/5 全部达标，汉字残留 0。
   ⇒ 另外补上：
       · 文字系统识别（西里尔/阿拉伯/天城文/泰文/希腊文/希伯来文…），
         让音色与文字对得上（音色错配会让 edge-tts **静默产出空音频**，不报错！）
       · 翻译结果剥离夹带的原文片段（模型偶尔仍会夹带汉字）
"""
import base64
import json
import re
import ssl
import urllib.error
import urllib.request

try:                        # certifi 提供 CA 根证书（安卓上 Python 读不到系统证书库）
    import certifi
    _CA_FILE = certifi.where()
except Exception:           # noqa: BLE001
    _CA_FILE = None

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-4v-flash"
TEXT_MODEL = "glm-4-flash"  # 纯文本模型，负责翻译 / 补译
MAX_TOKENS = 1024           # GLM-4V-Flash 输出上限，超过会报 400/1210

MODE_TALK = "talk"          # 看图解说
MODE_READ = "read"          # 朗读图中文字（原样）
MODE_TRANS = "trans"        # 翻译朗读


# --------------------------------------------------------------------------- #
# 文字系统识别
#
# 为什么需要它：edge-tts 的每个音色只认自己那套文字。音色与文字不匹配时
# **不一定报错** —— 实测英文音色念阿拉伯文/泰文/俄文会静默产出恒定
# 0.9 秒 / 10.7KB 的空音频；念希腊文则会按拉丁字母硬读出 3 倍长的错音。
# 所以在合成前必须先把"文字 vs 音色"对齐。
# --------------------------------------------------------------------------- #
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_KANA_RE = re.compile(r"[\u3040-\u30ff]")
_HANGUL_RE = re.compile(r"[\uac00-\ud7af\u1100-\u11ff\u3130-\u318f]")
_LATIN_RE = re.compile(r"[A-Za-z]")

# 顺序要紧：日文含汉字(先判假名)、韩文含方块字，拉丁字母必须垫底
_SCRIPT_RES = [
    ("ja", _KANA_RE),
    ("ko", _HANGUL_RE),
    ("zh", _CJK_RE),
    ("ru", re.compile(r"[\u0400-\u04ff\u0500-\u052f]")),
    ("ar", re.compile(r"[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff"
                      r"\ufb50-\ufdff\ufe70-\ufeff]")),
    ("he", re.compile(r"[\u0590-\u05ff]")),
    ("hi", re.compile(r"[\u0900-\u097f]")),
    ("bn", re.compile(r"[\u0980-\u09ff]")),
    ("pa", re.compile(r"[\u0a00-\u0a7f]")),
    ("gu", re.compile(r"[\u0a80-\u0aff]")),
    ("ta", re.compile(r"[\u0b80-\u0bff]")),
    ("te", re.compile(r"[\u0c00-\u0c7f]")),
    ("kn", re.compile(r"[\u0c80-\u0cff]")),
    ("ml", re.compile(r"[\u0d00-\u0d7f]")),
    ("si", re.compile(r"[\u0d80-\u0dff]")),
    ("th", re.compile(r"[\u0e00-\u0e7f]")),
    ("lo", re.compile(r"[\u0e80-\u0eff]")),
    ("my", re.compile(r"[\u1000-\u109f]")),
    ("el", re.compile(r"[\u0370-\u03ff\u1f00-\u1fff]")),
    ("ka", re.compile(r"[\u10a0-\u10ff\u2d00-\u2d2f]")),
    ("hy", re.compile(r"[\u0530-\u058f]")),
    ("am", re.compile(r"[\u1200-\u137f]")),
    ("km", re.compile(r"[\u1780-\u17ff]")),
]

# 文字系统 -> 能正确朗读该文字的音色"语言前缀"集合
SCRIPT_VOICE_PREFIXES = {
    "zh": ("zh",),
    "ja": ("ja",),
    "ko": ("ko",),
    "ru": ("ru", "uk", "bg", "sr", "mk", "be", "kk", "ky", "tg", "mn",
           "tt", "ba", "uz"),
    "ar": ("ar", "fa", "ur", "ps", "sd", "ug", "ms", "dv"),
    "he": ("he",),
    "hi": ("hi", "mr", "ne"),
    "bn": ("bn",),
    "pa": ("pa",),
    "gu": ("gu",),
    "ta": ("ta",),
    "te": ("te",),
    "kn": ("kn",),
    "ml": ("ml",),
    "si": ("si",),
    "th": ("th",),
    "lo": ("lo",),
    "my": ("my",),
    "ka": ("ka",),
    "hy": ("hy",),
    "am": ("am",),
    "km": ("km",),
    "el": ("el",),
}

SCRIPT_NAME = {
    "zh": "中文", "ja": "日文", "ko": "韩文", "ru": "西里尔文",
    "ar": "阿拉伯文", "he": "希伯来文", "hi": "天城文", "bn": "孟加拉文",
    "pa": "旁遮普文", "gu": "古吉拉特文", "ta": "泰米尔文", "te": "泰卢固文",
    "kn": "卡纳达文", "ml": "马拉雅拉姆文", "si": "僧伽罗文", "th": "泰文",
    "lo": "老挝文", "my": "缅甸文", "ka": "格鲁吉亚文", "hy": "亚美尼亚文",
    "am": "阿姆哈拉文", "km": "高棉文", "el": "希腊文",
    "latin": "拉丁字母",
}

_DETAIL_NOTE = {
    "short": "请用大约3句话、简洁概括。",
    "standard": "请用大约6~8句话，讲清楚画面与文字内容。",
    "long": "请尽量详细地覆盖画面细节与文字信息，但全文控制在800字以内"
            "（免费视觉模型有输出长度上限，超出会被截断）。",
}


# --------------------------------------------------------------------------- #
# 语言工具
# --------------------------------------------------------------------------- #
def has_cjk(text):
    """文本里是否含汉字（判断"模型有没有真的翻译成外文"）"""
    return bool(_CJK_RE.search(text or ""))


def is_cjk_lang(lang_code):
    """目标语言本身是否用汉字（中文/日文/韩文）"""
    return str(lang_code or "").lower().startswith(("zh", "ja", "ko"))


def script_of(text):
    """判断文本实际用的是哪套文字，返回文字系统代号；无法判断返回 ""。

    必须区分中·日·韩：日文里也有汉字，只看有没有汉字会把日文误当成中文，
    进而换错音色（ja-JP 音色读日文最准，换成中文音色反而读不对）。
    """
    t = text or ""
    for name, rx in _SCRIPT_RES:
        if rx.search(t):
            return name
    if _LATIN_RE.search(t):
        return "latin"
    return ""


def needs_translate(text, lang_code):
    """文本看起来不是目标语言 ⇒ 需要（重新）翻译。

    比"只看有没有汉字"更准：先判断文本用的是哪套文字，再看这套文字是否
    属于目标语言 —— 于是"要英语却回了俄语""要日语却回了中文"都能识别。
    拉丁字母之间（英/法/德…）无法靠字符区分，一律放行。
    """
    lc = str(lang_code or "").lower()
    if lc.startswith("zh"):
        return False
    sc = script_of(text)
    if sc in ("", "latin"):
        return False
    pref = lc.split("-")[0]
    if pref in SCRIPT_VOICE_PREFIXES.get(sc, ()):
        if lc.startswith("ja"):
            return not _KANA_RE.search(text or "")     # 日文必须有假名
        if lc.startswith("ko"):
            return not _HANGUL_RE.search(text or "")   # 韩文必须有谚文
        return False
    return True


_FRAG_SPLIT_RE = re.compile(r"(?<=[。！？；!?;\n])")


def strip_cjk_fragments(text):
    """去掉夹带的原文片段（含汉字的句子），只保留纯译文部分。

    实测 glm-4-flash 偶尔仍会把中文原文和译文一起吐出来，
    按句切开、丢掉含汉字的句子，就能把译文捞回来。
    """
    keep = []
    for frag in _FRAG_SPLIT_RE.split(text or ""):
        if frag and not has_cjk(frag):
            keep.append(frag)
    return "".join(keep).strip()


_NO_TEXT_RE = re.compile(r"(没有|未|无|不存在).{0,6}(文字|文本|内容|字样)"
                         r"|no\s+text|nothing\s+to", re.I)


def is_no_text(text):
    """判断"图里没有文字"这类回答"""
    t = (text or "").strip()
    if len(t) <= 2:
        return True
    return len(t) < 40 and bool(_NO_TEXT_RE.search(t))


def _ssl_context():
    if _CA_FILE:
        return ssl.create_default_context(cafile=_CA_FILE)
    return ssl.create_default_context()


# --------------------------------------------------------------------------- #
# 提示词
# --------------------------------------------------------------------------- #
def build_prompt(mode, lang_name, detail, scope="", lang_code=""):
    """scope：多图逐张处理时的位置说明，如“这是本次上传的第1张图（共3张）。”

    lang_code 用于判断目标语言是否是汉字系：目标为外文时，加"一个汉字都不许出现"
    这条硬约束（实测能把模型夹带中文原文的情况从 36 字降到 0 字）。
    """
    head = scope or ""
    no_cjk = ""
    if not is_cjk_lang(lang_code):
        no_cjk = ("输出中不得出现任何汉字，也不得出现原文句子；"
                  "整段只允许出现" + lang_name + "的文字。")

    if mode == MODE_READ:
        return (head + "请把这张图片里出现的所有文字内容逐字提取出来，原样输出，"
                "保持原文语言。不要翻译、不要解释、不要添加任何评论；"
                "只输出图片中的文字本身。若图片里没有文字，请如实回答“图片中没有文字”。")

    if mode == MODE_TRANS:
        # 注：翻译模式现在不再让视觉模型翻译（它服从率低），
        # 改由 api 层走「OCR + 文本模型翻译」。这里保留提示词以兼容旧调用。
        return (head + "你是一名" + lang_name + "母语者。请把这张图片里的文字内容，"
                "翻译成地道、口语化、适合朗读的" + lang_name + "，然后直接说出来。"
                "禁止输出原文、禁止中外对照、禁止解释、禁止使用任何 Markdown 符号。"
                + no_cjk +
                "如果图片里确实没有文字，就用一句" + lang_name + "简单描述画面内容。")

    return (head + "请仔细观察这张图片（可能包含不同语言的文字、图表或场景）："
            "先读取并理解图中所有文字与画面信息，然后"
            + _DETAIL_NOTE.get(detail, _DETAIL_NOTE["standard"]) +
            "用" + lang_name + "输出一段自然、口语化、适合语音朗读的解说词。"
            "要求：信息准确、条理清楚、只输出解说词本身，"
            + no_cjk +
            "不要出现任何 Markdown 符号（如 #、*、编号点）或额外说明。")


# --------------------------------------------------------------------------- #
# 图片
# --------------------------------------------------------------------------- #
def _guess_mime(data):
    if data[:8].startswith(b"\x89PNG"):
        return "image/png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:2] == b"BM":
        return "image/bmp"
    return "image/jpeg"


def file_to_data_url(path):
    with open(path, "rb") as f:
        data = f.read()
    b64 = base64.b64encode(data).decode("ascii")
    return "data:" + _guess_mime(data) + ";base64," + b64


def _content(text, urls):
    c = [{"type": "text", "text": text}]
    for u in urls:
        c.append({"type": "image_url", "image_url": {"url": u}})
    return c


# --------------------------------------------------------------------------- #
# 请求
# --------------------------------------------------------------------------- #
def _request(payload, api_key, timeout=120):
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout,
                                    context=_ssl_context()) as resp:
            data = json.loads(resp.read().decode("utf-8", "ignore"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:300]
        if e.code in (401, 403):
            raise RuntimeError("API Key 无效或已过期（HTTP %d）"
                               "，请到 open.bigmodel.cn 重新生成后粘贴保存" % e.code)
        raise RuntimeError("接口返回 HTTP %d：%s" % (e.code, detail))
    except urllib.error.URLError as e:
        raise RuntimeError("网络连接失败：%s（请检查手机网络）" % (e.reason,))
    except Exception as e:                                    # noqa: BLE001
        raise RuntimeError("请求异常：%s" % (e,))

    try:
        return (data["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError):
        raise RuntimeError("接口返回格式异常：%s" % (str(data)[:200],))


def _post(api_key, content):
    return _request({
        "model": MODEL,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.7,
        "max_tokens": MAX_TOKENS,
    }, api_key, timeout=120)


# --------------------------------------------------------------------------- #
# 纯文本翻译（不在视觉模型上翻译，全交给它）
# --------------------------------------------------------------------------- #
def translate_text(text, lang_name, api_key, forbid_cjk=False):
    """把 text 翻译成 lang_name，只返回译文。

    用文本模型（glm-4-flash）而不是视觉模型 —— 实测纯文本翻译的输出干净得多，
    不会夹带原文，也不会掺进对画面的描述。
    forbid_cjk=True 时，若结果里仍夹带汉字句子，会就地剥掉（保留纯译文部分）。
    """
    forbid = "输出中不得出现任何汉字，也不得出现原文。\n" if forbid_cjk else ""
    prompt = (
        "把下面的内容翻译成地道、口语化、适合朗读的" + lang_name + "。\n"
        "只输出" + lang_name + "译文本身：不要原文、不要对照、不要解释、"
        "不要 Markdown 符号。\n" + forbid +
        "--- 待翻译内容 ---\n" + (text or "")
    )
    out = _request({
        "model": TEXT_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": MAX_TOKENS,
    }, api_key, timeout=90)

    if forbid_cjk and out:
        cleaned = strip_cjk_fragments(out)
        if cleaned:
            out = cleaned
    return out


# --------------------------------------------------------------------------- #
# 对外主函数
# --------------------------------------------------------------------------- #
def understand(image_paths, mode, lang_name, detail, api_key, lang_code=""):
    """一张或多张图片 -> 用于朗读的文本"""
    urls = [file_to_data_url(p) for p in image_paths]
    n = len(urls)

    if n == 1:
        return _post(api_key, _content(
            build_prompt(mode, lang_name, detail, "", lang_code), urls))

    # 朗读原文必须逐张处理，保证图片顺序
    if mode == MODE_READ:
        parts = []
        for i, u in enumerate(urls, 1):
            scope = "这是本次上传的第%d张图（共%d张）。" % (i, n)
            parts.append(_post(api_key, _content(
                build_prompt(mode, lang_name, detail, scope, lang_code), [u])))
        return "\n\n".join("【图 %d】%s" % (i, t) for i, t in enumerate(parts, 1))

    # 先尝试所有图片一次送入（让模型理解图与图之间的关系）
    try:
        return _post(api_key, _content(
            build_prompt(mode, lang_name, detail, "", lang_code), urls))
    except Exception:                                         # noqa: BLE001
        parts = []
        for i, u in enumerate(urls, 1):
            scope = "这是本次上传的第%d张图（共%d张），请分开描述不要混在一起。" % (i, n)
            parts.append(_post(api_key, _content(
                build_prompt(mode, lang_name, detail, scope, lang_code), [u])))
        return "\n\n".join("【图 %d】%s" % (i, t) for i, t in enumerate(parts, 1))
