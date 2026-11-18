import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from devflow_cli.cli import main
from devflow_cli.core import DevFlowError, apply_install, doctor, status_rows, uninstall
from devflow_cli.editions import DEFAULT_EDITION, EDITION_SPECS, HOSTS, source_for


ROOT = Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old_asset_root = os.environ.get("DEVFLOW_ASSET_ROOT")
        os.environ["DEVFLOW_ASSET_ROOT"] = str(ROOT)

    @classmethod
    def tearDownClass(cls):
        if cls.old_asset_root is None:
            os.environ.pop("DEVFLOW_ASSET_ROOT", None)
        else:
            os.environ["DEVFLOW_ASSET_ROOT"] = cls.old_asset_root

    def project(self, temporary: str) -> Path:
        path = Path(temporary) / "project"
        path.mkdir()
        return path

    def test_all_host_and_edition_combinations_install_and_update(self):
        for edition in ("portable", "classic"):
            for host in ("codebuddy", "codex", "cursor", "claude"):
                with self.subTest(edition=edition, host=host), tempfile.TemporaryDirectory() as temporary:
                    project = self.project(temporary)
                    written, unchanged = apply_install(project, host, edition)
                    self.assertGreater(written, 0)
                    self.assertEqual(0, unchanged)
                    self.assertEqual([], doctor(project))
                    written, unchanged = apply_install(project, host, edition, update_only=True)
                    self.assertEqual(0, written)
                    self.assertGreater(unchanged, 0)
                    row = status_rows(project, host)[0]
                    self.assertEqual(0, row["changed"])
                    self.assertEqual(0, row["missing"])

    def test_untracked_user_file_conflict_is_atomic(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.project(temporary)
            user_file = project / ".claude/agents/devflow-stage-executor.md"
            user_file.parent.mkdir(parents=True)
            user_file.write_text("user content\n", encoding="utf-8")
            with self.assertRaises(DevFlowError):
                apply_install(project, "claude", "portable")
            self.assertEqual("user content\n", user_file.read_text(encoding="utf-8"))
            self.assertFalse((project / ".devflow/install-state.json").exists())

    def test_force_replaces_conflicting_skill_symlink_without_touching_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.project(temporary)
            external = Path(temporary) / "external-devflow"
            external.mkdir()
            external_skill = external / "SKILL.md"
            external_skill.write_text("external content\n", encoding="utf-8")
            link = project / ".agents/skills/devflow"
            link.parent.mkdir(parents=True)
            link.symlink_to(external, target_is_directory=True)

            with self.assertRaises(DevFlowError):
                apply_install(project, "codex", "portable")
            self.assertEqual(0, main([
                "skills", "install", "codex", "--project-root", str(project), "--force",
            ]))

            self.assertTrue(link.is_dir())
            self.assertFalse(link.is_symlink())
            self.assertEqual("external content\n", external_skill.read_text(encoding="utf-8"))
            self.assertNotEqual("external content\n", (link / "SKILL.md").read_text(encoding="utf-8"))

    def test_update_rejects_modified_managed_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.project(temporary)
            apply_install(project, "cursor", "portable")
            managed = project / ".cursor/agents/devflow-stage-executor.md"
            managed.write_text("user changed\n", encoding="utf-8")
            with self.assertRaises(DevFlowError):
                apply_install(project, "cursor", "portable", update_only=True)
            self.assertEqual("user changed\n", managed.read_text(encoding="utf-8"))

    def test_force_update_overwrites_modified_managed_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.project(temporary)
            apply_install(project, "cursor", "portable")
            managed = project / ".cursor/agents/devflow-stage-executor.md"
            managed.write_text("user changed\n", encoding="utf-8")
            apply_install(project, "cursor", "portable", update_only=True, force=True)
            self.assertNotEqual("user changed\n", managed.read_text(encoding="utf-8"))

    def test_uninstall_preserves_modified_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.project(temporary)
            apply_install(project, "claude", "classic")
            managed = project / ".claude/README.md"
            managed.write_text("user changed\n", encoding="utf-8")
            removed, preserved = uninstall(project, "claude")
            self.assertGreater(removed, 0)
            self.assertIn(".claude/README.md", preserved)
            self.assertEqual("user changed\n", managed.read_text(encoding="utf-8"))

    def test_same_host_cannot_mix_editions(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.project(temporary)
            apply_install(project, "codex", "portable")
            with self.assertRaises(DevFlowError):
                apply_install(project, "codex", "classic")

    def test_force_install_switches_editions_in_both_directions(self):
        cases = (
            ("portable", "classic", ".codebuddy/commands/devflow.md", ".codebuddy/commands/start-devflow.md"),
            ("classic", "portable", ".codebuddy/commands/start-devflow.md", ".codebuddy/commands/devflow.md"),
        )
        for source, target, removed_path, installed_path in cases:
            with self.subTest(source=source, target=target), tempfile.TemporaryDirectory() as temporary:
                project = self.project(temporary)
                apply_install(project, "codebuddy", source)

                apply_install(project, "codebuddy", target, force=True)

                rows = status_rows(project, "codebuddy")
                self.assertEqual(1, len(rows))
                self.assertEqual(target, rows[0]["edition"])
                self.assertFalse((project / removed_path).exists())
                self.assertTrue((project / installed_path).is_file())

    def test_force_edition_switch_preserves_modified_old_only_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.project(temporary)
            apply_install(project, "codebuddy", "portable")
            old_only = project / ".codebuddy/commands/devflow.md"
            old_only.write_text("user changed\n", encoding="utf-8")

            apply_install(project, "codebuddy", "classic", force=True)

            self.assertEqual("user changed\n", old_only.read_text(encoding="utf-8"))
            self.assertEqual("classic", status_rows(project, "codebuddy")[0]["edition"])

    def test_edition_registry_is_complete_and_sources_exist(self):
        self.assertEqual("classic", DEFAULT_EDITION)
        self.assertEqual(("portable", "classic"), tuple(EDITION_SPECS))
        for edition, metadata in EDITION_SPECS.items():
            hosts = metadata.get("hosts", HOSTS)
            self.assertEqual(set(hosts), set(metadata["entrypoints"]))
            for host in hosts:
                self.assertTrue((ROOT / source_for(edition, host)).is_dir())

    def test_pi_is_portable_only(self):
        self.assertIn("pi", EDITION_SPECS["portable"]["hosts"])
        self.assertNotIn("pi", EDITION_SPECS["classic"]["hosts"])
        self.assertEqual("/skill:devflow", EDITION_SPECS["portable"]["entrypoints"]["pi"])

    def test_pi_installs_portable_skills_and_rejects_classic(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            installed, _unchanged = apply_install(project, "pi", "portable")
            self.assertGreater(installed, 0)
            self.assertTrue((project / ".pi/skills/devflow/SKILL.md").is_file())
            self.assertTrue((project / ".pi/skills/manifest.json").is_file())
            with self.assertRaises(DevFlowError):
                apply_install(project, "pi", "classic")

    def test_dsh_installs_portable_skills_and_rejects_classic(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            installed, _unchanged = apply_install(project, "dsh", "portable")
            self.assertGreater(installed, 0)
            self.assertTrue((project / ".dsh/skills/devflow/SKILL.md").is_file())
            self.assertTrue((project / ".dsh/skills/manifest.json").is_file())
            self.assertTrue((project / ".dsh/skills/devflow/adapters/dsh/manifest.json").is_file())
            with self.assertRaises(DevFlowError):
                apply_install(project, "dsh", "classic")

    def test_hermes_installs_project_skills_and_rejects_classic(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            installed, _unchanged = apply_install(project, "hermes", "portable")
            self.assertGreater(installed, 0)
            self.assertTrue((project / ".hermes/skills/devflow/SKILL.md").is_file())
            self.assertTrue((project / ".hermes/skills/manifest.json").is_file())
            self.assertTrue((project / ".hermes/skills/devflow/adapters/hermes/manifest.json").is_file())
            with self.assertRaises(DevFlowError):
                apply_install(project, "hermes", "classic")

    def test_editions_and_plan_make_the_split_visible_without_writing(self):
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(0, main(["editions"]))
        text = output.getvalue()
        self.assertIn("portable:", text)
        self.assertIn("sources: skills/", text)
        self.assertIn("classic (default)", text)
        self.assertIn(".codebuddy/", text)

        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(0, main(["plan", "claude"]))
        text = output.getvalue()
        self.assertIn("edition=classic host=claude source=.claude/", text)
        self.assertIn(".claude/commands/start-devflow.md", text)

    def test_install_output_names_project_and_next_entrypoint(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.project(temporary)
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(0, main([
                    "install", "codebuddy", "--project-root", str(project),
                ]))
            text = output.getvalue()
            self.assertIn(f"project={project.resolve()}", text)
            self.assertIn("edition=classic", text)
            self.assertIn("run /start-devflow <你的需求>", text)

    def test_skills_command_installs_and_manages_portable_edition(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.project(temporary)
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(0, main([
                    "skills", "install", "codex", "--project-root", str(project),
                ]))
            self.assertIn("OK: skills install host=codex", output.getvalue())
            self.assertIn("run $devflow <你的需求>", output.getvalue())
            self.assertTrue((project / ".agents/skills/devflow/SKILL.md").is_file())
            self.assertFalse((project / ".codex").exists())

            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(0, main([
                    "skills", "status", "codex", "--project-root", str(project),
                ]))
            self.assertIn("skills/codex:", output.getvalue())

            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(0, main([
                    "skills", "uninstall", "codex", "--project-root", str(project),
                ]))
            self.assertIn("OK: skills uninstall host=codex", output.getvalue())

    def test_portable_install_keeps_skill_manifest_with_copied_skills(self):
        skill_roots = {
            "codebuddy": ".codebuddy/skills",
            "codex": ".agents/skills",
            "cursor": ".cursor/skills",
            "claude": ".claude/skills",
        }
        for host, relative in skill_roots.items():
            with self.subTest(host=host), tempfile.TemporaryDirectory() as temporary:
                project = self.project(temporary)
                apply_install(project, host, "portable")
                self.assertTrue((project / relative / "manifest.json").is_file())

    def test_codebuddy_copy_contains_runnable_generic_adapter_installer(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.project(temporary)
            apply_install(project, "codebuddy", "portable")
            downstream = Path(temporary) / "downstream"
            downstream.mkdir()
            installer = project / ".codebuddy/skills/devflow/scripts/install_adapter.py"
            result = subprocess.run(
                [
                    sys.executable,
                    str(installer),
                    "--adapter",
                    "claude",
                    "--project-root",
                    str(downstream),
                    "--copy-skills",
                    "--refresh-managed",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue((downstream / ".claude/skills/manifest.json").is_file())
            self.assertTrue((downstream / ".claude/skills/devflow/SKILL.md").is_file())

    def test_codebuddy_portable_agents_use_autorun_bypass_permissions(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.project(temporary)
            apply_install(project, "codebuddy", "portable")
            for name in ("devflow-stage-executor.md", "devflow-research-helper.md"):
                text = (project / ".codebuddy/agents" / name).read_text(encoding="utf-8")
                self.assertIn("permissionMode: bypassPermissions", text)
                self.assertIn("enabledAutoRun: true", text)

    def test_classic_install_makes_observability_hook_executable(self):
        hooks = (
            ("codebuddy", ".codebuddy/skills/agent-observability/scripts/run_hook.sh"),
            ("cursor", ".cursor/skills/agent-observability/scripts/run_hook.sh"),
            ("claude", ".claude/skills/agent-observability/scripts/run_hook.sh"),
        )
        for host, relative in hooks:
            with self.subTest(host=host), tempfile.TemporaryDirectory() as temporary:
                project = self.project(temporary)
                apply_install(project, host, "classic")
                hook = project / relative
                self.assertTrue(hook.is_file(), relative)
                self.assertTrue(hook.stat().st_mode & stat.S_IXUSR, relative)

    def test_update_restores_missing_executable_bit_on_hook(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.project(temporary)
            apply_install(project, "codebuddy", "classic")
            hook = project / ".codebuddy/skills/agent-observability/scripts/run_hook.sh"
            hook.chmod(0o644)
            written, unchanged = apply_install(project, "codebuddy", "classic", update_only=True)
            self.assertEqual(0, written)
            self.assertGreater(unchanged, 0)
            self.assertTrue(hook.stat().st_mode & stat.S_IXUSR)

    def _cli(self, project, *argv):
        output = StringIO()
        with redirect_stdout(output):
            code = main(list(argv) + ["--project-root", str(project)])
        return code, output.getvalue()

    def test_status_files_clean_install_lists_nothing(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.project(temporary)
            apply_install(project, "claude", "classic")
            code, text = self._cli(project, "status", "claude", "--files")
            self.assertEqual(0, code)
            row = status_rows(project, "claude")[0]
            self.assertEqual(
                f"classic/claude: files={row['files']} changed=0 missing=0\n",
                text,
            )
            self.assertNotIn("  changed  ", text)
            self.assertNotIn("  missing  ", text)

    def test_status_files_lists_edited_deleted_directory_and_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.project(temporary)
            apply_install(project, "claude", "classic")
            edited = project / ".claude/README.md"
            edited.write_text(edited.read_text(encoding="utf-8") + "status-files-marker-line\n", encoding="utf-8")
            missing = project / ".claude/commands/abort-devflow.md"
            missing.unlink()
            as_dir = project / ".claude/commands/git-commit.md"
            as_dir.unlink()
            as_dir.mkdir()
            as_link = project / ".claude/commands/git-prepare.md"
            as_link.unlink()
            as_link.symlink_to("git-commit.md")

            row = status_rows(project, "claude")[0]
            self.assertEqual(
                {"key", "host", "edition", "files", "changed", "missing"},
                set(row),
            )
            self.assertEqual(3, row["changed"])
            self.assertEqual(1, row["missing"])

            code, text = self._cli(project, "status", "claude", "--files")
            self.assertEqual(0, code)
            self.assertEqual(
                "classic/claude: files={files} changed=3 missing=1\n"
                "  changed  .claude/README.md\n"
                "  changed  .claude/commands/git-commit.md\n"
                "  changed  .claude/commands/git-prepare.md\n"
                "  missing  .claude/commands/abort-devflow.md\n".format(files=row["files"]),
                text,
            )

    def test_status_json_files_keys(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.project(temporary)
            apply_install(project, "claude", "classic")
            (project / ".claude/README.md").write_text("user changed\n", encoding="utf-8")
            (project / ".claude/commands/abort-devflow.md").unlink()

            code, text = self._cli(project, "status", "claude", "--json")
            self.assertEqual(0, code)
            payload = json.loads(text)
            self.assertEqual(
                ["key", "host", "edition", "files", "changed", "missing"],
                list(payload[0]),
            )
            self.assertNotIn("changed_files", payload[0])
            self.assertNotIn("missing_files", payload[0])

            code, text = self._cli(project, "status", "claude", "--json", "--files")
            self.assertEqual(0, code)
            payload = json.loads(text)
            self.assertEqual([".claude/README.md"], payload[0]["changed_files"])
            self.assertEqual([".claude/commands/abort-devflow.md"], payload[0]["missing_files"])
            self.assertEqual(1, payload[0]["changed"])
            self.assertEqual(1, payload[0]["missing"])

            code, text = self._cli(project, "status", "claude", "--json", "--patch")
            self.assertEqual(0, code)
            payload = json.loads(text)
            self.assertEqual([".claude/README.md"], payload[0]["changed_files"])
            self.assertEqual([".claude/commands/abort-devflow.md"], payload[0]["missing_files"])

    def test_status_patch_contains_edited_line(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.project(temporary)
            apply_install(project, "claude", "classic")
            edited = project / ".claude/README.md"
            edited.write_text(edited.read_text(encoding="utf-8") + "status-files-marker-line\n", encoding="utf-8")
            code, text = self._cli(project, "status", "claude", "--patch")
            self.assertEqual(0, code)
            self.assertIn("  changed  .claude/README.md", text)
            self.assertIn("--- a/.claude/README.md (package ", text)
            self.assertIn("+++ b/.claude/README.md (project)", text)
            self.assertIn("+status-files-marker-line", text)

    def test_status_patch_labels_package_content_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.project(temporary)
            apply_install(project, "claude", "classic")
            state_path = project / ".devflow/install-state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            for record in state["installations"]["classic:claude"]["files"]:
                if record["path"] == ".claude/README.md":
                    record["sha256"] = "0" * 64
                    break
            else:
                self.fail("expected .claude/README.md in install state")
            state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            code, text = self._cli(project, "status", "claude", "--patch")
            self.assertEqual(0, code)
            self.assertIn(".claude/README.md: package content changed since install", text)
            self.assertNotIn("+", text.split("package content changed since install", 1)[-1])

    def test_status_patch_binary_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.project(temporary)
            apply_install(project, "claude", "classic")
            (project / ".claude/README.md").write_bytes(b"\x00\xff binary-status-files")
            code, text = self._cli(project, "status", "claude", "--patch")
            self.assertEqual(0, code)
            self.assertIn(".claude/README.md: binary file differs", text)
            self.assertNotIn("binary-status-files", text)

    def test_skills_status_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.project(temporary)
            apply_install(project, "codex", "portable")
            managed = project / ".agents/skills/devflow/SKILL.md"
            managed.write_text(managed.read_text(encoding="utf-8") + "skills-status-files-marker\n", encoding="utf-8")
            gone = project / ".agents/skills/manifest.json"
            gone.unlink()
            code, text = self._cli(project, "skills", "status", "codex", "--files")
            self.assertEqual(0, code)
            self.assertIn("skills/codex: files=", text)
            self.assertIn("  changed  .agents/skills/devflow/SKILL.md", text)
            self.assertIn("  missing  .agents/skills/manifest.json", text)
            self.assertNotIn("classic/", text)

    def test_doctor_lists_paths_and_keeps_exit_code(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.project(temporary)
            apply_install(project, "claude", "classic")
            code, text = self._cli(project, "doctor")
            self.assertEqual(0, code)
            self.assertEqual("OK: assets and installations are healthy\n", text)

            (project / ".claude/README.md").write_text("user changed\n", encoding="utf-8")
            (project / ".claude/commands/abort-devflow.md").unlink()
            code, text = self._cli(project, "doctor")
            self.assertEqual(1, code)
            self.assertTrue(text.startswith("ERROR:\n- classic:claude: changed=1 missing=1\n"))
            self.assertIn("  changed  .claude/README.md", text)
            self.assertIn("  missing  .claude/commands/abort-devflow.md", text)
            self.assertIn("loopforge status claude --files", text)

            state_path = project / ".devflow/install-state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["installations"]["classic:claude"]["files"].extend(
                {"path": ".claude/extra-{0:02d}.md".format(index), "sha256": "ab"}
                for index in range(12)
            )
            state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            code, text = self._cli(project, "doctor")
            self.assertEqual(1, code)
            listed = [line for line in text.splitlines() if line.startswith("  changed  ") or line.startswith("  missing  ")]
            self.assertEqual(10, len(listed))
            self.assertIn("loopforge status claude --files", text)

    def test_status_and_doctor_without_new_flags_keep_current_strings(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.project(temporary)
            apply_install(project, "claude", "classic")
            row = status_rows(project, "claude")[0]
            code, text = self._cli(project, "status", "claude")
            self.assertEqual(0, code)
            self.assertEqual(
                f"classic/claude: files={row['files']} changed=0 missing=0\n",
                text,
            )
            code, text = self._cli(project, "status", "claude", "--json")
            self.assertEqual(0, code)
            self.assertEqual(
                json.dumps([{
                    "key": "classic:claude",
                    "host": "claude",
                    "edition": "classic",
                    "files": row["files"],
                    "changed": 0,
                    "missing": 0,
                }], ensure_ascii=False, indent=2) + "\n",
                text,
            )

            edited = project / ".claude/README.md"
            edited.write_text("user changed\n", encoding="utf-8")
            (project / ".claude/commands/abort-devflow.md").unlink()
            code, text = self._cli(project, "status", "claude")
            self.assertEqual(0, code)
            self.assertEqual(
                f"classic/claude: files={row['files']} changed=1 missing=1\n",
                text,
            )

            apply_install(project, "codex", "portable")
            code, text = self._cli(project, "skills", "status", "codex")
            portable = [item for item in status_rows(project, "codex") if item["edition"] == "portable"][0]
            self.assertEqual(0, code)
            self.assertEqual(
                f"skills/codex: files={portable['files']} changed=0 missing=0\n",
                text,
            )

            code, text = self._cli(project, "doctor")
            self.assertEqual(1, code)
            self.assertIn("ERROR:\n- classic:claude: changed=1 missing=1\n", text)

    def test_status_files_does_not_weaken_user_file_protection(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.project(temporary)
            apply_install(project, "claude", "classic")
            managed = project / ".claude/README.md"
            managed.write_text("user changed\n", encoding="utf-8")
            state_path = project / ".devflow/install-state.json"
            before_state = state_path.read_bytes()
            before_file = managed.read_bytes()
            self.assertEqual(0, self._cli(project, "status", "claude", "--files")[0])
            self.assertEqual(0, self._cli(project, "status", "claude", "--patch")[0])
            self.assertEqual(before_file, managed.read_bytes())
            self.assertEqual(before_state, state_path.read_bytes())
            with self.assertRaises(DevFlowError):
                apply_install(project, "claude", "classic", update_only=True)
            self.assertEqual("user changed\n", managed.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
