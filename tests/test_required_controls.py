from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from codamnd import cli
from codamnd.config import load_app_config
from codamnd.errors import ValidationFailed
from codamnd.gui_controller import GuiController
from codamnd.parser_employeurd import parse_employeurd_bytes, parse_employeurd_file
from codamnd.reconciliation import reconcile_gl_detail


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "samples" / "employeurd-balanced.txt"


class RequiredControlsTest(unittest.TestCase):
    def test_cli_requires_pdf_for_both_commands_before_writing(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for command in ("validate", "convert"):
                with self.subTest(command=command):
                    args = ["--config-dir", str(ROOT / "config"), command, str(SOURCE)]
                    if command == "convert":
                        args.append(str(directory / "output.mnd"))
                    else:
                        args.extend(["--report", str(directory / "report.md"), "--json", str(directory / "report.json")])
                    stderr = io.StringIO()
                    with redirect_stderr(stderr), redirect_stdout(io.StringIO()), patch("codamnd.cli._audit"):
                        code = cli.main([*args, "--require-gl-detail"])
                    self.assertEqual(code, cli.EXIT_VALIDATION)
                    self.assertIn("--gl-detail", stderr.getvalue())
                    self.assertEqual(list(directory.iterdir()), [])

    def test_disabled_required_control_blocks_gui_and_cli(self):
        config = load_app_config(ROOT / "config")
        config = replace(config, reports=replace(config.reports, gl_detail=replace(config.reports.gl_detail, enabled=False)))
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            controller = GuiController()
            with patch("codamnd.gui_controller.load_app_config", return_value=config):
                for operation in (controller.validate, controller.generate):
                    args = dict(source_path=SOURCE, control_report_path=directory / "missing.pdf", require_control_report=True)
                    if operation == controller.generate:
                        args.update(output_root=directory, write_report=True, write_validation_json=True)
                    with self.subTest(operation=operation.__name__), self.assertRaises(ValidationFailed):
                        operation(**args)
            with patch("codamnd.cli.load_app_config", return_value=config), patch("codamnd.cli._audit"), redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
                code = cli.main(["convert", str(SOURCE), str(directory / "output.mnd"), "--gl-detail", str(directory / "missing.pdf"), "--require-gl-detail"])
            self.assertEqual(code, cli.EXIT_VALIDATION)
            self.assertEqual(list(directory.iterdir()), [])

    def test_disabled_advisory_control_remains_optional(self):
        config = load_app_config(ROOT / "config")
        config = replace(config, reports=replace(config.reports, gl_detail=replace(config.reports.gl_detail, enabled=False)))
        result = reconcile_gl_detail(parse_employeurd_file(SOURCE), Path("missing.pdf"), config)
        self.assertEqual(result.status, "skipped")
        self.assertFalse(result.required)

    def test_oversized_source_amount_is_a_validation_error(self):
        for amount in ("9" * 49, "-" + "9" * 48, "10000000000.00", "-10000000000.00"):
            with self.subTest(amount=amount):
                line = "00000001 50000000001" + amount.rjust(49) + "20261025\r\n"
                with self.assertRaises(ValidationFailed) as raised:
                    parse_employeurd_bytes(line.encode("ascii"))
                self.assertEqual(raised.exception.errors[0].code, "source_amount_range")
                self.assertEqual(raised.exception.errors[0].line_number, 1)

    def test_maximum_mnd_amount_is_still_accepted(self):
        for amount in ("9999999999.99", "-9999999999.99"):
            line = "00000001 50000000001" + amount.rjust(49) + "20261025\r\n"
            self.assertEqual(str(parse_employeurd_bytes(line.encode("ascii"))[0].amount), amount)
