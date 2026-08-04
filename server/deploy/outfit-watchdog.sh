#!/usr/bin/env bash
# outfit-watchdog.sh — catch the failure modes systemd structurally cannot see.
#
# WHY THIS EXISTS (incident 2026-07-29 → 2026-08-04, six silent days):
# the DGX's Tailscale node key expired. The server had already bound
# 100.112.171.54 successfully at boot, so when the address disappeared from the
# interface the process kept running and the socket kept reporting LISTEN — every
# connection just timed out. `Restart=on-failure` never fired because nothing
# failed. The morning push fell back for six days and nobody knew.
#
# systemd can only see "did the process exit". This checks what actually matters:
# can something reach the endpoint the phone reaches.
#
#   1. Tailscale is Running and still owns the expected IP
#   2. GET /health answers, and answers ok:true
#   3. the node key is not about to expire (the root cause of the incident) —
#      warn EARLY, because once it expires only a human with a browser can fix it
#
# Self-heals what it can (restart the unit), and is deliberately quiet: it
# notifies on STATE CHANGE, plus one reminder a day while still broken. A
# watchdog that messages every 5 minutes gets muted, and a muted watchdog is
# worse than none.
#
# Install: see server/deploy/README-watchdog.md

set -uo pipefail

EXPECTED_IP="${OA_IP:-100.112.171.54}"
PORT="${OA_PORT:-8787}"
UNIT="${OA_UNIT:-outfit-advisor}"
NOTIFY="${OA_NOTIFY:-$HOME/Project/outfit-advisor/scripts/notify_telegram.sh}"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/outfit-advisor"
STATE="$STATE_DIR/watchdog.state"
# The key-expiry warning is an INDEPENDENT concern from up/down and needs its own
# state. Sharing one file made a key warning look like a failure, so the next
# healthy check announced a "recovery" from an outage that never happened.
KEYSTATE="$STATE_DIR/keywarn.state"
KEY_WARN_DAYS="${OA_KEY_WARN_DAYS:-21}"
REMIND_SECS=$((24 * 3600))

mkdir -p "$STATE_DIR"

log() { printf '%s %s\n' "$(date -Is)" "$*"; }

# notify <state-key> <message> [state-file]
# Sends only when <state-key> differs from the last one, or a day has passed.
notify() {
  local key="$1" msg="$2" sf="${3:-$STATE}" last_key="" last_at=0 now
  now=$(date +%s)
  if [[ -r "$sf" ]]; then
    last_key=$(sed -n '1p' "$sf" 2>/dev/null)
    last_at=$(sed -n '2p' "$sf" 2>/dev/null)
    [[ "$last_at" =~ ^[0-9]+$ ]] || last_at=0
  fi
  if [[ "$key" == "$last_key" && $((now - last_at)) -lt $REMIND_SECS ]]; then
    log "state unchanged ($key), not re-notifying"
    printf '%s\n%s\n' "$key" "$last_at" > "$sf"
    return 0
  fi
  printf '%s\n%s\n' "$key" "$now" > "$sf"
  if [[ -x "$NOTIFY" ]]; then
    "$NOTIFY" "$msg" >/dev/null 2>&1 || log "telegram notify FAILED"
  else
    log "no notifier at $NOTIFY"
  fi
  log "notified: $key"
}

# ---- 1. Tailscale ----------------------------------------------------------
ts_json=$(timeout 20 tailscale status --json 2>/dev/null)
if [[ -z "$ts_json" ]]; then
  log "FAIL tailscale: no status output"
  notify "tailscale-down" "🔴 OutfitAdvisor: Tailscale is not responding on the DGX. The morning push cannot reach the server. Run: tailscale up --operator=\$USER"
  exit 1
fi

read -r backend has_ip key_days <<<"$(printf '%s' "$ts_json" | python3 -c '
import json,sys,datetime as dt
d=json.load(sys.stdin); s=d.get("Self",{}) or {}
ips=s.get("TailscaleIPs") or []
exp=s.get("KeyExpiry")
days="none"
if exp:
    t=dt.datetime.fromisoformat(exp.replace("Z","+00:00"))
    days=str((t-dt.datetime.now(dt.timezone.utc)).days)
print(d.get("BackendState","?"), ("yes" if "'"$EXPECTED_IP"'" in ips else "no"), days)
' 2>/dev/null)"

if [[ "$backend" != "Running" || "$has_ip" != "yes" ]]; then
  log "FAIL tailscale: backend=$backend has_ip=$has_ip"
  notify "tailscale-logged-out" "🔴 OutfitAdvisor: the DGX has lost its Tailscale address ($EXPECTED_IP). State: $backend. The server is bound to an address that no longer exists, so the phone gets nothing — this is exactly the six-day silent outage from July. Fix on the DGX: tailscale up --operator=\$USER"
  exit 1
fi

# The root cause, caught before it bites. Once the key expires, only a human with
# a browser can recover it — so the warning has to arrive well ahead of time.
if [[ "$key_days" =~ ^-?[0-9]+$ ]] && (( key_days <= KEY_WARN_DAYS )); then
  log "WARN tailscale key expires in $key_days days"
  notify "key-expiring" "🟠 OutfitAdvisor: the DGX's Tailscale node key expires in $key_days days. When it does, the server goes unreachable and the morning push silently falls back. Disable key expiry for spark-d28c in the Tailscale admin console (Machines → ⋯ → Disable key expiry)." "$KEYSTATE"
fi

# ---- 2. the endpoint the phone actually calls -------------------------------
probe() { timeout 20 curl -fsS --max-time 15 "http://$EXPECTED_IP:$PORT/health" 2>/dev/null; }

health=$(probe)
if [[ -z "$health" ]]; then
  log "health FAILED, restarting $UNIT"
  systemctl --user restart "$UNIT" 2>/dev/null
  sleep 5
  health=$(probe)
  if [[ -z "$health" ]]; then
    log "FAIL server: still unreachable after restart"
    notify "server-down" "🔴 OutfitAdvisor: /health is unreachable on $EXPECTED_IP:$PORT and a restart did not fix it. Tailscale is fine, so this is the app. Check: journalctl --user -u $UNIT -n 50"
    exit 1
  fi
  log "recovered after restart"
  notify "server-restarted" "🟡 OutfitAdvisor: the /advice server was unreachable and the watchdog restarted it. It is answering again."
  exit 0
fi

# ---- 3. degraded but alive --------------------------------------------------
# vLLM down is not an outage: advice falls back to the on-device rule engine. It
# IS worth knowing, because the advice quietly gets worse.
if printf '%s' "$health" | grep -q '"vllm":false'; then
  log "WARN vllm down (advice will fall back to the rule engine)"
  notify "vllm-down" "🟠 OutfitAdvisor: the server is up but vLLM is not answering, so outfit advice falls back to the rule engine (no LLM text, no closet picks)."
  exit 0
fi

log "OK backend=$backend ip=$has_ip key_days=$key_days health=$health"

# "Recovered" is only news if something was broken. On a fresh install, or on the
# thousandth consecutive healthy run, silence is the correct output — announcing
# health is how a watchdog trains you to ignore it.
prev=""
[[ -r "$STATE" ]] && prev=$(sed -n '1p' "$STATE" 2>/dev/null)
if [[ -n "$prev" && "$prev" != "ok" ]]; then
  notify "ok" "🟢 OutfitAdvisor: recovered — Tailscale up, /health ok, vLLM ok."
else
  printf '%s\n%s\n' "ok" "$(date +%s)" > "$STATE"
fi
exit 0
