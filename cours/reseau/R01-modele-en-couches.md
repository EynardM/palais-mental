# R01 — Le modèle en couches : OSI, TCP/IP, encapsulation

> **Ce que tu sauras faire à la fin**
> - Nommer les 7 couches OSI et les 4 couches TCP/IP dans les deux sens, et dire à quelle couche appartient n'importe quel protocole ou équipement qu'on te cite.
> - Dessiner de mémoire l'empilement complet d'un octet de données applicatif jusqu'au bit sur le câble, avec la taille exacte de chaque en-tête.
> - Calculer un MSS à partir d'un MTU, prédire une fragmentation, et expliquer pourquoi un tunnel casse un pipeline qui marchait la veille.
> - Suivre pas à pas un paquet entre deux machines de sous-réseaux différents : ce qui change, ce qui ne change pas, et pourquoi.
> - Localiser une panne à la bonne couche en 3 commandes (`ip`, `ss`, `tcpdump`) au lieu de relancer le job « pour voir ».
> - Expliquer où le modèle en couches est un mensonge utile : TLS, VXLAN, QUIC, NAT, load balancers L7.
>
> **Pourquoi ça compte dans ton poste**
> Un pipeline de données, c'est de la donnée qui traverse des couches. Quand Spark met 6 heures au lieu de 40 minutes, quand un `COPY` vers l'entrepôt se fige à 90 %, quand un pod K8s parle à un service managé dans un autre VPC et que la connexion tombe pile sur les gros messages, la cause est presque toujours à la couche 3 ou 4 — MTU, MSS, fenêtre TCP, RTT, MTU d'overlay. Un data engineer qui sait dire « ce n'est pas Spark, c'est le PMTU discovery cassé par le security group qui bloque ICMP » vaut trois data engineers qui augmentent la taille du cluster. Et côté IA : servir un modèle, c'est du réseau — la latence de ton endpoint d'inférence, c'est du RTT plus du temps de calcul, et tu dois savoir séparer les deux.
>
> **Prérequis** : aucun module préalable, R01 est la fondation du parcours réseau. Utile mais pas obligatoire : savoir ce qu'est une adresse IP et lancer une commande dans un terminal.
>
> **Durée de lecture** : 75-90 min. Lis la fiche `R01-fiche.md` AVANT, même sans rien comprendre : le pretesting double la rétention.

---

## 1. Le problème avant la solution : pourquoi des couches ?

### 1.1 Le problème

Tu veux faire parler deux machines. Naïvement, tu écris un programme qui :
1. transforme ton message en signal électrique,
2. sait comment se partager le câble avec les autres machines,
3. sait comment trouver la machine d'en face à l'autre bout du monde,
4. sait quoi faire si un morceau se perd,
5. sait chiffrer,
6. sait ce que le message veut dire.

Six responsabilités dans un seul programme. Maintenant, change de câble : tu passes du cuivre à la fibre. Tout est à réécrire, y compris la partie « ce que le message veut dire ». C'est absurde. Change de protocole applicatif : tu réécris la gestion du câble. Absurde aussi.

**Le problème réel n'est pas « comment transmettre » — c'est « comment transmettre sans que chaque changement quelque part n'oblige à tout réécrire ».**

### 1.2 La solution : découper en couches indépendantes

On découpe le problème en **strates superposées**. Chaque couche :
- rend **un service** à la couche du dessus,
- utilise **le service** de la couche du dessous,
- **ignore totalement** comment les autres couches font leur travail.

Le contrat entre deux couches s'appelle une **interface**. Le contrat entre une couche N d'une machine et la couche N de la machine d'en face s'appelle un **protocole**.

> **Analogie — la lettre postale.**
> Tu écris une lettre en français (couche application : le sens). Tu la mets dans une enveloppe avec le nom du destinataire (couche transport : à quel service la remettre). L'enveloppe entre dans un sac postal avec la ville de destination (couche réseau : le routage global). Le sac monte dans un camion qui va de dépôt en dépôt (couche liaison : un saut à la fois). Le camion roule sur du bitume (couche physique).
> **Point clé** : le facteur ne lit pas ta lettre. Le camion ne sait pas ce qu'il y a dans les sacs. Et si demain on remplace le camion par un train, ta lettre est identique. C'est exactement ça, le découplage en couches.

### 1.3 Les trois bénéfices, nommés

**Découplage** : passer du Wi-Fi à l'Ethernet ne change pas une ligne de ton code Python. **Interopérabilité** : un Mac, un routeur Cisco et un serveur Linux se parlent parce qu'ils implémentent les mêmes *protocoles*, pas le même *code*. **Spécialisation** : l'équipe qui fabrique des cartes réseau et l'équipe qui écrit HTTP ne se parlent jamais.

> ❓ **RETIENS ÇA** — *Quelle est la différence entre une « interface » et un « protocole » dans un modèle en couches ?*
> <details><summary>▸ réponse</summary>
>
> **Interface = vertical**, entre deux couches adjacentes de la **même** machine. **Protocole = horizontal**, entre la couche N d'une machine et la couche N de la machine distante. TCP est un protocole ; l'API socket est une interface.
> </details>

---

## 2. Le modèle OSI : les 7 couches

OSI (*Open Systems Interconnection*), normalisé par l'ISO en 1984. Il n'a **jamais été implémenté tel quel** dans l'Internet — mais c'est le vocabulaire commun de tout le métier. Quand un ops te dit « c'est un problème L7 », il parle OSI.

```
 7 | Application  | Le service rendu à l'humain         | HTTP, DNS, SSH
 6 | Présentation | Format, encodage, (dé)chiffrement   | TLS*, UTF-8
 5 | Session      | Ouvrir/maintenir/fermer un dialogue | RPC, SOCKS
 4 | Transport    | De bout en bout, fiable ou non      | TCP, UDP, QUIC*
 3 | Réseau       | Adressage logique + routage global  | IP, ICMP, OSPF
 2 | Liaison      | Un saut, de voisin à voisin         | Ethernet, ARP*
 1 | Physique     | Bits -> signal (tension, lumière)   | RJ45, fibre
                                          (* = cas limites, voir §10)
```

> 🧠 **MÉMO** — De bas en haut : **P**hysique **L**iaison **R**éseau **T**ransport **S**ession **P**résentation **Application** →
> **« Pour Le Réseau, Tout Se Passe Automatiquement »**.
> De haut en bas (l'ordre où on descend en encapsulant) : **A**pplication **P**résentation **S**ession **T**ransport **R**éseau **L**iaison **P**hysique →
> **« Après Plusieurs Sages Tentatives, Recommence Là Précisément »**.
> Sache réciter **dans les deux sens**. En entretien, on demande souvent « la couche 4 c'est laquelle ? » — pas la liste.

### 2.1 Couche par couche, la question à laquelle elle répond

**Couche 1 — Physique. « Comment transformer un 1 et un 0 en quelque chose qui voyage ? »**
Tension électrique, impulsion lumineuse, onde radio. Définit connecteurs (RJ45, LC), débits, codage de ligne (4B/5B, PAM4). Elle ne connaît **aucune adresse** : elle voit passer un flux de bits, point. Équipements : câble, répéteur, hub, transceiver SFP+.

**Couche 2 — Liaison de données. « Sur ce câble partagé, à qui je parle, et ma trame est-elle intacte ? »**
Adressage **local** par MAC (48 bits). Délimite les trames dans le flux de bits, détecte les erreurs (FCS, CRC-32), gère l'accès au médium (CSMA/CD historiquement, aujourd'hui full-duplex commuté). Portée : **un seul saut**, d'une carte réseau à la carte réseau voisine — une MAC ne traverse jamais un routeur. Équipements : switch, bridge, NIC, point d'accès Wi-Fi.

**Couche 3 — Réseau. « Comment atteindre une machine qui n'est pas sur mon câble ? »**
Adressage **global et hiérarchique** (IP). Routage : à chaque routeur, décider par où sortir. Fragmentation si le lien suivant est trop étroit. Non fiable et sans connexion : IP fait « au mieux » et n'a aucune mémoire. Équipements : routeur, switch L3.

**Couche 4 — Transport. « Comment livrer à la bonne application, et garantir que rien ne manque ? »**
Multiplexage par **numéro de port** (16 bits). Première couche **de bout en bout** : les routeurs intermédiaires ne la lisent pas (en théorie — cf. §10). TCP y ajoute fiabilité, ordre, contrôle de flux et de congestion. UDP n'ajoute rien.

**Couche 5 — Session. « Comment structurer un dialogue long ? »**
Ouverture, synchronisation, points de reprise, fermeture ordonnée. Dans TCP/IP c'est absorbé par TCP et par l'application. Peu de protocoles purs ici : RPC, SOCKS, NetBIOS, PPTP.

**Couche 6 — Présentation. « Comment être sûr que les deux machines interprètent les octets pareil ? »**
Sérialisation, encodage de caractères, compression, chiffrement : ASN.1/BER, UTF-8, JPEG, et par convention TLS.

**Couche 7 — Application. « Que veut dire ce message ? »**
HTTP, DNS, SMTP, FTP, SSH, protocole *wire* de Kafka, protocole PostgreSQL. Attention : **ton programme n'est pas la couche 7** — le protocole qu'il parle l'est.

> ⚠️ **PIÈGE** — Beaucoup disent « mon application est en couche 7 ». Non : Firefox n'est pas la couche 7, **HTTP** est la couche 7. Le navigateur est un utilisateur de la couche 7. En entretien, formule : « la couche 7 définit la sémantique des messages échangés ».

> ❓ **RETIENS ÇA** — *Quelle est la première couche de bout en bout (end-to-end) ?*
> <details><summary>▸ réponse</summary>
>
> La **couche 4 (transport)**. Les couches 1-2 sont de saut en saut (*hop-by-hop*), la couche 3 est routée saut par saut même si l'adresse est globale. Seule la couche 4 dialogue directement avec son homologue distant sans intervention des routeurs intermédiaires.
> </details>

> ❓ **RETIENS ÇA** — *Sur combien de bits une adresse MAC, et sur combien de bits une adresse IPv4 ?*
> <details><summary>▸ réponse</summary>
>
> MAC = **48 bits** (6 octets, notés en hexa `aa:bb:cc:dd:ee:ff`, les 3 premiers octets = OUI du constructeur). IPv4 = **32 bits** (4 octets). IPv6 = **128 bits**.
> </details>

