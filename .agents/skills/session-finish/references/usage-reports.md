# Usage reports

Use available usage data. Run a report below only when it answers the current question; a routine handover does not require every report.

```sh
basicly usage report
```

- The `tool-usage` hook counts shell commands and `Skill` calls into `.basicly/usage/tool-usage.json`.
- The report lists tools and skills by count with the date of last use. It names the catalog skills that nothing used, which are the candidates for removal.
- Do not cite the **Unresolved heads** table. Its rows are recorder misses and tools that this machine does not have.
- When the report has no data, say so and continue. The hook may not be active in this repository.

When evaluating factory settings:

```sh
basicly usage tuning
```

- Each row is one governed parameter: the value in force, the outcomes under it, and a recommendation with its sample size.
- The command changes nothing. Report a recommendation worth an action. Never edit `basicly.toml` from it without the owner's approval.
- A `seeded` row has too few samples, so the declared prior stands. Do not cite it as a measurement.
- A row with zero samples names a limit that nothing records. That is a finding.

When a supervised pass kept lane transcripts, split the spend:

```sh
basicly usage lane-split
```

- Each lane shows the share of spend on context acquisition and the share on implementation. Read the shares, never the token counts. The counts use a different unit from the run record.
- `unclassifiable` means the transcript has no tool-name field. It does not mean the lane read nothing. A lane with no transcript is missing, not zero.
- Only Claude transcripts carry the event this command reads.

When evaluating dispatch failures:

```sh
basicly usage outcomes
```

- It shows how every recorded dispatch ended and the failure rate. Judge a run against this rate, not against your memory of it.
- These are dispatch outcomes: did the agent process finish. They do not show whether a lane found a result.
