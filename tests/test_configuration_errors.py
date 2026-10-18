from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from codamnd import app_gui, cli
from codamnd.config import _load_config_file, load_app_config
from codamnd.errors import ConfigurationError


class ConfigurationErrorsTest(unittest.TestCase):
    def test_yaml_error_identifies_file_and_location_without_copying_contents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "app.yml"
            path.write_text("mnd: [contenu-prive\n", encoding="utf-8")
            with self.assertRaises(ConfigurationError) as raised:
                _load_config_file(path)
            message = str(raised.exception)
            self.assertIn(str(path), message)
            self.assertIn("syntaxe YAML invalide", message)
            self.assertIn("ligne", message)
            self.assertIn("colonne", message)
            self.assertNotIn("contenu-prive", message)

    def test_invalid_utf8_is_a_configuration_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "app.yml"
            path.write_bytes(b"\xff")
            with self.assertRaises(ConfigurationError) as raised:
                _load_config_file(path)
            self.assertIn(str(path), str(raised.exception))
            self.assertEqual(path.read_bytes(), b"\xff")

    def test_cli_bad_configuration_returns_usage_error_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "comptes.yml").write_text("accounts: [", encoding="utf-8")
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                code = cli.main(["--config-dir", str(root), "inspect-source", str(ROOT / "samples" / "employeurd-balanced.txt")])
            self.assertEqual(code, cli.EXIT_USAGE)
            self.assertIn("Erreur configuration", stderr.getvalue())
            self.assertNotIn("Traceback", stderr.getvalue())

    def test_gui_startup_shows_configuration_error_and_closes_temporary_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "comptes.yml").write_text("accounts: [", encoding="utf-8")
            with (
                patch("codamnd.app_gui.default_config_dir", return_value=root),
                patch("codamnd.app_gui.tk.Tk") as tk_root,
                patch("codamnd.app_gui.messagebox.showerror") as dialog,
            ):
                self.assertEqual(app_gui.main(), 2)
            tk_root.assert_called_once_with()
            tk_root.return_value.withdraw.assert_called_once_with()
            tk_root.return_value.destroy.assert_called_once_with()
            self.assertEqual(dialog.call_args.args[0], "Configuration à corriger")
            self.assertIn("syntaxe YAML invalide", dialog.call_args.args[1])

    def test_valid_configuration_keeps_existing_values(self) -> None:
        config = load_app_config(ROOT / "config")
        self.assertEqual(config.mnd.output_encoding, "cp1252")
        self.assertTrue(config.validation.require_balanced)
        self.assertTrue(config.validation.require_mnd_roundtrip)


if __name__ == "__main__":
    unittest.main()
