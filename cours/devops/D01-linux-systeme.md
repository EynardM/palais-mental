# D01 — Linux : processus, fichiers, permissions, systemd

> **Ce que tu sauras faire à la fin**
> - Expliquer ce qu'est *vraiment* un fichier sous Linux (inode, descripteur, entrée de répertoire), et diagnostiquer les trois pannes classiques qui en découlent : `df` plein mais `du` vide, « No space left » avec des giga-octets libres, un log qui n'apparaît jamais.
> - Dérouler le cycle `fork()` → `exec()` → `exit()` → `wait()`, expliquer zombie et orphelin, et dire pourquoi PID 1 est un rôle et pas un processus ordinaire.
> - Choisir le bon signal, savoir lequel ne se rattrape pas, et expliquer précisément ce qui se passe entre `docker stop` et le `SIGKILL` dix secondes plus tard.
> - Lire et écrire une permission en octal sans hésiter, calculer un `umask`, reconnaître un `setuid` et un sticky bit dans un `ls -l`, poser une ACL.
> - Écrire une unit systemd correcte (`Type=`, `Restart=`, dépendances, drop-in), la déboguer avec `journalctl`, et arbitrer entre un timer systemd et une ligne de cron.
> - Distinguer RSS, VSZ et PSS, expliquer pourquoi `free` affiche « peu de mémoire libre » sans que ce soit un problème, et lire dans `dmesg` l'acte de décès d'un exécuteur Spark tué par l'OOM killer.
> - Ouvrir `top`, `ps`, `lsof`, `strace`, `dmesg` avec une hypothèse en tête plutôt qu'au hasard.
>
> **Pourquoi ça compte dans ton poste**
> Un data engineer ne « fait pas du Linux » : il *subit* du Linux, tous les jours, à travers une couche
> d'abstraction qui ment. Airflow te dit « task failed ». Kubernetes te dit `OOMKilled`. Spark te dit
> `ExecutorLost`. Ces trois messages ne veulent rien dire tant que tu ne sais pas lire ce qu'il y a
> dessous : un code de sortie 137, un cgroup qui a atteint `memory.max`, un processus tué par un signal
> que personne n'a rattrapé. Tout l'outillage data — conteneurs, orchestrateurs, JVM, drivers réseau —
> est bâti sur exactement cinq primitives Unix : le fichier, le processus, le signal, la permission,
> le cgroup. Les connaître froidement transforme une panne de trois jours en un diagnostic de dix minutes,
> et c'est aussi ce qu'on teste en entretien, parce que ça ne se bluffe pas.
>
> **Prérequis** : `R01` (couches, encapsulation) et `R06` (TCP, sockets, ports) aident pour la partie
> descripteurs et `lsof`, mais ce module se lit seul. Une console Linux ouverte à côté multiplie le rendement par deux.
> **Durée de lecture** : 75-90 min. Les sections 6 (permissions) et 9 (mémoire) contiennent des calculs : papier et crayon.

---

## 1. Le modèle mental : Linux tient en trois abstractions

Avant toute commande, pose-toi la question fondatrice : **quand un programme veut agir sur le monde, à qui parle-t-il ?**

Il ne parle pas au disque, ni à la carte réseau, ni à la RAM. Il parle au **noyau**, et uniquement par
des **appels système** (~350 sur Linux x86-64). Le noyau lui répond dans le vocabulaire de trois
abstractions, et absolument tout le reste en découle :

```
        ESPACE UTILISATEUR                  |        ESPACE NOYAU
                                            |
   ton process Python / Spark / nginx       |
              |                             |
              |  read() write() open()      |     ┌──────────────────────┐
              |  fork() execve() kill()     |     │  1. LE FICHIER       │  "sur quoi j'agis"
              +---- appel système ----------+---> │  2. LE PROCESSUS     │  "qui agit"
                     (syscall)              |     │  3. L'IDENTITÉ       │  "ai-je le droit"
                                            |     └──────────────────────┘
                                            |            |
                                            |     pilotes, ordonnanceur, MMU, FS
                                            |            |
                                            |     matériel : CPU, RAM, disque, NIC
```

- **Le fichier** répond à « sur quoi j'agis ». Un fichier régulier, mais aussi un disque, un terminal,
  une socket TCP, un tube, un processus (`/proc`), un capteur de température (`/sys`).
- **Le processus** répond à « qui agit ». Une adresse mémoire virtuelle, des descripteurs ouverts, une
  identité, un parent, des enfants.
- **L'identité** (UID, GID, capabilities) répond à « ai-je le droit ». Le noyau tranche à chaque appel.

> 🧠 **MÉMO** — **Objet, sujet, droit.** Le fichier est l'objet, le processus est le sujet, la permission
> est le verbe qui autorise la phrase. Toute panne système est l'une de ces trois choses qui manque.

> ❓ **RETIENS ÇA** — Par quel unique mécanisme un programme peut-il agir sur le matériel ?
> <details><summary>→ réponse</summary><br>L'<b>appel système</b> (syscall). Le programme n'accède jamais directement au disque, au réseau ou à la mémoire physique : il demande au noyau, qui vérifie ses droits et exécute. C'est ce qui rend <code>strace</code> si puissant : il montre <b>toute</b> l'interaction d'un process avec le monde extérieur.</details>

---

## 2. L'arborescence : pourquoi un seul arbre et pas des lettres de lecteur

**Le problème** : tu as trois disques, une clé USB, un partage NFS et un pseudo-système de fichiers
qui n'existe qu'en mémoire. Comment un programme les désigne-t-il sans savoir lequel est lequel ?

Windows répond `C:`, `D:`, `E:` — le programme doit connaître la topologie du matériel. Unix répond :
**un seul arbre, une seule racine `/`, et on greffe chaque périphérique sur une branche** (le *montage*).
Un programme qui écrit dans `/data/warehouse` ne sait pas — et n'a pas à savoir — s'il s'agit d'un SSD
local, d'un volume EBS, d'un NFS ou d'un tmpfs en RAM.

Le **FHS** (Filesystem Hierarchy Standard) fixe le rôle de chaque branche :

| Chemin | Contenu | Le critère qui le distingue |
|---|---|---|
| `/bin` `/sbin` `/lib` | Binaires et bibliothèques de base | Sur les distributions modernes, **liens symboliques vers `/usr/…`** (« usr-merge ») |
| `/usr` | Le système installé par les paquets | **Partageable et lisible seule** : rien de spécifique à la machine |
| `/usr/local` | Ce que **tu** as installé à la main | Le gestionnaire de paquets n'y touche jamais |
| `/etc` | Configuration, **texte, spécifique à la machine** | Jamais de binaire, jamais de donnée variable |
| `/var` | Données **variables** : logs, spool, caches, bases | `/var/log`, `/var/lib/docker`, `/var/lib/postgresql` |
| `/tmp` | Temporaire, **effacé au reboot**, souvent un tmpfs (RAM) | Mode `1777` (sticky bit) |
| `/run` | État volatile du système depuis le boot (PID files, sockets) | tmpfs, vidé à chaud |
| `/home` `/root` | Répertoires personnels | `/root` est **hors** de `/home` exprès : `/home` peut être un montage réseau absent au boot |
| `/opt` | Logiciels tiers monolithiques | Un sous-répertoire par éditeur |
| `/proc` | **Pseudo-FS** : un répertoire par PID + état du noyau | Taille apparente 0, contenu généré à la lecture |
| `/sys` | **Pseudo-FS** : périphériques, cgroups v1, paramètres du noyau | Un fichier = un attribut du noyau |
| `/dev` | Fichiers de périphériques, peuplé par udev | `/dev/null`, `/dev/zero`, `/dev/urandom`, `/dev/sda` |
| `/boot` | Noyau (`vmlinuz`), initramfs, GRUB | Souvent une partition séparée, petite, qui **se remplit** |
| `/srv` `/mnt` `/media` | Données servies · montage manuel · montage amovible | Conventions, peu utilisées en pratique |

**Le pense-bête qui règle 90 % des cas** : *une donnée qui change souvent va dans `/var`, une donnée qui
décrit la machine va dans `/etc`, un programme va dans `/usr`.*

> ⚠️ **PIÈGE** — `/tmp` est souvent un **tmpfs, donc en RAM, donc compté dans ta limite mémoire**.
> Un job Spark qui déverse ses fichiers de shuffle dans `/tmp` sur un conteneur limité à 4 Gio ne
> remplit pas un disque : il **remplit sa mémoire** et se fait tuer par l'OOM killer. Dans un pod
> Kubernetes, `emptyDir: {medium: Memory}` a exactement le même effet.

> ❓ **RETIENS ÇA** — Quelle est la différence de vocation entre `/etc` et `/var` ?
> <details><summary>→ réponse</summary><br><code>/etc</code> = configuration <b>statique, en texte, propre à cette machine</b> ; on peut la versionner. <code>/var</code> = données <b>variables produites par les services</b> (logs, bases, caches, spools) ; on la sauvegarde, on ne la versionne pas.</details>

---

## 3. « Tout est fichier » : inodes, descripteurs, redirections

### 3.1 Le problème : un nom unique pour des choses qui n'ont rien en commun

Lire un fichier sur disque, lire le clavier, recevoir des octets d'une socket TCP, lire la sortie
d'un autre programme : quatre mécanismes matériels complètement différents. Unix les a réunis sous
**une seule interface** : `open()`, `read()`, `write()`, `close()`. Conséquence pratique énorme :
un programme qui sait lire un fichier sait aussi lire une socket, un tube et un terminal, sans une
ligne de code de plus. C'est pour ça que `grep` fonctionne aussi bien sur `/var/log/syslog` que dans
un pipeline.

Le premier caractère de `ls -l` te dit à quelle famille tu as affaire :

```
-  fichier régulier        d  répertoire          l  lien symbolique
c  périphérique caractère  b  périphérique bloc   p  tube nommé (FIFO)
s  socket
```

### 3.2 L'inode : le fichier n'est pas son nom

**Question** : où est stocké le nom d'un fichier ?

Réponse contre-intuitive : **pas dans le fichier**. Un fichier, pour le système de fichiers, c'est un
**inode** — une fiche d'état civil numérotée qui contient tout *sauf* le nom :

```
   RÉPERTOIRE /data                          INODE 8394215                 BLOCS DE DONNÉES
   ┌───────────────────────┐          ┌──────────────────────────┐        ┌────────────┐
   │ "ventes.csv" → 8394215│─────────>│ type    : fichier        │───────>│  0100101…  │
   │ "backup.csv" → 8394215│─────┐    │ mode    : rw-r--r-- 0644 │   ┌───>│  1101001…  │
   │ "vieux.csv"  → 7712009│     │    │ UID/GID : 1000 / 1000    │   │    └────────────┘
   └───────────────────────┘     │    │ taille  : 3 892 401      │   │
        (entrées de répertoire)  │    │ atime/mtime/ctime        │   │
                                 └───>│ nlink   : 2  ◄── 2 noms  │   │
                                      │ pointeurs de blocs ──────┼───┘
                                      └──────────────────────────┘
```

Trois conséquences que tout le monde confond :

