# D02 — CHEATSHEET : Linux réseau & performance

Référence opérationnelle. À garder ouverte pendant qu'on travaille.

---

## 1. Le réflexe : les 8 étages, en 8 commandes

```bash
ip -c -br link                    # 1. interface UP / NO-CARRIER ?
ip -c -br -4 addr                 # 2. une IP ? (169.254.x = DHCP mort)
ip neigh show 10.0.1.1            # 3. la passerelle répond en ARP ?
ip route get 10.0.3.7             # 4. quelle route, quelle IP source ?
getent hosts kafka.data.svc       # 5. DNS *tel que le voit l'appli*
nc -zv -w 3 10.0.3.7 9092         # 6. port ouvert ? refused vs timeout
nft list ruleset | less           # 7. filtrage — LIRE LES COMPTEURS
curl -v -o /dev/null -w '%{time_connect} %{time_starttransfer} %{time_total}\n' URL   # 8.
```

| Réponse de `nc -zv` | Signal réseau | Cause |
|---|---|---|
| `succeeded` | SYN+ACK | OK jusqu'à L4 |
| `Connection refused` | **RST** | rien n'écoute / bind sur 127.0.0.1 / REJECT |
| `Connection timed out` (~2 min) | **rien** | DROP, ou pas de route retour |
| `No route to host` | ICMP unreachable | trou de routage ou REJECT ICMP |

## 2. Ancien → nouveau

| net-tools | iproute2 |
|---|---|
| `ifconfig` | `ip addr` / `ip link` |
| `ifconfig eth0 up` | `ip link set eth0 up` |
| `ifconfig eth0 mtu 9000` | `ip link set eth0 mtu 9000` |
| `route -n` | `ip route` |
| `route add default gw X` | `ip route add default via X` |
| `arp -an` | `ip neigh` |
| `netstat -tulpn` | `ss -tulpn` |
| `netstat -s` | `nstat` (deltas) / `nstat -az` (absolus) |
| `netstat -i` | `ip -s link` |
| `netstat -rn` | `ip route` |
| `iptables` | `nft` |

Options communes d'`ip` : **`-br`** bref · **`-c`** couleur · **`-s`** stats · **`-d`** détails · **`-4/-6`** ·
**`-j -p`** JSON · **`-n <ns>`** namespace.

## 3. `ip link`

```bash
ip -br link                                  ip -s link show eth0
ip link set eth0 up|down                     ip link set eth0 mtu 9000
ip link set eth0 promisc on                  ip link set eth0 address 02:11:22:33:44:55
ip link add br0 type bridge                  ip link set veth0 master br0
ip link add veth0 type veth peer name ceth0  ip link set ceth0 netns ns1
ip link add link eth0 name eth0.42 type vlan id 42
ip link del br0
```

| Flag / champ | Sens |
|---|---|
| `UP` | administratif (`ip link set … up`) |
| `LOWER_UP` | porteuse physique présente |
| `NO-CARRIER` | UP mais pas de signal (câble, veth non montée des 2 côtés) |
| `qdisc fq_codel` | file de sortie (défaut) ; `noqueue` sur `lo`/bridge |
| `qlen 1000` | `txqueuelen` par défaut Ethernet |
| `RX errors` | trame **abîmée** (CRC, câble, duplex) |
| `RX dropped` | trame **saine jetée par l'hôte** (buffer, VLAN, backlog) |
| `RX overrun` | ring buffer NIC débordé |

| MTU | Contexte |
|---:|---|
| 65536 | `lo` |
| 9001 / 8951 | jumbo cloud |
| 1500 | Ethernet standard |
| 1450 | derrière VXLAN (−50) |
| 1476 | GRE (−24) |
| 1440 / 1420 | WireGuard (−60 en IPv4, −80 en IPv6 ; `wg-quick` met **1420** par défaut) |

## 4. `ip addr`

```bash
ip -br -4 addr                       ip addr add 10.0.1.99/24 dev eth0
ip addr del 10.0.1.99/24 dev eth0    ip addr flush dev eth0
```
`inet 10.0.1.12/24 brd … scope global dynamic eth0` + `valid_lft` = bail DHCP.
Scopes : **`global`** routable · **`link`** (fe80::, 169.254) · **`host`** (127.0.0.1).
⚠ `/32` au lieu du vrai préfixe = **plus de route connectée** = LAN injoignable.

