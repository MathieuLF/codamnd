"""Installe l'environnement du dépôt sans clé ni service externe."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import venv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prépare les dépendances verrouillées dans .venv."
    )
    parser.add_argument(
        "--build", action="store_true", help="Installe aussi le packager Windows."
    )
    args = parser.parse_args()
    if sys.version_info < (3, 12):
        parser.error("Python 3.12 ou plus récent est requis.")
    try:
        import tkinter  # noqa: F401
    except ImportError:
        parser.error("Tkinter manque pour ce Python. Voir docs/developpement.md.")
    if args.build and sys.platform != "win32":
        parser.error("Le paquet officiel se construit sous Windows.")
    if args.build and sys.version_info[:2] != (3, 14):
        parser.error("Le build Windows utilise Python 3.14. Lancez le setup avec cet interpréteur.")

    # Le profil de build reste séparé du profil de revue.
    environment = ROOT / (".venv-build" if args.build else ".venv")
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.exists():
        venv.EnvBuilder(with_pip=True).create(environment)
    version = subprocess.check_output(
        [
            str(python),
            "-c",
            "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')",
        ],
        text=True,
    ).strip()
    if version != f"{sys.version_info.major}.{sys.version_info.minor}":
        parser.error(
            f"{environment.name} utilise un autre Python. Recréez-le avec le runtime choisi."
        )

    requirements = "requirements-build.txt" if args.build else "requirements-dev.txt"
    commands = [
        [str(python), "-m", "pip", "install", "-r", requirements],
        [str(python), "-m", "pip", "check"],
    ]
    for command in commands:
        completed = subprocess.run(command, cwd=ROOT, check=False)
        if completed.returncode:
            return completed.returncode
    print(f"Prêt : {python} scripts/agent_validate.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
