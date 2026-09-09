# R06 — Couche 4 : TCP en profondeur, UDP, QUIC

> **Ce que tu sauras faire à la fin**
> - Lire un en-tête TCP champ par champ, nommer les 8 flags dans l'ordre des bits, et dire ce que chacun déclenche.
> - Dérouler à la main l'ouverture en 3 temps, la fermeture en 4 temps et **les 11 états** de la machine TCP — et dire, devant un `ss` en production, ce que signifient 30 000 `TIME_WAIT` ou 400 `CLOSE_WAIT`.
> - Calculer un **BDP**, en déduire la fenêtre nécessaire et le facteur de *window scaling*, et expliquer chiffres à l'appui pourquoi un transfert inter-région plafonne à 6 Mbit/s sur un lien à 10 Gbit/s.
> - Expliquer slow start, congestion avoidance, fast retransmit/recovery, AIMD, et arbitrer entre **CUBIC et BBR** avec des arguments et pas des slogans.
> - Choisir TCP ou UDP pour un flux donné, et expliquer ce que QUIC change : 0-RTT, migration de connexion, multiplexage sans *head-of-line blocking*.
> - Diagnostiquer une connexion lente ou morte avec `ss -ti`, `nstat`, `tcpdump` et les filtres `tcp.analysis.*` — et distinguer une perte réseau d'un buffer applicatif plein.
>
> **Pourquoi ça compte dans ton poste**
> Un pipeline de données, vu du réseau, c'est un petit nombre de très grosses connexions TCP qui traversent des VPC, des
> NAT, des load balancers et des régions. Quand un job Spark met 6 heures au lieu de 40 minutes, la cause est presque
> toujours à la couche 4 : fenêtre trop petite pour le RTT, retransmissions, MTU cassée par un overlay, connexions coupées
> par un timeout de NAT. Les frameworks (Kafka, JDBC, gRPC, SDK S3) exposent tous des réglages qui sont en réalité des
> réglages TCP déguisés — et si tu fais de l'IA sur du trafic, les compteurs TCP **sont** tes features.
>
> **Prérequis** : `R01` (couches, encapsulation), `R02` (Ethernet, MTU), `R03` (IPv4/IPv6, ICMP), `R04` (routage, RTT).
> **Durée de lecture** : 80-90 min. Papier et crayon : les sections 12 et 18 se calculent, elles ne se lisent pas.

---

## 1. Le problème : le paquet est arrivé, et maintenant ?

Les couches 1 à 3 t'ont amené un paquet IP de A à B. Fin de l'histoire ? Non : IP laisse trois problèmes entiers.

**① À qui, dans la machine ?** B fait tourner 200 processus — un serveur web, un PostgreSQL, un broker Kafka. L'adresse IP
identifie la **machine**, pas le programme. Il faut un adressage **à l'intérieur** de l'hôte : le **port**.

**② Et si ça se perd ?** IP est *best effort* : un paquet peut être jeté par un routeur saturé, dupliqué, arriver dans le
désordre par ECMP. Sur un Parquet de 4 Go, un octet manquant le rend illisible. Il faut **détecter et réparer**.

**③ À quelle vitesse ?** L'émetteur a une carte 10 Gbit/s, le récepteur 200 Ko de buffer libre, le lien du milieu 1 Gbit/s.
Il faut **freiner** — deux fois : pour ne pas noyer le récepteur, et pour ne pas noyer le réseau.

```
      ┌──────────────────────────────────────────────────────────┐
      │  Couche 4 — TRANSPORT : ce que IP ne fait pas            │
      ├──────────────────────────────────────────────────────────┤
      │  ① Multiplexage     → quel processus ?      = PORTS      │
      │  ② Fiabilité        → rien ne se perd       = SEQ/ACK    │
      │  ③ Ordre            → rien ne se mélange    = SEQ        │
      │  ④ Contrôle de flux → ne pas noyer le PAIR  = rwnd       │
      │  ⑤ Contrôle de cong.→ ne pas noyer le RÉSEAU= cwnd       │
      └──────────────────────────────────────────────────────────┘
        TCP fait les 5.   UDP fait UNIQUEMENT le ①.
```

