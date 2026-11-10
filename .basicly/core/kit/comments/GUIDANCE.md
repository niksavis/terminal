---
name: no-comments
description: Keeps prose comments and docstrings out of code: where a fact goes instead and which tool directives stay. Use when writing a comment or docstring, or when the no-comments gate refuses a commit.
---

# No comments in code

The code is the only source of truth, so a change cannot leave a stale claim beside it.

## Steps

1. Run `python3 .basicly/core/kit/comments/cli.py check <path>` on each refused or edited file. It lists each prose comment and docstring.
2. Move each fact to the place the table below names. Fix the code when the fact says what it does.
3. Before step 4, turn a plain licence header, such as `# Copyright 2026 X`, into
   `SPDX-License-Identifier` and `SPDX-FileCopyrightText` lines, because `fix` removes a plain header.
4. Run `python3 .basicly/core/kit/comments/cli.py fix <path>` for the prose that is left. Run `check` again until it reports 0.
5. Stage the files and commit again.

## Rules

- **Put the fact where something checks it.** A comment is a claim that nothing checks.
- **Fix the code when it needs prose to say what it does.** Rename it, split it, or give
  the condition a name.
- **Do not write code that is harder to read.** A short name, a function with nine
  branches or a bare magic number has no comment to excuse it.
- **Keep each directive, with its code and a reason after it.** A tool reads the
  directive, and the reason is part of it.

## Where a fact goes

| The fact | Where it goes |
| --- | --- |
| A measurement: a count, a time, a rate | the commit message, and the issue or record of the change |
| What a function raises, changes or returns | a test that asserts it, and the type signature |
| What a bare `str` can hold | a type, an enum or a validator |
| Why this branch and not the other | a name for the condition, or a test named after the case |
| Which incident a guard exists for | the issue id in the commit message, and the test that reproduces it |
| What the module is for | its README, or the design document |
| A fact you cannot place | it was not necessary. Drop it. |

## Directives that stay

`check` never reports a directive, and `fix` never removes one. Among them:

`noqa` · `nosec` · `type: ignore` · `pragma: no cover` · `fmt: off` / `fmt: on` / `fmt: skip`
· a shebang · `eslint-disable` · `prettier-ignore` · `@ts-expect-error` · `@ts-nocheck`
· `stylelint-disable` · `go:build` · `CHECKSTYLE:` · `NOSONAR` · `SPDX-License-Identifier`
· `SPDX-FileCopyrightText` · a `/*!` licence banner · an HTML conditional comment.
`.basicly/core/kit/comments/directives.py` holds the full list.

## Commands

```sh
python3 .basicly/core/kit/comments/cli.py check <path>      # report; exit 1 when it finds prose
python3 .basicly/core/kit/comments/cli.py fix <path>        # remove the prose
python3 .basicly/core/kit/comments/cli.py languages         # each file extension it covers
```

- `check` never writes.
- `fix` writes only a change it can prove. A second `fix` run must change nothing, and every
  string literal must stay. A Python file must parse to the same syntax tree.
- `fix` reports a file that it cannot read with certainty and leaves the file unchanged.

## Scope

YAML, TOML, JSON and Markdown keep their comments, because no code beside them is the
source of truth. `check` and `fix` skip vendored directories such as `vendor` and `node_modules`.
Run `languages` for the current list.

## Comment ratchet

Strict mode, `[hooks.comments] policy = "no-comments"`, is the default and the goal.
When a repository explicitly selects `policy = "no-comment-ratchet"`, leave unrelated legacy
prose alone and add no new prose. The hook compares complete parsed comments and docstrings
in HEAD and the staged index, so rewritten or duplicated prose is new prose.
`python3 .basicly/core/hooks/comment_ratchet.py <path>` runs that check in a basicly repository.
The kit `check` command stays strict. Remove the ratchet setting once no prose is left.
