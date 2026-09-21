# -*- coding: utf-8 -*-
"""生成安卓启动图标位图

自适应图标（Android 8+）用矢量 XML，这里生成的是给 Android 7 用的 PNG 回退版本。
用法：python tools/make_icons.py
"""
import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.normpath(os.path.join(HERE, "..", "app", "src", "main", "res"))

BRAND = (30, 111, 232, 255)
WHITE = (255, 255, 255, 255)

# Android 密度 -> 图标像素
DENSITIES = {
    "mipmap-mdpi": 48,
    "mipmap-hdpi": 72,
    "mipmap-xhdpi": 96,
    "mipmap-xxhdpi": 144,
    "mipmap-xxxhdpi": 192,
}


def render(size=1024):
    S = size
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 蓝色圆角底
    d.rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * 0.22), fill=BRAND)

    # 白色照片卡片
    cx0, cy0 = int(S * 0.20), int(S * 0.30)
    cx1, cy1 = int(S * 0.50), int(S * 0.70)
    d.rounded_rectangle([cx0, cy0, cx1, cy1], radius=int(S * 0.035), fill=WHITE)

    # 卡片内的山形
    base = cy1 - int(S * 0.03)
    d.polygon([
        (cx0 + int(S * 0.015), base),
        (cx0 + int(S * 0.080), base - int(S * 0.105)),
        (cx0 + int(S * 0.125), base - int(S * 0.055)),
        (cx0 + int(S * 0.170), base - int(S * 0.105)),
        (cx1 - int(S * 0.015), base),
    ], fill=BRAND)

    # 三道声波（由内向外，圆心在卡片右侧之上，避免压到卡片）
    wcx, wcy = int(S * 0.62), int(S * 0.50)
    lw = max(2, int(S * 0.040))
    for R in (0.09, 0.16, 0.23):
        rr = int(S * R)
        d.arc([wcx - rr, wcy - rr, wcx + rr, wcy + rr],
              start=-58, end=58, fill=WHITE, width=lw)

    return img


def main():
    master = render(1024)
    for folder, px in DENSITIES.items():
        out_dir = os.path.join(RES, folder)
        os.makedirs(out_dir, exist_ok=True)
        icon = master.resize((px, px), Image.LANCZOS)
        path = os.path.join(out_dir, "ic_launcher.png")
        icon.save(path, "PNG")
        print("saved", path, px)
    print("OK")


if __name__ == "__main__":
    main()
