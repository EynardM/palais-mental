# CHEATSHEET R01 — Couches, en-têtes, MTU, diagnostic réseau

## 1. Tailles d'en-têtes et de trames

| Élément | Taille | Note |
|---|---|---|
| Préambule + SFD | 8 o | hors trame |
| En-tête Ethernet II | **14 o** | 6 dst + 6 src + 2 EtherType |
| Balise VLAN 802.1Q | +4 o | TPID 0x8100 + TCI (PCP 3b, DEI 1b, VID 12b) |
| FCS (CRC-32) | 4 o | en queue de trame |
| IFG | 12 o | hors trame |
| En-tête IPv4 | 20 o (max 60) | IHL en mots de 32 bits, 5 = 20 o |
| En-tête IPv6 | 40 o fixe | pas de checksum, pas de fragmentation par routeur |
| En-tête TCP | 20 o (max 60) | Data Offset en mots de 32 bits |
| En-tête UDP | 8 o | src, dst, longueur, checksum |
| En-tête ICMP | 8 o | type, code, checksum, reste |
| VXLAN (total externe) | 50 o | Eth 14 + IP 20 + UDP 8 + VXLAN 8 |
| GRE | 24 o | IP 20 + GRE 4 (minimum) |
| WireGuard | 60–80 o | selon IPv4/IPv6 |
| Trame Ethernet | 64 à **1518 o** | 1522 avec VLAN |
| Charge utile Ethernet | 46 à **1500 o** | bourrage sous 46 |

## 2. Formules

```
MSS            = MTU − en-tête IP − en-tête TCP       (1500 − 20 − 20 = 1460)
MSS IPv6       = MTU − 40 − 20                         (1500 → 1440)
Trame totale   = MTU + 14 + 4                          (1500 → 1518)
Sur le fil     = MTU + 14 + 4 + 8 + 12                 (1500 → 1538)
Débit TCP max  = Fenêtre / RTT
BDP            = Débit × RTT                           (10 Gb/s × 80 ms = 100 Mo)
Taille ping    = -s + 8 (ICMP) + 20 (IP)               (-s 1472 → 1500)
PMTU réel      = plus grand -s qui passe + 28
Latence fibre  = 5 µs/km  ->  10 ms RTT par 1000 km
```

## 3. EtherType (L2 → L3)

| Valeur | Protocole |
|---|---|
| `0x0800` | IPv4 |
| `0x0806` | ARP |
| `0x86DD` | IPv6 |
| `0x8100` | VLAN 802.1Q |
| `0x88A8` | QinQ 802.1ad |
| `0x8847` | MPLS unicast |

## 4. Numéros de protocole IP (L3 → L4)

| N° | Protocole | N° | Protocole |
|---|---|---|---|
| 1 | ICMP | 47 | GRE |
| 2 | IGMP | 50 | ESP (IPsec) |
| 6 | **TCP** | 51 | AH (IPsec) |
| 17 | **UDP** | 58 | ICMPv6 |
| 41 | IPv6-in-IPv4 | 89 | OSPF |
| 4 | IP-in-IP | 132 | SCTP |

## 5. Ports

**Plages** : 0–1023 well-known · 1024–49151 registered · 49152–65535 dynamiques (IANA).
**Éphémères Linux réels** : `32768–60999` → `sysctl net.ipv4.ip_local_port_range`.

| Port | Proto | Service | Port | Proto | Service |
|---|---|---|---|---|---|
| 20/21 | TCP | FTP data/ctrl | 1433 | TCP | MS SQL Server |
| 22 | TCP | SSH | 1521 | TCP | Oracle |
| 23 | TCP | Telnet | 2181 | TCP | ZooKeeper |
| 25 | TCP | SMTP | 2379/2380 | TCP | etcd client/peer |
| 53 | UDP+TCP | DNS | 3306 | TCP | MySQL |
| 67/68 | UDP | DHCP srv/cli | 4789 | UDP | **VXLAN** |
| 80 | TCP | HTTP | 5432 | TCP | **PostgreSQL** |
| 110 | TCP | POP3 | 5672 | TCP | AMQP / RabbitMQ |
| 123 | UDP | NTP | 6379 | TCP | Redis |
| 143 | TCP | IMAP | 6443 | TCP | **K8s API server** |
| 161/162 | UDP | SNMP | 8080 | TCP | HTTP alternatif |
| 389/636 | TCP | LDAP / LDAPS | 9092 | TCP | **Kafka broker** |
| 443 | TCP+UDP | HTTPS / QUIC-H3 | 9200/9300 | TCP | Elasticsearch |
| 514 | UDP | syslog | 10250 | TCP | kubelet |
| 587 | TCP | SMTP submission | 27017 | TCP | MongoDB |
| 993/995 | TCP | IMAPS / POP3S | 30000-32767 | TCP | K8s NodePort |

## 6. Codes ICMP utiles

