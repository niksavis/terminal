# The markdownlint hook

The hook finds node itself and never calls `npx`. It uses the first usable node from this
list, and never a Windows node under `/mnt`:

1. `node` on `PATH`
2. the newest node under nvm (`$NVM_DIR`, or `~/.nvm`)
3. `/usr/local/bin/node`, then `/usr/bin/node`

The hook and `basicly install` refuse missing prerequisites before reporting success.
Install checks before writing files, including with `--dry-run`. Read the refusal:

| Message | Fix |
| --- | --- |
| *node_modules/markdownlint-cli2/... is missing* | Run `npm ci` when the package is locked. Otherwise get approval, then run `npm install --save-dev markdownlint-cli2` and commit the package files. |
| *no usable node found on PATH, under nvm, or in /usr/bin* | Install a Linux node, for example `nvm install --lts`. |

The enabled hook reads inputs from the repository's `.markdownlint-cli2.jsonc`,
`.markdownlint-cli2.yaml`, `.markdownlint-cli2.cjs` or `.markdownlint-cli2.mjs`.
A style-only `.markdownlint.json` file does not select CLI2 inputs. Keep existing input and
rule choices; install creates no Markdown policy. Before a first commit, configure
real consumer Markdown inputs. The first-loop tutorial explicitly chooses `README.md`
and `NOTES.md`, with a clean README and every default rule enabled.

Only an explicit configuration opts out. The hook then prints `markdownlint: opted out by
hooks.markdownlint.enabled=false` and exits 0:

```toml
[hooks.markdownlint]
enabled = false
```

The hook reads `basicly.toml`, sorted `basicly.d/*.toml`, then `basicly.local.toml`.
Later settings win. Put a repository-wide opt-out in `basicly.toml`, and a machine-only opt-out in `basicly.local.toml`.
A malformed setting refuses. A technology selection excluding Node
does not install the markdown gate or require its runtime.
