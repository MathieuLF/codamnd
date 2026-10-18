"""Parcours du rapprochement net, avec TXT et PDF synthétiques uniquement."""

from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from codamnd.config import load_app_config
from codamnd.errors import ValidationFailed
from codamnd.gui_controller import GuiController
from codamnd.gui_state import summary_text
from codamnd.parser_employeurd import parse_employeurd_file
from codamnd.parser_mnd import parse_mnd_file
from codamnd.reconciliation import reconcile_gl_detail
from codamnd.user_messages import friendly_error_message, technical_error_message
from test_converter import _write_synthetic_gl_detail_pdf


ROOT = Path(__file__).resolve().parents[1]


def source_text(*, account="0213000140", amount="125.25", entry_date="20260618"):
    # PC 10, compte GL de dix chiffres, montant et date aux positions fixes.
    return "".join(
        "0000123410" + gl + str(value).rjust(49) + entry_date + "\r\n"
        for gl, value in ((account, Decimal(amount)), ("5411200000", -Decimal(amount)))
    )


class NetReconciliationTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.source = self.directory / "source.txt"
        self.source.write_bytes(source_text().encode("ascii"))
        self.report = self.directory / "control.pdf"
        self.config = load_app_config(ROOT / "config")
        self.entries = parse_employeurd_file(self.source)
        debit, credit = self.entries
        self.detail = [debit, replace(credit, amount=Decimal("-150.25")), replace(credit, amount=Decimal("25.00"))]
        _write_synthetic_gl_detail_pdf(self.report, self.detail, self.config)
        self.controller = GuiController(config_dir=ROOT / "config")
        audit = patch("codamnd.gui_controller._audit")
        audit.start()
        self.addCleanup(audit.stop)

    def arguments(self):
        return dict(source_path=self.source, control_report_path=self.report, require_control_report=True)

    def test_gui_and_generated_reports_distinguish_net_from_gross(self):
        validation = self.controller.validate(**self.arguments())
        self.assertIn("totaux nets par compte", summary_text(validation.conversion, validation.reconciliations))
        generated = self.controller.generate(
            **self.arguments(), output_root=self.directory / "output", write_report=True, write_validation_json=True,
        )
        result = generated.conversion
        self.assertEqual([entry.account for entry in parse_mnd_file(result.output_path)], ["0213000140", "5411200000"])
        markdown = result.report_path.read_text(encoding="utf-8")
        self.assertIn("Total débit net du PDF GL", markdown)
        self.assertIn("pdf_gross_debit: 150.25", markdown)
        payload = json.loads(result.validation_json_path.read_text(encoding="utf-8"))
        reconciliation = next(item for item in payload["reconciliations"] if item["report_type"] == "GL_DETAIL")
        self.assertEqual(reconciliation["report_debit"], "125.25")
        self.assertEqual(reconciliation["details"]["pdf_gross_debit"], "150.25")
        self.assertEqual(reconciliation["details"]["comparison_basis"], "net_by_account")

    def test_gui_rejection_preserves_the_real_cause_and_safe_diagnostics(self):
        cases = (
            ({"entry_date": "20260619"}, "gl_detail_date_mismatch", "date"),
            ({"account": "0213000200"}, "gl_detail_account_mismatch", "comptes"),
            ({"amount": "124.25"}, "gl_detail_amount_mismatch", "totaux"),
        )
        for changes, code, wording in cases:
            with self.subTest(changes=changes):
                self.source.write_bytes(source_text(**changes).encode("ascii"))
                with self.assertRaises(ValidationFailed) as raised:
                    self.controller.validate(**self.arguments())
                self.assertIn(code, [error.code for error in raised.exception.errors])
                self.assertIn(wording, friendly_error_message(raised.exception))
                diagnostics = technical_error_message(raised.exception)
                self.assertIn(code, diagnostics)
                for sensitive in (str(self.directory), "0213000140", "0213000200", "125.25", "20260619"):
                    self.assertNotIn(sensitive, diagnostics)

    def test_generation_rechecks_a_pdf_modified_after_net_validation(self):
        self.assertTrue(self.controller.validate(**self.arguments()).ok)
        self.report.write_bytes(self.report.read_bytes().replace(b"2026/06/18", b"2026/06/19"))
        output = self.directory / "output"
        with self.assertRaises(ValidationFailed) as raised:
            self.controller.generate(**self.arguments(), output_root=output, write_report=True, write_validation_json=True)
        self.assertIn("gl_detail_date_mismatch", [error.code for error in raised.exception.errors])
        self.assertFalse(output.exists())

    def test_netting_handles_debit_credit_and_zero_balances_per_account(self):
        debit, credit = self.entries
        detailed = [
            replace(debit, amount=Decimal("145.25")), replace(debit, amount=Decimal("-20.00")),
            replace(credit, amount=Decimal("-150.25")), replace(credit, amount=Decimal("25.00")),
            replace(debit, account="00213000200", amount=Decimal("30.00")),
            replace(debit, account="00213000200", amount=Decimal("-30.00")),
        ]
        _write_synthetic_gl_detail_pdf(self.report, detailed, self.config)
        result = reconcile_gl_detail(self.entries, self.report, self.config, required=True)
        self.assertEqual(result.status, "success")
        self.assertEqual(result.details["comparison_basis"], "net_by_account")
        self.assertEqual(result.report_debit, result.report_credit)
        self.assertEqual(result.report_debit, Decimal("125.25"))
        self.assertEqual(result.details["pdf_gross_debit"], "200.25")

    def test_netting_cannot_hide_equal_total_transfers_between_accounts(self):
        debit, credit = self.entries
        wrong = [replace(debit, amount=Decimal("100.25")), replace(debit, account="00213000200", amount=Decimal("25.00")), credit]
        for require_accounts in (True, False):
            config = replace(self.config, reports=replace(
                self.config.reports, gl_detail=replace(self.config.reports.gl_detail, require_account_totals=require_accounts),
            ))
            with self.subTest(require_accounts=require_accounts):
                result = reconcile_gl_detail(wrong, self.report, config, required=True)
                self.assertEqual(result.status, "failed")
                self.assertEqual(result.details["comparison_basis"], "gross")
