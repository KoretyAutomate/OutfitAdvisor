# Outfit Advisor watchdog

Catches the failure modes systemd structurally cannot see.

## The incident it exists for (2026-07-29 → 2026-08-04)

The DGX's Tailscale node key expired. The server had already bound
`100.112.171.54` at boot, so when the address left the interface the process kept
running and the socket kept reporting `LISTEN` — every connection simply timed
out. `Restart=on-failure` never fired, because nothing failed. The morning push
silently fell back for six days and the outage was found only because the user
mentioned the weather looked wrong.

systemd answers "did the process exit". That was never the question. The question
is **can something reach the endpoint the phone reaches**, which is what this
checks.

## What it checks, every 5 minutes

1. **Tailscale** is `Running` and still owns the expected IP.
2. **`GET /health`** answers over that IP, with `ok:true`.
3. **Node key expiry** — warns at 21 days remaining. This is the root cause, and
   once the key actually expires only a human with a browser can recover it, so
   the warning has to arrive well ahead of the deadline.
4. **The PHONE's tailnet presence** — warns once the Pixel has been offline for
   6+ hours. Added 2026-08-14, after it dropped off the tailnet for 15 hours and
   every check here stayed green: unit healthy, `/health` 200, Tailscale up. The
   server being reachable *from itself* proves nothing about the device that has
   to reach it, and the user meets that failure as "couldn't reach the server".

## What it does about it

| Condition | Action |
|---|---|
| Tailscale down / wrong IP | Notify. Cannot self-heal — needs `tailscale up --operator=$USER` |
| `/health` unreachable | Restart `outfit-advisor`, re-probe, notify whether it recovered |
| vLLM down | Notify as degraded — advice still works via the rule engine |
| Key expiring ≤21d | Notify once, then at most daily |
| Phone off the tailnet ≥6h | Notify — cannot self-heal, needs Tailscale reconnected on the phone |
| All healthy | **Say nothing** |

Notifications go to Telegram via `scripts/notify_telegram.sh` (the ClaudeBridge
bot), **on state change only**, plus one reminder a day while still broken. A
watchdog that messages every five minutes gets muted, and a muted watchdog is
worse than none. Silence when healthy is deliberate for the same reason.

Reachability, key-expiry and phone-presence are tracked in **separate** files
(`watchdog.state`, `keywarn.state`, `phone.state`) under `~/.local/state/outfit-advisor/`.
Sharing one file made a key warning look like an outage, so the next healthy
check announced a "recovery" from something that never broke.

## Install

```bash
cp server/deploy/outfit-watchdog.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now outfit-watchdog.timer
loginctl enable-linger korety     # survives logout/reboot (same requirement as the server)
```

## Operate

```bash
systemctl --user list-timers outfit-watchdog.timer    # when it next runs
journalctl --user -u outfit-watchdog -n 30            # what it has been finding
systemctl --user start outfit-watchdog.service        # run one check right now
```

## Test it without waiting for a real outage

```bash
# healthy -> silent
OA_NOTIFY=/nonexistent server/deploy/outfit-watchdog.sh

# simulate unreachable (nothing bound on 8799): restarts, fails, exits 1
OA_PORT=8799 OA_NOTIFY=/nonexistent server/deploy/outfit-watchdog.sh

# force the key-expiry warning regardless of the real expiry
OA_KEY_WARN_DAYS=365 OA_NOTIFY=/nonexistent server/deploy/outfit-watchdog.sh
```

Drop `OA_NOTIFY=/nonexistent` to exercise the real Telegram path.

## Overrides

`OA_IP`, `OA_PORT`, `OA_UNIT`, `OA_NOTIFY`, `OA_KEY_WARN_DAYS`,
`OA_PHONE_HOST` (default `pixel`), `OA_PHONE_WARN_HOURS` (default `6`).

## What it does NOT cover

The watchdog proves the server is reachable **from the DGX**. It cannot prove the
phone can reach it, nor that the morning push fires — that path has its own
history of failing silently (an 11 s watchdog guarding a 30 s call, fixed
2026-08-02). Only a real morning fire verifies that.
