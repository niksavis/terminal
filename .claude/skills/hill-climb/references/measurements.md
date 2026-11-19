# Round measurements

The script records reviewer findings and host-supplied usage with each round.
These measurements do not change the stop rules or independent verification.

## Finding counts

Counts come from saved reviewer replies.
The report keeps the important count after refutations separate from cited finding identities.
An identity hashes the claim and evidence after whitespace normalization.
Identical identities count once across lenses.
The report also counts identities present in earlier rounds.
Different wording can represent the same defect.
A citation proves neither correctness nor usefulness.
Refuted findings remain in these descriptive counts.
Use verified findings and unresolved decisions to explain revisions.

## Usage manifest

Save host usage for reviewers, verifiers and failed or retried dispatches when available.
Use a distinct host dispatch identifier for each agent attempt.
Do not reuse an identifier from an earlier round.
The owner supplies this manifest.
The script does not collect host telemetry.

The following JSON is a synthetic example.
The zero values are example measurements, not observed review costs.
Replace each hash with the SHA256 of that lens's saved reply bytes.
Include every requested lens in `reports_sha256`.

```json
{
  "reports_sha256": {
    "a": "REPLACE_WITH_REPLY_SHA256",
    "b": "REPLACE_WITH_REPLY_SHA256",
    "c": "REPLACE_WITH_REPLY_SHA256"
  },
  "agents": [
    {
      "id": "host-dispatch-a",
      "lens": "a",
      "role": "reviewer",
      "source": "host usage record for host-dispatch-a",
      "tokens": 0,
      "cost_usd": 0,
      "cost_kind": "cli-estimate",
      "duration_s": 0
    }
  ]
}
```

Hash a saved reply with the standard library.
Run this command for each requested lens.

```sh
python3 -c "import hashlib,pathlib; print(hashlib.sha256(pathlib.Path('DIR/rN/a.md').read_bytes()).hexdigest())"
```

Record the round with the manifest.

```sh
python3 -B ${CLAUDE_SKILL_DIR}/../swarm/scripts/swarm.py climb-round --state DIR/climb.json --lenses a,b,c --dir DIR/rN --refuted 0 --usage DIR/rN/usage.json
```

Use `null` or omit a metric when the host supplies no value.
Use zero only when the source reports zero.
Known metrics require a nonempty source reference.
Tokens must be nonnegative integers.
Costs and durations must be finite nonnegative numbers.
Label costs `reported` or `cli-estimate` according to their source.
A reported cost is externally supplied evidence, not confirmation of billing.
Keep CLI estimates labeled in the final report.
A verifier can use a requested lens or `null`.
A reviewer must name a requested lens.
Retried attempts can share a lens but need distinct identifiers.

## Scope and refusals

Usage totals cover reported agents only.
They omit unreported agents, author revisions and other host work.
Summed agent seconds do not measure elapsed time because agents can overlap.
Missing reviewers or missing agent metrics leave the corresponding total unknown.
The `known_` fields sum available values and preserve measured zero.
Legacy rounds without measurements remain unknown.
Do not infer savings or cost per useful finding from these fields alone.

The script binds the manifest to reply hashes and retains its SHA256.
This detects mismatched replies, not fabricated host usage.
The manifest must be JSON and cannot exceed the script's `USAGE_LIMIT` constant.
The script refuses duplicate fields, repeated dispatch identifiers and unknown agent fields.
It refuses environment-file names and manifest symlinks.
Refusals leave the climb state unchanged.
