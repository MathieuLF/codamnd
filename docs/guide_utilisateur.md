# Guide rapide

1. Téléchargez la dernière version depuis GitHub.
2. Extrayez le fichier zip.
3. Ouvrez l'application incluse dans le ZIP.
4. Ajoutez l'écriture détaillée EmployeurD au format TXT.
5. Ajoutez le PDF original du grand détail GL au besoin. Il doit venir d'EmployeurD, sans numérisation ni modification.
6. Cliquez sur `Vérifier la paie`.
7. Si tout est conforme, cliquez sur `Créer le MND`.
8. Testez le fichier dans MégaGest hors production avant de l'utiliser réellement.

Sans dossier de sortie choisi, l'application utilise Documents et crée un dossier horodaté.
Vous pouvez aussi saisir une destination avec de nouveaux sous-dossiers; ils seront créés lors de la génération si le dossier parent est accessible en écriture.

## Contrôle GL et fichiers produits

Le PDF GL est facultatif. Dans l’interface, son ajout rend automatiquement la concordance obligatoire : un écart empêche la création du MND. Le bouton `Enlever` retire le PDF et revient à la vérification du TXT seul.

Par défaut, seul le MND est créé. Dans la section `Destination`, vous pouvez aussi cocher :

- `Rapport Markdown (.md)` pour un résumé lisible de la vérification;
- `Validation JSON (.json)` pour les détails structurés.

Ces fichiers restent locaux et peuvent contenir des données de paie. Après la création, `Ouvrir la sortie` ouvre le dossier des fichiers produits; `Voir le résumé` affiche le résultat dans l’application.

Si une écriture échoue après la création d’un fichier, l’application affiche `Création incomplète` et liste les fichiers déjà écrits. Ils sont conservés et restent accessibles par `Ouvrir la sortie`. Corrigez le problème indiqué, puis relancez la vérification avant de générer une nouvelle sortie.

## Raccourcis clavier

| Raccourci | Action |
| --- | --- |
| `Ctrl+O` | Choisir le TXT EmployeurD |
| `Ctrl+G` | Créer le MND après une vérification réussie |
| `F5` | Vérifier la version disponible sur GitHub |

Pendant une vérification ou une génération, les fichiers et la destination restent verrouillés, y compris avec `Ctrl+O`.

## Première ouverture et aide

Au premier lancement, Windows SmartScreen peut afficher un avertissement parce que l'application n'est pas signée numériquement. Si le ZIP vient bien de GitHub Releases, cliquez sur `Informations complémentaires`, puis sur `Exécuter quand même`.

Ne joignez jamais de fichier de paie réel à un billet public.
