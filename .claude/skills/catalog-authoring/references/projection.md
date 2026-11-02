## Phrase a guidance body

- Write concrete, verifiable instructions: "use 2-space indentation", not "format code properly".
- Put each runnable command in a code fence. An agent runs a fenced command as written and improvises on a command in prose.
- Give the alternative with each prohibition. A bare "never X" leaves the agent stuck.
- Give a one-clause reason, so the rule applies beyond its literal case.
- Use at most one `IMPORTANT` marker per projection. More markers make each one invisible. `basicly catalog lint` counts them per composed projection and per skill, and refuses the second one by name. A marker in a code span or a fence does not count.

## Check

```sh
basicly catalog lint
basicly catalog dump
```

- `catalog lint` validates every source against its schema. It refuses a `.md` source and a YAML file without the `.yaml` extension. It runs on commit and in CI.
- `catalog dump` prints what the sources compose to: each planned output, each selected item with the core or `.basicly-local` file it came from, and each overlay override beside the core source it shadows. A wrong projection is a selection question, and `build` prints only the files it wrote.

## Verify where the agent reads it

When a change alters what an agent is told:

- Read it back where the agent reads it: the advertised skill list, the always-on file as loaded, the rule as injected.
- Measure a size or cost claim again on the delivered text before you write the figure into a document. A figure measured on the source is a guess about the host.
- A `user`-invoked skill projects no `description`. Claude Code then fills the listing from the first line of the body.
