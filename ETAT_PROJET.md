# NetCatChanger : état du projet

Mis à jour le 07.10.2026.

## En une phrase

Gestionnaire de profils réseau Windows (Privé / Public / Domaine), de
configuration IP, du pare-feu et de la sortie VPN WireGuard. **Version 3.0.0**
(réécriture Electron de la 2.2.1 Python / tkinter), **validée par Noar sur
SERVAL le 07.10.2026**, publication sur GitHub en cours.

## Où en est la 3.0

| Étape | Contenu | État |
|---|---|---|
| 1 | Squelette Electron, charte UI, `build_windows.cmd` | fait, build validé sur SERVAL |
| 2 | Lecture : cartes réseau, pare-feu, passerelles | fait, validé sur SERVAL |
| 3 | Actions : profil Privé/Public (avec Annuler), activer/désactiver, renommer, renouveler DHCP, vider le DNS, pare-feu ON/OFF | fait, validé sur SERVAL |
| 4 | Fenêtres : IP settings (préréglages, retour automatique en 15 s), réglages + À propos, avis de mise à jour | fait, validé sur SERVAL |
| 5 | Sortie VPN (WireGuard forcé sur une carte choisie) | fait, validé sur SERVAL |
| 6 | Installeur (migration 2.x), `README.md`, `CHANGELOG.md`, `scripts/push_github.cmd` | fait, validé sur SERVAL |

## Architecture en bref

```
src/main/main.js        fenêtre, sécurité (CSP, navigation bloquée), liste IPC,
                        journal VPN, retour IP en attente à la fermeture, mise à jour
src/main/preload.js     la seule porte entre la fenêtre et la machine
src/main/ps.js          lance PowerShell / netsh / ipconfig / ping (chemins System32,
                        listes d'arguments, valeurs par variables d'environnement)
src/main/ps/*.ps1       interfaces (lecture), watch (surveillance), wireguard (tunnels)
src/main/netdata.js     lecture de l'état réseau + surveillance tant que la fenêtre vit
src/main/actions.js     ce qui modifie la machine (profil, carte, IP, DNS, pare-feu)
src/main/vpn.js         sortie VPN : priorité / désactivation, tunnels WireGuard
src/main/netinfo.js     fonctions pures (parseurs, logique VPN), couvertes par les tests
src/main/store.js       config.json et session.log dans %APPDATA%\NetCatChanger
src/renderer/           index.html, style.css (charte), app.js
test/run-tests.js       npm test (186 vérifications)
scripts/build_windows.cmd    build de l'installeur, à lancer sur Windows
scripts/fetch-electron.js    télécharge Electron une fois (curl, reprise, SHA-256)
scripts/push_github.cmd/.ps1 publication sur GitHub, depuis Windows (décision de Noar)
docs/screenshots/       captures du README (rendues avec des données simulées)
docs/RELEASE-3.0.0.md   texte de la Release GitHub 3.0.0
build-resources/installer.nsh  migration depuis la 2.x (Inno Setup)
```

Principe : `interfaces.ps1` lit toutes les cartes en un seul appel et renvoie
le texte brut de `netsh wlan` ; c'est Node (`netinfo.js`) qui l'interprète.
Le code testé est donc exactement le code livré.

## Décisions prises (et pourquoi)

- **Electron plutôt que tkinter** (10.2026) : charte UI commune appliquée
  telle quelle, une seule famille technique. Coût accepté : environ 100 Mo
  d'installeur, 250 Mo installé, 150 à 250 Mo de mémoire fenêtre ouverte.
- **Rien de résident** : on ouvre, on change un réglage, on quitte. Plus de
  systray, de démarrage avec Windows ni de démarrage minimisé.
- **Pare-feu** : plus de coupure temporaire (option « c » de Noar). La
  coupure propose « profils actifs seulement » ou « tous les profils ».
