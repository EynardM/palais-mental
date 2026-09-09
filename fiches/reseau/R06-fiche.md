# R06 — FICHE : Couche 4 (TCP, UDP, QUIC)

> Lire **avant** le cours (pretesting), puis réciter de mémoire aux rappels. Cible : **3 minutes**.
> **TCP fait 5 choses qu'IP ne fait pas** : multiplexage (ports), fiabilité, ordre, contrôle de **flux**,
> contrôle de **congestion**. **UDP ne fait que le premier.** Et la formule qui explique tout :
> **`Débit = Fenêtre / RTT`**.

## Ports et identité d'une connexion
| | |
|---|---|
| Port | **16 bits**, 0-65535. 0-1023 well-known · 1024-49151 registered · 49152-65535 éphémère (IANA) |
| Éphémère **Linux** | `ip_local_port_range` = **32768 60999** → **28 232** ports |
| **Quadruplet** | IP src : port src → IP dst : port dst (+ protocole = **quintuplet**, hash ECMP/conntrack) |
| Protocole IP | **TCP 6** · **UDP 17** |

**22** SSH · **53** DNS (UDP **et** TCP) · **67/68** DHCP · **80/443** HTTP(S) · **443/UDP** QUIC · **123** NTP ·
**514** syslog · **4789** VXLAN · **3306** MySQL · **5432** PG · **6379** Redis · **9042** Cassandra ·
**9092** Kafka · **9200** Elastic · **2379** etcd · **6443** API K8s · **27017** Mongo.

## En-tête TCP — **20 o min, 60 o max** (40 o d'options)
```
| Port SRC (16) | Port DST (16) | SEQ (32) | ACK (32) | Offs(4) Rsvd(4) Flags(8) | FENÊTRE (16) |
| CHECKSUM (16, pseudo-en-tête inclus) | PTR URGENT (16) | OPTIONS 0-40 o | DONNÉES |
```
**Flags** : `CWR ECE URG ACK PSH RST SYN FIN` (0x80→0x01). **« Un Avion Perd Rapidement Son Fuel »** = UAPRSF.
**Options (SYN uniquement)** : **2** MSS · **3** Window Scale · **4** SACK-perm. Puis **5** SACK · **8** Timestamps.
**MSS** = 1500 − 20 IP − 20 TCP = **1460** (1448 avec Timestamps · 1440 en IPv6 · 1410 sous VXLAN). Défaut **536**.

## Ouverture, fermeture, TIME_WAIT
```
SYN(seq=x) → SYN+ACK(seq=y, ack=x+1) → ACK(ack=y+1)      = 1 RTT  (TLS1.3 +1 · TLS1.2 +2 · QUIC 1 ou 0)
FIN → ACK → [le pair peut encore émettre : half-close] → FIN → ACK    = 4 temps
```
**SYN et FIN consomment 1 numéro de séquence.** Un ACK seul, non. **seq = 1er octet ; ack = prochain attendu.**
**TIME_WAIT = 2×MSL, Linux 60 s en dur**, chez **celui qui ferme en premier**. Deux raisons : **ré-acquitter** si le
dernier ACK se perd · **laisser mourir** les vieux segments avant réutilisation du quadruplet.
Saturation client : **28 232 / 60 ≈ 470 conn/s** → `EADDRNOTAVAIL`. Remède : **pooling** > `ip_local_port_range` >
`tcp_tw_reuse=1`. **Jamais `tcp_tw_recycle`** (supprimé en 4.12).

## Les 11 états — qui est coupable
`CLOSED · LISTEN · SYN_SENT · SYN_RCVD · ESTABLISHED · FIN_WAIT_1 · FIN_WAIT_2 · CLOSING · CLOSE_WAIT ·
LAST_ACK · TIME_WAIT`
**`CLOSE_WAIT` chez moi = MON bug** (fuite de FD). **`FIN_WAIT_2` chez moi = le bug de l'AUTRE.**
`SYN_SENT` bloqué = pare-feu ou route retour absente. `ss -lnt` : **Recv-Q/Send-Q = accept queue courante/max** ;
sur ESTAB = **octets non lus / non acquittés**.
Files serveur : **SYN queue** (`tcp_max_syn_backlog`, → SYN cookies) puis **accept queue**
(`min(listen(), somaxconn)`, **somaxconn 4096** depuis 5.4).

## Fenêtres
**En vol ≤ min(rwnd, cwnd)** — **rwnd protège le PAIR, cwnd protège le RÉSEAU** (locale, dans aucun en-tête).
Champ Fenêtre 16 bits → **65 535 o** max. **Window Scale** : `s` de **0 à 14**, **SYN uniquement**, max
**65 535 × 2¹⁴ ≈ 1 Gio**. `window=0` → **Zero Window Probe** (persist timer). `ZeroWindow` = **appli lente**.

