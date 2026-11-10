# Release procedure in detail

## Contents

- Notes
- Tutorial pages
- Dry run
- What the cut does
- Publication

### 2. Write the notes

- Each change leaves its entry in `changelog.d/<record-id>.<category>.md`. The categories are `added`, `changed`, `deprecated`, `removed`, `fixed` and `security`. One file per change means that two lanes never collide on one anchor.
- A hand-written body under `### [Unreleased]` also publishes, beside the fragments.
- Write a summary under `### [Unreleased]`, above its first `###` heading. Write one paragraph on what the release changes for a user, then themed bullets. Name the record id of a fragment in each highlight.

The release folds each fragment into `### [Unreleased]` under its Keep a Changelog heading, sorted by category and then by file name. It moves that body into the dated `### vX.Y.Z - <date>` section, deletes the fragments in the same commit, and leaves `[Unreleased]` empty.

### 3. Wait for green CI

Cut only from a commit whose CI run on the release branch passed. A red or still running build is a stop.

### 4. Choose the version and run the dry run

Choose major, minor or patch yourself. The command refuses a version that does not move forward, but it does not choose one.

```sh
uv run basicly release <version> --issue <record-id> --dry-run
```

The dry run writes nothing and reports every refusal at once, each with the file or value it names. [refusals](references/refusals.md) lists them.

A page under `docs/tutorial/` that names the current version as the one it was recorded against is rewritten to the new version by the release. A page that names any other version refuses: walk it against a build of this checkout and fix it first.

The dry run assembles the release in a temporary checkout and runs its actual commit hooks. It reports failing gates or the verify runner's gate count without changing this checkout. It copies the prepared Python environment and uses the same hook configuration. Find out whether the tag workflow runs the full checks before publication; when it does not, run required full checks on the release commit before pushing the tag.

### 5. Cut the release

```sh
uv run basicly release <version> --issue <record-id>
```

It bumps `__version__`, regenerates the projections, rewrites the `vX.Y.Z` install pins in `README.md` and the other pin files, assembles the changelog, commits and creates the annotated tag. Add `--date YYYY-MM-DD` to set the changelog date. The default is today.

Required release gates must still pass. Use `--shipping <node>` when the verified shipping node differs from the root.
Keep publication inside the version and scope the user requested.

### 6. Push and confirm

Run the two commands that the release prints:

```sh
git push origin main
git push origin vX.Y.Z
```

When a workflow publishes from the tag push, it reads `CHANGELOG.md` from the tagged commit. Confirm that the workflow run is green and that the release page matches the summary. Never edit the release page after publication. A page that disagrees with its changelog section is a defect.

When a tag push is blocked by the Claude auto-mode classifier, read [auto-mode](references/auto-mode.md).
