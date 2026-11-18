Title: feat(local): list changed and missing installed files in status

## What changed

`loopforge status`, `loopforge skills status` and `loopforge doctor` only printed counts (`changed=N missing=M`). Before `update --force` or `uninstall`, there was no way to see which installed files those counts referred to.

`--files` lists each changed or missing path under the existing summary line. `--patch` implies `--files` and prints a unified diff of each changed text file against the content the current package would install. If the recorded hash does not match the current package, that file is labelled instead of presenting the whole diff as a local edit. Binary or undecodable files print `binary file differs`. A symlink or directory where a regular file was installed is treated as changed, matching uninstall. `--json` grows `changed_files` and `missing_files` only when `--files` or `--patch` is passed. Summary output without those flags is unchanged.

`loopforge doctor` still fails when an installation has changed or missing files. It now lists up to ten paths per installation and points to `loopforge status <host> --files`.

## Scope

- [ ] Platform core / API / runner
- [ ] Public adapter / deployment
- [ ] Classic
- [ ] Portable
- [ ] Shared behavior contract
- [x] Installer / CLI
- [ ] Documentation only

## Compatibility

Hosts affected: all Local hosts through the installer (Classic and Portable). No change to `.devflow/install-state.json` format and no migration. Python 3.8+.

## Validation

Baseline on untouched `upstream/main` (`e89cda9804643d3631e77652d1bca47a079adb69`):

```text
cd local && PYTHONPATH=src python3 -m unittest discover -s tests -v
```

passed: 24 tests, 0 failures (Python 3.12.3)

After the change:

```text
cd local && PYTHONPATH=src python3 -m unittest discover -s tests -v
```

passed: 34 tests, 0 failures (Python 3.12.3)

```text
cd local && PYTHONPATH=src uv run --python 3.8 python -m unittest discover -s tests -v
```

passed: 34 tests, 0 failures (CPython 3.8.20)

```text
cd local && python3 scripts/build-classic-hosts.py --check
```

passed

```text
cd local && bash scripts/validate.sh
```

passed

```text
cd local && bash scripts/smoke-install.sh
```

passed (python3.12-venv was installed in this environment first; the first attempt failed with missing ensurepip)

```text
cd local && bash scripts/smoke-npm.sh
```

passed

```text
cd local && bash scripts/smoke-curl-install.sh
```

passed

```text
cd local && bash scripts/e2e.sh
```

passed: 34 tests, 1 skipped (`playwright` not installed for `test_e2e_dashboard_browser`), 0 failures

```text
cd local && bash scripts/test-observability.sh
```

passed

```text
cd local && bash scripts/scan-secrets.sh
```

passed: no leaks found

```text
python3 scripts/check-public.py
```

passed

```text
bash scripts/scan-secrets.sh
```

passed: no leaks found

```text
go test -p=2 ./... -count=1 -timeout=180s
go vet ./...
bash scripts/build-chatbot.sh
```

not run: only `local/` installer CLI, tests and `docs/local` usage pages changed

## Safety

- [ ] I did not include credentials, internal endpoints, production data, or organization-specific infrastructure.
- [ ] I preserved user files and unrelated changes.
- [ ] I updated generated Classic host bundles when applicable.
- [ ] I documented third-party content and licensing changes when applicable.

## Demo

![demo](https://raw.githubusercontent.com/mvanhorn/pr-demo-assets/main/osc-bulk-1117/status-files/preview.gif)

Full recording (MP4): https://raw.githubusercontent.com/mvanhorn/pr-demo-assets/main/osc-bulk-1117/status-files/out.mp4
