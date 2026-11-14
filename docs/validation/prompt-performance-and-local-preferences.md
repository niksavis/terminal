# Prompt performance and local preferences

The November 2026 investigation found two independent startup costs: Ubuntu and
the managed shell both called `compinit`, and WSL Git status reached its timeout
when inspecting a checkout on a Windows drive.

Setup now retains the managed completion initialization and its security checks,
while suppressing the earlier Ubuntu global initialization. Starship uses the
installed Git executable and, when available, Windows Starship for Windows-drive
status checks from WSL. Missing Windows Starship leaves Linux status active.

## Local measurements

Five warm process launches on one Windows/WSL host produced these medians:

| Check | Before | After |
| --- | ---: | ---: |
| Windows-native prompt in a Windows checkout | 148 ms | 126 ms |
| WSL prompt in a Linux checkout | 25 ms | 13 ms |
| WSL prompt in a Windows checkout | 1,082 ms | 201 ms |
| WSL interactive login shell | About 800 ms | 242 ms |

These are examples from the inspected checkouts, not limits for other machines
or repositories. Prompt metrics remain disabled. The real Git clean-filter
control still distinguishes enabled metrics from the configured prompt and
retains branch and modified-file indicators.

## Readability and machine preferences

A Codex 0.169.0 session inside Herdr 0.9.5 emitted the history prompt fill as
`48;2;68;68;68`. The screenshot's fill pixels also measured RGB 68,68,68.
This is an application-painted RGB fill, so changing ANSI slot 8 cannot change it.
The analysis did not send input or signals to the active panes.

The optional local Tokyo Night-inspired preset uses a navy background and softer
application fills. Its calculated contrast ratios are 11.62:1 for normal text,
4.53:1 for text on the muted slot, and 2.56:1 for muted hints against navy.
Cell background opacity affects application fills generally; it is not a
Codex-specific theme override. Visual preferences can be changed locally.

The shared renderer, refresh-rate, Kitty graphics and ANSI palette defaults stay
unchanged. Setup preserves `wezterm-local.lua` and `starship.local.toml`, applies
local preferences after defaults, and supports both host-to-WSL deployment and a
run inside WSL. The opt-in preset changes no rendering backend.

## Validation

Native Windows passed 721 tests with 27 platform-specific skips. WSL passed all
748 tests. The six configured repository checks passed. The real WezTerm CLI
loaded the optional preset, verified effective local values after deployment,
and retained the conservative renderer/image behavior. Archive configuration
previews passed outside the checkout on both Windows and WSL.

Windows CLI probes now decode WezTerm UTF-8 output explicitly. The WSL CLI unit
fixture owns its Herdr-discovery result. Cross-OS validation uses separate virtual
environments, as described in the contributor guide.

References: [Starship Git status](https://starship.rs/config/#git-status),
[WezTerm appearance settings](https://wezterm.org/config/appearance.html#text-background-opacity),
and the [installed Codex style implementation](https://github.com/openai/codex/blob/rust-v0.169.0/codex-rs/tui/src/style.rs).
