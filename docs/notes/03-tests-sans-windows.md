# 03 — Tester sans Windows

Deux bugs bloquants sont passés en livraison parce qu'on s'était contenté de
relire le code : un exe qui ne se lançait pas, puis une app qui démarrait sans
les droits administrateur. **On ne valide plus sur relecture.** Voici ce qui est
vérifiable depuis le Mac, et comment.

---

## 1. Les tests hors ligne — toujours, à chaque modification

```
python3 tests/test_parsing.py
```

Doit afficher `all parsing checks passed`. Aucune dépendance, aucun Windows.
Couvre : le parseur `netsh` sur des sorties anglaise / française / allemande,
la normalisation des bandes et des débits, l'échappement PowerShell, la logique
d'élévation (avec un faux `ShellExecuteW`), la tâche planifiée d'autostart
(avec un faux `schtasks`), les masques de sous-réseau et la validation d'IP.

**Ajouter un test à chaque correction de bug.** Le fichier est volontairement
sans framework : une fonction `check(libellé, obtenu, attendu)` et une liste
d'appels. Pour tester une fonction qui parle à Windows, on remplace
temporairement `ns.run_cmd` ou `ns.ctypes` par un faux objet — il y a déjà des
exemples dans le fichier.

---

## 2. Le harnais d'interface — dès qu'on touche au visuel

```
python3 tests/ui_harness.py                    # la fenêtre principale
python3 tests/ui_harness.py --readonly         # UAC refusé (barre orange)
python3 tests/ui_harness.py --dialog ip        # dialogue de configuration IP
python3 tests/ui_harness.py --dialog fw        # dialogue pare-feu
python3 tests/ui_harness.py --dialog settings
python3 tests/ui_harness.py --dialog update
python3 tests/ui_harness.py --shot /tmp/ui.png # capture puis quitte
```

**Comment ça marche.** L'application ne parle à Windows qu'à travers quelques
fonctions : `run_ps` (PowerShell), `run_cmd` (netsh / ipconfig / schtasks),
`ping_ok`, `dns_ok`, et la classe `NetworkWatcher`. Le harnais les remplace par
des fonctions qui renvoient des données inventées. Tout le reste — la mise en
page, les couleurs, les cartes, les interrupteurs, les dialogues — s'exécute
pour de vrai.

Les données simulées couvrent quatre cas différents exprès : un Wi-Fi nominal,
un Ethernet en IP fixe, une carte en `169.254.x.x` (panne DHCP, doit apparaître
en rouge) et une carte désactivée. Pour tester un cas particulier, modifier
`MOCK_IFACES` en haut du fichier.

**Avec `--shot`, Claude Code peut lire la capture et vérifier lui-même le
rendu.** C'est la manière de vérifier une modification visuelle sans que Noar
ait à décrire ce qu'il voit.

### Prérequis sur le Mac

`python3 -m tkinter` doit ouvrir une petite fenêtre de test. Si ça échoue :

```
brew install python-tk
```

Sur macOS, `screencapture` peut demander l'autorisation « Enregistrement de
l'écran » la première fois (Réglages Système → Confidentialité et sécurité).
Si c'est refusé, la capture échoue mais la fenêtre s'affiche quand même : on
regarde directement.

### Ce que le harnais ne teste pas

L'élévation UAC, la tâche planifiée, l'icône dans la zone de notification
Windows, le chargement de Poppins via GDI, et tout échange réel avec le réseau.
Le rendu des polices diffère aussi de Windows (Segoe UI et Consolas n'existent
pas sur Mac, tkinter prend un substitut). **C'est un contrôle de mise en page et
de logique, pas une recette.** Le dire en livrant.

---

## 3. Les scripts PowerShell embarqués

`network_switcher.py` contient deux scripts PowerShell en texte
(`_BATCH_SCRIPT`, `_WATCH_SCRIPT`). Une faute de syntaxe dedans ne se voit pas
en Python : elle se voit seulement à l'exécution, sur Windows.

Si `pwsh` est installé sur le Mac (`brew install --cask powershell`), on peut
vérifier la syntaxe :

```bash
python3 - <<'EOF'
import re
src = open('src/network_switcher.py', encoding='utf-8').read()
for nom, sortie in (('_BATCH_SCRIPT', '/tmp/batch.ps1'),
                    ('_WATCH_SCRIPT', '/tmp/watch.ps1')):
    m = re.search(nom + r'\s*=\s*r"""(.*?)"""', src, re.S)
    open(sortie, 'w', encoding='utf-8').write(m.group(1))
EOF

pwsh -NoProfile -Command '
foreach ($f in @("/tmp/batch.ps1","/tmp/watch.ps1")) {
  $t=$null; $e=$null
  [void][System.Management.Automation.Language.Parser]::ParseFile($f,[ref]$t,[ref]$e)
  if ($e.Count) { Write-Output "ERREURS dans $f"; $e | ForEach-Object { Write-Output "  $($_.Message) ligne $($_.Extent.StartLineNumber)" } }
  else { Write-Output "OK  $f" }
}'
```

On peut aller plus loin : remplacer les cmdlets Windows par de fausses
fonctions PowerShell et exécuter réellement le bloc de parsing avec des sorties
`netsh` simulées en français, anglais et allemand. C'est ainsi qu'a été validé
le parseur multilingue.

---

## 4. Deux réflexes qui ont trouvé le plus de défauts

**Mesurer plutôt que supposer.** Le bug de l'exe qui ne démarrait pas a été
trouvé en lançant réellement l'application, pas en relisant le code. La
troisième relecture n'aurait rien donné de plus que les deux premières.

**Vérifier un test en le cassant.** Un test qui passe alors qu'il ne devrait pas
est pire que pas de test. Après avoir écrit un test, casser volontairement le
code qu'il couvre et vérifier qu'il échoue.