## 5. `ip neigh`

```bash
ip neigh                              ip neigh flush dev eth0
ip neigh add 10.0.1.1 lladdr 0a:58:0a:00:01:01 dev eth0 nud permanent
ip neigh | grep -E 'FAILED|INCOMPLETE'
```

| État | Sens | Alarme ? |
|---|---|---|
| `INCOMPLETE` | ARP parti, sans réponse | oui si persistant |
| `REACHABLE` | confirmé (~30 s) | non |
| `STALE` | vieux mais **utilisable** | **non — c'est normal** |
| `DELAY` | attente d'une confirmation (5 s) | non |
| `PROBE` | sondes unicast (3) | non |
| `FAILED` | ne répond pas | **oui** |
| `PERMANENT` / `NOARP` | statique / pas de résolution | non |

`net.ipv4.neigh.default.gc_thresh1/2/3` = **128 / 512 / 1024** → *neighbour table overflow*.

## 6. `ip route` / `ip rule`

```bash
ip route                                  ip route get 10.0.3.7
ip route get 8.8.8.8 from 10.0.1.99       ip route get 8.8.8.8 oif eth1
ip route add 10.20.0.0/16 via 10.0.1.254  ip route replace default via 10.0.1.1
ip route add default via 10.0.1.1 metric 200
ip route add 10.30.0.0/16 dev eth0 onlink via 192.168.99.1
ip route show table all                   ip route show table 100
ip rule                                   ip rule add from 10.0.1.99 lookup vpn priority 100
ip rule add fwmark 0x1 lookup vpn priority 101
```

**Sélection : 1) longest prefix match · 2) métrique la plus basse à préfixe égal · 3) ECMP.**

| Table | ID | Priorité de règle |
|---|---:|---:|
| `local` | 255 | 0 |
| `main` | 254 | 32766 |
| `default` | 253 | 32767 |

`proto` : `kernel` · `dhcp` · `static` · `boot` · `ra` · `bird`/`bgp`. `scope link` = pas de `via` (on ARP la cible).

## 7. `ss`

```bash
ss -lntp                                    # ports en écoute + processus
ss -tanp state established                  # connexions établies
ss -tin dst 10.0.3.7                        # radiographie TCP
ss -tn state time-wait | wc -l
ss -tp state close-wait                     # fuite de FD dans TON appli
ss -t '( dport = :9092 or sport = :9092 )'
ss -t dst 10.244.0.0/16                     ss -uap
ss -s                                       ss -tem                # étendu + mémoire
ss -K dst 10.0.3.7 dport = 9092             # TUER les sockets (root)
```

| Option | Effet |
|---|---|
| `-t -u -x -w` | TCP · UDP · Unix · raw |
| `-l` / `-a` | écoute / tout |
| `-n` | pas de résolution (**toujours**) |
| `-p` | processus |
| `-i` | infos TCP internes |
| `-e` | uid, inode, **cgroup** (→ conteneur) |
| `-m` | `skmem` |
| `-o` | timers |
| `-s` | résumé |

| État | `Recv-Q` | `Send-Q` |
|---|---|---|
| `LISTEN` | accept queue courante | max = `min(listen(), somaxconn)` |
| `ESTAB` | octets non lus | octets non acquittés |

`ss -ti` : `cwnd` en **segments** · `rtt:lissé/variance` ms · `rto` ms · `retrans:cur/total` ·
`send = cwnd × mss × 8 / rtt` · `minrtt` = latence incompressible · `wscale:envoyé,reçu`.

États filtrables : `established syn-sent syn-recv fin-wait-1 fin-wait-2 time-wait closed close-wait
last-ack listening closing connected synchronized bucket big`.

## 8. Compteurs

