# -*- coding: utf-8 -*-
"""下载指定 run 的 APK artifact 并解压到目标目录。"""
import io
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error
import zipfile

OWNER, REPO = "ready90", "Pic2Speech"
RUN_ID = sys.argv[1]
DEST_DIR = sys.argv[2]


def get_token():
    inp = "protocol=https\nhost=github.com\n\n"
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "never"
    p = subprocess.run(["git", "credential", "fill"], input=inp, capture_output=True,
                       text=True, encoding="utf-8", env=env)
    for line in (p.stdout or "").splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1].strip()
    return None


def _no_redirect_opener():
    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    return urllib.request.build_opener(_NoRedirect)


def fetch_artifact_zip(zip_api_url, tok):
    """GitHub 的 artifact /zip 会 302 跳到带 SAS 签名的 Azure 地址。
    若跟随重定向时把 Authorization 头也带过去，Azure 会返回 403
    （'Server failed to authenticate the request ... including the signature'）。
    所以先拿到 Location，再【不带任何鉴权头】下载。"""
    opener = _no_redirect_opener()
    req = urllib.request.Request(zip_api_url)
    req.add_header("Authorization", "token " + tok)
    req.add_header("User-Agent", "pic2speech")
    try:
        with opener.open(req, timeout=120) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code not in (301, 302, 303, 307, 308):
            raise
        loc = e.headers.get("Location")
        if not loc:
            raise RuntimeError("redirect without Location header")
        req2 = urllib.request.Request(loc)   # 注意：不带 Authorization
        req2.add_header("User-Agent", "pic2speech")
        with urllib.request.urlopen(req2, timeout=300) as r2:
            return r2.read()


def main():
    tok = get_token()
    out = {}
    url = "https://api.github.com/repos/%s/%s/actions/runs/%s/artifacts" % (OWNER, REPO, RUN_ID)
    req = urllib.request.Request(url)
    req.add_header("Authorization", "token " + tok)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "pic2speech")
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read().decode("utf-8", "replace"))
    arts = data.get("artifacts", [])
    out["artifacts"] = [{"id": a["id"], "name": a["name"], "size": a["size_in_bytes"],
                         "expired": a["expired"]} for a in arts]
    if not arts:
        out["ok"] = False
        out["err"] = "no artifacts"
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    # 选最大的（就是 APK zip）
    art = max(arts, key=lambda a: a["size_in_bytes"])
    zurl = "https://api.github.com/repos/%s/%s/actions/artifacts/%s/zip" % (OWNER, REPO, art["id"])
    blob = fetch_artifact_zip(zurl, tok)
    out["downloaded_bytes"] = len(blob)

    os.makedirs(DEST_DIR, exist_ok=True)
    zf = zipfile.ZipFile(io.BytesIO(blob))
    names = zf.namelist()
    out["zip_entries"] = names
    apks = []
    for n in names:
        if n.lower().endswith(".apk"):
            target = os.path.join(DEST_DIR, os.path.basename(n))
            with open(target, "wb") as f:
                f.write(zf.read(n))
            apks.append({"path": target, "size": os.path.getsize(target)})
    out["apks"] = apks
    out["ok"] = bool(apks)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
