"""Vérifie un tag existant sans le créer ni modifier le dépôt."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def check_tag(root: Path, tag: str, version: str) -> None:
    if not re.fullmatch(r"\d+\.\d+\.\d+", version) or tag != f"v{version}":
        raise ValueError(
            "Le tag doit correspondre à la version majeure.mineure.corrective."
        )
    project_version = tomllib.loads(
        (root / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]["version"]
    if project_version != version:
        raise ValueError("La version demandée ne correspond pas à pyproject.toml.")
    try:
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True, stderr=subprocess.PIPE
        ).strip()
        target = subprocess.check_output(
            ["git", "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}"],
            cwd=root,
            text=True,
            stderr=subprocess.PIPE,
        ).strip()
    except subprocess.CalledProcessError as error:
        raise ValueError(
            "Le tag doit déjà exister dans le dépôt et désigner un commit."
        ) from error
    if target != head:
        raise ValueError("Le tag ne désigne pas HEAD. La publication est bloquée.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    try:
        check_tag(ROOT, args.tag, args.version)
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print("Tag, version et commit concordent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