```bash
nstat                       # deltas depuis le dernier appel
nstat -az | grep -E 'ListenOverflows|ListenDrops|TCPSynRetrans|RetransSegs|TCPLostRetransmit'
ip -s link show eth0        # RX/TX errors, dropped
awk '{print $2}' /proc/net/softnet_stat    # drops par CPU (doit rester 0)
cat /proc/net/sockstat      # sockets + mémoire TCP
ethtool -S eth0 | grep -iE 'drop|err|miss'
ethtool -g eth0             # taille des ring buffers ; -G pour les changer
ethtool -k eth0             # offloads ; -K pour les désactiver
```

## 9. DNS

```bash
getent hosts NOM           # ← comme l'application (NSS : /etc/hosts PUIS DNS)
dig +short A NOM           dig @10.0.0.10 NOM        dig +trace NOM
dig +norecurse @ns1 NOM    dig -x 10.0.3.7           dig NOM AAAA
resolvectl status          resolvectl query NOM
```

| Statut | Sens |
|---|---|
| `NOERROR` + ANSWER≥1 | OK |
| `NOERROR` + ANSWER=0 | nom existant, **pas ce type** |
| `NXDOMAIN` | nom inexistant (faute, ou `search` manquant) |
| `SERVFAIL` | résolveur en échec (zone, DNSSEC, upstream) |
| `REFUSED` | ACL du serveur |

`options ndots:N` — défaut **1**, **5 en Kubernetes** → 4 tentatives × 2 (A/AAAA) = **8 requêtes** pour un nom externe.
`timeout:5 attempts:2` par défaut. Max **3 `nameserver`** pris en compte.

## 10. `curl` / `nc`

```bash
curl -v https://h/p
curl -sS -o /dev/null -w 'dns=%{time_namelookup} tcp=%{time_connect} tls=%{time_appconnect} ttfb=%{time_starttransfer} tot=%{time_total}\n' URL
curl --resolve h:443:10.0.3.21 https://h/     curl -k / --http1.1 / -x http://proxy:3128
nc -zv -w 3 HOST PORT      nc -zv -w1 HOST 9090-9100      nc -l 9000      nc -lu 9999
timeout 3 bash -c 'cat </dev/null >/dev/tcp/HOST/PORT' && echo OUVERT
```
Les `time_*` sont **cumulatifs** : handshake TCP = `time_connect − time_namelookup` ; TLS = `appconnect − connect` ;
réflexion serveur = `starttransfer − appconnect`.

## 11. `traceroute` / `mtr`

```bash
traceroute -I 8.8.8.8            # ICMP
traceroute -T -p 443 host        # SYN TCP (traverse les pare-feux)
mtr -n -T -P 9092 10.0.3.7
mtr --report --report-cycles 100 -n host
```
UDP par défaut sous Linux (ports 33434+), souvent filtré. **Seule la DERNIÈRE ligne mesure la vraie perte** :
une perte intermédiaire non propagée = ICMP rate-limité, pas un incident.

## 12. `tcpdump`

```bash
tcpdump -i eth0 -nn -c 100 host 10.0.3.7
tcpdump -i any -nn 'tcp port 9092 and not host 10.0.1.5'
tcpdump -i eth0 -nn -w /tmp/c.pcap 'host 10.0.3.7'   # capturer puis analyser
tcpdump -r /tmp/c.pcap -nn -ttt 'tcp[tcpflags] & tcp-rst != 0'
tcpdump -i eth0 -nn -e 'arp or icmp'
tcpdump -i eth0 -nn -G 60 -W 10 -w cap-%H%M.pcap     # rotation
nsenter -t $(docker inspect -f '{{.State.Pid}}' C) -n tcpdump -i eth0 -nn
```

| Option | Effet |
|---|---|
| `-nn` | ni DNS ni noms de services |
| `-e` | en-tête Ethernet (MAC, VLAN) |
| `-c N` / `-s N` | N paquets / snaplen (défaut **262144**) |
| `-w` / `-r` | écrire / relire |
| `-A -X -XX` | payload ASCII / hexa / avec L2 |
| `-Q in\|out` | sens |
| `-ttt` | delta entre paquets |
| `-i any` | toutes interfaces (**SLL** : filtres `ether` KO) |
| `-Z user` | abandonne les privilèges |

