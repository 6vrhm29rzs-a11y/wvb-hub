# Private ballot backup

`data/ballots_*.jsonl` is git-ignored in this public repository — the ranking,
the private per-team notes and the written reasons for overruling the model are
not publishable. Ignored also means **unbacked-up**, existing on one disk. This
is the copy.

## Shape

    <this repo>/data/ballots_<season>.jsonl      CANONICAL, local, append-only
              ↓  copy (never move)
    ~/wvb-ballot-backup/ballots/…                a plain git repo
              ↓  git push
    a PRIVATE GitHub repository

The private repo holds **only** `ballots/` and a README. No project source, no
NCAA data, no dashboard, no credentials.

⚠ **No URL or credential for the private repo appears anywhere in this public
repository, and that is structural rather than careful.** `ballot_backup.py`
never names a destination: it runs `git push` inside the backup directory, so
the remote comes from that directory's own `.git/config`, outside this project.
The directory itself is found from `$WVB_BALLOT_BACKUP`, defaulting to a path
under `$HOME` — so not even an absolute local path is written down here.

## When it runs

On save, from the Ballot Workshop, on Cody's Mac. **Never from GitHub Actions**
— the daily job publishes the public website, has no business touching a
private backup, and holds no credentials for it.

## Status, and why it is reported separately

Saving locally and backing up are two facts, so the workshop states them
separately:

| shown | meaning |
|---|---|
| `Saved · N on file · backed up` | on disk **and** pushed to the private repo |
| `Saved · N on file · BACKUP PENDING — <reason>` | **the ballot is saved**; the copy is not |
| `Saved in this browser only …` | the local server is not running; nothing is on disk |

A pending backup never means a lost ballot. Offline, a missing backup
directory, a rejected push and a timeout all land in `pending` with the reason
attached — never a green tick over a backup that did not happen.

## Restoring

    cp ~/wvb-ballot-backup/ballots/ballots_2026.jsonl  data/ballots_2026.jsonl

Then open the Ballot Workshop: it reads the file on load, so the history and
the week-to-week comparison come back with it. The file is JSON Lines — one
ballot per line, newest last — so it can be read or edited by hand.

## First-time setup on a new machine

    git clone <the private repo> ~/wvb-ballot-backup

That is all `ballot_backup.py` needs; it discovers the remote from there.

## Checking without changing anything

    python3 scripts/ballot_backup.py status
