# Terminal performance and stability

Investigation date: 2026-10-20.

The Windows event-loop CPU cause remains unproved. These changes remove a measured
startup cost and reduce exposure to specific upstream failure paths. They do not
establish that WezTerm cannot hang on another machine.

## Findings and changes

| Area | Evidence | Result |
| --- | --- | --- |
| Tab titles | [Upstream issue 4788](https://github.com/wezterm/wezterm/issues/4788) reports lag with a trivial callback and large key tables. The supplied handover identified full-config conversion into Lua on the GUI thread. | Keep native tab titles. Reject custom tab and window title callbacks. |
| Renderer | [WezTerm documents](https://wezterm.org/config/lua/config/front_end.html) its default as OpenGL after a WebGPU default reversal. [Issue 7017](https://github.com/wezterm/wezterm/issues/7017) reports a frozen display with WebGPU on a specific Linux driver. | Keep explicit Software on Windows and WSL. Let native Linux and macOS inherit WezTerm's default instead of forcing WebGPU. |
| Kitty images | [Issue 6344](https://github.com/wezterm/wezterm/issues/6344) provides a zero-size image crash. The upstream fix landed in June 2026, after the Windows stable build under test. | Disable the Kitty image protocol by default. This is a compatibility tradeoff for applications that use that protocol. |
| Shell startup | A controlled fzf function recorded two `--zsh` calls when the original zsh template loaded. The first result was discarded. | Capture that result and evaluate it once. Keep the fallback for older fzf versions. |
| Prompt metrics | The full-prompt check uses a real Git clean filter. Enabled metrics invoked it once; the shipped prompt invoked it zero times. | Keep Git metrics disabled and retain branch and status information. |

The image control has a direct source boundary. In the
[Windows stable source](https://github.com/wezterm/wezterm/blob/20240203-110809-5046fc22/term/src/terminalstate/kitty.rs),
`kitty_img` returns before image handling when `enable_kitty_graphics` is false.
The [configuration adapter](https://github.com/wezterm/wezterm/blob/20240203-110809-5046fc22/config/src/terminal.rs)
passes the configured value to that boundary.

The separate iTerm image protocol stays enabled. The
[stable imgcat source](https://github.com/wezterm/wezterm/blob/20240203-110809-5046fc22/wezterm/src/main.rs)
uses that protocol. A live image display was not tested. The isolated CLI probe
required terminal capability replies that the test pseudo-terminal did not supply.
The probe was stopped without touching an existing terminal session.

## Controls and local evidence

The tools used were Windows WezTerm `20240203-110809-5046fc22`, Linux WezTerm
`20260707-093716-fff02ca5`, Starship `1.26.0` in both environments, and fzf `0.74.5` in WSL.

The WezTerm checker reads the shipped template for four explicit inputs. These are
Windows, WSL, native Linux and native macOS. It checks the renderer policy, image
policy, retained performance settings, tabs and status footer. It exercises each
footer with a POSIX path, a Windows path and no working directory.

Each path receives 100 callback calls per platform input. The checker records
1,200 actual calls. During those calls, these five APIs raise an error:

- `wezterm.run_child_process`
- `wezterm.background_child_process`
- `io.open`
- `io.popen`
- `os.execute`

This checks the named APIs. It is not a general sandbox for all possible Lua work.
The checker also rejects custom tab and window title callbacks.

The focused regression file tests the checker with unsafe template mutations.
It re-enables Kitty images, forces native WebGPU, adds title callbacks and adds
each of the five prohibited operations. Every mutation must lose the success
marker and produce the expected diagnostic. The unmodified template must pass.

The focused tests passed on Linux. Native Windows passed 10 tests and skipped the
two zsh cases because native Windows had no zsh executable. Both real WezTerm
executables emitted the success marker. These are platform-input tests, not GPU
rendering tests on four physical platforms.

The full local suite passed all 674 tests. It also passed all 674 tests with the
application's imported WSL detection functions forced to false. The focused
terminal setup suite passed 527 tests. The configured fast checks and the six
extended pre-commit checks passed.

The fzf regression failed against the original template. It observed two
initialization calls instead of one. The changed template passed both modern
fzf and unsupported-option fixtures. The latter verifies that the compatibility
branch remains available.

The full prompt filter check passed with native Windows Starship and WSL
Starship. Windows measured one control invocation in 131 ms and zero configured
invocations in 74 ms. WSL measured one in 20 ms and zero in 6 ms. These are single
warm samples from synthetic repositories, not latency guarantees.

Run the checks from the checkout:

```sh
uv run pytest -q tests/test_terminal_setup/test_responsiveness.py
wezterm --config-file .scripts/check_wezterm_callbacks.lua show-keys --lua
uv run --with-editable . python .scripts/check_starship_prompt_filters.py
```

Require `TERMINAL_CALLBACK_CHECK_PASS` from WezTerm. Its exit code alone is not a
pass because configuration errors can fall back to defaults. The pytest wrapper
bounds each external check to 30 seconds. CLI-dependent tests skip when their
executable is absent. No CI installation or workflow was changed.

## Hypotheses that did not justify a change

The [stable GUI source](https://github.com/wezterm/wezterm/blob/20240203-110809-5046fc22/wezterm-gui/src/termwindow/mod.rs)
already compares right-status text before it updates the title. Another Lua cache
would duplicate that comparison. The existing footer remains short and uses no
external processes. Its interval remains 3,000 ms.

The [stable Windows loop](https://github.com/wezterm/wezterm/blob/20240203-110809-5046fc22/window/src/os/windows/connection.rs)
waits when its message queue is empty. A sample inside `PeekMessageW` alone does
not identify why the thread stays busy. The current host's six-second read-only
sample used 4.297 CPU seconds over 6.065 wall seconds. That is about 71% of one
logical core. The window responded in all three samples. Its live config still
contained the old custom tab formatter, so this is a baseline before that fix.

Software is a configuration choice, not sufficient proof of the active renderer.
The [Windows loader](https://github.com/wezterm/wezterm/blob/20240203-110809-5046fc22/window/src/os/windows/wgl.rs)
attempts to find Mesa when software rendering is requested. Check the renderer in
the debug overlay during a coordinated diagnostic window. Loaded driver DLLs
alone do not establish which path draws the window.

[WezTerm issue 7527](https://github.com/wezterm/wezterm/issues/7527) contains reports
about mux allocation failures and multi-agent workloads. Disabling Kitty images
does not fix the general mux codec problem. No such crash was reproduced here.
No nightly upgrade, mux migration or log suppression was applied.

[Starship issue 6065](https://github.com/starship/starship/issues/6065) reports prompt
delays after an extreme command timeout. The shipped timeout remains finite at
1,000 ms. [Starship's configuration reference](https://starship.rs/config/#git-status)
documents that its default status path uses gitoxide. No global Git executable,
submodule or status override was added. The local prompt check did not justify
removing status information.

## WSL and Linux checks

[Microsoft recommends](https://learn.microsoft.com/en-us/windows/wsl/filesystems)
keeping Linux workloads in the Linux filesystem for performance. That guidance
does not justify changing a user's start directory automatically.

[Microsoft documents](https://learn.microsoft.com/en-us/windows/wsl/wsl-config)
the VM memory cap and cache-reclamation modes separately. A large Windows WSL
working set does not establish Linux memory exhaustion. Read available memory,
swap activity and [Linux pressure information](https://docs.kernel.org/accounting/psi.html)
before choosing a memory intervention.

[WSL issue 10675](https://github.com/microsoft/WSL/issues/10675) describes a specific
older systemd and cache-reclamation workload. It does not prove the same cause for
a busy Windows GUI when a separate WSL shell remains responsive. No memory cap,
reclamation mode, system service or kernel setting was changed. No caches were
dropped and no application or distro was restarted.

## Remaining validation

Native macOS and native Linux desktop rendering were not exercised. Neither were
long-duration GUI workloads on low-memory, high-DPI, Intel, AMD, NVIDIA or remote
desktop hosts. No new upper bound on GUI CPU or memory use is claimed.

A future GUI comparison must keep output, pane count, display scale and renderer
constant. Measure CPU seconds over wall time, responsiveness and process memory
separately. Compare idle prompts, active title changes, sustained text output,
resizes and image workloads in disposable sessions. Keep existing sessions alive
and compare actual runtime renderer information before changing that backend.