---

## 3. Le modèle TCP/IP : 4 couches, celui qui tourne vraiment

OSI décrit. TCP/IP fonctionne. Le modèle TCP/IP (aussi appelé modèle DoD, ou modèle Internet, RFC 1122) a **4 couches**.

```
      MODÈLE OSI (7)              MODÈLE TCP/IP (4)
 7 | Application  |  \
 6 | Présentation |   >------>  | APPLICATION   |  HTTP DNS SMTP SSH Kafka PG
 5 | Session      |  /
 4 | Transport    |  ------->   | TRANSPORT     |  TCP UDP SCTP
 3 | Réseau       |  ------->   | INTERNET      |  IP ICMP ARP*
 2 | Liaison      |  \
                     >------>   | ACCÈS RÉSEAU  |  Ethernet Wi-Fi PPP fibre
 1 | Physique     |  /
```

**Les correspondances à connaître par cœur :**

| TCP/IP | OSI équivalent | Nom alternatif |
|---|---|---|
| Application | 5 + 6 + 7 | — |
| Transport | 4 | Host-to-host |
| Internet | 3 | Réseau |
| Accès réseau | 1 + 2 | Liaison / Link |

> 🧠 **MÉMO** — TCP/IP = **« 1-1-1-3 »** en partant du bas : la couche basse regroupe **2** couches OSI (1+2), puis 1 pour 1 (Internet↔3, Transport↔4), puis la couche haute regroupe **3** couches OSI (5+6+7). Le compte tombe : 2+1+1+3 = 7.

> ⚠️ **PIÈGE** — On voit parfois un « modèle TCP/IP à 5 couches » qui sépare physique et liaison. Ce n'est pas faux, c'est un modèle pédagogique hybride. Si on te pose la question en entretien : **le modèle TCP/IP de référence (RFC 1122) en a 4**. Mentionne la variante à 5 pour montrer que tu le sais.

> ❓ **RETIENS ÇA** — *Quelles couches OSI sont fusionnées dans la couche Application de TCP/IP ?*
> <details><summary>▸ réponse</summary>
>
> Les couches **5 (session), 6 (présentation) et 7 (application)**.
> </details>

### 3.1 Le sablier

```
   HTTP  DNS  SMTP  SSH  Kafka  gRPC   <- des dizaines d'applications
        \    \   |   |   /    /
              TCP   UDP  SCTP          <- quelques transports
                 \   |   /
                 IPv4 / IPv6           <- LE goulot : une seule couche 3
                 /   |   \
   Ethernet  Wi-Fi  4G/5G  PPP  fibre  <- des dizaines de liens
```

Principe **« IP over everything, everything over IP »**. Le goulot est volontaire : en imposant **un seul** protocole de couche 3, on garantit que n'importe quelle application marche sur n'importe quel lien. C'est la raison technique pour laquelle Internet a gagné.

---

## 4. Les PDU : le mot juste pour chaque couche

**PDU** = *Protocol Data Unit* = l'unité de données manipulée à une couche donnée. Utiliser le mauvais mot en entretien, c'est se griller en 2 secondes.

| Couche OSI | Couche TCP/IP | PDU | En anglais | Ce qu'elle contient |
|---|---|---|---|---|
| 7-6-5 | Application | **Données** (message) | data / message | Le contenu utile |
| 4 | Transport | **Segment** (TCP) / **Datagramme** (UDP) | segment / datagram | En-tête TCP ou UDP + données |
| 3 | Internet | **Paquet** (datagramme IP) | packet | En-tête IP + segment |
| 2 | Accès réseau | **Trame** | frame | En-tête Ethernet + paquet + FCS |
| 1 | Accès réseau | **Bit** (symbole) | bit | Signal physique |

> 🧠 **MÉMO** — De bas en haut : **B-T-P-S-D** → **« Bien Traiter Petits Segments de Données »**.
> Ou l'image : le **B**it devient une **T**rame, qui contient un **P**aquet, qui contient un **S**egment, qui contient des **D**onnées. Poupées russes, du plus gros contenant au plus petit contenu.

