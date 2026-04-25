# MASTER_HANDOVER.md migration checklist

> The repo file `HANDOVER.md` was renamed to `MASTER_HANDOVER.md` so it doesn't
> collide with handover files from other projects (e.g. `BETFAIR_HANDOVER.md`)
> when agents like Hermes load multiple project memories simultaneously.
>
> The repo-side rename is done. This checklist covers the server-side and
> Latitude-side updates that must follow before the Hermes pipeline works again.

---

## Status of the rename

- **Repo-side (done):** `git mv HANDOVER.md MASTER_HANDOVER.md`, all references in repo files updated, committed and pushed.
- **g9 server (TODO):** `sync-handover` script + symlinks need to follow the new filename.
- **Latitude (TODO):** PowerShell handover script (if any) that scp'd `HANDOVER.md` needs the new filename.
- **Hermes clone on g9 (auto-handled):** the next `sync-handover` run will fast-forward and the new filename will land in `/data/hermes/psc-handover/MASTER_HANDOVER.md`. The old `HANDOVER.md` will be removed by git as part of the rename commit.

---

## g9 — server-side migration

Run on g9 (`ssh g9-ts` or `ssh g9`) as root.

### 1. Sync the repo so the new filename is on disk

```bash
sudo /usr/local/bin/sync-handover
# expect: "OK: fast-forwarded to <sha>"
# expect: "MASTER_HANDOVER.md now at <bytes>..."
ls /data/hermes/psc-handover/
# should show MASTER_HANDOVER.md, NOT HANDOVER.md
```

If the script still references the old filename inside (`stat -c%s HANDOVER.md`), update:
```bash
sudo cp /data/hermes/psc-handover/scripts/sync-handover.sh /usr/local/bin/sync-handover
sudo chmod 755 /usr/local/bin/sync-handover
```

### 2. Repoint Hermes's memory symlink

The symlink `/home/hermes/.hermes/memories/HANDOVER.md` points at `/data/hermes/psc-handover/HANDOVER.md` — both the link name and target need updating.

```bash
# Remove old symlink
sudo rm /home/hermes/.hermes/memories/HANDOVER.md

# Create new symlink with the new name, pointing at new target
sudo -u hermes ln -s /data/hermes/psc-handover/MASTER_HANDOVER.md /home/hermes/.hermes/memories/MASTER_HANDOVER.md

# Verify
sudo -u hermes ls -la /home/hermes/.hermes/memories/MASTER_HANDOVER.md
sudo -u hermes cat /home/hermes/.hermes/memories/MASTER_HANDOVER.md | head -3
# should show "Last updated: ..." then "Current status: ..."
```

### 3. Clean up the retired Session 72b path (if it still exists)

```bash
# /data/shared/handover/HANDOVER.md was retired in Session 72c but may still exist.
# It's not load-bearing — the LAST_CHANGE marker in the same dir IS used by the reconcile cron.
sudo rm -f /data/shared/handover/HANDOVER.md
ls /data/shared/handover/
# should still contain LAST_CHANGE
```

### 4. Verify Hermes can read it

```bash
sudo -u hermes bash -c 'cat ~/.hermes/memories/MASTER_HANDOVER.md | head -5'
```

### 5. Update Hermes's skills if they hardcode the filename

```bash
sudo -u hermes grep -rn "HANDOVER.md" /home/hermes/.hermes/skills/ 2>/dev/null
# If matches in handover-update/SKILL.md or handover-memory-reconcile/SKILL.md,
# update them to MASTER_HANDOVER.md. Hermes can edit its own skills.
```

### 6. Verify the safety-net cron still works

```bash
cat /etc/cron.d/sync-handover
# command should still be /usr/local/bin/sync-handover --quiet
# (it doesn't reference the filename, just calls the script)

sudo /usr/local/bin/sync-handover --quiet
echo "exit=$?"
# expect exit=0
tail -5 /var/log/sync-handover.log
```

---

## Latitude — handover PowerShell script

If there's a PowerShell script that pushes `HANDOVER.md` to g9 after a git push, update the filename in it. Best guess of locations:

```powershell
# Likely candidates (search for one that contains scp HANDOVER.md):
ls C:\Users\Rob\*.ps1
ls "C:\Users\Rob\Documents\GIT Repos\python-master-strategy-creator\*.ps1" -ErrorAction SilentlyContinue
ls C:\Users\Rob\Desktop\*.ps1 -ErrorAction SilentlyContinue
```

Edit the one that contains:
```powershell
scp HANDOVER.md g9-ts:/tmp/HANDOVER.md
ssh g9-ts "sudo /usr/local/bin/ingest-handover"   # this command path also retired
```

Replace with:
```powershell
git push
ssh g9-ts "sudo /usr/local/bin/sync-handover"
```

Note: the `scp HANDOVER.md ...` step is no longer needed since Session 72c — `sync-handover` does `git fetch + git merge --ff-only`, so the file lands via git, not scp. The current MASTER_HANDOVER.md says this on lines 148-150.

---

## Verification — end-to-end

After all steps above:

1. From Latitude: edit `MASTER_HANDOVER.md`, change the timestamp, commit, push.
2. Run `ssh g9-ts "sudo /usr/local/bin/sync-handover"` — expect "OK: fast-forwarded".
3. On g9: `sudo -u hermes head -3 /home/hermes/.hermes/memories/MASTER_HANDOVER.md` — expect the new timestamp.
4. Wait one cron tick (5 min) and confirm `/var/log/sync-handover.log` shows another OK entry.

---

## Rollback (if needed)

If something breaks after the rename and you need to revert:

```bash
# In repo (Latitude):
cd "C:/Users/Rob/Documents/GIT Repos/python-master-strategy-creator"
git mv MASTER_HANDOVER.md HANDOVER.md
# Edit references back (or git revert the rename commit)
git commit -m "revert: handover rename"
git push

# On g9:
sudo /usr/local/bin/sync-handover
sudo rm /home/hermes/.hermes/memories/MASTER_HANDOVER.md
sudo -u hermes ln -s /data/hermes/psc-handover/HANDOVER.md /home/hermes/.hermes/memories/HANDOVER.md
```

---

## What the rename achieves

- Project-scoped naming: agents like Hermes that load memories from multiple projects no longer have two files both called `HANDOVER.md` colliding.
- Pairs cleanly with `BETFAIR_HANDOVER.md` (other project) and any future projects.
- Repo internal docs (CLAUDE.md, LOG.md, sync-handover.sh, CFD_SWEEP_SETUP.md, AUDIT_REPORT.md) all updated to reference the new name.
- Global `~/.claude/CLAUDE.md` standing rule updated: project-named handover, never plain `HANDOVER.md`.
