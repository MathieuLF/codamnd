from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from codamnd.app_gui import CodaMNDApp
from codamnd.errors import ErrorDetail, PartialOutputError, ValidationFailed
from codamnd.gui_controller import GuiController, GuiOperationResult
from codamnd.gui_state import build_output_preview
from codamnd.parser_employeurd import read_employeurd_bytes
from codamnd.parser_mnd import parse_mnd_file
from codamnd.preferences import AppPreferences, load_preferences
from codamnd.user_messages import friendly_error_message, technical_error_message


def _headless_app(source: Path, output: Path) -> SimpleNamespace:
    """Exécuter la logique des widgets sans créer de fenêtre dans les tests ordinaires."""
    app = SimpleNamespace(busy=False, last_result=None, last_error=None)
    for name, value in (
        ("source_path", str(source)),
        ("control_report_path", ""),
        ("output_dir", str(output)),
        ("require_control_report", False),
        ("write_report_md", False),
        ("write_validation_json", False),
        ("disabled_reason", ""),
        ("status", ""),
        ("status_detail", ""),
    ):
        setattr(app, name, Mock(get=Mock(return_value=value)))
    for name in (
        "source_meta", "control_report_meta", "output_meta", "output_files",
        "require_control_report_check", "clear_control_report_button",
        "validate_button", "generate_button", "folder_button", "summary_button",
        "source_button", "control_report_button", "output_button", "source_entry",
        "control_report_entry", "output_entry", "report_option", "json_option",
        "progress", "validation_mode_label", "_refresh_dashboard", "_refresh_status_badge",
        "_clear_payroll_summaries", "_log_event",
    ):
        setattr(app, name, Mock())
    for name in (
        "_refresh_all", "_build_input_previews", "_can_validate", "_can_generate",
        "_disabled_reason", "_resolved_output_root",
        "_show_error", "_open_folder",
    ):
        setattr(app, name, MethodType(getattr(CodaMNDApp, name), app))
    return app


