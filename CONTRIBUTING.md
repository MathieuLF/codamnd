# Contribuer

Les contributions sont les bienvenues, avec une règle simple : aucune donnée de paie réelle ne doit se retrouver dans le dépôt ou dans une demande publique.

## Données d'exemple

Utilisez seulement des données synthétiques dans les fichiers partagés, les captures d'écran et les billets GitHub.

Il est possible de tester l'application localement avec ses propres fichiers, mais ces fichiers doivent rester sur votre poste.

## Avant de proposer un changement

```powershell
python scripts/setup_dev.py
.venv\Scripts\Activate.ps1
python scripts/agent_validate.py
```

Ces commandes ne demandent ni base de données, ni serveur, ni clé secrète. `VT_API_KEY` sert seulement à une publication officielle.

Sur Linux : installer Tkinter pour le Python choisi, puis utiliser
`source .venv/bin/activate`. Voir le [guide développeur](docs/developpement.md).
La CI exécute la même validation sous Linux/Python 3.12 et Windows/Python 3.12 et 3.14.

Les versions transitives sont verrouillées dans `requirements-runtime.txt`,
`requirements-tools.txt`, `requirements-dev.txt` et `requirements-build.txt`.
Une mise à jour de dépendance doit synchroniser ces fichiers et `pyproject.toml`,
puis passer la validation sur les deux systèmes. Ne pas régénérer un verrou depuis
un environnement global contenant des paquets sans rapport avec le projet.

## À garder en tête

- Le MND ne doit pas être créé si une validation bloquante échoue.
- Le PDF original du grand détail GL est le rapport de contrôle attendu.
- Les textes visibles par les utilisateurs doivent rester courts et naturels.
