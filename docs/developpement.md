# Développement et Codex Cloud

## Architecture

CodaMND est une application locale, sans serveur ni base de données. Les TXT
EmployeurD sont lus par `parser_employeurd.py`, validés avec `validator.py`, convertis
par `converter.py` et écrits par `writer_mnd.py`. `parser_mnd.py` relit la sortie
pour vérifier sa cohérence. Les montants utilisent `Decimal`.

Le parser `reports/gl_detail_pdf_parser.py` lit le PDF GL avec pdfplumber.
`reconciliation.py` compare totaux et comptes. `gui_controller.py` partage ce
moteur avec la CLI; `app_gui.py`, les dialogues, l'état et le thème assurent la GUI.
Le microsite `docs/index.html` est indépendant de l'application.

## Installation Windows

Python 3.12 ou plus récent, pip, venv et Tkinter sont requis. Le runtime de
packaging officiel est Python 3.14. Depuis la racine du clone :

```powershell
python scripts/setup_dev.py
.venv\Scripts\Activate.ps1
python scripts/agent_validate.py
```

Sans activation : `.venv/Scripts/python.exe scripts/agent_validate.py`.

## Installation Linux / Cloud

Avec Python système sur Ubuntu 24.04 :

```bash
sudo apt-get update
sudo apt-get install -y python3-venv python3-tk git
python3 scripts/setup_dev.py
source .venv/bin/activate
python scripts/agent_validate.py
```

Si Python est fourni par un autre gestionnaire, vérifier `python -c "import tkinter"`
avec cet interpréteur. Le paquet système `python3-tk` ne complète pas automatiquement
un Python installé séparément. Aucun secret, `.env`, serveur, migration ou seed requis.

Pour Codex Cloud, choisir Python 3.12, faire préparer et tester ces commandes dans
l'environnement, puis publier sa configuration. Le script d'installation à enregistrer
est `python3 scripts/setup_dev.py` après préparation de Tkinter/venv. Pour les tâches,
utiliser `.venv/bin/python scripts/agent_validate.py`; ne pas supposer que l'activation
effectuée dans une autre session shell persiste. Aucun service n'est à démarrer.

