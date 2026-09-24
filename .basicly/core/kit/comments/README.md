# Comments kit

**The code is the source of truth, so a code file carries no prose.** This kit reports each
prose comment in a code file, and removes the comments when you ask. The kit needs no
basicly: no `import basicly`, nothing on `PATH`, no third-party package, no network and no
subprocess.

| File | What it does |
| --- | --- |
| `languages.py` | the comment and string grammar of each language that the kit claims |
| `directives.py` | the comments that a tool reads, which a strip must keep |
| `lexer.py` | finds comment spans in a file that is not Python, without entering a string |
| `python_source.py` | finds comments and docstrings in Python exactly, with `tokenize` and `ast` |
| `scan.py` | selects the lexer for a file and removes directives from the findings |
| `strip.py` | the edit, and the three proofs that it changed only prose |
| `cli.py` | the `check`, `fix` and `languages` subcommands |
| `GUIDANCE.md` | the kit skill, which `init` writes into each agent skill root |
| `INSTRUCTION.md` | the always-on block that `--with-instructions` writes |

## Use

```console
$ python3 cli.py check src/
src/thing.py:12: # what this function does
comments: 1 prose comments in 40 files, 0 unreadable
$ echo $?
1
```

`check` never writes. `fix` writes, and it writes nothing that it cannot prove safe. They are
two subcommands, not a flag, because an accidental strip can damage a working tree.

```console
$ python3 cli.py fix src/
comments: rewrote 38 of 40 files, refused 0
```

Without a path, both subcommands use the current directory. `--skip NAME` skips one more
directory name, in addition to the built-in list (for example `.git`, `node_modules` and
`.venv`).

Exit codes:

- **0**: no prose found, or `fix` refused no file.
- **1**: `check` found prose.
- **2**: the kit could not read a file with certainty, or a strip failed its proof.

A CI step and a commit hook read the same exit code 1.

## Install

Install the kit with `uvx`. The kit is a separate package, so a repository without basicly
gets it with one command:

```sh
uvx --from git+https://github.com/niksavis/basicly#subdirectory=packages/basicly-comments basicly-comments init
```

`init` does these steps:

- It vendors the kit into `.basicly/kit/comments`. After that, plain `python3` runs the kit
  with no `uvx`, no network and nothing on `PATH`.
- It writes the kit skill into `.claude/skills/comments/` and `.agents/skills/comments/`.
  Without the skill, no agent knows that the kit exists.

The other subcommands:

- `update` vendors the kit again and reports what changed.
- `status` tells whether the installed copy matches the package.
- `uninstall` removes only the files that `init` wrote.

With `--with-instructions`, `init` also writes a short always-on block into each of these
files that exists: `CLAUDE.md`, `.claude/CLAUDE.md`, `AGENTS.md` and
`.github/copilot-instructions.md`. The block is inside marked lines. A second run does not
duplicate it, and `uninstall` removes it. Without the flag, `init` does not edit your
instruction files. It tells you where to read the block.

You can also run the kit without vendoring: `basicly-comments <subcommand>` passes the
arguments to the kit.

You can copy the files by hand, because the kit imports only the standard library. Use this
when another harness drives the kit. The kit behaves the same for each install method.

## What is a comment, and what is not

A comment is prose unless a tool reads it. This is the only test, so the list in
`directives.py` is not a choice of style. If you remove `# noqa`, the linter fails. If you
remove `// @ts-expect-error`, the compiler fails. If you remove a shebang, the file does not
run. The kit also keeps `SPDX-License-Identifier` and a `/*!` banner, because a licence
notice is not a format decision.

Docstrings are prose.

## Languages

Run `python3 cli.py languages` for the list of file extensions. The kit does not claim
configuration, data or prose formats such as YAML, TOML, JSON and Markdown. In those files, a
comment is the only place for a reason, so the kit does not guess.

## The three proofs

A wrong strip does not fail visibly. It removes code without a sign, inside a very large
diff. Thus `strip.py` refuses each edit that it cannot prove:

1. **Python parses again and its syntax tree is the same**, without the docstrings.
2. **A second strip changes zero bytes.** A string that the kit read incorrectly usually
   gives different spans on the second pass. This proof finds that error in files that are
   not Python, where the first proof does not apply.
3. **No string literal changed.** Each quoted string in the output was in the input. This
   proof finds a `//` inside a JavaScript string that the kit read as a comment.

`ast` gives column offsets in UTF-8 bytes, and `tokenize` gives them in characters. The kit
converts between the two, so a docstring with a character of more than one byte does not
remove text from the next line.

## Limits

- The kit reads a `${...}` substitution in a JavaScript template literal as string content.
  A comment in the substitution stays. This is a miss, not a corruption.
- The kit does not read a `<script>` or `<style>` block inside HTML.
- The kit walks the directories itself, because it must not start a subprocess. Thus it
  skips directories by name. It does not ask git which files are ignored.

## Failure mode

**The kit fails closed.** If it cannot lex a file with certainty, it raises an error and
does not change the file. If it cannot prove a strip, it raises an error and writes nothing.
It never guesses, because each guess here removes text.
