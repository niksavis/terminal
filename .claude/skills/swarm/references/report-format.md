# Report format

Each agent's reply ends with one json block. Save each reply as `DIR/LENS.md`, then run the script.

| Field | Used by | Meaning |
| --- | --- | --- |
| lens | all | The lens name. It must equal the file name, or the reply is malformed. |
| verdict | swarm | pass or fail on the lens rubric; `check` requires it. |
| findings | all | A list of severity, claim, evidence, fix. |
| grades | hill-climb | One number from 0 to 10 for every property of the climb; `climb-round` requires it. |
| vote, reason, strongest_counter | council | The chosen option, why, and the best case against it; `tally` requires `vote`. |

The script rules:

- A missing file is "not run". A file with no json block is "malformed". Both make `check` exit 1.
- Evidence is cited when it holds a `path:line`, `ran:`, or a dollar sign and a space, at the start or after a space. The script marks a finding without cited evidence UNCITED.
- A `verdict` other than pass or fail is malformed.
- Every finding is listed on its own line, highest severity first. When another lens cites a `path:line` that this finding also cites, the line says "also cited by" that lens. Agreement of two lenses raises confidence; it never hides a claim.
- Command evidence (a dollar prompt or `ran:`) cites a finding but never links it to another.
- The `verdict` column shows each lens's pass or fail.
