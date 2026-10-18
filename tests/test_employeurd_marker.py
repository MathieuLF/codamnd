"""Régressions du champ en position 9, avec des écritures fictives seulement."""

from datetime import date
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from codamnd.config import load_app_config
from codamnd.converter import convert_file
from codamnd.errors import ValidationFailed
from codamnd.gui_controller import GuiController
from codamnd.parser_employeurd import parse_employeurd_bytes, parse_employeurd_line
from codamnd.parser_mnd import parse_mnd_file


ROOT = Path(__file__).resolve().parents[1]


def row(marker="1", *, account="50213000140", amount="125.25", entry_date="20260618"):
    return "00001234" + marker + account + amount.rjust(49) + entry_date


def balanced_source(marker="1"):
    return (row(marker) + "\r\n" + row(marker, account="55411200000", amount="-125.25") + "\r\n").encode("ascii")


class EmployeurDMarkerTest(unittest.TestCase):
    def test_periods_9_to_12_preserve_the_gl_account(self):
        from codamnd.validator import convert_account

        config = load_app_config(ROOT / "config")
        for period in range(9, 13):
            with self.subTest(period=period):
                line = "00001234" + f"{period:2d}" + "0213000140" + "125.25".rjust(49) + "20260618"
                entry = parse_employeurd_line(line)
                self.assertEqual(entry.batch, "00001234")
                self.assertEqual(convert_account(entry.account, config.accounts), "0213000140")

    def test_supported_markers_preserve_field_positions_and_raw_line(self):
        for marker in " 0123456789":
            with self.subTest(marker=marker):
                line = row(marker)
                entry = parse_employeurd_line(line, 7)
                self.assertEqual(entry.line_number, 7)
                self.assertEqual(entry.batch, "00001234")
                self.assertEqual(entry.account, "50213000140")
                self.assertEqual(entry.amount, Decimal("125.25"))
                self.assertEqual(entry.entry_date, date(2026, 6, 18))
                self.assertEqual(entry.raw_line, line)

    def test_unsupported_markers_are_still_rejected(self):
        for marker in ("X", "\t", "\u00a0", "\uff11"):
            with self.subTest(marker=marker), self.assertRaises(ValidationFailed) as raised:
                parse_employeurd_line(row(marker), 4)
            self.assertEqual(raised.exception.errors[0].code, "source_separator")
            self.assertEqual(raised.exception.errors[0].line_number, 4)

    def test_marker_does_not_relax_other_field_checks(self):
        for line, code in (
            (row().replace("00001234", "badbatch"), "source_batch"),
            (row(account="5021300014X"), "source_account"),
            (row(amount="125.251"), "source_amount_format"),
            (row(entry_date="20260231"), "source_date_invalid"),
            (row(""), "source_line_length"),
            (row("1 "), "source_line_length"),
        ):
            with self.subTest(code=code), self.assertRaises(ValidationFailed) as raised:
                parse_employeurd_line(line)
            self.assertIn(code, [error.code for error in raised.exception.errors])

    def test_crlf_requirement_is_preserved(self):
        self.assertEqual(len(parse_employeurd_bytes(balanced_source(), reject_non_crlf=True)), 2)
        with self.assertRaises(ValidationFailed):
            parse_employeurd_bytes(balanced_source().replace(b"\r\n", b"\n"), reject_non_crlf=True)

    def test_both_variants_produce_identical_mnd_bytes(self):
        config = load_app_config(ROOT / "config")
        outputs = []
        with tempfile.TemporaryDirectory() as directory:
            for index, marker in enumerate((" ", "1")):
                source = Path(directory) / f"source{index}.txt"
                output = Path(directory) / f"output{index}.mnd"
                source.write_bytes(balanced_source(marker))
                result = convert_file(source, output, config, write_report=False, write_validation_json=False)
                self.assertEqual(result.total_debit, Decimal("125.25"))
                self.assertEqual(result.total_credit, Decimal("125.25"))
                outputs.append(output.read_bytes())
                entries = parse_mnd_file(output)
                self.assertEqual([entry.account for entry in entries], ["0213000140", "5411200000"])
                self.assertEqual(entries[0].reference, "00001234")
                self.assertEqual(entries[0].batch, "001234")
                self.assertTrue(all(len(line) == 479 for line in outputs[-1].split(b"\r\n")[:-1]))
            self.assertEqual(outputs[0], outputs[1])

    @patch("codamnd.gui_controller._audit")
    def test_gui_validates_and_generates_numeric_marker_source(self, _audit):
        controller = GuiController(config_dir=ROOT / "config")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.txt"
            source.write_bytes(balanced_source())
            arguments = dict(source_path=source, control_report_path=None, require_control_report=False)
            self.assertTrue(controller.validate(**arguments).ok)
            result = controller.generate(
                **arguments, output_root=Path(directory) / "output", write_report=False, write_validation_json=False,
            )
            self.assertTrue(result.ok)
            self.assertEqual(len(parse_mnd_file(result.conversion.output_path)), 2)

    def test_unbalanced_numeric_marker_source_cannot_create_mnd(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.txt"
            output = Path(directory) / "output.mnd"
            source.write_bytes((row() + "\r\n").encode("ascii"))
            with self.assertRaises(ValidationFailed) as raised:
                convert_file(source, output, load_app_config(ROOT / "config"), write_report=False, write_validation_json=False)
            self.assertIn("source_unbalanced", [error.code for error in raised.exception.errors])
            self.assertFalse(output.exists())
