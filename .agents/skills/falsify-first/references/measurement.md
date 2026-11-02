# Measurement

## A difference needs its baseline

A finding of the form "X is present where it should not be" is two claims. The second claim is that X is not already present by another route. Attack the second claim first. It is the cheaper kill, and it decides the severity.

Example: an e-mail address in a tracker file is not a new exposure when `git log --format='%ae' | sort -u` already shows it as a commit author.

## Exclude the instrument

When a probe counts the file that defines its vocabulary, the probe and the thing it checks share a step. Their agreement is then not a second derivation.

1. **Name the population and what defines it.** Exclude the definition: the gate's own module, the schema, the fixture, the test that lists the set.
2. **Run the probe again without the definition.** If the number moves, the agreement was the instrument that read itself.
3. **Split the hits by population before you report one total.** One number over two populations reads as evidence and is not.

## Pin the instrument and the tree

Two substitutions keep the population correct and make the number wrong:

- **The instrument was swapped.** Another lane can overwrite a script at a shared path between the write and the run. Keep an instrument where only you can write it.
- **The tree was wrong.** `uv run --project <worktree> pytest` from another directory selects the environment, not the tree. It collects the tests of the other tree. Run from inside the tree. Prove the tree with a control that only it can satisfy, such as a symbol, a file or a string that exists nowhere else.

Take the measurement again when it came from a shared path or an unpinned tree.

## Limits

- This method changes what you believe. It is not a gate and refuses nothing.
- It makes a wrong belief cheap to drop. It does not prove that a surviving claim is correct.
- Not `test-discipline`, which structures a test after the behaviour is settled.
- Not `root-cause`, which runs after a failure to find why it happened.
- Not the `reviewer` role, which attacks a diff that already exists.