| Type | Code | Signification | Qui l'émet |
|---|---|---|---|
| 0 | 0 | Echo Reply | cible de `ping` |
| 3 | 0 | Network Unreachable | routeur |
| 3 | 1 | Host Unreachable | routeur |
| 3 | 3 | Port Unreachable | hôte (fin de `traceroute` UDP) |
| **3** | **4** | **Fragmentation Needed and DF set** | routeur — **PMTU** |
| 3 | 13 | Communication Administratively Prohibited | pare-feu |
| 8 | 0 | Echo Request | `ping` |
| 11 | 0 | TTL exceeded in transit | routeur — **traceroute** |
| ICMPv6 1 | — | Destination Unreachable | routeur |
| **ICMPv6 2** | — | **Packet Too Big** | routeur — **PMTU v6** |
| ICMPv6 128/129 | — | Echo Request / Reply | `ping6` |

## 7. Flags TCP

Ordre dans l'octet : `CWR ECE URG ACK PSH RST SYN FIN`

| Flag | tcpdump | Sens |
|---|---|---|
| SYN | `[S]` | ouverture |
| SYN+ACK | `[S.]` | acceptation |
| ACK | `[.]` | acquittement |
| PSH+ACK | `[P.]` | données à remonter tout de suite |
| FIN+ACK | `[F.]` | fermeture propre |
| RST | `[R]` | fermeture brutale / port fermé |

## 8. Commandes — couche 1 et 2

```bash
ip -br link show                       # état bref de toutes les interfaces
ip -s link show eth0                   # compteurs : errors, dropped, overruns
ip link show eth0 | grep mtu           # MTU de l'interface
ip link set eth0 mtu 1450              # changer le MTU (root)
ethtool eth0                           # vitesse, duplex, autonégociation
ethtool -S eth0                        # statistiques détaillées du driver
ethtool -k eth0                        # offloads (GRO/GSO/TSO) — faussent tcpdump
ip neigh show                          # cache ARP/NDP
ip neigh show dev eth0 | grep FAILED   # voisins injoignables
ip neigh flush all                     # vider le cache ARP (root)
arping -I eth0 10.0.1.1                # tester un voisin en L2 pur
bridge fdb show                        # table MAC d'un bridge local
```

États `ip neigh` : `REACHABLE` (valide) · `STALE` (à revalider) · `DELAY`/`PROBE` (en cours) · `FAILED` (pas de réponse ARP).

## 9. Commandes — couche 3

```bash
ip -br addr show                       # adresses IP, format bref
ip route show                          # table de routage
ip route get 10.0.2.20                 # QUELLE route sera utilisée pour cette IP
ip route show table all                # toutes les tables (policy routing)
ip rule show                           # règles de sélection de table
ping -c 4 10.0.2.20                    # atteignabilité + RTT
ping -M do -s 1472 10.0.2.20           # test MTU 1500 sans fragmentation
ping -M do -s 1422 10.0.2.20           # test MTU 1450 (overlay VXLAN)
tracepath 10.0.2.20                    # traceroute + découverte PMTU, sans root
traceroute -n 10.0.2.20                # UDP ports 33434+, TTL croissant
traceroute -I -n 10.0.2.20             # variante ICMP
mtr -n --report -c 100 10.0.2.20       # traceroute + perte par saut, 100 sondes
sysctl net.ipv4.ip_forward             # cette machine route-t-elle ?
```

## 10. Commandes — couche 4

```bash
ss -tlnp                               # ports TCP en écoute + processus
ss -ulnp                               # idem UDP
ss -tnp state established              # connexions établies
ss -tn state syn-sent                  # SYN partis sans réponse = DROP en face
ss -tin dst 10.0.2.20                  # RTT, cwnd, retransmissions par connexion
ss -s                                  # résumé global des sockets
nc -zv 10.0.2.20 5432                  # le port répond-il ? (TCP)
nc -zvu 10.0.2.20 53                   # test UDP (peu fiable par nature)
timeout 3 bash -c '</dev/tcp/host/5432' && echo ouvert   # sans netcat
sysctl net.ipv4.ip_local_port_range    # plage éphémère
sysctl net.ipv4.tcp_window_scaling     # doit valoir 1
sysctl net.ipv4.tcp_rmem net.ipv4.tcp_wmem   # buffers min/défaut/max
nstat -az TcpRetransSegs TcpExtTCPTimeouts   # retransmissions cumulées
```

Champs utiles de `ss -tin` : `rtt:12.4/3.1` (RTT/variance en ms) · `cwnd:10` (fenêtre de congestion en segments) · `mss:1448` · `retrans:0/12` · `bytes_acked`.

## 11. Capture — tcpdump

