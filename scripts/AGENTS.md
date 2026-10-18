# Scripts de développement et de publication

Appliquer aussi les consignes du `AGENTS.md` racine.

- `setup_dev.py` prépare `.venv` avec les verrous; `--build` prépare séparément
  `.venv-build` pour les contrôles du build Windows. La publication utilise son propre environnement avec le verrou à empreintes.
- `agent_validate.py` est la validation courante. Le scan de secrets intégré est ciblé;
  la CI le complète avec Gitleaks sur l'historique disponible.
- `smoke_gui.py` ouvre et ferme Tkinter avec des préférences temporaires.
- `build_exe.ps1` conserve les artefacts précédents et refuse un `dist/` déjà occupé.
  La version doit correspondre au projet.
- `release.ps1` prépare les artefacts locaux sans publier ni soumettre à VirusTotal.
- `prepare_release.py --write` modifie les versions et le changelog; `--dry-run`
  n'en modifie aucun, mais ses options de sortie peuvent créer des fichiers.
- `publish_release.ps1` modifie les sources même sans publication. `-CommitVersion`
  crée aussi un tag; `-Push` envoie branche et tag. Ces effets exigent une demande explicite.
- Ne pas exécuter de publication, push sur main, création de tag, déploiement ou
  soumission VirusTotal sans instruction explicite. Une tâche de préparation Cloud
  autorise les patches et validations locales, pas ces opérations externes.
- VirusTotal reçoit seulement l'exécutable public. Garder les données de paie et secrets locaux.
- Le workflow manuel exige un tag existant correspondant à la version et à HEAD.
  Ne pas contourner `check_release_tag.py`, les empreintes ou les contrôles VirusTotal.
- Le SBOM vérifie le verrou et les empreintes de l’inventaire natif, et distingue les
  dépendances embarquées des outils exclus. Préserver ces contrôles.