1. **Lien physique (`ln a b`)** : une seconde entrée de répertoire vers le **même inode**. `nlink` passe
   à 2. Aucun des deux noms n'est « l'original ». Impossible entre deux systèmes de fichiers (l'inode
   n'existe que dans le sien) et interdit sur les répertoires.
2. **Lien symbolique (`ln -s a b`)** : un **inode à part** qui ne contient qu'une chaîne de caractères,
   le chemin cible. Peut pointer n'importe où, y compris vers rien (« lien cassé »).
3. **`rm` ne supprime pas un fichier**, il fait `unlink()` : il retire une entrée de répertoire et
   décrémente `nlink`. Les blocs ne sont libérés que quand **`nlink == 0` ET plus aucun processus
   n'a le fichier ouvert**.

Le point 3 est la cause du bug système le plus fréquent en production :

> ⚠️ **PIÈGE — `df` dit 100 %, `du` ne trouve rien.** Quelqu'un a fait `rm gros.log` pendant que le
> service l'avait encore ouvert. Le nom a disparu (`du` parcourt les noms, il ne voit plus rien), mais
> les blocs restent alloués tant que le descripteur est ouvert (`df` interroge le superbloc, il les voit).
> Diagnostic : `lsof +L1` (fichiers ouverts dont `nlink < 1`). Remède : **redémarrer ou recharger le
> service** — pas un second `rm`. C'est aussi pour ça qu'on fait `logrotate` avec `copytruncate` ou un
> `SIGHUP` au service : il faut que le processus **rouvre** le fichier.

Les trois horodatages, source d'une question d'entretien classique :

| Champ | Change quand | Ne change PAS quand |
|---|---|---|
| **atime** | on **lit** le contenu | (souvent désactivé : montage `relatime` par défaut, mise à jour ≤ 1×/jour) |
| **mtime** | on **modifie le contenu** | on change les permissions |
| **ctime** | on modifie le contenu **ou les métadonnées** (chmod, chown, rename, lien) | — |

> ❓ **RETIENS ÇA** — Quelle est la différence entre `mtime` et `ctime` ?
> <details><summary>→ réponse</summary><br><code>mtime</code> = dernière modification du <b>contenu</b>. <code>ctime</code> = dernière modification de <b>l'inode</b>, donc contenu <b>ou</b> métadonnées (chmod, chown, renommage, lien). Un <code>chmod</code> change le ctime et pas le mtime. Aucun des deux n'est la date de création (le <i>birth time</i>, disponible en ext4/xfs via <code>statx</code> et <code>stat</code> récent).</details>

### 3.3 Descripteurs de fichiers : le numéro de vestiaire

Quand un processus fait `open("/data/x.csv")`, le noyau lui rend un **entier** : le descripteur de
fichier (FD). C'est un **numéro de vestiaire** — le process ne détient pas le fichier, il détient un
ticket vers une table gérée par le noyau.

```
  PROCESS 4712                   NOYAU
  table des FD              table des fichiers ouverts        inodes
  ┌───┬──────────┐          ┌─────────────────────────┐     ┌────────┐
  │ 0 │ ─────────┼─────────>│ offset 0, O_RDONLY      │────>│ /dev/pts/3 (tty)
  │ 1 │ ─────────┼─────────>│ offset 8192, O_WRONLY   │────>│ /var/log/app.log
  │ 2 │ ─────────┼─────────>│ (même entrée que 1)     │──┘
  │ 3 │ ─────────┼─────────>│ socket TCP :9092        │────>│ (pas d'inode disque)
  │ 4 │ ─────────┼─────────>│ offset 0, O_RDONLY      │────>│ /data/ventes.csv
  └───┴──────────┘          └─────────────────────────┘     └────────┘
```

**Les trois premiers sont réservés par convention**, et c'est toute la puissance du shell :

| FD | Nom | Par défaut | Sert à |
|---:|---|---|---|
| **0** | `stdin` | le clavier / le terminal | l'entrée de données |
| **1** | `stdout` | l'écran | **le résultat** du programme |
| **2** | `stderr` | l'écran | **les diagnostics** (erreurs, avancement) |

Pourquoi séparer 1 et 2 alors qu'ils vont au même endroit ? Parce qu'un jour tu écris
`./extract.sh > donnees.csv` : les données vont dans le fichier, **les messages d'erreur restent
visibles à l'écran** au lieu de corrompre le CSV. C'est la raison d'être de stderr, et elle est
purement pratique.

> ❓ **RETIENS ÇA** — Que valent les descripteurs 0, 1 et 2, et lequel n'est pas redirigé par `> fichier` ?
> <details><summary>→ réponse</summary><br>0 = stdin, 1 = stdout, 2 = stderr. <code>&gt; fichier</code> ne redirige que le <b>1</b>. Les erreurs continuent d'aller à l'écran tant qu'on n'écrit pas <code>2&gt;</code> ou <code>2&gt;&amp;1</code>.</details>

Voir les FD d'un process en vrai — indispensable en incident :

```bash
$ ls -l /proc/4712/fd
lrwx------ 1 dataeng dataeng 64 Sep  9 14:02 0 -> /dev/pts/3
l-wx------ 1 dataeng dataeng 64 Sep  9 14:02 1 -> /var/log/app.log
l-wx------ 1 dataeng dataeng 64 Sep  9 14:02 2 -> /var/log/app.log
lrwx------ 1 dataeng dataeng 64 Sep  9 14:02 3 -> 'socket:[184023]'
lr-x------ 1 dataeng dataeng 64 Sep  9 14:02 4 -> /data/ventes.csv (deleted)
```

- ligne `0` : l'entrée standard est le terminal `pts/3` → le process a été lancé à la main.
- lignes `1` et `2` : sortie et erreurs vont **au même fichier**.
- ligne `3` : une socket, identifiée par un numéro d'inode ; `ss -tanp` la reliera à un port.
- ligne `4` : **`(deleted)`** — exactement le bug du paragraphe précédent, en flagrant délit.

**La limite de FD** est la panne n° 2 des services data :

```bash
$ ulimit -n          # limite SOUPLE du shell courant
1024
$ ulimit -Hn         # limite DURE (plafond que l'utilisateur peut se donner)
524288
$ cat /proc/4712/limits | grep 'open files'
Max open files            1024                 524288               files
```

Chaque connexion Kafka, chaque partition Parquet ouverte, chaque socket HTTP consomme un FD.
À 1024, tu prends `Too many open files` (`EMFILE`). Sous systemd, la limite d'un service ne vient
**pas** de `/etc/security/limits.conf` mais de `LimitNOFILE=` dans l'unit.

### 3.4 Redirections et tubes : le shell recâble les FD

Le shell ne « connecte » rien : entre `fork()` et `exec()`, il **réécrit la table des FD de l'enfant**
avec `dup2()`. Le programme, lui, écrit bêtement sur son FD 1 sans jamais savoir où ça va.

| Syntaxe | Effet |
|---|---|
| `> f` | stdout → `f`, **écrase** |
| `>> f` | stdout → `f`, **ajoute** |
| `2> f` | stderr → `f` |
| `> f 2>&1` | stdout → `f`, **puis** stderr → là où pointe stdout (donc `f`) |
| `&> f` | idem, raccourci bash |
| `2>/dev/null` | jeter les erreurs |
| `< f` | stdin ← `f` |
| `<<EOF … EOF` | *here-document* : stdin ← texte inline |
| `<<< "chaine"` | *here-string* |
| `a \| b` | stdout de `a` → stdin de `b` |
| `a \|& b` | stdout **et** stderr de `a` → `b` |
| `<(cmd)` | *process substitution* : la sortie de `cmd` vue comme un fichier (`diff <(a) <(b)`) |

> ⚠️ **PIÈGE — l'ordre des redirections.** `cmd 2>&1 > f` **n'envoie pas** les erreurs dans `f`.
> Le shell lit de gauche à droite : `2>&1` copie la destination *actuelle* de 1 (le terminal) dans 2,
> **ensuite** `> f` déplace 1 vers le fichier. Résultat : stdout dans `f`, stderr à l'écran.
> La forme correcte est **`cmd > f 2>&1`** : d'abord la destination finale, ensuite la copie.

> 🧠 **MÉMO** — `2>&1` se lit **« 2 va où va 1, maintenant »**. C'est une *photo*, pas un lien
> permanent. Donc on la prend **après** avoir placé 1.

Un tube (`|`) est un **tampon en mémoire du noyau de 64 Kio** entre deux processus lancés
**simultanément**. Deux conséquences majeures :

- Le producteur **se bloque** quand le tampon est plein et que le consommateur ne lit pas : c'est un
  contrôle de flux gratuit (le même principe que la fenêtre TCP de `R06`).
- Si le consommateur ferme le tube et meurt, le producteur reçoit **`SIGPIPE` (13)** et meurt avec le
  code **141** (= 128 + 13). C'est exactement ce qui arrête `yes | head -3` — ce n'est pas une erreur.

> ⚠️ **PIÈGE — le code de retour d'un pipeline** est celui de **la dernière commande**.
> `curl -f url | wc -l` renvoie 0 même si `curl` a échoué. Remèdes : `set -o pipefail` (le pipeline
> prend le premier code non nul), ou le tableau `${PIPESTATUS[@]}`.

> ⚠️ **PIÈGE — la bufferisation, tueur silencieux de logs.** La libc bufferise stdout **par ligne quand
> c'est un terminal**, mais **par blocs (4 Kio) quand c'est un fichier ou un tube**. D'où : ton script
> Python affiche tout en interactif et **rien** dans les logs Airflow ou `kubectl logs` pendant une heure,
> puis tout d'un coup. Remèdes : `python -u`, `PYTHONUNBUFFERED=1` (à mettre dans tout Dockerfile Python),
> `stdbuf -oL -eL cmd`, ou `flush=True`.

> ❓ **RETIENS ÇA** — Pourquoi un conteneur Python n'affiche-t-il ses logs que par paquets, ou à la fin ?
> <details><summary>→ réponse</summary><br>Parce que stdout n'est plus un terminal mais un tube : la libc passe de la bufferisation <b>par ligne</b> à la bufferisation <b>par blocs de 4 Kio</b>. Correction : <code>PYTHONUNBUFFERED=1</code> ou <code>python -u</code>.</details>

---

## 4. Les processus : PID, fork, exec, états

### 4.1 Créer un processus : la copie puis la mutation

**Le problème** : comment un programme en lance-t-il un autre ? La réponse Unix est étrange et
géniale : **il ne le lance pas, il se dédouble puis se transforme.**

- **`fork()`** — le noyau crée une **copie quasi identique** du processus appelant : même code, même
  mémoire (en *copy-on-write* : les pages ne sont réellement dupliquées qu'à la première écriture),
  mêmes descripteurs ouverts. La seule différence est la valeur de retour :
  **0 chez l'enfant, le PID de l'enfant chez le parent, −1 en cas d'échec.**
- **`execve()`** — le processus **remplace son propre programme** par un autre. Même PID, même parent,
  mêmes FD (sauf ceux marqués `close-on-exec`) — mais tout l'espace mémoire est jeté et reconstruit.

```
   bash (PID 3120)
       │
       │ fork()
       ├──────────────► copie (PID 4712)     ← retour 0 : "je suis l'enfant"
       │  retour 4712                │
       │                             │ dup2()  ← le shell installe ici les redirections
       │                             │ execve("/usr/bin/python3", …)
       │                             ▼
       │                        python3 (PID 4712)   ← même PID, autre programme
       │ wait(4712)  ← le parent se bloque
       │                             │ exit(0)
       ◄─────────────────────────────┘  code de sortie 0
```

C'est **entre le `fork` et le `exec`** que le shell applique les redirections, le `nice`, le changement
d'utilisateur, la limite de FD. Voilà pourquoi séparer les deux étapes est utile plutôt qu'inutilement
compliqué.

> 🧠 **MÉMO** — **fork = photocopie, exec = greffe de cerveau.** La photocopie garde le même dossier
> administratif (PID, FD, cwd) ; la greffe change le contenu de la tête sans changer le dossier.

> ❓ **RETIENS ÇA** — Que renvoie `fork()` dans le processus enfant ?
> <details><summary>→ réponse</summary><br><b>0</b>. Le parent, lui, reçoit le <b>PID de l'enfant</b> (et −1 si la création a échoué). C'est la seule chose qui distingue les deux copies immédiatement après l'appel.</details>

Chiffres à connaître : le PID est un entier positif ; `/proc/sys/kernel/pid_max` vaut **32768** par
défaut historiquement, et **4 194 304** sur la plupart des systèmes systemd 64 bits. Les PID sont
attribués séquentiellement puis **réutilisés** après bouclage — d'où le danger d'un `kill $(cat pid)`
sur un fichier PID périmé.

### 4.2 Les états d'un processus

```
                     ┌──────────────────────────────────────────┐
                     │                                          │
   fork ──► R (runnable) ──ordonnanceur──► R (running) ──exit──► Z (zombie) ──wait()──► disparu
                 ▲                 │  │
                 │                 │  └── attend un E/S lente ──► D (uninterruptible sleep)
                 │  SIGCONT        │                                    │ (E/S finie)
                 │                 └── attend un évènement ──► S (interruptible sleep)
                 │                                                      │ (évènement)
                 └───── T (stopped, SIGSTOP/SIGTSTP) ◄──────────────────┘
```

| Code `ps` | État | Ce que ça veut dire en pratique |
|---|---|---|
| `R` | Running / runnable | Il consomme du CPU ou attend son tour |
| `S` | Sleep interruptible | **L'état normal de 95 % des process** : il attend une socket, un timer, une entrée |
| `D` | Sleep **non interruptible** | Bloqué dans le noyau sur une E/S (disque, NFS). **`kill -9` ne le touche pas.** |
| `T` | Stopped | Reçu `SIGSTOP`/`SIGTSTP` (Ctrl-Z) |
| `Z` | Zombie | **Terminé**, mais le parent n'a pas encore lu son code de sortie |
| `I` | Idle | Thread noyau inactif (n'entre pas dans la charge) |

Les suffixes : `<` priorité haute, `N` priorité basse (nice > 0), `s` chef de session,
`l` multi-thread, `+` dans le groupe de premier plan du terminal.

> ⚠️ **PIÈGE — l'état `D` ne se tue pas.** Un process bloqué sur un NFS mort ou un disque défaillant
> reste en `D` **malgré `kill -9`**, parce qu'il n'exécute plus aucune instruction en espace utilisateur :
> il n'y a personne pour recevoir le signal. Il ne partira qu'au retour de l'E/S, ou au reboot. Sur Linux,
> l'état `D` **compte dans la charge moyenne**, ce qui explique un load average à 40 sur une machine dont
> le CPU est à 3 %.

### 4.3 Zombie et orphelin : la confusion à ne plus jamais faire

C'est *la* question de tri en entretien. Les deux sont des situations opposées :

|  | **Zombie** (`Z`, `<defunct>`) | **Orphelin** |
|---|---|---|
| Qui est mort ? | **L'enfant** | **Le parent** |
| Que se passe-t-il ? | Le parent n'appelle pas `wait()` : le noyau garde la fiche pour lui donner le code de sortie | L'enfant est **ré-adopté par PID 1** |
| Ressources consommées | **Une entrée de table + un PID.** Zéro mémoire, zéro CPU | Aucune anomalie |
| C'est grave ? | Seulement en masse : **fuite de PID** → `fork: Resource temporarily unavailable` | **Non**, c'est le fonctionnement normal |
| Comment on corrige ? | On tue **le parent** (`kill -9` sur un zombie n'a aucun effet : il est déjà mort) | Rien à corriger |

> ❓ **RETIENS ÇA** — Peut-on tuer un processus zombie avec `kill -9` ?
> <details><summary>→ réponse</summary><br><b>Non.</b> Il est déjà mort — il ne reste qu'une entrée dans la table des processus. Le seul moyen est que son <b>parent</b> appelle <code>wait()</code>, ou que le parent meure : le zombie est alors ré-adopté par PID 1, qui moissonne en boucle.</details>

**Pourquoi ça compte dans un conteneur.** Un conteneur a son propre espace de noms PID : **ton
application est PID 1**. Or PID 1 a deux responsabilités qu'un serveur web ne remplit jamais :
moissonner les orphelins et gérer les signaux. Un `docker run python app.py` où l'app crée des
sous-process finit avec une table pleine de zombies. Remède : `docker run --init` (injecte `tini`),
ou `ENTRYPOINT ["tini","--"]`, ou `shareProcessNamespace` / un vrai superviseur.

### 4.4 L'arbre des processus

Tout processus a un **PPID**. La racine est **PID 1** (`systemd` sur une machine, ton app dans un
conteneur). Il n'y a qu'un seul arbre, et il se lit :

```bash
$ pstree -p 1 | head
systemd(1)─┬─containerd(842)─┬─{containerd}(861)
           ├─dockerd(1104)───{dockerd}(1122)
           ├─sshd(1290)───sshd(4102)───bash(4110)───python3(4712)
           └─java(2201)─┬─{GC Thread#0}(2211)
                        └─{VM Thread}(2214)
```

Les noms entre accolades sont des **threads** (des « tâches » partageant l'espace mémoire), pas des
processus. Une JVM Spark à 3 000 « process » dans `top` est en réalité 1 process et 3 000 threads —
d'où l'option `top -H` pour les voir, et `ps -eLf` pour les compter.

**Lire l'état d'un process : les deux commandes à connaître par cœur.**

```bash
$ ps aux | head -3
USER   PID %CPU %MEM    VSZ    RSS TTY  STAT START  TIME COMMAND
root     1  0.0  0.1 168404  12760 ?    Ss   Sep05  1:12 /sbin/init
spark 4712 98.7 24.3 9871234 3982104 ?  Rl   14:02 41:08 java -Xmx4g -cp …
```

- `VSZ 9 871 234` Kio ≈ **9,4 Gio d'espace d'adressage virtuel** — pour une JVM `-Xmx4g`, c'est
  normal : réservation du tas, piles de threads, bibliothèques mappées. **Ce n'est pas de la RAM.**
- `RSS 3 982 104` Kio ≈ **3,8 Gio réellement en RAM**. C'est *cette* colonne que l'OOM killer regarde.
- `STAT Rl` : en cours d'exécution (`R`), multi-thread (`l`).
- `%CPU 98,7` : **par rapport à un seul cœur**. Sur 8 cœurs, le maximum affiché est 800.

`ps aux` (syntaxe BSD) et `ps -ef` (syntaxe POSIX) montrent la même chose autrement. La forme
réellement utile en production est le format choisi :

```bash
$ ps -eo pid,ppid,stat,ni,rss,etime,cmd --sort=-rss | head -4
   PID   PPID STAT  NI    RSS     ELAPSED CMD
  4712   4110 Rl     0 3982104    41:12   java -Xmx4g …
  2201      1 Sl     0  812340  4-02:11:07 java -jar collector.jar
  1104      1 Ssl    0   98220  4-02:11:31 /usr/bin/dockerd
```

`ELAPSED 4-02:11:07` = 4 jours, 2 h 11 min. Comparer `ELAPSED` à `TIME` (temps CPU) distingue
immédiatement un process qui travaille d'un process qui attend.

### 4.5 Ordonnancement et `nice`

**Le problème** : 200 processus prêts, 8 cœurs. Qui passe ?

L'ordonnanceur par défaut de Linux distribue le CPU **proportionnellement à un poids**, en donnant la
main à celui qui a le moins été servi (historiquement CFS, remplacé par EEVDF depuis le noyau 6.6 ;
le modèle mental est le même). Ce poids se règle avec le **nice** :

| Valeur | Sens | Qui peut la mettre |
|---|---|---|
| **−20** | La plus prioritaire | root uniquement |
| **0** | Défaut | tout le monde |
| **+19** | La plus « gentille » | tout le monde |

« Nice » = *gentillesse* : **plus le nombre est grand, plus le process est poli, moins il a de CPU.**
Chaque incrément vaut environ **×1,25 de poids**, soit à peu près **10 % de CPU d'écart** par niveau.

```bash
$ nice -n 10 python etl_lourd.py       # lancer avec nice = 10
$ renice -n 5 -p 4712                  # changer à chaud
$ chrt -f 50 ./collecteur              # temps réel SCHED_FIFO, priorité 50 (1-99)
$ ionice -c 3 -p 4712                  # priorité disque "idle" — souvent PLUS utile que nice
```

> ⚠️ **PIÈGE** — Un utilisateur non root ne peut **qu'augmenter** son nice (se dégrader), jamais le
> diminuer, même pour revenir à 0. Et `nice` ne joue **que sur le CPU** : un job qui sature le disque
> reste nuisible malgré `nice 19`. Pour l'E/S, c'est `ionice` (classes : 1 temps réel, 2 best-effort
> par défaut, 3 idle).

---

## 5. Les signaux : la seule façon de parler à un processus qui tourne

### 5.1 Le problème

Un process tourne. Tu veux lui dire « arrête-toi », « recharge ta config », « fais une pause ».
Il n'a pas d'API, pas de port ouvert. **Le signal est l'interruption logicielle** que le noyau lui
délivre : il suspend l'exécution normale et saute dans un gestionnaire.

Un processus peut, pour chaque signal, **le rattraper** (installer un handler), **l'ignorer**, ou
laisser l'**action par défaut** s'appliquer. Sauf pour deux d'entre eux.

### 5.2 Les signaux à connaître par cœur

| N° | Nom | Action par défaut | Quand il arrive | Rattrapable ? |
|---:|---|---|---|---|
| **1** | `SIGHUP` | Terminer | Terminal fermé — **détourné en « recharge ta config »** par nginx, rsyslog, HAProxy | oui |
| **2** | `SIGINT` | Terminer | **Ctrl-C** | oui |
| **3** | `SIGQUIT` | Terminer + **core dump** | Ctrl-\ — sur la **JVM : affiche un thread dump**, sans tuer | oui |
| **9** | `SIGKILL` | **Tuer, point** | `kill -9` | **NON** |
| **13** | `SIGPIPE` | Terminer | Écrire dans un tube dont le lecteur est parti | oui |
| **15** | `SIGTERM` | Terminer | **Le défaut de `kill`**, de `docker stop`, de Kubernetes | oui |
| **17** | `SIGCHLD` | Ignorer | Un enfant s'est terminé → déclenche le `wait()` du parent | oui |
| **18** | `SIGCONT` | Reprendre | `fg` / `bg` | oui |
| **19** | `SIGSTOP` | **Suspendre** | `kill -STOP` | **NON** |
| **20** | `SIGTSTP` | Suspendre | **Ctrl-Z** | oui |
| **11** | `SIGSEGV` | Tuer + core | Accès mémoire invalide | oui (rarement utile) |
| **6** | `SIGABRT` | Tuer + core | `abort()`, assertion, `panic` | oui |
| **10 / 12** | `SIGUSR1` / `SIGUSR2` | Terminer | **Libres pour l'application** : rotation de logs, bascule de niveau de debug | oui |

> 🧠 **MÉMO — « 9 tue, 15 demande, 1 recharge. »** Et le nombre magique du shell :
> **code de sortie = 128 + numéro du signal.** Donc **137 = 128 + 9 (SIGKILL)**,
> **143 = 128 + 15 (SIGTERM)**, **130 = Ctrl-C**, **141 = SIGPIPE**.
> Quand Kubernetes affiche `Exit Code: 137`, il ne dit rien d'autre que « quelqu'un a envoyé un `kill -9` ».

> ❓ **RETIENS ÇA** — Quels sont les deux seuls signaux qu'un processus ne peut ni rattraper, ni bloquer, ni ignorer ?
> <details><summary>→ réponse</summary><br><b>SIGKILL (9)</b> et <b>SIGSTOP (19)</b>. C'est le noyau qui les applique directement, sans passer par le code du processus. Corollaire : un process en <code>kill -9</code> n'exécute <b>aucun</b> code de nettoyage — pas de flush, pas de commit, pas de suppression de fichier temporaire.</details>

> ❓ **RETIENS ÇA** — Que signifie un code de sortie 137 ?
> <details><summary>→ réponse</summary><br>128 + 9 : le processus a été tué par <b>SIGKILL</b>. Dans un conteneur, c'est presque toujours l'<b>OOM killer</b> (dépassement de <code>memory.max</code>) ou un délai de grâce d'arrêt expiré.</details>

### 5.3 L'arrêt propre : la séquence que tout le monde te demandera

```
 t=0     SIGTERM ──►  l'application reçoit le signal
                      ├─ arrête d'accepter du nouveau travail
                      ├─ termine les requêtes en cours
                      ├─ commite les offsets Kafka / flush les buffers
                      ├─ ferme proprement les connexions à la base
                      └─ exit(0)                       ◄── idéal : bien avant l'échéance
 …
 t=grâce SIGKILL ──►  si toujours vivant : exécution stoppée net, aucun code exécuté
```

| Contexte | Délai de grâce par défaut | Paramètre |
|---|---|---|
| `docker stop` | **10 s** | `docker stop -t 30` |
| Kubernetes | **30 s** | `terminationGracePeriodSeconds` |
| systemd | **90 s** | `TimeoutStopSec=` (défaut `DefaultTimeoutStopSec=90s`) |

Pour un data engineer, cette séquence n'est pas une curiosité : c'est la différence entre un consumer
Kafka qui **committe ses offsets** avant de partir (redémarrage sans doublon ni perte) et un consumer
tué à la hache qui rejoue 40 000 messages. Même chose pour un writer Parquet : `SIGKILL` en plein
milieu laisse un fichier tronqué que Spark refusera de lire.

```bash
$ kill 4712              # SIGTERM (15) — le défaut, TOUJOURS commencer par là
$ kill -TERM 4712        # identique, explicite
$ kill -HUP $(pidof nginx)   # recharge de configuration sans coupure
$ kill -QUIT <pid-jvm>   # thread dump JVM dans les logs, le process survit
$ kill -9 4712           # dernier recours, après avoir attendu
$ pkill -f 'python etl_'  # par motif de ligne de commande
$ killall -TERM python3   # par nom exact d'exécutable
$ timeout -s TERM 30 ./job.sh   # TERM après 30 s ; -k 10 ajoute un KILL 10 s plus tard
```

> ⚠️ **PIÈGE — PID 1 dans un conteneur ignore SIGTERM par défaut.** Le noyau applique une règle
> spéciale : pour PID 1, **les actions par défaut des signaux ne s'appliquent pas**. Si ton application
> n'installe pas explicitement de handler `SIGTERM`, le `docker stop` **ne fait rien** pendant 10 s,
> puis `SIGKILL`. Symptômes : tout arrêt de conteneur prend exactement 10 s (ou 30 s en Kubernetes),
> et les données en cours sont perdues. Remèdes : gérer le signal dans le code, ou utiliser un init
> (`--init`, `tini`).

> ⚠️ **PIÈGE — la forme shell d'un `CMD` Docker.** `CMD python app.py` lance `/bin/sh -c "python app.py"` :
> **c'est `sh` qui est PID 1**, et `sh` ne transmet pas les signaux à son enfant. Utilise toujours la
> **forme exec** : `CMD ["python", "app.py"]`. Une ligne de Dockerfile, et l'arrêt propre fonctionne.

---

## 6. Permissions : rwx, octal, umask, bits spéciaux

### 6.1 Le problème et la structure à trois classes

Le noyau doit trancher instantanément « ce processus a-t-il le droit ? ». Le modèle Unix est
volontairement minuscule : **3 classes × 3 droits = 9 bits**, plus 3 bits spéciaux.

```
  -  rwx  r-x  r--    1  spark  data   3892401  Sep  9 14:02  ventes.csv
  ^  ---  ---  ---    ^  -----  ----
  |   |    |    |     |    |     └── GROUPE propriétaire
  |   |    |    |     |    └──────── UTILISATEUR propriétaire
  |   |    |    |     └───────────── nlink (nb de liens physiques)
  |   |    |    └── AUTRES  (others)   r-- = 4
  |   |    └─────── GROUPE  (group)    r-x = 5
  |   └──────────── UTILISATEUR (user) rwx = 7      →  0754
  └── type : - fichier · d répertoire · l lien · c/b périph · p FIFO · s socket
```

**Règle d'évaluation, souvent mal comprise** : le noyau applique **la première classe qui correspond,
et s'arrête là**. Tu es le propriétaire ? On n'applique **que** les droits « user », même si « others »
est plus permissif. D'où le grand classique : `chmod 077 fichier` (`----rwxrwx`) rend un fichier
**illisible par son propriétaire** et lisible par tout le monde.

**Les valeurs octales** : `r = 4`, `w = 2`, `x = 1`. On additionne.

| Octal | Bits | Sens usuel |
|---:|---|---|
| **7** | rwx | tout |
| **6** | rw- | lecture/écriture (fichier de données) |
| **5** | r-x | lecture/traversée (répertoire ou binaire partagé) |
| **4** | r-- | lecture seule |
| **0** | --- | rien |

| Mode | Cas typique |
|---|---|
| **644** | fichier de données standard |
| **755** | script ou binaire exécutable, répertoire standard |
| **600** | secret : clé SSH privée, `.pgpass`, `.netrc` — **exigé** par les outils |
| **700** | répertoire personnel privé, `~/.ssh` |
| **664 / 775** | fichier / répertoire d'équipe (groupe en écriture) |

### 6.2 `x` sur un répertoire ne veut pas dire « exécuter »

C'est **le** point qui bloque tout le monde :

| Bit | Sur un **fichier** | Sur un **répertoire** |
|---|---|---|
| `r` | lire le contenu | **lister les noms** (`ls`) |
| `w` | modifier le contenu | **créer / supprimer / renommer** des entrées (nécessite aussi `x`) |
| `x` | exécuter | **traverser** : entrer dedans, accéder à un fichier dont on connaît le nom |

Conséquences que tu croiseras :

- `r-x` sur un répertoire : tu peux lister et lire. `--x` : tu **ne peux pas lister**, mais si tu
  connais le nom exact, tu peux ouvrir le fichier. C'est le mode des répertoires « boîte aux lettres ».
- `w` sur un répertoire suffit à **supprimer un fichier qui ne t'appartient pas**, même en lecture
  seule : la suppression modifie le *répertoire*, pas le fichier. D'où l'invention du sticky bit.
- Pour accéder à `/a/b/c.csv`, il te faut `x` sur `/`, sur `/a` **et** sur `/a/b`. Un seul `x` manquant
  dans la chaîne = `Permission denied` — et c'est la cause n° 1 des `Permission denied` incompréhensibles.

> ❓ **RETIENS ÇA** — Que permet exactement le bit `x` sur un répertoire ?
> <details><summary>→ réponse</summary><br>De <b>traverser</b> le répertoire : y entrer et accéder à un élément dont on connaît le nom. Sans <code>x</code>, même avec <code>r</code>, on peut lister les noms mais <b>rien ouvrir</b> à l'intérieur. Il faut <code>x</code> sur <b>tous</b> les répertoires du chemin.</details>

### 6.3 `umask` : ce qu'on retire à la naissance

**Le problème** : quel mode a un fichier créé par un programme ? Les appels `open()`/`mkdir()`
demandent **666** pour un fichier et **777** pour un répertoire (jamais `x` sur un fichier, c'est
volontaire). Le noyau retire ensuite les bits du `umask` du processus.

```
  mode final = mode demandé  ET  NON(umask)     — en pratique : une soustraction bit à bit
```

**Exercice corrigé n° 1 — `umask 027`**

```
  Fichier :  demandé 666  =  rw- rw- rw-
             umask   027  =  --- -w- rwx      (les bits à retirer)
             ──────────────────────────────
             résultat 640  =  rw- r-- ---     → propriétaire rw, groupe r, autres rien
  
  Répertoire : demandé 777  =  rwx rwx rwx
               umask   027  =  --- -w- rwx
               ─────────────────────────────
               résultat 750  =  rwx r-x ---
```

Calcul mental : **7 − 0 = 7, 7 − 2 = 5, 7 − 7 = 0** pour le répertoire ; pour le fichier on part de 6 :
**6 − 0 = 6, 6 − 2 = 4, 6 − 7 → 0** (on ne descend jamais sous 0).

| umask | Fichier | Répertoire | Contexte |
|---|---|---|---|
| **022** | 644 | 755 | défaut root et RHEL — lisible par tous |
| **002** | 664 | 775 | défaut utilisateur Debian/Ubuntu (groupe privé par utilisateur) |
| **027** | 640 | 750 | durci : rien pour « others » |
| **077** | 600 | 700 | secrets, machines multi-locataires |

> ⚠️ **PIÈGE** — `umask` est un attribut **du processus**, hérité par les enfants. Le modifier dans ton
> shell ne change rien pour un service systemd (`UMask=` dans l'unit), ni pour un conteneur, ni pour un
> job cron. Et il **ne s'applique jamais rétroactivement** : `umask 077` ne protège pas les fichiers déjà écrits.

> ❓ **RETIENS ÇA** — Avec `umask 022`, quel est le mode d'un fichier nouvellement créé ?
> <details><summary>→ réponse</summary><br><b>644</b> (666 − 022). Et <b>755</b> pour un répertoire (777 − 022). Le bit <code>x</code> n'est jamais donné automatiquement à un fichier.</details>

### 6.4 Les trois bits spéciaux

Ils s'ajoutent en **quatrième chiffre octal, à gauche** :

| Bit | Octal | Sur un fichier | Sur un répertoire | Vu dans `ls -l` |
|---|---:|---|---|---|
| **setuid** | **4** | s'exécute avec l'**UID du propriétaire** | (sans effet sous Linux) | `rws` en position user |
| **setgid** | **2** | s'exécute avec le **GID du groupe** | **les fichiers créés héritent du groupe du répertoire** | `rws` en position groupe |
| **sticky** | **1** | (obsolète) | **seul le propriétaire d'un fichier peut le supprimer** | `rwt` en position autres |

```bash
$ ls -l /usr/bin/passwd
-rwsr-xr-x 1 root root 68208 Mar 23 15:17 /usr/bin/passwd
#  ^ le 's' : n'importe quel utilisateur l'exécute AVEC LES DROITS DE ROOT
#  Nécessaire : passwd écrit dans /etc/shadow, qui est en 640 root:shadow.

$ ls -ld /tmp
drwxrwxrwt 10 root root 4096 Sep  9 14:31 /tmp
#  ^^^^^^^^t : tout le monde écrit (777), mais le 't' interdit de supprimer
#  le fichier d'un autre. Mode complet : 1777.

$ ls -ld /data/projet
drwxrws--- 4 root data 4096 Sep  9 11:02 /data/projet
#  le 's' du groupe (setgid) : tout fichier créé ici appartiendra au groupe 'data',
#  quel que soit le groupe primaire de son auteur. LA solution du répertoire partagé.

$ chmod 2775 /data/projet    # setgid + rwxrwxr-x
$ find / -perm -4000 -type f 2>/dev/null   # audit : tous les binaires setuid
```

> ⚠️ **PIÈGE** — Le bit **setuid est ignoré sur les scripts shell** sous Linux (trou de sécurité connu
> et fermé depuis longtemps). Un `chmod 4755 script.sh` ne donne aucun privilège. Pour élever les droits
> d'un script, on passe par `sudo` avec une règle précise dans `/etc/sudoers`.

> 🧠 **MÉMO — 4-2-1, de haut en bas :** **4 = setUID (l'Utilisateur en haut)**, **2 = setGID (le Groupe
> au milieu)**, **1 = sTicky (les auTres en bas)**. Même ordre que `rwx` = 4-2-1. Rien de nouveau à retenir.

**Alternative moderne aux setuid : les capabilities.** Découper les pouvoirs de root en ~40 privilèges
distincts au lieu du tout-ou-rien :

```bash
$ getcap /usr/bin/ping
/usr/bin/ping cap_net_raw=ep        # forger des paquets ICMP, sans être root
$ setcap 'cap_net_bind_service=+ep' /opt/app/server   # écouter sur le port 443 sans root
```

À connaître : `CAP_NET_BIND_SERVICE` (ports < 1024), `CAP_NET_RAW` (sockets brutes, `tcpdump`),
`CAP_NET_ADMIN` (config réseau), `CAP_SYS_PTRACE` (`strace` sur autrui), `CAP_SYS_ADMIN` (le fourre-tout,
≈ root). En Kubernetes, c'est `securityContext.capabilities.drop: ["ALL"]` puis `add:` le strict minimum.

### 6.5 ACL : quand trois classes ne suffisent plus

**Le problème** : le répertoire appartient à `data`, mais tu veux donner un accès en lecture à *une*
personne de l'équipe BI, sans créer un groupe ni changer le propriétaire. Le modèle à trois classes
ne sait pas exprimer ça. Les **ACL POSIX** l'ajoutent :

```bash
$ setfacl -m u:alice:r-- /data/ventes.csv     # ajouter un utilisateur
$ setfacl -m g:bi:r-x /data/exports           # ajouter un groupe
$ setfacl -d -m g:bi:r-x /data/exports        # ACL PAR DÉFAUT : héritée par les nouveaux fichiers
$ setfacl -x u:alice /data/ventes.csv         # retirer une entrée
$ setfacl -b /data/ventes.csv                 # tout effacer

$ ls -l /data/ventes.csv
-rw-r-----+ 1 spark data 3892401 Sep  9 14:02 ventes.csv
#          ^ le '+' signale la présence d'ACL — sinon totalement invisible

$ getfacl /data/ventes.csv
user::rw-
user:alice:r--          # l'entrée ajoutée
group::r--
mask::r--               # PLAFOND : borne les droits effectifs de toutes les entrées nommées
other::---
```

> ⚠️ **PIÈGE — le `mask` ACL.** C'est un **plafond** appliqué aux utilisateurs nommés et aux groupes.
> Si `mask::r--` et que tu as donné `u:alice:rwx`, alice a **r-- effectif**. `getfacl` l'annote
> `#effective:r--`. Pire : un `chmod g+w` sur le fichier **modifie le mask** et peut ouvrir ou fermer
> silencieusement toutes tes ACL. Deuxième piège : `cp` **ne conserve pas** les ACL sans `-p`/`--preserve=all`,
> et beaucoup d'outils (rsync sans `-A`, tar sans `--acls`) les perdent aussi.

---

## 7. Utilisateurs et groupes

Pour le noyau, un utilisateur **est un entier** (UID). Le nom n'existe que dans des fichiers texte
consultés par les bibliothèques de l'espace utilisateur.

```
/etc/passwd   dataeng:x:1000:1000:Data Engineer:/home/dataeng:/bin/bash
              ───┬─── │ ──┬─ ──┬─ ──────┬───── ──────┬─────── ───┬────
                 │    │   │    │        │            │           └ shell de connexion
                 │    │   │    │        │            └ répertoire personnel
                 │    │   │    │        └ GECOS (commentaire)
                 │    │   │    └ GID primaire
                 │    │   └ UID
                 │    └ 'x' = le hash est dans /etc/shadow (mode 640 root:shadow)
                 └ nom de connexion
              (lisible par tous : mode 644)

/etc/group    data:x:2000:dataeng,alice,bob        ← membres SECONDAIRES uniquement
/etc/shadow   dataeng:$y$j9T$…:19975:0:99999:7:::  ← hash, dates d'expiration. Mode 640.
```

| Plage d'UID | Usage |
|---|---|
| **0** | **root** — c'est l'UID qui compte, pas le nom. Un utilisateur d'UID 0 *est* root |
| 1-999 | comptes système (services). `nologin` comme shell |
| **≥ 1000** | comptes humains (`UID_MIN` dans `/etc/login.defs`) |
| 65534 | `nobody` |

**Groupe primaire vs secondaires** : le primaire (`GID` de `/etc/passwd`) est celui **attribué aux
fichiers que tu crées**. Les secondaires n'ouvrent que des droits.

```bash
$ id
uid=1000(dataeng) gid=1000(dataeng) groups=1000(dataeng),27(sudo),2000(data),999(docker)

$ usermod -aG data alice     # AJOUTER un groupe secondaire — le -a est VITAL
$ usermod -G data alice      # ⚠ SANS -a : REMPLACE tous les secondaires. Casse des accès.
```

> ⚠️ **PIÈGE** — Un changement de groupe n'est **pas rétroactif sur les sessions ouvertes** : les
> groupes sont figés dans le processus à la connexion. Après `usermod -aG`, il faut **se reconnecter**
> (ou `newgrp data`) pour que `id` change. Le classique : « je t'ai mis dans le groupe docker » →
> « ça ne marche toujours pas » → il fallait rouvrir la session.

> ⚠️ **PIÈGE — appartenir au groupe `docker` équivaut à être root.** Le groupe donne accès à la socket
> `/var/run/docker.sock` ; avec elle on monte `/` dans un conteneur privilégié. À traiter comme un `sudo`
> sans mot de passe.

`sudo` vs `su` : `su - alice` ouvre un **shell de connexion** complet (l'environnement d'alice) ;
`su alice` garde ton environnement — source d'un `PATH` incohérent. `sudo` exécute **une** commande
selon `/etc/sudoers`, en journalisant qui a fait quoi. Éditer les règles **uniquement avec `visudo`**,
qui valide la syntaxe : un `/etc/sudoers` invalide t'enferme dehors.

---

## 8. systemd : le PID 1 moderne

### 8.1 Le problème que systemd résout

Les scripts SysV d'avant lançaient les services **en séquence, dans l'ordre alphabétique de leur
numéro**, chacun devant gérer lui-même son démonisation, son fichier PID, ses logs, ses redémarrages.
Trois défauts rédhibitoires : c'est lent (tout est sérialisé), c'est fragile (un fichier PID périmé et
plus rien ne marche), et **personne ne sait vraiment quels processus appartiennent à quel service**.

systemd répond par trois idées :

1. **Un modèle déclaratif** : tu décris l'état voulu, pas la procédure.
2. **Le parallélisme par dépendances** : ce qui n'a pas de raison d'attendre démarre en même temps.
3. **Le cgroup comme frontière** : tous les processus d'un service vivent dans **son** cgroup.
   Plus jamais de processus orphelin qu'on ne sait pas rattacher, et le comptage mémoire/CPU devient exact.

### 8.2 Les types d'unités

| Extension | Rôle |
|---|---|
| `.service` | Un démon ou une tâche |
| `.socket` | Une socket ; systemd écoute et **démarre le service à la première connexion** |
| `.target` | Un **point de synchronisation** = un groupe d'unités (l'équivalent des runlevels) |
| `.timer` | Un déclencheur temporel (remplace cron) |
| `.mount` / `.automount` | Un montage (généré automatiquement depuis `/etc/fstab`) |
| `.path` | Déclenche sur apparition/modification d'un fichier |
| `.slice` / `.scope` | Arborescence de cgroups pour la répartition des ressources |

**Les targets clés**, dans l'ordre du démarrage :
`sysinit.target` (montages, swap, udev, journal) → `basic.target` (sockets, timers, chemins) →
`multi-user.target` (**le mode serveur**, tous les services réseau) → `graphical.target`.
`network-online.target` est **l'exception à connaître** : `network.target` signifie seulement « la
pile réseau est configurée », pas « une IP est joignable ».

### 8.3 Anatomie d'une unit de service

```ini
# /etc/systemd/system/etl-ventes.service
[Unit]
Description=ETL quotidien des ventes
Documentation=https://wiki.interne/etl-ventes
After=network-online.target postgresql.service    # ORDRE seulement
Wants=network-online.target                       # dépendance SOUPLE
Requires=postgresql.service                       # dépendance DURE : si PG s'arrête, on s'arrête

[Service]
Type=simple                 # défaut : le process principal reste au premier plan
User=etl
Group=data
WorkingDirectory=/opt/etl
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=-/etc/etl/env          # le '-' : ne pas échouer si absent
ExecStart=/opt/etl/venv/bin/python -m etl.run --source ventes
ExecReload=/bin/kill -HUP $MAINPID
Restart=on-failure          # redémarre si code de sortie != 0 ou signal fatal
RestartSec=10               # attendre 10 s (défaut : 100 ms)
TimeoutStopSec=120          # laisser 120 s pour finir proprement (défaut 90 s)
KillSignal=SIGTERM          # défaut
LimitNOFILE=65536           # limite de descripteurs — LA ligne oubliée
MemoryMax=8G                # cgroup : au-delà, OOM kill dans CE cgroup uniquement
CPUQuota=200%               # 2 cœurs au maximum
PrivateTmp=true             # /tmp isolé, jeté à l'arrêt
NoNewPrivileges=true        # interdit toute élévation via setuid
ProtectSystem=strict        # /usr et /etc en lecture seule
ReadWritePaths=/data/etl

[Install]
WantedBy=multi-user.target  # cible qui l'active au boot, créée par 'systemctl enable'
```

**`Type=` — la source d'erreur n° 1 :**

| Type | Quand systemd considère le service « démarré » | Cas d'usage |
|---|---|---|
| **`simple`** (défaut) | **immédiatement** après `fork`/`exec` | processus au premier plan |
| `exec` | après le `execve()` réussi | comme simple, mais détecte un binaire absent |
| `forking` | quand le processus **parent se termine** | vieux démons qui se détachent (`daemonize`) |
| `oneshot` | quand le processus **a fini** | tâches ponctuelles (avec `RemainAfterExit=yes`) |
| `notify` | quand le service envoie `READY=1` via `sd_notify()` | le plus précis, quand le code le supporte |

> ⚠️ **PIÈGE** — Mettre `Type=simple` sur un démon qui **se met en arrière-plan tout seul** : systemd
> voit le premier process se terminer et déclare le service mort, puis (avec `Restart=always`) boucle
> à l'infini. Réciproquement, `Type=forking` sur un process qui reste au premier plan fait attendre
> systemd jusqu'au `TimeoutStartSec` (90 s) puis échoue. **Règle moderne : ne détache jamais ton
> service — laisse-le au premier plan et utilise `simple`.**

**Ordre ≠ dépendance** — l'autre confusion majeure :

| Directive | Ce qu'elle fait | Ce qu'elle **ne fait pas** |
|---|---|---|
| `After=B` | **Ordonne** : ne démarre qu'après B | n'oblige pas B à démarrer |
| `Wants=B` | Tente de démarrer B | n'échoue pas si B échoue ; **n'ordonne rien** |
| `Requires=B` | Exige B ; si B échoue ou s'arrête, on s'arrête | **n'ordonne rien** non plus ! |
| `BindsTo=B` | Comme `Requires`, mais suit aussi les arrêts inopinés de B | — |
| `PartOf=B` | Les `stop`/`restart` de B se propagent à nous | pas les `start` |

> 🧠 **MÉMO** — **`Requires` dit QUI, `After` dit QUAND.** On écrit presque toujours les deux ensemble :
> `Requires=postgresql.service` + `After=postgresql.service`. Sans le `After`, les deux démarrent en
> parallèle et ton service se connecte à une base qui n'écoute pas encore.

> ❓ **RETIENS ÇA** — Quelle est la différence entre `Requires=` et `After=` ?
> <details><summary>→ réponse</summary><br><code>Requires=</code> exprime une <b>dépendance</b> (l'autre unité doit être active, sinon on échoue), <code>After=</code> exprime un <b>ordre de démarrage</b>. Elles sont totalement indépendantes : un <code>Requires=</code> seul lance les deux <b>en parallèle</b>.</details>

### 8.4 Le cycle de vie et les commandes

```bash
$ systemctl start|stop|restart|reload etl-ventes    # maintenant
$ systemctl enable|disable etl-ventes               # au boot (crée/retire le lien WantedBy)
$ systemctl enable --now etl-ventes                 # les deux d'un coup
$ systemctl mask etl-ventes     # lien vers /dev/null : IMPOSSIBLE à démarrer, même en dépendance
$ systemctl daemon-reload       # OBLIGATOIRE après toute modification d'un fichier .service
$ systemctl cat etl-ventes      # le fichier effectif, drop-ins inclus
$ systemctl edit etl-ventes     # crée un drop-in .d/override.conf — NE JAMAIS éditer /usr/lib
$ systemctl show etl-ventes -p TimeoutStopSec       # valeur effective d'un paramètre
$ systemctl list-units --failed                     # la première commande à taper sur une machine malade
$ systemd-analyze blame                             # ce qui a ralenti le démarrage
$ systemd-analyze critical-chain                    # le chemin critique du boot
```

```bash
$ systemctl status etl-ventes
● etl-ventes.service - ETL quotidien des ventes
     Loaded: loaded (/etc/systemd/system/etl-ventes.service; enabled; preset: enabled)
     Active: active (running) since Tue 2026-09-09 02:00:03 UTC; 12h ago
   Main PID: 41207 (python)
      Tasks: 9 (limit: 38314)
     Memory: 2.1G (max: 8.0G available: 5.8G)
        CPU: 4h 12min 8.402s
     CGroup: /system.slice/etl-ventes.service
             ├─41207 /opt/etl/venv/bin/python -m etl.run --source ventes
             └─41288 /usr/bin/psql -h db01 …
```

Lecture ligne par ligne :
- `Loaded: … enabled` → **le fichier est chargé ET le service démarrera au prochain boot**. `disabled`
  ici est l'explication de « ça marche jusqu'au reboot ».
- `Active: active (running) since … ; 12h ago` → **l'uptime du service**. Un « 12s ago » sur un service
  censé tourner depuis des jours = boucle de redémarrage.
- `Tasks: 9 (limit: 38314)` → 9 processus/threads dans le cgroup, plafond `TasksMax`.
- `Memory: 2.1G (max: 8.0G)` → consommation du **cgroup entier**, à comparer à `MemoryMax`.
- `CGroup:` → **la liste exacte des processus du service**, enfants compris. C'est l'apport majeur
  de systemd : plus aucune ambiguïté sur « qui appartient à quoi ».

### 8.5 journalctl

Le journal est **binaire, indexé et structuré** : chaque entrée porte des métadonnées (`_PID`,
`_UID`, `_SYSTEMD_UNIT`, `_COMM`, `PRIORITY`). D'où des filtres impossibles avec des fichiers texte.

```bash
$ journalctl -u etl-ventes -f            # suivre en direct (le 'tail -f' de systemd)
$ journalctl -u etl-ventes --since "2 hours ago" --until "10 min ago"
$ journalctl -u etl-ventes -b            # depuis le dernier démarrage ; -b -1 = le boot précédent
$ journalctl -p err -b                   # priorité <= 3 (err, crit, alert, emerg)
$ journalctl -k                          # messages du noyau (= dmesg)
$ journalctl _PID=41207                  # par PID exact
$ journalctl -u etl-ventes -o json-pretty | jq .   # exploitation programmatique
$ journalctl -n 200 --no-pager           # les 200 dernières lignes, sans pager
$ journalctl --disk-usage                # taille occupée
$ journalctl --vacuum-time=7d            # purger au-delà de 7 jours
```

**Les 8 priorités syslog**, à connaître (elles servent aussi en observabilité) :

| 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|
| emerg | alert | crit | **err** | **warning** | notice | **info** | **debug** |

> ⚠️ **PIÈGE — le journal peut être volatile.** Par défaut `Storage=auto` : les logs vont dans
> `/run/log/journal` (**RAM, perdus au reboot**) **sauf si** `/var/log/journal` existe. Sur une machine
> où tu dois enquêter sur un crash d'hier, `mkdir -p /var/log/journal && systemctl restart
> systemd-journald` — ou `Storage=persistent`. Sinon `journalctl -b -1` répondra « no journal files ».

> ❓ **RETIENS ÇA** — Après avoir modifié un fichier `.service`, quelle commande est obligatoire avant `restart` ?
> <details><summary>→ réponse</summary><br><code>systemctl daemon-reload</code>. Sans elle, systemd continue d'utiliser la version en mémoire : ton changement semble « ne rien faire ». Note que <code>systemctl edit</code> le fait tout seul.</details>

### 8.6 Timers systemd contre cron

```ini
# /etc/systemd/system/etl-ventes.timer      (le .service du même nom est activé)
[Unit]
Description=Déclenche l'ETL ventes chaque jour à 02:00

[Timer]
OnCalendar=*-*-* 02:00:00      # syntaxe : AAAA-MM-JJ hh:mm:ss ; aussi daily, hourly, Mon..Fri
Persistent=true                # si la machine était éteinte, rattraper au démarrage (= anacron)
RandomizedDelaySec=300         # étaler sur 5 min : évite que 200 machines tapent la base à 02:00:00
AccuracySec=1s                 # défaut : 1min

[Install]
WantedBy=timers.target
```

```bash
$ systemctl list-timers --all
NEXT                        LEFT     LAST                        PASSED  UNIT              ACTIVATES
Wed 2026-09-10 02:00:00 UTC 11h left Tue 2026-09-09 02:00:00 UTC 12h ago etl-ventes.timer  etl-ventes.service
$ systemd-analyze calendar "Mon..Fri *-*-* 06:30:00"    # vérifier une expression AVANT de la poser
```

| | **cron** | **timer systemd** |
|---|---|---|
| Syntaxe | `min h dom mon dow` — 5 champs | `OnCalendar=` en langage lisible |
| Rattrapage après extinction | non (sauf anacron) | **`Persistent=true`** |
| Logs | mail local ou rien | **`journalctl -u`**, comme tout le reste |
| Environnement | **quasi vide**, `PATH=/usr/bin:/bin` | celui de l'unit, explicite |
| Ressources | aucune limite | `MemoryMax`, `CPUQuota`, `Nice` |
| Chevauchement | deux instances peuvent se superposer | **impossible** : le service est déjà `active` |
| Dépendances | aucune | `After=`, `Requires=` |
| Étalement | à la main | `RandomizedDelaySec=` |
| Simplicité | **imbattable** pour un one-liner | 2 fichiers |

> ⚠️ **PIÈGE — l'environnement de cron.** Ton script marche en interactif et échoue en cron :
> 9 fois sur 10, c'est le `PATH` (cron n'a ni ton `.bashrc` ni ton `.profile`), la variable
> `HOME`, ou un `python` qui n'est pas celui du venv. **Toujours des chemins absolus dans un crontab**,
> et rediriger : `>> /var/log/x.log 2>&1`. Et pense au piège du `%` : dans un crontab, `%` non échappé
> est interprété comme une fin de commande — `date +\%F`.

> ❓ **RETIENS ÇA** — Quel avantage décisif un timer systemd a-t-il sur cron pour un job quotidien à 2 h ?
> <details><summary>→ réponse</summary><br><b><code>Persistent=true</code></b> : si la machine était éteinte à 2 h, le job est rattrapé au démarrage. Plus : logs unifiés dans le journal, pas de chevauchement possible, limites de ressources cgroup, et <code>RandomizedDelaySec</code> pour étaler la charge.</details>

---

## 9. Mémoire : RSS, VSZ, page cache, swap, OOM killer

### 9.1 Le problème : pourquoi les chiffres de mémoire mentent

**Question** : ton process affiche `VSZ 12 Gio` sur une machine de 8 Gio. Comment est-ce possible ?

Parce que chaque process voit un **espace d'adressage virtuel** privé, découpé en **pages de 4 Kio**,
que la MMU traduit vers des pages physiques **uniquement pour celles réellement utilisées**.
Réserver de l'espace virtuel ne coûte rien.

| Métrique | Définition | Piège |
|---|---|---|
| **VSZ / VIRT** | Tout l'espace **d'adressage** : tas réservé, piles, bibliothèques et fichiers mappés, zones jamais touchées | **Ne représente pas la RAM.** Une JVM `-Xmx4g` affiche souvent 10-15 Gio de VIRT. À ignorer 95 % du temps |
| **RSS / RES** | Les pages **réellement en RAM** | **Compte les pages partagées dans chaque process** → la somme des RSS dépasse la RAM totale |
| **PSS** | RSS où chaque page partagée est divisée par le nombre de partageurs | **La bonne métrique** pour répartir la mémoire. `smem`, ou `/proc/PID/smaps_rollup` |
| **Swap** | Pages sorties sur disque | Un RSS qui baisse pendant que la latence explose = swap |

> ❓ **RETIENS ÇA** — Quelle est la différence entre RSS et VSZ ?
> <details><summary>→ réponse</summary><br><b>VSZ</b> = espace d'adressage <b>virtuel</b> total réservé (y compris jamais touché). <b>RSS</b> = pages <b>résidentes en RAM</b>. Seul le RSS coûte de la mémoire physique — mais il double-compte les pages partagées entre process ; PSS corrige ce biais.</details>

### 9.2 Le page cache : « pas de mémoire libre » est une bonne nouvelle

Toute lecture ou écriture de fichier passe par le **page cache** : le noyau garde en RAM les blocs
lus, et met en tampon les blocs écrits (**pages sales**) avant de les envoyer au disque. C'est ce qui
fait qu'un second `wc -l gros.csv` est 50 fois plus rapide que le premier.

**De la RAM inutilisée est de la RAM gaspillée** : Linux remplit systématiquement le page cache et le
rend instantanément dès qu'une application demande de la mémoire.

```bash
$ free -h
               total        used        free      shared  buff/cache   available
Mem:            31Gi        12Gi       420Mi       1.2Gi        19Gi        18Gi
Swap:          8.0Gi       256Mi       7.7Gi
```

- `free 420Mi` → **n'a aucune importance**, c'est ce qui n'a jamais servi.
- `buff/cache 19Gi` → du page cache, **récupérable à la demande**.
- **`available 18Gi`** → **la seule colonne à lire** : ce qu'une nouvelle application peut obtenir
  sans swapper. C'est elle qu'il faut mettre en alerte, pas `free`.
- `Swap used 256Mi` avec un swap-in/out nul : ce sont de vieilles pages inactives, ce n'est pas un problème.
  Le signal d'alarme est le **débit** de swap (`si`/`so` dans `vmstat 1`), pas la quantité.

Réglages utiles : `vm.swappiness` (défaut **60**) arbitre entre évincer du page cache et swapper des
pages anonymes ; sur une base de données on descend souvent à 1-10. `vm.dirty_ratio` (**20 %**) et
`vm.dirty_background_ratio` (**10 %**) fixent quand le noyau écrit les pages sales — les monter fait
des à-coups d'E/S de plusieurs secondes en fin d'écriture.

> ⚠️ **PIÈGE** — Ne mesure jamais des performances d'E/S deux fois de suite sans vider le cache
> (`sync; echo 3 > /proc/sys/vm/drop_caches`), sinon tu mesures la RAM. Et n'appelle pas ça un
> « optimisation » en production : le cache se reconstruit et tout devient lent quelques minutes.

### 9.3 L'OOM killer, tueur silencieux des jobs Spark

**Le problème** : Linux **surengage** la mémoire (`vm.overcommit_memory=0`, heuristique). Il accorde
plus de mémoire virtuelle qu'il n'en a, en pariant que personne ne l'utilisera entièrement. Quand le
pari est perdu et qu'il n'y a plus ni page libre, ni page à évincer, ni swap : le noyau doit choisir
une victime. C'est l'**OOM killer**.

**Comment il choisit** : un score, principalement proportionnel au **RSS** (donc *le plus gros
consommateur meurt en premier*), ajusté par `oom_score_adj` ∈ **[−1000, +1000]** :

```bash
$ cat /proc/41207/oom_score        # score courant
$ cat /proc/41207/oom_score_adj    # ajustement ; -1000 = immunisé, +1000 = victime désignée
$ echo -500 > /proc/41207/oom_score_adj      # protéger un process critique
```

Kubernetes s'en sert directement : classe **Guaranteed** → `oom_score_adj = −997` ; **BestEffort** →
**+1000** (tué en premier) ; **Burstable** → une valeur intermédiaire selon la requête mémoire.
Écrire des `requests`/`limits` corrects n'est donc pas de la paperasse : **c'est décider qui meurt**.

L'acte de décès est dans le journal du noyau :

```bash
$ dmesg -T | tail -6
[Tue Sep  9 15:41:02 2026] java invoked oom-killer: gfp_mask=0x140cca, order=0, oom_score_adj=0
[Tue Sep  9 15:41:02 2026] Memory cgroup out of memory: Killed process 41207 (java)
                            total-vm:12874216kB, anon-rss:8253100kB, file-rss:24816kB, shmem-rss:0kB,
                            UID:1001 pgtables:16612kB oom_score_adj:0
```

- `invoked oom-killer` → **c'est ce process qui a demandé la page manquante** ; il n'est pas forcément
  la victime.
- **`Memory cgroup out of memory`** → **c'est un OOM de cgroup, pas de machine** : le conteneur a
  dépassé **sa** limite alors que la machine avait peut-être de la RAM libre. Message capital : la
  correction est dans `resources.limits`, pas dans la taille du nœud.
- `anon-rss:8253100kB` ≈ **7,9 Gio** de mémoire anonyme (le tas) — à comparer au `-Xmx`.
- Côté conteneur : `State: Terminated, Reason: OOMKilled, Exit Code: 137`.

> ⚠️ **PIÈGE — le « −Xmx4g mais tué à 6 Gio ».** Le `-Xmx` de la JVM ne borne **que le tas**. À côté
> s'ajoutent le Metaspace, les piles de threads (≈ 1 Mio × nombre de threads), les tampons directs
> (`MaxDirectMemorySize`), le JIT, le GC, et pour Spark la **mémoire off-heap** (`spark.executor.memoryOverhead`,
> par défaut **max(384 Mio, 10 % de la mémoire de l'exécuteur)**). La limite du conteneur doit couvrir
> **la somme**, sinon le cgroup tue une JVM qui, de son point de vue, respectait parfaitement sa consigne.

> 🧠 **MÉMO** — **`OutOfMemoryError` ≠ `OOMKilled`.** Le premier est une **exception Java** : la JVM
> est vivante, elle a atteint `-Xmx`, tu as une stack trace. Le second est un **`SIGKILL` du noyau** :
> aucun log applicatif, aucune trace, juste un code 137 et une ligne dans `dmesg`. Chercher une stack
> trace après un 137 est une perte de temps garantie.

> ❓ **RETIENS ÇA** — Où trouve-t-on la preuve qu'un processus a été tué par l'OOM killer ?
> <details><summary>→ réponse</summary><br>Dans le journal du noyau : <code>dmesg -T | grep -i oom</code> ou <code>journalctl -k | grep -i oom</code>. Le message précise si l'OOM est <b>global</b> ou <b>de cgroup</b>, le PID, le nom et l'<code>anon-rss</code> de la victime. Côté cgroup v2, le compteur <code>oom_kill</code> de <code>memory.events</code> le confirme aussi.</details>

**Exercice corrigé n° 2 — dimensionner un exécuteur Spark.**
On veut `spark.executor.memory = 8g` sur des conteneurs Kubernetes. Quelle `limits.memory` poser ?

```
  1) Tas JVM (-Xmx)                          8 192 Mio
  2) Overhead Spark = max(384, 10 % × 8192)  = max(384, 819) =  819 Mio
  3) Total demandé par Spark au gestionnaire = 8 192 + 819   = 9 011 Mio  ≈ 8,8 Gio
  4) Marge pour le page cache du shuffle, les piles de threads
     et le processus lui-même                                ≈ +10 %
  5) limits.memory                                            ≈ 9,7 Gio → on pose 10Gi
```

Poser `limits.memory: 8Gi` avec `executor.memory=8g` garantit un OOMKilled : on aurait oublié
l'overhead, qui n'est pas dans le tas. **Poser la limite au tas est l'erreur la plus fréquente
en Spark sur Kubernetes.**

---

## 10. Disque : montage, inodes, `df` vs `du`, LVM

### 10.1 Monter, c'est greffer

```bash
$ lsblk
NAME        MAJ:MIN RM  SIZE RO TYPE MOUNTPOINTS
nvme0n1     259:0    0  500G  0 disk
├─nvme0n1p1 259:1    0  512M  0 part /boot/efi
└─nvme0n1p2 259:2    0  499G  0 part
  ├─vg0-root 253:0   0   50G  0 lvm  /
  └─vg0-data 253:1   0  400G  0 lvm  /data
```

`/etc/fstab`, **six champs** :

```
UUID=8f3a-… /data ext4 defaults,noatime,nofail 0 2
# 1 périph.  2 pt   3 fs  4 options              5 dump  6 ordre de fsck (0 jamais, 1 racine, 2 autres)
```

Options utiles : `noatime` (n'écrit plus la date d'accès → gain réel sur des millions de petits
fichiers), `nofail` (**ne bloque pas le boot** si le volume est absent — indispensable pour un NFS
ou un disque de données), `ro`, `nosuid`, `nodev`, `noexec` (durcissement d'un `/data`).

> ⚠️ **PIÈGE** — **N'utilise jamais `/dev/sdb1` dans `/etc/fstab`** : l'ordre d'énumération des
> disques peut changer d'un boot à l'autre et tu montes le mauvais volume. Toujours `UUID=` (via
> `blkid`) ou `LABEL=`. Et une ligne fstab fausse **empêche le boot** : `mount -a` avant de redémarrer.

> ⚠️ **PIÈGE — monter par-dessus des données.** Si `/data` contient déjà des fichiers et que tu montes
> un volume dessus, les anciens fichiers **existent toujours** mais deviennent invisibles — et
> continuent d'occuper la place sur le système de fichiers parent. `df` montrera un `/` plein sans
> que `du /data` ne trouve rien.

### 10.2 `df` contre `du` : deux questions différentes

| | `df` | `du` |
|---|---|---|
| Question posée | « **Système de fichiers**, combien de blocs sont alloués ? » | « **Parcours les noms** et additionne leur taille » |
| Source | superbloc, **instantané** | parcours récursif, **lent** |
| Voit les fichiers supprimés mais ouverts | **oui** | non |
| Voit ce qui est masqué par un montage | oui (sur le FS parent) | non |
| Compte deux fois les liens physiques | non | non (`du` les compte une fois) |

Les trois écarts `df` > `du` et leur cause :

1. **fichier supprimé mais encore ouvert** → `lsof +L1` → recharger le service ;
2. **données masquées par un point de montage** → `mount --bind / /mnt && du -sh /mnt/data` ;
3. **blocs réservés à root** : ext4 en réserve **5 %** par défaut (`tune2fs -m 1 /dev/…` pour un
   volume de données pur, ce qui rend 4 % de 400 Gio = 16 Gio).

```bash
$ df -h /data
Filesystem            Size  Used Avail Use% Mounted on
/dev/mapper/vg0-data  394G  374G  0.0G 100% /data      ← plein

$ df -i /data
Filesystem             Inodes    IUsed   IFree IUse% Mounted on
/dev/mapper/vg0-data 26214400 26214400       0  100% /data      ← inodes ÉPUISÉS
```

> ⚠️ **PIÈGE — « No space left on device » avec de la place libre.** C'est **l'épuisement des inodes**.
> Sur ext4, le nombre d'inodes est **fixé à la création du système de fichiers** (par défaut 1 inode
> pour 16 Kio de capacité) et **ne peut pas être augmenté après coup** : il faut recréer le FS.
> Cause typique en data : des millions de micro-fichiers (le fameux « small files problem » de Hive/HDFS,
> ou un répertoire de spool jamais purgé). **Toujours faire `df -i` juste après `df -h`.**

**Exercice corrigé n° 3 — combien de fichiers tiennent sur un volume ?**
Un volume ext4 de 400 Gio créé avec les paramètres par défaut.

```
  1) Ratio par défaut : 1 inode pour 16 384 octets de capacité
  2) Nombre d'inodes  = 400 × 2^30 / 16 384
                      = 429 496 729 600 / 16 384
                      ≈ 26 214 400 inodes          ← cohérent avec le df -i ci-dessus
  3) Taille moyenne des fichiers Parquet produits : 12 Kio
  4) Blocs : chaque fichier occupe au minimum 1 bloc de 4 Kio ; 12 Kio → 3 blocs, pas de perte notable
  5) Capacité limitante :
        par l'espace  : 400 Gio / 12 Kio  ≈ 34 950 000 fichiers
        par les inodes:                   ≈ 26 214 400 fichiers   ← LE PLAFOND
  ⇒ On saturera les INODES avant l'espace, à ~75 % de remplissage.
    Remède : produire des fichiers plus gros (128-512 Mio, la bonne taille pour Parquet/Spark),
    ou créer le FS avec 'mkfs.ext4 -i 65536' si on sait qu'on aura peu de gros fichiers.
