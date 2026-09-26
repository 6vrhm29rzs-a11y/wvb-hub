# Report schedule (PROPOSED — not installed)

Replaces the 07:00 / 23:30 jobs per `Cody/coordination/decisions/2026-09-26-report-schedule-and-variants.md`.

- `com.codyrose.wvb-mail-morning.plist` — 05:40 PT prepares, 06:00 PT dispatches → `scripts/mail_scheduler.py morning`
- `com.codyrose.wvb-mail-night.plist` — every 15 min 17:00–21:30 PT (final attempt starts 21:15; 21:30 is a late retry) → `scripts/mail_scheduler.py night-check`
  (sends early once the whole slate is final and logged; otherwise at 21:30; once per date)

Times follow the Mac's local clock (America/Los_Angeles), so DST is handled by macOS.

Install (only after approval; this writes outside the project, to ~/Library/LaunchAgents):

    for j in morning night; do
      launchctl bootout gui/$(id -u)/com.codyrose.wvb-mail-$j 2>/dev/null
      cp ops/launchd/com.codyrose.wvb-mail-$j.plist ~/Library/LaunchAgents/
      launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.codyrose.wvb-mail-$j.plist
    done

Sending is still controlled by `Cody/data/mail_transport.txt` (off = build and keep, never send).
