# D01 — CHEATSHEET : Linux système

Référence opérationnelle. À garder ouverte pendant qu'on travaille.

---

## 1. Les nombres à ne jamais chercher

| Grandeur | Valeur | Note |
|---|---|---|
| Descripteurs standard | **0** stdin · **1** stdout · **2** stderr | `> f` ne touche que le 1 |
| Tampon d'un tube | **64 Kio** | contrôle de flux gratuit |
| Bufferisation stdout | **ligne** sur tty · **4 Kio** sur fichier/tube | `PYTHONUNBUFFERED=1` |
| `ulimit -n` | **1024** souple / **524288** dure | systemd : `LimitNOFILE=` |
| Page mémoire | **4 Kio** (huge page 2 Mio) | |
| `pid_max` | **32768** (souvent **4194304** en 64 bits systemd) | PID réutilisés |
| `nice` | **−20 … 0 … +19** | non-root : peut seulement augmenter |
| Priorité temps réel | **1 … 99** (`chrt -f`) | |
| Grâce avant SIGKILL | docker **10 s** · K8s **30 s** · systemd **90 s** | `-t` / `terminationGracePeriodSeconds` / `TimeoutStopSec` |
| `RestartSec` | **100 ms** | `StartLimitBurst=5` / `IntervalSec=10s` |
| `vm.swappiness` | **60** | 1-10 sur une base de données |
| `vm.dirty_ratio` / `_background_` | **20 %** / **10 %** | |
| `oom_score_adj` | **−1000 … +1000** | −1000 = immunisé |
| K8s `oom_score_adj` | Guaranteed **−997** · BestEffort **+1000** | Burstable : intermédiaire |
| Spark `memoryOverhead` | **max(384 Mio, 10 %)** | à ajouter à `limits.memory` |
| Inodes ext4 | **1 pour 16 Kio**, **figés au mkfs** | `mkfs.ext4 -i <octets>` |
| Blocs réservés root (ext4) | **5 %** | `tune2fs -m 1` |
| Extent LVM (PE) | **4 Mio** | |
| Ports privilégiés | **< 1024** → `CAP_NET_BIND_SERVICE` | |

## 2. Signaux et codes de sortie

| N° | Signal | Défaut | Rattrapable | Usage |
|---:|---|---|---|---|
| 1 | `SIGHUP` | terminer | oui | **recharger la config** (nginx, rsyslog) |
| 2 | `SIGINT` | terminer | oui | Ctrl-C |
| 3 | `SIGQUIT` | terminer + core | oui | **thread dump JVM** (ne tue pas la JVM) |
| 6 | `SIGABRT` | terminer + core | oui | `abort()`, assertion |
| 9 | `SIGKILL` | **tuer** | **NON** | dernier recours |
| 11 | `SIGSEGV` | terminer + core | oui | accès mémoire invalide |
| 13 | `SIGPIPE` | terminer | oui | lecteur du tube parti |
| 15 | `SIGTERM` | terminer | oui | **le défaut de `kill`** |
| 17 | `SIGCHLD` | ignorer | oui | un enfant s'est terminé |
| 18 | `SIGCONT` | reprendre | oui | `fg` / `bg` |
| 19 | `SIGSTOP` | suspendre | **NON** | |
| 20 | `SIGTSTP` | suspendre | oui | Ctrl-Z |
| 10 / 12 | `SIGUSR1/2` | terminer | oui | libres pour l'application |

**Code de sortie = 128 + n° de signal** · `130` Ctrl-C · **`137` SIGKILL (OOM)** · `139` SEGV · `141` SIGPIPE · **`143` SIGTERM**
Autres : `0` OK · `1` erreur générique · `2` mauvais usage · `126` non exécutable · `127` **commande introuvable** · `124` `timeout`.

```bash
kill -l                        # lister les signaux
kill 4712                      # SIGTERM
kill -HUP $(pidof nginx)       # recharge
pkill -f 'python etl_'         # par motif de ligne de commande
killall -TERM python3          # par nom d'exécutable
timeout -s TERM -k 10 30 ./job.sh   # TERM à 30 s, KILL 10 s plus tard
trap 'echo cleanup; exit 0' TERM INT   # handler en bash
```