TCP fait les cinq et te le facture (état, latence d'établissement, complexité). UDP fait le premier et te laisse les quatre
autres — ce qui est parfois exactement ce que tu veux.

> ❓ **RETIENS ÇA** — Quelles fonctions TCP assure-t-il qu'UDP n'assure pas ?
> <details><summary>→ réponse</summary><br>Fiabilité (retransmission), remise <b>dans l'ordre</b>, contrôle de flux (fenêtre de réception), contrôle de congestion. UDP n'apporte que le <b>multiplexage par ports</b> et un checksum optionnel.</details>

> 🧠 **MÉMO** — **TCP = le recommandé avec accusé de réception. UDP = la carte postale.** Le recommandé est suivi, réémis,
> ordonné, et coûte cher en formalités ; la carte postale part immédiatement, sans preuve, et arrive presque toujours.

---

## 2. Ports, sockets, quadruplet

Un port est un entier sur **16 bits** : **0 à 65535**. C'est le numéro d'appartement dans l'immeuble dont l'IP est l'adresse
postale. **0-1023** = *well-known* (root ou `CAP_NET_BIND_SERVICE` pour s'y lier sous Linux) · **1024-49151** = *registered*
· **49152-65535** = plage éphémère IANA. Mais Linux utilise `net.ipv4.ip_local_port_range = 32768 60999`,
soit **28 232 ports** — retiens ce chiffre, il revient en §5.

Une **socket** est l'objet système (un descripteur de fichier sous Linux) représentant une extrémité. Ce qui identifie une
**connexion** de façon unique, c'est le **quadruplet** :

```
        ┌──────────────── QUADRUPLET (4-tuple) ────────────────┐
        │  IP source : port source  ──►  IP dest : port dest   │
        └──────────────────────────────────────────────────────┘
              10.0.1.7 : 43912   ──►   10.0.2.9 : 5432

   + le protocole (TCP=6 / UDP=17) → QUINTUPLET, ce que hachent les load
     balancers, l'ECMP et les tables conntrack.
```

Conséquence capitale : **des milliers de connexions partagent le même port serveur**. Un PostgreSQL écoute sur le seul port
5432 et sert 5 000 clients, chacun distingué par son couple (IP client, port client). Le **client**, lui, est limité : vers
une même destination, il n'a que ses ports éphémères, soit **28 232** sous Linux.

> ⚠️ **PIÈGE** — « Un serveur ne peut pas dépasser 65 535 connexions. » **Faux.** Cette limite porte sur les
> **ports sources d'un client vers une destination donnée**. Un serveur à un million de connexions sur le port 443
> est normal (le fameux *C10M*). Ce qui le limite : `ulimit -n`, la mémoire des buffers socket, et
> `nf_conntrack_max` s'il y a du NAT sur le chemin.

> ❓ **RETIENS ÇA** — Qu'est-ce qui identifie une connexion TCP de façon unique ?
> <details><summary>→ réponse</summary><br>Le <b>quadruplet</b> (IP source, port source, IP destination, port destination). Avec le protocole, cela fait le quintuplet, utilisé pour le hachage ECMP et le suivi de connexion.</details>

| Port | Service | | Port | Service |
|---:|---|---|---:|---|
| **22** | SSH | | **3306** | MySQL / MariaDB |
| **25 / 587** | SMTP / submission | | **5432** | **PostgreSQL** |
| **53** | **DNS** (UDP *et* TCP) · **853** DoT | | **5672** | AMQP (RabbitMQ) |
| **67 / 68** | DHCP serveur / client (UDP) | | **6379** | Redis |
| **80 / 443** | HTTP / HTTPS (+ **QUIC** en UDP 443) | | **8020 / 9000** | HDFS NameNode |
| **123** NTP · **514** syslog | UDP | | **9042 / 9092** | Cassandra / **Kafka** |
| **161 / 162** | SNMP / traps (UDP) | | **9200 / 9300** | Elasticsearch API / transport |
| **389 / 636** | LDAP / LDAPS | | **2379 / 2380** | etcd client / peer |
| **4789** | **VXLAN** (UDP) · **6081** Geneve | | **6443 / 10250** | API server K8s / kubelet |
| **51820** | WireGuard (UDP) | | **27017** | MongoDB |

> 🧠 **MÉMO** — Les trois de ton quotidien : **5432 Postgres, 9092 Kafka, 9200 Elastic** — ça monte 5 → 9 → 9. Et les
> deux ports où tu verras du **TCP *et* de l'UDP en usage courant : 53 (DNS)** — UDP pour les requêtes courtes,
> TCP dès que la réponse dépasse la taille annoncée ou pour un transfert de zone — et **443** (HTTPS en TCP,
> **QUIC en UDP**).

---

## 3. L'en-tête TCP, champ par champ

**20 octets minimum**, jusqu'à **60 octets** avec les options. À redessiner à la main jusqu'à ce que ça vienne tout seul —
grand classique du tableau blanc.

```
 |◄──────── 32 bits ────────────────────────────────────────────►|
 +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
 |          Port SOURCE          |       Port DESTINATION        |  4 o
 +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
 |                    NUMÉRO DE SÉQUENCE (32 bits)               |  8 o
 +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
 |                 NUMÉRO D'ACQUITTEMENT (32 bits)               | 12 o
 +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
 | Offs. | Rsvd  |C|E|U|A|P|R|S|F|        FENÊTRE (16 bits)      | 16 o
 | (4b)  | (4b)  |W|C|R|C|S|S|Y|I|                               |
 |       |       |R|E|G|K|H|T|N|N|                               |
 +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
 |          CHECKSUM             |    POINTEUR URGENT            | 20 o
 +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
 |         OPTIONS (0 à 40 octets, multiple de 4)  |  bourrage   |
 +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
 |                          DONNÉES                              |
```

| Champ | Taille | Ce qu'il fait, concrètement |
|---|---|---|
| Ports source / dest | 16 b + 16 b | Qui parle, à qui — dans chaque machine |
| **Numéro de séquence** | 32 b | Position du **premier octet de charge utile** dans le flux. Un n° d'**octet**, pas de paquet |
| **Numéro d'acquittement** | 32 b | Le prochain octet **attendu**. Valide seulement si `ACK` est levé |
| Data Offset | 4 b | En-tête en **mots de 32 bits**. 5 = 20 o (sans options), max 15 = **60 o** |
| Réservé | 4 b | À zéro (un de ces bits est réutilisé par l'ECN moderne) |
| **Flags** | 8 b | CWR, ECE, URG, ACK, PSH, RST, SYN, FIN |
| **Fenêtre** | 16 b | Place libre en réception → **max 65 535** octets sans l'option scaling |
| Checksum | 16 b | Couvre le **pseudo-en-tête IP** (IP src/dst, protocole 6, longueur TCP) + en-tête + données. **Obligatoire** — et c'est pourquoi un NAT **doit** le recalculer |
| Pointeur urgent | 16 b | Offset de données « urgentes ». Obsolète (RFC 6093 : ne pas utiliser) |

```
   bit :   7     6     5     4     3     2     1     0
        ┌─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┐
        │ CWR │ ECE │ URG │ ACK │ PSH │ RST │ SYN │ FIN │
        └─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┘
  hexa :  0x80  0x40  0x20  0x10  0x08  0x04  0x02  0x01
```

| Flag | Ce qu'il veut dire | Quand tu le vois |
|---|---|---|
| **SYN** | « J'ouvre, voici mon numéro de séquence initial » | Uniquement aux 2 premiers segments |
| **ACK** | « Le champ acquittement est valide » | Sur **tout** sauf le tout premier SYN |
| **FIN** | « Je n'ai plus rien à envoyer » (je peux encore recevoir) | Fermeture propre |
| **RST** | « Cette connexion n'existe pas / j'abandonne » — pas d'accusé | Port fermé, crash, `SO_LINGER 0`, pare-feu |
| **PSH** | « Ne bufferise pas, remonte à l'application tout de suite » | Fin d'un message applicatif |
| **URG** | Le pointeur urgent est valide | Quasi jamais. Considère-le comme mort |
| **ECE / CWR** | « J'ai vu une marque de congestion » / « j'ai réduit » | Si ECN est actif |

> 🧠 **MÉMO** — Les 6 flags historiques, dans l'ordre : **U-A-P-R-S-F** → « **U**n **A**vion **P**erd **R**apidement
> **S**on **F**uel ». Les deux bits ECN (**CWR, ECE**) se rajoutent **devant**. Et le tandem qui compte :
> **SYN ouvre, FIN ferme poliment, RST claque la porte.**

> ⚠️ **PIÈGE** — Confondre **FIN** et **RST**. FIN = « j'ai fini d'émettre » : l'autre sens reste ouvert, les
> données en transit sont livrées, il y a un acquittement. RST = « oublie cette connexion » : immédiat, buffers
> **jetés**, et **on n'acquitte jamais un RST**. RST à la place d'un SYN-ACK = port fermé ou pare-feu en *reject* ;
> RST au milieu d'un transfert = crash applicatif, timeout de NAT, ou middlebox qui coupe.

> ❓ **RETIENS ÇA** — Taille minimale et maximale d'un en-tête TCP ?
> <details><summary>→ réponse</summary><br><b>20 octets</b> minimum, <b>60 octets</b> maximum (Data Offset max = 15 mots de 4 octets), soit au plus <b>40 octets d'options</b>.</details>

**Les options** (kind / taille) : **2 MSS** (4 o) et **3 Window Scale** (3 o) et **4 SACK-permitted** (2 o), les trois
**négociés dans le SYN uniquement** · **5 SACK** (10-34 o, blocs reçus hors séquence) · **8 Timestamps** (10 o, mesure du
RTT + protection PAWS) · **34 TCP Fast Open** · 0 EOL et 1 NOP pour l'alignement sur 4 octets. Un SYN Linux typique porte
MSS + SACK-perm + Timestamps + NOP + WS = **20 octets d'options**, soit un en-tête de 40 o.

> ⚠️ **PIÈGE** — MSS, Window Scale et SACK-permitted **ne se négocient que dans le SYN / SYN-ACK**. Si un pare-feu
> ou un vieux load balancer strippe ces options, tu perds le *window scaling* pour **toute la vie de la
> connexion** : fenêtre plafonnée à 64 Kio, débit effondré sur les longues distances, sans le moindre message
> d'erreur. Le grand classique du « ça marche mais c'est lent ».

**MSS ≠ MTU.** Le MSS est la taille maximale de la **charge utile TCP** :

```
   MTU 1500  =  20 (IP)  +  20 (TCP)  +  1460 (données)   →  MSS = 1460
   avec l'option Timestamps dans chaque segment : 1500 - 20 - 32 = 1448 utiles
   IPv6 : 1500 - 40 (IP6) - 20 (TCP) = 1440 · défaut si non annoncé : 536 / 1220
   VXLAN (overlay K8s) : 50 octets d'encapsulation → MTU 1450 → MSS 1410
```

---

## 4. L'ouverture : le handshake en 3 temps

**Le problème** : deux machines doivent s'accorder sur des numéros de séquence initiaux, et chacune doit être sûre que
l'autre est là *et* qu'elle l'entend. Un échange en deux temps ne suffit pas : après le message 2, le serveur ne sait pas si
le client l'a reçu.

```
  CLIENT                                                       SERVEUR
  (CLOSED)                                                     (LISTEN)
     │──── ① SYN,  seq=x (ISN client), MSS, WS, SACK-perm ────────►│
     │        SYN_SENT                                     SYN_RCVD│
     │◄─── ② SYN+ACK,  seq=y (ISN serveur),  ack=x+1 ──────────────│
     │──── ③ ACK,  seq=x+1,  ack=y+1  [+ données possibles] ──────►│
  ESTABLISHED                                              ESTABLISHED
     │◄══════════════ échange de données ═════════════════════════►│

  Coût : 1 RTT complet AVANT le premier octet utile.
  (le 3ᵉ segment part avec les données : il ne coûte pas de RTT de plus)
```

**Trois temps, pas deux, pas quatre.** Le segment ② est une fusion : SYN du serveur + ACK du client. À la fermeture cette
fusion n'est généralement pas possible, d'où 4 segments.

**L'ISN n'est ni 0 ni purement aléatoire.** RFC 6528 : fonction cryptographique du quadruplet et d'une clé secrète, plus une
horloge qui avance de 1 toutes les ~4 µs. Objectif : empêcher un attaquant de deviner un numéro de séquence pour injecter
des données, et empêcher qu'un vieux segment d'une connexion précédente soit accepté dans la nouvelle.

> ❓ **RETIENS ÇA** — Combien de RTT coûte l'établissement d'une connexion TCP avant le premier octet de données ?
> <details><summary>→ réponse</summary><br><b>1 RTT.</b> Avec TLS 1.3 par-dessus : 2 RTT. Avec TLS 1.2 : 3 RTT. QUIC ramène le tout à <b>1 RTT</b> (transport + crypto ensemble), et <b>0 RTT</b> en reprise de session.</details>

### 4.1 Les deux files d'attente du serveur

```
   SYN entrant
       ▼
  ┌──────────────────────┐  SYN-ACK envoyé, on attend l'ACK
  │  FILE SYN            │  taille : net.ipv4.tcp_max_syn_backlog
  │ (semi-ouvertes)      │  pleine → SYN cookies (tcp_syncookies=1 par défaut)
  └──────────┬───────────┘
             │  ACK reçu → la connexion est ÉTABLIE
             ▼
  ┌──────────────────────┐  taille : min(backlog de listen(), net.core.somaxconn)
  │  FILE D'ACCEPT       │  somaxconn = 4096 depuis Linux 5.4 (128 avant)
  │ (en attente d'accept)│  pleine → l'ACK final est JETÉ, le SYN-ACK sera retransmis
  │                      │  (ou RST immédiat si tcp_abort_on_overflow=1) ; cf. TcpExtListenOverflows
  └──────────┬───────────┘
             ▼  accept() par l'application

  State   Recv-Q  Send-Q  Local Address:Port
  LISTEN  0       4096    0.0.0.0:9092
          ▲       └── taille MAX de la file d'accept
          └────────── connexions ACTUELLEMENT en attente d'accept()
```

Si `Recv-Q` se colle à `Send-Q` sur un LISTEN, ton application n'appelle pas `accept()` assez vite : problème applicatif
(pool de threads saturé), pas réseau.

> ⚠️ **PIÈGE** — Sur une socket **LISTEN**, `Recv-Q`/`Send-Q` = « accept queue courante / max ». Sur une socket
> **ESTAB**, tout autre chose : `Recv-Q` = octets reçus **non lus par l'application**, `Send-Q` = octets envoyés
> **non acquittés** par le pair. Même colonne, deux sens. C'est LA question piège sur `ss`.

> ❓ **RETIENS ÇA** — Sur une connexion ESTABLISHED, un `Send-Q` élevé et stable, ça veut dire quoi ?
> <details><summary>→ réponse</summary><br>Des données sont parties mais ne sont <b>pas acquittées</b> : le réseau ou le pair est le goulot (perte, fenêtre du pair fermée, RTT énorme). Un <b>Recv-Q</b> élevé, à l'inverse, désigne une <b>application trop lente à lire</b>.</details>

---

## 5. La fermeture en 4 temps, et le mystère TIME_WAIT

**Le problème** : TCP est bidirectionnel. Que A n'ait plus rien à dire n'implique pas que B ait fini. On ferme donc **chaque
sens séparément** — d'où quatre segments et non trois.

```
  CLIENT (fermeture active)                       SERVEUR (fermeture passive)
  ESTABLISHED                                     ESTABLISHED
     │────── ① FIN, seq=u ─────────────────────────────►│
  FIN_WAIT_1                                      CLOSE_WAIT
     │◄───── ② ACK, ack=u+1 ────────────────────────────│
  FIN_WAIT_2   ← le serveur PEUT ENCORE ENVOYER →       │  (half-close)
     │◄───── ③ FIN, seq=v ──────────────────────────────│
  TIME_WAIT                                       LAST_ACK
     │────── ④ ACK, ack=v+1 ───────────────────────────►│
     │                                              CLOSED
     │  ⏳ attente 2×MSL (Linux : 60 s fixes)
   CLOSED
```

② et ③ **peuvent** fusionner si le serveur ferme immédiatement — on voit alors 3 segments. Ce n'est pas la règle : entre les
deux, le serveur peut émettre pendant des minutes. C'est le **half-close**, ce que fait `shutdown(fd, SHUT_WR)`.

Celui qui ferme **en premier** reste en **TIME_WAIT** pendant **2 × MSL** (Maximum Segment Lifetime). MSL vaut 2 minutes
dans la RFC 793, donc 4 minutes en théorie ; **Linux code 60 secondes en dur** (`TCP_TIMEWAIT_LEN`), et ce n'est **pas**
réglable par sysctl contrairement à ce qu'on lit partout. Deux raisons, toutes deux nécessaires : ① **le dernier ACK peut se
perdre** — le serveur retransmettrait son FIN, un client déjà CLOSED répondrait par un **RST** et le serveur croirait à une
rupture anormale ; ② **tuer les fantômes** — un segment retardé de l'ancienne connexion pourrait ressurgir après réouverture
**sur le même quadruplet** et être accepté comme donnée valide.

> 🧠 **MÉMO** — TIME_WAIT = **« j'attends au portail que le facteur ait fini sa tournée »**. Deux motifs :
> **ré-acquitter** si le dernier accusé s'est perdu, et **laisser mourir** les lettres en retard avant de rouvrir
> la même boîte.

> ⚠️ **PIÈGE** — Voir 30 000 `TIME_WAIT` et paniquer. C'est **normal et sain** sur une machine qui ferme beaucoup
> de connexions sortantes. Le seul cas problématique : un **client** qui ouvre beaucoup de connexions courtes vers
> **une seule destination** et épuise ses ports éphémères. Côté **serveur**, un TIME_WAIT coûte quelques centaines
> d'octets et ne bloque aucun port — le port serveur est fixe.

**Exercice corrigé — combien de connexions/s avant épuisement ?** *Un worker ouvre une connexion HTTP courte vers
`10.0.2.9:8080` par message, et ferme le premier. À quel débit sature-t-il ?* ① Fermeur actif = le client → un TIME_WAIT
**côté client** par connexion, pendant **60 s**. ② Ports disponibles : 60999 − 32768 + 1 = **28 232**. ③ En régime
permanent, ports occupés = débit × 60 → saturation à 28 232 / 60 ≈ **470 connexions/s**, au-delà de quoi `connect()` échoue
en `EADDRNOTAVAIL`.

**Corrections, par ordre de qualité** : ① réutiliser les connexions (keep-alive, pool) — la vraie solution ; ② élargir
`ip_local_port_range` à `1024 65535` (× 2,3) ; ③ `net.ipv4.tcp_tw_reuse=1`, qui autorise la réutilisation d'un TIME_WAIT
sortant si les timestamps sont actifs. **Jamais `tcp_tw_recycle`** : il cassait tout client derrière NAT, **supprimé du
noyau en 4.12**.

> ❓ **RETIENS ÇA** — Qui reste en TIME_WAIT, celui qui ferme ou celui qui subit la fermeture ?
> <details><summary>→ réponse</summary><br><b>Celui qui ferme en premier</b> (fermeture active). Celui qui subit passe par CLOSE_WAIT puis LAST_ACK et se libère immédiatement après le dernier ACK.</details>

> ⚠️ **PIÈGE** — Des `CLOSE_WAIT` qui **ne diminuent pas** ne sont jamais un problème réseau. Le pair a envoyé FIN,
> le noyau a répondu ACK, et il attend que **ton application appelle `close()`**. C'est une **fuite de descripteurs
> de fichiers** : `try` sans `finally`, session HTTP non fermée, curseur de base oublié.

---

## 6. La machine à états TCP complète

**11 états.** Redessine-la jusqu'à pouvoir la refaire de mémoire ; `palais/R06-palais.md` en ancre l'ordre.

```
                            ┌──────────┐
              ┌────────────►│  CLOSED  │◄──────────────┐
              │             └────┬─────┘               │
              │        listen()  │  │  connect() → SYN │
              │        ┌─────────┘  └────────┐         │
              │        ▼                     ▼         │
              │  ┌──────────┐          ┌───────────┐   │
              │  │  LISTEN  │          │ SYN_SENT  │   │
              │  └────┬─────┘          └─────┬─────┘   │
              │       │ reçoit SYN           │ reçoit SYN+ACK
              │       │ → envoie SYN+ACK     │ → envoie ACK
              │       ▼                      │         │
              │  ┌──────────┐  reçoit SYN    │         │
              │  │ SYN_RCVD │◄───────────────┤ (ouverture simultanée)
              │  └────┬─────┘                │         │
              │       │ reçoit ACK           │         │
              │       └──────────┬───────────┘         │
              │                  ▼                     │
              │           ┌─────────────┐              │
              │           │ ESTABLISHED │              │
              │           └──┬───────┬──┘              │
              │   close()    │       │  reçoit FIN     │
              │   → FIN      │       │  → envoie ACK   │
              │              ▼       ▼                 │
              │     ┌────────────┐  ┌────────────┐     │
              │     │ FIN_WAIT_1 │  │ CLOSE_WAIT │     │
              │     └──┬──────┬──┘  └──────┬─────┘     │
              │  ACK   │      │ FIN → ACK  │ close() → FIN
              │        ▼      ▼            ▼           │
              │ ┌────────────┐ ┌─────────┐ ┌─────────┐ │
              │ │ FIN_WAIT_2 │ │ CLOSING │ │LAST_ACK │─┘
              │ └──────┬─────┘ └────┬────┘ └─────────┘
              │  FIN   │       ACK  │        reçoit ACK
              │  → ACK │            │
              │        ▼            ▼
              │   ┌──────────────────────┐
              └───┤      TIME_WAIT       │  attente 2×MSL (Linux 60 s)
                  └──────────────────────┘
```

| État | Ce qu'il révèle en production |
|---|---|
| `SYN_SENT` | SYN envoyé, rien en retour → **pare-feu qui drop, ou route de retour manquante** (cf. R04) |
| `SYN_RECV` | Beaucoup = SYN flood, ou perte du 3ᵉ segment |
| `FIN_WAIT_1` | FIN envoyé, pas d'ACK : le pair ne répond plus |
| `FIN_WAIT_2` | Bloqué = **le pair n'appelle pas `close()`**. Timeout `tcp_fin_timeout` = 60 s |
| `CLOSE_WAIT` | FIN reçu, `close()` local attendu → **bug applicatif chez TOI** : fuite de FD |
| `CLOSING` / `LAST_ACK` | Fermeture simultanée (rare, normal) / mon FIN envoyé, j'attends l'ACK (transitoire) |
| `TIME_WAIT` | 2×MSL. Normal, sauf épuisement de ports côté client |

> 🧠 **MÉMO** — La règle qui désigne le coupable :
> **`CLOSE_WAIT` chez moi = MON bug. `FIN_WAIT_2` chez moi = le bug de l'AUTRE.**
> Dans les deux cas quelqu'un n'a pas appelé `close()` ; il suffit de savoir qui.

---

## 7. Numéros de séquence et d'acquittement

Le point qui bloque tout le monde, et qui se règle en une phrase : **TCP ne numérote pas les paquets, TCP numérote les
OCTETS.** Le numéro de séquence d'un segment = position, dans le flux, de son **premier octet de charge utile**. Le numéro
d'acquittement = le **prochain octet attendu**, donc « j'ai tout reçu jusqu'à ack−1 inclus ». Deux règles à ne jamais
oublier : **SYN consomme 1 numéro de séquence** et **FIN aussi**, bien qu'ils ne portent aucune donnée ; un ACK seul n'en
consomme **aucun**.

**Exercice intégralement corrigé.** Client ISN = 1000, serveur ISN = 5000. Le client envoie 500 octets, le serveur répond
1200 octets, puis le client ferme.

| # | Sens | Flags | seq | ack | len | Raisonnement |
|---:|---|---|---:|---:|---:|---|
| 1 | C→S | SYN | 1000 | — | 0 | ISN du client |
| 2 | S→C | SYN,ACK | 5000 | **1001** | 0 | ack = 1000 + 1 (le SYN compte pour 1) |
| 3 | C→S | ACK | 1001 | **5001** | 0 | ack = 5000 + 1 |
| 4 | C→S | PSH,ACK | **1001** | 5001 | 500 | l'ACK seul (#3) n'a rien consommé |
| 5 | S→C | ACK | 5001 | **1501** | 0 | 1001 + 500 |
| 6 | S→C | PSH,ACK | **5001** | 1501 | 1200 | le serveur émet enfin |
| 7 | C→S | ACK | 1501 | **6201** | 0 | 5001 + 1200 |
| 8 | C→S | FIN,ACK | **1501** | 6201 | 0 | le FIN part au numéro courant |
| 9 | S→C | ACK | 6201 | **1502** | 0 | 1501 + 1 (le FIN compte pour 1) |
| 10 | S→C | FIN,ACK | 6201 | 1502 | 0 | le serveur ferme à son tour |
| 11 | C→S | ACK | 1502 | **6202** | 0 | 6201 + 1 → puis TIME_WAIT côté client |

Sache refaire la colonne `ack` sans regarder : c'est demandé en entretien, et ça se rate sur la règle SYN/FIN.

> ❓ **RETIENS ÇA** — Un segment porte `seq=4000, len=1460`. Quel `ack` le récepteur renvoie-t-il ?
> <details><summary>→ réponse</summary><br><b>ack = 5460</b> (4000 + 1460) : « j'ai tout reçu jusqu'à 5459, envoie-moi la suite à partir de 5460 ».</details>

> ⚠️ **PIÈGE** — Les numéros affichés par Wireshark sont par défaut **relatifs** (le premier vaut 0) ; les vrais
> sont énormes et pseudo-aléatoires. On repasse en absolu via *Preferences → Protocols → TCP → décocher « Relative
> sequence numbers »*. Le champ étant sur 32 bits, le compteur **reboucle** après 4 Gio — à 10 Gbit/s, en
> **3,4 secondes**. D'où l'option **Timestamps** et le mécanisme **PAWS**, qui rejette un segment dont l'horodatage
> est plus ancien que le dernier accepté.

---

## 8. Fenêtre glissante et contrôle de flux

**Le problème** : envoyer un segment, attendre son ACK, envoyer le suivant — ça marche, et c'est catastrophique. À 80 ms de
RTT avec un MSS de 1460 octets : 1460 / 0,08 = **18 250 octets/s ≈ 146 kbit/s**, quelle que soit la bande passante. Il faut
envoyer **plusieurs segments avant d'être acquitté**. C'est la **fenêtre glissante** : le volume d'octets qu'on s'autorise à
avoir « en vol », non acquittés.

```
   ...acquittés  │ envoyés non acquittés │ autorisés  │ interdits...
  ───────────────┼───────────────────────┼────────────┼──────────────►
              SND.UNA                 SND.NXT   SND.UNA + fenêtre
                 └───────── FENÊTRE ─────────────────┘  (glisse à chaque ACK)

  Fenêtre effective = min( rwnd  ,  cwnd )
                          ▲         └── CONGESTION : ce que le RÉSEAU supporte (§10)
                          └──────────── FLUX : ce que le RÉCEPTEUR peut stocker
```

> 🧠 **MÉMO** — **rwnd protège le PAIR, cwnd protège le RÉSEAU.** Le pair l'annonce dans chaque segment ; le réseau
> ne dit rien, alors l'émetteur le **devine** en observant les pertes. Question d'entretien quasi certaine.

Le champ Fenêtre fait 16 bits → **65 535 octets** maximum. Suffisant en 1981, ridicule aujourd'hui. D'où l'option **Window
Scale** (RFC 7323) : un facteur de décalage `s` entre **0 et 14**, échangé **uniquement dans le SYN**, qui multiplie la
fenêtre annoncée par `2^s`. Les **deux** côtés doivent l'envoyer, sinon `s = 0` partout.

```
   Fenêtre réelle = champ (16 bits) × 2^s
   Maximum absolu = 65 535 × 2^14 = 1 073 725 440 octets ≈ 1 Gio
```

Si l'application ne lit plus, le buffer se remplit et le récepteur annonce **window = 0**. L'émetteur s'arrête et arme le
**persist timer** : il envoie périodiquement une **Zero Window Probe** de 1 octet — car l'ACK annonçant la réouverture
pourrait se perdre, et sans sonde la connexion resterait figée pour toujours. Le **silly window syndrome** est le cas
dégénéré (le récepteur libère 1 octet et l'annonce) ; parade de Clark : n'annoncer une réouverture qu'à partir d'un MSS ou
de la moitié du buffer.

> ❓ **RETIENS ÇA** — Wireshark montre un `TCP ZeroWindow` envoyé par le serveur. Qui est le coupable ?
> <details><summary>→ réponse</summary><br><b>L'application du serveur</b> : elle ne lit pas assez vite dans sa socket. Le réseau est hors de cause — consommateur lent (thread bloqué, GC, disque saturé).</details>

| Sysctl | Défaut typique | Rôle |
|---|---|---|
| `net.ipv4.tcp_rmem` | `4096 131072 6291456` | min / défaut / **max** du buffer de réception |
| `net.ipv4.tcp_wmem` | `4096 16384 4194304` | min / défaut / **max** du buffer d'émission |
| `net.core.rmem_max` | `212992` | Plafond d'un `SO_RCVBUF` **fixé à la main** |
| `net.ipv4.tcp_moderate_rcvbuf` | `1` | Auto-tuning de la fenêtre de réception |

> ⚠️ **PIÈGE** — Fixer `SO_RCVBUF` dans le code **désactive l'auto-tuning** et plafonne à `rmem_max`. Résultat
> fréquent : une application « optimisée » par un `setsockopt` codé en dur est **plus lente** que si on l'avait
> laissée tranquille. N'y touche que si tu as mesuré le BDP.

---

## 9. Retransmission : détecter et réparer une perte

### 9.1 Le RTO — la voie lente

Le **Retransmission TimeOut** dérive du RTT mesuré, algorithme de Jacobson/Karels :

```
   SRTT   = 7/8 × SRTT   + 1/8 × RTT_mesuré         (moyenne lissée)
   RTTVAR = 3/4 × RTTVAR + 1/4 × |SRTT - RTT|       (variabilité)
   RTO    = SRTT + 4 × RTTVAR
   RTO initial : 1 s (RFC 6298) · minimum Linux : 200 ms · maximum : 120 s
   Backoff exponentiel à chaque échec : 1, 2, 4, 8, 16, 32, 64 s...
```

**Algorithme de Karn** : on ne mesure **jamais** le RTT sur un segment retransmis — impossible de savoir si l'ACK répond à
l'original ou à la copie. L'option Timestamps lève l'ambiguïté et permet de mesurer partout.

| Sysctl | Défaut | Effet |
|---|---:|---|
| `net.ipv4.tcp_syn_retries` | 6 | 1+2+4+8+16+32+64 ≈ **127 s** avant abandon d'un `connect()` |
| `net.ipv4.tcp_synack_retries` | 5 | Idem côté serveur |
| `net.ipv4.tcp_retries2` | 15 | Abandon d'une connexion établie : **13 à 30 min** |
| `net.ipv4.tcp_fin_timeout` | 60 | Durée max en FIN_WAIT_2 |

> ⚠️ **PIÈGE** — « Mon job a mis 15 minutes à échouer alors que le serveur était mort. » C'est `tcp_retries2 = 15` :
> TCP n'abandonne pas vite, **par conception**. Si ton pipeline doit échouer vite, ce n'est pas au noyau de le
> décider — timeout applicatif, ou `TCP_USER_TIMEOUT` sur la socket.

### 9.2 Fast retransmit et SACK — la voie rapide

Attendre le RTO (200 ms minimum) pour une perte isolée est ruineux. TCP triche : à la réception d'un segment hors séquence,
le récepteur **ré-acquitte le dernier octet contigu**. L'émetteur voit donc des ACK dupliqués.

```
   Émis :   [1000] [2460] [3920] [5380] [6840]
                      ✗ perdu
   ACK  :   ack=2460   ack=2460   ack=2460   ack=2460
            (normal)   (dup 1)    (dup 2)    (dup 3) ──► FAST RETRANSMIT
                                                         on renvoie 2460 sans attendre
```

**3 ACK dupliqués → retransmission immédiate**, puis **fast recovery** (§10). Pourquoi 3 ? Parce qu'un simple
**réordonnancement** (ECMP) produit 1 ou 2 duplicatas : trois est le compromis réactivité / fausses alertes.

Avec l'acquittement cumulatif seul, un récepteur ayant reçu 1, 3, 4, 5 ne peut dire que « j'attends 2 » : l'émetteur ignore
le sort de 3, 4, 5 et risque de tout retransmettre. **SACK** (RFC 2018) ajoute la liste des **blocs reçus hors séquence** —
`ack=2000  SACK: 3460-5000, 6500-7000` signifie « il me manque à partir de 2000, mais j'ai déjà ces deux blocs ». Négocié
par `SACK-permitted` **dans le SYN** (`tcp_sack = 1` par défaut), **4 blocs** max (8 octets chacun), ramenés à **3** avec
les Timestamps — les 40 octets d'options ne suffisent plus. **D-SACK** (RFC 2883) signale à l'inverse un segment reçu **en
double** : l'émetteur apprend qu'il a retransmis pour rien.

> ❓ **RETIENS ÇA** — Combien d'ACK dupliqués déclenchent un fast retransmit, et pourquoi ce nombre ?
> <details><summary>→ réponse</summary><br><b>3</b>. En dessous, le signal se confondrait avec un simple <b>réordonnancement</b> de paquets, fréquent avec l'ECMP.</details>

### 9.3 Keepalive

Une connexion inactive n'échange **rien**. Si le pair disparaît (crash, VM détruite), personne ne le sait : la socket reste
`ESTAB` des deux côtés indéfiniment. C'est la **connexion fantôme**. `SO_KEEPALIVE` envoie des sondes vides :
`tcp_keepalive_time` **7200 s (2 h)** d'inactivité avant la première, `tcp_keepalive_intvl` **75 s** entre sondes,
`tcp_keepalive_probes` **9** avant abandon — soit **2 h 11 min**, et **seulement si l'application a activé `SO_KEEPALIVE`**,
ce qui n'est pas le défaut.

> ⚠️ **PIÈGE — celui que tu rencontreras vraiment.** Une **NAT Gateway ou un NLB AWS coupent les connexions
> inactives au bout de 350 s**, un pare-feu d'entreprise souvent entre 5 et 30 min. Ta connexion JDBC ou ton
> consumer Kafka dort 10 minutes, la table de NAT a oublié l'entrée, et le paquet suivant reçoit un **RST** — ou
> pire, disparaît en silence et tu attends 15 minutes de `tcp_retries2`. **Le keepalive par défaut à 2 h ne te sauve
> jamais** : descends `tcp_keepalive_time` sous le timeout de l'infra, typiquement **300 s**, ou configure le
> keepalive dans le pool applicatif.

---

## 10. Contrôle de congestion : le cœur du sujet

Octobre 1986 : le lien Berkeley–LBL, 400 mètres, passe de 32 kbit/s à **40 bit/s**. Cause : tous les émetteurs
retransmettaient dès qu'un paquet se perdait, ce qui aggravait la saturation, donc les pertes — c'est **l'effondrement de
congestion**. Van Jacobson y répond en 1988 avec les algorithmes qu'on utilise encore. L'idée fondamentale : **le réseau ne
dit pas qu'il est saturé, l'émetteur doit le deviner** — via la **perte**, et plus récemment le délai ou l'ECN. D'où une
deuxième fenêtre, la **fenêtre de congestion `cwnd`**, purement locale : elle n'apparaît dans **aucun en-tête**.
Et `en vol ≤ min(rwnd, cwnd)`.

### 10.1 Slow start

Au démarrage, l'émetteur ne sait rien du chemin : il commence petit et **double à chaque RTT**.

```
   cwnd initial (IW) = 10 MSS  (RFC 6928 ; 14,6 Ko avec MSS 1460)
   Chaque ACK reçu → cwnd += 1 MSS  ⇒ par RTT, cwnd DOUBLE (exponentiel)
   RTT :   0     1     2     3     4     5     6
   cwnd:  10 →  20 →  40 →  80 → 160 → 320 → 640 MSS
```

« Slow » est trompeur : c'est la phase la plus **agressive** de TCP. Ce qui est lent, c'est le **point de départ**, pas la
pente. Elle s'arrête à la première perte, ou quand `cwnd` atteint le seuil **`ssthresh`**.

### 10.2 Congestion avoidance et AIMD

Au-delà de `ssthresh`, croissance **linéaire** : `+1 MSS par RTT`. C'est l'**AIMD** — *Additive Increase, Multiplicative
Decrease* :

```
   Pas de perte → cwnd += 1 MSS par RTT          (additive increase)
   Perte        → cwnd = cwnd × β                (multiplicative decrease)
                  β = 0,5 pour Reno ; 0,7 pour CUBIC
   cwnd │    ╱|   ╱|   ╱|   ← la fameuse « dent de scie »
        │  ╱  | ╱  | ╱  |
        │╱slow▼ ← perte : on divise, puis on remonte
        └────────────────────► temps
```

**Pourquoi AIMD ?** Parce que c'est la seule famille simple qui **converge vers l'équité** (Chiu & Jain, 1989) : deux flux
partageant un lien finissent avec la même part, quels que soient leurs points de départ.

### 10.3 Réaction à une perte : les deux régimes

```
  ┌── PERTE PAR TIMEOUT (RTO) ─────────────── grave : on ne sait plus rien ──┐
  │   ssthresh = cwnd / 2  puis  cwnd = 1 MSS  ◄── retour en SLOW START      │
  └──────────────────────────────────────────────────────────────────────────┘
  ┌── PERTE PAR 3 DUP-ACK ────── bénin : des paquets circulent encore ───────┐
  │   ssthresh = cwnd / 2  puis  cwnd = ssthresh (+3 MSS)  ◄── FAST RECOVERY,│
  │   on RESTE en congestion avoidance                                       │
  └──────────────────────────────────────────────────────────────────────────┘
```

C'est **la** différence entre TCP Tahoe (1988, tout tombe à 1) et **TCP Reno** (1990, fast recovery). NewReno améliore
encore le cas des pertes multiples dans une même fenêtre.

> 🧠 **MÉMO** — **Timeout = amnésie totale** (cwnd à 1, slow start). **3 dup-ACK = simple frayeur** (on divise par
> deux et on continue). Le raisonnement est physique : des ACK qui arrivent prouvent que des paquets **traversent
> encore** le réseau ; un silence complet veut dire qu'on ne sait plus rien du chemin.

> ❓ **RETIENS ÇA** — Après un timeout de retransmission, que valent `cwnd` et `ssthresh` ?
> <details><summary>→ réponse</summary><br><code>ssthresh = cwnd/2</code> puis <code>cwnd = 1 MSS</code>, et on repart en <b>slow start</b>.</details>

### 10.4 Reno vs CUBIC vs BBR

| | **Reno / NewReno** | **CUBIC** | **BBR** |
|---|---|---|---|
| Signal utilisé | Perte | Perte | **Modèle** : débit du goulot + RTT min |
| Croissance | Linéaire, +1 MSS/RTT | **Cubique** en fonction du **temps** | Sondage périodique du débit |
| Réduction | × 0,5 | × 0,7 | Pas de division brutale |
| Dépend du RTT ? | **Oui** (pénalise les longs RTT) | **Non** | Non |
| Face au bufferbloat | Remplit les buffers | Remplit les buffers | **Les vide** (vise le BDP) |
| Défaut | Historique | **Linux depuis 2.6.19** | Google (à activer) |

**CUBIC** remplace la croissance linéaire par `W(t) = C·(t − K)³ + W_max`, `C = 0,4` : remontée **rapide** après la perte,
**plateau** autour de l'ancien maximum `W_max` (là où ça avait cassé), puis nouvel assaut. Point clé : la croissance dépend
du **temps écoulé**, pas du nombre de RTT — d'où l'équité entre un flux à 1 ms et un flux à 100 ms, là où Reno écrase le
second.

**BBR** (*Bottleneck Bandwidth and Round-trip propagation time*) **n'attend pas la perte** : il estime en continu `BtlBw`
(débit max observé) et `RTprop` (RTT minimal), en déduit le BDP, **pace** l'émission à `BtlBw` et plafonne les données en
vol vers `2 × BDP`. Il résout ainsi le **bufferbloat** :

```
   Un algo à PERTE remplit les buffers du routeur JUSQU'AU DÉBORDEMENT.
   Or le débit plafonne bien avant : tout le reste n'ajoute que de la LATENCE.

   débit ▲        ┌──────────────────  ← plateau : plus rien à gagner
         │       ╱│  BBR vise le COUDE ; Reno/CUBIC vont jusqu'au bout ──┐
         └─────┴──┴──────────────────────────────────────────────────┴──► en vol
                  BDP                                      BDP + buffer plein
   latence : plate jusqu'au coude, puis elle EXPLOSE.
```

**BBR gagne** sur les liens longue distance à perte non congestive (inter-régions, Wi-Fi, 4G/5G), où 0,1 % de perte effondre
CUBIC. **BBRv1 pose problème** face à des flux CUBIC sur buffer peu profond ; v2/v3 corrigent via l'ECN. Bascule :
`sysctl -w net.ipv4.tcp_congestion_control=bbr` (choix possibles : `net.ipv4.tcp_available_congestion_control`).

> ⚠️ **PIÈGE** — « BBR est meilleur, on l'active partout. » Sur un réseau interne à faible RTT et sans perte, le
> gain est **nul à négatif**, et l'équité vis-à-vis des autres flux change. À activer sur mesure avant/après
> (`iperf3`), jamais par croyance.

> ❓ **RETIENS ÇA** — Quelle grandeur BBR utilise-t-il à la place de la perte ?
> <details><summary>→ réponse</summary><br>Un <b>modèle du chemin</b> : la bande passante du goulot (BtlBw) et le RTT minimal (RTprop), dont le produit donne le BDP visé.</details>

---

## 11. Nagle, delayed ACK, et l'interaction qui coûte 40 ms

**Nagle** (RFC 896) répond à ceci : une session telnet envoie 1 octet par frappe, soit 1 octet utile pour 40 octets
d'en-têtes — 2,5 % d'efficacité. **La règle** : *tant que des données non acquittées sont en vol, accumule les petites
écritures ; envoie quand tu as un MSS complet ou quand l'ACK arrive.* Désactivation : `TCP_NODELAY`.

**Le delayed ACK** (RFC 1122) attaque le problème symétrique : ne pas envoyer un ACK vide par segment, mais attendre un peu
pour le piggybacker sur une réponse. Délai maximum RFC **500 ms** ; en pratique **40 à 200 ms** sous Linux, **200 ms** sous
Windows. On acquitte de toute façon **au moins un segment plein sur deux**. Séparément, les deux sont raisonnables.
**Ensemble, ils s'interbloquent** :

```
  Application : write(petit A) ; write(petit B) ; attend la réponse

  Émetteur (Nagle)                          Récepteur (delayed ACK)
     │─── A (petit) ──────────────────────────►│
     │  B est retenu : A n'est pas acquitté     │ « j'attends une réponse
     │      ⏳ ────────── 40 ms perdues ────────│   pour piggybacker... »
     │◄─── ACK(A) (expiration du timer) ────────│
     │─── B ───────────────────────────────────►│
  Symptôme : latence STABLE à ~40 ms (ou 200 ms) par requête, indépendante
             de la charge et de la taille du message.
```

**Correctifs** : `TCP_NODELAY` — ce que font Redis, Kafka, gRPC et toute bibliothèque RPC sérieuse — ou mieux, **écrire le
message en un seul `write()`**. À l'inverse `TCP_CORK` (Linux) retient jusqu'au segment plein ou 200 ms : utile pour servir
en-tête + fichier, inutile en RPC.

> 🧠 **MÉMO** — **Nagle = « j'attends d'avoir assez à dire ». Delayed ACK = « j'attends d'avoir une raison de
> parler ».** Deux polis qui se taisent ⇒ 40 ms de silence gêné.

> ⚠️ **PIÈGE** — Une latence **stable à 40 ms ou 200 ms** n'est presque jamais du réseau : c'est un **timer**. Une
> latence variable et corrélée à la charge, ça, c'est du réseau. Ce réflexe fait gagner des heures.

---

## 12. Le BDP, ou pourquoi ton transfert inter-DC rampe

La section la plus rentable du module : elle explique un phénomène que tu vas rencontrer, et elle tombe en entretien.

```
   BDP (octets) = Bande passante (bit/s) × RTT (s) ÷ 8
   Débit atteignable = Fenêtre / RTT      ← les deux relations à savoir par cœur
   Analogie : un tuyau d'eau — le DÉBIT est sa section, le RTT sa LONGUEUR ; le BDP
   est le volume qu'il faut avoir INJECTÉ pour que le tuyau soit plein.
```

### 12.1 Exercice intégralement corrigé

> Tu copies 1 To d'un DC européen vers un DC américain. Lien **10 Gbit/s**, **RTT 80 ms**. Le transfert plafonne à
> **6,5 Mbit/s**. Explique, puis corrige.

**① Le BDP.** `10 × 10⁹ × 0,080 ÷ 8 = 100 × 10⁶ octets = 100 Mo`. Il faut **100 Mo en vol** pour remplir ce tuyau.

**② La fenêtre réellement utilisée.** Sans window scaling, le champ Fenêtre plafonne à 65 535 octets :
`65 535 / 0,080 = 819 187 octets/s ≈ 6,55 Mbit/s`. On retrouve **exactement** le chiffre observé — diagnostic bouclé :
**le window scaling est absent**.

**③ Le facteur d'échelle nécessaire.** `65 535 × 2^s ≥ 100 × 10⁶ → 2^s ≥ 1526 → s = 11` (2048), soit une fenêtre de
`65 535 × 2048 = 134 Mo` ✔.

**④ Vérifier et corriger.**
```bash
sysctl net.ipv4.tcp_window_scaling                    # doit valoir 1
ss -ti dst 10.20.0.9 | grep -E 'wscale|rtt|cwnd'      # wscale:0,0 → option strippée sur le chemin
sysctl -w net.core.rmem_max=134217728
sysctl -w net.ipv4.tcp_rmem="4096 131072 134217728"   # idem tcp_wmem
```

**⑤ Le temps de transfert.** `8 × 10¹² / 6,55 × 10⁶ = 1 221 000 s`, soit **14 JOURS** — contre
`8 × 10¹² / 10 × 10⁹ = 800 s`, soit **13 minutes** à pleine vitesse.

### 12.2 Deuxième limite : la perte

Même avec la bonne fenêtre, un TCP à perte plafonne. La **formule de Mathis** donne le débit maximal d'un flux Reno en
fonction du taux de perte `p` — `Débit ≈ MSS / (RTT × √p)`, à un facteur ~1,22 près. Avec MSS 1460, RTT 80 ms et **0,001 %
de perte** (p = 10⁻⁵) :

```
   1460 / 0,080 = 18 250 octets/s ;  1/√10⁻⁵ = 316,2
   Débit ≈ 18 250 × 316,2 = 5,77 × 10⁶ octets/s ≈ 46 Mbit/s
```

**46 Mbit/s sur un lien à 10 Gbit/s, pour un paquet perdu sur cent mille.** Le résultat le plus contre-intuitif du module,
et la raison d'être des outils de transfert massif (Aspera, UDT, rclone multi-flux) et de BBR : soit on ouvre **N flux
parallèles** (débit × N), soit on prend un algorithme qui ne lit pas la perte comme de la congestion.

> 🧠 **MÉMO** — **Longue distance + perte infime = débit ridicule.** Deux remèdes : **plus de flux** (`-P 8` sous
> iperf3, `--parallel` dans les outils de copie) ou **BBR**. Augmenter la bande passante ne change **rien**.

**Le temps de montée compte aussi.** Pour atteindre 100 Mo en vol depuis IW = 10 MSS : `100 × 10⁶ / 1460 ≈ 68 500 segments`,
`10 × 2ⁿ ≥ 68 500 → n ≈ 12,7 → 13 RTT`, soit **1,05 s de slow start** rien que pour atteindre le régime nominal. D'où la
règle : **une grosse connexion longue** vaut mieux que mille petites qui repartent chacune de 10 MSS — c'est l'argument du
*connection pooling*.

> ❓ **RETIENS ÇA** — Formule du BDP et du débit atteignable ?
> <details><summary>→ réponse</summary><br><code>BDP = débit × RTT</code> (attention bits vs octets) et <code>débit = fenêtre / RTT</code>. À 10 Gbit/s et 80 ms de RTT : <b>100 Mo</b> de BDP.</details>

---

## 13. MTU, MSS et le trou noir de la PMTUD

TCP annonce son MSS dans le SYN, calculé sur la MTU de **son** interface. Si un lien intermédiaire a une MTU plus faible
(VXLAN, IPsec, VPN), le routeur devrait fragmenter — mais le bit **DF**, que TCP lève toujours, le lui interdit : il renvoie
un **ICMP type 3 code 4** « Fragmentation Needed » portant la MTU autorisée. C'est la **Path MTU Discovery** — et si cet
ICMP est filtré, personne n'apprend rien.

```
   Client MTU 1500 ──── VXLAN MTU 1450 ──── Serveur MTU 1500
       │  SYN         (40 o)      ────────► passe  ✔  la connexion S'ÉTABLIT
       │  requête     (200 o)     ────────► passe  ✔
       │  gros POST   (1500 o, DF) ──✗ trop gros ──┤ ICMP 3/4 (MTU=1450)
       │  ◄────────── BLOQUÉ par un pare-feu ──────┘
       └─ retransmet, retransmet... → le transfert GÈLE
   SIGNATURE : handshake OK, petites requêtes OK, gros transferts gelés.
```

**Corrections** : laisser passer l'ICMP type 3 (la règle de pare-feu la plus mal comprise du métier), activer
`net.ipv4.tcp_mtu_probing=1`, ou **clamper le MSS** sur le routeur — `iptables -t mangle -A FORWARD -p tcp --tcp-flags
SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu`.

> ⚠️ **PIÈGE** — Bloquer **tout** l'ICMP « pour la sécurité » casse la PMTUD et donne le symptôme le plus pénible
> qui soit : ça marche, sauf pour les gros volumes. Le seul ICMP éventuellement filtrable est l'echo (type 8).
> **Jamais le type 3.**

> ❓ **RETIENS ÇA** — Le handshake passe, les petites requêtes passent, les gros transferts gèlent. Diagnostic ?
> <details><summary>→ réponse</summary><br><b>Trou noir de PMTUD</b> : un lien à MTU réduite sur le chemin et l'ICMP 3/4 « Fragmentation Needed » filtré. Correction : autoriser l'ICMP 3, ou clamper le MSS.</details>

---

## 14. UDP : ce qui reste quand on enlève tout

```
 |◄──────── 32 bits ────────────────────────────────────────────►|
 +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
 |          Port SOURCE          |       Port DESTINATION        |  4 o
 +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
 |    LONGUEUR (en-tête+données) |           CHECKSUM            |  8 o
 +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
 |                          DONNÉES                              |
```

**8 octets d'en-tête**, fixes (contre 20 minimum pour TCP), **protocole IP 17** (TCP = 6). Le champ Longueur couvre
en-tête et données, **minimum 8** ; charge utile maximale **65 507** octets (65 535 − 8 − 20 d'IP) ; checksum **optionnel en IPv4**
(0 = non calculé), **obligatoire en IPv6**. **Ni séquence, ni acquittement, ni fenêtre, ni état** : un datagramme peut se
perdre, arriver en double ou dans le désordre, UDP ne le saura pas et ne te le dira pas. En échange, **zéro RTT
d'établissement**, aucun état en mémoire, pas de *head-of-line blocking*.

> ❓ **RETIENS ÇA** — Taille de l'en-tête UDP et numéro de protocole IP ?
> <details><summary>→ réponse</summary><br><b>8 octets</b>, protocole IP <b>17</b>. TCP : 20 octets minimum, protocole <b>6</b>.</details>

| Cas d'usage | Pourquoi UDP |
|---|---|
| **DNS** (53) | Une requête, une réponse, un datagramme. Un handshake doublerait la latence de chaque résolution |
| **DHCP** (67/68) | Le client n'a **pas encore d'adresse IP** : TCP est impossible |
| **NTP** (123) | Une retransmission fausserait la mesure du temps |
| **Voix / vidéo** (RTP) | Un paquet en retard est **inutile** : mieux vaut le perdre que bloquer le flux |
| **syslog** (514), StatsD | Volume énorme, perte tolérable, on ne veut pas bloquer l'émetteur |
| **VXLAN** (4789), **QUIC** (443) | Encapsulation, ou fiabilité reconstruite en espace utilisateur, plus finement |

Le critère en une phrase : **si une donnée périmée n'a plus de valeur, TCP te nuit** — il te la livrera quand même, en
retard, en bloquant tout le reste.

> ⚠️ **PIÈGE** — « UDP est plus rapide que TCP. » Paresseux. UDP a une **latence d'établissement nulle** et pas de
> head-of-line blocking, mais sur un gros transfert avec pertes un UDP naïf est **beaucoup plus lent** : il faut
> retransmettre à la main, et souvent mal. UDP n'est pas plus rapide, il est **plus direct**.

> ⚠️ **PIÈGE** — DNS n'est pas « UDP seulement ». Il bascule sur **TCP 53** dès que la réponse dépasse la taille
> annoncée (512 octets historiquement, 1232 recommandé avec EDNS0) et pour les transferts de zone (AXFR). Un
> pare-feu qui bloque le TCP 53 casse DNSSEC et les grosses réponses.

---

## 15. QUIC et HTTP/3

### 15.1 Les trois problèmes de TCP que QUIC attaque

**① Le head-of-line blocking de transport.** HTTP/2 multiplexe N flux dans **une** connexion TCP, mais TCP livre un flux
d'octets **strictement ordonné** : un segment perdu bloque **tout** ce qui suit, y compris les données d'autres flux HTTP
parfaitement arrivées.

```
   HTTP/2 sur TCP : un seul segment perdu bloque TOUT
   ┌────────────────────────────────────────────────┐
   │ stream 1 │ stream 2 │ ✗PERDU │ stream 3 │ ... │  ← 1 seul flux d'octets
   └────────────────────────────────────────────────┘
       → streams 1, 2 ET 3 attendent, alors que 3 est arrivé intact.

   HTTP/3 sur QUIC : streams INDÉPENDANTS au niveau transport
   ┌──────────┐ ┌──────────┐ ┌──────────┐
   │ stream 1 │ │ stream 2 │ │ stream 3 │   ← trois espaces d'ordre séparés
   └──────────┘ └────✗─────┘ └──────────┘
       livré        attend       livré      ← seul le 2 est pénalisé
```

**② Le coût d'établissement.** TCP + TLS 1.3 = **2 RTT** ; TCP + TLS 1.2 = **3 RTT**. À 80 ms de RTT, c'est 160 à 240 ms
avant le premier octet utile.

**③ L'ossification.** TCP vit dans le noyau et est inspecté par des milliers de middleboxes : déployer une amélioration
prend dix ans. QUIC vit en **espace utilisateur** et chiffre presque tout son en-tête — les middleboxes ne peuvent plus rien
y comprendre, donc plus rien y casser.

### 15.2 Ce qu'est QUIC

```
   HTTP/2 : │ HTTP/2 │ TLS 1.2/3 │  TCP  │ IP │       (RFC 7540)
   HTTP/3 : │ HTTP/3 │      QUIC (TLS 1.3 INTÉGRÉ)      │ UDP 443 │ IP │
              9114        RFC 9000 / 9001 / 9002
                          fiabilité + crypto + multiplexage dans UNE couche
```

QUIC est un transport **complet** posé sur UDP. Il réimplémente en espace utilisateur : numéros de paquets, acquittements
par plages (façon SACK généralisé), retransmission, contrôle de congestion (CUBIC ou BBR au choix), contrôle de flux **par
stream et global** — plus le chiffrement, **intégré et obligatoire**.

| Caractéristique | Détail |
|---|---|
| **Handshake** | **1 RTT** (transport + TLS 1.3 fusionnés) ; **0-RTT** en reprise de session |
| **Connection ID** | Identité de connexion **indépendante du quadruplet** → **migration** Wi-Fi ↔ 4G sans coupure |
| **Streams** | Bi/unidirectionnels, ordonnés **individuellement**, flow control par stream |
| **Chiffrement** | TLS 1.3 obligatoire, en-têtes protégés |
| **Retransmission** | **Sans ambiguïté** : les numéros de paquet sont strictement croissants, une donnée retransmise part dans un **nouveau** numéro → RTT toujours mesurable |
| **Anti-amplification** | Un serveur n'envoie pas plus de **3×** ce qu'il a reçu avant validation d'adresse |

**Le Connection ID est le point le plus élégant.** Une connexion TCP *est* son quadruplet : ton IP change, elle meurt. En
QUIC, la connexion est identifiée par un **CID** transporté dans les paquets : tu passes du Wi-Fi à la 4G, IP et port
changent, le CID reste, la connexion continue — et un load balancer sait encore où router.

> ⚠️ **PIÈGE** — « QUIC, c'est de l'UDP, donc ce n'est pas fiable. » **Faux.** QUIC est **fiable et ordonné par
> stream**. UDP n'est qu'un véhicule, choisi parce que c'est le seul moyen de déployer un nouveau transport sur
> l'Internet existant sans que les middleboxes le bloquent.

> ⚠️ **PIÈGE** — Le 0-RTT n'est pas gratuit : ces données sont **rejouables** par un attaquant. On ne les utilise
> donc que pour des requêtes **idempotentes** (un GET, jamais un POST de virement).

> 🧠 **MÉMO** — QUIC en quatre mots : **U**DP, **1**-RTT, **C**onnection ID, **S**treams indépendants. Le vrai gain
> n'est pas « c'est plus rapide » mais « **une perte ne pénalise plus que le stream concerné** ».

> ❓ **RETIENS ÇA** — Qu'est-ce que le *head-of-line blocking* et à quelle couche QUIC le supprime-t-il ?
> <details><summary>→ réponse</summary><br>Un objet en tête de file bloque tous ceux qui suivent. QUIC le supprime au niveau <b>transport</b> : les streams sont ordonnés indépendamment. Il subsiste <b>à l'intérieur d'un même stream</b>, ce qui est voulu.</details>

**Le coût** : plus de CPU (chiffrement par paquet, espace utilisateur, moins d'offload matériel), parfois bridé par des
opérateurs qui traitent l'UDP en seconde classe, et plus dur à observer (tout est chiffré). La découverte passe par
l'en-tête HTTP `Alt-Svc: h3=":443"` ou un enregistrement DNS **HTTPS/SVCB**, avec repli sur TCP si l'UDP 443 est bloqué.

---

## 16. Diagnostic : les commandes qui répondent vraiment

```bash
ss -s                          # résumé global (total, estab, timewait...)
ss -tlnp                       # ce qui ÉCOUTE, avec le processus  (-tanp state established : actives + PID)
ss -tn state time-wait | wc -l # compter les TIME_WAIT  (state close-wait : fuite de FD applicative)
ss -ti dst 10.20.0.9           # LE plus utile : métriques internes par socket
```

**Lire un `ss -ti`, ligne par ligne** — c'est ce qui te fera trouver la panne :

```
ESTAB 0 3126848  10.0.1.7:44120   10.20.0.9:9092
     cubic wscale:11,11 rto:200 rtt:84.3/2.1 mss:1448 cwnd:142 ssthresh:96
     bytes_sent:918273645 bytes_retrans:2847361 retrans:0/1943
     delivery_rate 18.6Mbps pacing_rate 23.4Mbps rcv_space:14480
```

| Champ | Lecture |
|---|---|
| `wscale:11,11` | Facteur d'échelle **émission,réception**. `0,0` = **fenêtre plafonnée à 64 Kio** |
| `rto:200` / `rtt:84.3/2.1` | Timeout de retransmission (ms) / RTT lissé et variance (ms). Ici `SRTT + 4×RTTVAR = 84,3 + 8,4 ≈ 93 ms`, relevé au **plancher Linux de 200 ms** |
| `mss:1448` | 1500 − 20 IP − 20 TCP − 12 (timestamps) |
| `cwnd:142` / `ssthresh:96` | Fenêtre de congestion **en segments** (≈ 206 Ko en vol) ; `cwnd > ssthresh` ⇒ congestion avoidance |
| `retrans:0/1943` | **en cours / cumulé**. Rapporté à `bytes_sent`, ça donne le taux |
| `delivery_rate` | Débit réellement constaté |
| `Send-Q 3126848` | 3 Mo envoyés non acquittés → le goulot est **en aval** |

**Le calcul réflexe** : `cwnd × mss / rtt` = débit plafond. Ici `142 × 1448 / 0,0843 ≈ 2,4 Mo/s ≈ 19,5 Mbit/s`. Si tu
attendais 1 Gbit/s, ce n'est ni l'application ni le disque : c'est `cwnd`, donc de la **perte**.

**Compteurs globaux** : `nstat -az | grep -Ei 'retrans|TCPLost|Timeout|Drop'`. **Le seul ratio qui compte** :
`TcpRetransSegs / TcpOutSegs` — **< 0,1 %** sain, 0,1-1 % à surveiller sur long RTT, **> 1 %** problème réseau réel
(saturation, MTU, câble, buffer d'équipement).

```bash
tcpdump -ni any -w capture.pcap 'host 10.20.0.9 and port 9092'
tcpdump -ni any 'tcp[tcpflags] & (tcp-syn|tcp-fin|tcp-rst) != 0'   # que les flags de contrôle
```

| Filtre d'affichage Wireshark | Ce que ça révèle |
|---|---|
| `tcp.analysis.flags` | **Tout ce que Wireshark juge anormal**. Commence toujours par là |
| `tcp.analysis.retransmission` / `.fast_retransmission` | Retransmission sur RTO / sur 3 dup-ACK |
| `tcp.analysis.duplicate_ack` / `.out_of_order` | ACK dupliqués / désordre (souvent ECMP, pas une perte) |
| `tcp.analysis.zero_window` | Récepteur saturé → **application lente**, pas le réseau |
| `tcp.flags.syn==1 && tcp.flags.ack==0` / `tcp.flags.reset==1` | Débuts de connexion / qui claque la porte |
| `tcp.stream eq 7` | Isoler une connexion (puis *Follow → TCP Stream*) |

Les deux graphiques à connaître : **Statistics → TCP Stream Graphs → Time Sequence (tcptrace)**, où les paliers horizontaux
sautent aux yeux, et **Throughput**, qui montre l'effondrement après chaque perte.

> ⚠️ **PIÈGE** — Une « retransmission » signalée par Wireshark peut être un **artefact de capture** : capturé sur
> une machine intermédiaire en ayant raté l'original, l'outil ne voit que la copie. Vérifie avec
> `tcp.analysis.spurious_retransmission` et, au moindre doute, **capture des deux côtés simultanément**.

> ❓ **RETIENS ÇA** — Un transfert stagne, `ss -ti` montre `cwnd:3` et `retrans:0/8412`. Diagnostic ?
> <details><summary>→ réponse</summary><br><b>Perte réseau massive</b> : la fenêtre de congestion est écroulée à 3 segments par des retransmissions à répétition. Ce n'est ni l'application ni la fenêtre de réception — on cherche un lien saturé, un problème de MTU, ou un équipement défaillant.</details>

---

## 17. Ce que ça donne dans un vrai pipeline de données

| Symptôme | Cause TCP la plus probable | Vérification |
|---|---|---|
| Copie inter-région à 6 Mbit/s | **Pas de window scaling** (option strippée) | `ss -ti \| grep wscale` |
| Débit plafonné, retransmissions | Perte + CUBIC (formule de Mathis) | `nstat`, puis `-P 8` ou BBR |
| Connexion JDBC morte après une pause | **Timeout de NAT** (350 s) sans keepalive | `tcp_keepalive_time` → 300 |
| `CLOSE_WAIT` qui s'accumulent | Fuite de descripteurs **applicative** | `ss -tn state close-wait`, `lsof -p` |
| `EADDRNOTAVAIL` sur un worker | Épuisement des ports éphémères / TIME_WAIT | Pooling, `ip_local_port_range` |
| Handshake OK, gros POST gelé | **Trou noir PMTUD** (overlay + ICMP filtré) | `ping -M do -s 1472`, MSS clamping |
| Latence stable à 40 ms par requête | Nagle × delayed ACK | `TCP_NODELAY`, ou un seul `write()` |
| `SYN_SENT` persistant | Pas de route retour / pare-feu (cf. R04) | `tcpdump` **des deux côtés** |

**Kafka.** Un consumer distant est un cas d'école de BDP : côté client c'est `receive.buffer.bytes` (défaut **64 Ko**,
`-1` = on laisse l'auto-tuning de l'OS) — côté broker, `socket.receive.buffer.bytes` (défaut **100 Ko**) — qui
doit couvrir le BDP broker↔consumer, sinon un consumer inter-région plafonne sans que le broker soit chargé. Vérifie
avec `ss -ti` **pendant** un fetch, pas après.

**Kubernetes.** Trois pièges cumulés : la MTU de l'overlay (VXLAN = 50 octets de moins), le NAT de `kube-proxy` qui consomme
des entrées `conntrack` (`nf_conntrack_count` contre `nf_conntrack_max`), et un `terminationGracePeriodSeconds` mal réglé
qui produit des RST au lieu de FIN pendant les rolling updates — vus par tes clients comme des « Connection reset by peer »
intermittents et inexplicables.

---

## 18. Exercice de synthèse, intégralement corrigé

> Un job Spark lit 500 Go depuis un stockage objet d'une autre région. RTT **95 ms**, lien annoncé **25 Gbit/s**,
> débit observé **220 Mbit/s** avec 32 connexions. `ss -ti` : `wscale:11,11`, `cwnd:38`, `mss:1448`,
> `rtt:95.4/8.2`, `retrans:0/24118` pour `bytes_sent:41 G`. Que se passe-t-il, et que fais-tu ?

**① Le window scaling est correct** (`wscale:11`) — la cause n°1 est éliminée.

**② Débit par connexion, depuis cwnd.** `38 × 1448 = 55 024 octets en vol` ; `55 024 / 0,0954 ≈ 576 800 octets/s`, soit
**4,6 Mbit/s** par connexion et `× 32 ≈ 147 Mbit/s` — cohérent avec les 220 observés. **`cwnd` est le facteur limitant.**

**③ BDP théorique.** `25 × 10⁹ × 0,095 / 8 ≈ 297 Mo`, soit `297 × 10⁶ / 1448 ≈ 205 000 segments` de `cwnd` pour saturer. On
en a **38** : on exploite 0,02 % du tuyau.

**④ Taux de perte.** `24 118 × 1448 ≈ 34,9 Mo retransmis sur 41 Go` → `p ≈ 8,5 × 10⁻⁴` (0,085 %).

**⑤ Vérification par Mathis.** `1448 / 0,0954 = 15 178 octets/s` ; `1/√(8,5×10⁻⁴) = 34,3` ; produit ≈ 520 600 octets/s ≈
**4,2 Mbit/s par flux**, contre 4,6 observés. Le modèle colle : on est **limité par la perte**, pas par les buffers.

**⑥ Actions, par rentabilité décroissante.** ① **BBR** : la perte cesse d'être lue comme de la congestion — le plus fort
effet de levier sur un chemin long et lossy. ② **Parallélisme** (32 → 128) : le débit total est ~linéaire en nombre de flux
tant que le lien n'est pas saturé. ③ **Chercher la cause de la perte** : 0,085 % n'est pas normal sur un backbone — lien
saturé, shaping, équipement en erreur (`mtr` long, `nstat`). ④ **Buffers** : `tcp_rmem` max ≥ 300 Mo, sinon même BBR
bloquera sur `rwnd`. ⑤ **Architecture** : la bonne réponse est souvent de **déplacer le calcul vers la donnée**.

---

## 19. Questions d'entretien

**1. Explique le handshake en 3 temps. Pourquoi 3 et pas 2 ?** Le client envoie un SYN portant son ISN ; le serveur répond
par un SYN-ACK avec son propre ISN et acquitte celui du client ; le client acquitte à son tour. Deux temps ne suffisent pas :
après le segment 2, le serveur ne sait pas si le client l'a reçu. Chaque partie doit savoir que son ISN est arrivé, soit
quatre événements — et le SYN-ACK en fusionne deux. Ce troisième segment prouve aussi que le client est bien à l'adresse
annoncée, ce qui limite l'usurpation. Coût : 1 RTT avant le premier octet, et le troisième segment peut déjà porter des
données.

**2. Qu'est-ce que TIME_WAIT et pourquoi existe-t-il ?** L'état dans lequel reste **celui qui ferme en premier**, pendant
2×MSL — 60 secondes en dur sous Linux. Deux raisons : si le dernier ACK se perd, le pair retransmet son FIN et il faut
quelqu'un pour ré-acquitter, sinon il reçoit un RST et croit à une rupture anormale ; et il faut laisser mourir les segments
retardés avant que le même quadruplet soit réutilisé. Ce n'est un problème que côté client, quand on épuise les ports
éphémères — et la vraie correction est le pooling, pas un sysctl.

**3. Différence entre contrôle de flux et contrôle de congestion ?** Le contrôle de flux protège le **récepteur** : il
annonce dans chaque segment une fenêtre `rwnd` égale à la place libre de son buffer, et l'émetteur ne la dépasse jamais —
c'est explicite et négocié. Le contrôle de congestion protège le **réseau** : personne n'annonce rien, alors l'émetteur
maintient une fenêtre `cwnd` purement locale qu'il augmente tant que tout passe et réduit dès qu'il détecte une perte. Ce
qui est en vol vaut le minimum des deux. Un `ZeroWindow` accuse l'application distante ; un `cwnd` écroulé accuse le réseau.

**4. Explique slow start, congestion avoidance et fast recovery.** Slow start démarre à 10 MSS et double `cwnd` à chaque RTT :
exponentiel, donc tout sauf lent — seul le point de départ est petit. Au-delà de `ssthresh`, congestion avoidance,
croissance linéaire de +1 MSS par RTT. À la perte, la réaction dépend du signal : sur timeout,
`ssthresh = cwnd/2` et `cwnd = 1 MSS`, retour en slow start, parce qu'on ne sait plus rien du chemin ; sur trois ACK dupliqués, fast retransmit puis fast
recovery — `cwnd` tombe à `ssthresh` et on reste en croissance linéaire, parce que des ACK qui arrivent prouvent que des
paquets circulent. C'est l'AIMD, la seule famille simple qui converge vers un partage équitable.

**5. CUBIC ou BBR ?** CUBIC est le défaut Linux depuis 2006 : il réagit à la perte, réduit de 30 %, et sa croissance est
cubique en fonction du **temps écoulé** et non du nombre de RTT — ce qui le rend équitable entre flux courts et longs, là où
Reno pénalisait les longs RTT. BBR n'attend pas la perte : il estime la bande passante du goulot et le RTT minimal, en
déduit le BDP et pace son émission dessus, ce qui évite de remplir les buffers et règle le bufferbloat. Il gagne franchement
sur les chemins longs à perte non congestive — inter-région, Wi-Fi, mobile — où 0,1 % de perte effondre CUBIC. Sur un réseau
interne à faible RTT le gain est nul, et BBRv1 peut être injuste envers CUBIC : je l'active après mesure, pas par principe.

**6. Un transfert entre deux régions plafonne à 6 Mbit/s sur un lien à 10 Gbit/s. Ton diagnostic ?**
Je calcule le BDP : 10 Gbit/s × 80 ms = 100 Mo à avoir en vol. Puis je remarque que 65 535 octets divisés par 80 ms donnent exactement 6,5 Mbit/s —
la signature d'une fenêtre bloquée à 64 Kio, donc d'un **window scaling absent**. Je confirme avec `ss -ti | grep wscale` :
`wscale:0,0` alors que `tcp_window_scaling=1` des deux côtés désigne un équipement du chemin qui strippe les options du SYN.
Sinon je monte `tcp_rmem`/`tcp_wmem` et `rmem_max` au-delà du BDP. Si la fenêtre est bonne, je regarde la perte : par
Mathis, 10⁻⁵ suffit à plafonner un flux à 46 Mbit/s à 80 ms de RTT — le remède est alors le parallélisme ou BBR.

**7. À quoi sert SACK, et que se passe-t-il sans lui ?** L'acquittement TCP est cumulatif : il ne peut dire que « j'ai tout
jusqu'à N ». Si les segments 2 et 7 se perdent sur dix, le récepteur ne signale que le manque du 2 ; sans SACK, l'émetteur
ignore le sort des suivants et finit par tout retransmettre — gaspillage massif dès que la fenêtre est grande. SACK ajoute
dans les options la liste des blocs reçus hors séquence, donc on ne renvoie que les trous. Négocié par `SACK-permitted` dans
le SYN, limité à 4 blocs, 3 avec les Timestamps faute de place dans les 40 octets d'options. D-SACK signale en plus les
doublons, ce qui révèle les retransmissions inutiles.

**8. Quand choisis-tu UDP plutôt que TCP ?** Quand une donnée périmée n'a plus de valeur, ou quand l'état de TCP est
impossible ou trop coûteux. DNS, parce qu'un handshake doublerait la latence de chaque résolution ; DHCP, parce que le
client n'a pas encore d'IP ; NTP, parce qu'une retransmission fausserait la mesure ; voix et vidéo, parce qu'un paquet en
retard est inutile et que le réclamer bloquerait le flux ; télémétrie et syslog, volume énorme et perte tolérable ; VXLAN,
parce que la fiabilité est du ressort du protocole encapsulé. En revanche « UDP est plus rapide » est faux en général : il
est plus direct, et il te délègue la fiabilité.

**9. Que change QUIC par rapport à TCP+TLS ?** Trois choses. Il fusionne handshake transport et TLS 1.3, ce qui ramène
l'établissement de 2 RTT à 1 RTT, et à 0 RTT en reprise de session — au prix d'un risque de rejeu qui limite le 0-RTT aux
requêtes idempotentes. Il supprime le head-of-line blocking de transport : les streams sont ordonnés indépendamment, donc
une perte ne pénalise que le stream concerné, là où HTTP/2 bloque tous les streams de la connexion TCP. Enfin la connexion
est identifiée par un Connection ID et non par le quadruplet, ce qui permet de changer de réseau sans la casser. Le tout en
espace utilisateur sur UDP 443, ce qui contourne l'ossification — au prix de plus de CPU et de moins d'observabilité.

**10. Tu vois 800 sockets en CLOSE_WAIT sur ton service. Que conclus-tu ?** Que le bug est chez moi, et qu'il est
applicatif. CLOSE_WAIT signifie que le pair a envoyé un FIN, que mon noyau l'a acquitté, et qu'il attend que **mon
application appelle `close()`** — ce qu'elle ne fait pas. C'est une fuite de descripteurs : réponse HTTP jamais fermée,
connexion sortie d'un pool sans être rendue, `try` sans `finally`. Ça ne redescendra jamais tout seul et je finirai en
`EMFILE`. Je confirme par `ss -tn state close-wait` puis `lsof -p`, et je remonte au chemin de code. À ne pas confondre avec
FIN_WAIT_2, le symétrique exact, qui accuse le pair.
---

## 20. Les 3 choses à retenir si tu ne retiens que ça

**1. TCP numérote des OCTETS et pilote deux fenêtres.** Le numéro de séquence est la position du premier octet du segment
dans le flux, l'acquittement est le **prochain octet attendu**, et SYN comme FIN consomment chacun un numéro. Par-dessus,
deux freins indépendants : `rwnd`, annoncée par le récepteur pour protéger **son buffer**, et `cwnd`, devinée par l'émetteur
pour protéger **le réseau**. Ce qui est en vol vaut le minimum des deux. Toute question sur TCP se ramène presque toujours à
« laquelle des deux fenêtres est le goulot ? ».

**2. `Débit = Fenêtre / RTT`. C'est la formule qui explique 90 % des transferts lents.** À 10 Gbit/s et 80 ms de RTT, il
faut **100 Mo en vol** ; sans window scaling on plafonne à 65 535 octets, soit **6,5 Mbit/s** — et ce chiffre exact doit
t'alerter dès que tu le vois. Deuxième plafond, plus vicieux : la perte — un taux de 10⁻⁵ suffit à limiter un flux à
~46 Mbit/s à 80 ms de RTT. Les remèdes ne sont jamais « acheter plus de bande passante » mais : grandir la fenêtre,
paralléliser les flux, ou passer en BBR.

**3. L'état d'une socket désigne le coupable, et il n'est presque jamais le réseau.** `SYN_SENT` bloqué → route ou pare-feu
(couche 3) · `CLOSE_WAIT` qui s'accumule → **ton** code ne ferme pas · `FIN_WAIT_2` bloqué → le code **du pair** ne ferme
pas · `ZeroWindow` → l'application distante ne lit pas · `Recv-Q` haut → consommateur lent, `Send-Q` haut → réseau ou pair ·
latence **stable** à 40/200 ms → un timer (Nagle × delayed ACK) · handshake OK mais gros transferts gelés → **MTU et
PMTUD**. Cette table transforme une enquête de trois heures en un diagnostic de trois minutes.
