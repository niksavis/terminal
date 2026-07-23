# Putting the repo's node on PATH in a non-interactive WSL shell

## Why it happens

Login and interactive shells source `~/.bashrc` / `~/.zshrc`, which run `nvm` and
prepend the active node's `bin` to `PATH`. Scripts, background jobs, and hooks
launched by a headless agent run *non-interactively* and skip that profile. With no
nvm `bin` on `PATH`, WSL interop can resolve `node` / `npx` to a Windows install
(`node.exe` under `/mnt/c/...`), which either runs the wrong runtime or cannot see
the Linux-installed `markdownlint-cli2`.

Symptom: a node-based hook (markdownlint) fails or misbehaves only from scripts, CI,
or background jobs, and passes when you commit interactively. It reads as flaky; it
is deterministic.

## The fix

Prepend the active nvm node's `bin` to `PATH` before running git or npx from a
script or background job:

```sh
NODE_BIN="$HOME/.nvm/versions/node/$(ls "$HOME/.nvm/versions/node" | tail -1)/bin"
export PATH="$NODE_BIN:$PATH"
```

Then confirm the resolution points at the Linux node, not the Windows one:

```sh
command -v node   # -> /home/<user>/.nvm/versions/node/vXX/bin/node, NOT /mnt/c/.../node.exe
```

## Alternatives

- Run the command from an interactive login shell so the profile loads nvm for you:
  `bash -lc 'git commit ...'`.
- If several node versions are installed, pin the exact one instead of `tail -1`.

This is the node-resolution half of the WSL interop story; the shell and filesystem
interop model is covered by the `wsl` skill.
