# yq

Read and change YAML files, and convert between YAML and JSON. Use it instead of a text edit on a config file.

## Rules

- **Check that `yq --version` names mikefarah/yq.** Other yq programs use a different syntax.
- **Run a read-only query before `-i`.** `-i` writes the file directly.
- **Use an exact path for an update.** A wide expression can change unrelated sections.
- **Review each in-place edit in `git diff`.** It shows what the expression changed.

## Commands

```bash
yq '.spec.replicas' file.yaml
yq -o json file.yaml
yq -o yaml file.json
yq -i '.version = "2.0"' file.yaml
yq eval-all 'select(fi == 0) * select(fi == 1)' a.yaml b.yaml
```

## Output

- The output format follows the input format. A JSON file prints as JSON.
- `-o yaml` prints YAML, and `-o json` prints JSON.
- `-P` pretty-prints. It does not change the format.
