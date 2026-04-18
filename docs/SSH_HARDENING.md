# SSH Hardening — c240

Applied Session 68 (2026-04-19) after a connection-storm incident where parallel
SSH attempts from Claude Code, VS Code, monitoring scripts, and Tailscale relay
wobble combined to saturate c240's sshd pre-auth connection queue. sshd's
MaxStartups default (10:30:100) was too low for multi-tool workflows.

## Symptoms

- `ssh: connect to host ... port 22: Connection timed out`
- `Connection timed out during banner exchange` (TCP OK, SSH handshake hangs)
- ICMP ping works, Samba (445) works, but port 22 unresponsive
- `ps -ef | grep sshd: rob` shows 15+ zombie sessions on server
- Load average climbs into double digits with no actual work running

## Root causes and fixes

### 1. Tailscale routing LAN-to-LAN traffic via DERP relay

**Cause:** The `c240` alias in Latitude's `~/.ssh/config` pointed at the Tailscale
IP `100.120.11.35`. Latitude is on the same LAN as c240 (2ms direct), but
Tailscale was routing via Sydney DERP relay. When that relay wobbled, SSH failed
even though LAN was trivially reachable.

**Fix:** `.ssh/config` on Latitude now uses LAN IPs as primary for home servers:

    Host c240
        HostName 192.168.68.53    # LAN, 2ms, no dependencies
        User rob

    Host c240-ts
        HostName 100.120.11.35    # Tailscale, used only when away from home
        User rob

Same pattern applied to gen8, r630, x1. All have `-ts` suffixed aliases for
Tailscale access.

### 2. sshd overloaded by parallel connection attempts

**Cause:** When the LAN route failed, every tool with SSH retry logic (Claude
Code agent loop, monitoring scripts, VS Code Remote SSH) kept attempting.
Connections piled up faster than sshd could auth-or-reject them, exhausting
the pre-auth queue (MaxStartups 10:30:100).

**Fix:** `/etc/ssh/sshd_config.d/10-claude-code-hardening.conf` on c240 (tracked
in repo at `ops/sshd_configs/`):

    MaxStartups 60:30:200   # was 10:30:100 — 6x headroom for bursts
    MaxSessions 20          # was 10 — more channels per connection
    ClientAliveInterval 60  # kick dead clients within 3 min
    ClientAliveCountMax 3
    LoginGraceTime 30       # drop half-open auths fast (was 120)
    TCPKeepAlive yes

Applied via `sudo systemctl reload ssh` (not restart — preserves live sessions).

Verify limits active with: `sudo sshd -T | grep -iE 'maxstartups|maxsessions|clientalive|logingrace'`

## Recovery procedure — if this happens again

1. **Stop the connection storm first.** Kill any Claude Code session, close
   Remote SSH in VS Code, do NOT run monitoring loops. Every connection attempt
   is adding to the queue.

2. **Wait 60 seconds.** Pre-auth timeouts clear. Existing orphans age out.

3. **Try LAN directly, not through alias:**
       ssh -o ConnectTimeout=30 rob@192.168.68.53 "uptime"

4. **If LAN SSH hangs during banner exchange,** sshd is stuck. Recovery:
   - If the `c240` alias in your `.ssh/config` still routes LAN, wait longer
     (2–5 min). Zombies will age out eventually.
   - If it still hangs after 10 min, CIMC power cycle is the backup:
       ssh gen8  # if gen8 is up
       sudo ipmitool -I lanplus -H <CIMC_IP> -U admin -P <pw> power cycle
     CIMC IP is currently unknown — open issue in HANDOVER (find via router ARP
     for MAC 00:A3:8E:8E:B3:84).
   - Physical reboot button under the house as last resort.

5. **After recovery,** check MaxStartups is still in effect:
       ssh c240 "sudo sshd -T | grep maxstartups"
   Expected: `maxstartups 60:30:200`

6. **If Tailscale involved,** restart on c240:
       ssh c240 "sudo tailscale down && sleep 2 && sudo tailscale up"
   This clears stuck DERP relay routing.

## Prevention — rules for multi-tool SSH workflows

- **LAN-first.** Any tool SSHing to c240 from Latitude or X1 must use the `c240`
  alias (LAN), not `c240-ts`. Only use `c240-ts` explicitly when remote.

- **Don't hammer.** No monitoring loops that poll faster than every 30s. No
  parallel SSH bursts from the same source without a `sleep 1` between them.

- **Serialize within a session.** If a tool (like Claude Code) issues many SSH
  commands in a session, each should wait for the prior to complete. Avoid
  parallel `&` backgrounding of SSH calls unless there's a specific need.

- **Prefer local scripts to many small SSH calls.** If a task has >10 steps on
  c240, push a single bash script via `scp` and run it in one SSH session,
  rather than issuing 10 separate SSH commands.

## References

- Incident: Session 68, 2026-04-19
- Hardening config in repo: `ops/sshd_configs/10-claude-code-hardening.conf`
- Client config: Latitude `~/.ssh/config` (`c240` → LAN-first)
- Related open issue: c240 CIMC IP unknown (HANDOVER issue #4)

