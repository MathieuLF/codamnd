# Construction Windows

CodaMND utilise un petit lanceur C qui charge le Python privé du dossier portable. Le moteur de conversion reste en Python. Aucun interpréteur système, extraction temporaire ou téléchargement au démarrage n'est nécessaire.

Le lanceur fixe le module d'entrée ainsi que les chemins Python et DLL. Il refuse les options `-c`, `-m` et les scripts arbitraires. Les variables Python et Tcl/Tk ambiantes ne choisissent pas le runtime. Un utilisateur pouvant modifier le dossier portable peut toutefois en modifier le code : l'empreinte publiée sert à vérifier le paquet, pas à empêcher ces modifications.

## Provenance et licences

[toolchain.json](toolchain.json) épingle les URL officielles, versions et empreintes de CPython 3.14.7 et Zig 0.15.2. La préparation extrait les archives dans `build/native-tools`, sans installer de logiciel ni modifier le registre ou le PATH. Chaque fichier est comparé à son archive avant construction. Les dépendances Python sont installées avec `pip --require-hashes` puis vérifiées contre leur RECORD.

L'archive complète [Python pour Windows](https://www.python.org/ftp/python/3.14.7/) fournit aussi Tcl/Tk 9.0.4, embarqué dans ses DLL. Les empreintes Python viennent de l'[index officiel](https://www.python.org/ftp/python/index-windows.json). L'extraction autonome est décrite dans la [documentation Python](https://docs.python.org/3.14/using/windows.html#offline-installs).

Le paquet contient les licences Python et de ses composants, Tcl/Tk, Zig, mingw-w64 et CodaMND, ainsi que les notices des dépendances dans leurs dossiers de métadonnées. `build-inventory.json` décrit les fichiers embarqués sans chemin propre au poste de construction. Le SBOM publié distingue les bibliothèques embarquées des outils de construction.

## Construire et vérifier

Depuis la racine du dépôt, avec Python 3.14.7 Windows x64 :

```powershell
scripts/release.ps1 -Version 0.2.1
```

Le script exige un dépôt propre et des destinations de publication libres. Il ne supprime pas les anciens candidats. Il construit le ZIP, exécute les tests synthétiques du véritable paquet, puis génère les empreintes et le SBOM. Il ne soumet rien à VirusTotal et ne publie pas de version.

Pour une construction séparée, après installation du verrou dans un environnement virtuel :

```powershell
python scripts/prepare_native_toolchain.py
python scripts/build_native.py --output build/native-release/essai-1
python scripts/validate_native.py --app build/native-release/essai-1/CodaMND
```

Les tests couvrent l'interface, TXT/MND/PDF, les déplacements avec accents et espaces, le ZIP extrait, les variables ambiantes hostiles et le refus de démarrer sans runtime privé. Les modules chargés doivent rester dans le paquet. Ces tests d'isolation ne remplacent pas un essai indépendant sur une machine Windows vierge.

Le diagnostic `CodaMND.exe --diagnostic rapport.json dossier-fixtures` travaille uniquement avec les fixtures synthétiques du dépôt. Il n'envoie rien et refuse de remplacer un rapport existant. Ses rapports détaillés peuvent contenir des chemins locaux : ne pas les publier sans revue.

## Publication

La publication manuelle exige un `main` propre et synchronisé, des tests réussis et une analyse terminée du véritable EXE, sans détection et avec un verdict exploitable de Zillya. Un changement de lanceur ne garantit pas un résultat antivirus favorable. Aucun contournement antivirus, exclusion ou désactivation de protection n'est prévu.

L'application reste non signée numériquement. L'absence de certificat est annoncée aux utilisateurs; aucun certificat payant n'est acheté automatiquement. Le contrôle local de signature utilise WinVerifyTrust et le cache de révocation Windows, sans PowerShell ni accès réseau. Un état indisponible reste non vérifié.
