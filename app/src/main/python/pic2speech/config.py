# -*- coding: utf-8 -*-
"""内置 API Key 的读取点。

设计：**内置 Key 不写死在源码里**。
CI 构建时由 `tools/inject_key.py` 从仓库 Secret（ZHIPU_API_KEY）生成同目录下的
`_secret.py`（该文件已被 .gitignore 忽略，永不进入代码仓库），
Chaquopy 再把它一起打进 APK。

本地直接跑或 Secret 没配时，`_secret.py` 不存在，这里安静地退回空值，
App 会照常提示手动填写 Key。
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
