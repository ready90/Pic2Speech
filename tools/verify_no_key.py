# -*- coding: utf-8 -*-
"""产物安全闸门：确认 APK 里不含任何智谱 API Key。

为什么需要它
------------
APK 本质就是 zip，Chaquopy 的 `assets/chaquopy/app.imy` 也是 zip，
两层双击即可进入。曾经内置的 Key 落在 `pic2speech/_secret.py` 里，
是**明文 Python 源码**，零技术门槛就能读出来。

所以本工程改为**不内置任何 Key**（用户在 App 内自行填写，只存本机）。
这个脚本在 CI 里作为终检：只要产物里还能翻出 Key 形态的字符串，
就让构建失败 —— 防止以后有人无意中把注入步骤加回来。

用法：
    python tools/verify_no_key.py app/build/outputs/apk/debug/app-debug.apk

退出码：0 = 干净；1 = 命中（构建应当失败）。
"""
import io
import re
import sys
import zipfile

# 智谱 Key 形态：32 位十六进制 + "." + 16 位 base62
KEY_SHAPE = re.compile(rb"[0-9a-fA-F]{32}\.[A-Za-z0-9]{16}")

# 明文赋值形态，例如：API_KEY = "xxxx"
KEY_ASSIGN = re.compile(rb"API[_\-]?KEY\s*=\s*[\"'][^\"'\r\n]{20,}[\"']")

# 文件名判据：注入脚本生成的模块名
SECRET_NAME = re.compile(r"_secret\.pyc?$", re.IGNORECASE)

# 单个条目最大扫描体积（跳过超大二进制，dex/imy 都远小于此值）
MAX_SCAN = 32 * 1024 * 1024

SKIP_SUFFIX = (".so", ".png", ".webp", ".ogg", ".mp3", ".jpg", ".jpeg")


def scan_blob(name, data, hits, depth):
    """扫描一段字节内容，命中则记入 hits。"""
    if len(data) > MAX_SCAN:
        return
    for rx, label in ((KEY_SHAPE, "Key 形态字符串"), (KEY_ASSIGN, "明文 Key 赋值")):
        for m in rx.finditer(data):
            raw = m.group(0)
            hits.append({
                "where": name,
                "kind": label,
                "sample": raw[:14].decode("ascii", "replace") + "…（已截断）",
            })

    # 嵌套 zip（.imy 就是 zip）：递归进去
    if depth < 4 and data[:2] == b"PK":
        try:
            inner = zipfile.ZipFile(io.BytesIO(data))
        except Exception:                                   # noqa: BLE001
            return
        for sub in inner.namelist():
            if SECRET_NAME.search(sub):
                hits.append({
                    "where": name + " → " + sub,
                    "kind": "注入生成的 Key 模块",
                    "sample": "文件存在即视为泄露",
                })
            if sub.lower().endswith(SKIP_SUFFIX):
                continue
            try:
                scan_blob(name + " → " + sub, inner.read(sub), hits, depth + 1)
            except Exception:                               # noqa: BLE001
                pass


def _safe_stdout():
    """Windows 控制台默认 GBK 编码，直接输出 ✓ / ✗ 这类符号会抛
    UnicodeEncodeError 把脚本打断 —— 看起来像"扫描失败"，其实是"打印失败"。
    这里统一兜底：编不出来的字符转义输出，保证脚本能跑完并给出真实退出码。"""
    try:
        sys.stdout.reconfigure(errors="backslashreplace")
    except Exception:                                       # noqa: BLE001
        pass


def main():
    _safe_stdout()
    if len(sys.argv) < 2:
        print("用法: python tools/verify_no_key.py <apk 路径>")
        return 2

    apk = sys.argv[1]
    hits = []

    with zipfile.ZipFile(apk) as z:
        for name in z.namelist():
            if SECRET_NAME.search(name):
                hits.append({
                    "where": name,
                    "kind": "注入生成的 Key 模块",
                    "sample": "文件存在即视为泄露",
                })
            if name.lower().endswith(SKIP_SUFFIX):
                continue
            try:
                scan_blob(name, z.read(name), hits, 1)
            except Exception:                               # noqa: BLE001
                pass

    # 掩码显示，避免把命中内容原样打进 CI 日志
    print("=" * 60)
    print("产物安全闸门：APK 内 API Key 检查")
    print("=" * 60)
    print("目标: %s" % apk)
    print("命中: %d 处" % len(hits))
    if hits:
        for h in hits:
            print("  [X] [%s] %s  <- %s" % (h["kind"], h["where"], h["sample"]))
        print("-" * 60)
        print("::error::APK 中检出 API Key！请检查是否有人把注入步骤加回了构建流程。")
        print("修复方向：删除 app/src/main/python/pic2speech/_secret.py，")
        print("         并确保 CI 不再执行 tools/inject_key.py。")
        return 1

    print("  [OK] 未发现 _secret.py")
    print("  [OK] 未发现 Key 形态字符串")
    print("  [OK] 未发现明文 Key 赋值")
    print("通过：该 APK 可以安全地对外分享。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
