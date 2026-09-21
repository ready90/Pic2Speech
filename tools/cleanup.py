# -*- coding: utf-8 -*-
"""清理测试产物并打印工程文件清单"""
import os
import shutil

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
OUT = os.path.join(ROOT, "tools", "tree.txt")

for base, dirs, files in os.walk(ROOT):
    for d in list(dirs):
        if d in ("__pycache__", ".gradle", "build"):
            shutil.rmtree(os.path.join(base, d), ignore_errors=True)
            dirs.remove(d)
    for f in files:
        if f.endswith(".log"):
            os.remove(os.path.join(base, f))

lines = []
for base, dirs, files in os.walk(ROOT):
    dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git")]
    for f in sorted(files):
        if f == "tree.txt":
            continue
        p = os.path.join(base, f)
        lines.append("%8d  %s" % (os.path.getsize(p),
                                  os.path.relpath(p, ROOT).replace("\\", "/")))

lines.sort(key=lambda s: s.split(None, 1)[1])
with open(OUT, "w", encoding="utf-8") as fh:
    fh.write("共 %d 个文件\n\n" % len(lines))
    fh.write("\n".join(lines))
print("files =", len(lines))
