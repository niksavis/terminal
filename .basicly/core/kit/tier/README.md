# Tier injection kit

**A subagent declares a portable tier. This kit makes the spawn run on the model that the
tier resolves to.** The kit needs no basicly: no `import basicly`, nothing on `PATH`, no
third-party package and no network.

| File | What it does |
| --- | --- |
| `tier_resolver.py` | tells which model a tier means for one host surface |
| `claude_tier_hook.py` | rewrites a Claude Code spawn to use that model |
| `install_hook.py` | writes the hook into the host settings |
| `model-map.json` | the data that all three files read; `init` vendors it beside them |

The `model-tier` skill, which `init` writes, tells an agent when to use the kit. A repository
that installs basicly also gets the `tier-injection` skill. This file tells how the kit
behaves and where it stops.

## How each host applies a tier

| Host | How the kit applies a tier |
| --- | --- |
| Claude Code | At spawn time. A `PreToolUse` hook adds the resolved model to the `Agent` tool input. |
| Copilot CLI | The kit does not apply it. The installer declines and gives the reason below. |
| Codex | The resolver answers for the `openai` surface. The installer has no Codex host. |

The spawn-time path is preferred. A model id in every definition file is a duplicated fact,
and it becomes wrong without a warning when the vendor retires the id.

For Copilot, the installer writes nothing, gives this reason and exits 1:

```console
$ python3 .basicly/kit/tier/install_hook.py --host copilot
copilot: nothing installed - this kit wires no copilot spawn yet. That host selects a subagent's model in configuration rather than through a hook, so a declared tier is projected into .github/agents and nothing there reads it. Claude is wired and works
```

A script can use the exit code and does not need to parse the text.

## Install

Install the kit with `uvx`. The kit is a separate package, so a repository without basicly
gets it with one command:

```sh
uvx --from git+https://github.com/niksavis/basicly#subdirectory=packages/basicly-tier basicly-tier init
```

`init` does these steps:

- It vendors the kit into `.basicly/kit/tier`. After that, plain `python3` runs the kit
  with no `uvx`, no network and nothing on `PATH`.
- It adds `.basicly/kit/tier/__pycache__/` to `.gitignore`.
- It writes the kit skill into `.claude/skills/tier/` and `.agents/skills/tier/`. Without
  the skill, no agent knows that the kit exists.
- It runs `install_hook.py`, so the Claude Code hook is written at project scope.

`init` refuses when basicly already manages the kit at `.basicly/core/kit/tier`, because
two copies would drift. Then run `basicly install` to update that copy.

The other subcommands:

- `update` vendors the kit again and reports what changed.
- `status` tells whether the installed copy matches the package.
- `uninstall` removes the hook, the skill and only the files that `init` wrote.

With `--with-instructions`, `init` also writes a short always-on block into each of these
files that exists: `CLAUDE.md`, `.claude/CLAUDE.md`, `AGENTS.md` and
`.github/copilot-instructions.md`. The block is inside marked lines. A second run does not
duplicate it, and `uninstall` removes it. Without the flag, `init` does not edit your
instruction files. It tells you where to read the block.

You can also run the kit without vendoring: `basicly-tier --host claude --tier low` passes
the arguments to the resolver. The map is part of the package, so no other file is
necessary.

You can copy the files by hand, because the kit imports only the standard library. Use this
when another harness drives the kit. The kit behaves the same for each install method.

## Install the spawn hook

```bash
python3 .basicly/kit/tier/install_hook.py --dry-run   # print what it would write
python3 .basicly/kit/tier/install_hook.py             # this repository
python3 .basicly/kit/tier/install_hook.py --user      # every repository on this machine
python3 .basicly/kit/tier/install_hook.py --uninstall # remove only this hook
```

A second run changes nothing. The installer finds its own hook by the script name, so it
never duplicates the hook and never changes a hook that you wrote. If `settings.json` exists
but is not valid JSON, the installer refuses and does not overwrite it.

**If the installer wrote the first hook or agent into a directory that the host did not
have before, quit and start the CLI process again.** The installer prints this notice after
each write. A later edit reloads on its own. To clear the conversation does not reload hooks
or agent definitions.

### The two scopes use different commands

The project file `.claude/settings.json` is committed and shared. Its command has nothing
that is specific to one machine. For a kit at `.basicly/kit/tier`, it is:

```json
"command": "uv run --no-project --no-python-downloads python \"${CLAUDE_PROJECT_DIR}/.basicly/kit/tier/claude_tier_hook.py\""
```

`--no-python-downloads` keeps the spawn path off the network: the command fails and does not
download an interpreter. If you have no `uv`, pass `--interpreter "py -3"` or another
command that runs Python.

The user file `~/.claude/settings.json` is local to one machine. `--user` writes absolute
paths, so it needs nothing on `PATH`. When `CLAUDE_CONFIG_DIR` is set, `--user` writes
`settings.json` in that directory.

If the hook is outside the repository, a project-scope install refuses. It does not write an
absolute path. Use `--user`, or copy the kit into the repository.

## Check a resolution without a spawn

The resolver prints one JSON object. It exits 0 when it resolved a model and 1 when it did
not.

```console
$ python3 .basicly/kit/tier/tier_resolver.py --host claude --tier low
{"alias": "haiku", "model": "claude-haiku-4-5", "reason": null, "skipped": [], "source": "argument",
 "surface": "anthropic", "tier": "low", "vendor": "anthropic"}
```

