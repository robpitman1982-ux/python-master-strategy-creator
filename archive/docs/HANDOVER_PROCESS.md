# SESSION HANDOVER PROCESS

## When to trigger
User says: "update the handover", "session handover", "end of session", "handover for new chat", or similar.

## Steps

1. **Read current HANDOVER.md** from `C:\Users\Rob\Documents\GIT Repos\python-master-strategy-creator\HANDOVER.md`
   - On servers: `~/python-master-strategy-creator/HANDOVER.md`

2. **Update only sections affected this session:**
   - Header: date + session name
   - Live Trading: if trading changes made
   - Home Lab Infrastructure: if infra changed (IPs, services, packages, hardware)
   - Cloud/VPS/Network: if connectivity changed
   - Strategy Engine: if engine code changed
   - Open Issues: add new, mark resolved (remove completed items), renumber
   - On The Horizon: check off completed, add new
   - Connection Quick Reference: if any commands/IPs changed

3. **DO NOT** change sections unaffected by the session
4. **DO NOT** add verbose explanations — this is an ops document
5. **Keep** IPs, credentials, file paths specific and searchable

6. **Push to GitHub:**
```powershell
cd "C:\Users\Rob\Documents\GIT Repos\python-master-strategy-creator" ; git add HANDOVER.md ; git commit -m "handover: [brief session description]" ; git push
```

7. **Confirm** push succeeded and summarise changes to user.

## Format rules
- Present tense for current state, past tense for history
- Every section independently searchable via Ctrl+F
- Tables aligned and readable
- No code snippets >5 lines (point to the file instead)
- No temporary debug info

## Desktop Commander notes
- SSH via Desktop Commander is unreliable for capturing stdout — use the `.bat` file redirect pattern:
  ```
  Write .bat file → ssh -T gen9 "command" > output.txt 2>&1
  Run .bat via cmd shell
  Read output.txt via read_file
  ```
- Always use absolute Windows paths
- Use `cmd` shell for .bat files, `powershell.exe` for everything else
