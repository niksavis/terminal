# basicly v0.26.10 consumer validation

Record: `term-21t2uw`. Date: 2026-10-19. Host: Linux under WSL.

The checkout started clean at `328bbad`. After basicly v0.26.10 was published,
its release wheel was downloaded and installed with `basicly install`.
All 463 packaged code and resource members matched the tagged basicly source.

The installer removed the local `basicly-workspace` Codex selection and profile.
`permissions-check` passes. Consumer `basicly.toml` and all nine tracked local
overlay files remained byte-identical to their saved copies.

The installer updated its managed command pins. The terminal skill installer
and contributor commands now also use v0.26.10. Historical validation reports
retain their original versions.

Full verification passed all five declared checks, including 662 tests in 2.17s.
The six extended repository checks passed, including Markdown and the rendered
cheat-sheet comparison. With WSL detection forced off in all five importing
modules, all 662 tests passed in 1.78s; the temporary fixture was removed.

`check`, `skills-check`, `hooks-check`, `permissions-check`, `styles-check`,
`agents-check` and `catalog lint` passed. Routing is 56/60 against the 85% floor.
The instruction-size check reports the existing Claude guidance at 12,168
characters; it remains a warning. No application behavior was changed.

These checks do not establish Windows-native or macOS execution, agent host
callbacks or remote terminal CI results.
