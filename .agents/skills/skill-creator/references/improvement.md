## Contents

- Improve the skill
- Blind comparison
- Tune the description
- Run the scripts
- Reference files

## Improve the skill

1. **Generalize from the feedback.** The skill will run on many prompts that are not in
   the test set. Do not add narrow fixes that fit only these examples, and do not add
   rigid rules. For a stubborn problem, try a different explanation or a different
   pattern of work.
2. **Keep the body lean.** Read the transcripts, not only the outputs. When the skill
   makes the model spend time on steps that do not help, remove the text that causes it
   and run again.
3. **Explain the why.** Understand what the user wants and why, and put that
   understanding into the instructions. A rule in capitals is a sign that a reason is
   missing.
4. **Bundle repeated work.** When every test run wrote a similar helper script, put one
   script in `scripts/` and tell the skill to use it.

Write a revision, read it again, and improve it before you run it.

### The iteration loop

1. Apply the improvements to `skill.yaml`, then run `basicly skills-build`.
2. Run all test cases again into `iteration-<N+1>/`, with the baselines. For a new skill
   the baseline stays `without_skill`. For an improved skill, choose between the original
   version and the previous iteration.
3. Open the viewer with `--previous-workspace` on the previous iteration.
4. Wait for the user to finish the review.
5. Read the feedback, improve, and repeat.

Stop when the user is satisfied, when all feedback is empty, or when the changes stop
helping.

## Blind comparison

To answer "is the new version actually better?", give two outputs to an independent
subagent without saying which version made each, and let it judge. Then analyze why the
winner won. `references/comparator.md` and `references/analyzer.md` give the steps. This
needs subagents, and the human review usually suffices.

## Tune the description

The routing evals in `evals.yaml` test the description against the catalog for free. For
a stronger check, the scripts below run the real host: they call `claude -p` once per
query and run, which costs tokens and time. Ask the user before you start them.

### Write the trigger eval set

Write about 20 queries, half that should trigger and half that should not:

```json
[
  {"query": "the user prompt", "should_trigger": true},
  {"query": "another prompt", "should_trigger": false}
]
```

- Make each query concrete and detailed, as a user types it: a file path, a column name,
  some background, casual wording, an abbreviation or a typo. "Format this data" is too
  abstract to test anything.
- Cover several phrasings of each intent for the queries that should trigger, including
  one that never names the skill and one where another skill competes but should lose.
- Make the queries that should not trigger near misses: they share words with the skill
  but need something else. An unrelated query tests nothing.
- A simple one-step query may not trigger any skill, because the agent can do it alone.
  Use queries that are substantive enough to need the skill.

Show the set to the user before the run. `assets/eval_review.html` is a page for that
review: replace `__EVAL_DATA_PLACEHOLDER__` with the JSON array, and
`__SKILL_NAME_PLACEHOLDER__` and `__SKILL_DESCRIPTION_PLACEHOLDER__` with the name and the
description, write it to the workspace and ask the user to open it. "Export Eval Set"
downloads `eval_set.json`; ask the user where the browser saved it.

### Run the optimization loop

Run the loop from the repository root, in the background, on the projected skill
directory. Use the model id that powers this session, so that the test matches what the
user gets.

```sh
python3 -B <skill-dir>/scripts/run_loop.py \
  --eval-set <workspace>/trigger-eval.json \
  --skill-path .claude/skills/<slug> \
  --model <model-id> --max-iterations 5 --verbose
```

- The loop holds out 40% of the queries as a test set, runs each query 3 times, and
  asks `claude -p` for a better description from the failures on the training set. It
  picks the best description by its score on the held-out set, to avoid overfitting.
- Each run installs a temporary skill named `<slug>-eval-<id>` under `.claude/skills/`
  and removes it when the run ends, also when it fails. A skill already installed with
  the same description competes with the temporary one, so tune a copy, not a skill that
  is live under the same description.
- `--report none` turns off the HTML report; `--results-dir <workspace>` keeps the
  results and the logs.
- `scripts/run_eval.py` runs one evaluation without the improvement step, and
  `scripts/improve_description.py` runs one improvement.

Read the progress from the output and tell the user which iteration is running and its
score.

### Apply the result

Put `best_description` from the JSON output into `skill.yaml`, then run
`basicly skills-build` and `basicly catalog lint`. Show the user the description before
and after, with the scores.

## Run the scripts

`<skill-dir>` is the projected directory of this skill, for example
`.claude/skills/skill-creator`. Every script needs only the Python standard library, so
no basicly engine and no package install is needed. They run on Python 3.12 and 3.14.

```sh
python3 -B .claude/skills/skill-creator/scripts/aggregate_benchmark.py --help
```

- Use `python` where `python3` is not the command name, for example on Windows.
- `-B` writes no `__pycache__` next to the scripts.
- `run_eval.py`, `run_loop.py` and `improve_description.py` need the `claude` command on
  `PATH` and network access, and they spend tokens. The other scripts run offline.

## Reference files

- `references/grader.md`: how to grade assertions against outputs.
- `references/comparator.md`: how to compare two outputs blind.
- `references/analyzer.md`: why one version beat another, and how to read a benchmark.
- `references/schemas.md`: the JSON files of a workspace.