| Filtre | Attrape |
|---|---|
| `host H` / `net 10.0.0.0/8` / `port 443` / `portrange 9090-9100` | base |
| `src H` / `dst H` | direction |
| `tcp[tcpflags] == tcp-syn` | **SYN purs** = tentatives de connexion |
| `tcp[tcpflags] & tcp-rst != 0` | qui coupe les connexions |
| `tcp[tcpflags] & (tcp-syn\|tcp-fin\|tcp-rst) != 0` | squelette des connexions |
| `ip[8] < 5` | TTL faible |
| `ip[6] & 0x20 != 0` | flag *More Fragments* |
| `ip[6:2] & 0x1fff != 0` | fragments non initiaux |
| `udp[10:2] = 0x0100` | requêtes DNS (flags DNS = udp[10:2], l'ID est en udp[8:2]) |
| `greater 1400` / `less 100` | taille |
| `vlan 42` | ⚠ décale tous les offsets suivants de 4 o |

Flags affichés : `S` SYN · `S.` SYN+ACK · `.` ACK · `P.` PSH+ACK · `F.` FIN+ACK · `R` RST · `E` ECE · `W` CWR.
Valeurs : `tcp-fin` 0x01 · `tcp-syn` 0x02 · `tcp-rst` 0x04 · `tcp-push` 0x08 · `tcp-ack` 0x10 · `tcp-urg` 0x20 ·
`tcp-ece` 0x40 · `tcp-cwr` 0x80.

## 13. Netfilter — ordre et priorités

```
1 NIC+tap RX → 2 raw(-300) → 3 conntrack(-200) → 4 mangle PRE(-150) → 5 nat PRE/DNAT(-100)
→ 6 ROUTAGE → 7 filter FORWARD|INPUT(0) → 8 mangle POST(-150) → 9 nat POST/SNAT(+100) → 10 qdisc+NIC+tap TX
```

| Table | Priorité | Crochets |
|---|---:|---|
| `raw` | −300 | PRE, OUT |
| conntrack | −200 | PRE, OUT |
| `mangle` | −150 | les 5 |
| `nat` (dnat) | −100 | PRE, OUT |
| `filter` | 0 | IN, FWD, OUT |
| `security` | +50 | IN, FWD, OUT |
| `nat` (snat) | +100 | POST, IN |

| Cible | Où | Effet |
|---|---|---|
| `DNAT --to IP:PORT` | nat PRE/OUT | change la **destination** |
| `REDIRECT --to-port N` | nat PRE/OUT | DNAT vers la machine elle-même |
| `SNAT --to IP` | nat POST | source **fixe** |
| `MASQUERADE` | nat POST | source = IP **courante** de l'interface de sortie |
| `MARK --set-mark 0x1` | mangle | marque pour `ip rule fwmark` |
| `NOTRACK` | raw | contourne conntrack |
| `REJECT --reject-with X` | filter | RST/ICMP au lieu du silence |

## 14. `iptables` / `nftables`

```bash
iptables -L -n -v --line-numbers            # -n OBLIGATOIRE
iptables -t nat -L -n -v
iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
iptables -A INPUT -p tcp --dport 22 -j ACCEPT
iptables -t nat -A POSTROUTING -s 10.10.0.0/24 -o eth0 -j MASQUERADE
iptables -t nat -A PREROUTING -i eth0 -p tcp --dport 8080 -j DNAT --to-destination 10.10.0.2:80
iptables -D INPUT 3            iptables -P INPUT DROP        iptables -Z    # remise à zéro compteurs
iptables-save > /etc/iptables/rules.v4      iptables-translate -A …          iptables -V

nft list ruleset               nft -a list ruleset            # -a = handles
nft add table inet filter
nft 'add chain inet filter input { type filter hook input priority filter; policy drop; }'
nft add rule inet filter input ct state established,related accept
nft add rule inet filter input tcp dport { 22, 80, 443 } accept counter
nft delete rule inet filter input handle 7
nft -f /etc/nftables.conf      # rechargement ATOMIQUE
nft flush ruleset              nft monitor trace
```

| | iptables | nftables |
|---|---|---|
| binaires | 4 (`ip/ip6/arp/eb`) | 1, familles `ip ip6 inet arp bridge netdev` |
| tables/chaînes | imposées | créées par toi (crochet + priorité) |
| ensembles | `ipset` | `set` / `map` natifs |
| rechargement | règle à règle | `nft -f` **atomique** |
| compteurs | toujours | optionnels (`counter`) |

Noms de priorité nft : `raw` −300 · `mangle` −150 · `dstnat` −100 · `filter` 0 · `security` 50 · `srcnat` 100.

## 15. `conntrack`

```bash
conntrack -L | head            conntrack -S            # drop, insert_failed, invalid
conntrack -E                   # événements en direct
conntrack -D -s 10.244.1.7     conntrack -F            # ⚠ flush total
sysctl net.netfilter.nf_conntrack_count net.netfilter.nf_conntrack_max
sysctl net.netfilter.nf_conntrack_buckets
dmesg -T | grep -i conntrack
```

| Timeout | Défaut |
|---|---:|
| `tcp_timeout_established` | **432 000 s (5 j)** |
| `tcp_timeout_time_wait` | 120 |
| `tcp_timeout_close_wait` | 60 |
| `tcp_timeout_syn_sent` | 120 |
| `udp_timeout` | 30 |
| `udp_timeout_stream` | 120 |
| `icmp_timeout` | 30 |

≈ **300 o / entrée** · `max = 4 × buckets` · `N = λ × T` (Little) pour le dimensionnement.

## 16. Namespaces — la recette complète

```bash
ip netns add ns1 && ip netns exec ns1 ip link set lo up      # ← ne JAMAIS oublier lo
ip link add br0 type bridge && ip addr add 10.10.0.1/24 dev br0 && ip link set br0 up
ip link add veth0 type veth peer name ceth0
ip link set veth0 master br0 && ip link set veth0 up
ip link set ceth0 netns ns1
ip netns exec ns1 ip addr add 10.10.0.2/24 dev ceth0
ip netns exec ns1 ip link set ceth0 up
ip netns exec ns1 ip route add default via 10.10.0.1
sysctl -w net.ipv4.ip_forward=1
nft add table ip nat
nft 'add chain ip nat postrouting { type nat hook postrouting priority srcnat; }'
nft add rule ip nat postrouting ip saddr 10.10.0.0/24 oifname "eth0" masquerade
```

```bash
ip netns list          ip -n ns1 route          ip netns exec ns1 CMD
lsns -t net            ls -l /proc/$$/ns/       nsenter -t PID -n CMD
pid=$(docker inspect -f '{{.State.Pid}}' C); ln -sf /proc/$pid/ns/net /var/run/netns/C
```

| Manque | Symptôme |
|---|---|
| `lo up` | `ping 127.0.0.1` → *Network is unreachable* |
| `veth0 up` côté hôte | **NO-CARRIER** dans le namespace |
| route par défaut | LAN OK, Internet *unreachable* |
| `ip_forward=1` | rien ne sort : `tcpdump -i eth0` muet |
| `masquerade` | paquets partent en `src=10.10.0.2`, **rien ne revient** |

8 namespaces : **mnt · pid · net · ipc · uts · user · cgroup · time**.

## 17. `sysctl` réseau

```bash
sysctl -a | grep -E 'somaxconn|rmem|forward'     sysctl -w net.core.somaxconn=8192
echo 'net.core.somaxconn = 8192' > /etc/sysctl.d/99-net.conf && sysctl --system
docker run --sysctl net.core.somaxconn=4096 …
```

| Paramètre | Défaut |
|---|---|
| `net.core.somaxconn` | **4096** (128 avant 5.4) |
| `net.ipv4.tcp_max_syn_backlog` | 1024-2048 (selon RAM) |
| `net.ipv4.tcp_syncookies` | 1 |
| `net.core.netdev_max_backlog` | 1000 |
| `net.ipv4.ip_forward` | 0 |
| `net.ipv4.tcp_rmem` | `4096 131072 6291456` |
| `net.ipv4.tcp_wmem` | `4096 16384 4194304` |
| `net.core.rmem_max` / `wmem_max` | 212992 |
| `net.ipv4.ip_local_port_range` | `32768 60999` (28 232) |
| `net.ipv4.tcp_fin_timeout` | 60 |
| `tcp_keepalive_time/_intvl/_probes` | 7200 / 75 / 9 |
| `net.ipv4.tcp_congestion_control` | `cubic` |
| `net.ipv4.tcp_mtu_probing` | 0 |
| `net.bridge.bridge-nf-call-iptables` | 1 (prérequis K8s) |
| `vm.max_map_count` | 65530 (Elastic exige 262144) |

## 18. `/proc` et `/sys`

| Chemin | Contenu |
|---|---|
| `/proc/net/dev` | compteurs par interface |
| `/proc/net/tcp` | sockets (hexa little-endian) |
| `/proc/net/sockstat` | sockets + mémoire TCP |
| `/proc/net/snmp`, `/netstat` | compteurs RFC (source de `nstat`) |
| `/proc/net/nf_conntrack` | table conntrack |
| `/proc/net/softnet_stat` | col.1 traités · **col.2 jetés** · col.3 time_squeeze |
| `/proc/<pid>/net/` | `/proc/net` **du netns de ce PID** |
| `/proc/<pid>/fd/`, `/limits` | descripteurs, RLIMIT_NOFILE |
| `/proc/pressure/{cpu,io,memory}` | PSI |
| `/proc/interrupts`, `/softirqs` | IRQ / `NET_RX`, `NET_TX` par cœur |
| `/sys/class/net/eth0/{mtu,speed,operstate,address}` | attributs |
| `/sys/class/net/eth0/statistics/*` | compteurs unitaires |

## 19. Performance — checklist 60 s

```bash
uptime ; dmesg -T | tail -30 ; vmstat 1 5 ; mpstat -P ALL 1 3 ; pidstat 1 3
iostat -xz 1 3 ; free -m ; sar -n DEV 1 3 ; ss -s ; nstat
cat /proc/pressure/cpu /proc/pressure/io /proc/pressure/memory
```

| `vmstat` | Lecture |
|---|---|
| `r` > cœurs | saturation **CPU** |
| `b`, `wa` élevés | **disque** |
| `si`/`so` ≠ 0 | **mémoire** (swap) |
| `st` ≠ 0 | vol de CPU par l'hyperviseur |
| `cs`, `in` très élevés | contention / IRQ |

| Ressource | Utilisation | Saturation | Erreurs |
|---|---|---|---|
| CPU | `mpstat -P ALL 1` | `r`, `/proc/pressure/cpu` | — |
| Mémoire | `free -m` (`available`) | `si/so`, OOM | `dmesg \| grep -i oom` |
| Disque | `iostat -xz` `%util` | `await`, `aqu-sz`, `b` | `dmesg` |
| Réseau | `sar -n DEV 1` | `ss -ti` retrans, `ip -s link` dropped | RX errors, TX carrier |

⚠ Load Linux = runnable **+ état D** (attente disque). ⚠ `%util` 100 % ≠ saturé sur NVMe → lire `await`.

## 20. Ordres de grandeur

| Opération | Latence |
|---|---|
| Cache L1 | ~1 ns |
| RAM | ~100 ns |
| Appel système | 0,3 - 1 µs |
| Changement de contexte | 1 - 5 µs |
| Aller-retour loopback | 30 - 50 µs |
| NVMe 4 Ko | 20 - 100 µs |
| SSD SATA | ~150 µs |
| RTT même rack | 0,1 - 0,2 ms |
| RTT inter-AZ | 0,5 - 2 ms |
| HDD seek | 5 - 10 ms |
| RTT Paris ↔ Francfort | ~10 ms |
| RTT Europe ↔ US-Est | 75 - 90 ms |
| RTT Europe ↔ Singapour | ~160 ms |
| **Règle** | **≈ 1 ms de RTT / 100 km** |

| Grandeur | Formule |
|---|---|
| BDP (octets) | `débit(bit/s) × RTT(s) / 8` |
| Débit atteignable | `fenêtre / RTT` |
| Débit `ss -ti` | `cwnd × mss × 8 / rtt` |
| Entrées conntrack | `λ (conn/s) × T (durée + timeout)` |
| RAM conntrack | `entrées × ~300 o` |
| Proba kᵉ endpoint kube-proxy | `1 / (N − k + 1)` |
