# Findings and responses

Answer every finding before a teardown ends. Copy this table into the report. Every row carries the finding's evidence, also when it is declined, so the user sees what was set aside.

| # | Severity | Finding | Evidence | Response | Detail |
| --- | --- | --- | --- | --- | --- |
| 1 | important | ... | path:line or ran: ... | fixed | commit or diff that fixes it |
| 2 | important | ... | path:line or ran: ... | contested | the evidence that the finding is wrong |
| 3 | nit | ... | path:line or ran: ... | declined | why the cost is higher than the gain |
| 4 | important | ... | path:line or ran: ... | escalated | the decision the user must make |

Responses:

- **fixed**: the change is made and its check ran.
- **contested**: counter-evidence is attached.
- **declined**: the cost is higher than the gain. Decline an important finding only when the user says so; write "declined by the user" and the rule the user overrode.
- **escalated**: the user decides; give one recommendation.
