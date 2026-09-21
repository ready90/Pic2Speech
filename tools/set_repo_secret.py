# -*- coding: utf-8 -*-
"""把智谱 API Key 写入 GitHub 仓库 Secret（ZHIPU_API_KEY）。

为什么这样做：Key 只进 APK、不进代码仓库。
CI 构建时由 tools/inject_key.py 从 Secret 生成 _secret.py 并打进 APK。

原理：GitHub 要求用仓库公钥做 libsodium sealed box 加密后再上传，
      所以本脚本依赖 PyNaCl。

用法：
    ZHIPU_API_KEY=xxx python tools/set_repo_secret.py
"""
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

OWNER, REPO = "ready90", "Pic2Speech"
SECRET_NAME = "ZHIPU_API_KEY"

try:
    from nacl import encoding, public
except ImportError:
    print("缺少 PyNaCl：pip install pynacl")
    sys.exit(2)


def get_token():
    inp = "protocol=https\nhost=github.com\n\n"
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "never"
    p = subprocess.run(["git", "credential", "fill"], input=inp,
                       capture_output=True, text=True, encoding="utf-8", env=env)
    for line in (p.stdout or "").splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1].strip()
    return None


def api(method, url, token, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "token " + token)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "pic2speech-secret")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            txt = r.read().decode("utf-8", "replace")
            return r.status, (json.loads(txt) if txt.strip() else {})
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:                                   # noqa: BLE001
        return 0, "EXC: %s" % e


def main():
    key = (os.environ.get("ZHIPU_API_KEY") or "").strip()
    if len(key) < 20:
        print(json.dumps({"ok": False, "err": "ZHIPU_API_KEY 未设置或过短"},
                         ensure_ascii=False))
        return 1

    tok = get_token()
    if not tok:
        print(json.dumps({"ok": False, "err": "取不到 GitHub 凭据"}, ensure_ascii=False))
        return 1

    base = "https://api.github.com/repos/%s/%s" % (OWNER, REPO)

    st, pk = api("GET", base + "/actions/secrets/public-key", tok)
    if st != 200:
        print(json.dumps({"ok": False, "at": "public-key", "status": st,
                          "body": str(pk)[:300]}, ensure_ascii=False))
        return 1

    box = public.SealedBox(public.PublicKey(base64.b64decode(pk["key"])))
    encrypted = base64.b64encode(box.encrypt(key.encode("utf-8"))).decode("ascii")

    st, res = api("PUT", base + "/actions/secrets/" + SECRET_NAME, tok, {
        "encrypted_value": encrypted,
        "key_id": pk["key_id"],
    })
    ok = st in (201, 204)
    out = {"ok": ok, "status": st, "secret": SECRET_NAME, "key_len": len(key),
           "masked": key[:6] + "***" + key[-4:]}
    if not ok:
        out["body"] = str(res)[:300]

    # 回读确认
    st2, lst = api("GET", base + "/actions/secrets", tok)
    if st2 == 200:
        names = [s["name"] for s in lst.get("secrets", [])]
        out["secrets_on_repo"] = names
        out["verified"] = SECRET_NAME in names

    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
