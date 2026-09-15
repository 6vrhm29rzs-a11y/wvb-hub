#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local backups for the files git cannot carry, plus a tree-state report.

Cody, 2026-09-13: "make sure all of the local files in
/Users/codyrose/Womens_College_Volleyball_2026 is updated and we have backup
logs and files and saves just in case we need to move back a step or redo
something or something for you to reference in case i ask what's next to do."

WHAT THIS IS AND IS NOT. Git already versions everything it tracks, and a
second copy of a tracked file is not a backup -- it is a stale duplicate that
will one day be restored over a newer commit. So this backs up exactly the
files that are DELIBERATELY gitignored and CANNOT be regenerated:

  * Cody's own writing -- his notes log, his weekly ballots. Private because
    this repository is PUBLIC, which is also why git is not an option.
  * Manually captured outside snapshots (FIGstats, Massey, transcribed TV
    listings). These are browser captures of pages that change; the capture
    cannot be retaken for a date that has passed.

⚠ IT REFUSES TO COPY ANYTHING THAT LOOKS LIKE A CREDENTIAL. Cody/data holds
an API key file. A backup directory quietly accumulating copies of a key is a
worse outcome than no backup at all, so key-shaped names are skipped by
pattern and the skip is PRINTED rather than silent.

⚠ A DERIVED FILE IS NEVER BACKED UP. data/*.json artifacts rebuild from
data/raw/ plus the scripts, both of which git carries. Backing them up would
be storing an answer instead of the question.

Snapshots are timestamped directories under Cody/backups/, newest kept, older
ones pruned past KEEP. Each carries a manifest with a sha256 per file, so
"did this change" is answerable without diffing by eye.

Run: python3 scripts/backup_local.py            (snapshot + report)
     python3 scripts/backup_local.py --report   (report only, no writes)
     python3 scripts/backup_local.py --if-stale (skip if one is recent)

The refresh loop calls the --if-stale form, so a snapshot lands roughly daily
without the 20-minute cycle minting -- and then pruning -- dozens of identical
copies a day. A backup rotation that churns is a backup rotation that throws
away the history it exists to keep.
"""

import datetime
import fnmatch
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKUPS = os.path.join(REPO, "Cody", "backups")
KEEP = 14
STALE_HOURS = 12

# gitignored AND irreplaceable. A glob, never a hand-listed filename: the
# ballot ignore rule already carries the lesson that a rule naming 2026
# protects nothing on 1 January.
# WARN: THE BALLOTS ARE NOT HERE, AND THAT IS DELIBERATE. `ballot_backup.py`
# already mirrors `data/ballots_*.jsonl` into a private repository OFF this
# disk, which is strictly better than a snapshot folder beside the original.
# Listing them here too would be two answers to one question -- the R4 trap
# this project keeps paying for -- and the weaker answer would be the one
# somebody restored from. It also tripped `test_ballot`'s model-isolation
# guard, which was right to notice a new script naming the ballot path.
SOURCES = (
    "Cody/data/*.jsonl",
    "Cody/data/*.txt",
    "Cody/data/*.json",
    # Cody's ChatGPT drop folder: gitignored (other people's writing on a
    # public repo) and NOT regenerable -- he pastes each brief once.
    "Cody dropbox of Chat GPT prompts/*",
    # the Claude<->Codex handoff record: gitignored, authoritative, and the
    # only copy of the exchange.
    "handoff/*.md",
    "handoff/*.jsonl",
    "handoff/msg/*",
)
# ⚠ NEVER COPIED, AND THE SKIP IS ANNOUNCED.
SECRET_LIKE = ("*key*", "*token*", "*secret*", "*credential*", "*.pem",
               "*password*")


def _secretish(name):
    low = os.path.basename(name).lower()
    return any(fnmatch.fnmatch(low, pat) for pat in SECRET_LIKE)


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _git(*args):
    try:
        return subprocess.run(("git",) + args, cwd=REPO, capture_output=True,
                              text=True).stdout.strip()
    except OSError:
        return ""


def sources():
    import glob
    out = []
    for pat in SOURCES:
        for p in sorted(glob.glob(os.path.join(REPO, pat))):
            if os.path.isfile(p):
                out.append(p)
    return out


def report():
    """What state the tree is in, in plain English."""
    print("TREE STATE")
    print("  (ballots are backed up separately and off this disk by "
          "scripts/ballot_backup.py)")
    dirty = _git("status", "--porcelain")
    mod = [l for l in dirty.splitlines() if not l.startswith("??")]
    untracked = [l[3:] for l in dirty.splitlines() if l.startswith("??")]
    print("  modified/staged files not yet committed : %d" % len(mod))
    # ⚠ UNTRACKED-AND-NOT-IGNORED IS THE DANGEROUS CATEGORY. An ignored file
    # is ignored on purpose and this script backs the important ones up; an
    # untracked file that git WOULD carry is work nobody has committed and
    # nobody has backed up either.
    print("  untracked files git would carry         : %d%s"
          % (len(untracked),
             ("  <- commit or ignore these" if untracked else "")))
    for u in untracked[:12]:
        print("      %s" % u)
    local = _git("rev-parse", "HEAD")[:7]
    remote = _git("rev-parse", "origin/main")[:7]
    ahead = _git("rev-list", "--count", "origin/main..HEAD")
    print("  local HEAD %s  origin/main %s" % (local or "?", remote or "?"))
    if ahead and ahead != "0":
        print("  %s local commit(s) are NOT on origin -- git push is Cody's "
              "command to run, never mine" % ahead)
    else:
        print("  local and origin/main agree")
    return len(untracked)


def snapshot():
    files = sources()
    if not files:
        print("\nBACKUP: nothing to back up (no private files on disk yet)")
        return 0
    stamp = datetime.datetime.now().strftime("%Y-%m-%dT%H%M")
    dest = os.path.join(BACKUPS, stamp)
    manifest = {"taken": stamp, "files": []}
    copied = skipped = 0
    for src in files:
        rel = os.path.relpath(src, REPO)
        if _secretish(src):
            print("  SKIPPED (credential-shaped name): %s" % rel)
            skipped += 1
            continue
        out = os.path.join(dest, rel)
        d = os.path.dirname(out)
        if not os.path.isdir(d):
            os.makedirs(d)
        shutil.copy2(src, out)
        manifest["files"].append({"path": rel, "bytes": os.path.getsize(src),
                                  "sha256": _sha(src)})
        copied += 1
    io.open(os.path.join(dest, "manifest.json"), "w", encoding="utf-8").write(
        json.dumps(manifest, indent=1, ensure_ascii=False))
    print("\nBACKUP: %d files -> Cody/backups/%s  (%d skipped)"
          % (copied, stamp, skipped))

    # ⚠ PRUNE, BUT SAY WHAT WAS PRUNED. A retention policy that removes things
    # quietly is indistinguishable from a bug that removes things.
    snaps = sorted(d for d in os.listdir(BACKUPS)
                   if os.path.isdir(os.path.join(BACKUPS, d)))
    for old in snaps[:-KEEP]:
        shutil.rmtree(os.path.join(BACKUPS, old))
        print("  pruned older snapshot %s (keeping the newest %d)" % (old, KEEP))
    return copied


def newest_age_hours():
    """Hours since the newest snapshot, or None when there is none."""
    if not os.path.isdir(BACKUPS):
        return None
    snaps = sorted(d for d in os.listdir(BACKUPS)
                   if os.path.isdir(os.path.join(BACKUPS, d)))
    if not snaps:
        return None
    try:
        t = datetime.datetime.strptime(snaps[-1], "%Y-%m-%dT%H%M")
    except ValueError:
        return None
    return (datetime.datetime.now() - t).total_seconds() / 3600.0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    quiet = "--if-stale" in argv
    if not quiet:
        report()
    if "--report" in argv:
        return 0
    if quiet:
        age = newest_age_hours()
        if age is not None and age < STALE_HOURS:
            print("backup: newest snapshot is %.1fh old (< %dh) -- skipping"
                  % (age, STALE_HOURS))
            return 0
    snapshot()
    return 0


if __name__ == "__main__":
    sys.exit(main())
