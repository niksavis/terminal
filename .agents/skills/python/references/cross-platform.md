# Cross-platform Python: the two shell-out traps that fail only on Windows CI

Both bugs below are deterministic, not flaky. They pass every local POSIX run and
fail only on a Windows runner, which is exactly what makes them expensive: the red
build looks intermittent when it is not. The catalog's deterministic gates cannot
catch either — they are runtime behavior — so they live here as judgment.

## 1. A subprocess env must inherit `os.environ`

Passing a hand-built `env` dict to `subprocess.run(..., env=...)` **replaces** the
child's environment; it does not merge. Drop `PATH` and the child can no longer
resolve bare executables.

```python
# Wrong: PATH is gone. `git` still resolves on POSIX (the shell/loader has
# fallbacks) but on Windows the CreateProcess call raises [WinError 2].
subprocess.run(["git", "status"], env={"GIT_AUTHOR_NAME": "ci"})

# Right: start from the real environment, then add or override.
env = {**os.environ, "GIT_AUTHOR_NAME": "ci"}
subprocess.run(["git", "status"], env=env)
```

Rule: build a child env by copying `os.environ` and layering your keys on top.
Only pass a bare dict when you deliberately want a scrubbed environment *and* have
put an absolute executable path (and any required `PATH`) back in yourself.

## 2. A backslash OS path in a shell string is eaten by `shlex.split`

POSIX `shlex.split` (and anything that shell-splits a command *string*) treats `\`
as an escape character. A Windows path such as `sys.executable`
(`C:\Users\...\python.exe`) is silently mangled — the backslashes vanish or merge
the next character — and the command fails to launch. On POSIX there are no
backslashes in the path, so the same code passes. (Incident: basicly-5tjk.)

```python
# Wrong: a shell STRING carrying a Windows path. shlex.split mangles the backslashes.
cmd = f"{sys.executable} -m basicly.cli build"
subprocess.run(shlex.split(cmd))

# Right (preferred): an argv LIST — no shell splitting happens at all.
subprocess.run([sys.executable, "-m", "basicly.cli", "build"])

# Right (when a string is unavoidable): normalize to forward slashes first.
cmd = f"{Path(sys.executable).as_posix()} -m basicly.cli build"
subprocess.run(shlex.split(cmd))
```

Rule: prefer an argv list over a shell string for anything you launch. When a
string is unavoidable, run every embedded OS path through `Path(...).as_posix()`
before it reaches `shlex.split`.

## Why "only Windows CI"

Both traps hinge on a POSIX-only fallback (a resolvable `PATH`, a backslash-free
path). A green local run on Linux or macOS proves nothing about the Windows path.
When a subprocess-touching change lands, reason about the Windows runner explicitly
rather than trusting the local pass.
