# 06 — Historique et points ouverts

## Versions

### 2.0.1 — état initial
Profils Privé / Public / Domaine par interface, pare-feu marche-arrêt global,
surveillance toutes les 3 secondes, informations Wi-Fi.

### 2.0.2 — correctifs (24/08/2026)
- **Parsing `netsh` par forme de valeur.** Le code cherchait les libellés
  anglais ; sur un Windows français, le standard Wi-Fi, la bande et le canal
  restaient vides en permanence. Le parseur reconnaît maintenant `92%`,
  `802.11ax`, `5 GHz` quelle que soit la langue.
- **Succès des commandes par code de sortie**, plus par « stderr vide » : un
  simple avertissement PowerShell était compté comme un échec, et certains
  échecs passaient pour des succès.
- **Watcher en un seul processus PowerShell persistant** au lieu d'en relancer
  un toutes les 3 secondes.
- Métadonnées de l'exe (`--version-file`), `LICENSE` GPL v3 ajouté (il manquait
  alors que le README le référençait), `tests/test_parsing.py` créé.

### 2.1.0 — grosse évolution fonctionnelle (24/08/2026)
Systray, presets IP avec retour arrière automatique à 15 secondes, désactivation
temporisée du pare-feu par profil actif, mode lecture seule sans administrateur,
diagnostics (passerelle / DNS / internet / APIPA), toutes les cartes réseau
visibles y compris débranchées et désactivées, renommage et activation des
cartes, vidage DNS et renouvellement de bail, préférences et journal dans
`%APPDATA%`, notification annulable au lieu d'une confirmation bloquante,
vérification de mise à jour, netteté HiDPI, démarrage avec Windows.

### 2.2.0 — refonte visuelle + installeur (25-26/08/2026) — **jamais publiée**
Reprise du langage visuel d'ingesto, interrupteur étiqueté pour le profil,
installeur Inno Setup. Deux bugs bloquants trouvés avant publication :

- **L'exe ne se lançait pas.** `PillSwitch` stockait sa largeur dans `self._w`,
  attribut interne de tkinter. Erreur Tcl à la construction, invisible en mode
  `--windowed`. → `_sw_w` / `_sw_h`.
- **L'application ne démarrait pas en administrateur.** Le point d'entrée ne
  demandait plus l'élévation depuis la 2.1.0 et comptait sur le seul manifeste.
  → auto-élévation + garde anti-boucle + barre de lecture seule + autostart par
  tâche planifiée.

### 2.2.1 — conformité de licence (26/08/2026)
Déclenchée par une question de Noar : « les icônes sont-elles bien des Lucide ? »
Elles ne l'étaient pas. Remplacement par les vraies icônes Lucide, mentions de
licence ajoutées partout, `src/gen_icons.py` créé, `icons.py` passé de 85 à
16 Ko (il transportait encore 24 images d'une animation morte). Voir
`04-icones-licences.md`.

---

## Points ouverts

1. **Jamais testé sur Windows réel** (au moment de la bascule) : le rendu de
   Poppins via GDI, l'installeur Inno Setup, la tâche planifiée d'autostart.
   → à valider dès le premier build.
2. **`assets/screenshot.png` est périmée** — elle montre l'interface d'avant la
   refonte 2.2.0. À refaire depuis l'application réelle.
3. **Le logo utilise encore l'ancienne palette** (violet `#5936d8`, rose
   `#ff0062`) au lieu des couleurs ingesto. Volontairement non modifié : c'est
   le dessin de Noar, à lui de décider.
4. **Pas de signature de code** — avertissement SmartScreen au premier
   lancement. Voir `05-build-installeur.md`.
5. **État du dépôt GitHub à vérifier.** Le dépôt contient des commits
   « Delete … » de l'ancienne organisation, et le workflow `.github/` n'y avait
   jamais été poussé au moment des livraisons par zip. À contrôler et remettre
   d'aplomb maintenant que git est utilisé normalement.
6. **Le workflow GitHub Actions n'a peut-être jamais tourné.** À lancer une
   première fois pour vérifier qu'il produit bien les deux artefacts.
7. **Pistes fonctionnelles proposées et non retenues** (août 2026) : raccourci
   clavier global pour basculer le profil de l'interface active ; mesure du
   débit réel de la liaison. Tout le reste du backlog d'alors a été livré.

---

## Contexte utile

- Maquette de référence de la refonte 2.2.0 :
  https://claude.ai/code/artifact/471aac5c-3ac3-4d6e-baec-c862549b613d
- L'application sœur **ingesto** est la source du langage visuel. En cas de
  doute sur une couleur ou un composant, c'est la référence.
- Les notes de suivi antérieures vivent dans le projet Claude « CODING »
  (`claude/netcatchanger-suivi.md`). Elles ne suivent pas sur le Mac : à partir
  de la bascule, ce dossier `docs/notes/` est la seule mémoire du projet.
