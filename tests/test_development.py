from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from codamnd.resource_paths import default_config_dir
from codamnd.version import __version__
from scripts import audit_release_readiness, check_release_tag, generate_sbom


class DevelopmentTest(unittest.TestCase):
    def run_cli(self, directory: Path, *args: str) -> subprocess.CompletedProcess[str]:
        environment = {
            **os.environ,
            "PYTHONPATH": str(ROOT / "src"),
            "LOCALAPPDATA": str(directory / "local"),
            "XDG_CONFIG_HOME": str(directory / "preferences"),
            "PYTHONUTF8": "1",
        }
        return subprocess.run(
            [sys.executable, "-m", "codamnd", *args],
            cwd=directory,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

    def test_cli_converts_and_reads_synthetic_data_outside_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = ROOT / "samples" / "employeurd-balanced.txt"
            target = directory / "sortie.mnd"
            conversion = self.run_cli(directory, "convert", str(source), str(target))
            self.assertEqual(conversion.returncode, 0, conversion.stderr)
            self.assertIn("debit=6643.00", conversion.stdout)
            self.assertTrue(target.with_suffix(".rapport.md").is_file())
            self.assertTrue(target.with_suffix(".validation.json").is_file())
            self.assertIn(b"\r\n", target.read_bytes())
            parsed = self.run_cli(directory, "parse-mnd", str(target))
            self.assertEqual(parsed.returncode, 0, parsed.stderr)
            self.assertIn("credit=6643.00", parsed.stdout)
            overwrite = self.run_cli(directory, "convert", str(source), str(target))
            self.assertEqual(overwrite.returncode, 1, overwrite.stderr)

    def test_cli_blocks_unbalanced_source_without_creating_mnd(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            target = directory / "interdit.mnd"
            result = self.run_cli(
                directory,
                "convert",
                str(ROOT / "samples" / "employeurd-unbalanced.txt"),
                str(target),
            )
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertFalse(target.exists())
            self.assertIn("source_unbalanced", result.stderr)

    def test_cli_explicit_config_and_missing_self_tests(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            result = self.run_cli(
                directory,
                "--config-dir",
                str(directory / "absent"),
                "inspect-source",
                str(ROOT / "samples" / "employeurd-balanced.txt"),
            )
            self.assertEqual(result.returncode, 2, result.stderr)
            result = self.run_cli(directory, "self-test")
            self.assertEqual(result.returncode, 2, result.stderr)

    def test_installed_configuration_fallback_and_cwd_override(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            installed = directory / "prefix" / "share" / "codamnd" / "config"
            installed.mkdir(parents=True)
            # Simuler une wheel, sans configuration dans son arbre source.
            with (
                patch("codamnd.resource_paths.Path.cwd", return_value=directory),
                patch(
                    "codamnd.resource_paths.__file__",
                    str(directory / "lib" / "codamnd" / "resource_paths.py"),
                ),
                patch("codamnd.resource_paths.sys.prefix", str(directory / "prefix")),
            ):
                self.assertEqual(default_config_dir(), installed)
                override = directory / "config"
                override.mkdir()
                self.assertEqual(default_config_dir(), override)

    def test_sbom_lock_includes_pdf_dependencies_without_dev_tools(self) -> None:
        names = set(generate_sbom._locked_package_names(ROOT / "requirements-release.txt"))
        self.assertTrue({"pdfplumber", "pdfminer-six", "pillow", "pypdfium2", "cryptography"} <= names)
        self.assertTrue({"ruff", "mypy", "cx-freeze"}.isdisjoint(names))

    def test_secret_audit_checks_web_files_and_env_example(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            synthetic_token = "ghp_" + "x" * 24
            for name in ("site.js", "index.html", ".env.example"):
                (directory / name).write_text(synthetic_token, encoding="utf-8")
            ignored = directory / ".venv"
            ignored.mkdir()
            (ignored / "ignored.py").write_text(synthetic_token, encoding="utf-8")
            self.assertEqual(len(audit_release_readiness._secret_issues(directory)), 3)

    def test_release_tag_accepts_head_and_rejects_other_commit_or_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)

            def git(*args: str) -> None:
                subprocess.run(
                    ["git", *args], cwd=directory, check=True, capture_output=True
                )

            git("init", "-q")
            git("config", "user.name", "Test synthétique")
            git("config", "user.email", "test@example.invalid")
            (directory / "pyproject.toml").write_text(
                '[project]\nversion = "1.2.3"\n', encoding="utf-8"
            )
            git("add", "pyproject.toml")
            git("-c", "commit.gpgsign=false", "commit", "-qm", "Fixture")
            with self.assertRaises(ValueError):
                check_release_tag.check_tag(directory, "v1.2.3", "1.2.3")
            git("-c", "tag.gpgsign=false", "tag", "-a", "v1.2.3", "-m", "Fixture")
            check_release_tag.check_tag(directory, "v1.2.3", "1.2.3")
            with self.assertRaises(ValueError):
                check_release_tag.check_tag(directory, "v9.9.9", "9.9.9")
            git(
                "-c",
                "commit.gpgsign=false",
                "commit",
                "--allow-empty",
                "-qm",
                "Autre commit",
            )
            with self.assertRaisesRegex(ValueError, "HEAD"):
                check_release_tag.check_tag(directory, "v1.2.3", "1.2.3")


if __name__ == "__main__":
    unittest.main()
