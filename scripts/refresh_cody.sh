#!/bin/sh
# Rebuild everything Cody looks at, in order, from whatever data is on disk.
# Safe to re-run. Stops at the first failure rather than publishing half a build.
set -e
cd "$(dirname "$0")/.."
export WVB_SEASON=2026
echo "== importing any dropped rosters =="
python3 scripts/import_dropped_rosters.py
echo
echo "== rebuilding =="
python3 scripts/venues.py
python3 scripts/availability.py
python3 scripts/predict_2026.py | tail -3
python3 scripts/simulate_season_2026.py | head -3
python3 scripts/score_predictions.py | tail -4
python3 scripts/join_players.py > /dev/null
python3 scripts/project_2026.py | tail -n +1
python3 scripts/build_vb.py | tail -2
python3 scripts/build_rankings_board.py
python3 scripts/build_hub.py
echo
echo "== gates =="
for t in scripts/test_*.py; do
  printf "%-34s " "$(basename "$t")"
  if python3 "$t" > /tmp/wvb_gate.out 2>&1; then echo PASS; else echo FAIL; tail -12 /tmp/wvb_gate.out; exit 1; fi
done
python3 scripts/provenance.py --check | tail -1
echo
echo "Open: $(pwd)/Cody/START-HERE.html"
echo "Live scores: python3 scripts/live_server.py   (then open the URL it prints)"
