# 04 — Icônes, polices, conformité de licence

## Pourquoi cette note existe

En août 2026, les icônes de l'application venaient d'un jeu inconnu : exports
Illustrator en viewBox 800×800, métadonnées effacées, **aucune attribution nulle
part**, aucune trace de licence. Les indices (points de contrôle à zéros
doublés, grille 24 px, trait 2 px) pointaient vers **Untitled UI**, dont la
licence **interdit la redistribution des fichiers d'icônes** — incompatible avec
un dépôt public sous GPL v3, qui exige que tout ce qui est distribué le soit
sous des termes compatibles.

Elles ont été remplacées en 2.2.1. **La règle qui en découle : aucune icône
n'entre dans ce projet sans licence traçable.**

## Ce qui est utilisé aujourd'hui

**Lucide** (https://lucide.dev), licence **ISC** — compatible GPL, n'exige que
la conservation de la mention de copyright. Version 1.34.0, récupérée depuis le
paquet npm `lucide-static` (pas redessinée de mémoire, pas récupérée d'un site
tiers).

| Icône Lucide | Usage | Clés dans `icons.py` |
|---|---|---|
| `wifi` | cartes sans fil | `wifi_private`, `wifi_public`, `wifi_domain`, `wifi_muted` |
| `network` | cartes filaires | `wired_*` (mêmes quatre) |
| `shield-check` | pare-feu actif | `fw_on` |
| `shield-off` | pare-feu désactivé | `fw_off` |

Seules la **couleur du trait** et la **taille de rendu** sont modifiées. La
géométrie est intacte.

**Poppins Bold**, licence **SIL Open Font License 1.1**, embarquée dans l'exe
pour le logo et les titres.

**Le logo NetCatChanger** est le dessin de Noar, couvert par la GPL du projet
comme le reste.

## Où vivent les mentions

Toutes ces mentions sont obligatoires et doivent **voyager avec les binaires**,
pas seulement avec le dépôt :

- `LICENSE-lucide.txt` (racine) — texte ISC + table des icônes utilisées
- `assets/lucide/` — les SVG sources intacts, avec leur en-tête de licence
- `README.md` — section « Third-party components »
- La fenêtre **About** de l'application
- L'installeur : `installer.iss` copie `LICENSE-lucide.txt` et `Poppins-OFL.txt`
  dans le dossier d'installation

Si on ajoute une icône, il faut mettre à jour **les cinq**.

## Régénérer les icônes

`src/icons.py` contient les icônes en base64. **Il ne s'édite jamais à la
main** : on le régénère.

```bash
pip install cairosvg
npm install lucide-static
python3 src/gen_icons.py node_modules/lucide-static/icons
```

Le script prend les SVG, applique les couleurs de la charte (`COLORS` en haut du
fichier), rend en PNG aux bonnes tailles (40 px pour les interfaces, 36 px pour
le pare-feu) et réécrit `icons.py`. L'entrée `logo` est recopiée telle quelle.

Conséquence pratique : changer la palette ou remplacer une icône est devenu une
opération d'une minute. Avant, il fallait éditer du base64 à la main.

⚠ `node_modules/` et `package.json` sont dans `.gitignore` — ce sont des outils
de développement, ils n'ont pas à être versionnés.

## Ajouter une icône Lucide

1. Choisir le nom sur https://lucide.dev
2. `cp node_modules/lucide-static/icons/<nom>.svg assets/lucide/`
3. Ajouter l'entrée dans `ICON_SOURCE` de `src/gen_icons.py`
4. Régénérer
5. Mettre à jour la table dans `LICENSE-lucide.txt`

## Ce qui reste à faire un jour

`assets/screenshot.png` (utilisée dans le README) date d'avant la refonte
visuelle 2.2.0 : elle montre les anciennes icônes et l'ancienne interface. À
refaire par Noar depuis l'application réelle sur Windows — une capture prise
avec le harnais de test contiendrait des données inventées.
