# SESSION END HANDOVER INSTRUCTIONS

When the user says "update the handover", "session handover", "end of session", or similar, follow this procedure:

## What to do

1. **Read the current HANDOVER.md** from the repo (`~/python-master-strategy-creator/HANDOVER.md` on servers, or `C:\Users\Rob\Documents\GIT Repos\python-master-strategy-creator\HANDOVER.md` on desktop)

2. **Update these sections** based on what was done this session:
   - **Header:** Update the date and session name
   - **Section 2 (Live Trading):** If any trading changes were made
   - **Section 4 (Strategy Engine):** If engine code changed
   - **Section 5 (Home Lab):** If infrastructure changed (IPs, services, packages, hardware)
   - **Section 6-8 (Cloud/VPS/Network):** If connectivity or cloud infra changed
   - **Section 9 (Market Data):** If data was added or transferred
   - **Section 10 (Sweep Results):** If new sweep results came in
   - **Section 11 (Portfolio Selector):** If selector logic changed
   - **Section 13 (Open Issues):** Add new issues, mark resolved ones, reprioritize
   - **Section 14 (Roadmap):** Check off completed items, add new ones
   - **Section 16 (Session Log):** Add a new row for this session

3. **DO NOT** remove resolved items from the session log — that's the history.
4. **DO NOT** change sections that weren't affected this session.

5. **Push to GitHub:**
   ```bash
   cd ~/python-master-strategy-creator
   git add HANDOVER.md
   git commit -m "handover: [brief description of session]"
   git push
   ```

6. **Confirm** the push succeeded and tell the user the handover is updated.

## Format rules
- Keep tables aligned and readable
- Use present tense for current state, past tense for session log
- Be specific with IPs, credentials, file paths — this is an ops document
- Every section independently searchable via ctrl+F
- Keep Quick Reference up to date with working connection commands

## What NOT to include
- Verbose explanations of why decisions were made
- Code snippets longer than 5 lines (point to the file instead)
- Temporary debugging info that won't matter next session
