# Status & handoff — 2026-07-22

Plain-language record of what got built, what's running, and the one thing that needs your hands.

## What this is

A dashboard to run and monitor your Bareos tape backups without opening bareos-webui. Flask app,
talks straight to the Bareos Director's console port (9101) on the `Bare_OS` VM (192.168.1.41)
using a dedicated, ACL-restricted console credential. Built almost entirely by Kimi K2 through the
dev-pipeline (Claude planned and adversarially reviewed; Kimi wrote every line of app code — zero
Claude-authored fallbacks across the whole build).

## What's working right now

**A live, working frontend at http://192.168.1.19:5056** (running on Billy as a Docker container,
`restart: unless-stopped`). Open it in your browser — you'll see four panels (jobs / history /
media / director), all populated with real data from your Director. The **run** button on each job
fires a real backup (with a confirm dialog first). Verified end to end: real jobs listed, a real
backup run triggered and landed in history, tape/media volume shown, injection attempts rejected.

## The one thing that needs you: TrueNAS-native placement

You wanted this to live *inside* TrueNAS (Apps section). I deployed it there as a custom app and it
runs (container healthy, dashboard loads) — **but it can't reach the Bareos Director**, while Billy,
your Windows box, and everything else on the LAN reach it fine.

**Why:** the only machine that can't reach the `Bare_OS` VM is the TrueNAS host itself. That's the
classic TrueNAS **macvtap host↔VM isolation** — a VM attached via macvtap is reachable by every
other device on the network *except its own hypervisor host*. Since a TrueNAS custom app runs on
the TrueNAS host's network, it inherits that blind spot. This is a networking property of how the
VM's NIC is attached, **not** a bug in the dashboard (identical image, identical env, works
perfectly on Billy).

**Options to make the TrueNAS-native app work (pick one when you're back):**
1. **Re-attach the `Bare_OS` VM NIC to a bridge** instead of macvtap, so the host can reach it.
   Cleanest, but it's a VM network change — do it at the console/with a fallback, since a wrong
   move can drop the VM off the network. I did **not** do this autonomously on your backup box.
2. **socat/relay** on Billy (TrueNAS app → Billy:9101 → Director). Works, but makes the
   "TrueNAS-native" app depend on Billy being up — a bit self-defeating.
3. **Just use the Billy deployment** (above) and skip TrueNAS-native. It's a URL/bookmark instead
   of a TrueNAS Apps tile, but it's fully working today with zero extra steps.

The TrueNAS custom app (`bareos-dash`) is left deployed but idle — it'll start working the moment
option 1 is done, or you can delete it in one click.

## Bareos-side change I made

Created a new named console on the Director: `dashboard`, `Profile = operator` (can run/list/status;
**cannot** delete/purge/prune/configure). Its password is in the gitignored `.env` here and passed
to the containers as env vars — never committed. This is the credential the dashboard authenticates
with, deliberately scoped so a dashboard bug can't do worse than trigger an unwanted backup.

## Repo / CI

- GitHub: https://github.com/Jemplayer82/bareos-truenas-dash (public)
- CI builds `ghcr.io/jemplayer82/bareos-truenas-dash:latest` + `:<sha>` on push to master,
  gated by a gitleaks secret scan. Image is public (anonymous pull works — TrueNAS/Billy need no
  registry login).
- 48 tests, all green. Close-out gates (verify/security/cruft/docs) all pass.
