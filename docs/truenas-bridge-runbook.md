# TrueNAS bridge migration — make the native app reach the Director

**Why:** The `Bare_OS` VM (192.168.1.41) and the TrueNAS host (192.168.1.40) both hang directly off
the physical NIC `enp3s0`, and there is no bridge on the box. TrueNAS wires VMs attached to a
host-owned physical NIC as **macvtap**, which by design blocks the host ⇄ its-own-VM path (both
still reach the rest of the LAN — that's why Billy reaches `.41` fine, but the TrueNAS host, and any
app running on it, cannot). Putting `enp3s0` behind a bridge and attaching the VM to that bridge
removes the isolation.

Verified config as of 2026-07-22:
- `enp3s0` — physical, holds `192.168.1.40`, **no bridge members** (no `br0` exists)
- VMs on `enp3s0` (macvtap): `Bare_OS` (00:a0:98:41:f7:8e), `Proxmox_Backup`, `Coral`

## ⚠️ Before you start

- **Have console/IPMI or physical keyboard+monitor access to the TrueNAS box.** This changes the one
  interface the whole NAS rides on. If a step drops connectivity, you fix it at the console.
- Your safety net is TrueNAS's **60-second test-and-revert**: after "Test Changes" it auto-rolls back
  unless you confirm within the window. Do **not** "Save Permanently" until you've confirmed the UI
  still loads.
- Note current network: host `192.168.1.40`, gateway, on `enp3s0`.

## Steps

### 1. Create the bridge
- **Network → Interfaces → Add**
- Type: **Bridge**, Name: **`br0`**
- Bridge Members: **`enp3s0`**
- DHCP: off. Add alias **`192.168.1.40/24`** (same IP the host uses now).
- (Leave `enp3s0`'s own IP to be removed in the same batch — the UI moves it to the bridge.)

### 2. Take the IP off the raw NIC
- Edit **`enp3s0`** → remove its `192.168.1.40` alias / disable DHCP, so the address lives only on
  `br0`. Confirm the **default gateway** is still set (Network → Global Configuration if needed).

### 3. Test — the critical part
- **Test Changes.** The UI will blip. Reload `https://192.168.1.40` — if it comes back, you're good;
  click **Save Changes** (permanent) within the 60s window. If it *doesn't* come back, do nothing —
  it auto-reverts in 60s and you're back where you started.

### 4. Re-point the VM(s) at the bridge
- **Virtualization → Bare_OS → Devices → the NIC → Edit**
- Change **Attach NIC** from `enp3s0` to **`br0`**. Save.
- **Restart Bare_OS** (or stop/start the NIC) so it re-attaches.
- Optional but recommended: do the same for `Proxmox_Backup` and `Coral` to clear the same latent
  isolation for them.

## Verify

From the TrueNAS host shell (System Settings → Shell), or just re-check the app:
```
# should now succeed from the host itself:
nc -vz 192.168.1.41 9101      # (or): curl -s http://192.168.1.41/bareos-webui/ -o /dev/null -w '%{http_code}\n'
```
Then hit the native app — the container is host-networked, so once the host can reach `.41` it works.
If it was mid-poll during the change, restart it: **Apps → bareos-dash → Restart**. Confirm:
```
curl -s http://192.168.1.40:5000/api/status     # expect {"connected":true,...}
```

## Rollback

- Before step 3 confirm: nothing is permanent — the 60s revert restores everything.
- After confirm: to undo, re-point the VM NIC back to `enp3s0`, move `192.168.1.40` back onto
  `enp3s0`, delete `br0`. Same test-window safety applies.

## If you'd rather not touch host networking

The working dashboard on Billy (`http://192.168.1.19:5056`) needs none of this. The bridge is only
required to make the *TrueNAS-native* app reach the Director. See `../STATUS.md`.