- **Droits administrateur exigés** au lancement (`requireAdministrator`).
- **Build sur Windows uniquement**, pas de script Mac (décision de Noar).
- **Couleurs** (Noar, 10.2026) : le rose `#ff0062` pour « cat » dans le
  logo seulement. Dans la fenêtre : **bleu** pour ce qui est choisi (profil
  actuel, badge VPN, interrupteurs) ; badges **gris** par défaut, **verts**
  quand ce qu'ils nomment fonctionne (INTERNET, vitesse de lien, norme et
  bande Wi-Fi, DHCP, GATEWAY qui répond, TUNNEL actif), **rouges** quand ça
  ne fonctionne pas (CABLE UNPLUGGED, NO NETWORK PROFILE, 169.254, GATEWAY
  muet) ; ADAPTER DISABLED et STATIC restent gris (choix, pas panne). Icône
  d'une carte connectée verte, débranchée rouge. Ni orange ni violet.
  Vérifié par des tests.
- **Renommer** : clic droit sur le nom de la carte, puis « Rename… » (ou la
  touche Menu quand le nom a le focus). Plus de bouton Rename.
- **Renouveler le bail DHCP** : dans la fenêtre IP settings (carte en DHCP et
  connectée). Plus de bouton Renew sur la carte.
- **Mise en page** (Noar) : cartes réseau en haut, sortie VPN puis pare-feu
  en bas ; adresses IP en 14 px ; Public / Private en deux badges ; une seule
  action visible par carte (« IP settings ») ; plus de
  voyants INTERNET / DNS globaux mais un badge INTERNET par carte.