```

### 10.3 LVM en une page

**Le problème** : une partition a une taille figée entre deux points du disque. Comment agrandir
`/data` quand il n'y a plus de place derrière ? LVM ajoute une indirection :

```
   Disques physiques      →   PV (Physical Volume)
   /dev/nvme0n1p2, /dev/sdb    ─┐
                                ├──►  VG (Volume Group)  "vg0" = un réservoir d'extents (PE, 4 Mio)
   /dev/sdc                    ─┘            │
                                             ├──► LV "root"  50 Gio  → ext4 → /
                                             └──► LV "data" 400 Gio  → xfs  → /data
```

```bash
$ pvcreate /dev/sdc                     # déclarer un disque comme PV
$ vgextend vg0 /dev/sdc                 # l'ajouter au réservoir
$ lvextend -L +200G -r /dev/vg0/data    # agrandir le LV ET le système de fichiers (-r)
$ lvcreate -L 10G -s -n snap_data /dev/vg0/data   # instantané (sauvegarde cohérente)
```

> ⚠️ **PIÈGE** — Agrandir le LV ne suffit pas : le **système de fichiers** doit être étendu aussi
> (`-r` le fait, sinon `resize2fs` pour ext4, `xfs_growfs` pour XFS). Et **XFS ne sait que grandir**,
> jamais rétrécir — choix courant sur les volumes de données, à connaître avant de s'engager.

---

## 11. La boîte à outils de diagnostic

### 11.1 `top` : la vue d'ensemble en 5 secondes

```
top - 15:41:02 up 4 days,  2:11,  2 users,  load average: 14.02, 9.55, 4.31
Tasks: 412 total,   3 running, 408 sleeping,   0 stopped,   1 zombie
%Cpu(s): 22.1 us,  4.3 sy,  0.0 ni, 11.9 id, 61.2 wa,  0.0 hi,  0.4 si,  0.1 st
MiB Mem :  31890.0 total,    420.3 free,  12288.7 used,  19181.0 buff/cache
MiB Swap:   8192.0 total,   7936.0 free,    256.0 used.  18102.4 avail Mem

  PID USER   PR  NI    VIRT    RES    SHR S  %CPU  %MEM     TIME+ COMMAND
