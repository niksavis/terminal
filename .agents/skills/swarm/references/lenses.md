# Lenses and rubrics

A lens is one point of view with its own rubric. Pick lenses that do not overlap. Pass the rubric lines into the brief.

| Lens | Agent | Rubric: a pass means |
| --- | --- | --- |
| correctness | reviewer | Every path gives the right result. Edge cases, errors and empty input are handled. Tests prove the claim. |
| security | auditor | No untrusted input crosses a trust boundary unchecked. No shell or query built from input. No secret in code or logs. Errors leak no internals. |
| poka-yoke | general-purpose | Wrong use is refused by name before damage, with the correct command. Defaults are safe. One rule lives in one place. |
| simplicity | general-purpose | Nothing is built twice. Existing code is reused. No dead code. The smallest diff that meets the need. |
| architecture | architect | Module boundaries hold. Dependencies point one way. The design survives the next likely change. |
| tests | general-purpose | Tests fail when the behaviour breaks. Tests are isolated and order-independent. Each bug fix has a regression test. |
| ux | designer | The person sees the result first. Each message names the next action. Every state of a screen is drawn. |
| wording | general-purpose | One term for one thing. Short sentences. No term defined two ways. |
| facts | researcher | Every number, version and vendor claim has a source or a command. Absence claims ran a positive control. |
| spec | general-purpose | The artifact does what its record or request asked, no more. Each acceptance criterion is met. |
| feasibility | general-purpose | Each step is sized, ordered and has a done state the work can reach. |
| recovery | general-purpose | Each risky step has an undo. A failure leaves a state that can be resumed. |

Pick 3 to 6 lenses. More lenses cost more and rarely find more. The `reviewer` agent accepts only the correctness and security lenses. When a named agent does not exist on this host, use a general-purpose agent with the rubric.

## Teardown presets

| Artifact | Lenses |
| --- | --- |
| diff or code | correctness, security, tests, simplicity, poka-yoke |
| plan | feasibility, spec, recovery, poka-yoke, facts |
| design, including a design doc | architecture, ux, poka-yoke, recovery, simplicity |
| skill or instruction | spec, wording, poka-yoke, facts, simplicity |
| other document | facts, wording, spec |

Add one lens for a known risk, up to 6. For a diff, also run the host's security review when one exists, such as `/security-review` in Claude Code.
