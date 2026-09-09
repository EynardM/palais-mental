# R06 — CHEATSHEET : TCP, UDP, QUIC

Référence opérationnelle. À garder ouverte pendant qu'on travaille.

---

## 1. Formules à avoir sous la main

| Grandeur | Formule | Exemple à retenir |
|---|---|---|
| **BDP** (octets) | `BP(bit/s) × RTT(s) / 8` | 10 Gbit/s × 80 ms = **100 Mo** |
| **Débit atteignable** | `Fenêtre / RTT` | 65 535 / 0,08 = **6,5 Mbit/s** (sans scaling) |
| **Débit depuis `ss -ti`** | `cwnd × mss / rtt` | 142 × 1448 / 0,0843 ≈ **19,5 Mbit/s** |
| **Mathis (plafond de perte)** | `≈ MSS / (RTT × √p)` | p = 10⁻⁵, RTT 80 ms → **46 Mbit/s** |
| **Facteur window scale** | `2^s ≥ BDP / 65 535` | BDP 100 Mo → **s = 11** |
| **Fenêtre max scalée** | `65 535 × 2^s`, s ≤ 14 | **≈ 1 Gio** |
| **Slow start : RTT pour W** | `n = log₂(W / 10 MSS)` | 100 Mo → **13 RTT ≈ 1,05 s** |
| **Épuisement de ports** | `ports / 60 s` | 28 232 / 60 ≈ **470 conn/s** |
| **RTO** | `SRTT + 4 × RTTVAR` | init **1 s**, min Linux **200 ms** |
| **Latence fibre** | **≈ 1 ms de RTT / 100 km** | Europe ↔ US-est **75-90 ms** |

## 2. En-tête TCP (20-60 o) et flags

| Offset | Champ | Taille |
|---:|---|---|
| 0 | Port source / destination | 2 + 2 o |
| 4 | Numéro de séquence | 4 o |
| 8 | Numéro d'acquittement | 4 o |
| 12 | Data offset (4 b) · réservé (4 b) · flags (8 b) · **fenêtre** (16 b) | 4 o |
| 16 | Checksum (pseudo-en-tête inclus) · pointeur urgent | 4 o |
| 20 | Options (0-40 o, multiple de 4) | — |

| Flag | Bit | Hexa | Sens | `tcpdump` |
|---|---:|---|---|---|
| CWR | 7 | 0x80 | Fenêtre réduite (ECN) | `tcp-cwr` |
| ECE | 6 | 0x40 | Écho de congestion (ECN) | `tcp-ece` |
| URG | 5 | 0x20 | Pointeur urgent (obsolète) | `tcp-urg` |
| ACK | 4 | 0x10 | Champ ack valide | `tcp-ack` |
| PSH | 3 | 0x08 | Remonter à l'appli tout de suite | `tcp-push` |
| RST | 2 | 0x04 | Abandon brutal | `tcp-rst` |
| SYN | 1 | 0x02 | Ouverture | `tcp-syn` |
| FIN | 0 | 0x01 | Fin d'émission | `tcp-fin` |

## 3. Options TCP

| Kind | Option | Longueur | Où | Note |
|---:|---|---:|---|---|
| 0 / 1 | EOL / NOP | 1 | partout | Alignement sur 4 octets |
| **2** | MSS | 4 | **SYN** | Défaut si absent : 536 (v4) / 1220 (v6) |
| **3** | Window Scale | 3 | **SYN** | Shift 0-14, les deux côtés sinon s = 0 |
| **4** | SACK-permitted | 2 | **SYN** | — |
| **5** | SACK | 10-34 | data | 4 blocs max, **3** avec Timestamps |
| **8** | Timestamps | 10 | partout | RTTM + PAWS |
| 34 | TCP Fast Open | 6-18 | SYN | Données dans le SYN, cookie |

## 4. MTU / MSS

| Contexte | MTU | MSS TCP |
|---|---:|---:|
| Ethernet standard | 1500 | **1460** (1448 avec Timestamps) |
| Ethernet + IPv6 | 1500 | **1440** |
| VXLAN (overlay K8s) | **1450** | 1410 |
| Geneve | 1450 | 1410 |
| IPsec (variable) | ~1400-1440 | ~1360-1400 |
| PPPoE | 1492 | 1452 |
| Jumbo frames | 9000 | 8960 |
| MTU minimale IPv6 | 1280 | 1220 |

