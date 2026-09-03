from __future__ import annotations

import json
import platform
import re
import sys
from importlib import metadata
from argparse import ArgumentParser
from datetime import datetime, timezone
from pathlib import Path


LOCKED_REQUIREMENT_RE = re.compile(r"^([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+!-]+)")


def main() -> int:
    parser = ArgumentParser()
    parser.add_argument("--version", default=None)
    args = parser.parse_args()

    sys.path.insert(0, str(Path("src").resolve()))
    from codamnd.version import __version__

    if args.version and args.version != __version__:
        raise SystemExit(f"La version de mise en ligne {args.version} ne correspond pas à la version de l'application {__version__}.")

    output = Path("dist") / f"CodaMND-v{__version__}.sbom.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    components = [
        {
            "type": "framework",
            "name": "Python",
            "version": platform.python_version(),
        }
    ]
    lock_file = Path("requirements-release.txt")
    locked_requirements = _locked_requirements(lock_file)
    dependency_issues: list[str] = []
    for package_name, locked_version in locked_requirements.items():
        try:
            package_version = metadata.version(package_name)
        except metadata.PackageNotFoundError:
            dependency_issues.append(f"Dépendance verrouillée absente: {package_name}=={locked_version}")
            continue
        if package_version != locked_version:
            dependency_issues.append(
                f"Version installée différente du verrou: {package_name}=={package_version} (attendue: {locked_version})"
            )
        components.append({"type": "library", "name": package_name, "version": package_version})

    if dependency_issues:
        raise SystemExit("\n".join(dependency_issues))

    payload = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tools": [{"vendor": "local", "name": "scripts/generate_sbom.py"}],
            "component": {
                "type": "application",
                "name": "CodaMND",
                "version": __version__,
            },
        },
        "components": components,
    }
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(output)
    return 0


def _locked_package_names(path: Path) -> list[str]:
    return list(_locked_requirements(path))


def _locked_requirements(path: Path) -> dict[str, str]:
    requirements: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = LOCKED_REQUIREMENT_RE.match(line)
        if match:
            name, version = match.groups()
            normalized_name = re.sub(r"[-_.]+", "-", name).lower()
            previous = requirements.get(normalized_name)
            if previous and previous != version:
                raise ValueError(f"Versions verrouillées contradictoires pour {normalized_name}.")
            requirements[normalized_name] = version
    return dict(sorted(requirements.items()))


if __name__ == "__main__":
    raise SystemExit(main())
