# Model map

Two files, one idea: **a tier is declared once and resolved to a concrete model per
vendor, and to a per-surface spelling, cost and availability.**

| File | Kind | Edit it? |
| --- | --- | --- |
| `anchors.yaml` | reviewed input — one anchor per (tier, vendor), plus surfaces and the capability rule | yes |
| `model-map.json` | generated artifact — every (tier, vendor, surface) cell resolved | no, regenerate |
| `model-map.schema.json` | the map's published JSON Schema | only with the generator |

## The concept

No provider model id is portable. The same model is `claude-haiku-4-5` to
Anthropic and `claude-haiku-4.5` to GitHub Copilot, and only some surfaces read a
`model` key at all — so an id pinned in one place is wrong or invisible everywhere
else. An agent source therefore declares a **model tier** (`low`, `medium`,
`high`, `maximum` — `schema.MODEL_TIERS`, cheapest first) and this map holds the
resolution.

Three axes, because all three change the answer:

- **tier** — the portable capability level a source declares.
- **vendor** — who makes the model. Four are covered: Anthropic, OpenAI, Moonshot
  AI, Google.
- **surface** — where the id gets written. Each key is a models.dev provider id.

Surface is not cosmetic, and it is not just about spelling:

- **Cost varies by surface.** Measured 2026-07-31, `gpt-5.6-luna` is 0.2/1.2 USD
  per MTok on `openai` and **1/6** on `github-copilot`; `gpt-5.6-terra` is 2/12
  versus **2.5/15**. A single per-vendor price would be wrong, so cost lives on the
  surface entry.
- **Limits vary by surface.** Copilot serves `claude-haiku-4.5` with a
  136,000-token input cap where Anthropic's `claude-haiku-4-5` has none.
- **Availability varies by surface** — see below.

## Unavailable is a value, not a gap

A tier can legitimately have no model on a surface. Measured 2026-07-31,
`github-copilot` serves exactly one Moonshot model (`kimi-k2.7-code`) and its
entire Gemini range is `gemini-2.5-pro`, `gemini-3-flash-preview`,
`gemini-3.1-pro-preview`, `gemini-3.5-flash` — so five of the 32 cells have no
model. Those are recorded explicitly:

```json
{
  "status": "unavailable",
  "reason": "provider 'github-copilot' serves no model named 'Kimi K2.5'"
}
```

There is **no `model` key**, on purpose. A consumer that reads `["model"]` fails
loudly instead of being handed a different tier's model — the silent demotion
`basicly-izda` exists to prevent. The generator never substitutes.

## The collapse is in the data

Only Anthropic publishes a genuine fourth class (Fable). OpenAI, Moonshot and
Google ship three-class ladders, so their `high` and `maximum` resolve to the same
top model — the vendor-ladder fact behind `architecture` D-08's tier routing.
Rather than repeating a row and hoping a reader notices, the collapsed tier carries:

```json
"collapse": { "same_model_as_tier": "high", "reason": "..." }
```

It is declared in `anchors.yaml` and the generator **cross-checks that the two
tiers really do name the same model**, so the declaration cannot drift from the
ids.

Two anchor choices worth knowing:

- OpenAI's `maximum` is not one of the six `-pro` models despite their capability:
  `github-copilot` serves none of them, so the tier would be unusable on one of
  the two surfaces this repo requires.
- Google's top class is a `-preview` id (`gemini-3.1-pro-preview`). Previews get
  renamed or withdrawn at GA, so this is the least stable pin in the map. It is
  pinned rather than guessed at, and `--check` fails naming the id the moment it
  stops resolving. There is deliberately no fallback to an older Pro.

## Only general models can be a tier

Google publishes 41 records and 21 of them are not general text models — image
(`gemini-3.1-flash-image`, "Nano Banana 2"), TTS, embedding, live, and Lyria/Veo
entries; OpenAI ships `gpt-image-2` and `gpt-realtime-2.1`. A sweep would happily
pick an image model as a tier, so `anchors.yaml` states a rule and the generator
**refuses rather than guesses** when an anchor fails it:

