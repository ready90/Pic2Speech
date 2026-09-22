# -*- coding: utf-8 -*-
"""把智谱 API Key 写成 Python 模块（可选步骤）。

⚠️ 请先读完这段再决定要不要用
--------------------------------
写进 `_secret.py` 的 Key 会被 Chaquopy 打进 APK 的
`assets/chaquopy/app.imy`，而 **APK 和 .imy 都是 zip**，两层双击即可进入，
里面是**明文 Python 源码**。也就是说：任何拿到这个 APK 的人，
在电脑上用解压软件点两下，就能看到你的 Key，不需要装 App、不需要反编译。

因此本工程**默认不内置任何 Key**（用户在 App 内自行填写，只保存到手机本机）。
本脚本默认只生成一个 Key 为空的占位模块，不写入任何真实凭据。

只有当你明确要为「绝不外传的自己私用版本」内置 Key 时，才加 `--allow-embed`：

    ZHIPU_API_KEY=xxx python tools/inject_key.py --allow-embed

加了 `--allow-embed` 之后，请务必记住：**这个 APK 不能发给任何人**，
包括网盘、微信群、U 盘。CI 侧还有一道 `tools/verify_no_key.py` 闸门，
内置了 Key 的产物会被判为不合格而让构建失败。
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

WARN = """
================================================================
⚠️  你正在把 API Key 内置进 APK —— 请确认你清楚这意味着什么
================================================================
APK 是 zip，assets/chaquopy/app.imy 也是 zip，两层双击就能进入，
Key 以明文源码形式躺在 pic2speech/_secret.py 里。
任何拿到这个 APK 的人都能读到它，并可以用它调用你账号下的全部模型
（包括计费模型，费用算在你头上）。

⇒ 这个 APK 只能你自己用，绝不能外传（网盘 / 群聊 / U 盘都不行）。
================================================================
"""


def main(argv):
    allow = "--allow-embed" in argv
    key = (os.environ.get("ZHIPU_API_KEY") or "").strip()
    if allow:
        key = key  # 显式允许时才采用真实 Key
    else:
        key = ""   # 默认路径：绝不写入真实凭据

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(TEMPLATE % json.dumps(key), encoding="utf-8")

    if allow and len(key) >= 20:
        print(WARN)
        print("已写入 %s" % OUT)
        print("内置 Key 掩码 = %s***%s" % (key[:6], key[-4:]))
        print("::warning::此 APK 含内置 Key，仅限自己私用，切勿外传")
        return 0

    if allow:
        print("::warning::指定了 --allow-embed 但未提供 ZHIPU_API_KEY，已写入空 Key")

    print("已生成空 Key 模块 %s" % OUT)
    print("App 将在首次使用时引导用户填写自己的 Key（只保存在手机本机）。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