## 3. Permissions

| Octal | Bits | | Spécial | Octal | `ls -l` |
|---:|---|---|---|---:|---|
| 7 | `rwx` | | **setuid** | **4000** | `rws` (user) |
| 6 | `rw-` | | **setgid** | **2000** | `rws` (group) |
| 5 | `r-x` | | **sticky** | **1000** | `rwt` (other) |
| 4 | `r--` | | | | |
| 0 | `---` | | | | |

| Bit | Fichier | Répertoire |
|---|---|---|
| `r` | lire le contenu | **lister les noms** |
| `w` | modifier | **créer/supprimer/renommer** (nécessite `x`) |
| `x` | exécuter | **traverser** — requis sur **tout le chemin** |

| Mode | Usage | | umask | Fichier | Répertoire |
|---|---|---|---|---|---|
| **644** | données | | **022** | 644 | 755 |
| **755** | binaire, répertoire | | **002** | 664 | 775 |
| **600** | clé SSH, `.pgpass` | | **027** | 640 | 750 |
| **700** | `~/.ssh` | | **077** | 600 | 700 |
| **1777** | `/tmp` | | | | |
| **2775** | répertoire d'équipe (setgid) | | | | |

**Calcul** : fichier = `666 & ~umask` · répertoire = `777 & ~umask`.

```bash
chmod 640 f            chmod u+x,g-w f       chmod -R g+rX dir/   # X = x sur les répertoires ET sur les fichiers déjà exécutables
chmod 2775 /data/proj  chmod +t /shared      chown user:group f   chgrp -R data dir/
find / -perm -4000 -type f 2>/dev/null       # audit setuid
find /data ! -user spark -ls                 # fichiers d'un autre propriétaire
getfacl f · setfacl -m u:alice:r-- f · setfacl -d -m g:bi:r-x dir · setfacl -x u:alice f · setfacl -b f
getcap /usr/bin/ping · setcap 'cap_net_bind_service=+ep' ./srv · capsh --print
```

## 4. Processus

```bash
ps aux                                    # BSD : USER PID %CPU %MEM VSZ RSS STAT START TIME CMD
ps -ef                                    # POSIX : UID PID PPID C STIME TTY TIME CMD
ps -eo pid,ppid,stat,ni,rss,etime,cmd --sort=-rss | head
ps -eLf | wc -l                           # compter les THREADS
pstree -aps 4712                          # remonter jusqu'à PID 1
top -H -p 4712                            # threads d'un process
nice -n 10 cmd · renice -n 5 -p PID · chrt -f 50 cmd · ionice -c 3 -p PID
taskset -c 0-3 cmd                        # épingler sur des cœurs
nohup cmd & · setsid cmd · disown %1      # détacher du terminal
jobs · fg %1 · bg %1 · Ctrl-Z (TSTP) · Ctrl-C (INT)
```

| `STAT` | Sens | | Suffixe | Sens |
|---|---|---|---|---|
| `R` | running / runnable | | `<` | priorité haute |
| `S` | sommeil interruptible | | `N` | nice > 0 |
| **`D`** | **E/S non interruptible** (immunisé au `kill -9`, compte dans le load) | | `s` | chef de session |
| `T` / `t` | stoppé / tracé | | `l` | multi-thread |
| `Z` | **zombie** | | `+` | premier plan |

## 5. Fichiers, descripteurs, redirections

| Syntaxe | Effet | | Syntaxe | Effet |
|---|---|---|---|---|
| `> f` | stdout, écrase | | `2>/dev/null` | jeter les erreurs |
| `>> f` | stdout, ajoute | | `< f` | stdin depuis `f` |
| `2> f` | stderr | | `<<EOF … EOF` | here-document |
| **`> f 2>&1`** | **les deux dans `f`** ✅ | | `<<< "s"` | here-string |
| `2>&1 > f` | ❌ stderr reste à l'écran | | `<(cmd)` | fichier virtuel |
| `&> f` | les deux (bash) | | `a \|& b` | stdout+stderr dans le tube |
| `\| tee f` | dupliquer vers `f` (`-a` ajoute) | | `exec 3< f` | ouvrir le FD 3 |

