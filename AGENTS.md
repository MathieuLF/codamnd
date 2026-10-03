# Guide de contribution automatisée

## Environnement rapide

- Python 3.12 ou plus récent avec Tkinter suffit pour les tests et les revues de code.
- La construction officielle utilise Python 3.14, comme le verrou Windows et le workflow de mise en ligne.
- Aucune base de données, aucun serveur et aucune clé secrète ne sont requis pour la validation courante.
- `VT_API_KEY` sert seulement à une publication officielle avec VirusTotal; ne pas l'exiger pour une revue.
- Les fichiers de test dans `samples/` sont synthétiques. Ne jamais ajouter de fichier de paie réel, rapport GL réel, MND réel ou secret.

```powershell
python scripts/setup_dev.py
.venv\Scripts\Activate.ps1
python scripts/agent_validate.py
```

Sur Linux, installer Tkinter pour l'interpréteur utilisé (`python3-venv python3-tk`
sur Ubuntu avec Python système), puis `source .venv/bin/activate`.
Les tests ordinaires ne nécessitent pas d'affichage; la GUI nécessite un bureau ou Xvfb.
Guide complet : [docs/developpement.md](docs/developpement.md).

## Architecture et points d'entrée

- `src/codamnd/` : parsers TXT/MND, validations, conversion et rapprochement PDF GL.
- `cli.py` : `codamnd` / `python -m codamnd`; `app_gui.py` : `codamnd-gui`.
- `config/` : règles YAML par défaut, également incluses dans la wheel.
- `tests/` et `samples/` : tests et données synthétiques; `docs/` : microsite statique.
- `scripts/` : setup, validation et packaging; voir ses consignes spécifiques.
- Exécuter les commandes du dépôt depuis sa racine. Pour une configuration personnalisée,
  passer `--config-dir`; la CLI installée retrouve sinon les configurations embarquées.

## Validation utile

- Validation complète courte : `python scripts/agent_validate.py`
- Tests seulement : `python -m unittest discover -s tests`
- Compilation seulement : `python -X pycache_prefix=build/pycache -m compileall src scripts`
- Audit release : `python scripts/audit_release_readiness.py --version <version>`
- Lint : `python -m ruff check src scripts tests convert.py`
- Typecheck : `python -m mypy` (modèles, erreurs, parsers TXT/MND, writer et plan de sortie).
- GUI : `python scripts/smoke_gui.py`; Linux : `xvfb-run -a python scripts/smoke_gui.py`.
- `agent_validate.py` ne lance pas de fenêtre, de publication ou de build Windows.

## Invariants et fichiers locaux

- Préserver les montants en `Decimal`, l'équilibre débit/crédit, les largeurs fixes,
  l'encodage cp1252 et les fins de ligne CRLF du MND, ainsi que sa relecture de contrôle.
- Une validation bloquante interdit la création du MND. Le rapprochement PDF est
  facultatif par défaut et bloquant lorsqu'il est explicitement requis.
- Ne pas écraser une sortie existante sans option explicite.
- `build/`, `dist/`, `public/`, `.venv*`, sorties et journaux sont générés et non suivis.
- Préférences : LOCALAPPDATA sur Windows, XDG_CONFIG_HOME/~/.config sur Linux.
  Journaux : LOCALAPPDATA/CodaMND/logs ou ~/.codamnd/logs. Ne pas les joindre à une PR.
- Les fichiers `requirements-*.txt` verrouillent runtime, validation et packaging.
  Les modifier avec `pyproject.toml` et vérifier Windows/Linux; aucun outil de build
  Windows ni secret VirusTotal n'est nécessaire dans l'environnement Cloud courant.

## Règles de contribution

- Garder les textes utilisateurs courts, naturels et en français.
- Le canal public principal est le ZIP portable `CodaMND-v*-portable.zip`.
- Ne pas publier de release, créer de tag, pousser sur `main` ou soumettre à VirusTotal sans demande explicite.
- Les noms de branche ne doivent pas contenir `codex`.
- Pour une revue de code, prioriser les bogues, régressions, risques de publication et tests manquants.

## Profil quotidien de développement

Utiliser `python scripts/agent_validate.py --profile dev` pour la boucle légère après setup. Voir les profils du README pour la couverture exacte. Ce résultat est partiel : sélectionner les intégrations et navigateurs selon les chemins modifiés, puis utiliser les contrôles complets existants pour leur qualification. Les commandes et exigences Full/release restent inchangées. Ne jamais présenter le profil développement comme une certification complète ni lancer une publication automatiquement.
