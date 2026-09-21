# -*- coding: utf-8 -*-
"""图片理解：智谱 GLM-4V-Flash（免费视觉大模型）

刻意只用标准库 urllib 发请求，不用 openai SDK ——
SDK 的依赖链里有 pydantic-core（Rust 编写），在安卓上几乎装不上。
"""
import base64
import json
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
MAX_TOKENS = 1024           # GLM-4V-Flash 输出上限，超过会报 400/1210

MODE_TALK = "talk"          # 看图解说
MODE_READ = "read"          # 朗读图中文字（原样）
MODE_TRANS = "trans"        # 翻译朗读

_DETAIL_NOTE = {
    "short": "请用大约3句话、简洁概括。",
    "standard": "请用大约6~8句话，讲清楚画面与文字内容。",
    "long": "请尽量详细地覆盖画面细节与文字信息，但全文控制在800字以内"
            "（免费视觉模型有输出长度上限，超出会被截断）。",
}


def _ssl_context():
    if _CA_FILE:
        return ssl.create_default_context(cafile=_CA_FILE)
    return ssl.create_default_context()


def build_prompt(mode, lang_name, detail, scope=""):
    """scope：多图逐张处理时的位置说明，如“这是本次上传的第1张图（共3张）。”"""
    head = scope or ""
    if mode == MODE_READ:
        return (head + "请把这张图片里出现的所有文字内容逐字提取出来，原样输出，"
                "保持原文语言。不要翻译、不要解释、不要添加任何评论；"
                "只输出图片中的文字本身。若图片里没有文字，请如实回答“图片中没有文字”。")
    if mode == MODE_TRANS:
        return (head + "请把图片里出现的所有文字内容提取出来，"
                "并翻译成" + lang_name + "，以口语化、适合朗读的方式输出。"
                "若图片里没有文字，就简明描述一下画面内容。"
                "只输出结果本身，不要使用任何 Markdown 符号。")
    return (head + "请仔细观察这张图片（可能包含不同语言的文字、图表或场景）："
            "先读取并理解图中所有文字与画面信息，然后"
            + _DETAIL_NOTE.get(detail, _DETAIL_NOTE["standard"]) +
            "用" + lang_name + "输出一段自然、口语化、适合语音朗读的解说词。"
            "要求：信息准确、条理清楚、只输出解说词本身，"
            "不要出现任何 Markdown 符号（如 #、*、编号点）或额外说明。")


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


def _post(api_key, content):
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.7,
        "max_tokens": MAX_TOKENS,
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120,
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


def understand(image_paths, mode, lang_name, detail, api_key):
    """一张或多张图片 -> 用于朗读的文本"""
    urls = [file_to_data_url(p) for p in image_paths]
    n = len(urls)

    if n == 1:
        return _post(api_key, _content(build_prompt(mode, lang_name, detail), urls))

    # 朗读原文必须逐张处理，保证图片顺序
    if mode == MODE_READ:
        parts = []
        for i, u in enumerate(urls, 1):
            scope = "这是本次上传的第%d张图（共%d张）。" % (i, n)
            parts.append(_post(api_key, _content(
                build_prompt(mode, lang_name, detail, scope), [u])))
        return "\n\n".join("【图 %d】%s" % (i, t) for i, t in enumerate(parts, 1))

    # 先尝试所有图片一次送入（让模型理解图与图之间的关系）
    try:
        return _post(api_key, _content(build_prompt(mode, lang_name, detail), urls))
    except Exception:                                         # noqa: BLE001
        parts = []
        for i, u in enumerate(urls, 1):
            scope = "这是本次上传的第%d张图（共%d张），请分开描述不要混在一起。" % (i, n)
            parts.append(_post(api_key, _content(
                build_prompt(mode, lang_name, detail, scope), [u])))
        return "\n\n".join("【图 %d】%s" % (i, t) for i, t in enumerate(parts, 1))
