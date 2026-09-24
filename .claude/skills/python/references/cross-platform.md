# Shell out on every platform

Each mistake below passes on Linux and macOS and fails only on Windows. Each depends on a
POSIX fallback, so a green local run proves nothing about Windows. The failure is
deterministic, not flaky.

## 1. Copy `os.environ` into a child environment

`subprocess.run(..., env=...)` replaces the environment of the child. It does not merge.
Without `PATH`, the child cannot find a bare executable name.

```python
# Wrong: PATH is gone. POSIX still finds git; Windows raises [WinError 2].
subprocess.run(["git", "status"], env={"GIT_AUTHOR_NAME": "ci"})

# Right: copy the real environment, then add or override keys.
env = {**os.environ, "GIT_AUTHOR_NAME": "ci"}
subprocess.run(["git", "status"], env=env)
```

Pass a bare dict only for a deliberately clean environment. Then give an absolute
executable path, and put back any `PATH` that the child needs.

## 2. Keep a Windows path out of a shell string

POSIX `shlex.split` reads `\` as an escape character. It removes the backslashes of a
Windows path such as `sys.executable` (`C:\Users\...\python.exe`), and the command does
not start. A POSIX path has no backslashes, so the same code passes there.

```python
# Wrong: a shell string that carries a Windows path.
cmd = f"{sys.executable} -m tool build"
subprocess.run(shlex.split(cmd))

# Right: an argv list. Nothing splits it.
subprocess.run([sys.executable, "-m", "tool", "build"])

# Right, when a string is necessary: change the path to forward slashes first.
cmd = f"{Path(sys.executable).as_posix()} -m tool build"
subprocess.run(shlex.split(cmd))
```

Use an argv list for every process you start. When a string is necessary, pass each
embedded path through `Path(...).as_posix()` before `shlex.split`.
