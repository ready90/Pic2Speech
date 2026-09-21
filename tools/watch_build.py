# -*- coding: utf-8 -*-
"""取仓库最新一次 workflow run，等它结束，输出步骤结论并下载日志。"""
import io
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
import zipfile

OWNER, REPO = "ready90", "Pic2Speech"
MAX_WAIT = int(sys.argv[1]) if len(sys.argv) > 1 else 2400


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


def get(url, tok):
    req = urllib.request.Request(url)
    req.add_header("Authorization", "token " + tok)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "pic2speech")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def get_bytes(url, tok):
    req = urllib.request.Request(url)
    req.add_header("Authorization", "token " + tok)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "pic2speech")
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read()


def main():
    tok = get_token()
    out = {}
    runs = get("https://api.github.com/repos/%s/%s/actions/runs?per_page=1" % (OWNER, REPO), tok)
    run = runs["workflow_runs"][0]
    rid = run["id"]
    out["run_id"] = rid
    out["created"] = run["created_at"]
    out["commit"] = (run.get("head_commit") or {}).get("message")
    out["polls"] = []

    deadline = time.time() + MAX_WAIT
    while time.time() < deadline:
        try:
            r = get("https://api.github.com/repos/%s/%s/actions/runs/%s" % (OWNER, REPO, rid), tok)
            out["polls"].append({"t": time.strftime("%H:%M:%S"), "status": r.get("status"),
                                 "conclusion": r.get("conclusion")})
            if r.get("status") == "completed":
                out["final"] = r.get("conclusion")
                break
        except Exception as e:
            out["polls"].append({"t": time.strftime("%H:%M:%S"), "err": str(e)[:100]})
        time.sleep(30)

    if out.get("final") is None:
        out["final"] = "TIMEOUT"

    try:
        jobs = get("https://api.github.com/repos/%s/%s/actions/runs/%s/jobs" % (OWNER, REPO, rid), tok)
        out["jobs"] = [{"job": j["name"], "conclusion": j["conclusion"],
                        "steps": [{"n": s["number"], "name": s["name"], "conclusion": s["conclusion"]}
                                  for s in j.get("steps", [])]}
                       for j in jobs.get("jobs", [])]
    except Exception as e:
        out["jobs_err"] = str(e)[:200]

    try:
        data = get_bytes("https://api.github.com/repos/%s/%s/actions/runs/%s/logs" % (OWNER, REPO, rid), tok)
        zf = zipfile.ZipFile(io.BytesIO(data))
        logdir = os.path.join(os.environ.get("TEMP", "."), "ghlogs_%s" % rid)
        os.makedirs(logdir, exist_ok=True)
        for n in zf.namelist():
            with open(os.path.join(logdir, n.replace("/", "__")), "wb") as f:
                f.write(zf.read(n))
        out["logdir"] = logdir
        out["log_files"] = zf.namelist()
    except Exception as e:
        out["log_err"] = str(e)[:200]

    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
