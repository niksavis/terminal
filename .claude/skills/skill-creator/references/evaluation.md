## Contents

- Routing evals first
- Test cases
- Run and evaluate the test cases

## Routing evals first

Write `evals.yaml` beside `skill.yaml` before any live run. `basicly catalog lint` runs it
on every commit: it ranks every description against each prompt, deterministically and
at no cost.

```yaml
schema_version: 1
trigger:
  positive:
    - prompt: "a request in the words a user would type"
  negative:
    - prompt: "a near miss that another skill answers"
      owner: other-skill-slug
```

- Write three or more positive prompts and two or more negative ones.
- Paraphrase how a user asks. A prompt copied from the description proves nothing.
- Make each negative a near miss and name the skill that owns it.
- When a prompt fails, fix the description, not the prompt.
- Read every warning that `catalog lint` prints: the rank-1 rate of the whole catalog has
  a floor, and two descriptions above the similarity ceiling are refused.

## Test cases

Write two or three realistic test prompts, the kind a user would actually type. Show them
to the user: "Here are a few test cases I'd like to try. Do these look right, or do you
want to add more?" Then run them.

Put the workspace outside the catalog and outside every projected skill root, for
example in the session scratch directory: `<workspace>/` with `iteration-1/`,
`iteration-2/` and so on. Save the test cases to `<workspace>/evals.json`. Write the
prompts now and the assertions later. `references/schemas.md` gives the full schema.

```json
{
  "skill_name": "example-skill",
  "evals": [
    {
      "id": 1,
      "prompt": "The task prompt of the user",
      "expected_output": "Description of the expected result",
      "files": []
    }
  ]
}
```

## Run and evaluate the test cases

Do this section as one sequence. Each test case gets a directory in the iteration, and
each configuration gets a run directory:

```text
<workspace>/iteration-N/
└── eval-<name>/
    ├── eval_metadata.json
    ├── with_skill/run-1/       outputs/, grading.json, timing.json
    └── without_skill/run-1/    outputs/, grading.json, timing.json
```

### Step 1: Run independent, isolated comparison arms

Each test case needs isolated with-skill and baseline arms. Parallel agents are justified
when the arms are independent and the host supports them; otherwise the owner runs the
arms sequentially. Match model, effort, permissions and task inputs. Keep actual timing
and failures; concurrent completion is not evidence of a speedup.

```text
Execute this task:
- Skill path: <path-to-skill>
- Task: <eval prompt>
- Input files: <eval files if any, or "none">
- Save outputs to: <workspace>/iteration-<N>/eval-<name>/with_skill/run-1/outputs/
- Outputs to save: <what the user cares about, for example "the final CSV">
```

The baseline depends on the case:

- **A new skill**: no skill at all. Same prompt, saved to `without_skill/run-1/outputs/`.
- **An improved skill**: the old version. Before you edit, copy the projected skill
  directory to `<workspace>/skill-snapshot/` and point the baseline at the copy. Save to
  `old_skill/run-1/outputs/`.

Write an `eval_metadata.json` for each test case, with empty assertions for now. Give
each eval a name that says what it tests, and use that name for its directory. Write the
file again for each new or changed eval in a later iteration.

```json
{
  "eval_id": 0,
  "eval_name": "descriptive-name-here",
  "prompt": "The task prompt of the user",
  "assertions": []
}
```

### Step 2: Draft assertions while the runs work

Draft quantitative assertions for each test case and explain them to the user. A good
assertion is objectively verifiable and has a name that says what it checks, so that it
reads clearly in the viewer. Judge a subjective skill by reading its output, not by
forced assertions. Update `eval_metadata.json` and `evals.json` with the assertions.

### Step 3: Record the timing as each run completes

The completion notice of each subagent holds `total_tokens` and `duration_ms`. It is the
only place that holds them, so save them at once to `timing.json` in the run directory:

```json
{
  "total_tokens": 84852,
  "duration_ms": 23332,
  "total_duration_seconds": 23.3
}
```

### Step 4: Grade, aggregate and open the viewer

1. **Grade each run.** Start a grader subagent, or grade inline, with
   `references/grader.md`. Save the result to `grading.json` in the run directory. Its
   `expectations` array uses the fields `text`, `passed` and `evidence`, because the
   viewer reads those names. Check an assertion with a script when a script can check it.
2. **Aggregate into a benchmark.** This writes `benchmark.json` and `benchmark.md` with
   the pass rate, time and tokens of each configuration, the mean, the standard deviation
   and the delta. List each `with_skill` configuration before its baseline.

   ```sh
   python3 -B <skill-dir>/scripts/aggregate_benchmark.py <workspace>/iteration-N --skill-name <name>
   ```

3. **Do an analyst pass.** Read the benchmark for patterns that the averages hide: an
   assertion that passes with and without the skill, a high-variance eval, a time or token
   cost. The "Analyzing Benchmark Results" section of `references/analyzer.md` lists them.
4. **Open the viewer** with the outputs and the numbers. Use this script; do not write
   custom HTML.

   ```sh
   python3 -B <skill-dir>/scripts/generate_review.py <workspace>/iteration-N \
     --skill-name <name> --benchmark <workspace>/iteration-N/benchmark.json
   ```

   It serves the page on `127.0.0.1` and opens the browser; run it in the background and
   stop it when the review is done. For iteration 2 and later, add
   `--previous-workspace <workspace>/iteration-<N-1>`. Without a display, add
   `--static <workspace>/review.html` to write one self-contained file instead. The page
   loads nothing from the network.
5. **Tell the user** that the results are open: the "Outputs" tab shows each test case
   with a feedback box, and the "Benchmark" tab shows the numbers.

Open the viewer before you judge the outputs yourself, so that the user sees them early.

### Step 5: Read the feedback

"Submit All Reviews" saves `feedback.json` in the workspace. With `--static`, the browser
downloads the file; ask the user where it is saved.

```json
{
  "reviews": [
    {"run_id": "eval-0-with_skill-run-1", "feedback": "the chart has no axis labels", "timestamp": "..."},
    {"run_id": "eval-1-with_skill-run-1", "feedback": "", "timestamp": "..."}
  ],
  "status": "complete"
}
```

An empty feedback means the user found the output fine. Improve the cases that have a
complaint.
