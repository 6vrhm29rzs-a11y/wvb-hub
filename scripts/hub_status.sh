#!/usr/bin/env bash
# Is the hub up, and is the private link to it working?
#
# ⚠ ONE COMMAND, BECAUSE "IS IT REACHABLE?" HAS FOUR ANSWERS. The server, the
# tailnet, the proxy and the allowlist are separate things, and when the phone
# shows nothing it is not obvious which one is missing. This says which.
#
# Read-only: it starts nothing and changes nothing.
set -uo pipefail
PORT="${WVB_PORT:-8799}"
ok(){ printf "  \033[32m✓\033[0m %s\n" "$1"; }
no(){ printf "  \033[31m✗\033[0m %s\n" "$1"; }
hm(){ printf "  \033[33m•\033[0m %s\n" "$1"; }

echo "WVB HUB STATUS"
echo "──────────────────────────────────────────────────────────────"

# 1. the local server
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  PID=$(lsof -nP -tiTCP:"$PORT" -sTCP:LISTEN | head -1)
  BINDADDR=$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN | awk 'NR==2{print $9}')
  ok "server listening on $BINDADDR (pid $PID)"
  case "$BINDADDR" in
    127.0.0.1:*|[*)  ;;
    *) no "  ⚠ NOT bound to loopback -- expected 127.0.0.1:$PORT" ;;
  esac
  code=$(curl -s -o /dev/null -w "%{http_code}" -m 6 "http://127.0.0.1:$PORT/START-HERE.html" || echo 000)
  [ "$code" = "200" ] && ok "page answers on localhost ($code)" || no "page did not answer ($code)"
else
  no "server NOT running on port $PORT"
  echo "      start it:  python3 scripts/live_server.py"
fi

# 2. the chat key (read at launch, so this is about the running process)
if [ -n "${ANTHROPIC_API_KEY:-}" ]; then ok "ANTHROPIC_API_KEY present in this shell"
else hm "no ANTHROPIC_API_KEY in this shell — Ask Digby will be off"; fi

# 3. the allowlist
if [ -n "${WVB_TRUSTED_HOSTS:-}" ]; then ok "WVB_TRUSTED_HOSTS = $WVB_TRUSTED_HOSTS"
else hm "WVB_TRUSTED_HOSTS unset — localhost only (phone will 403 on APIs)"; fi

# 4. tailscale
if command -v tailscale >/dev/null 2>&1; then
  if tailscale status >/dev/null 2>&1; then
    DNS=$(tailscale status --json 2>/dev/null | python3 -c 'import json,sys;d=json.load(sys.stdin);print((d.get("Self") or {}).get("DNSName","").rstrip("."))' 2>/dev/null)
    ok "tailscale up${DNS:+ as $DNS}"
    if tailscale serve status >/dev/null 2>&1 && [ -n "$(tailscale serve status 2>/dev/null)" ]; then
      ok "tailscale serve configured:"
      tailscale serve status 2>/dev/null | sed 's/^/      /'
      if [ -n "$DNS" ]; then
        code=$(curl -s -o /dev/null -w "%{http_code}" -m 10 "https://$DNS/START-HERE.html" || echo 000)
        [ "$code" = "200" ] && ok "HTTPS hub answers at https://$DNS ($code)" \
                            || no "HTTPS hub did not answer at https://$DNS ($code)"
      fi
      # ⚠ THE MISMATCH THAT LOOKS LIKE A BROKEN SITE. Serve preserves the
      # original Host, so the tailnet name must be in the allowlist or every
      # private endpoint 403s while the page itself loads fine.
      if [ -n "$DNS" ] && [ -n "${WVB_TRUSTED_HOSTS:-}" ]; then
        case ",${WVB_TRUSTED_HOSTS}," in
          *",$DNS,"*) ok "allowlist covers $DNS" ;;
          *) no "allowlist does NOT contain $DNS — APIs will 403 from the phone" ;;
        esac
      fi
    else
      hm "tailscale serve not configured"
      echo "      set it up:  tailscale serve --bg --https=443 http://127.0.0.1:$PORT"
    fi
    # ⚠ FUNNEL IS THE PUBLIC ONE. It must stay off.
    if tailscale funnel status 2>/dev/null | grep -qi "http"; then
      no "⚠ TAILSCALE FUNNEL APPEARS ACTIVE — this exposes the hub publicly"
    else
      ok "funnel off (hub is not public)"
    fi
  else
    no "tailscale installed but not connected — open the app and sign in"
  fi
else
  hm "tailscale not installed — Mac-only access for now"
  echo "      install:  brew install --cask tailscale"
fi
echo "──────────────────────────────────────────────────────────────"
