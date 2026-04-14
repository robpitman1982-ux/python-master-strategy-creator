# SSH After Reboot Fix — Both Servers
## Date: 10 April 2026
## Status: RESOLVED AND TESTED

---

## THE PROBLEM

SSH to Gen 8 (and potentially Gen 9) did not work after reboot. Server booted,
network came up (ping responded), port 22 showed open, but SSH connections either
timed out or were refused. SSH only worked after someone manually logged in at the console.

## ROOT CAUSE

Ubuntu 24.04 uses `ssh.socket` (systemd socket activation) by default instead of
running `ssh.service` directly. On older HP ProLiant hardware, socket activation
is unreliable at boot — the socket binds but doesn't properly trigger the service.

## WHAT CLAUDE TRIED (AND BROKE)

Added systemd overrides to make SSH wait for `network-online.target`:
```
/etc/systemd/system/ssh.service.d/wait-for-network.conf
/etc/systemd/system/ssh.socket.d/wait-for-network.conf
```
This made things WORSE — `systemd-networkd-wait-online` hung on this hardware,
completely blocking SSH from starting at all.

## THE FIX (Credit: ChatGPT)

Three-layer approach applied to BOTH Gen 9 and Gen 8:

### Layer 1: Disable socket activation, use plain ssh.service
```bash
sudo rm -f /etc/systemd/system/ssh.service.d/wait-for-network.conf
sudo rm -f /etc/systemd/system/ssh.socket.d/wait-for-network.conf
sudo systemctl daemon-reload
sudo systemctl unmask ssh ssh.socket
sudo systemctl enable ssh
sudo systemctl disable ssh.socket
sudo systemctl stop ssh.socket
sudo systemctl restart ssh
```

### Layer 2: Delayed recovery service (belt)
```bash
sudo tee /etc/systemd/system/ssh-recover.service >/dev/null <<'EOF'
[Unit]
Description=Recover SSH after boot
After=multi-user.target network.target
Wants=network.target

[Service]
Type=oneshot
ExecStart=/bin/sh -c 'sleep 25; systemctl restart ssh'

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable ssh-recover.service
```

### Layer 3: Cron fallback (suspenders)
```bash
sudo crontab -l 2>/dev/null | { cat; echo '@reboot sleep 45 && /bin/systemctl restart ssh'; } | sudo crontab -
```

## VERIFICATION CHECKLIST

After applying, confirm:
```bash
sudo systemctl is-enabled ssh          # → enabled
sudo systemctl is-enabled ssh.socket   # → disabled
sudo systemctl is-enabled ssh-recover  # → enabled
sudo crontab -l | grep ssh            # → @reboot sleep 45 && /bin/systemctl restart ssh
sudo ls -R /etc/systemd/system/ssh.service.d /etc/systemd/system/ssh.socket.d 2>/dev/null
# → empty or "No such file or directory"
```

## TEST RESULTS

### Gen 9 (DL360 Gen9) — 10 April 2026
- Rebooted via `sudo reboot`
- SSH connected at 1 minute uptime ✅
- ssh.service: enabled, active
- ssh.socket: disabled
- Port 22: listening on all interfaces
- Powered down via `sudo shutdown -h now` ✅

### Gen 8 (DL380p Gen8) — 10 April 2026
- Woken via WOL magic packet (subnet broadcast to 192.168.68.255)
- SSH connected at 4 minutes uptime ✅
- ssh.service: enabled, active
- ssh.socket: disabled
- Port 22: listening on all interfaces
- Powered down via `sudo shutdown -h now` ✅

### WOL Test
- WOL from home desktop (192.168.68.72) to Gen 8 (MAC ac:16:2d:6e:74:2c)
- Required subnet-directed broadcast (192.168.68.255 port 9) — plain broadcast didn't work
- PowerShell WOL command:
```powershell
$mac = 'AC:16:2D:6E:74:2C'
$macBytes = $mac -split ':' | ForEach-Object { [byte]('0x' + $_) }
$magicPacket = [byte[]](,0xFF * 6) + ($macBytes * 16)
$udpClient = New-Object System.Net.Sockets.UdpClient
$udpClient.EnableBroadcast = $true
$ep = New-Object System.Net.IPEndPoint([System.Net.IPAddress]::Parse('192.168.68.255'), 9)
$udpClient.Send($magicPacket, $magicPacket.Length, $ep) | Out-Null
$udpClient.Close()
```

## KEY LESSON

On older HP ProLiant servers running Ubuntu 24.04:
- **DO NOT** use `ssh.socket` (systemd socket activation) — disable it
- **DO NOT** add `network-online.target` dependencies — they can hang
- **DO** use plain `ssh.service` with a delayed recovery oneshot as backup
- **DO** add a cron @reboot fallback for belt-and-suspenders reliability
