# Formats des fichiers

Cette page résume la structure attendue par l'application.

## TXT EmployeurD

Une ligne contient 77 caractères, sans compter la fin de ligne.

| Positions | Longueur | Contenu |
| --- | ---: | --- |
| 1-8 | 8 | Numéro de compagnie, utilisé comme lot EmployeurD |
| 9-10 | 2 | Période comptable (PC), alignée à droite : ` 5`, `10`, etc. |
| 11-20 | 10 | Compte GL |
| 21-69 | 49 | Montant |
| 70-77 | 8 | Date, format `AAAAMMJJ` |

Exemple synthétique :

```text
00001234 50213000140                                          2450.0020260618
```

Une période comptable à deux chiffres garde exactement les mêmes positions
(ici PC `15`, compte GL `0213000140`) :

```text
00001234150213000140                                          2450.0020260618
```

La position 9 contient l'espace de remplissage ou le chiffre des dizaines de PC.
Ne pas insérer d'espace dans le fichier : cela décalerait les champs et changerait
sa longueur. Les deux variantes passent les mêmes contrôles de comptes, montants,
dates et d'équilibre, ainsi que la relecture du MND généré.

## MND MégaGest

Une ligne MND produite contient 479 caractères, sans compter la fin de ligne `CRLF`.

| Positions | Longueur | Contenu |
| --- | ---: | --- |
| 1 | 1 | Type, toujours `P` |
| 2-11 | 10 | Compte MND |
| 17-22 | 6 | Période `AAAAMM` |
| 53-62 | 10 | Référence |
| 63-70 | 8 | Date `AAAAMMJJ` |
| 71-120 | 50 | Libellé |
| 236-248 | 13 | Débit |
| 250-262 | 13 | Crédit |
| 264-269 | 6 | Lot MND |
| 274-281 | 8 | Date `AAAAMMJJ` |

Les autres positions sont remplies par des espaces.

## Compte

Pour conserver la compatibilité avec les configurations existantes, le « compte
source » interne de 11 chiffres correspond aux positions 10-20 : unité de PC,
puis compte GL. Par défaut, l'application retire ce premier chiffre. Les mappings
`source_to_mnd` existants restent inchangés. La période MND `AAAAMM` est toujours
dérivée de la date d'écriture, et non de PC.

```text
50213000140 -> 0213000140
```

## Rapports de contrôle

Le rapport recommandé est le PDF original du grand détail de l'écriture GL, tel que généré par EmployeurD. Un PDF scanné, imprimé à nouveau ou modifié peut empêcher la lecture fiable des lignes.

L'application y lit:

- la date d'écriture;
- les lignes de comptes GL;
- le côté débit ou crédit selon la position dans le PDF;
- les sous-totaux;
- le total compagnie.

Le contrôle compare ensuite les totaux débit/crédit et les montants par compte GL avec le TXT EmployeurD, après conversion du compte source de 11 chiffres vers le compte GL/MND de 10 chiffres.

Si le TXT regroupe des mouvements opposés en un solde net par compte, le contrôle
compare les soldes nets du PDF, uniquement si chaque compte concorde. Les
sous-totaux et totaux bruts du PDF restent vérifiés avant ce rapprochement.
Le rapport signale ce mode de comparaison et conserve les totaux bruts du PDF.