L'installation nécessite l'accès aux dépôts système, à PyPI et à ses wheels.
Les tests et conversions synthétiques fonctionnent ensuite sans réseau. Les mises à
jour publiques consultent GitHub seulement si elles sont demandées; VirusTotal et
les identifiants de publication restent hors du setup Cloud courant.
Republier le setup si les dépendances ou le runtime changent et vérifier une nouvelle tâche.
Voir la [documentation officielle Cloud](https://learn.chatgpt.com/docs/environments/cloud-environments).

## Lancement et configuration

```bash
codamnd --help
codamnd inspect-source samples/employeurd-balanced.txt
codamnd validate samples/employeurd-balanced.txt
codamnd convert samples/employeurd-balanced.txt outputs/exemple.mnd
codamnd parse-mnd outputs/exemple.mnd
codamnd-gui
```

`python convert.py` et `python -m codamnd` sont également des entrées CLI.
La conversion écrit un MND, un rapport Markdown et un JSON; ils restent locaux.
Le PDF GL est facultatif : ajouter `--gl-detail <PDF>` et `--require-gl-detail`
pour exiger un rapprochement réussi. Utiliser seulement des données synthétiques
dans l'environnement Cloud, les tests et les captures partagées.

La priorité de configuration est le dossier explicitement fourni avec `--config-dir`,
puis `config/` du répertoire courant, la configuration du paquet Windows, du clone
source ou de la wheel installée. Les YAML sont lus avec PyYAML, déclaré et verrouillé.
Les clés sont réparties dans `app.yml`, `comptes.yml`, `regles_validation.yml` et `rapports.yml`.

L'application conserve des préférences dans LOCALAPPDATA/CodaMND sur Windows,
XDG_CONFIG_HOME/codamnd ou ~/.config/codamnd sur Linux. Les journaux sont dans
LOCALAPPDATA/CodaMND/logs ou ~/.codamnd/logs; `audit_log.directory` permet un dossier explicite.
La vérification au démarrage est désactivée par défaut dans `config/app.yml`.

## Vérification d'un changement

```bash
python scripts/agent_validate.py
```

Cette commande exécute `pip check`, Ruff (erreurs de syntaxe/variables), mypy,
la suite unittest, la compilation Python de `src/` et `scripts/`, puis l'audit local
de préparation de release. Le typecheck couvre les modèles, erreurs, parsers TXT/MND,
writer et plan de sortie; il ne couvre pas encore toute la GUI ou le parser PDF.
Les tests mêlent unités et intégration, avec des PDF synthétiques temporaires et
des appels GitHub/VirusTotal simulés. Aucun seuil de couverture n'est actuellement imposé.

Commandes ciblées :

```bash
python -m unittest discover -s tests
python -m ruff check src scripts tests convert.py
python -m mypy
python -X pycache_prefix=build/pycache -m compileall src scripts
```

Pour formater un fichier modifié : `python -m ruff format <fichier.py>`.
Ne pas reformater tout le dépôt pour une correction ponctuelle.

Contrôle de lancement GUI sous Windows : `python scripts/smoke_gui.py`.
Sous Linux : installer `xvfb`, puis `xvfb-run -a python scripts/smoke_gui.py`.
Ce contrôle construit la fenêtre et les widgets puis les ferme avec des préférences
temporaires. Il ne remplace pas une vérification manuelle des interactions.

La CI utilise ces commandes sur Windows/Python 3.12 et 3.14 et Linux/Python 3.12,
construit le paquet Windows en 3.14 et recherche les secrets avec Gitleaks.
CodeQL constitue un contrôle séparé. Les protections de branche se configurent sur GitHub.

## Dépendances et build

`requirements-runtime.txt` verrouille l'application et ses dépendances transitives;
`requirements-tools.txt` les outils de validation. `requirements-dev.txt` les installe
avec le projet éditable. `requirements-build.txt` installe le packager Windows dans
`.venv-build`, séparément du profil de revue `.venv`.
Les verrous de revue fixent les versions. La publication utilise séparément
`requirements-release.txt`, avec les empreintes des distributions.

Pour une mise à jour, modifier les bornes concernées dans `pyproject.toml`, résoudre
dans un environnement jetable propre, puis reporter les versions dans le profil
approprié. `python -m pip freeze --exclude codamnd --exclude-editable` aide à inventorier
les versions résolues. Vérifier les trois couples OS/runtime de la CI et `pip check`.

```powershell
python scripts/setup_dev.py --build
.venv-build\Scripts\Activate.ps1
.\scripts\build_exe.ps1
```

Le build lit la version du projet et crée le ZIP dans `dist/`. Pour préparer aussi
empreintes, SBOM et notes : `.\scripts\release.ps1`. Un checkout propre est exigé;
`-AllowDirty` autorise seulement une préparation locale explicitement voulue.
La construction refuse les artefacts précédents dans `dist/`; les archiver avant un nouveau build.

Le paquet Windows utilise le lanceur natif CodaMND, CPython privé et Zig, avec
provenance et empreintes vérifiées. Voir `packaging/windows/native/README.md`.
Le backend de construction et le verrou de publication utilisent setuptools 83.0.0.
`release.ps1` crée un environnement neuf avec les dépendances à empreintes et
valide le véritable paquet portable avant de produire le SBOM. Celui-ci vérifie
l'inventaire des fichiers et distingue les composants embarqués des outils exclus.

La publication reste manuelle. Le workflow exige main, un tag existant sur HEAD,
la version concordante et VirusTotal. `.env.example` sert uniquement à cet usage.
`publish_release.ps1` prépare une nouvelle version; `-CommitVersion` crée également
un tag, `-Push` pousse branche et tag, et `-CreateGitHubRelease` exige ces options
ainsi que `-SubmitVirusTotal`. Ne pas exécuter cette chaîne pour une tâche ordinaire.

## Dépannage et microsite

- `No module named tkinter` : compléter le Python choisi avec Tcl/Tk/Tkinter.
- `no display name` : utiliser un bureau ou Xvfb pour la GUI; les tests ordinaires n'en ont pas besoin.
- `No module named ruff/mypy` : utiliser le Python de `.venv` et relancer le setup.
- Runtime de `.venv` différent : recréer cet environnement après avoir préservé tout fichier utile.
- Configuration introuvable : réinstaller le projet ou passer `--config-dir` explicitement.
- Erreur de dépendance : utiliser le profil prévu et relancer `pip check`.

Le microsite peut être prévisualisé avec `python -m http.server 8000 --directory docs`;
arrêter avec Ctrl+C. Son encart de version consulte GitHub et ses analytics utilisent
GoatCounter. Aucun service externe n'est nécessaire pour servir les fichiers statiques.
`.dockpanel/deploy.sh` copie `docs/` dans `public/`, dossier généré ignoré par Git.
Il ne représente pas une autorisation de déployer sur l'hébergeur.
