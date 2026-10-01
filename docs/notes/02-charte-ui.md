# 02 — Charte UI

L'interface reprend le langage visuel d'**ingesto** (tokens « Direction A ·
Sleek »), décision de Noar du 25/08/2026. Maquette de référence validée :
https://claude.ai/code/artifact/471aac5c-3ac3-4d6e-baec-c862549b613d

## Règle de base : tkinter ne connaît pas la transparence

ingesto est en HTML/CSS et utilise des fonds translucides (`rgba(…, .14)`).
tkinter n'a pas de canal alpha. **Toutes les teintes sont donc pré-calculées en
couleurs pleines**, mélangées d'avance sur le fond de carte. Ne jamais essayer
d'écrire une couleur avec transparence : elle sera refusée ou ignorée.

## Couleurs (constantes en haut de `network_switcher.py`)

| Rôle | Constante | Valeur |
|---|---|---|
| Fond fenêtre | `BG` | `#0e0f13` |
| Fond carte | `CARD` | `#121318` |
| Champs, chips neutres | `BG3` | `#16181d` |
| Survol, barres | `BG4` | `#1b1d24` |
| Bordure / bordure forte | `BORDER` / `BORDER2` | `#232428` / `#313236` |
| Texte / secondaire / atténué | `TEXT` / `TEXT2` / `MUTED` | `#e8eaf0` / `#aeb3bd` / `#8b909b` |
| **Profil Privé** | `PRIVATE` | `#8b6ff0` (violet) |
| **Profil Public** | `PUBLIC` | `#f2555a` (rouge) |
| État sain, Domaine | `DOMAIN` | `#35c98b` (vert) |
| DHCP | `BLUE` | `#4d90f0` |
| IP fixe, avertissement | `WARN` | `#f2a03d` (orange) |

Teintes pré-mélangées associées : `PRIVATE_D`/`PRIVATE_BD`, `GREEN_D`/`GREEN_BD`,
`RED_D`/`RED_BD`/`RED_BD2`, `BLUE_D`/`BLUE_BD`, `ORANGE_D`/`ORANGE_BD`.
Le suffixe `_D` = fond teinté, `_BD` = bordure.

## Typographie

- Texte courant : `FONT` = Segoe UI. Valeurs techniques (IP…) : `MONO` = Consolas.
- Titres et logo : `DISPLAY_FAMILY` — **Poppins Bold**, embarquée dans l'exe et
  chargée en privé via GDI (`AddFontResourceExW` avec `FR_PRIVATE`) : rien n'est
  installé sur le système de l'utilisateur. Si le chargement échoue, la
  constante retombe sur Segoe UI, l'app fonctionne quand même.
- Le logo est écrit en trois morceaux : `net` + `cat` (violet) + `changer`.

## Le composant `PillSwitch`

Interrupteur dessiné sur un `Canvas` (tkinter n'a pas de switch natif). Deux
états, chacun avec ses propres couleurs, ce qui permet au même composant de
servir deux usages **sans qu'on puisse les confondre** :

- **Profil réseau** : Public (rouge, à gauche) ⟷ Privé (violet, à droite), avec
  une étiquette de chaque côté, celle de l'état actif colorée.
- **Pare-feu** : OFF (rouge) / ON (vert) — sémantique marche/arrêt classique.

C'est volontaire : deux interrupteurs dans la même fenêtre qui ne veulent pas
dire la même chose, distingués par la couleur. Ne pas uniformiser.

⚠ Rappel du piège : **jamais d'attribut `_w`/`_h`** dans cette classe (voir
`CLAUDE.md`).

## Les « chips »

Petits badges d'information : fond teinté, texte coloré, bordure 1 px. Produits
par `self._chip(parent, texte, couleur_texte, fond, bordure)` et mis à jour par
`self._set_chip(...)`. Utilisés pour : Wi-Fi 6, 5 GHz, DHCP (bleu), STATIC
(orange), GW ✓ (vert/rouge), Internet et DNS dans l'en-tête, statut des cartes
inactives.

## Structure d'une carte d'interface

Tuile d'icône teintée à gauche → nom + description → rangée de chips → barre de
signal Wi-Fi si applicable → rangée d'actions (IP…, Rename, Disable, Renew) →
colonne d'adresses IP à droite → interrupteur de profil tout à droite.

Une carte en `169.254.x.x` (APIPA, pas de réponse DHCP) prend une bordure rouge
et un chip d'alerte : c'est la panne la plus fréquente, elle doit sauter aux yeux.

## Ce qui n'est pas dans la charte

Le logo (`assets/NetCatChanger.svg`) est le dessin de Noar et utilise encore
l'ancien violet `#5936d8` et un rose `#ff0062`. **Volontairement non modifié** —
c'est son identité, pas un token d'interface.
