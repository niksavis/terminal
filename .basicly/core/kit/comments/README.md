# Comments kit

**The code is the source of truth, so a code file carries no prose.** This kit reports
every prose comment in a code file and removes them when asked. Seven Python files, with
**no basicly**: no `import basicly`, nothing on `PATH`, no third-party package, no
network, no subprocess.

| File | What it does |
| --- | --- |
| `languages.py` | the comment and string grammar of every language claimed |
| `directives.py` | which comments a tool reads, so a strip must keep them |
| `lexer.py` | finds comment spans in a non-Python file without entering a string |
| `python_source.py` | finds comments and docstrings in Python, exactly, via `tokenize` and `ast` |
| `scan.py` | dispatch, and the subtraction that turns a comment into a finding |
| `strip.py` | the edit, and the three proofs that it changed only prose |
| `cli.py` | `check`, `fix`, `languages` |

## Install

**`uvx` is the way in.** The kit is published as its own package, so a repository that has
never heard of this harness gets it in one command:

```console
$ uvx --from git+https://github.com/niksavis/basicly#subdirectory=packages/basicly-comments basicly-comments init
comments: 8 file(s) written, 0 unchanged, in .basicly/kit/comments
```

`init` **vendors** the kit into `.basicly/kit/comments`, so from then on plain `python3` runs
it with no `uvx`, no network and nothing on `PATH`. `update` re-vendors and reports what
changed, `status` says whether the installed copy matches, and `uninstall` removes exactly
the files `init` wrote and nothing else.

`init` also writes the kit's **skill** into `.claude/skills/comments/` and `.agents/skills/comments/`,
so an agent in that repository knows the kit exists and when to
reach for it. That is the half a code-only install leaves out: a kit nothing calls is a kit
nobody has.

Add `--with-instructions` and it also writes a short always-on block into whichever of
`CLAUDE.md`, `.claude/CLAUDE.md`, `AGENTS.md` and `.github/copilot-instructions.md` are
present, inside a marked region that a second run does not duplicate and `uninstall` removes
byte for byte. Without the flag it prints the block instead, because editing your instruction
file is not something an installer should do unasked.

Running it without vendoring works too — `basicly-comments <subcommand>` passes straight through to
the kit.

**Copying the files by hand is the fallback, not the route.** It still works, because the
kit imports nothing but the standard library, and it is the right answer when you are
driving the kit from another harness rather than adopting it. The rest of this document
describes the kit itself, which behaves identically however it arrived.

## Use

```console
$ python3 cli.py check src/
src/thing.py:12: # what this function does
comments: 1 prose comments in 40 files, 0 unreadable
$ echo $?
1
```

`check` never writes. `fix` writes, and writes nothing it could not prove. They are two
subcommands rather than a flag pair because a strip that runs by accident costs a working
tree.

```console
$ python3 cli.py fix src/
comments: rewrote 38 of 40 files, refused 0
```

Exit codes: **0** clean, **1** `check` found prose, **2** a file could not be read with
certainty or refused its own proof. A CI step and a commit hook both read the same 1.

## What counts as a comment, and what does not

A comment is prose unless a tool reads it. That is the whole test, and it is why the
allowlist in `directives.py` is not a matter of taste: strip `# noqa` and the linter
fails, strip `// @ts-expect-error` and the compiler fails, strip a shebang and the file
stops being executable. `SPDX-License-Identifier` and a `/*!` banner are kept for a
different reason - deleting a licence notice is not a formatting decision.

Measured over this repository on 2026-09-12: of 10263 `#` comments in the tracked Python
tree, 335 are directives and 9928 are prose. Docstrings are counted as prose and are the
larger half at 9612.

## Languages

Run `python3 cli.py languages` for the live list. Config, data and prose formats - YAML,
TOML, JSON, Markdown - are **not** claimed: their comments are the only place a why can
live, so the kit declines rather than guessing.

## The three proofs, and why they exist

A wrong strip does not fail loudly. It deletes code silently, inside a diff thousands of
lines wide. So `strip.py` refuses any edit it cannot prove:

1. **Python re-parses and its syntax tree is unchanged**, docstrings aside.
2. **The strip is idempotent** - a second pass changes zero bytes. A mis-read string
   usually yields a different span set the second time, which is how this catches the
   class of error the first proof cannot see for non-Python files.
3. **No string literal changed** - every quoted run in the output was in the input. This
   is the check that catches a `//` inside a JavaScript string being read as a comment.

They are not decoration. Driven over this repository's 560 Python files on 2026-09-12 the
proofs refused 95 files on the first run and 84 on the second, and the defect they were
pointing at was real both times: a blank-line pass that mangled indentation, and then
`ast` reporting `col_offset` in **UTF-8 bytes** where `tokenize` reports characters, so a
docstring holding one em dash ate the next line's first space. After both fixes, 560 of
560 strip clean.

## Where it stops, stated rather than hidden

- A `${...}` substitution inside a JavaScript template literal is treated as string
  content, so a comment written in there survives. That is a miss, not a corruption.
- A `<script>` or `<style>` block inside HTML is not descended into.
- The walk is the kit's own, because a subprocess is forbidden here, so it skips
  directories by name rather than by asking git what is ignored.

## Failure mode

**Fail closed on a question.** A file it cannot lex with certainty raises and is left
alone; a strip it cannot prove raises and nothing is written. It never guesses, because
every guess here is a deletion.
