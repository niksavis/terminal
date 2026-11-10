## Default: basicly commit

```sh
basicly commit "<description>"
basicly commit "<description>" --body "Bump to 1.2.0 in README.md." --dry-run
```

It derives the type from the work type of the record and the staged paths, the scope from the staged paths and the record id from the branch. It refuses a description that the character rules reject, names the character, and does not commit.

| Flag | Effect |
| --- | --- |
| `--body` | Free-form body, for capitals, dots and file names |
| `--type` | Overrides the derived type |
| `--scope` | Overrides the derived scope |
| `--issue` | Overrides the record id bound to the branch |
| `--breaking` | Adds the `!` before the colon |
| `--dry-run` | Prints the message and does not commit |

## Format

Write the subject by hand only when `basicly commit` cannot derive it, for example outside the worktree of a record.

```text
type(scope)!: description (record-id[, record-id...])
```

| Part | Rule |
| --- | --- |
| `type` | One of `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert` |
| `(scope)` | Optional. Lowercase kebab-case, no space |
| `!` | Optional. Directly before the colon. Marks a breaking change |
| `description` | Imperative mood. Entirely lowercase. Letters, digits, spaces and hyphens only, so no underscore and no dot. At least 3 characters. It starts with a letter and has no trailing punctuation |
| `(record-id, ...)` | One or more ids that the tracker holds, comma-separated in one trailing parenthetical |

- A record id is `<prefix>-<base>`, with optional dotted levels for child records, for example `app-q49` or `app-zrj.4.1`. The prefix is the tracker prefix of this repository.
- The hook finds an id by its prefix at a word boundary anywhere in the message. A hyphenated word in the description is not an id. A trailer such as `Refs: app-q49` also counts.
- Merge commits and subjects that start with `Revert "` are exempt.

Procedure:

1. Pick the type that matches the intent of the change.
2. Find or create the record with `work-tracker`.
3. Add `!` only for a breaking change of an interface or a behaviour.
4. Write the description.
5. Add the record ids in one trailing parenthetical.
6. Run `git commit -m "..."`, or name the paths with `git commit -F - -- <paths>`.
