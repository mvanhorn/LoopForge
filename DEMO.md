# Demo: `loopforge install` / `update --dry-run`

Captured from the real CLI (`node local/bin/loopforge.mjs`) in an empty throwaway project with `DEVFLOW_ASSET_ROOT` set by that wrapper to `local/`.

`commands.log` records each command, the exact stdout/stderr, and `exit=`.

Sequence:

1. `loopforge install claude --dry-run` on an empty project (`add=81`, exit 0). No `.devflow/` was created.
2. `loopforge install claude` (`written=81`).
3. Overwrite `.claude/README.md` with `user changed README`.
4. Snapshot the tree with git, then `loopforge update claude --dry-run` (`conflict=1` on `.claude/README.md`, exit 1).
5. `loopforge update claude --dry-run --force` (`overwrite .claude/README.md`, exit 0).
6. `git status --porcelain` and `find . -newer ../stamp` print no paths.
7. `loopforge update claude --dry-run --json | python3 -m json.tool` (exit 1; JSON reports the same conflict).

`out.mp4` is a 1920x1080, 30 fps, H.264 yuv420p replay of those captured lines, labeled "Replay of real captured command output". `preview.gif` is 1280x720, 10 fps, 64-color palette, 1069378 bytes.

See `logs/ffprobe.txt` for probe output.