```bash
ls -l /proc/PID/fd            # tous les descripteurs, avec (deleted) le cas échéant
cat /proc/PID/limits · /proc/PID/status · /proc/PID/cmdline · /proc/PID/environ
stat f                        # inode, liens, atime/mtime/ctime, blocs
ln a b · ln -s a b · readlink -f b · realpath f
set -o pipefail · echo ${PIPESTATUS[@]} · set -euo pipefail
stdbuf -oL -eL cmd · python -u · PYTHONUNBUFFERED=1
```

## 6. systemd

```bash
systemctl start|stop|restart|reload|status UNIT
systemctl enable --now UNIT · disable · mask (→/dev/null) · unmask
systemctl daemon-reload                 # OBLIGATOIRE après édition d'un .service
systemctl cat UNIT · edit UNIT (drop-in) · show UNIT -p TimeoutStopSec
systemctl list-units --failed · list-unit-files --state=enabled · list-timers --all
systemctl is-active|is-enabled|is-failed UNIT
systemd-analyze blame · critical-chain · verify f.service · calendar "Mon..Fri 06:30"
systemd-cgtop · systemctl status UNIT (section CGroup = les process du service)
```

| Directive | Rôle | | Directive | Rôle |
|---|---|---|---|---|
| `Type=simple` | défaut, premier plan | | `After=` | **ordre** |
| `Type=forking` | le parent se termine | | `Requires=` | **dépendance dure** |
| `Type=oneshot` | + `RemainAfterExit=yes` | | `Wants=` | dépendance souple |
| `Type=notify` | `sd_notify(READY=1)` | | `BindsTo=` / `PartOf=` | suit les arrêts / propage stop |
| `Restart=on-failure\|always` | redémarrage | | `WantedBy=multi-user.target` | activation au boot |
| `ExecStart=` `ExecStartPre=` `ExecReload=` | commandes | | `User=` `Group=` `UMask=` | identité |
| `LimitNOFILE=65536` | descripteurs | | `MemoryMax=` `CPUQuota=200%` `TasksMax=` | cgroup |
| `PrivateTmp=` `ProtectSystem=strict` `NoNewPrivileges=` | durcissement | | `EnvironmentFile=-/etc/x` | `-` = optionnel |

**Chemins, par priorité décroissante** : `/etc/systemd/system/` (admin) > `/run/systemd/system/` > `/usr/lib/systemd/system/` (paquet).
Drop-in : `/etc/systemd/system/UNIT.d/override.conf`. Unité utilisateur : `~/.config/systemd/user/` + `systemctl --user`.

```bash
journalctl -u UNIT -f            # suivre
journalctl -u UNIT -b            # ce boot ; -b -1 = boot précédent ; --list-boots
journalctl --since "2 hours ago" --until "10 min ago" · --since "2026-09-09 02:00"
journalctl -p err -b             # priorité <= 3 ; -k = noyau ; _PID=1234 ; -o json-pretty
journalctl -n 200 --no-pager · --disk-usage · --vacuum-time=7d · --vacuum-size=500M
```
**Priorités** : `0` emerg · `1` alert · `2` crit · **`3` err** · **`4` warning** · `5` notice · **`6` info** · **`7` debug**.

## 7. Timers et cron

| `OnCalendar=` | Sens | | Champ cron | Plage |
|---|---|---|---|---|
| `*-*-* 02:00:00` | tous les jours à 2 h | | minute | 0-59 |
| `Mon..Fri *-*-* 06:30` | jours ouvrés | | heure | 0-23 |
| `*-*-01 00:00:00` | le 1er du mois | | jour du mois | 1-31 |
| `hourly` `daily` `weekly` `monthly` | raccourcis | | mois | 1-12 |
| `*:0/15` | toutes les 15 min | | jour de semaine | **0-7 (0 et 7 = dimanche)** |

Timer : `Persistent=true` (rattrapage) · `RandomizedDelaySec=300` · `OnBootSec=` · `OnUnitActiveSec=` · `AccuracySec=1s` (défaut `1min`) · `[Install] WantedBy=timers.target`.
Cron : `crontab -e|-l|-r` · `/etc/cron.d/` · `@reboot @daily @hourly` · `MAILTO=` · **`%` à échapper** · **PATH minimal → chemins absolus**.

