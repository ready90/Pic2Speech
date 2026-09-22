# -*- coding: utf-8 -*-
"""API Key 的读取点 —— 现在**恒为空**（不内置任何 Key）。

安全口径（2026-09-22 起）
-------------------------
曾经的做法是 CI 从仓库 Secret 把 Key 注入 `_secret.py`，随 APK 一起打包。
但 APK 本质是 zip、`assets/chaquopy/app.imy` 也是 zip，两层双击即可进入，
`_secret.py` 还是**明文 Python 源码** —— 任何拿到 APK 的人都能零门槛读到 Key，
并用它调用本账号下的全部模型（含计费模型）。

因此本工程已改为 **不内置任何 Key**：
  * Key 由用户在 App 界面上自行粘贴，仅保存到手机本机私有存储；
  * CI 不再注入，并有 `tools/verify_no_key.py` 闸门拦下含 Key 的产物。

这里的 `DEFAULT_API_KEY` 保留为空字符串，仅为兼容既有调用点。
`_secret.py` 若不存在（正常情况）或内容为空，都会安静地退回空值，
App 照常引导用户手动填写 Key，不会报错。
"""


def _load():
    try:
        from ._secret import API_KEY            # noqa: WPS433
        return str(API_KEY or "").strip()
    except Exception:                           # noqa: BLE001
        return ""


DEFAULT_API_KEY = _load()


def has_builtin_key():
    return len(DEFAULT_API_KEY) >= 20


def masked():
    """给界面显示用的掩码，例如 40edcc***ie1Gq"""
    k = DEFAULT_API_KEY
    if len(k) < 12:
        return ""
    return k[:6] + "***" + k[-4:]
