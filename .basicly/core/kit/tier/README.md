# Tier injection kit

**A subagent declares a portable tier; this kit makes the spawn actually run on the
model that tier resolves to.** Three Python files and one JSON map, with **no
basicly**: no `import basicly`, nothing on `PATH`, no third-party package, no
network. Copy them into a repository that has never heard of this harness and they
work.

| File | What it does |
| --- | --- |
| `tier_resolver.py` | answers _which model_ a tier means, for one host surface |
| `claude_tier_hook.py` | rewrites a Claude Code spawn to use it |
| `install_hook.py` | wires the hook into the host's settings |
| `../models/model-map.json` | the committed data all three read ([contract](../models/README.md)) |

The `tier-injection` skill is the entry point for using it. This file is the
reference for how it behaves and where it stops.

## The hybrid: one host resolves at spawn time, the other cannot

| Host | How a tier is applied | Why |
| --- | --- | --- |
| **Claude Code** | **dynamically**, at spawn time, by the hook here | it exposes a `PreToolUse` hook that can rewrite the `Agent` tool's input |
| **Copilot CLI** | **statically** — frontmatter in the definition, plus `copilot --model` for the session | it exposes no hook that fires for a spawn, so there is nothing to intercept |

Dynamic is preferred because a model pinned into a definition file is a fact
duplicated in every definition, and it goes stale silently. The static path is the
documented **fallback**, not a second-class accident.

**Corrected 2026-08-08.** This section previously said copilot "has no hook surface
at all", citing no hooks directory under `~/.copilot`, no hook key in `settings.json`
and no hook option in `--help`. **All three were artifacts of the probe.** Copilot CLI
does support hooks: they are documented under `copilot help config` and in GitHub's
own reference, configured **inline** under a `hooks` key in `config.json` (user level)
or `settings.json` (repo level), or as `.github/hooks/*.json` files — and basicly
already ships one, `basicly-tool-usage-copilot.json` on `postToolUse`. The documented
events are `sessionStart`, `sessionEnd`, `userPromptSubmitted`, `preToolUse`,
`postToolUse` and `errorOccurred`.

**What remains true is narrower, and it is the part this kit depends on.** Across three
probes on **1.0.77** a `preToolUse` hook never fired _for an agent spawn_ — on agent
delegation, on a shell tool with `--allow-all-tools`, and on the same without it. And
even where `preToolUse` does fire, GitHub documents it as able to **approve or deny** a
tool call; this kit needs to **rewrite** one, which is a strictly stronger capability.
So the static fallback stands until someone demonstrates a spawn-time rewrite, and the
open question is _"can a copilot hook modify an `Agent` call?"_, never _"does copilot
have hooks?"_

So the installer **declines for copilot and says why**, rather than reporting a
success for a hook that would never fire:

```console
$ python3 .basicly/core/kit/tier/install_hook.py --host copilot
copilot: nothing installed - no copilot hook is known to fire
for a spawn (...); use static frontmatter plus `copilot --model` instead
```

It exits **1**, so a script can branch on it without parsing the report.

## Install

```bash
python3 .basicly/core/kit/tier/install_hook.py --dry-run   # print what it would write
python3 .basicly/core/kit/tier/install_hook.py             # this repository
python3 .basicly/core/kit/tier/install_hook.py --user      # every repository on this machine
```

Re-running converges: it never duplicates the hook, and it matches hooks by the
script they run, so one you wrote yourself is never touched. A `settings.json` that
exists but cannot be parsed is **refused, never overwritten**.

**If this was the first hook or agent written into a directory the host did not
already have, quit and relaunch — the whole CLI process.** Hooks and agent
definitions are otherwise file-watched and reload within seconds of an edit
(measured against claude 2.1.226, 2026-08-09), so a _later_ change needs nothing.
A _newly created_ scope directory does. Clearing the conversation is not the same
thing and reloads neither, which is the wrong lever a consumer reaches for first —
the hook then appears to do nothing while every diagnostic says it is correctly
installed.

### The two scopes are written differently, on purpose

A repository's `.claude/settings.json` is **committed and shared**, so it gets a
command with nothing machine-specific in it:

```json
"command": "uv run --no-project --no-python-downloads python \"${CLAUDE_PROJECT_DIR}/.basicly/core/kit/tier/claude_tier_hook.py\""
```

`${CLAUDE_PROJECT_DIR}` is substituted by the host itself, before any shell sees
it, so it resolves to the project root whatever the working directory is and it
works under PowerShell too. `--no-python-downloads` keeps the spawn path network
free: it fails closed rather than fetching an interpreter mid-spawn. Pass
`--interpreter "py -3"` if you have no `uv`.

`~/.claude/settings.json` is machine-local, so `--user` keeps absolute paths and
needs nothing on `PATH`. A project-scope install that cannot name the hook relative
to the repository **refuses** rather than falling back to an absolute path.

## Check a resolution without spawning anything

The resolver is a CLI in its own right. It prints one JSON object and exits 0 when
it resolved, 1 when it did not.

```console
$ python3 .basicly/core/kit/tier/tier_resolver.py --host claude --tier low
{"alias": "haiku", "model": "claude-haiku-4-5", "reason": null, "source": "argument",
 "surface": "anthropic", "tier": "low", "vendor": "anthropic"}
```

Surface matters, and not only for spelling — the same model is `claude-haiku-4-5`
to Anthropic and `claude-haiku-4.5` to Copilot:

```console
$ python3 .basicly/core/kit/tier/tier_resolver.py --host copilot --tier low
{"alias": null, "model": "claude-haiku-4.5", ... "surface": "github-copilot", ...}
```

`--name` looks a definition up by subagent name, and `--default-tier` supplies one
for a definition that declares none:

