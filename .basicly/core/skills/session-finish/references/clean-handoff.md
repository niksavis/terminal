## 3. Clean handoff

1. Run `git status`. Remove partial edits, debug output and stray files. Name in the summary anything that you leave on purpose.
2. Check the state of records whose implementation changed. Close completed claimed work, or record its true state. Do not repeat gates or reopen closed work for a handover.
3. List task-owned background processes; stop temporary ones and identify user-requested services left running.
4. Before you restore a file from a backup, compare the backup with `git show HEAD:<path>`.
5. If new recovery facts remain, write one concise handover note on the existing root record. Mark it `[new facts]` so later notes do not replace it in the current view. Keep closed work explicitly closed; preserve facts needed after interruption and link full evidence rather than pasting it:

   ```sh
   basicly tracker write -- comments add <root-id> "[session handover $(date +%F)] [new facts] STATE: ... NEXT: ..."
   ```

6. End with changed outcomes, actual checks and open work. Include usage figures only when available and useful. Reuse an existing equivalent handoff; no extra report commit is needed solely because a phase changed.
