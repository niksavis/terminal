# Put the Linux node on PATH in a non-interactive WSL shell

## Cause

An interactive shell reads `~/.bashrc` or `~/.zshrc`. That profile runs nvm and puts the
active node `bin` directory first on `PATH`. A script, a background job or a hook runs
non-interactively and does not read the profile. Then WSL interop can resolve `node` or
`npx` to a Windows `node.exe` under `/mnt/c/...`. That node is the wrong runtime, or it
cannot find the packages installed on Linux.

The symptom is a node tool that fails only from a script or a background job, and passes
in your terminal. The failure is deterministic, not flaky.

## Fix

Put the nvm node `bin` directory first on `PATH` before the script runs git, node or npx:

```sh
NODE_BIN="$HOME/.nvm/versions/node/$(ls "$HOME/.nvm/versions/node" | tail -1)/bin"
export PATH="$NODE_BIN:$PATH"
```

Then make sure that the Linux node resolves:

```sh
command -v node   # expect ~/.nvm/versions/node/<version>/bin/node, not /mnt/c/.../node.exe
```

## Other ways

- Run the command in a login shell, which loads nvm: `bash -lc 'git commit ...'`.
- When more than one node version is installed, name the version instead of `tail -1`.