41207 spark  20   0   12.3g   7.9g  24816 S  98.7  25.3  41:08.22 java
```

Ce que dit **cette** capture, dans l'ordre où il faut la lire :
- `load average: 14.02, 9.55, 4.31` → moyennes à **1, 5 et 15 min**. Elles **montent** (14 > 9 > 4) :
  la dégradation est en cours, pas terminée. À comparer au nombre de cœurs (`nproc`).
- **`61.2 wa`** → 61 % du temps à **attendre les E/S**. Voilà l'explication du load à 14 avec un CPU
  presque inactif : les process sont en état `D`, qui compte dans la charge sous Linux. **Le problème
  est le disque ou le réseau, pas le CPU.** Prochaine commande : `iostat -xz 1`.
- `0.1 st` (steal) → temps volé par l'hyperviseur ; > 5 % en continu sur une VM cloud = voisin bruyant.
- `1 zombie` → toléré à l'unité, à surveiller si le nombre croît.
- `RES 7.9g` contre `VIRT 12.3g` → normal pour une JVM ; c'est le **RES** qu'il faut comparer à la limite.

### 11.2 Les autres, avec ce qu'on leur demande

| Outil | La question à laquelle il répond | Invocation utile |
|---|---|---|
| `htop` | comme `top`, interactif, avec l'arbre | `F5` arbre, `F6` tri, `F9` kill |
| `ps` | l'instantané scriptable | `ps -eo pid,ppid,stat,rss,etime,cmd --sort=-rss` |
| `pstree` | qui a lancé qui | `pstree -aps <pid>` (remonte jusqu'à PID 1) |
| `lsof` | **qui tient ce fichier / ce port ?** | `lsof /data/x.csv` · `lsof -i :9092` · `lsof -p PID` · `lsof +L1` |
| `fuser` | idem, plus rapide, sait tuer | `fuser -km /data` (tue tout ce qui empêche de démonter) |
| `strace` | **quels appels système fait-il ?** | `strace -f -T -p PID` · `strace -c -f ./cmd` (résumé) |
| `ltrace` | quels appels de bibliothèque ? | rarement utile |
| `dmesg` | qu'a dit **le noyau** ? | `dmesg -T -l err,warn` · `dmesg -w` (suivi) |
| `vmstat` | CPU/mémoire/E/S en séries | `vmstat 1` — colonnes `r b`, `si so`, `bi bo`, `us sy id wa` |
| `iostat` | quel disque souffre ? | `iostat -xz 1` — `%util`, `await`, `aqu-sz` |
| `pidstat` | par processus, dans le temps | `pidstat -p PID 1` · `-d` pour l'E/S |
| `ss` | quelles sockets ? (cf. `R06`) | `ss -tanp` |

**`strace` en pratique — l'outil qui répond à « il ne fait rien, mais quoi ? »**

```bash
$ strace -f -T -e trace=openat,read,connect -p 41207
[pid 41288] openat(AT_FDCWD, "/data/ventes/part-00042.parquet", O_RDONLY) = 9 <0.000041>
[pid 41288] read(9, "PAR1\25\4\25\260…", 4096)                              = 4096 <0.000019>
[pid 41288] connect(12, {sa_family=AF_INET, sin_port=htons(5432), …})       = -1 EINPROGRESS
[pid 41288] read(12, 0x7f2a4c001a30, 8192)                                  = ? ERESTARTSYS  ← BLOQUÉ ICI
```

- `-f` suit les processus **et threads** enfants — sans lui, on ne voit rien sur une JVM ou un fork.
- `-T` affiche entre chevrons la **durée de chaque appel** : c'est là que se voit la lenteur.
- La dernière ligne montre un `read()` sur le FD 12 (la socket PostgreSQL) qui **ne revient pas** :
  le process n'est pas lent, il **attend la base**. Diagnostic terminé en trois lignes.
- **Coût** : `strace` intercepte chaque syscall et peut ralentir un process **d'un facteur 10 à 100**.
  Ne jamais le laisser tourner longtemps sur un service de production ; préférer `strace -c` sur
  quelques secondes, ou `perf`/eBPF.

> ❓ **RETIENS ÇA** — Quelle commande révèle quel processus tient encore un fichier supprimé qui occupe le disque ?
> <details><summary>→ réponse</summary><br><code>lsof +L1</code> (fichiers ouverts dont le nombre de liens est inférieur à 1), ou <code>lsof | grep deleted</code>. La correction est de <b>recharger ou redémarrer</b> le processus fautif, pour qu'il ferme le descripteur.</details>

### 11.3 La méthode : cinq commandes, dans cet ordre

Sur une machine qui va mal, ne pars pas au hasard. Cet enchaînement couvre l'immense majorité des cas :

```
 1. uptime          → la charge monte-t-elle ? (comparer aux 3 moyennes et à nproc)
 2. top / htop      → CPU ? mémoire ? ou 'wa' (E/S) ? Qui est en tête ?
 3. free -h         → colonne 'available'. Et vmstat 1 : si/so non nuls = swap actif
 4. df -h ET df -i  → espace ET inodes. Le second est oublié 9 fois sur 10
 5. dmesg -T | tail → OOM ? erreur disque ? reset de carte réseau ?
    puis journalctl -p err -b et systemctl --failed