class GuiReliabilityTest(unittest.TestCase):
    def test_missing_preferences_keep_first_launch_default_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "absent" / "preferences.json"
            for default in (False, True):
                with self.subTest(default=default):
                    self.assertEqual(
                        load_preferences(path, default_update_check_on_startup=default),
                        AppPreferences(update_check_on_startup=default),
                    )
                    self.assertFalse(path.parent.exists())

    def test_invalid_preferences_fall_back_without_rewriting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preferences.json"
            for content in (b"\xff", b'{"output_dir":', b"[]", b'"texte"', b"null", b"1"):
                with self.subTest(content=content):
                    path.write_bytes(content)
                    self.assertEqual(
                        load_preferences(path, default_update_check_on_startup=True),
                        AppPreferences(),
                    )
                    self.assertEqual(path.read_bytes(), content)

    def test_only_json_true_enables_startup_update_check(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preferences.json"
            for value in (True, False, "false", "true", "", 0, 1, None, [], [True], {}, {"enabled": True}):
                with self.subTest(value=value):
                    content = json.dumps({"output_dir": " C:/Sorties ", "update_check_on_startup": value})
                    path.write_text(content, encoding="utf-8")
                    preferences = load_preferences(path)
                    self.assertEqual(preferences.output_dir, "C:/Sorties")
                    self.assertIs(preferences.update_check_on_startup, value is True)
                    self.assertEqual(path.read_text(encoding="utf-8"), content)

    def test_invalid_output_preference_keeps_valid_update_preference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preferences.json"
            for value in (None, True, 42, [], {}):
                with self.subTest(value=value):
                    path.write_text(json.dumps({"output_dir": value, "update_check_on_startup": True}), encoding="utf-8")
                    self.assertEqual(load_preferences(path), AppPreferences(update_check_on_startup=True))

    def test_generic_validation_errors_keep_their_local_explanation(self) -> None:
        for message in (
            "Le fichier source est vide.",
            "Le fichier source dépasse la limite de 10 Mo.",
            "Le rapport de contrôle est requis en mode bloquant.",
        ):
            with self.subTest(message=message):
                self.assertEqual(friendly_error_message(ValidationFailed(message)), f"- {message}")

    def test_known_error_keeps_friendly_message_and_line_number(self) -> None:
        error = ValidationFailed([ErrorDetail("source_date_invalid", "Détail technique", 7, "date")])
        self.assertEqual(friendly_error_message(error), "- Une date du fichier EmployeurD est invalide. Ligne 7.")

    def test_generic_support_diagnostic_does_not_copy_local_details(self) -> None:
        message = r"Fichier C:\Paie\confidentiel.txt : montant 9876.54."
        error = ValidationFailed(message)
        self.assertIn(message, friendly_error_message(error))
        self.assertEqual(technical_error_message(error), "- validation_failed")

    def test_refresh_reads_source_once_and_keeps_button_gates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            app = _headless_app(ROOT / "samples" / "employeurd-balanced.txt", Path(directory))
            for busy, validated in ((False, False), (False, True), (True, True)):
                with self.subTest(busy=busy, validated=validated):
                    app.busy = busy
                    app.last_result = GuiOperationResult(ok=True, message="OK") if validated else None
                    with patch("codamnd.parser_employeurd.read_employeurd_bytes", wraps=read_employeurd_bytes) as read_source:
                        app._refresh_all()
                    self.assertEqual(read_source.call_count, 1)
                    app.validate_button.state.assert_called_with(["disabled"] if busy else ["!disabled"])
                    app.generate_button.state.assert_called_with(["!disabled"] if validated and not busy else ["disabled"])

    def test_refresh_identifies_invalid_txt_pdf_and_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = ROOT / "samples" / "employeurd-balanced.txt"
            wrong_type = root / "rapport.csv"
            wrong_type.write_text("exemple synthétique", encoding="utf-8")
            cases = (
                (str(root / "absent.txt"), "", str(root), "TXT EmployeurD"),
                (str(wrong_type), "", str(root), "TXT EmployeurD"),
                (str(source), str(wrong_type), str(root), "PDF GL"),
                (str(source), str(root / "absent.pdf"), str(root), "PDF GL"),
                (str(source), "", str(wrong_type), "Destination"),
            )
            for txt, pdf, output, expected in cases:
                with self.subTest(expected=expected, txt=txt, pdf=pdf):
                    app = _headless_app(source, root)
                    app.source_path.get.return_value = txt
                    app.control_report_path.get.return_value = pdf
                    app.output_dir.get.return_value = output
                    app.last_result = GuiOperationResult(ok=True, message="Ancien résultat")
                    app._refresh_all()
                    self.assertIn(expected, app.disabled_reason.set.call_args.args[0])
                    app.validate_button.state.assert_called_with(["disabled"])
                    app.generate_button.state.assert_called_with(["disabled"])

    def test_refresh_notices_source_removed_after_previous_preview(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "synthese.txt"
            source.write_bytes((ROOT / "samples" / "employeurd-balanced.txt").read_bytes())
            app = _headless_app(source, root)
            app.last_result = GuiOperationResult(ok=True, message="OK")
            app._refresh_all()
            app.generate_button.state.assert_called_with(["!disabled"])
            source.unlink()
            app._refresh_all()
            app.generate_button.state.assert_called_with(["disabled"])
            self.assertIn("n'existe pas", app.disabled_reason.set.call_args.args[0])

    def test_generation_revalidates_changed_source_and_uses_current_batch(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch("codamnd.gui_controller._audit"):
            root = Path(directory)
            source = root / "synthese.txt"
            balanced = (ROOT / "samples" / "employeurd-balanced.txt").read_bytes()
            source.write_bytes(balanced)
            controller = GuiController(config_dir=ROOT / "config")
            inputs = dict(source_path=source, control_report_path=None, require_control_report=False)
            self.assertTrue(controller.validate(**inputs).ok)
            source.write_bytes((ROOT / "samples" / "employeurd-unbalanced.txt").read_bytes())
            with self.assertRaises(ValidationFailed):
                controller.generate(**inputs, output_root=root / "sorties", write_report=False, write_validation_json=False)
            self.assertFalse((root / "sorties").exists())
            source.write_bytes(balanced.replace(b"00001234", b"00005678"))
            result = controller.generate(**inputs, output_root=root / "sorties", write_report=False, write_validation_json=False)
            self.assertEqual(result.conversion.batch, "00005678")
            self.assertTrue(result.conversion.output_path.name.endswith("lot_00005678.mnd"))
            self.assertTrue(all(entry.reference == "00005678" for entry in parse_mnd_file(result.conversion.output_path)))

    def test_file_selection_and_removal_are_ignored_while_busy(self) -> None:
        app = SimpleNamespace(busy=True)
        with (
            patch("codamnd.app_gui.filedialog.askopenfilename") as select_file,
            patch("codamnd.app_gui.filedialog.askdirectory") as select_directory,
        ):
            for method in ("_choose_source", "_choose_control_report", "_clear_control_report", "_choose_output_dir"):
                with self.subTest(method=method):
                    getattr(CodaMNDApp, method)(app)
            select_file.assert_not_called()
            select_directory.assert_not_called()

    def test_nested_output_preview_is_read_only_and_generation_creates_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch("codamnd.gui_controller._audit"):
            root = Path(directory) / "nouveau" / "sous-dossier"
            source = ROOT / "samples" / "employeurd-balanced.txt"
            preview = build_output_preview(str(source), str(root))
            self.assertTrue(preview.ok)
            self.assertFalse(root.parent.exists())
            result = GuiController(config_dir=ROOT / "config").generate(
                source_path=source, output_root=root, control_report_path=None,
                require_control_report=False, write_report=False, write_validation_json=False,
            )
            self.assertTrue(result.conversion.output_path.is_file())
            self.assertTrue(result.conversion.output_path.is_relative_to(root))

    def test_nested_output_rejects_file_ancestor_and_unwritable_ancestor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = ROOT / "samples" / "employeurd-balanced.txt"
            obstacle = root / "fichier"
            obstacle.write_text("exemple", encoding="utf-8")
            self.assertFalse(build_output_preview(str(source), str(obstacle / "enfant" / "sortie")).ok)
            with patch("codamnd.gui_state.os.access", return_value=False):
                self.assertFalse(build_output_preview(str(source), str(root / "nouveau" / "sortie")).ok)

    def test_partial_output_stays_accessible_without_enabling_generation_or_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            written = root / "operation" / "sortie.mnd"
            written.parent.mkdir()
            written.write_bytes(b"synthetique")
            error = PartialOutputError((written,), written.with_suffix(".rapport.md"))
            app = _headless_app(ROOT / "samples" / "employeurd-balanced.txt", root / "autre")
            app.last_result = GuiOperationResult(ok=True, message="Ancien résultat")
            with patch("codamnd.app_gui.messagebox.showerror") as dialog:
                app._show_error(error)
            app._refresh_all()
            app.status.set.assert_called_with("Création incomplète")
            self.assertNotIn("Aucun MND", app.status_detail.set.call_args.args[0])
            self.assertIn(str(written), dialog.call_args.args[1])
            self.assertIsNone(app.last_result)
            app.generate_button.state.assert_called_with(["disabled"])
            app.summary_button.state.assert_called_with(["disabled"])
            app.folder_button.state.assert_called_with(["!disabled"])
            with patch("codamnd.app_gui.open_folder") as open_folder:
                app._open_folder()
            open_folder.assert_called_once_with(written)


if __name__ == "__main__":
    unittest.main()
