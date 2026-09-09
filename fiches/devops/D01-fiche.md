# D01 — FICHE : Linux (processus, fichiers, permissions, systemd)

> Lire **avant** le cours (pretesting), puis réciter de mémoire aux rappels. Cible : **3 minutes**.
> Linux tient en 3 abstractions : **le fichier** (sur quoi j'agis) · **le processus** (qui agit) ·
> **l'identité** (ai-je le droit). Tout passe par des **appels système**.

## Arborescence
`/etc` config texte machine · `/var` données variables (logs, bases) · `/usr` paquets · `/usr/local` ce que tu poses ·
`/tmp` **souvent tmpfs = RAM**, mode **1777** · `/run` volatile · `/proc` `/sys` pseudo-FS · `/boot` noyau.

## Fichier = inode, pas nom
| | |
|---|---|
| **Inode** | mode, UID/GID, taille, atime/mtime/ctime, **nlink**, pointeurs de blocs. **Pas le nom** |
| Nom | entrée de répertoire → n° d'inode |
| `ln` **physique** | 2ᵉ nom, même inode, `nlink`++, **même FS uniquement**, pas sur un répertoire |
| `ln -s` **symbolique** | inode à part contenant un **chemin** |
| `rm` = `unlink()` | blocs libérés seulement si **nlink = 0 ET aucun FD ouvert** |
| mtime / ctime | contenu / **contenu OU métadonnées** (chmod change ctime, pas mtime) |
| Types `ls -l` | `-` `d` `l` `c` `b` `p` (FIFO) `s` (socket) |

## Descripteurs, redirections, tubes
**0 stdin · 1 stdout · 2 stderr.** `> f` ne redirige **que le 1**. Voir : `ls -l /proc/PID/fd`.
`> f 2>&1` ✅ · **`2>&1 > f` ❌** (photo prise avant déplacement). `&> f` · `<<EOF` · `<<<` · `<(cmd)` · `\|&`.
Tube = **tampon noyau 64 Kio**, 2 process **simultanés**. Lecteur parti → **SIGPIPE(13) → code 141**.
Code d'un pipeline = **dernière commande** → `set -o pipefail`, `${PIPESTATUS[@]}`.
**Bufferisation** : ligne sur tty, **blocs 4 Kio sur fichier/tube** → `PYTHONUNBUFFERED=1`, `python -u`, `stdbuf -oL`.
`ulimit -n` **1024** souple / **524288** dure · sous systemd c'est `LimitNOFILE=`.

## Processus
`fork()` = copie **copy-on-write**, retourne **0 chez l'enfant**, PID chez le parent · `execve()` = **même PID, autre programme**.
Redirections/nice/user posés **entre** fork et exec. PID 1 = systemd (ou **ton app** dans un conteneur). `pid_max` 32768 → 4194304.

| État | Sens |
|---|---|
| `R` | en cours / prêt |
| `S` | sommeil **interruptible** (95 % des cas) |
| **`D`** | sommeil **non interruptible** (E/S) — **`kill -9` inopérant**, **compte dans le load** |
| `T` `Z` | stoppé · **zombie** |

**Zombie** = **enfant** mort, parent n'a pas `wait()` → 1 PID gaspillé, `kill -9` inutile → tuer **le parent**.
**Orphelin** = **parent** mort → ré-adopté par **PID 1** → normal.
`nice` **−20 → +19** (défaut 0), **+ = moins prioritaire**, non-root ne peut qu'**augmenter**. E/S = `ionice`.

## Signaux — **code de sortie = 128 + n°**
**1 HUP** (recharge conf) · **2 INT** (Ctrl-C) · **3 QUIT** (thread dump JVM) · **9 KILL** · **13 PIPE** ·
**15 TERM** (défaut) · **17 CHLD** · **19 STOP** · **20 TSTP** (Ctrl-Z).
**Seuls 9 et 19 ne se rattrapent ni ne se bloquent.** **137 = KILL · 143 = TERM · 130 = Ctrl-C · 141 = PIPE.**
Délais de grâce : **docker 10 s · Kubernetes 30 s · systemd 90 s**.
**PID 1 ignore SIGTERM sans handler** → `--init`/`tini` · **`CMD ["x","y"]` en forme exec**, jamais shell.

## Permissions — `r=4 w=2 x=1`
Première classe qui correspond, **on s'arrête là** (`chmod 077` = illisible par le proprio).
**Sur un répertoire** : `r` lister · `w` créer/supprimer (+`x`) · **`x` traverser** — il faut `x` sur **tout le chemin**.
**644** données · **755** exécutable/répertoire · **600** clé SSH · **700** `~/.ssh` · **775/664** équipe.
**umask** : fichier = **666 −** umask, répertoire = **777 −** umask. `022`→644/755 · `027`→**640/750** · `077`→600/700.
Attribut **du processus**, hérité, **jamais rétroactif** (`UMask=` en systemd).
**Bits spéciaux : 4 setuid · 2 setgid · 1 sticky.** `rws` user (`passwd` = **4755**) · `rws` groupe = **héritage du groupe**
sur un répertoire (**2775**) · `rwt` = **/tmp 1777**, seul le proprio supprime. **setuid ignoré sur les scripts.**
Moderne : capabilities (`cap_net_bind_service` < 1024, `cap_net_raw`). ACL : `setfacl -m u:x:r--`, `+` dans `ls -l`, **le `mask` plafonne**.

## Utilisateurs
`/etc/passwd` **7 champs** `nom:x:UID:GID:GECOS:home:shell` (644) · `/etc/shadow` hash (640) · `/etc/group`.
**UID 0 = root** · 1-999 système · **≥1000** humains. Groupe **primaire** = groupe des fichiers créés.
`usermod -aG` — **sans `-a` ça remplace**. Changement de groupe **non rétroactif** : se reconnecter. `docker` ≈ root.

## systemd
Unités : `.service .socket .target .timer .mount .path .slice`. Priorité : **`/etc/systemd/system` > `/run` > `/usr/lib`**.
Targets : `sysinit` → `basic` → **`multi-user`** → `graphical`. **`network-online` ≠ `network`.**
**`Type=`** : `simple` (défaut) · `forking` (le parent sort) · `oneshot` · `notify` (`READY=1`).
**`Requires=` dit QUI, `After=` dit QUAND** — indépendants, s'écrivent ensemble. `Wants` souple · `BindsTo` · `PartOf`.
`Restart=on-failure`, `RestartSec` **100 ms**, `TimeoutStopSec` **90 s**, `LimitNOFILE`, `MemoryMax`, `CPUQuota`.
**`systemctl daemon-reload` obligatoire après édition.** `edit` (drop-in `.d/override.conf`) · `cat` · `mask` (→ /dev/null) ·
`enable --now` · `list-units --failed` · `systemd-analyze blame`.
`journalctl -u X -f · -b (-1) · -p err · -k · --since · -o json · --vacuum-time=7d`.
Priorités **0 emerg 1 alert 2 crit 3 err 4 warning 5 notice 6 info 7 debug**.
**`Storage=auto` → volatile si `/var/log/journal` n'existe pas.**
**Timer > cron** : `Persistent=true` (rattrapage), journal, pas de chevauchement, cgroup, `RandomizedDelaySec`.
Cron = 5 champs `min h jour mois jsem`, **environnement quasi vide** → chemins absolus, `%` à échapper.

## Mémoire
**VSZ** = adressage virtuel (une JVM `-Xmx4g` → 12 Gio, **à ignorer**) · **RSS** = pages en RAM (**double-compte le partagé**) ·
**PSS** = part équitable (`/proc/PID/smaps_rollup`). Page = **4 Kio**.
`free -h` → **lire `available`**, pas `free`. `buff/cache` = **page cache récupérable**. `vm.swappiness` **60**.
**OOM killer** : score ≈ RSS, ajusté par `oom_score_adj` **[−1000, +1000]** (K8s : Guaranteed **−997**, BestEffort **+1000**).
Preuve : **`dmesg -T | grep -i oom`**. « **Memory cgroup out of memory** » = **limite du conteneur**, pas du nœud.
**`OutOfMemoryError` (exception JVM, tas plein) ≠ `OOMKilled` (SIGKILL noyau, code 137, zéro log).**
Spark : limite ≥ `executor.memory` + `memoryOverhead` = **max(384 Mio, 10 %)** + marge.

## Disque
`/etc/fstab` **6 champs** : périph `UUID=` · point · type · options (`noatime`, **`nofail`**) · dump · **passno**.
**`df`** = superbloc (voit les supprimés-ouverts et le masqué) · **`du`** = parcours des noms.
`df` plein / `du` vide → **`lsof +L1`** (fichier supprimé encore ouvert) · montage par-dessus · **5 % réservés root** (ext4).
**« No space left » avec de la place = inodes épuisés → `df -i`.** ext4 : **1 inode / 16 Kio**, **figé au `mkfs`**.
LVM : **PV → VG → LV** (extent 4 Mio). `lvextend -L +200G **-r**` (le `-r` étend le FS). **XFS ne rétrécit pas.**

## Diagnostic — l'ordre
`uptime` → `top` → `free -h` → **`df -h` ET `df -i`** → `dmesg -T | tail` → `journalctl -p err -b` / `systemctl --failed`.
`top` : load **1/5/15 min** (inclut **`D`**), **`wa`** = attente E/S, `st` = vol d'hyperviseur.
`lsof -i :9092` · `lsof +L1` · `strace -f -T -p PID` (**×10 à ×100 de coût**) · `strace -c` · `iostat -xz 1` · `vmstat 1` (`si/so`).

---

## Test express — 8 questions
1. Quels sont les deux seuls signaux qu'on ne peut ni rattraper ni ignorer, et que vaut un code 137 ?
2. Avec `umask 027`, quel mode a un fichier créé ? un répertoire ? Pourquoi jamais `x` sur le fichier ?
3. Zombie ou orphelin : lequel des deux est mort, et lequel est normal ?
4. `df` dit 100 %, `du` ne trouve rien : trois causes possibles, dans l'ordre où tu les testes.
5. Différence exacte entre `Requires=` et `After=` — que se passe-t-il si on n'écrit que `Requires=` ?
6. Que permet le bit `x` sur un **répertoire**, et sur combien de niveaux du chemin faut-il l'avoir ?
7. Pourquoi la somme des RSS de tous les process peut-elle dépasser la RAM installée ?
8. Un conteneur met exactement 30 s à s'arrêter à chaque fois : les deux causes possibles.