> ⚠️ **PIÈGE** — Le mot « paquet » est utilisé à tort et à travers dans le langage courant (« j'ai capturé des paquets »). Techniquement, **tcpdump capture des trames**. Dans un contexte formel, garde la rigueur : segment = L4 TCP, datagramme = L4 UDP **ou** L3 IP (ambiguïté historique — précise « datagramme IP » ou « datagramme UDP »), paquet = L3, trame = L2.

> ❓ **RETIENS ÇA** — *Quel est le nom de la PDU de couche 4 en UDP ?*
> <details><summary>▸ réponse</summary>
>
> Un **datagramme** (UDP datagram). En TCP c'est un **segment**. Le mot « segment » implique une découpe d'un flux continu — ce que fait TCP et pas UDP.
> </details>

---

## 5. L'encapsulation : le cœur du module

### 5.1 Le principe

Chaque couche, en descendant, **ajoute son propre en-tête** devant les données qu'elle reçoit de la couche du dessus. Elle traite tout ce qui vient d'en haut comme une **charge utile opaque** (*payload*) qu'elle ne lit pas.

En remontant, chaque couche **retire son en-tête**, le lit pour savoir quoi faire, et passe le reste à la couche du dessus : c'est la **décapsulation**.

> **Analogie — les poupées russes / le colis.**
> Tu mets un bijou (données) dans une boîte étiquetée « service bijouterie, comptoir 443 » (en-tête TCP). Cette boîte va dans un carton étiqueté « 93.184.216.34 » (en-tête IP). Ce carton monte dans une palette étiquetée « camion de gauche » (en-tête Ethernet). Chaque manutentionnaire ne lit **que son étiquette** et n'ouvre jamais le niveau du dessous. À l'arrivée, on déballe dans l'ordre inverse.

### 5.2 Le schéma à savoir redessiner

```
APPLICATION   +--------------------------------------------------+
              |                DATA (ex: 1460 o)                 |
              +--------------------------------------------------+
                                    |
                        + en-tête TCP (20 o min)
                                    v
TRANSPORT     +--------+-----------------------------------------+
              | TCP hdr|                DATA                     |   = SEGMENT
              |  20 o  |              1460 o                     |     1480 o
              +--------+-----------------------------------------+
                                    |
                        + en-tête IP (20 o min)
                                    v
INTERNET      +-------+--------+----------------------------------+
              | IP hdr|TCP hdr |            DATA                  |  = PAQUET
              | 20 o  | 20 o   |           1460 o                 |    1500 o
              +-------+--------+----------------------------------+
                                    |
                   + en-tête Ethernet (14 o) + FCS (4 o)
                                    v
ACCÈS RÉSEAU  +------+-------+-------+--------------------+-----+
              |Eth   |IP hdr |TCP hdr|       DATA         | FCS |  = TRAME
              |14 o  |20 o   |20 o   |      1460 o        | 4 o |    1518 o
              +------+-------+-------+--------------------+-----+
                                    |
                       + préambule 8 o + IFG 12 o
                                    v
PHYSIQUE      1010111010101110101110101010111000101...  = BITS
              (1538 octets réellement occupés sur le fil)
```

**Les chiffres de ce schéma sont à connaître par cœur.** Ce sont eux qui reviennent en entretien et en debug.

| Élément | Taille | Note |
|---|---|---|
| En-tête Ethernet II | **14 o** | 6 MAC dst + 6 MAC src + 2 EtherType |
| Balise VLAN 802.1Q | **+4 o** | Optionnelle, insérée après les MAC |
| En-tête IPv4 | **20 o** min, 60 o max | 20 si pas d'options (cas normal) |
| En-tête IPv6 | **40 o** fixe | Pas d'options dans l'en-tête de base |
| En-tête TCP | **20 o** min, 60 o max | 20 + options (timestamps, SACK, window scale) |
| En-tête UDP | **8 o** fixe | Il n'y a rien à ajouter |
| FCS (CRC-32) | **4 o** | En **queue** de trame, pas en tête |
| Préambule + SFD / IFG | **8 o** / **12 o** | Synchronisation et silence, hors trame |
| Charge utile Ethernet | 46 à **1500 o** | 46 mini (bourrage sinon) |
| Trame Ethernet complète | 64 à **1518 o** | 1522 avec VLAN |

> 🧠 **MÉMO** — **14 / 20 / 20 / 8**. Quatre nombres, dans l'ordre où tu les rencontres en descendant : **Ethernet 14, IP 20, TCP 20, UDP 8**. Récite-les comme un code PIN. Et le total qui compte : **14+20+20 = 54 octets** d'en-têtes pour transporter le moindre octet en TCP/IPv4 sur Ethernet.

> ❓ **RETIENS ÇA** — *Taille d'un en-tête TCP minimal, d'un en-tête UDP, d'un en-tête IPv4 minimal, d'un en-tête Ethernet II ?*
> <details><summary>▸ réponse</summary>
>
> TCP **20 o**, UDP **8 o**, IPv4 **20 o**, Ethernet II **14 o**. (+ FCS 4 o en fin de trame.)
> </details>

> ❓ **RETIENS ÇA** — *Pourquoi une trame Ethernet fait-elle au minimum 64 octets ?*
> <details><summary>▸ réponse</summary>
>
> Héritage de la détection de collision en half-duplex : une trame devait durer assez longtemps (**slot time** de 512 bits = 64 octets) pour que l'émetteur détecte une collision avant d'avoir fini d'émettre. Si la charge utile fait moins de 46 octets, on ajoute du **bourrage** (padding).
> </details>

### 5.3 La décapsulation : comment chaque couche sait à qui passer la suite

C'est LE mécanisme que les débutants ne voient pas. À chaque couche, un **champ de démultiplexage** dit à qui remettre la charge utile.

```
  Trame arrive
      v
  [ Ethernet ] -- EtherType 0x0800 -> IPv4 | 0x86DD -> IPv6
                             0x0806 -> ARP | 0x8100 -> VLAN (relire l'EtherType)
      v
  [   IPv4   ] -- Protocol 6 -> TCP | 17 -> UDP | 1 -> ICMP
                           47 -> GRE | 50 -> ESP (IPsec)
      v
  [   TCP    ] -- Port dst 5432 -> postgres | 9092 -> kafka | 443 -> nginx
```

**Les trois clés de démultiplexage à connaître :**

| Couche | Champ | Valeurs à connaître |
|---|---|---|
| 2 → 3 | `EtherType` (2 o) | `0x0800` IPv4, `0x0806` ARP, `0x86DD` IPv6, `0x8100` VLAN |
| 3 → 4 | `Protocol` (1 o) | `1` ICMP, `6` TCP, `17` UDP, `41` IPv6-in-IPv4, `47` GRE, `50` ESP, `58` ICMPv6, `89` OSPF, `132` SCTP |
| 4 → 7 | Port destination (2 o) | cf. §7.3 et la cheatsheet |

> 🧠 **MÉMO** — Protocol IP : **1 = ICMP** (le plus simple, le numéro 1), **6 = TCP**, **17 = UDP**. Astuce : **6 < 17** comme **TCP est plus vieux qu'UDP dans ton apprentissage**, et 6 + 17 = 23 = le port de telnet. C'est arbitraire mais ça accroche.

> ⚠️ **PIÈGE** — Le numéro **6** dans « Protocol = 6 » n'a **rien à voir** avec la couche 6 OSI. C'est un numéro IANA arbitraire. De même, le port 443 n'a rien à voir avec une couche. Ne cherche pas de sens là où il n'y en a pas.

> ❓ **RETIENS ÇA** — *Quel champ de l'en-tête IPv4 indique que la charge utile est du TCP, et quelle est sa valeur ?*
> <details><summary>▸ réponse</summary>
>
> Le champ **`Protocol`** (1 octet, 10e octet de l'en-tête), valeur **6**. UDP = 17, ICMP = 1.
> </details>

---

## 6. Anatomie des en-têtes réels

Ces schémas sont **faits pour être redessinés à la main**. Fais-le trois fois de mémoire, ça suffit.

### 6.1 Trame Ethernet II

```
 <---- hors trame ----> <---------------- TRAME (64 à 1518 o) -------------------->
+----------+----+--------+--------+------+--------------------------+-----+
|Préambule |SFD | MAC    | MAC    |Ether |        Charge utile      | FCS |
|  7 o     |1 o | dest   | source |Type  |        46 à 1500 o       | 4 o |
|          |    | 6 o    | 6 o    | 2 o  |                          |     |
+----------+----+--------+--------+------+--------------------------+-----+
                 \______________________/
                    en-tête = 14 octets
```

- **MAC destination en premier** : le switch peut décider où commuter dès les 6 premiers octets lus, sans attendre la fin. Optimisation *cut-through*.
- `ff:ff:ff:ff:ff:ff` = **broadcast**. Bit de poids faible du premier octet à 1 = **multicast**.
- **FCS** = CRC-32 sur toute la trame. Si le CRC est faux, la trame est **jetée silencieusement** — pas de retransmission à ce niveau sur Ethernet.

### 6.2 En-tête IPv4 (20 octets sans options)

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-------+-------+---------------+-------------------------------+
|Version|  IHL  |DSCP       |ECN|        Total Length           |  4 o
+-------+-------+---------------+-----+-------------------------+
|         Identification        |Flags|    Fragment Offset      |  8 o
+---------------+---------------+-----+-------------------------+
|      TTL      |   Protocol    |        Header Checksum        | 12 o
+---------------+---------------+-------------------------------+
|                     Adresse SOURCE (32 bits)                  | 16 o
+---------------------------------------------------------------+
|                   Adresse DESTINATION (32 bits)               | 20 o
+---------------------------------------------------------------+
|                   Options (0 à 40 o, rare)                    |
+---------------------------------------------------------------+
       Flags : bit 0 = réservé (0) | bit 1 = DF | bit 2 = MF
```

Les champs qui te serviront vraiment :

| Champ | Taille | À quoi ça sert en pratique |
|---|---|---|
| `Version` | 4 bits | 4 ou 6 |
| `IHL` | 4 bits | Longueur de l'en-tête **en mots de 32 bits**. 5 = 20 octets. Max 15 = 60 octets. |
| `Total Length` | 16 bits | Taille du paquet **entier** (en-tête + données). Max 65535. |
| `Identification` | 16 bits | Identifiant du datagramme d'origine, pour réassembler les fragments. |
| `DF` | 1 bit | *Don't Fragment*. Indispensable au PMTU discovery. |
| `MF` | 1 bit | *More Fragments*. À 1 sur tous les fragments sauf le dernier. |
| `Fragment Offset` | 13 bits | Position du fragment, **en unités de 8 octets**. |
| `TTL` | 8 bits | Décrémenté de 1 par routeur. À 0 → paquet jeté + ICMP Time Exceeded. |
| `Protocol` | 8 bits | 6 = TCP, 17 = UDP, 1 = ICMP. |
| `Header Checksum` | 16 bits | Sur **l'en-tête seulement**. Recalculé à chaque routeur (car TTL change). |

> ⚠️ **PIÈGE** — Le checksum IPv4 ne couvre **que l'en-tête**, jamais les données. La protection des données est déléguée à TCP/UDP (checksum L4) et à Ethernet (FCS L2). En **IPv6, le checksum d'en-tête n'existe plus** du tout : on ne recalcule rien à chaque routeur, ce qui accélère le routage.

> 🧠 **MÉMO — TTL** : valeurs initiales par défaut, **Linux/macOS 64, Windows 128, routeurs Cisco 255**. Un `ping` qui revient avec TTL 57 : 64 − 57 = **7 sauts** depuis un hôte Linux. C'est un test mental utile pour deviner l'OS distant et compter les sauts sans traceroute.

> ❓ **RETIENS ÇA** — *Le champ Fragment Offset est exprimé dans quelle unité ?*
> <details><summary>▸ réponse</summary>
>
> En **unités de 8 octets**. C'est pourquoi la taille de chaque fragment (sauf le dernier) doit être un **multiple de 8**. 13 bits × 8 = 65 528 octets adressables, cohérent avec le Total Length max de 65 535.
> </details>

### 6.3 En-tête TCP (20 octets sans options)

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-------------------------------+-------------------------------+
|         Port SOURCE           |      Port DESTINATION          |  4 o
+-------------------------------+-------------------------------+
|                   Numéro de séquence (32 bits)                |  8 o
+---------------------------------------------------------------+
|                  Numéro d'acquittement (32 bits)              | 12 o
+-------+-------+---------------+-------------------------------+
| Data  | Rsvd  |C E U A P R S F|          Window Size          | 16 o
| Offset|       |W C R C S S Y I|                               |
|       |       |R E G K H T N N|                               |
+-------+-------+---------------+-------------------------------+
|          Checksum             |       Urgent Pointer          | 20 o
+-------------------------------+-------------------------------+
|            Options (0 à 40 o : MSS, WScale, SACK, TS)         |
+---------------------------------------------------------------+
```

- **Data Offset** (4 bits) : longueur de l'en-tête TCP en mots de 32 bits. 5 = 20 octets.
- **Window Size** (16 bits) : combien d'octets le récepteur accepte encore. Max brut = **65 535**. L'option *Window Scale* le multiplie jusqu'à **1 Go** — sans elle, pas de haut débit longue distance (cf. exercice §8.3).
- Flags dans l'ordre : **CWR, ECE, URG, ACK, PSH, RST, SYN, FIN**.

### 6.4 En-tête UDP (8 octets, c'est tout)

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-------------------------------+-------------------------------+
|         Port SOURCE           |     Port DESTINATION           |  4 o
+-------------------------------+-------------------------------+
|      Longueur (en-tête+data)  |          Checksum             |  8 o
+-------------------------------+-------------------------------+
```

Quatre champs de 2 octets. Rien d'autre. Pas de numéro de séquence, pas d'acquittement, pas de fenêtre : **UDP ne fait que du multiplexage par port + une détection d'erreur optionnelle**. Tout le reste est à la charge de l'application.

> ❓ **RETIENS ÇA** — *Qu'apporte UDP par rapport à IP nu ?*
> <details><summary>▸ réponse</summary>
>
> Deux choses seulement : le **multiplexage par ports** (16 bits src + 16 bits dst) et un **checksum couvrant les données** (optionnel en IPv4 — un checksum à 0 signifie « non calculé » —, obligatoire en IPv6).
> </details>

> ⚠️ **PIÈGE** — Le checksum TCP et UDP est calculé sur un **pseudo-en-tête** qui inclut les adresses IP source et destination, le numéro de protocole et la longueur. C'est une violation assumée du modèle en couches : la couche 4 lit des champs de la couche 3. Conséquence pratique : **un NAT doit recalculer le checksum TCP/UDP** quand il réécrit l'adresse IP. C'est un excellent exemple à sortir en entretien quand on te demande « où le modèle en couches ne tient pas ».

---

## 7. Les équipements, couche par couche

### 7.1 Le tableau de référence

| Couche | Équipement | Décision basée sur | Domaine de collision | Domaine de broadcast |
|---|---|---|---|---|
| 1 | **Hub / répéteur** | rien, il répète le signal | **1 seul** (partagé) | 1 seul |
| 2 | **Switch / bridge** | adresse **MAC** destination | **1 par port** | 1 par VLAN |
| 3 | **Routeur / switch L3** | adresse **IP** destination | 1 par port | **1 par interface** |
| 4 | **Pare-feu stateful / NAT / NLB** | IP + **port** + état de connexion | — | — |
| 7 | **Reverse proxy / ALB / WAF / API GW** | URL, en-têtes HTTP, SNI, cookie | — | — |

> 🧠 **MÉMO — « Le switch coupe les collisions, le routeur coupe les broadcasts. »**
> Une phrase, deux faits. C'est la question posée dans 1 entretien réseau sur 3.

### 7.2 Ce que fait chaque équipement, concrètement

**Hub (L1)** — obsolète. Il recopie le signal reçu sur un port vers tous les autres ports. Tout le monde entend tout, tout le monde entre en collision. Historique, mais utile pour comprendre pourquoi le switch a gagné.

**Switch (L2)** — il maintient une **table CAM** (dite aussi table MAC) : `MAC → port`, apprise en observant les **MAC sources** des trames entrantes. Vieillissement typique **300 s** (5 min). Trois comportements :
- MAC destination **connue** → *forwarding* vers le bon port uniquement.
- MAC destination **inconnue** → *flooding* sur tous les ports sauf celui d'origine (*unknown unicast flooding*).
- MAC destination = broadcast/multicast → diffusion.

**Routeur (L3)** — il maintient une **table de routage** : `préfixe réseau → interface de sortie + prochain saut`. Pour chaque paquet :
1. décapsule la trame Ethernet (**l'en-tête L2 est jeté**),
2. lit l'IP destination, cherche le préfixe le plus long qui correspond (*longest prefix match*),
3. **décrémente le TTL**, recalcule le checksum IP,
4. **réencapsule dans une NOUVELLE trame Ethernet** avec de nouvelles MAC source/destination,
5. émet.

**Pare-feu L4 / NAT / load balancer réseau (L4)** — il lit IP + ports + flags TCP et maintient une **table d'états** (`5-tuple : IP src, port src, IP dst, port dst, protocole`). Il ne comprend rien au contenu. AWS NLB, `iptables`, un security group : L4.

**Reverse proxy / load balancer applicatif (L7)** — il **termine** la connexion TCP côté client, lit le HTTP, puis **ouvre une autre connexion TCP** vers le backend. Il peut router sur `/api/*`, sur un cookie, sur le `Host:`. AWS ALB, nginx, Envoy, un Ingress K8s : L7. Coût : plus de latence et plus de CPU qu'un L4.

> ❓ **RETIENS ÇA** — *Qu'est-ce qui change et qu'est-ce qui ne change pas quand un paquet traverse un routeur ?*
> <details><summary>▸ réponse</summary>
>
> **Change** : les adresses MAC source et destination (nouvelle trame), le TTL (−1), le checksum d'en-tête IP.
> **Ne change pas** : les adresses IP source et destination (sauf NAT), les ports, les données.
> </details>

> ❓ **RETIENS ÇA** — *Différence fondamentale entre un load balancer L4 et un load balancer L7 ?*
> <details><summary>▸ réponse</summary>
>
> Le **L4** relaie un flux TCP/UDP en se basant uniquement sur IP+port : il ne lit pas le contenu, une seule connexion de bout en bout (ou un simple relais d'octets). Le **L7 termine la connexion TCP**, lit et comprend le protocole applicatif (HTTP), et en ouvre une nouvelle vers le backend : routage par URL/en-tête/cookie possible, mais latence et CPU en plus.
> </details>

### 7.3 Les ports à connaître par cœur

Les plages (IANA) :

| Plage | Nom | Usage |
|---|---|---|
| 0 – 1023 | **Well-known** | Services système, root requis sous Linux pour écouter |
| 1024 – 49151 | **Registered** | Applications enregistrées (PostgreSQL 5432, etc.) |
| 49152 – 65535 | **Dynamic / ephemeral** | Ports source choisis par le client |

> ⚠️ **PIÈGE** — Sous **Linux**, la plage éphémère réelle par défaut n'est **pas** 49152-65535 mais **32768-60999** (`sysctl net.ipv4.ip_local_port_range`). C'est ~28 000 ports : au-delà, une machine qui ouvre trop de connexions **vers la même destination** épuise ses ports source (`EADDRNOTAVAIL`). Ça arrive vraiment sur les workers d'un pipeline qui martèlent une seule base.

Les ports indispensables (liste complète dans la cheatsheet) :

| Port | Protocole | Service |
|---|---|---|
| 22 / 80 | TCP | SSH / HTTP |
| 53 | **UDP** et TCP | DNS |
| 443 | TCP **et UDP** | HTTPS (TCP) / QUIC-HTTP3 (UDP) |
| 123 | UDP | NTP |
| 3306 / 5432 | TCP | MySQL / PostgreSQL |
| 6379 / 27017 | TCP | Redis / MongoDB |
| 9092 / 9200 | TCP | Kafka broker / Elasticsearch |
| 6443 / 2379 | TCP | Kubernetes API server / etcd |
| 4789 | UDP | VXLAN |

---

## 8. MTU, MSS et fragmentation

C'est **la** section qui te fera gagner des heures de debug dans ton poste. Lis-la deux fois.

### 8.1 Le problème

Un lien physique ne transporte pas des trames de taille infinie. Chaque technologie fixe une taille maximale de **charge utile** transportable dans une trame : c'est le **MTU** (*Maximum Transmission Unit*).

```
   +------+------------------------------------------+-----+
   | Eth  |         PAQUET IP  <= MTU                | FCS |
   | 14 o |         (1500 o max sur Ethernet)        | 4 o |
   +------+------------------------------------------+-----+
          |<----------------- MTU ------------------>|
   Le MTU = taille max du PAQUET IP (en-tête IP compris).
   Il N'INCLUT PAS l'en-tête Ethernet ni le FCS.
```

Valeurs de MTU à connaître :

| Contexte | MTU | Note |
|---|---|---|
| Ethernet standard | **1500** | La valeur de référence |
| Ethernet jumbo frames | **9000** | LAN datacenter, si tout le chemin le supporte |
| AWS — dans un VPC / via Internet Gateway | **9001** / **1500** | Jumbo dedans, 1500 dès que ça sort |
| GCP — VPC par défaut | **1460** | Configurable jusqu'à 8896 |
| PPPoE (ADSL) | **1492** | 1500 − 8 o d'en-tête PPPoE |
| Overlay VXLAN sur MTU 1500 | **1450** | 1500 − 50 o d'encapsulation |
| WireGuard sur MTU 1500 | **1420** | 80 o d'overhead |
| IPv4 — minimum garanti | **68** | Tout lien IPv4 doit le supporter |
| IPv6 — minimum obligatoire | **1280** | Tout lien IPv6 doit le supporter |

### 8.2 MSS : la traduction du MTU pour TCP

Le **MSS** (*Maximum Segment Size*) est la taille maximale des **données applicatives** dans un segment TCP.

```
   MSS = MTU − en-tête IP − en-tête TCP

   IPv4 classique :   MSS = 1500 − 20 − 20 = 1460 octets
   IPv6 classique :   MSS = 1500 − 40 − 20 = 1440 octets
   VXLAN (IPv4)   :   MSS = 1450 − 20 − 20 = 1410 octets
   Jumbo 9000     :   MSS = 9000 − 20 − 20 = 8960 octets
```

Le MSS est **annoncé dans les options TCP du SYN** par chaque côté. Chacun annonce le sien ; chacun émet en respectant le MSS annoncé par l'autre. Ce n'est pas négocié, c'est déclaré.

> 🧠 **MÉMO** — **1500 − 40 = 1460.** Ethernet moins « vingt plus vingt ». Le nombre **1460** doit sortir instantanément. Et **1448** est le MSS que tu verras le plus souvent en vrai : 1460 − 12 octets d'option *TCP timestamps*, activée par défaut sous Linux.

> ⚠️ **PIÈGE** — Confusion classique en entretien : « MTU = 1500 donc je peux envoyer 1500 octets de données ». Non. Tu peux envoyer **1460** octets de données applicatives. Le MTU est la limite du **paquet IP**, pas de la charge utile applicative, et pas de la trame (qui fait 1518).

> ❓ **RETIENS ÇA** — *Le MTU inclut-il l'en-tête Ethernet ?*
> <details><summary>▸ réponse</summary>
>
> **Non.** Le MTU est la taille max du paquet IP (en-tête IP compris) transporté dans la trame. Sur Ethernet, MTU 1500 → trame de 1518 octets (14 + 1500 + 4), et 1538 octets réellement occupés sur le fil avec préambule et IFG.
> </details>

### 8.3 Fragmentation IP — exercice intégralement corrigé

**Énoncé.** Une machine émet un datagramme IPv4 de **4000 octets au total** (en-tête IP de 20 octets inclus). Il doit traverser un lien de **MTU 1500**, avec le bit DF à 0. Combien de fragments, de quelles tailles, avec quels offsets et quels flags ?

**Étape 1 — isoler la charge utile à fragmenter.**
Total 4000 o − en-tête IP 20 o = **3980 octets** de données à répartir.
(Attention : le contenu inclut l'en-tête TCP, mais IP s'en fiche — pour IP c'est de la donnée opaque. Seul le **premier** fragment contiendra l'en-tête TCP.)

**Étape 2 — taille max de données par fragment.**
Chaque fragment est un paquet IP complet, donc chacun porte son propre en-tête de 20 o.
1500 − 20 = **1480 octets** de données maximum par fragment.

**Étape 3 — contrainte du multiple de 8.**
L'offset s'exprime en unités de 8 octets, donc la taille de données de chaque fragment sauf le dernier doit être un multiple de 8.
1480 ÷ 8 = 185 → **1480 est bien un multiple de 8**. Parfait, on garde 1480.

**Étape 4 — répartition.**
3980 ÷ 1480 = 2 avec un reste de 3980 − 2×1480 = 3980 − 2960 = **1020**.
→ **3 fragments** : 1480 + 1480 + 1020 = 3980 ✔

**Étape 5 — offsets (en unités de 8 octets).**
- Fragment 1 : données 0 → 1479, offset = 0 ÷ 8 = **0**
- Fragment 2 : données 1480 → 2959, offset = 1480 ÷ 8 = **185**
- Fragment 3 : données 2960 → 3979, offset = 2960 ÷ 8 = **370**

**Étape 6 — tableau final.**

| # | Total Length | Données | Offset (unités de 8) | MF | Identification |
|---|---|---|---|---|---|
| 1 | 1500 | 1480 | 0 | **1** | X |
| 2 | 1500 | 1480 | 185 | **1** | X |
| 3 | 1040 | 1020 | 370 | **0** | X |

Vérification : 1480 + 1480 + 1020 = 3980, et 3980 + 20 = 4000 ✔. Les trois fragments portent **la même Identification** : c'est ce qui permet au destinataire de les regrouper.

> ⚠️ **PIÈGE** — Le réassemblage se fait **uniquement à la destination finale**, jamais sur un routeur intermédiaire. Un routeur qui reçoit un fragment le route comme un paquet normal. Conséquence : si **un seul** fragment se perd, **tout** le datagramme est perdu, et TCP retransmet l'intégralité. La fragmentation multiplie donc l'impact d'une perte — c'est pour ça qu'on la fuit.

### 8.4 PMTU Discovery et le trou noir

Le mécanisme moderne évite la fragmentation : on met **DF=1** sur tout et on découvre le MTU minimal du chemin.

```
  Machine A                Routeur R1              Routeur R2         Machine B
  MTU 1500                 sortie MTU 1400
     |                          |                       |                 |
     |--- paquet 1500, DF=1 --->|                       |                 |
     |                          | 1500 > 1400 et DF=1   |                 |
     |                          | -> je JETTE            |                 |
     |<-- ICMP type 3 code 4 ---|                       |                 |
     |    "Fragmentation Needed, Next-Hop MTU = 1400"   |                 |
     |                          |                       |                 |
     | (A mémorise PMTU=1400 pour cette destination)     |                 |
     |--- paquet 1400, DF=1 --->|---------------------->|---------------->|
```

**Le message clé : ICMP type 3 code 4 (*Fragmentation Needed and DF set*), avec le MTU du prochain saut.** En IPv6 : **ICMPv6 type 2 (*Packet Too Big*)**, car les routeurs IPv6 ne fragmentent **jamais**.

> ⚠️ **PIÈGE — LE BUG QUE TU RENCONTRERAS EN VRAI.** Beaucoup d'admins bloquent tout l'ICMP « par sécurité ». Résultat : le message « Fragmentation Needed » n'arrive jamais à l'émetteur. Il continue d'envoyer du 1500 avec DF=1, tout est jeté silencieusement, et **rien ne revient**. C'est le **PMTU black hole**.
> **Signature clinique, à reconnaître les yeux fermés :** le *handshake* TCP marche, les petites requêtes marchent, `ping` marche, mais **dès qu'un gros transfert commence, la connexion se fige** puis casse en timeout. Un `SELECT 1` passe, un `SELECT *` bloque.
> **Test en une commande :**
> ```bash
> ping -M do -s 1472 <destination>   # 1472 + 8 (ICMP) + 20 (IP) = 1500
> ping -M do -s 1372 <destination>   # teste 1400
> ```
> Le plus grand `-s` qui passe + 28 = ton PMTU réel.
> **Correctif classique** : le *MSS clamping* sur le routeur/pare-feu :
> ```bash
> iptables -t mangle -A FORWARD -p tcp --tcp-flags SYN,RST SYN \
>          -j TCPMSS --clamp-mss-to-pmtu
> ```

> ❓ **RETIENS ÇA** — *Quel message ICMP porte l'information de PMTU en IPv4, et quel est son équivalent IPv6 ?*
> <details><summary>▸ réponse</summary>
>
> IPv4 : **ICMP type 3 (Destination Unreachable), code 4 (Fragmentation Needed and DF set)**, avec le champ Next-Hop MTU.
> IPv6 : **ICMPv6 type 2 (Packet Too Big)**. Bloquer l'ICMP casse les deux.
> </details>

> ❓ **RETIENS ÇA** — *Un routeur IPv6 peut-il fragmenter un paquet trop gros ?*
> <details><summary>▸ réponse</summary>
>
> **Non, jamais.** Seule la source peut fragmenter en IPv6 (via un en-tête d'extension Fragment). Le routeur jette le paquet et renvoie ICMPv6 « Packet Too Big ». C'est un choix de conception pour accélérer le routage.
> </details>

### 8.5 Exercice corrigé — l'overhead réel d'un pipeline

**Énoncé.** Ton producteur Kafka envoie des messages de **100 octets** un par un, sans batching, sur Ethernet MTU 1500. Quelle fraction de la bande passante physique transporte réellement de la donnée utile ?

**Correction pas à pas.**
1. Données : 100 o
2. + en-tête TCP : 100 + 20 = 120 o (on ignore les options pour simplifier)
3. + en-tête IP : 120 + 20 = 140 o
4. + Ethernet (14) + FCS (4) : 140 + 18 = **158 o de trame**
5. Or la trame minimale Ethernet est de 64 o : 158 > 64, donc pas de bourrage.
6. + préambule/SFD (8) + IFG (12) : 158 + 20 = **178 octets réellement occupés sur le fil**

**Efficacité = 100 / 178 = 56 %.** Presque la moitié de ton lien transporte des en-têtes.

**Et avec du batching à 1460 octets de données ?**
1460 / (1460 + 20 + 20 + 18 + 20) = 1460 / 1538 = **94,9 %**.

**Conclusion opérationnelle** : `linger.ms` et `batch.size` chez Kafka, `maxRecordsPerBatch` chez Spark, `COPY` plutôt qu'`INSERT` unitaire — ce ne sont pas des micro-optimisations. C'est un facteur **×1,7 sur le débit utile**, avant même de parler du coût CPU par paquet (qui, lui, est bien plus punitif : le noyau paie un coût quasi fixe par paquet, pas par octet).

---

## 9. Le trajet complet d'un paquet entre deux sous-réseaux

C'est **l'exercice de synthèse** du module. Si tu sais le raconter de mémoire, tu as compris l'encapsulation.

### 9.1 La topologie

```
  +--------------+          +----------------------+          +--------------+
  |   MACHINE A  |          |       ROUTEUR R      |          |   MACHINE B  |
  |              |          |                      |          |              |
  | IP 10.0.1.10 |          | eth0: 10.0.1.1       |          | IP 10.0.2.20 |
  | MAC AA:...:0A |=========| MAC RR:...:01        |          | MAC BB:...:14|
  |              |  Switch1 |                      | Switch2  |              |
  | GW 10.0.1.1  |          | eth1: 10.0.2.1       |=========|GW 10.0.2.1   |
  +--------------+          | MAC RR:...:02        |          +--------------+
     LAN 10.0.1.0/24        +----------------------+             LAN 10.0.2.0/24
```

A veut ouvrir une connexion TCP vers B sur le port 5432 (PostgreSQL).

### 9.2 Étape 0 — A décide : local ou distant ?

A applique le masque de son propre réseau à l'IP destination :

```
  Mon IP        : 10.0.1.10  /24  ->  mon réseau  : 10.0.1.0
  IP destination: 10.0.2.20       ->  son réseau  : 10.0.2.0
                                       10.0.1.0 != 10.0.2.0
  => DESTINATION HORS DE MON RÉSEAU. Je dois passer par ma passerelle.
```

**C'est la décision fondatrice.** Elle détermine à quelle MAC la trame sera adressée.

### 9.3 Étape 1 — A ne connaît pas la MAC de la passerelle : ARP

A a besoin de la MAC de **10.0.1.1** (la passerelle), **pas** celle de B. Il consulte son cache ARP ; s'il est vide :

```
  A -> BROADCAST :  "Qui a 10.0.1.1 ? Réponds à AA:...:0A"
       MAC dest = ff:ff:ff:ff:ff:ff   (tout le LAN reçoit)
       EtherType = 0x0806 (ARP)

  R -> A (unicast) : "10.0.1.1, c'est moi : RR:...:01"

  A met en cache :  10.0.1.1  ->  RR:...:01   (durée ~30 s réutilisable, `ip neigh`)
```

> ⚠️ **PIÈGE** — A ne fait **jamais** d'ARP pour l'IP de B. ARP ne fonctionne que dans un **même domaine de broadcast**, et le broadcast ne traverse pas le routeur. Erreur de débutant classique en entretien.

### 9.4 Étape 2 — A construit et envoie la trame

```
  +--------------------+--------------------+--------------------------+
  | ETHERNET           | IP                 | TCP                      |
  | dst = RR:...:01    | src = 10.0.1.10    | src port = 41522         |
  |       (routeur !)  | dst = 10.0.2.20    | dst port = 5432          |
  | src = AA:...:0A    |       (B final !)  | SYN                      |
  | type = 0x0800      | TTL = 64           |                          |
  +--------------------+--------------------+--------------------------+
```

**Le point à comprendre absolument :** l'adresse **MAC** pointe vers le **prochain saut** (le routeur). L'adresse **IP** pointe vers la **destination finale** (B). Les deux ne désignent pas la même machine.

> 🧠 **MÉMO — « L'IP c'est la destination du voyage, la MAC c'est le prochain arrêt. »**
> Analogie : tu prends le train Paris→Rome avec correspondance à Milan. Ton billet final dit « Rome » (IP), mais tu montes dans le train pour « Milan » (MAC). À Milan, on te met dans un nouveau train — nouvelle MAC, même destination finale.

### 9.5 Étape 3 — Le switch 1 commute

Le switch lit la MAC destination `RR:...:01`, la trouve dans sa table CAM sur le port 5, envoie **uniquement** sur ce port. Il **ne touche à rien** : ni MAC, ni IP, ni TTL. Il est totalement transparent. Il ne décrémente rien.

### 9.6 Étape 4 — Le routeur traite

```
  1. Le FCS est vérifié -> OK. L'EN-TÊTE ETHERNET EST JETÉ.
  2. Lit IP destination = 10.0.2.20
  3. Table de routage : longest prefix match
        10.0.1.0/24  -> directement connecté, eth0
        10.0.2.0/24  -> directement connecté, eth1   <== match
        0.0.0.0/0    -> 203.0.113.1
  4. TTL : 64 -> 63.  Recalcule le checksum d'en-tête IP.
  5. La destination est directement connectée sur eth1
     -> ARP pour 10.0.2.20 (broadcast sur LAN 2) -> BB:...:14
  6. CONSTRUIT UNE NOUVELLE TRAME ETHERNET :
        MAC src = RR:...:02   (son interface eth1)
        MAC dst = BB:...:14   (B)
  7. Émet sur eth1.
```

### 9.7 Étape 5 — État des en-têtes, avant/après

```
              AVANT le routeur                APRÈS le routeur
  MAC src     AA:...:0A  (A)          -->     RR:...:02  (routeur eth1)   CHANGÉ
  MAC dst     RR:...:01  (rout. eth0) -->     BB:...:14  (B)              CHANGÉ
  IP  src     10.0.1.10                -->     10.0.1.10                  IDENTIQUE
  IP  dst     10.0.2.20                -->     10.0.2.20                  IDENTIQUE
  TTL         64                       -->     63                         −1
  chk IP      0x1a2b                   -->     0x1a2c                     RECALCULÉ
  Ports TCP   41522 -> 5432            -->     41522 -> 5432              IDENTIQUES
  Données     ...                      -->     ...                        IDENTIQUES
```

**Récite ce tableau.** C'est la question d'entretien la plus fréquente de tout le module.

### 9.8 Étape 6 — B décapsule

```
  1. NIC de B : MAC dst = la mienne -> j'accepte. FCS OK.
  2. EtherType = 0x0800 -> je remonte à IPv4.  [en-tête Ethernet retiré]
  3. IP dst = 10.0.2.20 = la mienne. Protocol = 6 -> TCP. [en-tête IP retiré]
  4. TCP : port dst = 5432 -> quel socket écoute sur 5432 ?
           -> le processus postgres.                      [en-tête TCP retiré]
  5. Les données remontent dans le buffer de réception du socket.
     read() côté application les récupère.
```

Et B répond en refaisant tout le chemin en sens inverse : nouvelle décision local/distant, nouvel ARP si besoin, etc.

> ❓ **RETIENS ÇA** — *Pourquoi A fait-il un ARP pour la passerelle et non pour la machine de destination ?*
> <details><summary>▸ réponse</summary>
>
> Parce qu'ARP est un protocole de **couche 2**, limité au **domaine de broadcast local**. La destination est sur un autre sous-réseau, donc injoignable par broadcast. A doit remettre la trame à son prochain saut L2, qui est la passerelle.
> </details>

> ❓ **RETIENS ÇA** — *Combien de fois l'en-tête Ethernet est-il reconstruit sur un trajet à 3 routeurs ?*
> <details><summary>▸ réponse</summary>
>
> **4 fois** : une fois par la source, puis une fois par chaque routeur (3). Il y a 4 « segments L2 » traversés. Le TTL, lui, perd 3 unités.
> </details>

---

## 10. Où le modèle en couches fuit

Le modèle est un **outil de pensée**, pas une loi physique. Savoir où il craque est exactement ce qui distingue un ingénieur d'un récitant.

### 10.1 TLS : coincé entre 4 et 7

TLS s'exécute **au-dessus de TCP** et **en dessous de HTTP**. Dans OSI, on le range en 6 (présentation, car il chiffre) ou en 5 (session, car il négocie un contexte). Dans TCP/IP, il n'y a pas de case : on dit « L4.5 » ou « couche 5-6 ». La vraie réponse en entretien :

> « TLS ne rentre pas proprement dans OSI. Il s'appuie sur un transport fiable — donc au-dessus de la 4 — et fournit chiffrement et intégrité aux protocoles applicatifs — donc en dessous de la 7. Par convention on le place en 6, parfois en 5. Le fait qu'il n'ait pas de case propre montre bien que OSI est un cadre descriptif, pas une architecture d'implémentation. »

Conséquence concrète : un load balancer L7 doit **terminer TLS** pour lire l'URL. D'où la **terminaison TLS** sur l'ALB, et le débat re-chiffrement vers le backend. Et le **SNI** (*Server Name Indication*), en clair dans le ClientHello, est ce qui permet à un proxy de router par domaine **sans** déchiffrer.

Coûts de handshake, à connaître :

| Établissement | RTT avant le premier octet applicatif |
|---|---|
| TCP seul | **1 RTT** (SYN → SYN-ACK → ACK+données) |
| TCP + TLS 1.2 | **3 RTT** (1 TCP + 2 TLS) |
| TCP + TLS 1.3 | **2 RTT** (1 TCP + 1 TLS) |
| QUIC (1er contact) | **1 RTT** (transport + crypto fusionnés) |
| QUIC 0-RTT (reprise) | **0 RTT** |

### 10.2 VXLAN : du L2 dans du L3 dans du L2

**Le problème.** Tu veux que deux VM dans deux racks différents, voire deux datacenters, croient être sur le même segment Ethernet. Impossible : entre elles il y a du routage IP.

**La solution.** On **encapsule la trame Ethernet complète dans un datagramme UDP**.

```
+--------+--------+--------+--------+-------------------------------------+
| Eth    | IP     | UDP    | VXLAN  |   TRAME ETHERNET INTERNE COMPLÈTE   |
| externe| externe| dst    | header |  +------+------+------+---------+   |
| 14 o   | 20 o   | 4789   | 8 o    |  | Eth  | IP   | TCP  | données |   |
|        |        | 8 o    | VNI 24b|  | 14 o | 20 o | 20 o |         |   |
+--------+--------+--------+--------+-------------------------------------+
 \_________________ 50 octets d'overhead _________________/
```

- Port UDP de destination : **4789**.
- En-tête VXLAN : **8 octets**, dont un **VNI de 24 bits** → **16 777 216** segments virtuels (contre 4094 VLAN en 802.1Q). C'est la raison d'être de VXLAN : le multi-tenant à grande échelle.
- Overhead total avec IPv4 externe : **50 octets** → MTU interne **1450** sur un underlay à 1500.

**Violation du modèle** : la couche 2 se retrouve **au-dessus** de la couche 4. L'ordre des couches n'est plus une hiérarchie, c'est une pile qu'on peut réempiler. Idem pour GRE, IPsec, WireGuard, GENEVE.

> ⚠️ **PIÈGE — LE BUG K8s CLASSIQUE.** Ton CNI (Flannel/Calico en mode VXLAN) fixe le MTU des pods à **1450**. Si quelqu'un remet 1500 en dur, ou si un nœud a un MTU d'underlay plus petit que prévu, tu obtiens exactement la signature du §8.4 : `kubectl exec` marche, les health checks passent, et le pod qui `COPY` 2 Go vers l'entrepôt se fige à 90 %. **Réflexe : `ip link show eth0` dans le pod, compare avec l'underlay.**

> ❓ **RETIENS ÇA** — *Combien d'octets d'overhead VXLAN sur IPv4, et quel MTU interne sur un underlay à 1500 ?*
> <details><summary>▸ réponse</summary>
>
> **50 octets** (14 Ethernet + 20 IP + 8 UDP + 8 VXLAN externes) → MTU interne **1450**.
> </details>

> ❓ **RETIENS ÇA** — *Sur combien de bits le VNI de VXLAN, et pourquoi ça compte ?*
> <details><summary>▸ réponse</summary>
>
> **24 bits** → ~16,7 millions de réseaux virtuels, contre 4094 VLAN utilisables en 802.1Q (VID sur 12 bits). C'est ce qui rend le cloud multi-tenant possible.
> </details>

### 10.3 QUIC : le transport qui remonte en espace utilisateur

**Le problème.** TCP est implémenté dans le **noyau**. Faire évoluer TCP suppose de mettre à jour tous les OS de la planète — et les *middleboxes* (NAT, pare-feux) jettent ce qu'elles ne reconnaissent pas. TCP est **ossifié**.

**La solution QUIC.** On implémente un transport complet (fiabilité, ordre, contrôle de congestion, chiffrement) **par-dessus UDP, en espace utilisateur**, dans la bibliothèque applicative.

```
   PILE CLASSIQUE            PILE QUIC
   +--------------+          +---------------------------+
   | HTTP/2       |          | HTTP/3                    | espace
   +--------------+          +---------------------------+ utilisateur
   | TLS 1.3      |          | QUIC (fiabilité + ordre   | (l'appli !)
   +--------------+          |   + TLS 1.3 + congestion) |
   | TCP  (noyau) |          +---------------------------+
   +--------------+          | UDP  (noyau)              |
   | IP           |          +---------------------------+
   +--------------+          | IP                        |
                             +---------------------------+
```

Ce que ça t'apporte de savoir :
- **HTTP/3 = HTTP over QUIC**, sur **UDP port 443**. Si ton pare-feu bloque l'UDP 443, tu retombes silencieusement en HTTP/2 sur TCP — parfois avec une latence bien pire, sans aucun message d'erreur.
- QUIC supprime le **head-of-line blocking** de TCP : plusieurs *streams* indépendants dans une connexion, une perte sur l'un ne bloque pas les autres. TCP, lui, ne peut pas livrer l'octet n+1 avant l'octet n.
- Le **Connection ID** remplace le 5-tuple : la connexion **survit à un changement d'IP** (Wi-Fi → 4G, ou un NAT qui rebinde).
- Tout est chiffré, **y compris les en-têtes de transport** : ni le NAT ni le pare-feu ne peuvent inspecter la fenêtre ou les numéros de séquence. Fin de l'optimisation par middlebox.

**Violation du modèle** : la frontière noyau/utilisateur, qui coïncidait avec la frontière transport/application, a bougé. La couche 4 est maintenant dans le binaire de l'application.

### 10.4 Les autres fuites, en une ligne chacune

| Fuite | En quoi elle viole le modèle |
|---|---|
| **Checksum TCP/UDP** | La couche 4 lit les adresses IP (pseudo-en-tête) de la couche 3. |
| **NAT** | Un équipement L3 réécrit les **ports** (L4) et recalcule les checksums L4. |
| **ARP / MPLS** | Entre L2 et L3 : ARP traduit du L3 en L2, MPLS est littéralement « la couche 2.5 ». |
| **DPI / WAF** | Un équipement réseau qui lit et modifie du contenu applicatif. |
| **Load balancer L7** | Casse le end-to-end de la couche 4 : deux connexions TCP au lieu d'une. |
| **ICMP** | Protocole L3 qui transporte des infos **sur** la L4 (ports dans le message d'erreur). |

> 🧠 **MÉMO — la phrase à sortir en entretien** : *« Le modèle en couches est une abstraction de conception, pas une contrainte d'implémentation. Elle est violée partout où la performance ou la sécurité l'exigent — et chaque violation a un coût en complexité qu'on paie en debug. »*

---

## 11. Ce que ça change vraiment pour toi, data engineer

### 11.1 La latence : l'ordre de grandeur qu'on ne peut pas négocier

La lumière dans une fibre va à ~200 000 km/s, soit **5 µs par kilomètre**, soit **10 ms d'aller-retour pour 1000 km**. Aucune optimisation logicielle ne bat la physique.

| Trajet | RTT typique | Ce que ça implique |
|---|---|---|
| Même machine (loopback) | ~0,05 ms | Négligeable |
| Même rack / même AZ | **0,1 – 0,5 ms** | Idéal pour du chatty |
| Inter-AZ, même région | **0,5 – 2 ms** | Acceptable, mais ×5 vs intra-AZ |
| Paris ↔ Francfort | **~10 ms** | Attention aux requêtes en boucle |
| Paris ↔ us-east-1 | **~80 – 90 ms** | Un aller-retour par ligne = catastrophe |
| Paris ↔ Singapour | **~160 – 180 ms** | Batcher ou déplacer le calcul |

**Le calcul qui tue.** Ton job fait 100 000 requêtes séquentielles vers une base dans une autre région à 80 ms de RTT :
`100 000 × 0,08 s = 8000 s = 2 h 13`, **avant même le moindre calcul**. Le même job en une requête batchée : quelques secondes.
**Règle** : à travers une région, on compte les **allers-retours**, pas les octets. Un aller-retour coûte plus cher qu'un mégaoctet.

### 11.2 Le produit bande passante × délai (BDP) — exercice corrigé

**Énoncé.** Tu transfères un dataset de Paris vers `us-east-1` sur un lien 10 Gb/s, RTT 80 ms, en une seule connexion TCP sans *window scaling*. Débit maximal atteignable ?

**Correction.**
Une connexion TCP ne peut avoir plus d'une fenêtre de données « en vol » avant de recevoir un ACK.
`Débit_max = Fenêtre / RTT`

Sans window scaling, la fenêtre max est le champ Window Size sur 16 bits : **65 535 octets**.
`65 535 o × 8 = 524 280 bits`
`524 280 / 0,080 s ≈ 6 553 500 bit/s ≈ 6,5 Mb/s`

**Sur un lien à 10 Gb/s, tu obtiens 6,5 Mb/s. Soit 0,065 % du lien.**

**Combien faudrait-il ?**
`BDP = 10 Gb/s × 0,080 s = 800 000 000 bits = 100 Mo`
Il faut **100 Mo de fenêtre** pour saturer ce lien avec **une** connexion.

**Solutions, dans l'ordre :**
1. **Window scaling** (option TCP, facteur jusqu'à 2^14 → fenêtre jusqu'à 1 Go). Activé par défaut sous Linux (`net.ipv4.tcp_window_scaling=1`) — vérifie qu'aucune middlebox ne l'écrase.
2. **Augmenter les buffers** : `net.ipv4.tcp_rmem` / `tcp_wmem`.
3. **Paralléliser** : N connexions TCP donnent N × le débit d'une seule. C'est exactement pourquoi `s5cmd`, `aws s3 cp` multipart, ou `--num-executors` élevé transfèrent plus vite qu'un `scp`.

> 🧠 **MÉMO** — **« Débit = Fenêtre / RTT. »** Trois symboles, la moitié des problèmes de perf réseau. Si tu doubles le RTT sans changer la fenêtre, tu divises le débit par deux.

> ❓ **RETIENS ÇA** — *Formule du débit maximal d'une connexion TCP unique ?*
> <details><summary>▸ réponse</summary>
>
> **Débit ≈ Fenêtre de réception / RTT**. Sans window scaling, la fenêtre plafonne à 65 535 octets, ce qui limite à ~6,5 Mb/s sur un RTT de 80 ms.
> </details>

### 11.3 La grille de diagnostic par couche

Quand « le pipeline est lent » ou « ça ne marche pas », descends les couches dans l'ordre. **Ne saute jamais une couche.**

| Couche | Symptôme | Commande |
|---|---|---|
| **1** | Interface DOWN, erreurs CRC, autonégociation | `ip -s link show` / `ethtool eth0` |
| **2** | Voisin du même /24 injoignable, cache ARP `FAILED` | `ip neigh show` / `arping <ip>` |
| **3** | Pas de route, mauvaise passerelle, pertes, boucle | `ip route get <ip>` / `mtr -n <ip>` |
| **4** | Refus, timeout, rien n'écoute, retransmissions | `ss -tlnp` / `nc -zv <ip> <port>` / `ss -tin` |
| **5-6** | Erreur TLS, certificat, SNI | `openssl s_client -connect h:443 -servername h` |
| **7** | HTTP 500, mauvais `Host`, DNS | `curl -v` / `dig +short <nom>` |

**Les trois diagnostics différentiels à mémoriser :**

| Ce que tu observes | Ce que ça signifie |
|---|---|
| `Connection refused` **immédiat** | Le paquet est **arrivé** (L1-L3 OK), mais **rien n'écoute** sur ce port. Problème d'application, pas de réseau. |
| `Connection timed out` (après ~2 min) | Rien ne répond : pare-feu qui **DROP** silencieusement, security group, mauvaise route. |
| **Handshake OK mais gros transferts figés** | **MTU / PMTU**. Presque toujours. Va directement au §8.4. |

> 🧠 **MÉMO** — **« Refused = ça arrive mais personne n'écoute. Timeout = ça n'arrive pas. Figé sur du gros = MTU. »** Trois phrases qui couvrent 80 % des tickets réseau que tu ouvriras.

### 11.4 Kubernetes vu comme un empilement de couches

```
  Ton pod Spark  ->  1. DNS pg.svc.cluster.local -> CoreDNS      [L7]
                     2. ClusterIP -> IP de pod (iptables/IPVS)   [L4]
                     3. Sortie du pod via la paire veth          [L2]
                     4. Encapsulation VXLAN par le CNI, MTU 1450 [L2 dans L4]
                     5. Routage du nœud vers le VPC              [L3]
                     6. Security group : IP + port autorisés ?   [L4]
                     7. VPC peering / Transit Gateway            [L3]
                  -> Service PostgreSQL managé
```

Ce que chaque brique K8s est, en une ligne :

| Brique | Couche | Ce qu'elle fait |
|---|---|---|
| **CNI** (Calico, Flannel, Cilium) | 2-3 | Donne une IP à chaque pod, route entre nœuds. Fixe le MTU. |
| **Service ClusterIP** | 4 | IP virtuelle → DNAT vers une IP de pod, par `iptables`/IPVS. |
| **NodePort** | 4 | Expose sur un port du nœud, plage **30000-32767**. |
| **Service LoadBalancer** | 4 | NLB cloud devant les nœuds. |
| **Ingress / Gateway API** | **7** | Routage HTTP par host/path, terminaison TLS. |
| **NetworkPolicy** | 3-4 | Pare-feu IP+port entre pods. Ne comprend **pas** HTTP. |
| **Service mesh** (Istio, Linkerd) | 4-7 | Sidecar proxy qui intercepte tout, mTLS, retry, routage L7. |

> ⚠️ **PIÈGE** — Une `NetworkPolicy` ne peut **pas** filtrer sur un chemin d'URL : elle travaille en L3/L4. Pour du filtrage L7, il faut un service mesh ou un Ingress. Question d'entretien fréquente sur les postes cloud/data.

---

## 12. Exercices de synthèse corrigés

### Exercice 1 — MSS derrière un tunnel

**Énoncé.** Tes pods K8s sont sur un overlay VXLAN, l'underlay est un VPC AWS à MTU **9001**. Quel MTU pour les pods, et quel MSS annoncé ?

**Correction.**
1. Overhead VXLAN sur IPv4 : 14 (Eth ext) + 20 (IP ext) + 8 (UDP ext) + 8 (VXLAN) = **50 o**
2. MTU pod = 9001 − 50 = **8951**
3. MSS = MTU − 20 (IP interne) − 20 (TCP interne) = 8951 − 40 = **8911**

**Vérification terrain** : `ip link show eth0` dans le pod doit afficher `mtu 8951`. Si tu vois 1450, ton CNI n'a pas détecté le jumbo de l'underlay — tu perds un facteur ~6 sur l'efficacité par paquet.

### Exercice 2 — Lire une sortie de commande

**Énoncé.** Interprète :
```
$ ping -M do -s 1472 10.20.30.40
PING 10.20.30.40 (10.20.30.40) 1472(1500) bytes of data.
ping: local error: message too long, mtu=1450
```

**Correction.**
- `-M do` force **DF=1** : interdiction de fragmenter.
- `-s 1472` = 1472 octets de données ICMP. Le noyau annonce `1472(1500)` : 1472 + 8 (en-tête ICMP) + 20 (en-tête IP) = **1500** octets de paquet IP.
- `local error ... mtu=1450` : l'erreur est **locale**, la pile a refusé avant émission car l'interface de sortie a un MTU de 1450.
- **Diagnostic** : tu es derrière un overlay (VXLAN ou tunnel équivalent, 50 o d'overhead sur 1500).
- **Le plus gros `-s` qui passera** : 1450 − 28 = **1422**.

### Exercice 3 — Où est la panne ?

**Énoncé.** Ton job Spark écrit vers un entrepôt cross-région. `nc -zv warehouse 5432` répond `succeeded`. `SELECT 1` fonctionne. Le `COPY` de 4 Go se fige après ~30 secondes puis échoue en timeout. Diagnostic ?

**Correction, en descendant les couches.**
1. `nc` réussit → L1 à L3 OK, port ouvert, pare-feu OK sur le SYN. **Élimine les couches 1 à 3 et le filtrage de port.**
2. `SELECT 1` fonctionne → authentification et protocole applicatif bons. **Élimine la couche 7.**
3. Ça ne casse **que sur du volume** → les gros segments passent mal, les petits passent. **C'est la signature MTU.**
4. **Conclusion : PMTU black hole.** Un équipement du chemin a un MTU inférieur, jette les paquets DF=1 trop gros, et l'ICMP type 3 code 4 est filtré (typiquement par un security group). Confirmation : `ping -M do -s 1472 warehouse` échoue, `ping -M do -s 1372` passe. Correctifs : autoriser l'ICMP *destination unreachable*, ou baisser le MTU de l'interface, ou faire du MSS clamping sur la gateway.

### Exercice 4 — Reconstituer la pile depuis une capture

**Énoncé.** Que t'apprend cette ligne ?
```
14:22:31.442 IP 10.0.1.10.41522 > 10.0.2.20.5432: Flags [S], seq 991284, win 64240, options [mss 1460,sackOK,TS val 118 ecr 0,nop,wscale 7], length 0
```

**Correction, champ par champ.**
- `IP` → couche 3 = IPv4, donc EtherType `0x0800` dans la trame.
- `10.0.1.10.41522` → IP source + **port source 41522**, dans la plage éphémère Linux (32768-60999). C'est **le client**.
- `10.0.2.20.5432` → **PostgreSQL**. C'est le serveur.
- `Flags [S]` → **SYN** : premier paquet du *three-way handshake*. La connexion s'ouvre.
- `win 64240` → fenêtre annoncée avant scaling.
- `mss 1460` → l'émetteur est sur un lien **MTU 1500 sans tunnel** (1460 + 20 + 20).
- `wscale 7` → facteur d'échelle 2^7 = 128 → fenêtre réelle max 64240 × 128 ≈ **8,2 Mo**. Le window scaling est bien actif.
- `sackOK` → *Selective ACK* supporté : en cas de perte, on retransmettra uniquement les segments manquants.
- `TS val ... ecr 0` → option **timestamps** activée (12 octets d'option). `ecr 0` confirme que c'est bien le premier paquet, aucun écho reçu.
- `length 0` → **aucune donnée applicative** : normal pour un SYN.

---

## 13. Questions d'entretien

**1. Cite les 7 couches OSI et donne un protocole pour chacune.**
> Physique : Ethernet 1000BASE-T, la fibre, le RJ45 — on y définit les tensions et le codage de ligne. Liaison : Ethernet II, Wi-Fi 802.11, PPP, avec adressage MAC sur 48 bits et détection d'erreur par FCS. Réseau : IPv4, IPv6, ICMP, OSPF, BGP — adressage logique et routage. Transport : TCP, UDP, SCTP, avec le multiplexage par ports 16 bits. Session : RPC, SOCKS, NetBIOS. Présentation : encodage, sérialisation, chiffrement — c'est là qu'on range TLS par convention. Application : HTTP, DNS, SMTP, SSH. Dans la pratique on travaille avec le modèle TCP/IP à 4 couches, où 5-6-7 sont fusionnées en une seule couche Application.

**2. Quelle différence entre le modèle OSI et le modèle TCP/IP ?**
> OSI a 7 couches, c'est un modèle de référence normalisé par l'ISO, jamais implémenté tel quel. TCP/IP en a 4 et c'est ce qui tourne réellement sur Internet. La correspondance : Accès réseau TCP/IP couvre les couches 1 et 2 d'OSI, Internet correspond à la 3, Transport à la 4, et Application regroupe 5, 6 et 7. La vraie différence n'est pas le nombre de couches mais la démarche : OSI a été conçu avant les protocoles, TCP/IP a été décrit après coup à partir de protocoles qui marchaient déjà. C'est pour ça que TCP/IP est plus pragmatique et OSI un meilleur outil pédagogique et de vocabulaire.

**3. Qu'est-ce que l'encapsulation ? Donne les tailles.**
> Chaque couche ajoute son en-tête devant les données reçues de la couche supérieure, qu'elle traite comme une charge utile opaque. En descendant : les données applicatives reçoivent un en-tête TCP de 20 octets minimum — ça devient un segment ; puis un en-tête IP de 20 octets — ça devient un paquet ; puis un en-tête Ethernet de 14 octets plus un FCS de 4 octets en queue — ça devient une trame. Au total, 54 octets d'en-têtes pour du TCP/IPv4 sur Ethernet, plus 4 de FCS. Avec un MTU de 1500, il reste 1460 octets de données utiles. À la réception on décapsule dans l'ordre inverse, chaque couche utilisant un champ de démultiplexage : EtherType pour passer de L2 à L3, le champ Protocol pour L3 vers L4, le port de destination pour L4 vers l'application.

**4. Différence entre un switch et un routeur ?**
> Un switch travaille en couche 2 : il commute sur l'adresse MAC destination grâce à une table CAM qu'il apprend en observant les MAC sources, et il segmente les domaines de collision — un par port. Un routeur travaille en couche 3 : il route sur l'IP destination par longest prefix match, il segmente les domaines de broadcast, il décrémente le TTL et il reconstruit intégralement l'en-tête de couche 2 à chaque saut. La formule courte : le switch coupe les collisions, le routeur coupe les broadcasts. Le switch est transparent — il ne modifie rien dans la trame ; le routeur, lui, réécrit systématiquement les adresses MAC.

**5. Qu'est-ce que le MTU ? Le MSS ? Quel rapport ?**
> Le MTU est la taille maximale d'un paquet IP, en-tête IP compris, qu'un lien peut transporter dans une trame — 1500 octets sur Ethernet standard. Il n'inclut ni l'en-tête Ethernet ni le FCS. Le MSS est la quantité maximale de données applicatives dans un segment TCP : MSS = MTU moins l'en-tête IP moins l'en-tête TCP, soit 1460 en IPv4 classique et 1440 en IPv6 puisque son en-tête fait 40 octets. Le MSS est annoncé par chaque côté dans les options du SYN. En pratique on voit souvent 1448 plutôt que 1460, parce que l'option TCP timestamps consomme 12 octets.

**6. Que se passe-t-il quand un paquet est trop gros pour le prochain lien ?**
> Deux cas. Si le bit DF vaut 0, le routeur fragmente : il découpe la charge utile en morceaux multiples de 8 octets, recopie l'identification dans chaque fragment, positionne l'offset et le flag More Fragments, et le réassemblage se fait uniquement à la destination finale. Si DF vaut 1, le routeur jette le paquet et renvoie un ICMP type 3 code 4 « Fragmentation Needed », avec le MTU du prochain saut ; c'est le mécanisme de Path MTU Discovery. En IPv6 les routeurs ne fragmentent jamais : ils renvoient un ICMPv6 type 2 « Packet Too Big » et seule la source peut fragmenter. Le problème pratique, c'est que si quelqu'un filtre l'ICMP, l'émetteur n'est jamais informé : c'est le PMTU black hole, avec sa signature typique — le handshake passe, les grosses données se figent.

**7. Décris le trajet d'un paquet entre deux machines de sous-réseaux différents.**
> La source applique son masque et constate que la destination n'est pas dans son réseau : elle doit passer par sa passerelle. Elle fait un ARP pour obtenir la MAC de la passerelle — jamais celle de la destination, car ARP est limité au domaine de broadcast local. Elle émet une trame dont la MAC destination est celle du routeur mais dont l'IP destination est celle de la machine finale. Le switch commute sans rien modifier. Le routeur jette l'en-tête Ethernet, consulte sa table de routage, décrémente le TTL, recalcule le checksum d'en-tête IP, fait un ARP sur le réseau de sortie, et construit une trame Ethernet entièrement nouvelle. À l'arrivée, les adresses IP source et destination et les ports sont inchangés ; seuls les MAC, le TTL et le checksum IP ont bougé. C'est le principe à retenir : l'IP désigne la destination du voyage, la MAC désigne le prochain arrêt.

**8. Où le modèle en couches ne tient-il pas ?**
> Plusieurs endroits. Le checksum TCP et UDP inclut un pseudo-en-tête avec les adresses IP : la couche 4 lit la couche 3, ce qui oblige le NAT à recalculer le checksum L4 quand il réécrit une IP. TLS n'a pas de case : au-dessus de TCP, en dessous d'HTTP, on le range par convention en couche 6. VXLAN encapsule une trame Ethernet complète dans de l'UDP — donc du L2 au-dessus du L4 — avec 50 octets d'overhead et un VNI sur 24 bits. QUIC réimplémente un transport complet en espace utilisateur au-dessus d'UDP, parce que TCP est ossifié dans les noyaux et les middleboxes. Et les load balancers L7 cassent le principe end-to-end en terminant la connexion TCP pour en ouvrir une autre. La conclusion, c'est que le modèle est une abstraction de conception, pas une contrainte d'implémentation.

**9. Différence entre TCP et UDP, et quand choisir l'un ou l'autre ?**
> TCP est orienté connexion : établissement en trois temps, numéros de séquence, acquittements, retransmission, livraison ordonnée, contrôle de flux par fenêtre et contrôle de congestion. Son en-tête fait 20 octets minimum. UDP n'apporte que deux choses au-dessus d'IP : le multiplexage par ports et un checksum optionnel, dans un en-tête de 8 octets fixes. On choisit TCP dès qu'on veut de la fiabilité sans la coder soi-même : bases de données, HTTP, transferts de fichiers. UDP quand la latence prime sur l'exhaustivité — DNS, NTP, télémétrie, streaming — ou quand on veut implémenter sa propre logique de fiabilité, ce que fait précisément QUIC.

**10. Pourquoi un transfert entre deux régions cloud est-il lent alors que le lien est à 10 Gb/s ?**
> Parce que le débit d'une connexion TCP unique vaut la fenêtre divisée par le RTT, pas la capacité du lien. Sur un RTT de 80 ms avec une fenêtre plafonnée à 65 535 octets faute de window scaling, on obtient environ 6,5 Mb/s — 0,065 % du lien. Pour saturer 10 Gb/s à 80 ms de RTT il faut un produit bande passante × délai de 100 Mo de fenêtre. Les leviers sont donc : vérifier que le window scaling est actif, augmenter les buffers noyau, et surtout paralléliser les connexions — c'est exactement ce que fait un upload S3 multipart. Et en amont, réduire le nombre d'allers-retours : à 80 ms, 100 000 requêtes séquentielles coûtent plus de deux heures rien qu'en latence.

---

## 14. Les 3 choses à retenir si tu ne retiens que ça

**1. L'encapsulation, avec ses chiffres : 14 / 20 / 20 / 8.**
Ethernet 14 octets, IP 20, TCP 20, UDP 8. Chaque couche ajoute son en-tête devant une charge utile qu'elle ne lit pas, et un champ de démultiplexage (EtherType → Protocol → port) dit à qui remettre la suite en remontant. Sur un MTU de 1500, il reste **1460** octets de données utiles. Si tu ne retiens qu'un nombre, c'est celui-là.

**2. L'IP c'est la destination du voyage, la MAC c'est le prochain arrêt.**
À chaque saut, l'en-tête de couche 2 est **entièrement reconstruit** et le TTL perd 1 ; les adresses IP et les ports, eux, ne bougent pas (sauf NAT). Une machine fait un ARP pour sa **passerelle**, jamais pour une destination hors de son sous-réseau. Le switch coupe les collisions, le routeur coupe les broadcasts.

**3. Quand un handshake passe mais que les gros transferts se figent, c'est le MTU.**
C'est la panne réseau la plus fréquente et la plus mal diagnostiquée dans un contexte cloud/K8s, parce que les tunnels (VXLAN −50 o, WireGuard −80 o) réduisent le MTU sans prévenir et que l'ICMP filtré casse le PMTU discovery. Réflexe en une ligne : `ping -M do -s 1472 <cible>`. Et souviens-toi que le modèle en couches est un mensonge utile : TLS n'a pas de case, VXLAN met du L2 dans du L4, QUIC remonte le transport en espace utilisateur.
