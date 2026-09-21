# -*- coding: utf-8 -*-
"""资源引用一致性校验（无需 Android SDK 即可运行）

检查：
  1) 所有 XML 是否格式良好
  2) Kotlin 里引用的 R.id.* / R.layout.* / R.string.* / R.color.* 是否真实存在
  3) XML 里引用的 @string/ @color/ @style/ @mipmap/ @drawable/ @xml/ 是否已定义
  4) Manifest 引用的类与资源是否就位

用法：python tools/check_resources.py
"""
import os
import re
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
APP = os.path.join(ROOT, "app", "src", "main")
RES = os.path.join(APP, "res")
KT = os.path.join(APP, "java", "com", "pic2speech", "app")
PY = os.path.join(APP, "python", "pic2speech")

problems = []
notes = []


def note(msg):
    notes.append(msg)
    print("[ok] " + msg)


def bad(msg):
    problems.append(msg)
    print("[!!] " + msg)


# ---------- 1. XML 格式 ----------
xml_files = []
for base, _dirs, files in os.walk(APP):
    for f in files:
        if f.endswith(".xml"):
            xml_files.append(os.path.join(base, f))
for p in xml_files:
    try:
        ET.parse(p)
    except Exception as e:                                     # noqa: BLE001
        bad("XML 格式错误 %s -> %s" % (os.path.relpath(p, ROOT), e))
note("XML 文件 %d 个，格式检查完成" % len(xml_files))

# ---------- 2. 收集已定义的资源 ----------
ids, strings, colors, styles, mipmaps, drawables, layouts = set(), set(), set(), set(), set(), set(), set()
for p in xml_files:
    rel = os.path.relpath(p, RES).replace("\\", "/")
    root = ET.parse(p).getroot()
    if rel.startswith("layout/"):
        layouts.add(os.path.splitext(os.path.basename(p))[0])
        for el in root.iter():
            v = el.get("{http://schemas.android.com/apk/res/android}id") or el.get("android:id")
            if v and v.startswith("@+id/"):
                ids.add(v[5:])
    elif rel.startswith("values/"):
        for el in root:
            name = el.get("name")
            if not name:
                continue
            if el.tag == "string":
                strings.add(name)
            elif el.tag == "color":
                colors.add(name)
            elif el.tag == "style":
                styles.add(name)
    elif rel.startswith("mipmap"):
        mipmaps.add(os.path.splitext(os.path.basename(p))[0])
    elif rel.startswith("drawable"):
        drawables.add(os.path.splitext(os.path.basename(p))[0])
    elif rel.startswith("xml/"):
        drawables.add(os.path.splitext(os.path.basename(p))[0])

note("id=%d string=%d color=%d style=%d layout=%d mipmap=%d"
     % (len(ids), len(strings), len(colors), len(styles),
        len(layouts), len(mipmaps)))

# ---------- 3. Kotlin 里的 R.* 引用 ----------
kt_text = ""
for f in sorted(os.listdir(KT)):
    if f.endswith(".kt"):
        with open(os.path.join(KT, f), encoding="utf-8") as fh:
            kt_text += fh.read()

for kind, pool in (("id", ids), ("layout", layouts), ("string", strings),
                   ("color", colors)):
    # 注意排除 android.R.*（系统自带资源，不属于本项目）
    for m in re.findall(r"(?<!android\.)R\.%s\.(\w+)" % kind, kt_text):
        if m not in pool:
            bad("Kotlin 引用了不存在的 R.%s.%s" % (kind, m))
note("Kotlin 中 R.* 引用检查完成")

# ---------- 4. XML 里的 @xxx/yyy 引用 ----------
declared = {
    "string": strings, "color": colors, "style": styles,
    "mipmap": mipmaps, "drawable": drawables,
}
for p in xml_files:
    with open(p, encoding="utf-8") as fh:
        text = fh.read()
    for kind, name in re.findall(r"@(string|color|style|mipmap|drawable|xml)/(\w+)", text):
        if kind == "xml":
            path = os.path.join(RES, "xml", name + ".xml")
            if not os.path.exists(path):
                bad("%s 引用缺失的 @xml/%s" % (os.path.basename(p), name))
            continue
        pool = declared.get(kind, set())
        if name not in pool:
            bad("%s 引用缺失的 @%s/%s" % (os.path.basename(p), kind, name))
note("XML 资源引用检查完成")

# ---------- 5. Manifest / 关键文件 ----------
with open(os.path.join(APP, "AndroidManifest.xml"), encoding="utf-8") as fh:
    mf = fh.read()
for cls in ("com.chaquo.python.android.PyApplication",
            "androidx.core.content.FileProvider", ".MainActivity"):
    if cls not in mf:
        bad("Manifest 缺少 %s" % cls)
for perm in ("android.permission.INTERNET",):
    if perm not in mf:
        bad("Manifest 缺少权限 %s" % perm)

required = [
    os.path.join(APP, "java", "com", "pic2speech", "app", "MainActivity.kt"),
    os.path.join(APP, "java", "com", "pic2speech", "app", "PyBridge.kt"),
    os.path.join(APP, "java", "com", "pic2speech", "app", "ImageUtil.kt"),
    os.path.join(PY, "api.py"), os.path.join(PY, "vision.py"),
    os.path.join(PY, "tts.py"), os.path.join(PY, "voices.json"),
    os.path.join(PY, "__init__.py"),
    os.path.join(ROOT, ".github", "workflows", "build-apk.yml"),
    os.path.join(ROOT, "app", "build.gradle.kts"),
    os.path.join(ROOT, "settings.gradle.kts"),
    os.path.join(ROOT, "build.gradle.kts"),
]
for p in required:
    if not os.path.exists(p):
        bad("缺少文件 %s" % os.path.relpath(p, ROOT))
note("关键文件齐全性检查完成")

# ---------- 6. Python 语法 ----------
import py_compile
for f in ("api.py", "vision.py", "tts.py", "__init__.py"):
    try:
        py_compile.compile(os.path.join(PY, f), doraise=True)
    except Exception as e:                                     # noqa: BLE001
        bad("Python 语法错误 %s -> %s" % (f, e))
note("Python 语法检查完成")

print()
if problems:
    print("RESULT: FAILED  (%d 个问题)" % len(problems))
    for p in problems:
        print("   - " + p)
    sys.exit(1)
print("RESULT: ALL PASS")
