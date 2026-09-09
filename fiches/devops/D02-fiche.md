# D02 — FICHE : Linux réseau & performance

> Lire **avant** le cours (pretesting), puis réciter de mémoire aux rappels. Cible : **3 minutes**.
> **Le fil rouge** : on diagnostique **de bas en haut** — Interface, Adresse, Voisin, Route, DNS, Socket,
> Filtre, Appli. Et **RST immédiat = personne n'écoute · silence = quelque chose DROPpe**.

## Les 8 étages du diagnostic
| # | Question | Commande | Panne typique |
|---|---|---|---|
| 1 | interface UP ? | `ip -c -br link` | `NO-CARRIER`, `DOWN` |
| 2 | une IP ? | `ip -c -br addr` | rien, ou `169.254.x.x` (DHCP mort) |
| 3 | voisin L2 ? | `ip neigh` | `FAILED`, mauvais VLAN |
| 4 | une route ? | `ip route get <dst>` | *Network is unreachable*, `src` inattendu |
| 5 | DNS ? | `getent hosts <nom>` | resolv.conf, ndots, résolveur mort |
| 6 | port ouvert ? | `nc -zv -w3 h p` / `ss -lntp` | bind sur **127.0.0.1** |
| 7 | filtre ? | `nft list ruleset` (**lire les compteurs**) | DROP |
| 8 | appli ? | `curl -v -w '%{time_*}'` | TTFB élevé |

## iproute2
`ip -br` bref · `-c` couleur · `-s` stats · `-d` détails · `-j -p` JSON · `-n NS` namespace.
**`ifconfig` ne voit qu'UNE IP** (net-tools lit `/proc` figé) ; **`ip`/`ss` parlent netlink**, filtre **dans le noyau**.
**`UP` = admin · `LOWER_UP` = porteuse** · UP sans LOWER_UP = `NO-CARRIER`.
`RX errors` = trame **abîmée** (câble). `RX dropped` = trame **saine jetée par l'hôte** (buffer, VLAN, backlog).
MTU **1500** · lo **65536** · VXLAN **1450** (−50) · jumbo 9001. qdisc défaut `fq_codel`, `txqueuelen 1000`.
Adresse : `/24` installe la route connectée — **mettre /32 casse tout le LAN**. Scopes **global · link · host**.
Tout `ip` est **volatile** (perdu au reboot) → netplan / systemd-networkd / NetworkManager.

## `ip neigh` — machine à états
`INCOMPLETE → REACHABLE (~30 s) → STALE (utilisable !) → DELAY (5 s) → PROBE (3 sondes) → FAILED`
**`STALE` est NORMAL.** `gc_thresh1/2/3` = **128 / 512 / 1024** → *neighbour table overflow* au-delà.

