Title: feat(local): preview install and update changes with --dry-run

## What changed

`loopforge plan` only lists files in the bundle. It does not compare them to the project, so there is no way to see what `install` / `update` would write, leave unchanged, remove, or overwrite. When `apply_install` finds conflicts it stops with "检测到用户文件冲突，未修改任何内容" and at most the first eight paths.

`install`, `update`, `skills install`, and `skills update` now accept `--dry-run`. The command prints a one-line summary (`DRY RUN: <command> edition=... host=... add=N update=N unchanged=N remove=N conflict=N`) and then each non-unchanged path with its action. With `--force`, conflicts are labeled `overwrite` and an edition switch is shown. `--json` (only with `--dry-run`) prints the same data as JSON. The project is not modified: no files, no `.devflow/install-state.json`, no directories, no mode changes. Exit status is 0 when the real command would succeed and 1 when it would stop on conflicts, including the edition-switch refusal without `--force` and "尚未安装" for update.

Per-file actions come from `plan_install`. `apply_install` uses that function, so the dry run cannot disagree with the real run. Existing install/update messages and return values are unchanged.

The English and Chinese usage docs now recommend `--dry-run` before `--force`.

## Scope

- [ ] Platform core / API / runner
- [ ] Public adapter / deployment
- [ ] Classic
- [ ] Portable
- [ ] Shared behavior contract
- [x] Installer / CLI
- [ ] Documentation only

## Compatibility

Hosts affected: all Local hosts through the installer (codebuddy, codex, cursor, claude, pi, dsh, hermes). No install-state format change and no migration. Python 3.8+.

## Validation

Ran on this branch. Baseline on untouched `upstream/main` is noted where it was recorded.

```text
# baseline, untouched upstream/main, Python 3.12.3
cd local && PYTHONPATH=src python3 -m unittest discover -s tests -v
  passed: 24 tests

# this branch, Python 3.12.3
cd local && PYTHONPATH=src python3 -m unittest discover -s tests -v
  passed: 33 tests (9 new dry-run cases)

# this branch, Python 3.8.20 (uv)
cd local && PYTHONPATH=src python3.8 -m unittest discover -s tests -v
  passed: 33 tests

cd local && python3 scripts/build-classic-hosts.py --check
  passed

cd local && bash scripts/validate.sh
  passed

cd local && bash scripts/smoke-install.sh
  first run blocked: system Python lacked ensurepip/venv
  after installing python3.12-venv: passed (installer unit tests 33, wheel install, claude install/status/uninstall, skills install)

cd local && bash scripts/smoke-npm.sh
  passed

cd local && bash scripts/smoke-curl-install.sh
  passed

cd local && bash scripts/e2e.sh
  passed: 33 tests; skipped: 1 (playwright is not installed)

cd local && bash scripts/test-observability.sh
  passed: 131 tests in each of .codebuddy, .cursor, .claude

cd local && bash scripts/scan-secrets.sh
  passed: no leaks found

python3 scripts/check-public.py
  passed

bash scripts/scan-secrets.sh
  passed: no leaks found

go test -p=2 ./... -count=1 -timeout=180s
  not run: only local/ installer CLI, tests, and docs/local usage pages changed

go vet ./...
  not run: same reason
```

## Safety

- [ ] I did not include credentials, internal endpoints, production data, or organization-specific infrastructure.
- [ ] I preserved user files and unrelated changes.
- [ ] I updated generated Classic host bundles when applicable.
- [ ] I documented third-party content and licensing changes when applicable.

## Demo

![demo](https://raw.githubusercontent.com/mvanhorn/pr-demo-assets/main/osc-bulk-1117/install-dry-run/preview.gif)

Full recording (MP4): https://raw.githubusercontent.com/mvanhorn/pr-demo-assets/main/osc-bulk-1117/install-dry-run/out.mp4
