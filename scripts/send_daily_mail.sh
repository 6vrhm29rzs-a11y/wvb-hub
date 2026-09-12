#!/bin/sh
# Send one daily report. Called by launchd (see com.codyrose.wvb-mail-*.plist).
#
#   send_daily_mail.sh night|morning
#
# ⚠ IT BUILDS THE REPORT FROM THE PAGE, SO THE PAGE MUST BE FRESH FIRST. The
# report reads the built page's own TEAMS payload; if the pipeline has not run
# the mail would faithfully report yesterday. local_refresh is cheap when
# nothing has changed (it fingerprints on FINALS ONLY and rebuilds nothing if
# none landed), so it is run unconditionally here rather than guessing.
#
# ⚠ A FAILURE MUST BE LOUD IN THE LOG AND SILENT IN THE INBOX. Sending a
# half-built report is worse than sending nothing: a mail cannot be corrected
# after the fact the way a page can. So a non-zero build exits WITHOUT sending.
set -u
KIND="${1:-night}"
REPO="/Users/codyrose/Womens_College_Volleyball_2026"
LOG="$HOME/Library/Logs/wvb-mail.log"
export WVB_SEASON=2026
cd "$REPO" || exit 1

echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z')  $KIND ===" >> "$LOG"

python3 scripts/local_refresh.py >> "$LOG" 2>&1 \
  || echo "  refresh failed -- reporting from the page as it stands" >> "$LOG"

BODY="$(mktemp)"
if ! python3 scripts/mail_report.py "$KIND" > "$BODY" 2>>"$LOG"; then
    echo "  BUILD FAILED -- nothing sent" >> "$LOG"
    rm -f "$BODY"; exit 1
fi

LINES=$(wc -l < "$BODY")
# A report that lost its payload still "succeeds" and prints a header and two
# rules. Refuse to send a husk: the real ones run 35-75 lines.
if [ "$LINES" -lt 12 ]; then
    echo "  REPORT IS ONLY $LINES LINES -- looks empty, nothing sent" >> "$LOG"
    rm -f "$BODY"; exit 1
fi

case "$KIND" in
  night)   SUBJ="WVB Hub — Night Desk — $(date '+%Y-%m-%d')" ;;
  morning) SUBJ="WVB Hub — Morning Brief — $(date '+%Y-%m-%d')" ;;
  *)       SUBJ="WVB Hub — $KIND — $(date '+%Y-%m-%d')" ;;
esac

if python3 scripts/mailer.py "$SUBJ" < "$BODY" >> "$LOG" 2>&1; then
    echo "  sent ($LINES lines)" >> "$LOG"
else
    echo "  SEND FAILED -- see the error above. If it is 534 WebLoginRequired," >> "$LOG"
    echo "  sign in to wvbhub.desk@gmail.com in a browser once; the app" >> "$LOG"
    echo "  password is fine, Google is holding the ACCOUNT." >> "$LOG"
    rm -f "$BODY"; exit 1
fi
rm -f "$BODY"