## Routage
**1. LONGEST PREFIX MATCH · 2. métrique la plus basse (à préfixe ÉGAL) · 3. ECMP.**
`ip rule` : **0 local (table 255) · 32766 main (254) · 32767 default (253)**. `scope link` = pas de `via`, on ARP la cible.
`ip route get` = **la vérité** (applique les règles, donne l'IP `src`).

## `ss`
`-t -u -l -a -n -p -i -e -m -s -o -K`. Filtres : `state established '( dport = :9092 )'`, `dst 10.244.0.0/16`.
| | `Recv-Q` | `Send-Q` |
|---|---|---|
| **LISTEN** | accept queue **courante** | **max** = `min(listen(), somaxconn)` |
| **ESTAB** | octets **non lus** par l'appli | octets **non acquittés** |
Recv-Q = Send-Q sur LISTEN → **débordement**, confirmé par `nstat` → `TcpExtListenOverflows`.
`ss -ti` : `cwnd` (segments) · `rtt/var` ms · `retrans:cur/total` · `send = cwnd×mss×8/rtt` · `minrtt` = latence incompressible.
**CLOSE_WAIT chez moi = MON bug** (pas de `close()`) · **FIN_WAIT_2 = le bug de l'AUTRE**.

## tcpdump
**RX : sonde AVANT netfilter (avant DNAT). TX : sonde APRÈS le NAT (adresses traduites).**
`-nn -e -c -w/-r -s -A/-X -Q in|out -ttt -i any`(SLL, pas de filtre `ether`). Snaplen défaut **262144**.
Primitives : `host net port portrange` × `src dst` × `ip tcp udp icmp arp vlan ether`, combinées `and/or/not`.
`tcp[tcpflags] == tcp-syn` = **SYN purs** · `& tcp-rst != 0` = qui coupe · `ip[6:2] & 0x1fff != 0` = fragments.
Flags affichés : `S` SYN · `S.` SYN+ACK · `.` ACK · `P.` données · `F.` FIN · `R` RST.
Signatures : **SYN×4 (1/2/4 s), rien** = DROP · **SYN → RST** = rien n'écoute · **RST tardif** = LB/NAT idle timeout.
⚠ `length 4344` sur MTU 1500 = **GRO/TSO** → `ethtool -K eth0 gro off gso off tso off`.

## Netfilter — l'ordre (à réciter)
```
1 NIC+tcpdump RX → 2 raw(-300) → 3 conntrack(-200) → 4 mangle PRE(-150)
→ 5 nat PRE/DNAT(-100) → 6 ROUTAGE → 7 filter FORWARD|INPUT(0)
→ 8 mangle POST(-150) → 9 nat POST/SNAT(+100) → 10 qdisc+NIC+tcpdump TX
```
**DNAT en PREROUTING (change la destination → avant le routage) · SNAT en POSTROUTING (dépend de l'interface de sortie).**
Crochets : PREROUTING · INPUT · FORWARD · OUTPUT · POSTROUTING. Tables : raw · mangle · nat · filter · security.
**Une règle `nat` ne s'applique qu'au 1ᵉʳ paquet (`NEW`)** ; conntrack rejoue ensuite.

## conntrack
États : `NEW · ESTABLISHED · RELATED · INVALID · UNTRACKED`. `[ASSURED]` = confirmé, sacrifié en dernier.
`tcp_timeout_established` = **432 000 s = 5 JOURS** · `time_wait` 120 · `udp` 30 · `icmp` 30.
≈ **300 octets/entrée** → 1 M ≈ 300 Mo. `max = 4 × buckets`. `table full, dropping packet` = drops **aléatoires**.
`conntrack -S` → `insert_failed` = course DNS UDP K8s → résolutions à **exactement 5 s**.

## Docker & kube-proxy = du Netfilter
`docker0` = **172.17.0.1/16** · `-p 8080:80` = **DNAT**, donc **FORWARD**, donc **INPUT/ufw ne protège pas**.
Tes règles vont dans **`DOCKER-USER`**. MASQUERADE de `172.17.0.0/16` + règle **hairpin**.
ClusterIP = **sur AUCUNE interface**, juste du DNAT sur chaque nœud. Répartition `--probability` : kᵉ règle = **1/(N−k+1)**.
Modes : `iptables` O(n) · `ipvs` O(1) · `nftables` (récent). Prérequis : `bridge-nf-call-iptables=1`.

## Namespaces
8 types : **mnt pid net ipc uts user cgroup time**. Conteneur = namespaces + cgroups + rootfs.
netns isole : interfaces, IP, routes, ARP, **ports**, netfilter, **conntrack**, `/proc/net`, `sysctl net.*`.
**Recette en 6 étapes** : `netns add` (+ **`lo up`**) → `bridge` + IP → `veth` (les **2** bouts UP) → IP+route dedans → `ip_forward=1` → `masquerade`.
⚠ Docker ne peuple pas `/var/run/netns` → `nsenter -t $(docker inspect -f '{{.State.Pid}}' c) -n tcpdump …`

## sysctl qui comptent
`somaxconn` **4096** (128 avant 5.4) · `tcp_max_syn_backlog` ~1024-2048 · `netdev_max_backlog` **1000** ·
`ip_forward` **0** · `tcp_rmem` **4096 131072 6291456** · `tcp_wmem` 4096 16384 4194304 · `rmem_max/wmem_max` **212992** ·
`ip_local_port_range` **32768 60999** · `tcp_fin_timeout` **60** · keepalive **7200/75/9** · `cubic` par défaut ·
`rp_filter` tue l'asymétrique · `tcp_mtu_probing=1` si ICMP filtré.
⚠ `tcp_rmem` = auto-tuning ; `rmem_max` = plafond de `SO_RCVBUF`. **Un `SO_RCVBUF` explicite désactive l'auto-tuning.**
Dans un conteneur, seuls les sysctl **namespacés** (`net.*`) sont modifiables.

## /proc et /sys
`/proc/net/{dev,tcp,sockstat,snmp,nf_conntrack,softnet_stat}` · `/proc/<pid>/net` = **le netns de ce PID** ·
`/sys/class/net/eth0/{mtu,speed,operstate,statistics/*}` · `/proc/pressure/{cpu,io,memory}` = **PSI**.
`softnet_stat` colonne 2 = **paquets jetés** (backlog plein), colonne 3 = time_squeeze.

## Performance — méthode USE
Pour chaque ressource : **U**tilisation, **S**aturation (le vrai signal), **E**rreurs.
`vmstat 1` : **`r` > cœurs = CPU · `b`/`wa` = disque · `si/so` ≠ 0 = mémoire · `st` = voisin bruyant**.
Puis `pidstat` (qui) → outil spécialisé (pourquoi). ⚠ **Le load Linux compte l'attente disque (état D)**.
⚠ **`%util` 100 % sur NVMe ne veut rien dire** → lire `await` et `aqu-sz`.
Latences : L1 1 ns · RAM 100 ns · syscall ~0,5 µs · loopback 30-50 µs · NVMe 20-100 µs · HDD seek 5-10 ms ·
RTT rack 0,1 ms · inter-AZ 0,5-2 ms · Paris↔Francfort 10 ms · Europe↔US-Est 80 ms · **≈1 ms de RTT / 100 km**.

## Test express
1. Quelle différence entre `UP` et `LOWER_UP` ?
2. `10.0.0.0/8 metric 10` et `10.0.1.0/24 metric 500` : quelle route pour `10.0.1.77` ?
3. Sur un socket LISTEN, que valent `Recv-Q` et `Send-Q` ?
4. Pourquoi le DNAT est-il en PREROUTING et le SNAT en POSTROUTING ?
5. Combien de temps une connexion TCP inactive occupe-t-elle une entrée conntrack ?
6. Sur quelle interface est configurée l'adresse ClusterIP d'un Service Kubernetes ?
7. Quelles adresses source montre `tcpdump -i eth0` en émission sur une machine qui masquerade ?
8. `nc` répond « refused » instantanément vs met 2 minutes : qu'est-ce que ça change au diagnostic ?