## Retransmission
`SRTT = 7/8·SRTT + 1/8·RTT` · `RTTVAR = 3/4·RTTVAR + 1/4·|SRTT−RTT|` · **`RTO = SRTT + 4·RTTVAR`**
RTO initial **1 s** · min Linux **200 ms** · max **120 s** · backoff ×2. **Karn** : pas de mesure sur un retransmis.
**3 ACK dupliqués → fast retransmit** (3 car ECMP produit 1-2 duplicatas) puis **fast recovery**.
**SACK** : blocs hors séquence, **4 max (3 avec Timestamps)**. **D-SACK** = doublon reçu.
`syn_retries` **6** ≈ 127 s · `retries2` **15** ≈ 13-30 min · `fin_timeout` **60 s**.
**Keepalive** : **7200 s / 75 s / 9 sondes** = 2 h 11 — **inutile** face à un NAT à **350 s** → descendre à **300**.

## Congestion
| Perte détectée par | ssthresh | cwnd | Suite |
|---|---|---|---|
| **Timeout (RTO)** | cwnd/2 | **1 MSS** | **Slow start** — amnésie totale |
| **3 dup-ACK** | cwnd/2 | ssthresh (+3) | **Fast recovery** — congestion avoidance |

**Slow start** : IW = **10 MSS** (RFC 6928), ×2 par RTT. **Congestion avoidance** : +1 MSS/RTT. **AIMD** = seule
famille simple qui **converge vers l'équité**. β = **0,5 Reno / 0,7 CUBIC**.
**CUBIC** (défaut Linux) : `W(t)=C(t−K)³+W_max`, croissance fonction du **temps**, pas du RTT.
**BBR** : pas la perte mais **BtlBw × RTprop = BDP**, pacing, anti-bufferbloat. Gagne sur **long + lossy**.

## BDP — la section qui rapporte
**`BDP = BP × RTT / 8`** · **`Débit = Fenêtre / RTT`**
10 Gbit/s × 80 ms = **100 Mo** en vol. Sans scaling : **65 535 / 0,08 = 6,5 Mbit/s** ← *signature à reconnaître*.
`s = 11` requis. **Mathis** : `Débit ≈ MSS/(RTT·√p)` → **p = 10⁻⁵ ⇒ 46 Mbit/s** à 80 ms. Remèdes : **N flux** ou
**BBR** — jamais « plus de bande passante ». Montée : **13 RTT ≈ 1 s** pour atteindre 100 Mo depuis 10 MSS.

## Petits paquets, MTU
**Nagle** (retient tant que du non-acquitté est en vol) × **delayed ACK** (40-200 ms Linux, 200 ms Windows) ⇒
**latence STABLE à 40/200 ms**. Une latence stable = **un timer**, pas le réseau. Fix : `TCP_NODELAY` / un seul `write()`.
**PMTUD black hole** : handshake OK, petites requêtes OK, **gros transferts gelés** = MTU réduite + **ICMP 3/4 filtré**.
Fix : autoriser **ICMP type 3**, `tcp_mtu_probing=1`, ou **MSS clamping**.

## UDP · QUIC
**UDP : 8 octets** (ports, longueur ≥ 8, checksum **optionnel IPv4 / obligatoire IPv6**), proto **17**, charge utile
max **65 507**. Ni seq, ni ACK, ni fenêtre, ni état. *Si une donnée périmée n'a plus de valeur, TCP te nuit.*
**QUIC** = transport complet **sur UDP 443** (RFC 9000), **TLS 1.3 intégré** → **1 RTT** (0-RTT en reprise, **rejouable**
⇒ idempotent seulement). **Connection ID** ⇒ migration Wi-Fi↔4G. **Streams ordonnés indépendamment** ⇒ plus de
**head-of-line blocking de transport** (HTTP/2 le subit). Découverte : `Alt-Svc: h3=":443"` ou DNS HTTPS/SVCB.

## Diagnostic
`ss -s` · `ss -tlnp` · `ss -tn state time-wait|close-wait` · **`ss -ti`** → `wscale` (**0,0 = plafond 64 Kio**),
`rtt`, `cwnd`, `retrans:cours/cumulé`, `delivery_rate`. **Débit plafond = `cwnd × mss / rtt`.**
`nstat -az | grep -i retrans` → **`TcpRetransSegs / TcpOutSegs`** : **< 0,1 %** sain, **> 1 %** panne réseau.
Wireshark : `tcp.analysis.flags` d'abord, puis `.retransmission`, `.duplicate_ack`, `.zero_window`, `.out_of_order`.

---

## Test express — 8 questions, réponses dans le cours
1. Qu'est-ce qui identifie une connexion TCP ? Combien de connexions un serveur peut-il tenir sur le port 443 ?
2. Taille min/max d'un en-tête TCP ? Cite les 8 flags dans l'ordre des bits.
3. Pourquoi 3 temps à l'ouverture et 4 à la fermeture ? Qui reste en TIME_WAIT, et pourquoi 2 raisons ?
4. `seq=4000, len=1460` : quel `ack` revient ? Que consomment SYN et FIN ?
5. Différence rwnd / cwnd ? Que valent cwnd et ssthresh après un RTO ? après 3 dup-ACK ?
6. BDP à 10 Gbit/s et 80 ms ? Débit sans window scaling ? Quel facteur `s` faut-il ?
7. Latence stable à 40 ms sur chaque requête : cause et correctif ? Et « handshake OK, gros transferts gelés » ?
8. Trois choses que QUIC change par rapport à TCP+TLS. Où le head-of-line blocking subsiste-t-il ?
