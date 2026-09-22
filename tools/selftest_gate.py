# -*- coding: utf-8 -*-
"""`tools/verify_no_key.py` 的自测（回归用）。

闸门这种东西必须两侧都验：
  * 拿**含 Key 的历史包**跑 → 必须命中，证明它不是摆设；
  * 拿**摘掉 Key 的包**跑  → 必须通过，证明它不会误报（否则每次构建都红）。

第二种样本是现场造的：把历史包里 `app.imy` 中所有带 secret 的条目剔除，
其余字节原样复制。所以这个脚本不会污染任何正式产物。

用法：
    python tools/selftest_gate.py dist/Pic2Speech-v1.5-player-debug.apk
"""
import importlib.util
import io
import os
import pathlib
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
GATE = ROOT / "tools" / "verify_no_key.py"


def load_gate():
    spec = importlib.util.spec_from_file_location("verify_no_key", str(GATE))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_gate(gate, apk):
    saved = sys.argv
    sys.argv = ["verify_no_key.py", str(apk)]
    try:
        return gate.main()
    finally:
        sys.argv = saved


def strip_secret(src, dst):
    """把 app.imy 里所有带 secret 的条目剔掉，其余原样复制。"""
    removed = []
    with zipfile.ZipFile(src) as zin, \
            zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "assets/chaquopy/app.imy":
                inner = zipfile.ZipFile(io.BytesIO(data))
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as o:
                    for n in inner.namelist():
                        if "secret" in n.lower():
                            removed.append(n)
                            continue
                        o.writestr(n, inner.read(n))
                data = buf.getvalue()
            zout.writestr(item, data)
    return removed


def main():
    if len(sys.argv) < 2:
        print("用法: python tools/selftest_gate.py <含 Key 的历史 APK 路径>")
        return 2

    src = pathlib.Path(sys.argv[1])
    if not src.is_file():
        print("找不到文件: %s" % src)
        return 2

    gate = load_gate()
    tmp = ROOT / "dist" / "_selftest_clean.apk"
    verdict = []

    print("### 1/2 含 Key 的包（期望：命中，退出码 1）")
    rc_dirty = run_gate(gate, src)
    verdict.append(("含 Key 包应命中", rc_dirty == 1, "退出码=%d" % rc_dirty))

    print()
    print("### 2/2 摘掉 Key 的包（期望：通过，退出码 0）")
    removed = strip_secret(src, tmp)
    print("已剔除条目: %s" % (removed or "（没有可剔除的）"))
    try:
        rc_clean = run_gate(gate, tmp)
    finally:
        if tmp.is_file():
            os.remove(tmp)
    verdict.append(("干净包不应误报", rc_clean == 0, "退出码=%d" % rc_clean))

    print()
    print("=" * 60)
    print("自测结论")
    print("=" * 60)
    ok = True
    for name, passed, note in verdict:
        print("  [%s] %-18s %s" % ("OK" if passed else "NG", name, note))
        ok = ok and passed
    print("RESULT: %s" % ("ALL PASS" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
