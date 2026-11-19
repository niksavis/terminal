# Vault migration

The standalone tracker kit imports a ledger, beads, br or beans backlog into an initialized vault.
It exports one prefix into an empty ledger folder.
Run these commands with the kit files installed beside `cli.py`.
No Basicly engine is required.

Inspect the source before publishing it.

```sh
python3 .basicly/core/kit/tracker/cli.py migrate .basicly/ledger --to-vault --preview
```

Preview reports canonical counts and a public digest.
It uses temporary integrity checks without changing the source, destination or machine cache.
It does not fetch or publish.
An actual import must produce the same digest with the same source and redaction rules.

Replace `VAULT_URL` with the initialized vault address.
This command deliberately keeps no private mapping.

```sh
python3 .basicly/core/kit/tracker/cli.py migrate .basicly/ledger --to-vault --vault VAULT_URL --no-map-kept
```

To retain the mapping, replace `--no-map-kept` with `--private-map PRIVATE_FILE`.
The owner supplies `PRIVATE_FILE`; the tool has no default location.
Back up that file on the private side.
Without it, old external references to changed event ids cannot be resolved through the migration map.
Normal vault reads, writes and exports never need it.

The map contains old and new ids and changed field names.
It contains no plaintext removed value.
Old ids can confirm hidden values, so never publish the map.
The map path is resolved before validation, including symlinks.
A destination outside every Git checkout is allowed.
Inside another checkout, Git must confirm that the file is ignored.
Vault checkouts and linked worktrees always refuse, even when ignored.
An existing file requires `--overwrite-private-map`.
The tool never edits ignore files.

Add `--redact-name NAME` for each exact, case-sensitive name that must become `contributor`.
The rule applies to imported holder history and template text too.
An empty name list removes no names.
Secrets and machine paths still use the standard redactor.
History and record ids stay intact.
Unchanged payloads keep their event ids.
Changed payloads receive valid deterministic ids, and operational references follow them.
Template field collisions refuse before publication.

Live vault claims remain authoritative for the current holder.
An imported assignee grants no claim.
The view retains historical holder events and derives the current holder from vault claims.
Its report separates source events from derived holder events.

For another source format, supply its export path.
`br` has its own format key and uses the beads JSONL reader.
Beans expects its source folder.

```sh
python3 .basicly/core/kit/tracker/cli.py migrate --to-vault --preview --from br --source EXPORT_FILE
```

An import is a one-time operation.
Repeating the same source against the same vault refuses before another publication.
Identical input and rules produce identical canonical bytes and event ids.
Git commit hashes depend on destination history and are outside that comparison.
The tool checks source accounting, public digests and unchanged ledger integrity before publishing.
The report counts old event citations in tracked text files and current Git history.
It reports unavailable or unreadable inputs explicitly and never rewrites those citations.

Export the canonical view of one prefix.
Replace `PREFIX` and `EMPTY_FOLDER` with the selected prefix and an empty destination.

```sh
python3 .basicly/core/kit/tracker/cli.py migrate EMPTY_FOLDER --from-vault --vault VAULT_URL --prefix PREFIX
```

The export includes the validated public template stored with the import.
Missing, malformed or altered required template metadata refuses the read.
Custom-template reviews and confirmations use the exported template.
An existing ledger or another nonempty destination refuses before writing.

These commands move data; they do not switch a code repository to a vault.
Keep the old ledger until the owner approves the cutover commands and rollback checks.
