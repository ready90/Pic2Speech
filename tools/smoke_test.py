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
from pic2speech import tts                # noqa: E402

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

print()
print("RESULT:", "ALL PASS" if all(results) else "FAILED",
      "(%d/%d)" % (sum(results), len(results)))