```

Ensuite seulement on cible : `lsof` pour les fichiers, `strace` pour un process figé,
`iostat -xz 1` pour le disque, `ss -tanp` pour le réseau.

---

## 12. Questions d'entretien

**1. Explique ce qui se passe entre le moment où tu tapes `ls -l` et l'affichage du résultat.**
Le shell découpe la ligne, résout `ls` via le `PATH`, puis appelle `fork()`, ce qui crée une copie de
lui-même en copy-on-write. Dans l'enfant, il installe les redirections avec `dup2()` s'il y en a, puis
appelle `execve("/usr/bin/ls", …)`, qui remplace l'image mémoire par celle de `ls` — même PID, mêmes
descripteurs. Le parent se bloque dans `wait()`. `ls` fait `openat()` sur le répertoire, `getdents64()`
pour lire les entrées, un `statx()` par entrée pour les métadonnées, écrit sur le FD 1, puis `exit()`.
Le noyau réveille le shell avec `SIGCHLD` ; `wait()` récupère le code de sortie et l'entrée de la table
des processus est libérée. Si le shell n'appelait pas `wait()`, l'entrée resterait : ce serait un zombie.

**2. Quelle différence entre `SIGTERM` et `SIGKILL`, et pourquoi ça compte en production ?**
`SIGTERM` (15) est une demande d'arrêt : le processus peut l'intercepter et exécuter son code de
nettoyage — vider ses tampons, commiter ses offsets Kafka, fermer ses transactions, finir les requêtes
en cours. `SIGKILL` (9) est appliqué par le noyau, ne peut être ni intercepté, ni bloqué, ni ignoré, et
n'exécute **aucune** ligne de code applicatif. En pratique, tout arrêt correct commence par `SIGTERM` et
laisse un délai de grâce — 10 s pour `docker stop`, 30 s pour Kubernetes, 90 s par défaut pour systemd —
avant d'envoyer `SIGKILL`. Un service tué à la hache laisse des fichiers Parquet tronqués, des offsets
non commités et des verrous orphelins. Et un processus en état `D` ne meurt même pas sur `SIGKILL`,
puisqu'il n'exécute plus rien en espace utilisateur.

**3. Un conteneur met exactement 30 secondes à s'arrêter, à chaque fois. Pourquoi ?**
C'est la signature d'un `SIGTERM` non traité : Kubernetes envoie `SIGTERM`, attend
`terminationGracePeriodSeconds` (30 s par défaut), puis `SIGKILL`. Deux causes usuelles. Soit
l'application est PID 1 dans le conteneur et n'installe pas de gestionnaire — or le noyau n'applique
pas les actions par défaut des signaux à PID 1, donc le signal est purement ignoré. Soit le `CMD` est
écrit en forme shell, auquel cas c'est `/bin/sh` qui est PID 1 et ne relaie pas le signal à son enfant.
Corrections : forme exec (`CMD ["python","app.py"]`), gestionnaire de signal dans le code, ou un init
léger (`--init`, `tini`). Confirmation rapide : le code de sortie est 137 au lieu de 0 ou 143.

**4. `df` dit que le disque est plein, `du -sh /` ne trouve que la moitié. Que fais-tu ?**
Trois hypothèses, dans cet ordre. Un ou plusieurs fichiers **supprimés mais encore ouverts** : `du`
parcourt les noms et ne les voit plus, `df` interroge le superbloc et voit les blocs toujours alloués.
Je vérifie avec `lsof +L1` et je recharge le service fautif. Deuxième hypothèse, des données **masquées
par un point de montage** monté par-dessus : je les retrouve avec un `mount --bind / /mnt` puis un `du`
sur `/mnt`. Troisième, les **blocs réservés à root**, 5 % par défaut sur ext4, ajustables avec
`tune2fs -m`. Et dans tous les cas je lance `df -i` en parallèle, parce que « No space left on device »
avec de l'espace libre est presque toujours un épuisement d'inodes.

**5. `RSS` ou `VSZ` : lequel regardes-tu, et pourquoi la somme des RSS dépasse la RAM ?**
Je regarde le RSS : c'est la mémoire physiquement occupée. Le VSZ n'est qu'un espace d'adressage
réservé, qui inclut les bibliothèques mappées, les zones jamais touchées et le tas réservé — une JVM
`-Xmx4g` affiche couramment 12 Gio de VSZ sans consommer 12 Gio. La somme des RSS dépasse la RAM parce
que chaque processus **compte intégralement les pages partagées** : la libc, les binaires, la mémoire
partagée sont comptés une fois par processus. Pour répartir honnêtement, il faut le PSS, qui divise
chaque page partagée par le nombre de partageurs ; on le lit dans `/proc/PID/smaps_rollup` ou avec `smem`.

**6. Un exécuteur Spark disparaît sans stack trace, code 137. Diagnostic ?**
137 = 128 + 9 : `SIGKILL`. Comme il n'y a aucune trace applicative, ce n'est pas une
`OutOfMemoryError` Java — celle-ci laisserait une exception et un tas de messages GC. C'est l'OOM
killer du noyau, que je confirme dans `dmesg -T | grep -i oom` ou `journalctl -k`. Le message dira si
l'OOM est **global** ou **de cgroup** : en conteneur c'est presque toujours le cgroup, donc la limite du
pod, pas la taille du nœud. La cause récurrente est d'avoir aligné `limits.memory` sur
`spark.executor.memory` en oubliant que la JVM consomme, en plus du tas, le Metaspace, les piles de
threads, les tampons directs, et le `memoryOverhead` de Spark — par défaut le maximum entre 384 Mio et
10 % de la mémoire de l'exécuteur. La limite doit couvrir la somme.

**7. Différence entre `Requires=` et `After=` dans une unit systemd ?**
Ce sont deux axes indépendants. `Requires=` est une dépendance d'**existence** : l'unité citée sera
démarrée avec la nôtre, et si elle échoue ou s'arrête, la nôtre est arrêtée aussi. `After=` est une
dépendance d'**ordre** : nous ne démarrons qu'une fois l'autre démarrée. Un `Requires=` sans `After=`
lance les deux **en parallèle** — d'où le classique service applicatif qui échoue au boot parce que
PostgreSQL n'écoute pas encore. On écrit donc presque toujours les deux ensemble. Variantes utiles :
`Wants=` pour une dépendance souple qui n'échoue pas, `BindsTo=` qui suit aussi les arrêts inopinés,
`PartOf=` qui ne propage que les arrêts et redémarrages.

**8. `umask 027` : quel mode aura un fichier créé par ce processus ? Et un répertoire ?**
Un fichier est demandé en 666 (jamais `x` automatiquement) et un répertoire en 777. Le umask retire des
bits : 666 moins 027 donne **640**, c'est-à-dire `rw-r-----` ; 777 moins 027 donne **750**, soit
`rwxr-x---`. Concrètement, le propriétaire lit et écrit, le groupe lit, les autres n'ont rien. Deux
précisions qui montrent qu'on maîtrise : le umask est un attribut du **processus**, hérité par les
enfants — donc celui de mon shell n'a aucun effet sur un service systemd, qui a sa directive `UMask=`,
ni sur un conteneur. Et il ne s'applique **jamais rétroactivement** aux fichiers déjà créés.

**9. Timer systemd ou cron pour un batch quotidien ?**
Pour un one-liner sur une machine isolée, cron reste imbattable en simplicité. Dès qu'il s'agit d'un
job de production, je prends un timer : `Persistent=true` rattrape l'exécution si la machine était
éteinte, les logs partent dans le journal et se filtrent avec `journalctl -u`, le job hérite des
limites de ressources du cgroup (`MemoryMax`, `CPUQuota`, `Nice`), deux exécutions ne peuvent pas se
chevaucher puisque l'unité est déjà active, on peut exprimer des dépendances (`After=network-online.target`),
et `RandomizedDelaySec=` étale la charge quand deux cents machines déclencheraient à la même seconde.
J'ajoute que le premier piège de cron est son environnement quasi vide : pas de `.bashrc`, un `PATH`
minimal, donc chemins absolus obligatoires.

**10. Un processus est en état `D` depuis dix minutes et `kill -9` ne fait rien. Que se passe-t-il ?**
`D` est le sommeil **non interruptible** : le processus est bloqué à l'intérieur du noyau, dans une
opération d'E/S qui ne peut pas être abandonnée à mi-chemin — typiquement un NFS injoignable, un
volume réseau détaché, ou un disque défaillant. Les signaux ne lui sont pas délivrés parce qu'il
n'exécute plus aucune instruction en espace utilisateur ; il ne repartira qu'au retour de l'E/S, ou
jamais. Sur Linux, l'état `D` **compte dans la charge moyenne**, ce qui explique un load average
à 40 sur une machine dont le CPU est inactif. Je regarde `cat /proc/PID/stack` et `dmesg` pour
identifier la couche fautive, et je corrige la cause : remonter le NFS, remplacer le disque. Sinon,
il ne reste que le redémarrage.

---

## 13. Les 3 choses à retenir si tu ne retiens que ça

**1. Un fichier n'est pas son nom, un processus n'est pas son programme.** Le fichier est un **inode** ;
le nom n'est qu'une entrée de répertoire qui pointe dessus, et les blocs ne sont libérés que lorsque
plus aucun nom **et** plus aucun descripteur ne le référencent. C'est de cette seule règle que
découlent le lien physique, le `df`/`du` incohérent, le fichier `(deleted)` qui remplit un disque, et
la nécessité de recharger un service après un `logrotate`. Symétriquement, `fork()` crée une copie
et `execve()` change de programme sans changer de PID — ce qui explique où le shell place les
redirections, pourquoi un zombie n'est qu'une fiche administrative que seul le parent peut classer,
et pourquoi PID 1 est un rôle, pas un processus comme les autres.

**2. Les nombres du système sont un langage : apprends-les et les pannes se lisent d'elles-mêmes.**
**137 = 128 + 9 = SIGKILL**, donc OOM killer, donc `dmesg`, donc une limite de cgroup et pas la taille
du nœud. **143 = SIGTERM**, donc un arrêt demandé. **141 = SIGPIPE**, donc un lecteur parti.
**9 ne se rattrape pas, 19 non plus.** **644/755/600**, **umask 022**, **1777 sur `/tmp`**, **4 setuid /
2 setgid / 1 sticky**. **10 s pour `docker stop`, 30 s pour Kubernetes, 90 s pour systemd.** Ces valeurs
n'apparaissent jamais dans le code ni dans les tests : elles se retiennent, et c'est exactement ce qui
sépare un diagnostic de dix minutes d'une enquête de trois jours.

**3. En 2026, tout ce que tu observes est enfermé dans un cgroup — regarde toujours la bonne échelle.**
systemd place chaque service dans son cgroup, Docker et Kubernetes en font autant pour chaque conteneur.
Conséquence : `free -h` et `/proc/meminfo` te montrent la **machine**, pas ta limite ; `top` te montre
les cœurs de l'hôte, pas ton `CPUQuota` ; et l'OOM killer peut abattre ton processus alors que la
machine a 20 Gio de libre, simplement parce que **ton** cgroup a atteint `memory.max`. Avant de conclure
quoi que ce soit sur les ressources, demande-toi toujours : est-ce que je regarde la machine, ou le
cgroup ? Sur cette seule question se joue la moitié des incidents mal diagnostiqués en production data.
