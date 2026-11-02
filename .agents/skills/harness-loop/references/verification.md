# Verification

Which checks to run, and when to rerun them. The always-on Quality Gate keeps the
short rule; this reference holds the cases.

| Situation | Action |
| --- | --- |
| A small code edit | Run focused checks while editing and cheap gates first. |
| A check fails | Read why, fix its cause and rerun that check. |
| Changed inputs | When source or environment inputs change, rerun affected checks. |
| A tracker-only or phase-only change | Skip the rerun only when the existing engine establishes equivalent trusted inputs; otherwise rerun affected checks. |
| A release candidate | Run required full verification on the integrated candidate. |

- A commit or phase transition alone does not invalidate equivalent evidence.
- After the last edit, review the diff and run the affected repository checks.
- Read the output and the pass/fail summary, not only the exit code.
- Keep all required gates enabled. A bypassed check is reported as bypassed, never as passing.