Test de MTU : `ping -M do -s 1472 <ip>` (1472 + 8 ICMP + 20 IP = 1500). MSS clamping :
`iptables -t mangle -A FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu`.

## 5. États TCP et ce qu'ils accusent

| État | Signification | Coupable si ça s'accumule |
|---|---|---|
| `LISTEN` | Socket serveur prête | — |
| `SYN_SENT` | SYN envoyé, rien en retour | Pare-feu / route retour absente |
| `SYN_RECV` | SYN reçu, ACK attendu | SYN flood, perte du 3ᵉ segment |
| `ESTAB` | Établie | — |
| `FIN_WAIT_1` | FIN envoyé, non acquitté | Le pair ne répond plus |
| `FIN_WAIT_2` | FIN acquitté, on attend son FIN | **Le pair** n'appelle pas `close()` |
| `CLOSE_WAIT` | FIN reçu, `close()` local attendu | **Toi** — fuite de descripteurs |
| `CLOSING` | Fermeture simultanée | Rare, normal |
| `LAST_ACK` | Mon FIN envoyé | Transitoire |
| `TIME_WAIT` | 2×MSL (Linux **60 s**) | Client : épuisement de ports |

## 6. Sysctl — les valeurs par défaut à connaître

| Sysctl | Défaut | Effet |
|---|---|---|
| `net.ipv4.ip_local_port_range` | `32768 60999` | 28 232 ports éphémères |
| `net.core.somaxconn` | **4096** (128 avant 5.4) | Plafond de l'accept queue |
| `net.ipv4.tcp_max_syn_backlog` | 128-2048 selon RAM | Taille de la SYN queue |
| `net.ipv4.tcp_syncookies` | 1 | Anti SYN-flood |
| `net.ipv4.tcp_syn_retries` | **6** | ≈ 127 s avant échec de `connect()` |
| `net.ipv4.tcp_synack_retries` | 5 | Côté serveur |
| `net.ipv4.tcp_retries2` | **15** | 13-30 min avant abandon d'une connexion |
| `net.ipv4.tcp_fin_timeout` | **60** | Durée max en FIN_WAIT_2 |
| `net.ipv4.tcp_keepalive_time` | **7200** | 2 h d'inactivité avant la 1ʳᵉ sonde |
| `net.ipv4.tcp_keepalive_intvl` | **75** | Intervalle entre sondes |
| `net.ipv4.tcp_keepalive_probes` | **9** | Sondes avant abandon |
| `net.ipv4.tcp_window_scaling` | 1 | Option Window Scale |
| `net.ipv4.tcp_sack` / `tcp_timestamps` | 1 / 1 | SACK / horodatage + PAWS |
| `net.ipv4.tcp_congestion_control` | `cubic` | Algorithme actif |
| `net.ipv4.tcp_rmem` | `4096 131072 6291456` | min / défaut / max réception |
| `net.ipv4.tcp_wmem` | `4096 16384 4194304` | min / défaut / max émission |
| `net.core.rmem_max` / `wmem_max` | `212992` | Plafond d'un `SO_RCVBUF` manuel |
| `net.ipv4.tcp_moderate_rcvbuf` | 1 | Auto-tuning de la fenêtre |
| `net.ipv4.tcp_mtu_probing` | 0 | Mettre **1** contre les trous noirs PMTUD |
| `net.ipv4.tcp_tw_reuse` | 2 (loopback) | **1** = réutiliser les TIME_WAIT sortants |
| `net.ipv4.tcp_slow_start_after_idle` | 1 | Mettre **0** sur un serveur à connexions longues |
| `net.netfilter.nf_conntrack_max` | selon RAM | Sature en K8s / NAT → drops silencieux |

Réglage BDP 100 Mo : `sysctl -w net.core.rmem_max=134217728 net.core.wmem_max=134217728` puis
`tcp_rmem`/`tcp_wmem` avec 134217728 en 3ᵉ valeur. **Ne jamais** figer `SO_RCVBUF` dans le code sans mesure.

## 7. `ss` — la commande centrale