The surface changes the model name. The same model is `claude-haiku-4-5` on Anthropic and
`claude-haiku-4.5` on Copilot:

```console
$ python3 .basicly/kit/tier/tier_resolver.py --host copilot --tier low
{"alias": null, "model": "claude-haiku-4.5", ... "surface": "github-copilot", ...}
```

`--name` finds a definition by subagent name. `--default-tier` gives a tier to a definition
that declares none, or to a name with no definition:

```console
$ python3 .basicly/kit/tier/tier_resolver.py --host claude --name my-agent --default-tier medium
{"alias": "sonnet", "model": "claude-sonnet-5", ... "source": "default", "tier": "medium", ...}
```

Other options:

- `--definition PATH` reads the tier from one definition file.
- `--tier` outranks the tier in the definition.
- `--vendor` sets the vendor. Without it, the resolver tries the vendors in the order that
  the map gives for the tier, and lists each vendor it skipped in `skipped`.
- `--map PATH` or the `BASICLY_MODEL_MAP` variable sets the map file.
- The `BASICLY_DEFAULT_TIER` variable gives the default tier when `--default-tier` is absent.

**The resolver fails closed.** An unavailable cell has no model, and the resolver never uses
the model of a different tier:

```console
$ python3 .basicly/kit/tier/tier_resolver.py --host copilot --tier low --vendor google
{"alias": null, "model": null, "reason": "google low is unavailable on github-copilot:
 provider 'github-copilot' serves no model named 'Gemini 3.1 Flash Lite'", ...}
$ echo $?
1
```

## Use the map from another harness, without basicly

You can copy the four files to a different location. Keep the two directories beside each
other, or give `--map` the path to the map:

```console
$ find . -type f
./kit/tier/claude_tier_hook.py
./kit/tier/install_hook.py
./kit/tier/tier_resolver.py
./models/model-map.json

$ env -i python3 -S -I kit/tier/tier_resolver.py --host claude --tier high --map models/model-map.json
{"alias": "opus", "model": "claude-opus-5", ... "tier": "high", "vendor": "anthropic"}
```

This command runs in an empty environment: no `PATH`, no `HOME`, no `site` (`-S`) and
isolated mode (`-I`). It checks that the kit needs no basicly. Your harness reads `model`, or
`alias` where the surface uses the short name, and sets the model in its own way. The JSON
output is the contract.

## How the hook changes a spawn

1. **The hook copies every key of the original tool input and adds only `model`.** It does
   not remove or change other keys.
2. **The hook adds `model` only when the tool input has none.** If the input or the
   definition frontmatter already names a model, the hook does nothing.
3. **The hook writes the short alias, not the full model id.** The aliases are `haiku`,
   `sonnet`, `opus` and `fable` for the tiers `low`, `medium`, `high` and `maximum`.
4. **When `CLAUDE_CODE_SUBAGENT_MODEL` is set, the hook does nothing.** Examine that
   variable first when an injection seems to have no effect.
5. **The host loads a hook in a new directory only when the CLI process starts.** See the
   restart notice in [Install the spawn hook](#install-the-spawn-hook). A dry run or a run
   that changes nothing does not print the notice, because there is nothing to reload.

## Debug an injection

Give the hook a `PreToolUse` payload on stdin, as the host does:

```console
$ printf '%s' '{"tool_name":"Agent","cwd":"'"$PWD"'","tool_input":{"subagent_type":"my-agent","prompt":"x"}}' \
    | python3 .basicly/kit/tier/claude_tier_hook.py
{"hookSpecificOutput": {"hookEventName": "PreToolUse",
 "updatedInput": {"model": "haiku", "prompt": "x", "subagent_type": "my-agent"}}}
```

**No output is a valid answer, and it is the usual one.** The hook exits 0 with no output,
and the host default model stays, in these cases:

- The call is not an `Agent` spawn.
- `CLAUDE_CODE_SUBAGENT_MODEL` is set.
- The tool input or the definition frontmatter already names a model.
- The hook finds no map in the directory tree of the spawn.
- The hook finds no definition file `.claude/agents/<name>.md` in the spawn directory or
  the home directory.
- Nothing resolves: the definition declares no tier, the tier is unknown, or the map marks
  the cell unavailable.

A definition that declares no tier is the usual cause:

```console
$ printf '%s' '{"tool_name":"Agent","cwd":"'"$PWD"'","tool_input":{"subagent_type":"no-tier-agent","prompt":"x"}}' \
    | python3 .basicly/kit/tier/claude_tier_hook.py
$ echo $?
0
```

To find out if the hook declined or is broken, ask the resolver the same question. The
resolver gives a `reason` where the hook gives no output.

## Constraints this kit must keep

The constraints for all kits are in [`../README.md`](../README.md). These constraints are
for this kit only.

- **Fail closed.** An unavailable cell has no `model` key, so a lookup gives no model and
  does not use a default. `alias` is never set without `model`.
- **A defect in the hook must not stop a spawn.** Input that is not valid JSON, and a file
  that the hook cannot read, give exit 0 with no output. The hook is a convenience in the
  spawn path, not a security boundary.
- **The hook looks for the map in the directory tree of the spawn.** A map beside the kit
  counts only when the kit is inside that tree. Without this limit, a hook installed once
  per machine would inject a model into each unrelated repository on that machine.
