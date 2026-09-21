# -*- coding: utf-8 -*-
"""生成 voices.json

从 edge-tts 拉取全部可用音色（需联网，只需跑一次），按语言分组后写入
app/src/main/python/pic2speech/voices.json，供安卓端离线使用。

用法：
    python tools/gen_voices.py
"""
import asyncio
import json
import os

import edge_tts

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(
    HERE, "..", "app", "src", "main", "python", "pic2speech", "voices.json"))

# 常用语言排在最前
PRIORITY = ["zh-CN", "zh-HK", "zh-TW", "en-US", "en-GB", "ja-JP", "ko-KR",
            "fr-FR", "de-DE", "es-ES", "ru-RU", "pt-BR", "it-IT", "ar-SA",
            "hi-IN", "th-TH", "vi-VN", "id-ID", "ms-MY", "tr-TR"]

# 语言代码 -> 中文名（同时用作给视觉模型的“目标语言”名称）
CN_NAME = {
    "zh-CN": "中文", "zh-HK": "粤语", "zh-TW": "繁体中文",
    "zh-CN-liaoning": "中文（辽宁话）", "zh-CN-shaanxi": "中文（陕西话）",
    "yue-CN": "粤语", "wuu-CN": "吴语",
    "en-US": "英语", "en-GB": "英语", "en-AU": "英语", "en-CA": "英语",
    "en-IE": "英语", "en-IN": "英语", "en-KE": "英语", "en-NG": "英语",
    "en-NZ": "英语", "en-PH": "英语", "en-SG": "英语", "en-TZ": "英语",
    "en-ZA": "英语", "en-HK": "英语",
    "ja-JP": "日语", "ko-KR": "韩语",
    "fr-FR": "法语", "fr-CA": "法语", "fr-BE": "法语", "fr-CH": "法语",
    "de-DE": "德语", "de-AT": "德语", "de-CH": "德语",
    "es-ES": "西班牙语", "es-MX": "西班牙语", "es-AR": "西班牙语",
    "es-BO": "西班牙语", "es-CL": "西班牙语", "es-CO": "西班牙语",
    "es-CR": "西班牙语", "es-CU": "西班牙语", "es-DO": "西班牙语",
    "es-EC": "西班牙语", "es-GQ": "西班牙语", "es-GT": "西班牙语",
    "es-HN": "西班牙语", "es-NI": "西班牙语", "es-PA": "西班牙语",
    "es-PE": "西班牙语", "es-PR": "西班牙语", "es-PY": "西班牙语",
    "es-SV": "西班牙语", "es-US": "西班牙语", "es-UY": "西班牙语",
    "es-VE": "西班牙语",
    "pt-BR": "葡萄牙语", "pt-PT": "葡萄牙语",
    "it-IT": "意大利语",
    "ru-RU": "俄语", "uk-UA": "乌克兰语",
    "ar-SA": "阿拉伯语", "ar-AE": "阿拉伯语", "ar-BH": "阿拉伯语",
    "ar-DZ": "阿拉伯语", "ar-EG": "阿拉伯语", "ar-IQ": "阿拉伯语",
    "ar-JO": "阿拉伯语", "ar-KW": "阿拉伯语", "ar-LB": "阿拉伯语",
    "ar-LY": "阿拉伯语", "ar-MA": "阿拉伯语", "ar-OM": "阿拉伯语",
    "ar-QA": "阿拉伯语", "ar-SY": "阿拉伯语", "ar-TN": "阿拉伯语",
    "ar-YE": "阿拉伯语",
    "hi-IN": "印地语", "bn-BD": "孟加拉语", "bn-IN": "孟加拉语",
    "ta-IN": "泰米尔语", "ta-MY": "泰米尔语", "ta-SG": "泰米尔语",
    "ta-LK": "泰米尔语", "te-IN": "泰卢固语", "ml-IN": "马拉雅拉姆语",
    "mr-IN": "马拉地语", "gu-IN": "古吉拉特语", "kn-IN": "卡纳达语",
    "pa-IN": "旁遮普语", "ur-PK": "乌尔都语", "ur-IN": "乌尔都语",
    "th-TH": "泰语", "vi-VN": "越南语", "id-ID": "印尼语", "ms-MY": "马来语",
    "fil-PH": "菲律宾语", "km-KH": "高棉语", "lo-LA": "老挝语",
    "my-MM": "缅甸语", "si-LK": "僧伽罗语", "ne-NP": "尼泊尔语",
    "tr-TR": "土耳其语", "az-AZ": "阿塞拜疆语", "kk-KZ": "哈萨克语",
    "ky-KG": "吉尔吉斯语", "uz-UZ": "乌兹别克语", "tk-TM": "土库曼语",
    "tt-RU": "鞑靼语", "mn-MN": "蒙古语", "ug-CN": "维吾尔语",
    "fa-IR": "波斯语", "ps-AF": "普什图语", "he-IL": "希伯来语",
    "nl-NL": "荷兰语", "pl-PL": "波兰语", "cs-CZ": "捷克语",
    "sk-SK": "斯洛伐克语", "sl-SI": "斯洛文尼亚语", "hu-HU": "匈牙利语",
    "ro-RO": "罗马尼亚语", "bg-BG": "保加利亚语", "hr-HR": "克罗地亚语",
    "sr-RS": "塞尔维亚语", "bs-BA": "波斯尼亚语", "mk-MK": "马其顿语",
    "sq-AL": "阿尔巴尼亚语", "el-GR": "希腊语", "mt-MT": "马耳他语",
    "et-EE": "爱沙尼亚语", "lt-LT": "立陶宛语", "lv-LV": "拉脱维亚语",
    "fi-FI": "芬兰语", "sv-SE": "瑞典语", "da-DK": "丹麦语",
    "nb-NO": "挪威语", "is-IS": "冰岛语", "ca-ES": "加泰罗尼亚语",
    "gl-ES": "加利西亚语", "cy-GB": "威尔士语", "ga-IE": "爱尔兰语",
    "ka-GE": "格鲁吉亚语", "hy-AM": "亚美尼亚语",
    "sw-KE": "斯瓦希里语", "af-ZA": "南非荷兰语", "am-ET": "阿姆哈拉语",
    "so-SO": "索马里语", "zu-ZA": "祖鲁语", "yo-NG": "约鲁巴语",
    "ha-NG": "豪萨语", "ig-NG": "伊博语", "rw-RW": "卢旺达语",
    "sn-ZW": "绍纳语", "st-ZA": "塞索托语", "tn-ZA": "茨瓦纳语",
    "xh-ZA": "科萨语", "iu-Cans-CA": "因纽特语", "iu-Latn-CA": "因纽特语",
    "su-ID": "巽他语",
}


