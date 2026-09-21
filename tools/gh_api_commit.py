# -*- coding: utf-8 -*-
"""用 GitHub Git Data API 把一个或多个本地文件打成「单个提交」推到远程。

用途：当 github.com:443 被阻断（git push 不通）、但 api.github.com 可达时，
      仍然可以把本地改动推到 GitHub。

用法：
    python gh_api_commit.py "提交说明" 文件1 [文件2 ...]

文件路径为相对 WORKDIR 的相对路径。
"""
import base64
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error

OWNER, REPO, BRANCH = "ready90", "Pic2Speech", "main"
WORKDIR = r"D:\workbuddy-space\办公\图片转语音工具-Android"


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


def api(method, url, token, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "token " + token)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "pic2speech-api-commit")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            txt = r.read().decode("utf-8", "replace")
            return r.status, (json.loads(txt) if txt.strip() else {})
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, "EXC: %s" % e


def main():
    message = sys.argv[1]
    rel_paths = sys.argv[2:]
    tok = get_token()
    if not tok:
        print(json.dumps({"ok": False, "err": "no token"}, ensure_ascii=False))
        return
    base = "https://api.github.com/repos/%s/%s" % (OWNER, REPO)
    res = {}

    st, ref = api("GET", base + "/git/ref/heads/" + BRANCH, tok)
    if st != 200:
        print(json.dumps({"ok": False, "at": "get_ref", "status": st, "body": str(ref)[:300]},
                         ensure_ascii=False))
        return
    parent = ref["object"]["sha"]

    st, commit = api("GET", base + "/git/commits/" + parent, tok)
    if st != 200:
        print(json.dumps({"ok": False, "at": "get_commit", "status": st, "body": str(commit)[:300]},
                         ensure_ascii=False))
        return
    base_tree = commit["tree"]["sha"]

    entries = []
    for rp in rel_paths:
        local = os.path.join(WORKDIR, rp)
        with open(local, "rb") as f:
            raw = f.read()
        st, blob = api("POST", base + "/git/blobs", tok, {
            "content": base64.b64encode(raw).decode("ascii"),
            "encoding": "base64",
        })
        if st not in (200, 201):
            print(json.dumps({"ok": False, "at": "blob", "path": rp, "status": st,
                              "body": str(blob)[:300]}, ensure_ascii=False))
            return
        entries.append({"path": rp.replace("\\", "/"), "mode": "100644", "type": "blob",
                        "sha": blob["sha"]})
        res.setdefault("blobs", []).append(rp)

    st, tree = api("POST", base + "/git/trees", tok, {"base_tree": base_tree, "tree": entries})
    if st not in (200, 201):
        print(json.dumps({"ok": False, "at": "tree", "status": st, "body": str(tree)[:300]},
                         ensure_ascii=False))
        return

    st, newc = api("POST", base + "/git/commits", tok, {
        "message": message, "tree": tree["sha"], "parents": [parent],
    })
    if st not in (200, 201):
        print(json.dumps({"ok": False, "at": "commit", "status": st, "body": str(newc)[:300]},
                         ensure_ascii=False))
        return
    res["commit"] = newc["sha"]

    st, upd = api("PATCH", base + "/git/refs/heads/" + BRANCH, tok, {"sha": newc["sha"]})
    if st not in (200, 201):
        print(json.dumps({"ok": False, "at": "update_ref", "status": st, "body": str(upd)[:300]},
                         ensure_ascii=False))
        return

    res["ok"] = True
    res["ref_status"] = st
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