| Commande | Ce que ça donne |
|---|---|
| `ss -s` | Résumé : total, TCP estab, closed, orphaned, timewait |
| `ss -tan` | Toutes les sockets TCP, sans résolution |
| `ss -tlnp` | Ce qui **écoute** + processus (`Recv-Q`/`Send-Q` = accept queue / max) |
| `ss -tanp state established` | Connexions actives + PID/programme |
| `ss -tn state time-wait \| wc -l` | Compter les TIME_WAIT |
| `ss -tn state close-wait` | Fuite de FD applicative |
| `ss -tn state syn-sent` | Pare-feu / route retour |
| **`ss -ti`** | **Métriques internes** : cwnd, rtt, retrans, wscale… |
| `ss -tm` | Mémoire des buffers socket |
| `ss -ti dst 10.0.0.9` / `'( dport = :9092 )'` | Filtres |
| `ss -K dst 10.0.0.9` | **Tuer** des sockets (root) |

**Champs de `ss -ti`** : `cubic` (algo) · `wscale:s,r` (**0,0 ⇒ plafond 64 Kio**) · `rto:` ms · `rtt:moy/var` ms ·
`mss:` · `cwnd:` **en segments** · `ssthresh:` · `bytes_sent/bytes_acked/bytes_retrans` · `retrans:courant/cumulé` ·
`lost:` `sacked:` `reordering:` · `delivery_rate` · `pacing_rate` · `rcv_space` · `lastsnd/lastrcv/lastack` (ms).

## 8. Compteurs et captures

```bash
nstat -az | grep -Ei 'retrans|TCPLost|Timeout|Drop|ListenDrops'   # préféré
netstat -s | grep -iE 'retrans|listen|overflow'                   # équivalent verbeux
cat /proc/net/netstat /proc/net/snmp                              # source brute
watch -n1 'nstat -n; nstat | head -20'                            # deltas en direct
```

| Compteur | Ce qu'il révèle |
|---|---|
| `TcpRetransSegs / TcpOutSegs` | **Taux de retransmission** : < 0,1 % sain, > 1 % panne |
| `TcpExtListenOverflows` | **Accept queue pleine** → augmenter `somaxconn` / accepter plus vite |
| `TcpExtListenDrops` | SYN jetés |
| `TcpExtTCPTimeouts` | Pertes détectées trop tard (RTO) |
| `TcpExtTCPLostRetransmit` | Une retransmission elle-même perdue |
| `TcpExtTCPSynRetrans` | SYN retransmis → destination injoignable |
| `TcpExtPAWSEstab` | Horodatages incohérents (souvent NAT) |

```bash
tcpdump -ni any -w cap.pcap 'host 10.0.0.9 and port 9092'         # capture ciblée
tcpdump -ni any 'tcp[tcpflags] & (tcp-syn|tcp-fin|tcp-rst) != 0'  # contrôle uniquement
tcpdump -ni any 'tcp[tcpflags] & tcp-rst != 0'                    # qui envoie des RST
tcpdump -ni any -c 100 -vv 'icmp and icmp[0] == 3'                # ICMP unreachable (PMTUD)
tshark -r cap.pcap -q -z conv,tcp                                 # conversations
tshark -r cap.pcap -Y tcp.analysis.retransmission | wc -l         # compter les retransmissions
```

| Filtre Wireshark | Usage |
|---|---|
| `tcp.analysis.flags` | **Tout ce qui est anormal** — commencer ici |
| `tcp.analysis.retransmission` / `.fast_retransmission` | RTO / 3 dup-ACK |
| `tcp.analysis.spurious_retransmission` | Retransmission inutile (ou artefact de capture) |
| `tcp.analysis.duplicate_ack` | Perte ou réordonnancement |
| `tcp.analysis.zero_window` / `.window_full` | Récepteur saturé → appli lente |
| `tcp.analysis.out_of_order` | ECMP, pas forcément une perte |
| `tcp.analysis.ack_rtt > 0.2` | ACK lents |
| `tcp.flags.syn==1 && tcp.flags.ack==0` | Tous les débuts de connexion |
| `tcp.flags.reset==1` | Qui claque la porte |
| `tcp.stream eq N` | Isoler une connexion (→ *Follow TCP Stream*) |
| `tcp.len > 0 && tcp.window_size < 1000` | Fenêtre qui se referme |

Graphiques : *Statistics → TCP Stream Graphs →* **Time Sequence (tcptrace)** et **Throughput**. *Expert Information*
pour la synthèse.

## 9. Mesurer et régler

