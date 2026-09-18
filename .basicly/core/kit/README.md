# The kit

The portable half of this harness. Everything under here is deployed **into a consumer
repository** and runs there, so it is written to a stricter contract than `src/basicly/`:
the engine imports the kit, and the kit imports nothing.

One directory per kit. The directory is not decoration — `kit-deployment` and the
`kit-boundary` hook key their scope on it, so a module sitting loose at this level is a
module no gate is looking at. That is how the tier kit's three files went ungated until
2026-08-08.

| Kit | What it is for | Its own README |
| --- | --- | --- |
| [`tier/`](tier/README.md) | resolving a declared model tier into the model a host will actually spawn, by a hook installed into that host | [`tier/README.md`](tier/README.md) |
| `tracker/` | the owned append-only work-tracker ledger: events, snapshot, `fsck`, import, ranking | [`tracker/SPEC.md`](tracker/SPEC.md) |
| [`comments/`](comments/README.md) | reporting and removing prose comments from code files, so the code is the only source of truth | [`comments/README.md`](comments/README.md) |

## How a consumer gets one

Each kit is published as its own package under [`packages/`](../../../packages), built from
the directory here so there is never a second copy to drift. A repository that will never
run `basicly` installs one directly:

```console
$ uvx --from git+https://github.com/niksavis/basicly#subdirectory=packages/basicly-tracker basicly-tracker init
tracker: added to .gitattributes: events-*.jsonl -text merge=union
tracker: 18 file(s) written, 0 unchanged, in .basicly/kit/tracker
```

`init` vendors the kit into `.basicly/kit/<name>`, writes the kit's skill into every agent
skill root, and writes any git rule the kit's correctness depends on, refusing to install at
all if it cannot. `--with-instructions` also places a short always-on block. `uninstall`
removes exactly what it wrote. Copying the files by hand still works and is the documented
fallback, not the route.

**A kit ships its guidance, not only its code.** Every kit directory carries a `GUIDANCE.md`
that becomes the consumer's `SKILL.md` and an `INSTRUCTION.md` that becomes the always-on
block, because a consumer who never runs `basicly` gets none of the projected catalog and
would otherwise have working code that no agent knows to call.

Those two files are the **standalone** path's source. `basicly build` does not project them,
so a reader should not look for their output — a basicly consumer is told the same thing
through the catalog instead. Where both exist they are one text with a gate on it:
`.basicly/core/skills/no-comments/skill.yaml` is generated from
`kit/comments/GUIDANCE.md`, and `tests/test_kit_packages.py` fails if they drift.

## Constraints anything here must keep

These bind **every** kit, and each one is cited from the modules it governs.

- **No basicly, no third party, no network.** A kit module imports the standard library and
  its own siblings, nothing else. `kit-boundary` enforces the first half; the rest is on the
  author.
- **Parseable by an interpreter older than this repo's 3.14 floor**: no syntax newer than
  3.9, and **one exception class per handler**. This repo's `ruff format` targets 3.14 and
  will rewrite a parenthesized multi-exception `except` into syntax a consumer's Python may
  not have — so the paren-free form the `python-guidelines` skill prescribes for `src/` is
  the wrong form here.
- **Fail closed on a question, open on a crash.** A kit that cannot answer must raise rather
  than return a plausible default; a kit that crashes in a path the consumer did not ask for
  must not take the consumer's tool down with it. Which of the two applies is the kit's own
  call and belongs in its README.

## Adding a kit

Give it a directory, a README stating what it is for and which of the two failure modes
above it takes, a `GUIDANCE.md` skill and an `INSTRUCTION.md` block so a standalone consumer
is told the kit exists, and an entry in the table here. Then check whether `kit-deployment` needs to
know about it: that gate asserts a **host repository** satisfies a kit's deployment
requirements, and a kit with no such requirements needs no entry.
