# -*- coding: utf-8 -*-
"""安卓工程 Python 侧冒烟测试（在电脑上跑，验证逻辑与真实合成）

用法：python tools/smoke_test.py
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(
    os.path.join(HERE, "..", "app", "src", "main", "python")))

import pic2speech.api as api              # noqa: E402
from pic2speech import tts, vision        # noqa: E402

results = []


def check(name, cond, extra=""):
    results.append(bool(cond))
    print(("PASS" if cond else "FAIL"), "-", name, extra)


# ---------- 音色表 ----------
v = json.loads(api.voices_json())
check("voices.json 可解析", v["languages_count"] > 100, "语言数=%s" % v["languages_count"])
check("音色总数", v["voices_count"] > 300, "音色数=%s" % v["voices_count"])
check("含 zh-CN", any(l["code"] == "zh-CN" for l in v["languages"]))
check("含 ja-JP", any(l["code"] == "ja-JP" for l in v["languages"]))
check("默认音色可取", api._default_voice("ja-JP").startswith("ja-JP-"),
      api._default_voice("ja-JP"))
check("未知语言回退不乱", api._default_voice("xx-XX") != "")

# ---------- 文本处理 ----------
check("clean_for_speech 去 Markdown",
      tts.clean_for_speech("# 标题\n- *要点*") == "标题\n要点",
      repr(tts.clean_for_speech("# 标题\n- *要点*")))
check("短文本不分块", len(tts.split_text("你好世界。")) == 1)

long_text = "这是一个用于测试切分的句子。" * 300
parts = tts.split_text(long_text)
check("长文本会被切分", len(parts) > 1, "块数=%d" % len(parts))
check("切分后内容不丢失",
      sum(len(p) for p in parts) == len(tts.clean_for_speech(long_text)) or
      sum(len(p) for p in parts) >= len(long_text) - 10)

check("英文词间加空格", tts._glue_word("Hello", "world") == "Hello world")
check("中文之间不加空格", tts._glue_word("你好", "世界") == "你好世界")
check("标点紧跟", tts._glue_word("你好", "，") == "你好，")
check("detect_lang 中文", api.detect_lang("你好世界，这是中文。") == "zh-CN")
check("detect_lang 英文", api.detect_lang("Hello world, this is English") == "en-US")

# ---------- 假 Key 的错误处理（应返回中文提示，不抛异常） ----------
tmp = tempfile.mkdtemp()
img = os.path.join(tmp, "t.jpg")
with open(img, "wb") as f:
    f.write(b"\xff\xd8\xff\xe0" + b"\x00" * 256)
fake = "40edcc" + "1" * 43
r = json.loads(api.generate([img], "zh-CN", "zh-CN-XiaoxiaoNeural", 0,
                            "talk", "short", fake, tmp))
check("假 Key：返回 ok=false 而不是抛异常", r.get("ok") is False)
check("假 Key：提示是中文且可读",
      ("无效" in r.get("error", "")) or ("401" in r.get("error", ""))
      or ("HTTP" in r.get("error", "")), (r.get("error", "") or "")[:90])

# ---------- 真实语音合成 ----------
r2 = json.loads(api.resynth("安卓版语音合成测试，一二三四五六七八九十。",
                            "zh-CN-XiaoxiaoNeural", 0, tmp))
check("resynth 成功", r2.get("ok") is True, str(r2)[:140])
if r2.get("ok"):
    size = os.path.getsize(r2["mp3"])
    check("MP3 已生成且非空", size > 5000, "%d 字节" % size)
    srt = r2.get("srt") or ""
    has = bool(srt) and "-->" in open(srt, encoding="utf-8").read()
    check("SRT 字幕已生成", has, os.path.basename(srt))

# ---------- 其他语言音色可用（日语） ----------
r3 = json.loads(api.resynth("こんにちは、これはテストです。",
                            api._default_voice("ja-JP"), 0, tmp))
check("日语合成成功", r3.get("ok") is True, str(r3.get("error", ""))[:80])

# =========================================================================== #
# 回归：修复「选法语后翻译朗读失败」（2026-09-21）
#
# 根因链：① glm-4v-flash 经常不理会"翻译成 X 语言"，直接吐回中文原文；
#         ② edge-tts 用非中文音色念中文会硬报 `No audio was received`；
#         ①+② ⇒ 界面显示"语音合成失败"。
# 修法：严格提示词 + 文本模型补译 + 音色与文字自动匹配 + 合成兜底重试。
# 这里把每一环都钉住，防止以后改回去。
# =========================================================================== #
check("script_of 中文 → zh", vision.script_of("温馨提示禁止吸烟") == "zh")
check("script_of 日文 → ja", vision.script_of("こんにちは") == "ja")
check("script_of 日文(汉字+假名) → ja", vision.script_of("営業時間は9時です") == "ja")
check("script_of 韩文 → ko", vision.script_of("안녕하세요") == "ko")
check("script_of 英文 → latin", vision.script_of("Hello world") == "latin")

check("目标日语+纯汉字 ⇒ 判定需补译", vision.needs_translate("温馨提示", "ja-JP"))
check("目标日语+含假名 ⇒ 不补译", not vision.needs_translate("営業時間は9時です", "ja-JP"))
check("目标韩语+纯汉字 ⇒ 需补译", vision.needs_translate("温馨提示", "ko-KR"))
check("目标法语+汉字 ⇒ 需补译", vision.needs_translate("温馨提示", "fr-FR"))
check("目标中文+汉字 ⇒ 不补译", not vision.needs_translate("温馨提示", "zh-CN"))
check("目标法语+法语 ⇒ 不补译", not vision.needs_translate("Bonjour à tous", "fr-FR"))

_fr = api._find_lang("fr-FR")
_v, _n = api._pick_voice("trans", "温馨提示", "fr-FR-DeniseNeural", _fr)
check("中文文本+法语音色 ⇒ 自动换音色", _v != "fr-FR-DeniseNeural", "%s / %s" % (_v, _n))
_v2, _n2 = api._pick_voice("trans", "Bonjour à tous", "fr-FR-DeniseNeural", _fr)
check("法文文本+法语音色 ⇒ 不换音色", _v2 == "fr-FR-DeniseNeural" and not _n2, _v2)
_ja = api._find_lang("ja-JP")
_v3, _ = api._pick_voice("read", "営業時間は9時です", "zh-CN-XiaoxiaoNeural", _ja)
check("日文文本+中文音色 ⇒ 换回日语音色", _v3.startswith("ja-JP-"), _v3)

# 原故障场景：中文文本 + 法语音色 → 应自动兜底出音频，而不是报错
try:
    _mp3, _srt, _used, _snote = api._synthesize_safe(
        "温馨提示：本店禁止吸烟。", "fr-FR-DeniseNeural", 0, tmp, "smoke", _fr)
    check("中文文本+法语音色 ⇒ 自动兜底出音频", os.path.getsize(_mp3) > 5000,
          "%s / %s" % (_used, _snote))
except Exception as _e:                                            # noqa: BLE001
    check("中文文本+法语音色 ⇒ 自动兜底出音频", False, str(_e)[:90])

print()
print("RESULT:", "ALL PASS" if all(results) else "FAILED",
      "(%d/%d)" % (sum(results), len(results)))
