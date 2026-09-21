# -*- coding: utf-8 -*-
"""校验 APK 结构：必须是合法 zip，含 AndroidManifest、dex、Python 原生库、edge-tts 包。"""
import hashlib
import json
import os
import sys
import zipfile

APK = sys.argv[1]


def main():
    out = {"apk": APK, "exists": os.path.exists(APK)}
    if not out["exists"]:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return
    size = os.path.getsize(APK)
    out["size_bytes"] = size
    out["size_mb"] = round(size / 1048576, 2)
    h = hashlib.sha256()
    with open(APK, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    out["sha256"] = h.hexdigest()

    try:
        zf = zipfile.ZipFile(APK)
    except Exception as e:
        out["valid_zip"] = False
        out["err"] = str(e)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return
    out["valid_zip"] = True
    names = zf.namelist()
    out["entry_count"] = len(names)

    def match(sub):
        return sorted(n for n in names if sub in n)

    out["has_manifest"] = "AndroidManifest.xml" in names
    out["dex"] = match(".dex")
    out["python_so"] = match("libpython")
    out["chaquopy_java_so"] = match("libchaquopy_java")
    out["abis"] = sorted({n.split("/")[1] for n in names
                          if n.startswith("lib/") and len(n.split("/")) > 2})
    out["edge_tts_entries"] = match("edge_tts")[:10]
    out["edge_tts_count"] = len(match("edge_tts"))
    out["pic2speech_app_entries"] = match("pic2speech")[:12]
    out["aiohttp_entries"] = len(match("aiohttp"))
    out["assets_sample"] = [n for n in names if n.startswith("assets/")][:15]
    out["bad_file"] = zf.testzip()
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
