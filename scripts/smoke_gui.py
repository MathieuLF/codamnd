"""Ouvre puis ferme la GUI avec des préférences et journaux temporaires."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from codamnd.app_gui import CodaMNDApp


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="codamnd-gui-") as directory:
        root = Path(directory)
        with (
            patch.dict(
                os.environ, {"LOCALAPPDATA": directory, "XDG_CONFIG_HOME": directory}
            ),
            patch("codamnd.app_gui.default_config_dir", return_value=ROOT / "config"),
            patch(
                "codamnd.preferences.preferences_dir", return_value=root / "preferences"
            ),
        ):
            app = CodaMNDApp()
            try:
                app.withdraw()
                app.update_idletasks()
                app.update()
                assert app.winfo_exists()
            finally:
                app.destroy()
    print("Lancement GUI OK (préférences temporaires).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
