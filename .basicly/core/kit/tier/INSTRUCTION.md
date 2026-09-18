## Model Tier

**A subagent declares a portable tier, never a model id** — `low`, `medium`, `high`,
`maximum` — and the kit resolves it to the model that tier means for the host in play:

```sh
python3 .basicly/kit/tier/tier_resolver.py --host claude --tier low
```

Choose the tier by how much judgment the work needs, not by caution: `low` for mechanical
and checkable, `high` for design judgment or a review that must catch subtle faults. It
fails closed rather than substituting a neighbouring tier. See the `model-tier` skill.