```console
$ python3 .basicly/core/kit/tier/tier_resolver.py --host claude --name code-reviewer --default-tier medium
{"alias": "sonnet", "model": "claude-sonnet-5", ... "source": "default", "tier": "medium", ...}
```

**It fails closed.** An unavailable cell carries no model, and the resolver never
substitutes a neighbouring tier's:

```console
$ python3 .basicly/core/kit/tier/tier_resolver.py --host copilot --tier low --vendor google
{"alias": null, "model": null, "reason": "google low is unavailable on github-copilot:
 provider 'github-copilot' serves no model named 'Gemini 3.1 Flash Lite'", ...}
$ echo $?
1
```

## Drive the map from another harness, with no basicly

The kit is four files. Copy them anywhere, keep the two directories beside each
other or point `--map` wherever you put the map, and call it:

```console
$ find . -type f
./kit/tier/claude_tier_hook.py
./kit/tier/install_hook.py
./kit/tier/tier_resolver.py
./models/model-map.json

$ env -i python3 -S -I kit/tier/tier_resolver.py --host claude --tier high --map models/model-map.json
{"alias": "opus", "model": "claude-opus-5", ... "tier": "high", "vendor": "anthropic"}
```

That is an **empty environment** — no `PATH`, no `HOME`, `-S` for no `site`, `-I`
for isolated mode — which is how the no-basicly constraint is checked rather than
merely claimed. Your harness reads `model`, or `alias` where the surface wants the
short form, and pins it however it pins models. The JSON is the contract.

## Traps

Five, each of which has cost real debugging time.

1. **`updatedInput` replaces the tool input, it does not merge into it** — contrary
   to the general hooks documentation. The hook therefore copies every original key
   through and adds only `model`. Drop a key and it is gone from the spawn.
2. **`model` is absent from `tool_input` unless the caller set it**, so it has to be
   **added**, not rewritten. Code that looks for an existing key to overwrite finds
   nothing and does nothing.
3. **The `Agent` tool's `model` is an alias, not an id.** Measured against the
   2.1.220 binary: it is `enum(["sonnet","opus","haiku","fable"])`, so
   `claude-opus-5` is rejected there — a different vocabulary from the same host's
   definition _frontmatter_, which takes a full id. The hook injects the alias.
4. **`CLAUDE_CODE_SUBAGENT_MODEL` outranks** the per-invocation parameter the hook
   writes. Where it is set, every injection is inert and the hook stays deliberately
   silent. **Check that variable first** when an injection appears not to work.
5. **Installing the hook has no effect until the host CLI process is restarted**, and
   clearing the conversation reloads neither hooks nor agent definitions. Measured with
   a control on 2026-08-01: a definition written by an earlier conversation _and_ a
   brand-new one written seconds before were both rejected as "Agent type not found" in
   a conversation begun by `/clear`, while agents predating the process start loaded
   normally — which rules out the alternative explanation that an unrecognised `tier:`
   frontmatter key was getting the definitions rejected. This is the fifth trap and it
   is the one a reader hits first, so it is in the install steps too rather than only
   here. A dry run and an already-installed converge run do not say it: nothing changed
   for a restart to pick up.

## Debugging an injection

Drive the hook the way the host does — a `PreToolUse` payload on stdin:

```console
$ printf '%s' '{"tool_name":"Agent","cwd":"'"$PWD"'","tool_input":{"subagent_type":"my-agent","prompt":"x"}}' \
    | python3 .basicly/core/kit/tier/claude_tier_hook.py
{"hookSpecificOutput": {"hookEventName": "PreToolUse",
 "updatedInput": {"model": "haiku", "prompt": "x", "subagent_type": "my-agent"}}}
```

**Silence is a valid answer**, and the common one. The hook declines — exit 0, empty
stdout, host default stands — in six cases: the call is not an `Agent` spawn;
`CLAUDE_CODE_SUBAGENT_MODEL` is set; the input or the frontmatter already names a
model; the spawn's directory tree has no map; or nothing resolves (no tier, an
unknown tier, or a cell the map marks unavailable). A definition declaring no tier
is the usual reason:

```console
$ printf '%s' '{"tool_name":"Agent","cwd":"'"$PWD"'","tool_input":{"subagent_type":"code-reviewer","prompt":"x"}}' \
    | python3 .basicly/core/kit/tier/claude_tier_hook.py
$ echo $?
0
```

To tell "declined" from "broken", ask the resolver the same question directly — it
reports a `reason` where the hook is silent.

## Constraints this kit must keep

The kit-wide constraints are in [`../README.md`](../README.md). These are this kit's own.

- **Fail closed.** An unavailable cell carries no `model` key, so a lookup raises
  rather than defaulting, and `alias` is never set without `model`.
- **A bug here must never stop an agent from spawning.** Malformed input, an
  unreadable file, or any unexpected error exits 0 with no output. This is a
  convenience in the spawn path, not a security boundary.
- **The map is looked up from the spawn's own directory tree**, with the
  kit-adjacent fallback off. The kit is always beside itself, so with that fallback
  on, a hook installed once per machine would inject a model into every unrelated
  repository on it.

## Where the evidence lives

The standalone design note (`docs/design/tier-kit.md`) was deleted 2026-08-08 once the kit
shipped: this README is now the whole record, and the traps above are the part that was worth
keeping. The hybrid rationale — why injection is preferred over static emission, and why copilot
cannot take it — is in the section above.
The work records carry the measurements: `basicly-wbsz.1` the resolver, `wbsz.2` the hook
and the alias finding, `wbsz.3` the installer and the live end-to-end proof,
`basicly-dukb` the portable project-scope command.
