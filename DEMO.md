# Demo: `loopforge status --files` / `--patch`

Throwaway project: `/tmp/status-files-demo`. The CLI was the in-tree installer (`python3 -m devflow_cli.cli` with `DEVFLOW_ASSET_ROOT` pointing at `local/`), invoked as `loopforge`.

Exact commands, stdout/stderr and exit codes are in `commands.log`. `out.mp4` is a labeled replay of those lines (`Replay of real captured command output`). `preview.gif` is derived from the MP4.

Sequence:

1. `loopforge install claude --project-root .`
2. `loopforge status claude --project-root .` (clean counts)
3. Append `status-files-demo-edit` to `.claude/README.md` and delete `.claude/commands/abort-devflow.md`
4. `loopforge status claude --project-root .` (counts only: changed=1 missing=1)
5. `loopforge status claude --files --project-root .`
6. `loopforge status claude --patch --project-root .` (unified diff includes `+status-files-demo-edit`)
7. `loopforge doctor --project-root .` (lists the paths, exit=1)
8. `loopforge status claude --files --json --project-root . | python3 -m json.tool`

Media: `logs/ffprobe.txt`. GIF is 1280x720, 278443 bytes.
