## Code Is Authoritative

**A code file carries no prose.** No comment, no docstring: the code is the only source
of truth, so changing it cannot leave a stale claim beside it. The `no-comments` check
refuses the commit; `python3 .basicly/kit/comments/cli.py fix <path>` removes them.

A **directive a tool reads** stays — `noqa`, `nosec`, `type: ignore`, `pragma: no cover`,
a shebang, `fmt: off`, a licence banner.

Put the fact a comment would have carried where it stays true: a name, a test name, the
issue it came from, a README. Needing prose to say *what* the code does is a defect in the
code. See the `no-comments` skill.
