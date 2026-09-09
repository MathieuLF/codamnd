param(
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$Version = "0.2.1",
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path -LiteralPath "$PSScriptRoot/..").Path
Set-Location -LiteralPath $RepoRoot
$AppVersion = & $Python -c "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])"
if ($LASTEXITCODE -ne 0 -or $AppVersion.Trim() -ne $Version) {
    throw "La version demandée ne correspond pas au code source."
}
# Never erase an earlier candidate or its antivirus evidence.
if ((Test-Path -LiteralPath "dist/CodaMND") -or (Get-ChildItem -Path "dist/CodaMND-v$Version*" -ErrorAction SilentlyContinue)) {
    throw "Des artefacts existent déjà dans dist. Archivez-les avant de reconstruire."
}
& $Python scripts/prepare_native_toolchain.py
if ($LASTEXITCODE -ne 0) { throw "La vérification de la chaîne de construction a échoué." }
$BuildOutput = "build/native-release/package-$([guid]::NewGuid().ToString('N'))"
# build_native.py embeds packaging/windows/CodaMND.ico and CodaMND.manifest.
& $Python scripts/build_native.py --output $BuildOutput
if ($LASTEXITCODE -ne 0) { throw "La construction native a échoué." }
& $Python scripts/validate_native.py --app "$BuildOutput/CodaMND"
if ($LASTEXITCODE -ne 0) { throw "La validation du paquet portable a échoué." }
New-Item -ItemType Directory -Path "dist" -Force | Out-Null
Copy-Item -LiteralPath "$BuildOutput/CodaMND" -Destination "dist/CodaMND" -Recurse
Copy-Item -LiteralPath "$BuildOutput/CodaMND-v$Version-portable.zip" -Destination "dist"
Copy-Item -LiteralPath "$BuildOutput/CodaMND-v$Version-portable.zip.sha256" -Destination "dist"
$ExeHash = (Get-FileHash -Algorithm SHA256 -LiteralPath "dist/CodaMND/CodaMND.exe").Hash.ToLowerInvariant()
"$ExeHash  CodaMND.exe" | Set-Content -Encoding ascii "dist/CodaMND-v$Version-portable.exe.sha256"
