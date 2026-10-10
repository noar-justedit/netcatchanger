# NetCatChanger : état du projet

Mis à jour le 09.10.2026.

## En une phrase

Gestionnaire de profils réseau Windows (Privé / Public / Domaine), de
configuration IP, du pare-feu et de la sortie VPN WireGuard. **Version 3.1.1**
(09.10.2026) : corrige le retour automatique de l'IP secondaire, écrit et
vérifié hors Windows, **à tester sur SERVAL**. La 3.1.0 (IP secondaire,
« Use for Internet ») a été validée sur SERVAL le 08.10.2026 ; la 3.0.0
(réécriture Electron de la 2.2.1) le 07.10.2026.

## Review complète avant la 3.1.1 (09.10.2026, demandée par Noar)

Trois relectures (sécurité, bugs, cohérence de l'interface). Noar a laissé
carte blanche (« corrige ce qui te semble judicieux »). Corrigé :

- **Sécurité** (l'appli tourne en administrateur ; risques venant d'un autre
  programme du même compte Windows) :
  - PowerShell : `PSModulePath` limité aux modules de Windows et `PATH` à
    System32, dans l'environnement des processus ET au début de chaque
    script (`ps.js`, `PS_PRELUDE`, `childEnv`). netsh appelé par son chemin
    complet partout, wg.exe via le dossier Program Files lu par .NET.
  - Fusibles Electron (`electron-builder.yml`, `electronFuses`) : pas de mode
    Node, pas de NODE_OPTIONS, pas d'inspecteur, code chargé seulement
    depuis l'archive. Vérifié sur un build Linux d'essai (`@electron/fuses
    read`) ; l'appli refuse aussi de démarrer avec un port de débogage.
  - Journal ouvert avec notepad.exe (chemin complet), liens GitHub ouverts
    par explorer.exe (bureau de l'utilisateur, non élevé) au lieu de
    demander à Windows quel programme utiliser.
  - `config.json` / `session.log` : jamais écrits à travers un lien
    (jonction, lien symbolique) ; journal VPN / route validé au chargement
    (`store.validJournal`), listes vérifiées.
- **Bugs** : verrou sur les changements de priorité (une lecture en cours
  ne peut plus effacer le journal) ; fin par Windows → les cartes mises de
  côté sont remises aussi ; « Automatic » ne bute plus sur une carte
  éteinte ; fermeture pendant Apply / Revert → l'appli attend et remet ;
  avertissement si une adresse secondaire n'a pas pu être remise ; adresse
  principale : carte DHCP sans bail → aucune, carte fixe sans passerelle →
  jamais une secondaire gardée ; un seul contrôle Internet par adresse ;
  netsh en échec jamais pris pour un succès ; retrait d'une adresse sur une
  carte éteinte → aussi la copie de démarrage ; `load()` protégé ; messages
  PowerShell en UTF-8.
- **Interface** : pare-feu vert quand il est actif, partiellement actif →
  interrupteur sur off et un clic remet tout ; carte VPN verte quand le
  serveur répond ; bouton « Automatic » partout pour une route choisie ;
  pas d'« IP settings » sur un tunnel ou une carte éteinte, pas de
  « Secondary IP » sur une carte éteinte ; interrupteur du pare-feu grisé
  si l'état est inconnu ; noms longs coupés par « … » ; icônes Lucide
  `check` et `x` à la place des caractères ✓ et × ; vocabulaire
  (« adapter », « Could not … », fenêtre « Secondary IP ») ; Entrée ajoute
  une adresse ; avis de mise à jour fermé par Échap → reproposé.

Laissé de côté (choix de Noar à trancher, ou non vérifiable ici) :

- Le point violet du logo (`#5936d8`), contraire à « ni violet » : c'est son
  dessin, à lui de décider.
- La barre de signal Wi-Fi bleue, les noms « ADAPTER DISABLED », « Back to
  normal » de l'ancien mode VPN 3.0.0 : validés tels quels jusqu'ici.
- Les deux façons de gérer les préréglages (liste déroulante dans IP
  settings, pastilles dans Secondary IP) : à unifier si Noar le veut.
- Dossier des réglages dans `%APPDATA%` (modifiable par l'utilisateur) :
  le déplacer dans `%ProgramData%` casserait la reprise des réglages 2.x ;
  les écritures à travers un lien sont refusées en attendant.
- `SystemRoot` / `ProgramFiles` côté Node lus dans l'environnement : à
  vérifier sur un PC de test s'ils peuvent être détournés.
- DNS manuels d'une carte DHCP perdus après un « Revert » (rare).
- Intégrité de l'archive (fusible `enableEmbeddedAsarIntegrityValidation`) :
  non activée, je n'ai pas pu la tester sur un build Windows.

## À vérifier sur SERVAL pour la 3.1.1

- Le build passe (fusibles Electron) et l'appli démarre.
- ON d'une IP secondaire sur l'OWC : la coupure de quelques secondes ne doit
  plus remettre l'adresse en OFF.
- Toutes les lectures marchent encore (cartes, Wi-Fi, WireGuard, pare-feu) :
  PowerShell a maintenant un environnement restreint.
- Use for Internet : Wi-Fi, puis OWC, puis Automatic.
- Bouton du journal (Notepad) et lien GitHub (navigateur non administrateur).
- Pare-feu : couper un seul profil à la main, l'appli montre 2/3 et un clic
  remet tout.

## Où en est la 3.1

| Étape | Contenu | État |
|---|---|---|
| 1 | IP secondaire : lecture de toutes les adresses, ON / OFF par adresse, fenêtre « Secondary IP », préréglages, contrôles | validé sur SERVAL |
| 2 | Correction 3.0.0 : adresse principale mal choisie, IP settings effaçait les adresses secondaires | validé sur SERVAL |
| 3 | « Use for Internet » (priorité de route), fusionné avec la sortie VPN | validé sur SERVAL |
| 4 | Interface validée par Noar | validée le 08.10.2026, après retouches (alignement, badge SECONDARY IP, interrupteurs dans une colonne) |

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
src/main/ps/*.ps1       interfaces (lecture), watch (surveillance), wireguard (tunnels),
                        secondary (ajout / retrait d'une adresse secondaire)
src/main/netdata.js     lecture de l'état réseau + surveillance tant que la fenêtre vit
src/main/actions.js     ce qui modifie la machine (profil, carte, IP, DNS, pare-feu)
src/main/vpn.js         priorités : « Use for Internet » (routeOn), ancien mode VPN 3.0.0,
                        tunnels WireGuard
src/main/netinfo.js     fonctions pures (parseurs, logique VPN), couvertes par les tests
src/main/store.js       config.json et session.log dans %APPDATA%\NetCatChanger
src/renderer/           index.html, style.css (charte), app.js
test/run-tests.js       npm test (269 vérifications)
scripts/build_windows.cmd    build de l'installeur, à lancer sur Windows
scripts/fetch-electron.js    télécharge Electron une fois (curl, reprise, SHA-256)
scripts/push_github.cmd/.ps1 publication sur GitHub, depuis Windows (décision de Noar)
docs/screenshots/       captures du README (rendues avec des données simulées)
docs/RELEASE-3.x.y.md   texte des Releases GitHub
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

- **IP secondaire** (3.1.0, spec de Noar) :
  - Windows n'a pas d'adresse « désactivée » : OFF retire l'adresse de
    Windows et la garde dans `config.json` (clé `secondary`, par GUID de
    carte), prête à revenir. Une adresse ajoutée hors de l'appli apparaît en
    ON ; si on la passe en OFF, elle est gardée. « Remove » l'oublie.
  - Jamais de passerelle (une deuxième route par défaut casserait Internet
    et le VPN). Aucun champ, aucun argument `gateway` (vérifié par un test).
  - `ps/secondary.ps1` : carte retrouvée par GUID, netsh appelé avec son
    numéro d'interface ; sur une carte en DHCP, `dhcpstaticipcoexistence`
    activé avant l'ajout et désactivé quand il ne reste plus d'adresse
    manuelle ; sur une carte fixe, simple ajout. Windows 10 2004 (build
    19041) minimum pour le DHCP, sinon message clair.
  - Doublon : impossible à tester par ping avant l'ajout (pas de route vers
    la plage). L'appli ajoute, lit l'état que donne la détection de doublon
    de Windows (Tentative, Preferred, Duplicate) pendant 6 s au plus, et
    retire l'adresse si elle est en double. Carte non connectée : pas de
    vérification possible, l'appli le dit.
  - Contrôles avant ajout (`checkSecondary`) : adresse valide, ni réseau ni
    broadcast (sauf /31 /32), pas 0.x, 127.x, 169.254, multicast ; pas la
    même plage que l'adresse principale de la carte ni qu'une autre carte
    connectée ; pas déjà utilisée.
  - Retour automatique (Noar) : si la carte avait Internet, l'appli lit le
    verdict de Windows de 10 s à 25 s après un ON (toutes les 3 s) et
    repasse l'adresse en OFF seulement après 3 lectures « pas d'Internet »
    d'affilée (`internetWatchVerdict`). Pourquoi 10 s (09.10.2026) : sur
    SERVAL, ajouter ou retirer une adresse coupe Internet quelques secondes
    (Windows réexamine le réseau, mêmes commandes à la main) ; dans la 3.1.0
    le contrôle commençait à 3 s et pouvait retirer l'adresse pour rien.
    Limites : une coupure sans rapport peut aussi déclencher le retour ; le
    contrôle s'arrête si l'appli est fermée pendant ces 25 s.
  - Coupure de quelques secondes à chaque ON / OFF : comportement de Windows,
    pas de message dans l'appli (Noar a refusé le message, 09.10.2026).
  - Adresse source vérifiée sur SERVAL (09.10.2026) : avec l'IP secondaire,
    Windows sort bien vers Internet avec l'adresse DHCP. Aucune règle de
    priorité (prefixpolicy) nécessaire.
  - Préréglages (`secondary_presets`) : nom + adresse + préfixe, sans carte
    (recommandation acceptée par défaut, Noar n'a pas tranché ce point).
  - Adresses d'une carte disparue : listées dans la fenêtre (« Use here » /
    « Forget »).
  - Badge rouge si un nouveau bail DHCP tombe dans la même plage, ou si
    Windows signale un doublon.
  - Sur la carte (Noar, retour sur SERVAL 08.10.2026) : chaque adresse
    secondaire est une ligne de la grille des adresses (nom dans la colonne
    des libellés, adresse alignée à droite avec IPv4 / IPv6 / Gateway,
    interrupteur à droite de l'adresse). La grille des adresses a trois
    colonnes : libellé, adresse alignée à droite, interrupteurs. Celui de la
    carte est sur la ligne IPv4, ceux des adresses secondaires (même taille)
    sur leur ligne : toutes les adresses finissent au même bord, tous les
    interrupteurs sont dans la même colonne. Badge SECONDARY IP : vert si une adresse est active, gris si
    toutes sont en OFF, rouge en cas de problème.
  - Fenêtre à part (« Secondary IP ») plutôt qu'une section d'IP settings :
    ses actions s'appliquent tout de suite, IP settings attend « Apply ».
- **Corrections 3.0.0** (Noar) : l'adresse principale est choisie par
  `pickPrimary` (l'adresse DHCP ; sur une carte fixe, celle de la plage de la
  passerelle), plus « la première listée » ; IP settings remet les adresses
  secondaires après un passage DHCP / fixe, et l'annulation 15 s aussi.
- **Use for Internet** (Noar, 10.2026 : temporaire, fusion avec le VPN) :
  - Bouton sur chaque carte connectée avec passerelle, quand il y en a au
    moins deux. La carte choisie reçoit la priorité 1 ; une autre carte qui
    ferait encore jeu égal ou mieux est mise à 9000. Magasin actif
    seulement : un redémarrage de Windows remet l'automatique.
  - Badge INTERNET ROUTE : bleu sur la carte choisie, gris sur celle que
    Windows choisit seul. « Automatic » remet tout.
  - Le bouton « Use another connection » de la carte VPN fait la même chose.
    Journal dans `config.json` (clé `vpn`, `method: "route"`, avec la
    priorité d'origine de chaque carte touchée) écrit avant le changement.
    Un journal 3.0.0 (`method: "metric"`) reste compris et peut être défait.
  - Limite : si la carte choisie reste connectée mais qu'Internet ne passe
    plus derrière (box en panne), Windows ne bascule pas.
- **Nom** : Noar a envisagé « net manager », puis décidé de garder
  NetCatChanger (08.10.2026).

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

## Vérifié sur SERVAL pour la 3.1.0 (08.10.2026)

- IP secondaire sur l'OWC en DHCP : ajout, ON / OFF, Remove ; `netsh
  interface ipv4 show interface <n>` montre la coexistence activée puis
  désactivée au retrait de la dernière ; l'adresse survit à un redémarrage.
- Doublon : prendre l'adresse d'un appareil présent, l'appli doit refuser.
- Carte en IP fixe : ajout d'une adresse supplémentaire.
- IP settings sur une carte qui a une adresse secondaire : passage DHCP ->
  fixe -> DHCP, puis laisser filer les 15 s ; l'adresse secondaire doit
  rester.
- Use for Internet : Wi-Fi et Ethernet branchés, basculer, vérifier
  `Get-NetRoute -DestinationPrefix 0.0.0.0/0` et un site ; « Automatic » ;
  redémarrage (l'appli doit annoncer le retour à l'automatique) ; avec le
  VPN, « Use another connection ».

## Problèmes connus

- 3.1.0 sur SERVAL (08.10.2026), corrigé : l'interrupteur OFF d'une
  adresse secondaire écrivait « ok » dans le journal sans rien retirer.
  Cause : dans Windows PowerShell 5.1, un objet Windows (CIM) seul n'a pas
  de `.Count` ; `(& $find).Count` valait donc rien, l'adresse semblait déjà
  partie et netsh n'était jamais appelé. Même cause : la détection de
  doublon ne lisait jamais l'état de l'adresse. Corrigé par `@(& $find)`,
  reproduit puis vérifié avec un faux Windows sous PowerShell 7, protégé
  par un test. Ajouts au passage : si netsh échoue, `Remove-NetIPAddress` ;
  message de Windows dans l'erreur ; chaque demande ON / OFF écrite dans
  `session.log`. Vérifié sur SERVAL le 08.10.2026.

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