```bash
iperf3 -s                                     # serveur
iperf3 -c host -t 30 -P 8                     # 8 flux parallèles (contourne la perte)
iperf3 -c host -w 64M                         # forcer la taille de fenêtre
iperf3 -c host -u -b 500M                     # UDP à débit fixé (mesure la perte/jitter)
sysctl net.ipv4.tcp_available_congestion_control
sysctl -w net.ipv4.tcp_congestion_control=bbr
ss -ti | grep -c 'bbr'                        # vérifier l'algo réellement utilisé
ethtool -S eth0 | grep -iE 'drop|err|discard' # pertes au niveau carte
ip -s link show eth0                          # erreurs/drops interface
mtr -T -P 9092 --report-cycles 100 host       # perte par saut, en TCP
```

## 10. UDP / QUIC

| | UDP | QUIC |
|---|---|---|
| En-tête | **8 o** (ports, longueur, checksum) | Variable, **chiffré** |
| Protocole IP | **17** | 17 (UDP), port **443** |
| Charge utile max | **65 507 o** | Datagrammes ≤ PMTU (1200 o min exigé) |
| Checksum | Optionnel IPv4 (0), **obligatoire IPv6** | Intégrité par AEAD |
| Handshake | **0 RTT** (aucun) | **1 RTT**, 0-RTT en reprise |
| Fiabilité | Aucune | Complète, **par stream** |
| RFC | 768 | **9000** / 9001 / 9002, HTTP/3 **9114**, QPACK 9204 |

Usages UDP : DNS 53, DHCP 67/68, TFTP 69, NTP 123, SNMP 161/162, syslog 514, IPsec 500/4500, VXLAN 4789,
Geneve 6081, WireGuard 51820, RTP (dynamique), StatsD 8125.
Découverte HTTP/3 : en-tête `Alt-Svc: h3=":443"; ma=86400` ou enregistrement DNS **HTTPS/SVCB**.
Debug QUIC : `curl --http3 -v https://…` · Wireshark filtre `quic` (déchiffrement via `SSLKEYLOGFILE`).

## 11. Options socket utiles

| Option | Effet |
|---|---|
| `TCP_NODELAY` | Désactive **Nagle** — indispensable en RPC |
| `TCP_QUICKACK` | Désactive temporairement le delayed ACK |
| `TCP_CORK` | Retient jusqu'au segment plein ou 200 ms |
| `SO_KEEPALIVE` + `TCP_KEEPIDLE/INTVL/CNT` | Keepalive par socket (surcharge les sysctl) |
| `TCP_USER_TIMEOUT` | **Délai max avant échec**, indépendant de `retries2` |
| `SO_REUSEADDR` | Se lier à un port en TIME_WAIT |
| `SO_REUSEPORT` | Plusieurs sockets en LISTEN sur le même port (répartition par hash) |
| `SO_LINGER (0)` | `close()` envoie un **RST** au lieu d'un FIN |
| `SO_RCVBUF` / `SO_SNDBUF` | Fige la taille du buffer et **désactive l'auto-tuning** |

## 12. Diagnostic express — symptôme → cause

| Symptôme | Cause probable | Action |
|---|---|---|
| Débit ≈ **6,5 Mbit/s** à 80 ms | Window scaling absent | `ss -ti \| grep wscale` |
| Débit plafonné, `retrans` élevé | Perte + CUBIC (Mathis) | `-P 8`, ou BBR |
| `cwnd` très bas et stable | Perte réseau | `nstat`, `mtr -T` |
| `Send-Q` élevé | Réseau ou pair | Regarder `cwnd`, `rwnd` |
| `Recv-Q` élevé sur ESTAB | **Application lente** | Profiler le consommateur |
| `ZeroWindow` du pair | Appli distante saturée | Côté serveur |
| `EADDRNOTAVAIL` | Ports éphémères épuisés | Pooling, `ip_local_port_range` |
| `CLOSE_WAIT` en hausse | Fuite de FD chez toi | `lsof -p`, code |
| Connexion morte après pause | Timeout NAT (350 s) | `tcp_keepalive_time=300` |
| Latence stable 40 / 200 ms | Nagle × delayed ACK | `TCP_NODELAY` |
| Gros transferts gelés | Trou noir PMTUD | ICMP 3, `tcp_mtu_probing=1`, clamping |
| `SYN_SENT` persistant | Pare-feu / route retour | `tcpdump` **des deux côtés** |
| RST intermittents en K8s | `terminationGracePeriod`, conntrack plein | `nf_conntrack_count` |
