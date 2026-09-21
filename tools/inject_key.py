# -*- coding: utf-8 -*-
"""CI 构建前调用：把仓库 Secret 里的智谱 API Key 写成 Python 模块。

Key 通过环境变量 ZHIPU_API_KEY 传入（GitHub Actions 里来自 secrets.ZHIPU_API_KEY）。
生成的文件 `app/src/main/python/pic2speech/_secret.py` 已被 .gitignore 忽略，
所以 Key 永远不会进入代码仓库，但会被 Chaquopy 打进 APK。

用法：
    ZHIPU_API_KEY=xxx python tools/inject_key.py

未配置 Secret 时不报错，只是生成一个空值模块 —— App 会退回手动填写 Key。
"""
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "app" / "src" / "main" / "python" / "pic2speech" / "_secret.py"

TEMPLATE = (
    "# -*- coding: utf-8 -*-\n"
    "# 本文件由 tools/inject_key.py 自动生成，请勿提交到代码仓库\n"
    "API_KEY = %s\n"
)


def main():
    key = (os.environ.get("ZHIPU_API_KEY") or "").strip()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(TEMPLATE % json.dumps(key), encoding="utf-8")

    print("已写入 %s" % OUT)
    print("内置 Key 长度 = %d" % len(key))
    if len(key) < 20:
        # GitHub Actions 会把这种 ::warning:: 显示成构建告警
        print("::warning::ZHIPU_API_KEY 未配置或过短，App 将要求手动填写 Key")
    else:
        print("内置 Key 掩码 = %s***%s" % (key[:6], key[-4:]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