def main():
    voices = asyncio.run(edge_tts.list_voices())

    groups = {}
    for v in voices:
        loc = (v.get("Locale") or "").strip()
        if not loc:
            continue
        groups.setdefault(loc, []).append(v)

    languages = []
    for loc, vs in groups.items():
        ga = [v for v in vs if (v.get("Status") or "GA") == "GA"] or vs
        ga.sort(key=lambda v: (v.get("Gender") != "Female",
                               v.get("ShortName", "")))

        friendly = ga[0].get("FriendlyName") or ""
        eng = friendly.split(" - ", 1)[1].strip() if " - " in friendly else ""
        cn = CN_NAME.get(loc, "")

        out_voices = []
        for v in ga:
            sid = v.get("ShortName") or ""
            nick = sid
            if sid.startswith(loc + "-"):
                nick = sid[len(loc) + 1:]
            if nick.endswith("Neural"):
                nick = nick[:-len("Neural")]
            g = v.get("Gender") or ""
            out_voices.append({
                "id": sid,
                "nick": nick,
                "gender": "女" if g == "Female" else ("男" if g == "Male" else g),
            })

        languages.append({
            "code": loc,
            "label": ((cn or eng or loc) + " ｜ " + loc),
            "prompt_name": cn or eng or loc,
            "voices": out_voices,
        })

    def order(item):
        c = item["code"]
        return (PRIORITY.index(c) if c in PRIORITY else 999, c)

    languages.sort(key=order)

    total = sum(len(x["voices"]) for x in languages)
    data = {
        "updated": "2026-09-21",
        "languages_count": len(languages),
        "voices_count": total,
        "languages": languages,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print("OK ->", OUT)
    print("languages =", len(languages), " voices =", total)


if __name__ == "__main__":
    main()
