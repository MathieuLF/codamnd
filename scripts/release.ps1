param(
    [string]$Version = "0.1.0",
    [switch]$AllowDirty
)

$ErrorActionPreference = "Stop"

$ReleasePythonVersion = python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($LASTEXITCODE -ne 0 -or $ReleasePythonVersion.Trim() -ne "3.14") {
    throw "La construction officielle exige Python 3.14 pour correspondre au verrou de dépendances."
}
python -m venv build/release-venv --clear
if ($LASTEXITCODE -ne 0) {
    throw "La création de l'environnement de mise en ligne a échoué avec le code $LASTEXITCODE"
}
$ReleasePython = (Resolve-Path -LiteralPath "build/release-venv/Scripts/python.exe").Path
& $ReleasePython -m pip install --require-hashes -r requirements-release.txt
if ($LASTEXITCODE -ne 0) {
    throw "L'installation des dépendances verrouillées a échoué avec le code $LASTEXITCODE"
}

$AuditArgs = @("scripts/audit_release_readiness.py", "--version", $Version)
if (-not $AllowDirty) {
    $AuditArgs += "--require-clean"
}
& $ReleasePython @AuditArgs
if ($LASTEXITCODE -ne 0) {
    throw "L'audit de préparation a échoué avec le code $LASTEXITCODE"
}

& $ReleasePython -m unittest discover -s tests
if ($LASTEXITCODE -ne 0) {
    throw "Les tests ont échoué avec le code $LASTEXITCODE"
}

& $ReleasePython -X pycache_prefix=build/pycache -m compileall src
if ($LASTEXITCODE -ne 0) {
    throw "La compilation Python a échoué avec le code $LASTEXITCODE"
}

.\scripts\build_exe.ps1 -Version $Version -Python $ReleasePython

$PackageHash = & $ReleasePython -c "import sys; sys.path.insert(0, 'src'); from pathlib import Path; from codamnd.integrity import app_package_sha256; print(app_package_sha256(Path('dist/CodaMND')) or '')"
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($PackageHash)) {
    throw "La génération de l'empreinte du paquet a échoué avec le code $LASTEXITCODE"
}
$PackageHash = $PackageHash.Trim()
$PackageHash + "  CodaMND-v$Version-package" | Set-Content -Encoding ascii "dist/CodaMND-v$Version.package.sha256"

& $ReleasePython scripts/generate_sbom.py --version $Version
if ($LASTEXITCODE -ne 0) {
    throw "La génération du SBOM a échoué avec le code $LASTEXITCODE"
}

& $ReleasePython scripts/extract_changelog.py --version $Version --output "dist/CodaMND-v$Version.release-notes.md"
if ($LASTEXITCODE -ne 0) {
    throw "L'extraction du journal des changements a échoué avec le code $LASTEXITCODE"
}

$PortableExe = "dist/CodaMND/CodaMND.exe"

$VirusTotal = "dist/CodaMND-v$Version.virustotal.md"
@"
# Rapport VirusTotal CodaMND v$Version

Rapport à produire après l'analyse de l'exécutable public seulement.
Ne jamais soumettre de TXT EmployeurD, rapport de contrôle, MND, Markdown ou JSON de validation.
"@ | Set-Content -Encoding utf8 $VirusTotal
