# NetCatChanger — mémoire de travail

Gestionnaire de profils réseau Windows (Privé / Public / Domaine) + contrôle du
pare-feu. Python 3 / tkinter, **Windows uniquement**. GPL v3.
Dépôt : https://github.com/noar-justedit/netcatchanger

Version actuelle : **2.2.1**

---

## Règles absolues

1. **Rien en dehors de la demande.** Scripts de build, outillage, dépendances,
   organisation des fichiers, comportements par défaut : proposer, expliquer
   l'impact, attendre le « oui » de Noar. Jamais d'initiative silencieuse.
2. **Aucun bump de version sans confirmation explicite du numéro.** Demander,
   attendre la réponse, puis bumper aux **6 endroits** (voir « Bumper une
   version » plus bas).
3. **Ne jamais pousser sur GitHub.** Commits locaux autorisés et souhaités ;
   `git push` est la décision de Noar, il le fait lui-même.
4. **Ne jamais changer l'`AppId` de l'installeur**
   (`{D447AA79-8F4C-4201-AE85-7783961525FE}` dans `installer/installer.iss`).
   C'est lui qui permet à Windows de reconnaître les mises à jour ; le changer
   installerait une deuxième copie à côté de l'ancienne.
5. **Icônes : Lucide uniquement** (licence ISC, compatible GPL). Ne jamais
   réintroduire une icône dont la licence n'est pas traçable. Voir
   `docs/notes/04-icones-licences.md`.
6. **Noar n'est pas développeur.** Expliquer le principe de fonctionnement en
   vocabulaire simple, signaler les conséquences pratiques (ce qui peut casser
   plus tard, ce qui sera difficile à modifier, les limites de la solution).

---

## Contrainte structurante : Mac pour éditer, Windows pour exécuter

Noar travaille sur Mac. L'application est Windows-only (PowerShell, netsh,
pare-feu Windows, UAC). PyInstaller ne sait pas compiler pour Windows depuis un
Mac.

**Faisable sur le Mac :** lire et modifier le code, lancer
`python3 tests/test_parsing.py`, lancer le harnais d'interface avec des données
simulées (voir `docs/notes/03-tests-sans-windows.md`), vérifier la syntaxe des
scripts PowerShell embarqués si `pwsh` est installé.

**Impossible sur le Mac :** produire l'exe ou l'installeur, tester l'élévation
UAC, la tâche planifiée, le systray Windows, le chargement de la police via
GDI, et tout ce qui touche réellement au réseau.

**Donc :** le cycle est *éditer + tester sur Mac → Noar pousse → il lance le
workflow GitHub Actions → il télécharge l'exe et l'installeur → il teste sur
Windows*. Ne jamais annoncer qu'une correction « fonctionne » alors que seule
la partie testable sur Mac a été vérifiée : dire ce qui a été vérifié et ce qui
ne l'a pas été.

---

## Structure

```
netcatchanger/
├── src/
│   ├── network_switcher.py   TOUTE l'application (~2100 lignes, un seul fichier)
│   ├── icons.py              icônes pré-rendues en base64 — JAMAIS éditer à la main
│   ├── gen_icons.py          outil de dev : régénère icons.py depuis les SVG Lucide
│   ├── gen_icon.py           génère assets/app_icon.ico au build
│   ├── version_info.txt      métadonnées de l'exe Windows
│   └── fonts/                Poppins Bold (SIL OFL), embarquée dans l'exe
├── installer/installer.iss   script Inno Setup (installeur Windows)
├── assets/
│   ├── NetCatChanger.svg     logo, dessin de Noar
│   ├── lucide/               SVG sources Lucide, intacts (ISC)
│   ├── app_icon.ico
│   └── screenshot.png        ⚠ date d'avant le restyle 2.2.0, à refaire
├── scripts/
│   ├── build_windows.bat     build exe + installeur (à lancer SUR Windows)
│   ├── run_as_admin.bat      lancer sans builder
│   └── debug.bat             lancer avec la console visible
├── tests/test_parsing.py     tests hors ligne, tournent sur tout OS
├── .github/workflows/build-windows.yml   build cloud (exe + installeur)
├── version.json              lu par la vérification de mise à jour
├── LICENSE                   GPL v3
├── LICENSE-lucide.txt        ISC + table des icônes utilisées
└── docs/notes/               notes de référence (lire avant de toucher au domaine)
```

