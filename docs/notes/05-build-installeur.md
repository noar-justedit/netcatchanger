# 05 — Build, installeur, droits administrateur

## Les deux façons de produire l'application

**Sur une machine Windows** (Python 3.8+ installé, « Add to PATH » coché) :
double-cliquer `scripts\build_windows.bat`. Le script installe ce qu'il faut
via pip, génère l'icône, compile l'exe avec PyInstaller, puis compile
l'installeur **si Inno Setup 6 est présent** (https://jrsoftware.org/isinfo.php).
Sans Inno Setup il affiche un message et produit seulement l'exe portable.

**Sans machine Windows** : onglet **Actions** du dépôt GitHub → workflow
*Build Windows EXE* → *Run workflow*. Il tourne sur un vrai Windows, produit
l'exe **et** l'installeur (Inno Setup y est préinstallé) et les publie en deux
artefacts téléchargeables. **C'est la seule voie depuis le Mac** : PyInstaller
ne sait pas compiler pour Windows depuis macOS, et il n'existe pas de
contournement raisonnable.

Le workflow se déclenche à la main (`workflow_dispatch`) — pousser du code ne
lance rien tout seul.

## Ce que fait la ligne PyInstaller

```
--onefile              un seul .exe, rien à installer à côté
--windowed             pas de fenêtre console
--uac-admin            demande les droits administrateur au lancement
--icon / --version-file  icône et métadonnées (nom, version, copyright)
--collect-submodules pystray   embarque la bibliothèque du systray
--add-data icons.py / fonts/Poppins-Bold.ttf   embarque icônes et police
```

Si un jour l'exe démarre sans icône de systray ou sans police, c'est presque
toujours un `--add-data` ou un `--collect-submodules` manquant.

## L'installeur (`installer/installer.iss`)

Inno Setup. Produit `NetCatChanger-Setup-X.Y.Z.exe` : installation dans Program
Files, entrée au menu Démarrer, icône de bureau optionnelle, page de licence
GPL, désinstalleur propre, interfaces anglaise et française.

Deux choix délibérés :

- **Les réglages survivent à la désinstallation.** `%APPDATA%\NetCatChanger`
  (préférences, presets IP, journal) n'est pas supprimé : réinstaller ne fait
  pas perdre ses presets.
- **`AppId` fixe** : `{D447AA79-8F4C-4201-AE85-7783961525FE}`. C'est
  l'identifiant par lequel Windows reconnaît qu'une nouvelle version remplace
  l'ancienne. **Le changer installerait une deuxième copie à côté de la
  première.** Il ne doit jamais bouger, quelle que soit la version.

## Les droits administrateur — comment ça marche

L'application ne peut rien faire sans droits administrateur : changer un profil
réseau, toucher au pare-feu, poser une adresse IP, tout l'exige.

**Deux ceintures, volontairement.** L'exe porte un manifeste
`requireAdministrator` (le `--uac-admin`), *et* l'application redemande
l'élévation elle-même au lancement (`should_elevate()` puis `run_as_admin()`).
Le manifeste seul ne suffit pas : il disparaît quand on lance le script Python
directement, et il peut être perdu au repackaging. C'est exactement le bug de la
2.2.0 — l'app démarrait en lecture seule sans rien dire.

**Le garde anti-boucle.** La copie relancée reçoit le drapeau `--no-elevate`.
Sans lui, une machine où la détection d'administrateur échoue relancerait
l'application à l'infini.

**Si l'utilisateur refuse l'UAC**, l'application ne disparaît pas et ne fait pas
semblant de fonctionner : elle démarre en lecture seule, avec une barre orange
pleine largeur qui l'explique et propose de relancer en administrateur.
`run_as_admin()` renvoie vrai ou faux selon le code de retour de
`ShellExecuteW` (> 32 = accepté) — c'est ce qui permet de distinguer « refusé »
de « lancé ».

## Le démarrage avec Windows

**Une entrée de registre `Run` ne peut pas lancer une application qui exige les
droits administrateur** : Windows l'ignore, ou réclame l'UAC à chaque ouverture
de session. C'était le cas jusqu'en 2.2.0 — l'option ne marchait tout
simplement pas.

Depuis 2.2.1 : une **tâche planifiée** créée avec
`schtasks /Create /RL HIGHEST /SC ONLOGON`, qui démarre l'application élevée et
sans fenêtre au login. L'ancienne entrée de registre est supprimée
automatiquement à la mise à jour. Créer la tâche exige elle-même les droits
administrateur — la case est refusée en mode lecture seule, avec un message.

## Signature de code

L'exe n'est pas signé. Conséquence : SmartScreen affiche un avertissement
« Éditeur inconnu » au premier lancement chez un nouvel utilisateur, qui doit
cliquer « Informations complémentaires » puis « Exécuter quand même ». Un
certificat de signature de code se loue à l'année. Décision de Noar, non prise
à ce jour.
