## Set up the condition that the code reads

- When the code loads its own configuration or environment, put the values where the code
  reads them: the file, the directory, the environment variable. A configuration object
  that the test gives to a helper never reaches a function that calls its own loader.
- Prove that the condition is live. Assert that your input changes the value that the
  code branches on. A threshold at its default or a window too small to trigger stages a
  case that the code never sees.
- When you write a test after its fix, delete the fix and watch the test fail for the
  stated reason.

## Mutate the fix in both directions

1. Delete the fix. A test must fail. This proves that the tests see the fix.
2. Make the check fire on every input: always warn, always refuse, always the same verdict.
   A control must fail. If none fails, the suite proves only that the check reacts, not
   that it discriminates. This direction finds the missing control.
3. Record which direction found what, so that the next reader can tell a verified check
   from an exercised one.

**Restore from a copy, never with `git checkout -- <file>`.** The working tree usually
holds the change under test, and `git checkout` restores from the index and discards it.
Copy the file aside first and copy it back.

## An absence needs a positive control

- A search, scan or query that finds nothing proves nothing alone. Run the same method on a
  case that you know is present. When that control also finds nothing, the method is wrong.
- An assertion that something is absent also passes when the locator is wrong. Pin the
  locator with a case that must match before you trust the case that must not.

## A seam is not duplication

- A module-level alias or thin wrapper around a dependency (a CLI, a clock, an HTTP client)
  is usually a test seam. Tests replace it.
- Before you move repeated access behind one shared helper, look at what the tests patch.
  A new module bypasses each patch of the old alias, and many tests fail for a reason that
  is not the refactor.
- If the change is still correct, move the patch points in the same commit. Keep one seam
  per module, not one for the whole codebase.

## Platform-hermetic tests

A local gate runs on one OS. Make each platform difference an input to the test:

- Test a path rule with both `PureWindowsPath` and `PurePosixPath`. `Path` takes the form of the host.
- Compare paths as `Path` objects, or render both sides with the same `as_posix()`.
- Do not use `select` or `selectors` on a pipe, because on Windows they accept only sockets. Read in a thread and bound the read with `join(timeout=...)`.
- Use `skipif` only when the behaviour cannot exist on the other platform.