- **Badge INTERNET** : verdict de Windows (`IPv4Connectivity` /
  `IPv6Connectivity`, le test HTTP de l'icône réseau de la barre des tâches),
  pas un ping. Windows met quelques secondes à le réviser.
- **Passerelle** : ping compté réussi seulement si la réponse contient `TTL=`.
- **Cartes désignées par leur GUID**, retrouvées par comparaison exacte ;
  jamais `-Name` / `-InterfaceAlias` (jokers `[ ] * ?`). La fenêtre ne peut
  agir que sur une carte de la dernière lecture. Une action à la fois.
- **IP settings** : comme la 2.x (DHCP ou fixe, préréglages au même format
  dans `config.json`, retour automatique en 15 s sans confirmation). Ajouts :
  masque vérifié (bits contigus) ; un changement à moitié appliqué est défait
  aussitôt ; un changement encore en attente est défait si l'appli se ferme.
  La fenêtre « Keep these settings? » ne se ferme pas avec Échap (décision en
  cours, charte).
- **Mise à jour** : `version.json` lu sur GitHub au lancement par la pile
  réseau de Chromium (`net.fetch`, proxy système) ; seule la page des
  Releases du dépôt peut être ouverte ; jamais deux fois pour une version.
- **Sortie VPN** :
  - WireGuard for Windows prend la route par défaut de plus petite
    `RouteMetric + InterfaceMetric` parmi les autres cartes et y attache sa
    connexion (d'où le désaccord possible avec `Find-NetRoute`, et l'inutilité
    d'une route vers le serveur). L'appli calcule ce choix et l'affiche.
  - Méthode recommandée : seule la carte mise de côté change, priorité 9000
    en IPv4 et IPv6, dans le magasin **actif** seulement (`-PolicyStore
    ActiveStore`) : un redémarrage de Windows remet la priorité d'origine.
    La carte préférée n'est pas touchée, donc le tunnel garde sa priorité.
  - Interface simplifiée pour des non-spécialistes (Noar, 10.2026) : la
    section « VPN » n'apparaît que si un tunnel WireGuard tourne (ou si le
    mode est actif). Une phrase dit par quelle connexion passe le VPN et si
    le serveur répond ; si rien ne répond, un bouton « Use <connexion> »
    l'envoie par une autre connexion, puis le VPN est reconnecté
    automatiquement ; ensuite « Back to normal ». Plus d'interrupteur, de
    bouton Configure ni de choix de méthode : toujours la méthode par
    priorité, la carte mise de côté étant celle que WireGuard utilise à ce
    moment. La désactivation de carte reste dans `vpn.js` (journaux anciens)
    mais n'est plus proposée.
  - Le mode survit à la fermeture de l'appli (Noar). Ce qui va être changé
    est écrit dans `config.json` (clé `vpn`) **avant** d'être changé ; en
    cas d'échec tout est remis et le journal effacé. À chaque lecture,
    l'appli compare le journal à Windows : si Windows a déjà tout remis
    (redémarrage, carte réactivée), elle efface le journal et le signale.
  - Tunnels : services `WireGuardTunnel$<nom>` en cours, `wg.exe show
    <nom> dump` (dernier handshake, octets reçus). « Reconnect » redémarre
    le service du tunnel. Si un seul pair reçoit `0.0.0.0/0`, la fenêtre de
    réglage prévient que la case « Block untunneled traffic » bloque alors le
    réseau local de la carte mise de côté.

## Questions ouvertes (à poser à Noar)

1. La case « Block untunneled traffic » de son tunnel WireGuard est-elle
   cochée ?
2. Résultat sur SERVAL (Ethernet et Wi-Fi branchés) de
   `Get-NetIPInterface | ft InterfaceAlias,AddressFamily,InterfaceMetric,AutomaticMetric`
   et `Get-NetRoute -DestinationPrefix 0.0.0.0/0 | ft InterfaceAlias,RouteMetric,ifMetric`.

## Ce qui a été vérifié sur SERVAL avant la 3.0.0 (à refaire après une modification du domaine concerné)

- Étape 3 : chaque action, et sa ligne dans le journal.
- IP settings : passer une carte en fixe puis en DHCP ; laisser filer les
  15 s (retour automatique) ; fermer l'appli pendant le compte à rebours
  (retour aussi) ; préréglages enregistrés, rechargés, supprimés.
- Sortie VPN : `Set-NetIPInterface -PolicyStore ActiveStore` accepté pour
  la priorité ; WireGuard change de sortie sans reconnexion (sinon
  « Reconnect ») ; après redémarrage de Windows, l'appli annonce la fin du
  mode ; lecture de `wg.exe` (handshake, octets reçus).
- Installeur : sur un PC avec la 2.2.1, la 2.x disparaît (une seule entrée
  dans Applications), la tâche planifiée « NetCatChanger » est supprimée,
  les préréglages IP sont conservés. Le déroulé n'a pas pu être exécuté sous
  Wine (l'installeur s'y bloque même sans 2.x) ; le script NSIS compile.
- Avis de mise à jour : n'apparaîtra qu'une fois une version plus récente
  publiée sur GitHub.

## Problèmes connus

- Builds sur SERVAL (06.10.2026) : le téléchargement d'Electron par
  electron-builder abandonnait au bout de 10 minutes, et l'installeur
  d'Electron (`fetch` de Node) échouait net. Corrigé par
  `scripts/fetch-electron.js` (curl, reprise, SHA-256, cache dans
  `%LOCALAPPDATA%\NetCatChanger-build`) et `-c.electronDist=...`.
- Une version de `build_windows.cmd` avait gardé deux lignes d'une boucle
  supprimée : la fenêtre se fermait aussitôt. Réécrit, testé sous Wine avec
  des faux `node` / `npm`, protégé par des tests ; la console reste ouverte.
- L'avertissement npm « electron-winstaller ... install scripts » est sans
  effet (type d'installeur non utilisé).

## Publication (`scripts/push_github.cmd`, sur Windows)

Double-cliqué dans le dossier décompressé sur SERVAL (lance
`push_github.ps1`) : clone GitHub dans un dossier temporaire, refuse si
`version.json` et `package.json` diffèrent ou si la version n'est pas
strictement supérieure à celle de GitHub, remplace tout le contenu (ajouts,
modifications, suppressions : le code Python, `installer/`, les `.bat` et le
workflow de la 2.x disparaissent), montre la liste et attend « y ».
`version.json` reste à l'ancienne version sur GitHub tant que la Release
`vX.Y.Z` (ou `X.Y.Z`) n'a pas d'installeur publié ; relancer le script
ensuite l'envoie seul. Jamais d'envoi forcé ; fins de ligne envoyées telles
quelles (`core.autocrlf=false`). Testé avec PowerShell 7 contre un dépôt
local (deux passages, refus de version) ; nécessite Git for Windows, qui
demande la connexion GitHub au premier envoi.

## Emplacements de la version

1. `package.json` : `"version"`
2. `package-lock.json` : les deux `"version"` de NetCatChanger en tête de fichier
3. `version.json` : `"version"` (une fois poussé, déclenche la notification
   de mise à jour chez les utilisateurs)
4. `CHANGELOG.md` : titre de l'entrée

L'appli lit sa version dans `package.json` ; rien d'autre à modifier.
Vérification : `grep -rn "<ancienne version>" --exclude-dir=node_modules .`
