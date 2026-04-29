# sessions/

Sprint specs. One markdown file per sprint, pre-registered before data is
touched, frozen at commit time.

## Files

- `SPRINT_TEMPLATE.md` — copy this when starting a new sprint
- `SPRINT_NN_<name>.md` — actual sprint files (numbered sequentially)

## Convention

1. **Before any sweep / portfolio run / test against data**:
   - Copy `SPRINT_TEMPLATE.md` to `SPRINT_NN_<descriptive_name>.md`
   - Fill in sections 1-6 (goal, mechanism, frozen grid, verdict
     definitions, methodology, optional consultation)
   - Commit the file with message `sprint NN: open — <name>`
2. **Run the sweep / experiment.** Do NOT change the spec mid-run. If
   you discover you want to change something, that becomes Sprint N+1.
3. **At sprint close**:
   - Fill in section 8 (result, verdict, lessons)
   - Commit with message `sprint NN: close — <verdict>`
   - Append a one-line entry to `LOG.md`

## Why pre-register?

Empirical lesson from this project: the position sizing bug (Session 45)
went undetected for 30+ sessions because the boring "obviously correct"
arithmetic was never sanity-checked against a frozen baseline. Sprints with
frozen verdict criteria force the question "what would change my mind?"
before you have data that wants to nudge the criteria.

## Why verdict semantics?

`NO EDGE`, `CANDIDATES`, `SUSPICIOUS`, `BLOCKED` are exhaustive and
mutually exclusive. Every sprint has to land in exactly one. This stops the
"keep going until we find something" failure mode.

`SUSPICIOUS` is the underrated one — it triggers gate audits, not strategy
promotions. If 80% of candidates pass the promotion gate, the gate is
probably broken; that's a sprint outcome worth its own commit.
