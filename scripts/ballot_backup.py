#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mirror the local ballot file into a private backup repository.

    python3 scripts/ballot_backup.py          # sync this season
    python3 scripts/ballot_backup.py status   # what state is the backup in?

WHY A SEPARATE REPO. `data/ballots_*.jsonl` is git-ignored in the public
project, which is correct -- the ranking, the private per-team notes and the
written reasons for overruling the model are not publishable. But ignored also
means unbacked-up, existing on exactly one disk. This copies it somewhere
private.

⚠ THE LOCAL FILE IS CANONICAL AND THIS NEVER TOUCHES IT. Nothing here writes,
moves, truncates or reorders `data/ballots_*.jsonl`. It is read and copied.
A backup that can damage the thing it backs up is not a backup.

⚠ AND A FAILED SYNC IS NEVER REPORTED AS A SAVE. Every failure path returns
state "pending" with the reason, so the workshop can say "saved locally, backup
pending" rather than a green tick that means nothing. Offline, no remote, a
rejected push and a missing backup directory all land in the same honest place.

⚠ NO URL AND NO CREDENTIAL LIVES IN THIS FILE, and that is deliberate: this
script is committed to a PUBLIC repository. The destination is whatever remote
the backup directory itself already has configured, in its own .git/config,
outside this project. This code could not name the private repo if it wanted
to. The directory is found by env var, defaulting to a path under $HOME -- so
not even an absolute local path is hard-coded here.

NOT RUN BY CI, EVER. This is for saves made on Cody's Mac from the Ballot
Workshop. The daily GitHub Actions job publishes the public website and has no
business touching a private backup -- and no credentials for it either.

Python 3.9 target.
"""

import json
import os
import shutil
import subprocess
import sys
from typing import Dict, Optional

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))

# Where the backup working copy lives. Overridable, and never an absolute path
# written into a public file.
BACKUP_DIR = os.environ.get("WVB_BALLOT_BACKUP") or os.path.join(
    os.path.expanduser("~"), "wvb-ballot-backup")

SRC = os.path.join(REPO, "data", "ballots_%d.jsonl" % SEASON)
TIMEOUT = 25            # a hung network must not hang a ballot save


def _git(args, cwd):
    # type: (list, str) -> subprocess.CompletedProcess
    return subprocess.run(["git"] + args, cwd=cwd, capture_output=True,
                          text=True, timeout=TIMEOUT)


def status():
    # type: () -> Dict
    """Where the backup stands, without changing anything."""
    if not os.path.exists(SRC):
        return {"state": "nothing-to-back-up", "detail":
                "no ballot has been saved this season"}
    if not os.path.isdir(os.path.join(BACKUP_DIR, ".git")):
        return {"state": "pending", "detail":
                "no backup repository at %s" % BACKUP_DIR}
    dst = os.path.join(BACKUP_DIR, "ballots", os.path.basename(SRC))
    if not os.path.exists(dst):
        return {"state": "pending", "detail": "this season is not in the backup yet"}
    same = (open(SRC, "rb").read() == open(dst, "rb").read())
    if not same:
        return {"state": "pending", "detail": "the backup is behind the local file"}
    r = _git(["status", "--porcelain"], BACKUP_DIR)
    if r.returncode == 0 and r.stdout.strip():
        return {"state": "pending", "detail": "copied but not committed"}
    r = _git(["rev-list", "--count", "@{u}..HEAD"], BACKUP_DIR)
    if r.returncode == 0 and (r.stdout.strip() or "0") != "0":
        return {"state": "pending", "detail":
                "committed but not pushed (%s commit(s) ahead)" % r.stdout.strip()}
    return {"state": "synced", "detail": "backed up"}


def sync():
    # type: () -> Dict
    """Copy, commit and push. Never raises -- the caller has already saved.

    Returns {"state": "synced"|"pending"|"nothing-to-back-up", "detail": str}.
    """
    try:
        if not os.path.exists(SRC):
            return {"state": "nothing-to-back-up",
                    "detail": "no ballot file for %d" % SEASON}
        if not os.path.isdir(os.path.join(BACKUP_DIR, ".git")):
            return {"state": "pending", "detail":
                    "no backup repository at %s -- see docs/ballot_backup.md"
                    % BACKUP_DIR}

        dstdir = os.path.join(BACKUP_DIR, "ballots")
        if not os.path.isdir(dstdir):
            os.makedirs(dstdir)
        dst = os.path.join(dstdir, os.path.basename(SRC))
        # ⚠ COPY, NEVER MOVE. The local file is the canonical one and must be
        # exactly where it was when this returns, byte for byte.
        shutil.copy2(SRC, dst)

        rel = os.path.join("ballots", os.path.basename(SRC))
        r = _git(["add", rel], BACKUP_DIR)
        if r.returncode != 0:
            return {"state": "pending", "detail": "git add failed: %s"
                    % (r.stderr or "").strip()[:120]}

        r = _git(["status", "--porcelain"], BACKUP_DIR)
        if r.returncode == 0 and not r.stdout.strip():
            # already identical to what is committed; still confirm it is pushed
            return status()

        n = sum(1 for l in open(SRC, encoding="utf-8") if l.strip())
        r = _git(["commit", "-m",
                  "ballots %d: %d saved" % (SEASON, n)], BACKUP_DIR)
        if r.returncode != 0:
            return {"state": "pending", "detail": "commit failed: %s"
                    % ((r.stderr or r.stdout) or "").strip()[:120]}

        r = _git(["push", "-q", "origin", "HEAD"], BACKUP_DIR)
        if r.returncode != 0:
            # ⚠ COMMITTED LOCALLY, NOT PUSHED. Still "pending" -- the copy is
            # on the same disk as the original, which is not a backup.
            return {"state": "pending", "detail":
                    "saved and committed locally, push failed: %s"
                    % ((r.stderr or "").strip().splitlines() or [""])[-1][:120]}
        return {"state": "synced", "detail": "backed up (%d ballot(s))" % n}
    except subprocess.TimeoutExpired:
        return {"state": "pending", "detail": "backup timed out; local file is safe"}
    except Exception as e:                                    # noqa: BLE001
        return {"state": "pending", "detail": "%s; local file is safe" % e}


def main(argv):
    what = (argv[1] if len(argv) > 1 else "sync").lower()
    res = status() if what == "status" else sync()
    print("%-18s %s" % (res["state"], res["detail"]))
    print("  local  : %s" % os.path.relpath(SRC, REPO))
    print("  backup : %s" % BACKUP_DIR)
    return 0 if res["state"] in ("synced", "nothing-to-back-up") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
