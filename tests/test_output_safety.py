from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from codamnd import cli
from codamnd.config import load_app_config
from codamnd.converter import _write_text_atomic, convert_file, validate_file
from codamnd.errors import FileOperationError, PartialOutputError, ValidationFailed
from codamnd.user_messages import technical_error_message


class OutputSafetyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = ROOT / "samples" / "employeurd-balanced.txt"
        self.config = load_app_config(ROOT / "config")
        self.output = self.root / "sortie.mnd"
        self.report = self.output.with_suffix(".rapport.md")
        self.json = self.output.with_suffix(".validation.json")

    def test_existing_report_or_json_blocks_conversion_before_any_write(self) -> None:
        for sample in ("employeurd-balanced.txt", "employeurd-unbalanced.txt"):
            for existing in (self.report, self.json):
                with self.subTest(sample=sample, existing=existing.name):
                    existing.write_bytes(b"a conserver")
                    with self.assertRaises(ValidationFailed) as raised:
                        convert_file(ROOT / "samples" / sample, self.output, self.config)
                    self.assertEqual(raised.exception.errors[0].code, "output_exists")
                    self.assertEqual(existing.read_bytes(), b"a conserver")
                    self.assertEqual(list(self.root.iterdir()), [existing])
                    existing.unlink()

    def test_existing_report_survives_failed_reconciliation(self) -> None:
        reconciliation = replace(
            validate_file(self.source, self.config).reconciliations[0],
            status="failed", required=True,
        )
        self.report.write_bytes(b"ancien rapport")
        with self.assertRaises(ValidationFailed):
            convert_file(self.source, self.output, self.config, reconciliations=[reconciliation])
        self.assertEqual(self.report.read_bytes(), b"ancien rapport")
        self.assertFalse(self.output.exists())
        self.assertFalse(self.json.exists())

    def test_disabled_optional_outputs_leave_existing_files_untouched(self) -> None:
        self.report.write_bytes(b"rapport existant")
        self.json.write_bytes(b"json existant")
        convert_file(self.source, self.output, self.config, write_report=False, write_validation_json=False)
        self.assertTrue(self.output.exists())
        self.assertEqual(self.report.read_bytes(), b"rapport existant")
        self.assertEqual(self.json.read_bytes(), b"json existant")

    def test_explicit_overwrite_replaces_all_selected_outputs(self) -> None:
        for path in (self.output, self.report, self.json):
            path.write_bytes(b"ancien contenu")
        result = convert_file(self.source, self.output, self.config, overwrite=True)
        self.assertEqual(result.status, "success")
        self.assertIn(b"\r\n", self.output.read_bytes())
        self.assertTrue(self.report.read_text(encoding="utf-8").startswith("# Rapport"))
        self.assertIn('"status": "success"', self.json.read_text(encoding="utf-8"))

    def test_validate_checks_all_requested_reports_before_writing(self) -> None:
        self.json.write_bytes(b"ancien json")
        for sample in ("employeurd-balanced.txt", "employeurd-unbalanced.txt"):
            with self.subTest(sample=sample), self.assertRaises(ValidationFailed):
                validate_file(
                    ROOT / "samples" / sample, self.config,
                    report_path=self.report, validation_json_path=self.json,
                )
            self.assertFalse(self.report.exists())
            self.assertEqual(self.json.read_bytes(), b"ancien json")

    def test_directory_destination_blocks_before_mnd_even_with_overwrite(self) -> None:
        self.json.mkdir()
        with self.assertRaises(FileOperationError):
            convert_file(self.source, self.output, self.config, overwrite=True)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.report.exists())
        self.assertTrue(self.json.is_dir())

    def test_report_failures_identify_exactly_the_files_written(self) -> None:
        for failed, expected in ((self.report, (self.output,)), (self.json, (self.output, self.report))):
            with self.subTest(failed=failed.name):
                def fail_one(path, text, *, encoding, overwrite):
                    if path == failed:
                        raise FileOperationError("échec simulé")
                    return _write_text_atomic(path, text, encoding=encoding, overwrite=overwrite)

                with patch("codamnd.converter._write_text_atomic", side_effect=fail_one):
                    with self.assertRaises(PartialOutputError) as raised:
                        convert_file(self.source, self.output, self.config)
                self.assertEqual(raised.exception.written_paths, expected)
                self.assertEqual(raised.exception.failed_path, failed)
                self.assertEqual(set(self.root.iterdir()), set(expected))
                self.assertNotIn(str(self.root), technical_error_message(raised.exception))
                self.assertTrue(self.output.read_bytes().endswith(b"\r\n"))
                for path in expected:
                    path.unlink()

    def test_first_write_failure_is_not_reported_as_partial(self) -> None:
        with patch("codamnd.converter._write_text_atomic", side_effect=FileOperationError("échec simulé")):
            with self.assertRaises(FileOperationError) as raised:
                convert_file(self.source, self.output, self.config)
        self.assertNotIsInstance(raised.exception, PartialOutputError)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_partial_overwrite_preserves_the_file_that_could_not_be_replaced(self) -> None:
        for path in (self.output, self.report, self.json):
            path.write_bytes(b"ancien contenu")

        def fail_json(path, text, *, encoding, overwrite):
            if path == self.json:
                raise FileOperationError("échec simulé")
            return _write_text_atomic(path, text, encoding=encoding, overwrite=overwrite)

        with patch("codamnd.converter._write_text_atomic", side_effect=fail_json):
            with self.assertRaises(PartialOutputError) as raised:
                convert_file(self.source, self.output, self.config, overwrite=True)
        self.assertEqual(raised.exception.written_paths, (self.output, self.report))
        self.assertEqual(self.json.read_bytes(), b"ancien contenu")

    def test_validate_reports_partial_artifacts_without_claiming_a_mnd(self) -> None:
        def fail_json(path, text, *, encoding, overwrite):
            if path == self.json:
                raise FileOperationError("échec simulé")
            return _write_text_atomic(path, text, encoding=encoding, overwrite=overwrite)

        with patch("codamnd.converter._write_text_atomic", side_effect=fail_json):
            with self.assertRaises(PartialOutputError) as raised:
                validate_file(self.source, self.config, report_path=self.report, validation_json_path=self.json)
        self.assertEqual(raised.exception.written_paths, (self.report,))
        self.assertFalse(self.output.exists())

    def test_atomic_write_does_not_replace_a_file_created_during_the_write(self) -> None:
        publish_name = "rename" if os.name == "nt" else "link"
        publish = getattr(os, publish_name)

        def competing_write(staged, target):
            Path(target).write_bytes(b"autre operation")
            return publish(staged, target)

        with patch(f"codamnd.converter.os.{publish_name}", side_effect=competing_write):
            with self.assertRaises(FileOperationError):
                _write_text_atomic(self.output, "nouveau contenu", encoding="utf-8", overwrite=False)
        self.assertEqual(self.output.read_bytes(), b"autre operation")
        self.assertEqual(list(self.root.iterdir()), [self.output])

    def test_posix_link_publication_writes_complete_content_and_cleans_temporary(self) -> None:
        # Exercer aussi la publication POSIX sur le système de fichiers local.
        posix_ops = SimpleNamespace(name="posix", path=os.path, fsync=os.fsync, link=os.link)
        with patch("codamnd.converter.os", posix_ops):
            _write_text_atomic(self.output, "complet\r\n", encoding="utf-8", overwrite=False)
        self.assertEqual(self.output.read_bytes(), b"complet\r\n")
        self.assertEqual(list(self.root.iterdir()), [self.output])

    def test_cli_partial_error_lists_written_paths_and_returns_io_failure(self) -> None:
        def fail_report(path, text, *, encoding, overwrite):
            if path == self.report:
                raise FileOperationError("échec simulé")
            return _write_text_atomic(path, text, encoding=encoding, overwrite=overwrite)

        stderr = io.StringIO()
        with (
            patch("codamnd.converter._write_text_atomic", side_effect=fail_report),
            patch("codamnd.cli._audit"),
            redirect_stdout(io.StringIO()), redirect_stderr(stderr),
        ):
            code = cli.main(["--config-dir", str(ROOT / "config"), "convert", str(self.source), str(self.output)])
        self.assertEqual(code, cli.EXIT_IO)
        self.assertIn("Création incomplète", stderr.getvalue())
        self.assertIn(str(self.output), stderr.getvalue())
        self.assertIn(str(self.report), stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