---

## Architecture en trois phrases

Toute l'application tient dans `src/network_switcher.py`. Elle interroge
Windows en lançant **PowerShell** : un gros script (`_BATCH_SCRIPT`) récupère
en un seul appel l'état de toutes les cartes réseau, et un second script
(`_WATCH_SCRIPT`) tourne en permanence dans un processus unique et signale les
changements. Les modifications (adresse IP, renommage, tâche planifiée) passent
par `netsh`, `ipconfig` et `schtasks` appelés avec une **liste d'arguments**
(fonction `run_cmd`), jamais une ligne de commande concaténée — c'est ce qui
rend l'app insensible aux noms d'interface contenant espaces ou apostrophes.

---

## Pièges connus — déjà payés une fois

- **Jamais d'attribut `_w` ou `_h` dans une sous-classe de widget tkinter.**
  tkinter utilise `self._w` en interne pour le nom Tcl du widget. Le `PillSwitch`
  y stockait sa largeur : l'exe se lançait et mourait sans message (mode
  `--windowed` = aucune console). Les attributs s'appellent `_sw_w` / `_sw_h`.
- **Le succès d'une commande PowerShell se lit sur le code de sortie, pas sur
  stderr.** PowerShell écrit aussi ses avertissements sur stderr. Utiliser
  `run_ps_action()`, qui enveloppe la commande dans un try/catch et renvoie
  `(ok, message)`.
- **Les libellés de `netsh` sont traduits.** « Radio type » devient « Type de
  radio » en français. Le parseur reconnaît les valeurs par leur **forme**
  (`92%`, `802.11ax`, `5 GHz`), jamais par le libellé. Ne pas « simplifier » en
  revenant à des libellés anglais.
- **Une entrée de registre `Run` ne peut pas lancer une application qui exige
  les droits admin.** Le démarrage avec Windows passe par une tâche planifiée
  (`schtasks /RL HIGHEST`).
- **L'élévation ne doit pas dépendre du seul manifeste de l'exe.** L'app la
  demande elle-même au lancement (`should_elevate()` + `run_as_admin()`), avec
  le drapeau `--no-elevate` sur la copie relancée pour éviter une boucle infinie.
- **tkinter ne connaît pas la transparence.** Toutes les teintes de la charte
  sont pré-calculées en couleurs pleines. Ne jamais écrire une couleur `rgba`.

---

## Bumper une version (après confirmation du numéro par Noar)

Six endroits, tous à mettre à jour ensemble :

1. `src/network_switcher.py` → `APP_VERSION`
2. `src/version_info.txt` → `filevers`, `prodvers`, `FileVersion`, `ProductVersion`
3. `installer/installer.iss` → `#define MyAppVersion`
4. `scripts/build_windows.bat` → le titre, l'en-tête et les noms de l'installeur
5. `version.json` → `version` (c'est ce fichier, une fois poussé, qui déclenche
   la notification de mise à jour chez les utilisateurs)
6. La note de release (en anglais, voir `docs/notes/01-conventions.md`)

Vérification : `grep -rn "<ancienne version>" --include="*.py" --include="*.bat"
--include="*.txt" --include="*.json" --include="*.iss" .` ne doit plus rien
renvoyer (hors `LICENSE-lucide.txt`).

---

## Avant de dire qu'une modification est bonne

1. `python3 tests/test_parsing.py` → doit afficher `all parsing checks passed`.
2. Si l'interface est touchée : lancer le harnais et **regarder la fenêtre**
   (`docs/notes/03-tests-sans-windows.md`).
3. Si un script PowerShell embarqué est touché : vérifier sa syntaxe.
4. Dire explicitement ce qui n'a pas pu être vérifié faute de Windows.

---

## Notes de référence

| Fichier | Quand le lire |
|---|---|
| `docs/notes/01-conventions.md` | livraison, notes de release, git |
| `docs/notes/02-charte-ui.md` | toute modification visuelle |
| `docs/notes/03-tests-sans-windows.md` | avant de tester quoi que ce soit |
| `docs/notes/04-icones-licences.md` | icônes, polices, conformité |
| `docs/notes/05-build-installeur.md` | build, installeur, droits admin |
| `docs/notes/06-historique.md` | contexte d'une décision, points ouverts |