```bash
tcpdump -i eth0 -nn -v host 10.0.2.20            # tout le trafic vers cette IP
tcpdump -i any -nn 'tcp port 5432'               # PostgreSQL
tcpdump -i eth0 -nn 'tcp[tcpflags] & tcp-syn != 0'   # uniquement les SYN
tcpdump -i eth0 -nn 'icmp'                       # voir passer le PMTU
tcpdump -i eth0 -nn 'icmp[icmptype] == 3'        # Destination Unreachable
tcpdump -i eth0 -nn 'udp port 4789'              # trafic VXLAN
tcpdump -i eth0 -nn -e arp                       # ARP avec en-têtes Ethernet
tcpdump -i eth0 -nn -s 0 -w capture.pcap         # capture complète pour Wireshark
tcpdump -i eth0 -nn 'greater 1400'               # trames > 1400 o (suspicion MTU)
```

- `-nn` : pas de résolution DNS ni de noms de ports (indispensable, sinon ça ment et ça rame).
- `-e` : affiche l'en-tête Ethernet (les MAC) — utile pour vérifier le prochain saut.
- Attention aux **offloads** (GRO/TSO) : tcpdump peut montrer des segments de 64 Ko qui n'existent pas sur le fil. `ethtool -K eth0 gro off tso off` pour un diagnostic MTU fiable.

Lecture d'une ligne : `IP src.port > dst.port: Flags [S], seq N, win W, options [mss 1460,sackOK,TS ...,wscale 7], length 0`.

## 12. Couches 5-7

```bash
dig +short example.com                 # résolution A
dig +trace example.com                 # chaîne de délégation complète
dig @8.8.8.8 example.com               # interroger un résolveur précis
getent hosts example.com               # résolution via le NSS de l'OS
openssl s_client -connect h:443 -servername h    # handshake TLS + certificat
openssl s_client -connect h:443 -tls1_3          # forcer une version
curl -v https://example.com            # en-têtes HTTP + détail TLS
curl -w '@-' -o /dev/null -s URL <<'EOF'
dns:%{time_namelookup} tcp:%{time_connect} tls:%{time_appconnect} ttfb:%{time_starttransfer} total:%{time_total}\n
EOF
curl --resolve host:443:10.0.2.20 https://host/  # bypass DNS, teste un backend
```

Le `curl -w` ci-dessus **décompose la latence par couche** : DNS (L7), TCP (L4), TLS (L5-6), TTFB (applicatif).

## 13. Débit et charge

```bash
iperf3 -s                              # serveur, port 5201 par défaut
iperf3 -c srv -t 30                    # 1 flux, 30 s
iperf3 -c srv -P 8                     # 8 flux parallèles -> contourne la limite Fenêtre/RTT
iperf3 -c srv -u -b 100M               # UDP à 100 Mb/s, mesure la perte et la gigue
iperf3 -c srv -M 1400                  # forcer le MSS
```

Si `-P 8` donne ~8× le débit de `-P 1`, le facteur limitant est la **fenêtre TCP**, pas le lien.

## 14. Réglages MTU / MSS

```bash
ip link set eth0 mtu 1450                                   # MTU d'interface
ip route change 10.0.2.0/24 dev eth0 mtu 1450               # MTU par route
iptables -t mangle -A FORWARD -p tcp --tcp-flags SYN,RST SYN \
         -j TCPMSS --clamp-mss-to-pmtu                      # MSS clamping
sysctl net.ipv4.tcp_mtu_probing=1                           # PMTUD robuste aux trous noirs
kubectl exec -it POD -- ip link show eth0                   # MTU réel d'un pod
```

## 15. Table de référence des valeurs par défaut

| Paramètre | Valeur |
|---|---|
| MTU Ethernet / jumbo | 1500 / 9000 |
| MSS IPv4 / IPv6 / avec timestamps | 1460 / 1440 / 1448 |
| TTL Linux / Windows / Cisco | 64 / 128 / 255 |
| Fenêtre TCP sans scaling / avec | 65 535 o / jusqu'à 1 Go (wscale ≤ 14) |
| Aging table CAM (Cisco) | 300 s |
| `base_reachable_time_ms` (ARP Linux) | 30 000 ms |
| VNI VXLAN / VID 802.1Q | 24 bits (16,7 M) / 12 bits (4094 utilisables) |
| Trame Ethernet min / max | 64 o / 1518 o |
| MTU minimum IPv4 / IPv6 | 68 / 1280 |
| Handshake TCP / TLS 1.2 / TLS 1.3 / QUIC | 1 / 3 / 2 / 1 RTT |

## 16. Conversions rapides

| Bits | Octets | Débit | Temps pour 1 Go |
|---|---|---|---|
| 1 Kb | 125 o | 100 Mb/s | ~80 s |
| 1 Mb | 125 Ko | 1 Gb/s | ~8 s |
| 1 Gb | 125 Mo | 10 Gb/s | ~0,8 s |
| 8 Gb | 1 Go | 25 Gb/s | ~0,32 s |

Règle : **débit en Gb/s ÷ 8 = Go/s**. 10 Gb/s = 1,25 Go/s en théorie, ~1,19 Go/s utiles après en-têtes (94,9 % d'efficacité avec MTU 1500).
