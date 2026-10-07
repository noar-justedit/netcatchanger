# Règles de travail pour l'IA : NetCatChanger

Ces règles valent pour toute IA qui reprend ce projet (Claude ou une autre).
Lire ensuite `ETAT_PROJET.md` : état actuel, décisions, prochaines étapes.

## Contexte

- Noar est monteur et technicien vidéo, **pas développeur**. Il travaille sur
  Mac, mais **builde NetCatChanger sur son PC Windows** (SERVAL).
- NetCatChanger est une application **Windows uniquement** : elle pilote
  PowerShell, `netsh`, le pare-feu Windows. Pas de version Mac ni Linux.
- Il publie lui-même sur GitHub : le code à partir du ZIP fourni, les builds
  dans les Releases.

## 1. Périmètre : rien en dehors de la demande

- Ne modifier que ce qui est demandé.
- Pour tout le reste (outillage, scripts de build, dépendances, organisation
  des fichiers, comportements par défaut) : proposer, expliquer l'impact,
  attendre un « oui » explicite. Jamais d'initiative silencieuse.

## 2. Communication

- Répondre en français, simplement, sans jargon. Pas de tiret cadratin (—).
- Expliquer en quelques phrases ce que fait le code et pourquoi cette méthode.
- Signaler les conséquences concrètes : ce qui peut casser, ce qui sera
  difficile à modifier, les limites, les impacts coût / sécurité /
  maintenance / performances.
- Pas de flatterie. Si Noar se trompe, le dire et expliquer pourquoi.
- Ne jamais dire qu'une correction « fonctionne » quand seule la partie
  testable hors Windows a été vérifiée : dire ce qui a été vérifié et ce qui
  ne l'a pas été.

## 3. Builds

- `scripts/build_windows.cmd`, double-cliqué **sur Windows**, produit
  `dist/NetCatChanger-Setup-<version>.exe`. Il demande Node.js LTS.
- Décision de Noar (10.2026) : pas de script de build Mac pour ce projet.

## 4. Versions

- Aucun bump sans que Noar ait confirmé explicitement le numéro.
- Procédure : proposer un numéro, attendre la confirmation, mettre à jour tous
  les emplacements listés dans `ETAT_PROJET.md` (« Emplacements de la
  version »), puis vérifier qu'aucun n'a été oublié. Format X.Y.Z.

## 5. Livraison : le ZIP

- À chaque bump, fournir `NetCatChanger_vX.Y.Z.zip`. Décompressé, il est
  exactement ce que Noar pousse sur GitHub.
- Il ne contient ni builds (Releases), ni `node_modules/`, ni `dist/`, ni
  aucun secret.
- Il suffit à lui seul pour reprendre le développement.

## 6. Fichiers de suivi (à jour à chaque bump)

`README.md`, `AGENTS.md` (ce fichier), `CLAUDE.md` (renvoie ici),
`ETAT_PROJET.md`, `CHANGELOG.md`.

## 7. Publication : `scripts/push_github.cmd` (Windows)

Noar décompresse le ZIP **sur son PC Windows** et double-clique
`scripts/push_github.cmd` (qui lance `push_github.ps1`) : GitHub devient
exactement le contenu du dossier. Copie temporaire du dépôt, liste des
changements, confirmation « y », jamais d'envoi forcé, refus si la version
n'est pas strictement supérieure à celle de GitHub ou si `version.json` et
`package.json` diffèrent. `version.json` part en dernier (après la Release et
son installeur). Le script doit rester en ASCII (PowerShell 5.1). **Ne jamais
pousser soi-même** : c'est la décision de Noar.

## 8. Règles propres à NetCatChanger

- **Icônes : Lucide uniquement** (licence ISC, compatible GPL v3), copiées
  telles quelles. Sources dans `assets/lucide/`, table dans
  `LICENSE-lucide.txt`, vérification automatique dans `test/run-tests.js`.
- **Charte UI commune** des applis de Noar (`charte-ui-noar.md`, posée sur
  ingesto 2.7.0) : trois surfaces, aucun filet, l'accent (rose) pour le logo
  seul. Écarts voulus par Noar : bleu pour ce qui est choisi ; badges gris
  par défaut, verts quand ça fonctionne, rouges quand ça ne fonctionne pas ;
  icône verte pour une carte connectée ; ni orange ni violet (des tests le
  vérifient).
- **Sécurité** : l'appli tourne en administrateur.
  - Aucune valeur saisie (nom de carte, adresse) n'est collée dans le texte
    d'un script PowerShell : elle passe par une variable d'environnement.
  - Les programmes sont appelés par leur chemin complet dans System32, avec
    une liste d'arguments, jamais une ligne de commande concaténée.
  - La fenêtre n'affiche jamais de contenu distant, ne navigue jamais
    ailleurs, n'utilise jamais `innerHTML` pour un texte venu de la machine.
  - `preload.js` est la liste fermée des actions offertes à la fenêtre.
- **Pièges déjà payés** (hérités de la 2.x) :
  - Les libellés de `netsh` sont traduits (« Type de radio »). Le parseur
    reconnaît les valeurs par leur forme (`92%`, `802.11ax`, `5 GHz`), jamais
    par le libellé.
  - Le succès d'une commande PowerShell se lit sur le code de sortie, pas sur
    stderr (`runPsAction`).
  - `netsh` écrit dans la page de code de la console : capturer sa sortie
    AVANT de passer la sortie PowerShell en UTF-8 (`interfaces.ps1`).
  - PowerShell transforme une liste d'un seul élément en objet seul : le code
    Node accepte les deux.
