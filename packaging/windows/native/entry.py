"""Fixed entry point for the native prototype; not a general Python launcher."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def configure_runtime() -> Path:
    root = Path(sys.executable).resolve().parent
    sys.frozen = True
    # Tcl/Tk also has environment-based discovery, independent of Python -I.
    for name in ("TCL_LIBRARY", "TK_LIBRARY", "TCLLIBPATH"):
        os.environ.pop(name, None)
    # CPython 3.14's Tcl/Tk 9 archives are distributed at their standard location.
    # The DLLs mount those archives themselves. Do not resolve Tcl from the host.
    return root


def main(argv: list[str] | None = None) -> int:
    configure_runtime()
    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        if len(args) == 3 and args[0] == "--diagnostic":
            from _codamnd_probe import run

            return run(Path(args[1]), Path(args[2]))
        # In particular, never accept Python's -c/-m/script execution options.
        return 2
    try:
        from codamnd.app_gui import CodaMNDApp

        app = CodaMNDApp()
        app.title(app.title() + " — prototype")
        app.mainloop()
        return 0
    except Exception:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            None,
            "Impossible d'ouvrir CodaMND. Vérifiez que le dossier portable est complet.",
            "CodaMND — prototype",
            0x10,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