```yaml
general_model_rule:
  require_text_input: true
  require_text_only_output: true
  require_tool_call: true
```

`reasoning` is recorded per anchor but deliberately not required — requiring it
would exclude general tool-calling models such as `gpt-4o` and `gemini-2.0-flash`.

## Plug and play

`model-map.json` is a standalone data artifact. It is plain JSON with a
`schema_version`, a documented schema next to it, and a provenance stamp; it
contains no basicly-internal structure and no dependence on this repo's layout.
Copy that one file into an unrelated project and drive your own spawner from it:

```python
import json

MAP = json.load(open("model-map.json"))

def model_for(tier: str, vendor: str, surface: str) -> str:
    """The value to write into `surface`'s model field, or raise if unavailable."""
    cell = MAP["tiers"][tier]["vendors"][vendor]["surfaces"][surface]
    if cell["status"] != "available":
        raise LookupError(f"{vendor} {tier} is unavailable on {surface}: {cell['reason']}")
    return cell["model"]

model_for("low", "anthropic", "github-copilot")  # -> 'claude-haiku-4.5'
model_for("low", "anthropic", "anthropic")       # -> 'claude-haiku-4-5'
model_for("low", "moonshotai", "github-copilot") # -> LookupError, never a substitute
```

Alongside each `model` are `cost_usd_per_mtok.input` / `.output` and
`limit_tokens.context` / `.output`, plus `limit_tokens.input` **only where the
provider publishes a separate input cap** — treat it as optional and fall back to
`context`. `tier_order` carries the vocabulary cheapest-first so a consumer can
downgrade a tier without hardcoding the list, and each surface's `verified` field
says whether its id spelling was actually exercised or is taken from models.dev on
trust.

## Regenerating

```sh
uv run python .scripts/generate_model_map.py          # fetch and rewrite the map
uv run python .scripts/generate_model_map.py --check   # fetch and report drift
```

The generator resolves each anchor through models.dev. There is no `base_model`
field there to link a provider's serving id to the underlying model (it is absent
from every record and from the record schema), so the join is **exact `name`
equality**, corroborated by `family`. The `" (latest)"` suffix is part of the join
key: Anthropic serves both `claude-haiku-4-5` as `Claude Haiku 4.5 (latest)` and
`claude-haiku-4-5-20251001` as `Claude Haiku 4.5`, so stripping it makes the low
anchor ambiguous.

Two rules the generator exists to keep:

- **The fetch happens at authoring and check time only, never in the dispatch
  path.** Nothing that dispatches an agent reads models.dev, so the harness gains
  no runtime network dependency and determinism holds. That is also why the drift
  check is *not* a `[[verify.checks]]` entry: a gate that needs the network must
  not run on every commit. Run `--check` by hand or from a scheduled job. The
  committed map's shape, and its agreement with `anchors.yaml` and `MODEL_TIERS`,
  are gated offline by `tests/test_model_map.py`.
- **The map is reviewed as a diff, and the drift check reports rather than
  auto-applies.** models.dev is community-contributed, so a bad upstream edit
  must surface as a red check, never as a silent change to which model runs
  someone's code. `--check` never writes; it names the id and the change and exits
  non-zero, and accepting the change is a deliberate regenerate-and-review.

`--check` compares only the `tiers` section. Provenance changes on every fetch,
because other providers edit the shared upstream document constantly, so treating
a new digest as drift would make the check fire daily and mean nothing. A cell
flipping `available` to `unavailable` *is* drift and is reported.

## Provenance

The stamp records what models.dev actually offers, and no more. `api.json` is a
CDN-cached generated artifact: the payload carries no commit field (its top level
is provider ids only) and the response carries no `last-modified` header, so
**there is no upstream git commit sha to stamp** and none is claimed. What is
recorded is the `sha256` and byte length of the exact fetched document, the fetch
date, and the CDN `etag`. Note the etag is the first 32 hex digits of that same
sha256, so it corroborates the digest rather than adding independent identity.

Each available cell also carries `upstream_last_updated`, models.dev's own date
for that record — the closest thing to per-model upstream versioning available.
