# Lanceur natif — prototype local

Ce paquet est un prototype technique, pas une version officielle. Ne pas l'utiliser pour une paie réelle ni le redistribuer comme une release validée.

Le moteur CodaMND reste inchangé. Un petit lanceur C charge le Python privé du dossier portable avec l'API publique d'intégration CPython 3.14. Aucun lanceur cx_Freeze, environnement virtuel, interpréteur système, extraction temporaire ou téléchargement au démarrage n'est utilisé.

Le lanceur fixe le module d'entrée et les chemins de recherche Python et DLL. Les options `-c`, `-m` et les scripts arbitraires sont refusés. Les variables Python et Tcl/Tk ambiantes ne servent pas à choisir le runtime. Cela ne protège pas contre la modification du dossier portable par un utilisateur ayant le droit d'y écrire.

Le contrôle de signature utilise désormais WinVerifyTrust, sans processus PowerShell. Il vérifie la signature embarquée et la révocation à partir du cache Windows local, sans accès réseau; une preuve absente ou périmée n'est pas interprétée comme une signature valide. Ce contrôle ne remplace pas une analyse antivirus.

## Construction séparée

Depuis la racine du dépôt, avec l'environnement verrouillé de construction :

```powershell
build/release-venv/Scripts/python.exe scripts/build_native_prototype.py --output build/native-prototype/essai-1
```

Prérequis du prototype : CPython 3.14.7 Windows x64 et Tcl/Tk 9.0.4, dépendances de `requirements-release.txt`, compilateur Zig 0.15.2 portable. Son [archive officielle](https://ziglang.org/download/0.15.2/zig-x86_64-windows-0.15.2.zip), placée dans `build/native-tools/`, doit avoir l'empreinte SHA256 suivante :

`3a0ed1e8799a2f8ce2a6e6290a9ff22e6906f8227865911fb7ddedc3cc14cb0c`

Extraire cette archive dans `build/native-tools/zig-x86_64-windows-0.15.2/`. Aucun outil n'est installé globalement. La construction refuse un dossier de sortie existant. Le ZIP produit porte explicitement la mention `native-prototype`; le circuit de publication officiel reste inchangé.

`prototype-inventory.json` donne la provenance et l'empreinte des fichiers embarqués. Les dépendances runtime sont sélectionnées depuis leurs métadonnées, comparées au verrou et leurs fichiers vérifiés contre leur RECORD installé. Cette vérification ne remplace pas l'installation initiale avec `pip --require-hashes`, ni une chaîne d'approvisionnement signée. Les bibliothèques CPython/Tcl/Tk proviennent de l'installation locale indiquée, avec inventaire; leur téléchargement officiel reproductible reste une étape à formaliser avant promotion.

## Validation

```powershell
build/release-venv/Scripts/python.exe scripts/validate_native_prototype.py --app build/native-prototype/essai-1/CodaMND
python scripts/agent_validate.py
```

Le diagnostic optionnel `CodaMND.exe --diagnostic rapport.json dossier-fixtures` travaille avec des fixtures synthétiques, initialise l'interface, vérifie la conversion TXT/MND et le contrôle PDF, puis ferme l'application. Il écrit uniquement un nouveau rapport local. Les vérifications de mise à jour et d'intégrité distante utilisent des réponses simulées; aucun envoi ni appel réseau de mise à jour n'est réalisé par ce diagnostic. Les chemins du rapport sont locaux et ne doivent pas être publiés sans revue.

Avant promotion : validation sur Windows sans Python installé, revue du lanceur et des licences, circuit de provenance/verrouillage du runtime, intégration SBOM/manifestes/CI, analyses antivirus du paquet et du candidat, et décision de signature. Aucun résultat antivirus favorable n'est garanti par cette architecture. Ne pas assouplir les contrôles de publication.

Références : [API d'initialisation CPython](https://docs.python.org/3.14/c-api/init_config.html), [distribution Python embarquée](https://docs.python.org/3.14/using/windows.html#the-embeddable-package), [recherche DLL Windows](https://learn.microsoft.com/en-us/windows/win32/api/libloaderapi/nf-libloaderapi-setdefaultdlldirectories).
