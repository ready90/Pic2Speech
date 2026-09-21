# -*- coding: utf-8 -*-
"""图片理解：智谱 GLM-4V-Flash（免费视觉大模型）

刻意只用标准库 urllib 发请求，不用 openai SDK ——
SDK 的依赖链里有 pydantic-core（Rust 编写），在安卓上几乎装不上。

★ 2026-09-21 修复「翻译朗读失败」：
   GLM-4V-Flash 经常**不理会"翻译成 X 语言"的指令**，直接吐回原文（中文）。
   而 edge-tts 用非中文音色念中文时会硬报 `No audio was received` ⇒ 界面显示"合成失败"。
   三道防线：
     1. 提示词改成强约束（实测汉字残留 36 → 0）；
     2. 拿回文本后做语言校验，不合格就用文本模型 glm-4-flash 补译一遍；
     3. 合成阶段再做音色兜底（见 api.py）。
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
TEXT_MODEL = "glm-4-flash"  # 纯文本模型，用于"视觉模型没翻译好"时的补译
MAX_TOKENS = 1024           # GLM-4V-Flash 输出上限，超过会报 400/1210

MODE_TALK = "talk"          # 看图解说
MODE_READ = "read"          # 朗读图中文字（原样）
MODE_TRANS = "trans"        # 翻译朗读

_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")

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


_KANA_RE = re.compile(r"[\u3040-\u30ff]")
_HANGUL_RE = re.compile(r"[\uac00-\ud7af]")
_LATIN_RE = re.compile(r"[A-Za-z]")


def script_of(text):
    """判断文本实际用的是哪套文字：ja / ko / zh / latin / ""。

    必须区分中·日——日文里也有汉字，只看有没有汉字会把日文误当成中文，
    进而换错音色（ja-JP 音色读日文最准，换成中文音色反而读不对）。
    """
    t = text or ""
    if _KANA_RE.search(t):
        return "ja"
    if _HANGUL_RE.search(t):
        return "ko"
    if has_cjk(t):
        return "zh"
    if _LATIN_RE.search(t):
        return "latin"
    return ""


def needs_translate(text, lang_code):
    """目标语言是外文，但文本看起来仍是中文原文 ⇒ 视觉模型没照做，需要补译。

    中文/日文/韩文都含汉字，所以对 ja/ko 要再细判：日文必须有假名、
    韩文必须有谚文，只有汉字没有假名/谚文的，基本就是没翻译的中文。
    """
    lc = str(lang_code or "").lower()
    if lc.startswith("zh") or not has_cjk(text):
        return False
    if lc.startswith("ja"):
        return not _KANA_RE.search(text or "")
    if lc.startswith("ko"):
        return not _HANGUL_RE.search(text or "")
    return True


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
# 纯文本补译（视觉模型不听话时的第二道防线）
# --------------------------------------------------------------------------- #
def translate_text(text, lang_name, api_key, forbid_cjk=False):
    """把 text 翻译成 lang_name，只返回译文。

    用文本模型（glm-4-flash）而不是视觉模型 —— 实测纯文本翻译的输出干净得多，
    不会夹带原文，也不会掺进对画面的描述。
    """
    forbid = "输出中不得出现任何汉字，也不得出现原文。\n" if forbid_cjk else ""
    prompt = (
        "把下面的内容翻译成地道、口语化、适合朗读的" + lang_name + "。\n"
        "只输出" + lang_name + "译文本身：不要原文、不要对照、不要解释、"
        "不要 Markdown 符号。\n" + forbid +
        "--- 待翻译内容 ---\n" + (text or "")
    )
    return _request({
        "model": TEXT_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": MAX_TOKENS,
    }, api_key, timeout=90)


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
