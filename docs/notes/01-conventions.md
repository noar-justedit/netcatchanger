# 01 — Conventions de travail et de livraison

## Ce qui change avec Claude Code

Avant (Cowork) : chaque version arrivait sous forme d'un zip
`netcatchanger_X.Y.Z.zip` que Noar décompressait à la main.

Maintenant : **les fichiers du dossier sont modifiés directement**, et le
travail est enregistré dans git. La convention du zip est caduque. Ce qui reste :

- la **note de release**, toujours **en anglais**, produite à chaque version
  publiée ;
- la règle du **go explicite** avant d'agir ;
- la règle du **numéro de version confirmé** avant tout bump.

## Git

- Claude Code **commit** en local, volontiers et souvent : un commit par
  changement cohérent, message court en anglais à l'impératif
  (`Fix elevation fallback when UAC is declined`).
- Claude Code ne **pousse jamais**. `git push` est la décision de Noar.
- Pousser ne déclenche aucun build : le workflow GitHub Actions se lance à la
  main depuis l'onglet **Actions** (`workflow_dispatch`).

## Notes de release

En anglais, dans le corps de la release GitHub. Structure qui a fait ses preuves :

- une phrase d'accroche qui dit ce que la version change pour l'utilisateur ;
- une section par sujet visible, titre parlant, deux ou trois paragraphes ;
- une section « Under the hood » pour ce qui n'est pas visible ;
- une section « Upgrading » qui dit s'il y a quelque chose à faire.

**Écrire la note depuis la dernière version réellement publiée**, pas depuis la
précédente version interne. Si des versions intermédiaires n'ont jamais été
poussées, il faut **réconcilier** les passages qui se contredisent, pas les
empiler. Exemple vécu : la 2.1.0 annonçait « fonctionne sans droits
administrateur », la 2.2.1 fait l'inverse — la note publiée ne décrit que le
comportement final.

## Publication d'une version

1. Bumper les 6 endroits (voir `CLAUDE.md`).
2. Commit.
3. Noar pousse.
4. Il lance le workflow **Build Windows EXE**, récupère les deux artefacts
   (exe portable + installeur).
5. Il teste sur Windows.
6. Il crée la release GitHub avec le tag `vX.Y.Z`, colle la note, joint
   l'installeur.
7. `version.json` étant poussé sur `main`, les installations existantes voient
   la mise à jour au prochain lancement.

⚠ Ne jamais pousser un `version.json` qui annonce une version dont la release
n'existe pas encore : les utilisateurs cliqueraient « Get it » pour rien.
Publier la release **avant** ou en même temps.

## Ton des échanges avec Noar

Pas de flatterie, pas d'acquiescement par défaut. S'il part sur une fausse
piste, le dire clairement avec les éléments à l'appui. Expliquer le principe de
fonctionnement simplement, sans jargon, et signaler les conséquences pratiques :
ce qui peut casser plus tard, ce qui sera difficile à modifier, les limites.