## 8. Mémoire

```bash
free -h                     # lire AVAILABLE, pas free ; buff/cache est récupérable
vmstat 1                    # r b | swpd free buff cache | si so | bi bo | in cs | us sy id wa st
cat /proc/meminfo · /proc/PID/status | grep Vm · /proc/PID/smaps_rollup   # Pss
smem -k -s pss              # classement par PSS
dmesg -T | grep -i -E 'oom|killed process'
cat /sys/fs/cgroup/<...>/memory.max · memory.current · memory.events   # cgroup v2
echo -500 > /proc/PID/oom_score_adj
sysctl vm.swappiness vm.overcommit_memory vm.dirty_ratio
sync; echo 3 > /proc/sys/vm/drop_caches      # vider le page cache (bench uniquement)
```

| Métrique | Ce que c'est | Piège |
|---|---|---|
| **VSZ / VIRT** | espace d'adressage réservé | pas de la RAM ; JVM `-Xmx4g` → 12 Gio |
| **RSS / RES** | pages en RAM | **double-compte le partagé** |
| **PSS** | part équitable du partagé | la bonne métrique |
| `available` | allouable sans swapper | **la colonne à alerter** |

## 9. Disque

```bash
df -h · df -i               # ESPACE puis INODES — toujours les deux
du -sh * | sort -h · du -h --max-depth=1 /var | sort -h · du -sh --exclude=… 
lsblk -f · blkid · findmnt · findmnt -t nfs4 · mount | column -t
mount -o remount,ro /data · umount -l /data (paresseux) · fuser -km /data
lsof +L1 · lsof /data/f · lsof -i :9092 · lsof -p PID · lsof -u user
tune2fs -l /dev/sda1 · tune2fs -m 1 /dev/sda1 · dumpe2fs -h · xfs_info /data
pvs vgs lvs · pvcreate · vgextend vg0 /dev/sdc · lvextend -L +200G -r /dev/vg0/data
resize2fs /dev/vg0/data (ext4) · xfs_growfs /data (XFS, GROWTH SEULEMENT)
```

`/etc/fstab` : `UUID=… /data ext4 defaults,noatime,nofail 0 2` — **6 champs**, passno `0` jamais / `1` racine / `2` autres.
Options : `noatime` `nofail` `ro` `nosuid` `nodev` `noexec` `_netdev`.

| Symptôme | Cause probable | Commande |
|---|---|---|
| `df` plein, `du` vide | fichier supprimé encore ouvert | **`lsof +L1`** |
| `df` plein, `du` vide | données masquées par un montage | `mount --bind / /mnt; du /mnt` |
| `No space left`, place libre | **inodes épuisés** | **`df -i`** |
| `Device or resource busy` | quelqu'un tient le point de montage | `fuser -vm /data` |
| disque 100 % `%util` | saturation E/S | `iostat -xz 1` |

## 10. Diagnostic

| Question | Commande |
|---|---|
| La machine est-elle chargée ? | `uptime` (1/5/15 min, comparer à `nproc`) |
| Qui consomme quoi ? | `top` · `htop` · `ps -eo …--sort=-rss` |
| CPU ou E/S ? | `top` → colonne **`wa`** ; `vmstat 1` ; `iostat -xz 1` |
| Ça swappe ? | `vmstat 1` colonnes **`si`/`so`** |
| Qui tient ce fichier / ce port ? | `lsof /chemin` · `lsof -i :PORT` · `fuser -v` |
| Que fait ce process figé ? | `strace -f -T -p PID` · `cat /proc/PID/stack` · `strace -c` |
| Le noyau a-t-il parlé ? | `dmesg -T -l err,warn` · `dmesg -w` · `journalctl -k` |
| Quels services ont échoué ? | `systemctl --failed` · `journalctl -p err -b` |
| Combien de threads ? | `ps -o nlwp -p PID` · `top -H` |
| Qui écoute sur le réseau ? | `ss -tanp` · `ss -s` |

**L'ordre d'attaque** : `uptime` → `top` → `free -h` → `df -h` **et** `df -i` → `dmesg -T | tail` → `systemctl --failed`.
