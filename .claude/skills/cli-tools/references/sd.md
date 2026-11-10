# sd

Find and replace text in files. Use it instead of `sed` for a readable replacement that works on all platforms.

## Rules

- **Preview with `-p` before you write.** sd edits files in place and prints almost nothing.
- **Use `-F` for literal text.** The pattern is a regular expression by default.
- **Select the files first with `fd` or `rg -l`.** A wide file list changes many files at once.
- **Review a batch replacement in `git diff`.** It is the only record of what changed.

## Commands

```bash
sd 'old' 'new' file.ts
sd -p 'old' 'new' file.ts
sd -F 'a.b' 'a_b' file.ts
sd 'v(\d+)' 'version-$1' file.txt
```

Replace across many files in four steps. A different count is a stop:

```bash
rg -c -F 'old_api' | awk -F: '{s+=$2} END {print s}'
rg -l -F 'old_api' | xargs sd -p -F 'old_api' 'new_api'
rg -l -F 'old_api' | xargs sd -F 'old_api' 'new_api'
rg -c -F 'new_api' | awk -F: '{s+=$2} END {print s}'
```

The first count must equal the last. Then read `git diff`.

## Output

- Default mode writes the files and prints nothing.
- `-p` prints the changed text and writes nothing.
