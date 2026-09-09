# R03 — Couche 3 : IPv4, CIDR & subnetting, IPv6

> **Ce que tu sauras faire à la fin**
> - Décoder un en-tête IPv4 champ par champ en hexadécimal, et dire ce que chaque champ change au comportement du paquet.
> - Calculer **de tête**, en moins de 20 secondes : réseau, broadcast, plage utilisable, nombre d'hôtes, à partir d'une IP et d'un masque quelconque.
> - Découper un bloc en sous-réseaux de tailles inégales (VLSM) sans chevauchement et sans gaspillage, et agréger des routes en un préfixe unique.
> - Reconnaître instantanément une adresse privée, une loopback, une APIPA, une multicast, une CGNAT — et dire ce qu'elle t'apprend sur la panne en cours.
> - Écrire, abréger et lire une adresse IPv6, expliquer pourquoi tout est en /64, et dérouler SLAAC de bout en bout.
> - Diagnostiquer un chevauchement de CIDR entre deux VPC, un épuisement d'IP dans un cluster K8s, et un trou noir de PMTU — les trois pannes L3 que tu rencontreras vraiment.
>
> **Pourquoi ça compte dans ton poste**
> Un pipeline de données ne vit jamais dans un seul réseau. Il lit dans un VPC, écrit dans un autre, passe par
> un peering, un VPN, un cluster Kubernetes qui a son propre plan d'adressage. Les trois quarts des tickets
> « le job ne démarre pas » sont des problèmes de couche 3 : deux VPC qui ont choisi `10.0.0.0/16` tous les
> deux, un subnet saturé qui empêche un pod de démarrer, une route absente. Savoir subnetter n'est pas un
> exercice d'école : c'est ce qui te permet de **dimensionner** un réseau de cluster avant qu'il ne coince en
> production, et de lire une table de routage sans l'aide de personne. Côté IA : les features d'un détecteur
> d'anomalies réseau sont des agrégats par préfixe — si tu ne sais pas ce qu'est un /24, tu ne sais pas
> grouper tes flux.
>
> **Prérequis** : `R01` (modèle en couches, encapsulation, PDU), `R02` (Ethernet, MAC, ARP, MTU).
> **Durée de lecture** : 75-90 min. Papier, crayon, et une calculatrice que tu n'utiliseras pas.

---

## 1. Le problème que résout la couche 3

La couche 2 sait livrer une trame **sur un segment**. Un seul. Elle utilise pour ça une adresse MAC, qui est
plate : `a0:36:9f:1c:22:8e` ne dit rien de l'endroit où se trouve la machine. C'est un numéro de série, pas
une adresse.

Pose-toi la question : **peut-on faire un Internet avec des MAC ?** Il faudrait que chaque routeur du monde
connaisse chacune des dizaines de milliards de cartes réseau existantes. Une table de 10¹⁰ entrées à
consulter en quelques nanosecondes, mise à jour chaque fois qu'une machine bouge. Impossible.

La solution est celle de la poste : **une adresse hiérarchique**. Le centre de tri de Marseille ne connaît
pas la rue des Lilas ; il sait juste que tout ce qui commence par 75 part vers Paris. C'est exactement ce
que fait IP : une adresse est composée d'une **partie réseau** (le code postal) et d'une **partie hôte** (le
numéro dans la rue). Un routeur ne connaît que des parties réseau — il ignore les machines individuelles,
sauf sur ses propres liens.

```
   MAC (couche 2)                      IP (couche 3)
   ┌────────────────────┐              ┌──────────────────────────┐
   │ a0:36:9f:1c:22:8e  │              │ 10.42.7.19 / 16          │
   └────────────────────┘              └────────┬────────┬────────┘
    plate, non structurée                   RÉSEAU     HÔTE
    « numéro de série »                    10.42.*     .7.19
    → table de 10 milliards                → 1 seule entrée de table
```

> ❓ **RETIENS ÇA** — Pourquoi ne peut-on pas router sur des adresses MAC ?
> <details><summary>→ réponse</summary><br>Parce qu'elles sont <b>plates</b> : aucune structure géographique ou topologique. Router sur des MAC exigerait une table mondiale de toutes les cartes réseau. IP est <b>hiérarchique</b> : un routeur n'apprend que des préfixes, pas des machines.</details>

La couche 3 apporte trois choses que la couche 2 n'a pas : l'**adressage hiérarchique** (agréger des millions
de machines en une entrée de table), le **routage de proche en proche** (traverser des technologies de lien
différentes : Ethernet, fibre, 4G, VPN) et la **fragmentation + le TTL** (survivre à des MTU hétérogènes,
tuer les paquets en boucle).

> 🧠 **MÉMO** — **L2 = le prochain arrêt. L3 = la destination du voyage.** L'adresse IP survit à tout le
> trajet ; l'adresse MAC est réécrite à chaque saut. Cette phrase est le pont entre R02 et R03 : garde-la.

---

## 2. L'adresse IPv4 : 32 bits, et rien d'autre

Une adresse IPv4 est un **entier non signé de 32 bits**. Point. La notation en quatre nombres pointés
(`192.168.1.10`) est une **commodité d'écriture pour humains** : on découpe les 32 bits en quatre octets
écrits en décimal. Le réseau, lui, ne voit que des bits.

```
  192   .   168   .    1    .   10
 11000000 10101000 00000001 00001010
 └──────┘ └──────┘ └──────┘ └──────┘
  octet 1  octet 2  octet 3  octet 4
 └──────────────── 32 bits ─────────────────┘
   = 3232235786 en décimal pur
```

**Espace total : 2³² = 4 294 967 296 adresses**, environ 4,3 milliards — pour 8 milliards d'humains et des
dizaines de milliards d'objets. C'est tout le drame d'IPv4, et la raison d'être du NAT et d'IPv6. Chaque
octet va de 0 à 255 : `192.168.1.300` n'existe pas, `10.0.0.256` non plus.

> ⚠️ **PIÈGE** — Une adresse IP n'identifie **pas une machine**, elle identifie une **interface**. Un routeur
> a autant d'adresses IP que d'interfaces actives. Un serveur avec deux cartes a deux IP. La loopback
> `127.0.0.1` en est une troisième. « L'IP du serveur » est un abus de langage commode mais faux.

> 🧠 **MÉMO** — Les huit puissances de 2 d'un octet, à connaître dans les deux sens :
> **128 · 64 · 32 · 16 · 8 · 4 · 2 · 1**. Tout le subnetting tient dans cette ligne. Récite-la
> à l'envers aussi : 1, 2, 4, 8, 16, 32, 64, 128.

**Conversion binaire → décimal** : pose les poids au-dessus des bits, additionne ceux qui valent 1.

```
  poids : 128  64  32  16   8   4   2   1
  bits  :   1   1   0   0   0   0   0   0   →  128 + 64      = 192
  bits  :   1   0   1   0   1   0   0   0   →  128 + 32 + 8  = 168
  bits  :   1   1   1   0   0   0   0   0   →  128 + 64 + 32 = 224
```

---

## 3. L'en-tête IPv4, champ par champ

L'en-tête IPv4 fait **20 octets minimum** (sans options) et **60 octets maximum**. C'est tout ce que le
routeur lit ; il ne regarde jamais les données.

```
  0                   1                   2                   3
  0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
 ┌───────┬───────┬───────────────┬───────────────────────────────┐
 │Version│  IHL  │  DSCP  │ECN   │        Total Length           │  4 octets
 │ (4b)  │ (4b)  │  (6b)  │(2b)  │           (16b)               │
 ├───────┴───────┴────────┴──────┼─────┬─────────────────────────┤
 │       Identification          │Flags│    Fragment Offset      │  4 octets
 │           (16b)               │(3b) │         (13b)           │
 ├───────────────┬───────────────┼─────┴─────────────────────────┤
 │      TTL      │   Protocol    │        Header Checksum        │  4 octets
 │     (8b)      │     (8b)      │             (16b)             │
 ├───────────────┴───────────────┴───────────────────────────────┤
 │                    Source IP Address (32b)                    │  4 octets
 ├───────────────────────────────────────────────────────────────┤
 │                  Destination IP Address (32b)                 │  4 octets
 ├───────────────────────────────────────────────────────────────┤
 │              Options (0 à 40 octets, rarissime)               │
 └───────────────────────────────────────────────────────────────┘
                                                        Total : 20 o mini
```

**Redessine cet en-tête trois fois de mémoire.** C'est l'exercice le plus rentable du module : il tombe en
entretien, et il te sert à lire une capture `tcpdump -x`.

### 3.1 Version (4 bits)

Vaut `4` pour IPv4, `6` pour IPv6. C'est le tout premier demi-octet du paquet. Un paquet IPv4 commence donc
toujours par le nibble `4`, et comme l'IHL vaut presque toujours 5, **le premier octet d'un paquet IPv4 est
quasi systématiquement `0x45`**. C'est ton repère visuel en hexadécimal.

### 3.2 IHL — Internet Header Length (4 bits)

La longueur de **l'en-tête**, exprimée en **mots de 32 bits** (donc en tranches de 4 octets). Minimum 5
(5 × 4 = 20 octets), maximum 15 (15 × 4 = 60 octets). Il existe parce que le champ Options est de taille
variable : sans IHL, le routeur ne saurait pas où commencent les données.

> ⚠️ **PIÈGE** — IHL est en **mots de 4 octets**, pas en octets. IHL = 5 → 20 octets. L'erreur classique en
> entretien, c'est de répondre « 5 octets ».

### 3.3 DSCP (6 bits) + ECN (2 bits)

Historiquement un seul octet appelé **ToS** (Type of Service), redécoupé par la RFC 2474.

- **DSCP** (*Differentiated Services Code Point*, 6 bits) : la classe de qualité de service, qui décide de la
  file d'attente du routeur. À connaître : `0` = CS0 = *best effort* (le défaut), `46` = **EF**
  (*Expedited Forwarding*, la voix), `48` = CS6 (contrôle réseau : OSPF, BGP), `34` = AF41 (vidéo).
- **ECN** (*Explicit Congestion Notification*, 2 bits) : permet à un routeur de **signaler la congestion sans
  jeter le paquet**. `00` = émetteur non ECN, `10`/`01` = ECN capable, `11` = **CE** (*Congestion
  Experienced*) — un routeur a marqué le paquet, le récepteur préviendra l'émetteur qui ralentira comme
  s'il avait perdu un paquet. Sans ECN, la seule façon de dire « ralentis » est de **jeter**. ECN remplace
  la gifle par un mot.

> ❓ **RETIENS ÇA** — Quelle valeur DSCP pour la voix, et quel est son nom ?
> <details><summary>→ réponse</summary><br><b>DSCP 46 = EF</b> (Expedited Forwarding). File prioritaire, faible latence, faible gigue.</details>

### 3.4 Total Length (16 bits)

La longueur **totale** du paquet : en-tête **plus** données. En octets, cette fois. Maximum
**65 535 octets** (2¹⁶ − 1). En pratique, limitée par le MTU du lien : 1500 octets sur Ethernet.

Taille des données = `Total Length − (IHL × 4)`. Un paquet TCP « vide » (juste un ACK) fait typiquement
40 octets : 20 d'IP + 20 de TCP.

### 3.5 Identification, Flags, Fragment Offset — le trio de la fragmentation

Ces trois champs ne servent qu'à une chose : découper un paquet trop gros et le recoller à l'arrivée.

- **Identification** (16 bits) : numéro identique pour **tous les fragments d'un même paquet d'origine** — la
  référence du colis. La destination regroupe par (Source, Destination, Protocol, ID).
- **Flags** (3 bits) : bit 0 **réservé** (toujours 0) · bit 1 **DF** — *Don't Fragment*, « interdiction de me
  découper, si je ne passe pas jette-moi et préviens » (base du **Path MTU Discovery**) · bit 2 **MF** —
  *More Fragments*, à 1 sur tous les fragments **sauf le dernier**.
- **Fragment Offset** (13 bits) : position de ce fragment dans le paquet d'origine, **en unités de 8 octets**.
  D'où la contrainte : tout fragment sauf le dernier a une taille de données multiple de 8.

> 🧠 **MÉMO** — **DF = « Défense de Fragmenter »**, **MF = « Msieur, y en a encore »**. Et l'offset se compte
> en **paquets de 8** parce que 2¹³ × 8 = 65 536, juste ce qu'il faut pour adresser tout le paquet
> (13 bits ne suffiraient pas seuls : 2¹³ = 8192 positions).

**Exemple complet, à savoir refaire.** Un datagramme IPv4 de **4000 octets** (20 d'en-tête + 3980 de données)
doit traverser un lien de **MTU 1500**.

```
 Place dispo par fragment = 1500 − 20 (en-tête recopié) = 1480 octets de données
 1480 est bien un multiple de 8 (1480 / 8 = 185) ✔

 Fragment 1 : données 0    → 1479   (1480 o)  offset =    0     MF=1  taille totale 1500
 Fragment 2 : données 1480 → 2959   (1480 o)  offset =  185     MF=1  taille totale 1500
 Fragment 3 : données 2960 → 3979   (1020 o)  offset =  370     MF=0  taille totale 1040
                                              ^^^^^^^
                                  1480/8=185 · 2960/8=370
 Total transmis : 1500 + 1500 + 1040 = 4040 octets pour 4000 → 40 o d'overhead (2 en-têtes en plus)
```

> ❓ **RETIENS ÇA** — En quelle unité s'exprime le Fragment Offset ?
> <details><summary>→ réponse</summary><br>En <b>unités de 8 octets</b>. Un offset de 185 signifie octet 1480 du paquet d'origine.</details>

> ⚠️ **PIÈGE** — **Un routeur IPv6 ne fragmente jamais.** En IPv4 il le peut (si DF=0) ; en IPv6 seule la
> source fragmente, via un en-tête d'extension. C'est un des grands changements d'IPv6, et une question
> d'entretien fréquente.

**Pourquoi c'est un fléau en production** : si **un seul** fragment est perdu, tout le paquet l'est et TCP
retransmet l'intégralité. Les pare-feux stateful gèrent mal les fragments (seul le premier porte les ports)
et beaucoup les jettent. Règle de terrain : **on évite la fragmentation, on ajuste le MTU/MSS**.

### 3.6 TTL — Time To Live (8 bits)

Un compteur décrémenté de **1 par chaque routeur traversé**. À **zéro**, le paquet est **détruit** et le
routeur renvoie un ICMP *Time Exceeded* (type 11) à la source. Sans lui, une boucle de routage saturerait le
réseau en quelques secondes.

Valeurs initiales par défaut : **Linux / macOS / Android = 64** · **Windows = 128** · **routeurs Cisco
(trafic généré) = 255**. Un `ping` qui répond `ttl=57` depuis un Linux ? 64 − 57 = **7 sauts**. Tu viens de
compter les routeurs sans faire de traceroute.

> ❓ **RETIENS ÇA** — Un paquet arrive avec TTL = 51 depuis un serveur Linux. Combien de sauts ?
> <details><summary>→ réponse</summary><br>64 − 51 = <b>13 sauts</b>. (On suppose le TTL initial 64, standard sur Linux.)</details>

> ⚠️ **PIÈGE** — « TTL » veut dire *Time* To Live, mais ce n'est **pas** un temps : c'est un **compteur de
> sauts**. La RFC prévoyait initialement une décrémentation à la seconde, jamais appliquée. IPv6 a corrigé le
> nom : le champ s'appelle **Hop Limit**.

### 3.7 Protocol (8 bits)

Le numéro du protocole encapsulé — le **démultiplexeur** vers la couche 4. Sans lui, la pile ne saurait pas
si les données qui suivent sont du TCP, de l'UDP ou autre chose.

| N° | Protocole | N° | Protocole |
|---|---|---|---|
| **1** | **ICMP** | 47 | GRE (tunnels) |
| 2 | IGMP (multicast) | 50 | ESP (IPsec chiffré) |
| **6** | **TCP** | 51 | AH (IPsec authentifié) |
| **17** | **UDP** | **58** | **ICMPv6** |
| 41 | IPv6 encapsulé (6in4) | 89 | OSPF |
| 4 | IPv4 encapsulé (IP-in-IP) | 132 | SCTP |

> 🧠 **MÉMO** — Les trois à ne jamais rater : **1 = ICMP, 6 = TCP, 17 = UDP**. « **1, 6, 17** » se récite
> comme une date. Les security groups AWS et les règles iptables les utilisent en clair : quand tu écris
> `protocol: -1` dans un security group, tu dis « tous ».

### 3.8 Header Checksum (16 bits)

Une somme de contrôle **de l'en-tête uniquement**, pas des données, calculée en complément à un sur des mots
de 16 bits. Conséquence structurelle : puisque le **TTL change à chaque saut**, le checksum est **recalculé
par chaque routeur** — un coût par paquet, à l'échelle de milliards de paquets par seconde.

**IPv6 a supprimé ce champ** : Ethernet a déjà un FCS en dessous, TCP et UDP un checksum au-dessus. Un
troisième contrôle intermédiaire ne fait que coûter du CPU.

> ❓ **RETIENS ÇA** — Le checksum IPv4 couvre-t-il les données ?
> <details><summary>→ réponse</summary><br><b>Non</b>, l'en-tête seulement. Les données sont protégées par le checksum TCP/UDP (obligatoire en TCP, en UDP/IPv6, optionnel en UDP/IPv4) et par le FCS Ethernet.</details>

### 3.9 Adresses source et destination (32 bits chacune)

Elles ne changent **jamais** pendant le trajet — sauf traversée d'un **NAT**, qui réécrit précisément ces
champs (et donc recalcule le checksum, et donc doit aussi corriger le checksum TCP/UDP à cause du
pseudo-en-tête).

### 3.10 Options (0 à 40 octets)

*Record Route*, *Timestamp*, *Source Routing*. En pratique **jamais utilisées**, souvent bloquées par les
pare-feux (le *Source Routing* est un vecteur d'attaque). Elles expliquent l'existence du champ IHL.

**Un en-tête réel à décoder en hexa** :

```
  45 00 00 3c | 1c 46 40 00 | 40 06 b1 e6 | c0 a8 00 68 | c0 a8 00 01
  │  │    │      │      │      │  │    │     source        destination
  │  │    │      │      │      │  │    checksum   192.168.0.104 → 192.168.0.1
  │  │    │      │      │      │  Protocol 06 = TCP
  │  │    │      │      │      TTL 0x40 = 64 → émetteur Linux
  │  │    │      │      Flags 0x40 → DF=1, MF=0, offset=0
  │  │    │      ID = 0x1c46
  │  │    Total Length 0x003c = 60 octets
  │  DSCP/ECN = 0 (best effort)
  Version 4, IHL 5 → en-tête de 20 octets
```

---

## 4. Des classes historiques au CIDR

### 4.1 L'ancien monde : les classes

À l'origine (1981), la frontière réseau/hôte était **déduite des premiers bits** de l'adresse. Pas de masque
à transmettre : l'adresse portait sa propre structure.

| Classe | Bits de tête | Premier octet | Masque implicite | Réseaux | Hôtes/réseau |
|---|---|---|---|---|---|
| **A** | `0...` | 1 – 126 | /8 (255.0.0.0) | 126 | 16 777 214 |
| **B** | `10..` | 128 – 191 | /16 (255.255.0.0) | 16 384 | 65 534 |
| **C** | `110.` | 192 – 223 | /24 (255.255.255.0) | 2 097 152 | 254 |
| **D** | `1110` | 224 – 239 | — | **multicast** | — |
| **E** | `1111` | 240 – 255 | — | réservé / expérimental | — |

(127.x.x.x est absent de la classe A : c'est la loopback.)

**Pourquoi ça a échoué.** Une entreprise de 300 machines : la classe C (254 hôtes) ne suffit pas, la classe B
(65 534) en gaspille 65 200, et il n'y a rien entre les deux. Dans les années 90, l'espace des classes B
s'épuisait pendant que des millions d'adresses dormaient : la **crise de l'adressage**.

> ❓ **RETIENS ÇA** — Pourquoi les classes ont-elles été abandonnées ?
> <details><summary>→ réponse</summary><br>Granularité absurde : 254, 65 534 ou 16 millions d'hôtes, rien entre les deux. Gaspillage massif et explosion des tables de routage. Remplacées par CIDR en 1993 (RFC 1519).</details>

### 4.2 Le nouveau monde : CIDR

**CIDR** = *Classless Inter-Domain Routing*, RFC 1519, 1993. Une seule idée : **la frontière réseau/hôte
devient libre** et se transporte explicitement sous forme d'un **préfixe**. `10.42.7.19/22` se lit : « les
**22 premiers bits** identifient le réseau, les **10 derniers** l'hôte ».

```
  10.42.7.19 /22

  00001010 00101010 00000111 00010011   ← l'adresse
  11111111 11111111 11111100 00000000   ← le masque /22 = 255.255.252.0
  └────────── 22 bits réseau ──┘└ 10 bits hôte ┘

  ET logique bit à bit ↓
  00001010 00101010 00000100 00000000  = 10.42.4.0   ← ADRESSE RÉSEAU
```

Deux formules, les seules à retenir :

```
  Nombre total d'adresses d'un /n  =  2^(32 − n)
  Nombre d'hôtes utilisables       =  2^(32 − n) − 2
                                          ↑
                          on retire l'adresse réseau (bits hôte à 0)
                          et l'adresse broadcast   (bits hôte à 1)
```

> ⚠️ **PIÈGE** — Le « −2 » n'existe **pas** en IPv6, et **pas non plus** sur un `/31` (RFC 3021 :
> les liens point-à-point utilisent les 2 adresses) ni sur un `/32` (route d'hôte, une seule adresse). En
> revanche, dans les clouds, c'est pire : **AWS réserve 5 adresses par subnet**, pas 2.

---

## 5. La table des masques — à connaître par cœur

C'est **la** table du module. Si tu ne mémorises qu'une chose ici, c'est elle.

| Préfixe | Masque décimal | Dernier octet du masque | Adresses | Hôtes utilisables | Blocs dans un /24 |
|---|---|---|---|---|---|
| /24 | 255.255.255.0 | 0 | 256 | 254 | 1 |
| /25 | 255.255.255.**128** | 1000 0000 | 128 | 126 | 2 |
| /26 | 255.255.255.**192** | 1100 0000 | 64 | 62 | 4 |
| /27 | 255.255.255.**224** | 1110 0000 | 32 | 30 | 8 |
| /28 | 255.255.255.**240** | 1111 0000 | 16 | 14 | 16 |
| /29 | 255.255.255.**248** | 1111 1000 | 8 | 6 | 32 |
| /30 | 255.255.255.**252** | 1111 1100 | 4 | **2** | 64 |
| /31 | 255.255.255.**254** | 1111 1110 | 2 | 2 (RFC 3021) | 128 |
| /32 | 255.255.255.255 | 1111 1111 | 1 | 1 (route d'hôte) | 256 |

Et les préfixes courts, côté troisième octet :

| Préfixe | Masque | Adresses | Hôtes | Équivalent |
|---|---|---|---|---|
| /23 | 255.255.**254**.0 | 512 | 510 | 2 × /24 |
| /22 | 255.255.**252**.0 | 1 024 | 1 022 | 4 × /24 |
| /21 | 255.255.**248**.0 | 2 048 | 2 046 | 8 × /24 |
| /20 | 255.255.**240**.0 | 4 096 | 4 094 | 16 × /24 |
| /19 | 255.255.**224**.0 | 8 192 | 8 190 | 32 × /24 |
| /18 | 255.255.**192**.0 | 16 384 | 16 382 | 64 × /24 |
| /17 | 255.255.**128**.0 | 32 768 | 32 766 | 128 × /24 |
| /16 | 255.255.0.0 | 65 536 | 65 534 | 256 × /24 |
| /12 | 255.**240**.0.0 | 1 048 576 | 1 048 574 | 16 × /16 |
| /8 | 255.0.0.0 | 16 777 216 | 16 777 214 | 256 × /16 |

> 🧠 **MÉMO** — Les **huit valeurs légales** d'un octet de masque, dans l'ordre :
> **128 · 192 · 224 · 240 · 248 · 252 · 254 · 255**.
> Chacune est la précédente **plus la puissance de 2 suivante en descendant** : 128, +64, +32, +16, +8, +4, +2, +1.
> **Toute autre valeur dans un masque est invalide.** Si tu vois `255.255.255.100`, c'est une faute de frappe.

> 🧠 **MÉMO 2** — La **taille de bloc** est le complément de la valeur du masque à 256 :
> masque 192 → bloc **64** ; masque 224 → bloc **32** ; masque 240 → bloc **16** ; masque 248 → bloc **8**.
> `256 − valeur du masque = taille du bloc`. C'est la clé de toute la méthode de calcul qui suit.

> ❓ **RETIENS ÇA** — Combien d'hôtes utilisables dans un /26 ?
> <details><summary>→ réponse</summary><br>2^(32−26) − 2 = 64 − 2 = <b>62</b>.</details>

---

## 6. Subnetting : la méthode, en 5 gestes

Oublie le binaire pour les cas courants. La méthode décimale rapide, celle qu'on utilise réellement :

```
 ┌─────────────────────────────────────────────────────────────────────┐
 │ 1. Repère l'OCTET INTÉRESSANT : celui où le masque n'est ni 255 ni 0 │
 │ 2. Calcule la TAILLE DE BLOC :  256 − valeur du masque dans cet octet│
 │ 3. Liste les MULTIPLES du bloc : 0, bloc, 2×bloc, ... jusqu'à 256    │
 │ 4. L'ADRESSE RÉSEAU = le plus grand multiple ≤ valeur de l'IP        │
 │ 5. BROADCAST = réseau suivant − 1.  Plage utile = réseau+1 → bcast−1 │
 └─────────────────────────────────────────────────────────────────────┘
```

Cas particulier trivial : si le masque est /8, /16 ou /24, l'octet intéressant n'existe pas — le réseau
s'obtient en mettant à zéro tous les octets suivants.

> 🧠 **MÉMO** — **« BLOC = 256 − MASQUE »**. Trois mots. Tout le subnetting sort de là.

---

## 7. Sept exercices intégralement corrigés

### Exercice 1 — Découper un /22 en /24

**Énoncé** : tu disposes de `10.20.4.0/22`. Découpe-le en /24. Donne chaque sous-réseau avec sa plage.

**Raisonnement.** On gagne 24 − 22 = **2 bits**, donc 2² = **4 sous-réseaux**. L'octet intéressant du /22 est
le **3ᵉ** (masque 255.255.**252**.0), taille de bloc 256 − 252 = **4** : le /22 couvre les 3ᵉ octets 4 à 7.

```
 10.20.4.0/22  =  10.20.4.0 ──────────────────────── 10.20.7.255   (1024 adresses)
   ├── 10.20.4.0/24 : .4.0 → .4.255  (utile .4.1 → .4.254)
   ├── 10.20.5.0/24 : .5.0 → .5.255  (utile .5.1 → .5.254)
   ├── 10.20.6.0/24 : .6.0 → .6.255  (utile .6.1 → .6.254)
   └── 10.20.7.0/24 : .7.0 → .7.255  (utile .7.1 → .7.254)
```

**Vérification** : 4 × 256 = 1024 = 2^(32−22) ✔. Total utilisable 4 × 254 = 1016 contre 1022 pour le /22
non découpé : **on perd 6 adresses**, prix de 3 couples réseau/broadcast supplémentaires.

### Exercice 2 — Trouver le réseau d'une IP donnée

**Énoncé** : `192.168.37.201/26`. Donne réseau, broadcast, première et dernière IP utilisable, nombre d'hôtes.

**Raisonnement.** /26 → masque `255.255.255.192`, octet intéressant le **4ᵉ**, bloc = 256 − 192 = **64**.
Multiples de 64 : 0, 64, 128, **192**. 201 tombe dans le dernier bloc.

```
 4ᵉ octet :  0 ──── 63 │ 64 ──── 127 │ 128 ──── 191 │ 192 ──── 255
             ↑ bloc 1   ↑ bloc 2       ↑ bloc 3       ↑ bloc 4  ← 201 est ICI
                                                      net .192 · bcast .255
```

**Réseau 192.168.37.192/26 · broadcast .255 · plage utilisable .193 → .254 · 2⁶ − 2 = 62 hôtes.**
Contrôle en binaire : `201 = 11001001` ET `11000000` = `11000000` = **192** ✔

### Exercice 3 — Un masque qui coupe dans le 3ᵉ octet

**Énoncé** : `172.22.145.77/19`. Réseau, broadcast, plage, nombre d'hôtes.

**Raisonnement.** /19 = 8 + 8 + 3 bits → masque `255.255.224.0`, octet intéressant le **3ᵉ**,
bloc = 256 − 224 = **32**. Multiples de 32 : 0, 32, 64, 96, **128**, 160, 192, 224 → plus grand multiple
≤ 145 = **128**. Réseau suivant : 172.22.**160**.0.

**Réseau 172.22.128.0/19 · broadcast 172.22.159.255 · plage 172.22.128.1 → 172.22.159.254 ·
2^(32−19) − 2 = 8190 hôtes.**

> ⚠️ **PIÈGE** — Erreur classique : dire que le broadcast est `172.22.128.255`. Non ! Quand le masque coupe
> dans le 3ᵉ octet, le **4ᵉ octet est entièrement en partie hôte** : le broadcast a donc `255` au 4ᵉ octet
> **et** la dernière valeur du bloc au 3ᵉ.

### Exercice 4 — Deux IP sont-elles dans le même réseau ?

**Énoncé** : `10.4.130.9/23` et `10.4.129.200/23` peuvent-elles se parler sans routeur ?

**Raisonnement.** /23 → `255.255.254.0`, octet intéressant le **3ᵉ**, bloc = 256 − 254 = **2** : les /23
commencent sur les 3ᵉ octets **pairs**. `10.4.130.9` → 130 pair → réseau **10.4.130.0/23** (130.0 →
**131**.255). `10.4.129.200` → 129 impair → multiple de 2 inférieur = 128 → réseau **10.4.128.0/23**
(128.0 → 129.255).

**Réponse : NON.** Elles sont dans deux /23 différents et adjacents. Il leur faut un routeur.

```
 10.4.128.0/23  ├─ 128.0 ───── 129.255 ─┤  ← 10.4.129.200 est ici
 10.4.130.0/23  ├─ 130.0 ───── 131.255 ─┤  ← 10.4.130.9   est ici
                      elles se touchent mais ne se parlent pas
```

> 🧠 **MÉMO** — /23 → 3ᵉ octet **pair**. /22 → multiple de **4**. /21 → multiple de **8**. /20 → multiple
> de **16**. Le bloc est toujours 2^(24−n).

### Exercice 5 — VLSM : découper au plus juste

**Énoncé** : tu as `10.10.0.0/22`. Alloue, sans gaspiller, des sous-réseaux pour :
A = 500 hôtes · B = 200 hôtes · C = 60 hôtes · D = 25 hôtes · E et F = 2 liens point-à-point.

**Méthode VLSM** : on trie **du plus gros au plus petit** et on alloue en séquence. C'est non négociable :
allouer un petit bloc d'abord fragmente l'espace et empêche de placer les gros.

| Besoin | Il faut 2^h − 2 ≥ … | Préfixe | Bloc alloué | Plage utilisable |
|---|---|---|---|---|
| A, 500 hôtes | h = 9 → 510 | **/23** | `10.10.0.0/23` | 10.10.0.1 → 10.10.1.254 |
| B, 200 hôtes | h = 8 → 254 | **/24** | `10.10.2.0/24` | 10.10.2.1 → 10.10.2.254 |
| C, 60 hôtes | h = 6 → 62 | **/26** | `10.10.3.0/26` | 10.10.3.1 → 10.10.3.62 |
| D, 25 hôtes | h = 5 → 30 | **/27** | `10.10.3.64/27` | 10.10.3.65 → 10.10.3.94 |
| E, lien P2P | 2 adresses | **/30** | `10.10.3.96/30` | 10.10.3.97 → .98 |
| F, lien P2P | 2 adresses | **/30** | `10.10.3.100/30` | 10.10.3.101 → .102 |

```
 10.10.0.0/22  (1024 adresses : 10.10.0.0 → 10.10.3.255)
 ┌──────────────────────────────┬────────────┬──────┬────┬──┬──┬───────────┐
 │            A  /23            │    B /24   │ C/26 │D/27│E │F │   LIBRE   │
 │      10.10.0.0 → 1.255       │  2.0→2.255 │3.0→63│64→95│96│100│ 3.104→3.255│
 └──────────────────────────────┴────────────┴──────┴────┴──┴──┴───────────┘
   512 adr.                       256 adr.     64     32   4  4    152 restantes
```

**Vérification** : 512 + 256 + 64 + 32 + 4 + 4 = **872** adresses consommées sur 1024. Reste
`10.10.3.104 → 10.10.3.255` = **152 adresses libres**, réutilisables en /29, /28 ou /30.

> ⚠️ **PIÈGE** — Un sous-réseau doit **toujours** commencer sur un multiple de sa propre taille. Tu ne peux
> pas placer un /26 à `10.10.3.10`. C'est la règle d'**alignement** : le réseau d'un /n est forcément un
> multiple de 2^(32−n). Un outil comme `ipcalc` refusera ; un humain fatigué, non.

### Exercice 6 — Agréger (supernetting)

**Énoncé** : ton routeur annonce 4 routes : `192.168.8.0/24`, `192.168.9.0/24`, `192.168.10.0/24`,
`192.168.11.0/24`. Peux-tu les résumer en une seule ?

**Raisonnement.** On écrit le 3ᵉ octet en binaire et on cherche le **plus long préfixe commun**.

```
   8  = 0000 1000
   9  = 0000 1001
  10  = 0000 1010
  11  = 0000 1011
        ^^^^ ^^      ← 6 bits communs
                ^^   ← 2 bits qui varient (00,01,10,11)
```

Préfixe commun = 16 bits (192.168) + 6 bits = **/22**. **Réponse : `192.168.8.0/22`**, qui couvre exactement
192.168.8.0 → 192.168.11.255. Quatre lignes de table de routage deviennent une.

> ⚠️ **PIÈGE** — Ça n'aurait **pas** marché avec 192.168.**9**.0 → 192.168.12.0. Un agrégat doit être
> **aligné** : le bloc doit commencer sur un multiple de sa taille. 8 est multiple de 4 ✔ ; 9 ne l'est pas ✘.

### Exercice 7 — Dimensionner un VPC pour un cluster K8s

**Énoncé** : tu crées un VPC AWS `10.30.0.0/16`. Tu veux 3 zones de disponibilité, avec dans chacune un
subnet public (NAT gateway, load balancer) et un subnet privé (nœuds EKS, pods avec le CNI AWS qui donne de
vraies IP de VPC aux pods). Tu prévois 60 nœuds à terme, ~50 pods par nœud.

**Raisonnement.** Côté privé : 60 nœuds × 50 pods ≈ **3100 IP**, sur 3 AZ → ~1050 par AZ. Un /22 (1022,
soit 1019 après les réserves AWS) est **juste trop petit** → **/21** (2048). Côté public, quelques NAT
gateways et ENI de load balancer : un **/24** par AZ suffit.

```
 VPC 10.30.0.0/16   (65 536 adresses)
 ├─ privés   10.30.0.0/21 AZ-a  ·  10.30.8.0/21 AZ-b  ·  10.30.16.0/21 AZ-c
 │              (0.0→7.255)          (8.0→15.255)          (16.0→23.255)
 ├─ publics  10.30.24.0/24 AZ-a ·  10.30.25.0/24 AZ-b ·  10.30.26.0/24 AZ-c
 └─ 10.30.27.0 → 10.30.255.255   RÉSERVÉ pour la croissance (~58 000 adresses)
```

**Le point important** : **on ne peut pas agrandir un subnet AWS après création**, son CIDR est immuable.
D'où la règle : **surdimensionne dès le départ** et laisse un grand trou libre. Une IP privée inutilisée ne
coûte rien ; un re-adressage de cluster en production coûte un week-end.

> ❓ **RETIENS ÇA** — Combien d'adresses AWS réserve-t-il dans chaque subnet, et lesquelles ?
> <details><summary>→ réponse</summary><br><b>5 adresses</b> : l'adresse réseau (.0), le routeur VPC (.1), le serveur DNS (.2), une réservée pour usage futur (.3), et le broadcast (dernière). Un /28 AWS ne donne donc que <b>11</b> IP utilisables, pas 14.</details>

---

## 8. Les adresses spéciales — reconnaître au premier coup d'œil

| Plage | Nom / RFC | Ce que ça veut dire |
|---|---|---|
| **10.0.0.0/8** | Privée RFC 1918 | 16,7 M d'adresses. Le choix des grands VPC. |
| **172.16.0.0/12** | Privée RFC 1918 | 172.16.0.0 → **172.31**.255.255. 1 M d'adresses. |
| **192.168.0.0/16** | Privée RFC 1918 | 65 536 adresses. Les box, les labos. |
| **127.0.0.0/8** | Loopback | Ne quitte jamais la machine. Tout le /8, pas juste .0.0.1. |
| **169.254.0.0/16** | APIPA / link-local (RFC 3927) | **Le DHCP a échoué.** Auto-attribution. |
| **169.254.169.254** | Metadata cloud | AWS/GCP/Azure : credentials et user-data de l'instance. |
| **100.64.0.0/10** | CGNAT (RFC 6598) | NAT de l'opérateur. Aussi utilisé par Tailscale, EKS. |
| **224.0.0.0/4** | Multicast | 224.0.0.1 = tous les hôtes, 224.0.0.2 = tous les routeurs. |
| **240.0.0.0/4** | Réservé (ex-classe E) | Inutilisable en pratique. |
| **255.255.255.255** | Broadcast limité | Ne traverse aucun routeur. Utilisé par DHCP DISCOVER. |
| **0.0.0.0/8** | « Cet hôte » | `0.0.0.0` en source = « je n'ai pas encore d'IP » (DHCP). |
| **0.0.0.0/0** | Route par défaut | « Tout le reste ». En bind : « toutes les interfaces ». |
| 192.0.2.0/24 · 198.51.100.0/24 · 203.0.113.0/24 | Documentation (RFC 5737) | À utiliser dans les schémas, jamais en vrai. |

> ❓ **RETIENS ÇA** — Tu vois `169.254.31.7` sur une interface. Quel est le diagnostic immédiat ?
> <details><summary>→ réponse</summary><br>La machine <b>n'a pas obtenu de bail DHCP</b> et s'est auto-attribué une adresse APIPA. Le serveur DHCP est injoignable : câble, VLAN, relais DHCP, ou serveur mort.</details>

> ⚠️ **PIÈGE** — `172.16.0.0/12` s'arrête à **172.31**.255.255, pas à 172.16.255.255 et pas à 172.255.x.x.
> Le /12 fige les 4 premiers bits du 2ᵉ octet : 0001**0000** = 16 → 0001**1111** = 31. C'est l'erreur la plus
> fréquente en entretien. `172.32.0.0` est une adresse **publique**.

> 🧠 **MÉMO** — Les trois plages privées : **« 10, tout · 172 seize-à-trente-et-un · 192.168 »**.
> Un /8, un /12, un /16. Et pour l'ordre des masques : **8, 12, 16**, comme les tailles de pointure.

> ❓ **RETIENS ÇA** — Que signifie `0.0.0.0/0` dans une table de routage ?
> <details><summary>→ réponse</summary><br>La <b>route par défaut</b> : masque de longueur 0, elle matche toutes les destinations. C'est la route de plus faible priorité (préfixe le plus court), utilisée quand aucune autre ne correspond.</details>

---

## 9. La table de routage et le *longest prefix match*

Un routeur reçoit un paquet. Comment choisit-il la sortie ? Il compare l'IP de destination à toutes les
entrées de sa table et retient, parmi celles qui matchent, **celle dont le préfixe est le plus long**. Pas la
première, pas la plus rapide : **la plus spécifique**.

```
 Table de routage :
 ┌──────────────────┬─────────────┬───────────┐
 │ Destination      │ Passerelle  │ Interface │
 ├──────────────────┼─────────────┼───────────┤
 │ 0.0.0.0/0        │ 10.0.0.1    │ eth0      │  ← défaut, préfixe 0
 │ 10.0.0.0/8       │ 10.0.0.1    │ eth0      │  ← préfixe 8
 │ 10.42.0.0/16     │ 10.0.0.9    │ eth1      │  ← préfixe 16
 │ 10.42.7.0/24     │ 10.0.0.20   │ eth2      │  ← préfixe 24
 └──────────────────┴─────────────┴───────────┘

 Paquet pour 10.42.7.55  →  4 entrées matchent  →  on prend /24  →  eth2
 Paquet pour 10.42.9.55  →  3 entrées matchent  →  on prend /16  →  eth1
 Paquet pour  8.8.8.8    →  1 entrée  matche    →  on prend /0   →  eth0
```

> 🧠 **MÉMO** — **« Le plus précis gagne. »** Comme une adresse postale : « 12 rue des Lilas » l'emporte
> toujours sur « France ».

> ❓ **RETIENS ÇA** — Deux routes matchent un paquet, l'une en /16 l'autre en /24. Laquelle est utilisée ?
> <details><summary>→ réponse</summary><br>La <b>/24</b> — <i>longest prefix match</i>. Le préfixe le plus long est le plus spécifique et gagne toujours, quelle que soit la métrique.</details>

Piège cloud majeur : si ton VPC est en `10.0.0.0/16` et que tu ajoutes une route `10.0.5.0/24` vers un VPN,
**le VPN gagne** pour ces adresses, y compris à l'intérieur du VPC. Beaucoup de « pourquoi mon instance ne
joint plus sa voisine » viennent de là.

---

## 10. IPv6

### 10.1 Pourquoi

2³² = 4,3 milliards, et c'est fini depuis 2011 (l'IANA a distribué ses derniers blocs). IPv6 utilise
**128 bits** : 2¹²⁸ ≈ **3,4 × 10³⁸** adresses, soit environ **10²⁸ par être humain**. On ne les épuisera pas.
Mais IPv6 n'est pas « IPv4 avec plus de bits ». Il change des choses structurelles :

| | IPv4 | IPv6 |
|---|---|---|
| Taille d'en-tête | 20-60 o (variable) | **40 o fixe** |
| Checksum d'en-tête | oui, recalculé à chaque saut | **supprimé** |
| Fragmentation | source **et** routeurs | **source uniquement** (en-tête d'extension) |
| Broadcast | oui | **supprimé** — remplacé par du multicast |
| ARP | oui | remplacé par **NDP** (ICMPv6) |
| Configuration auto | DHCP | **SLAAC** (+ DHCPv6 en option) |
| MTU minimum garanti | 68 o (576 recommandé) | **1280 o** |
| NAT | omniprésent | prévu inutile (adresses publiques partout) |

### 10.2 L'en-tête IPv6

```
 ┌────────┬──────────────┬───────────────────────────────────────┐
 │Version │Traffic Class │            Flow Label                 │
 │  (4b)  │     (8b)     │              (20b)                    │
 ├────────┴──────────────┼──────────────────┬────────────────────┤
 │    Payload Length     │   Next Header    │    Hop Limit       │
 │        (16b)          │      (8b)        │       (8b)         │
 ├───────────────────────┴──────────────────┴────────────────────┤
 │                                                               │
 │                  Source Address (128 bits)                    │
 │                                                               │
 ├───────────────────────────────────────────────────────────────┤
 │                                                               │
 │               Destination Address (128 bits)                  │
 │                                                               │
 └───────────────────────────────────────────────────────────────┘
                                                  Total : 40 octets FIXE
```

Correspondances : **Traffic Class** ≈ DSCP+ECN · **Next Header** ≈ Protocol · **Hop Limit** ≈ TTL ·
**Payload Length** = longueur des **données seules** (contrairement à Total Length en IPv4). Le **Flow Label**
(20 bits) est nouveau : il identifie un flux pour que les routeurs répartissent la charge (ECMP) sans ouvrir
la couche 4 — utile quand elle est chiffrée.

> ❓ **RETIENS ÇA** — Différence entre Total Length (IPv4) et Payload Length (IPv6) ?
> <details><summary>→ réponse</summary><br><b>Total Length inclut l'en-tête IPv4</b> ; <b>Payload Length exclut</b> les 40 octets de l'en-tête IPv6 et ne compte que la charge utile (extensions comprises).</details>

### 10.3 Notation et abréviation

128 bits écrits en **8 groupes de 16 bits en hexadécimal**, séparés par des `:`. Deux règles d'abréviation,
et deux seulement : (1) **supprimer les zéros de tête** de chaque groupe (`0db8` → `db8`, `0000` → `0`) ;
(2) **remplacer UNE seule suite de groupes entièrement nuls** par `::`.

```
 Complet :   2001:0db8:0000:0000:0000:ff00:0042:8329
 Règle 1 :   2001: db8:   0:   0:   0:ff00:  42:8329
 Règle 2 :   2001:db8::ff00:42:8329            ← forme canonique
```

> ⚠️ **PIÈGE** — **`::` ne peut apparaître qu'une seule fois** dans une adresse. `2001::25de::cade` est
> **invalide** : impossible de savoir combien de groupes nuls sont dans chaque `::`. Si l'adresse a deux
> suites de zéros, on abrège **la plus longue** (et en cas d'égalité, la première).

Quelques adresses à reconnaître :

| Adresse | Forme longue | Rôle |
|---|---|---|
| `::1` | 0000:…:0001 | **loopback** (= 127.0.0.1) |
| `::` | tout à zéro | **non spécifiée** (= 0.0.0.0) |
| `fe80::1` | fe80:0000:…:0001 | **link-local** |
| `ff02::1` | — | tous les nœuds du lien (≈ broadcast) |
| `ff02::2` | — | tous les routeurs du lien |
| `2001:db8::/32` | — | **documentation** (RFC 3849) — l'équivalent de 192.0.2.0/24 |

**Dans une URL**, on encadre l'adresse de crochets pour ne pas confondre les `:` avec celui du port :
`http://[2001:db8::1]:8080/`.

### 10.4 Le plan d'adressage : tout est en /64

Une adresse IPv6 unicast globale se lit en trois morceaux :

```
 2001:0db8:1234 : 5678 : 0000:0000:0000:0001
 └──────────────┘ └────┘ └────────────────────┘
   Préfixe global  Subnet     Interface ID
     (48 bits)     (16b)        (64 bits)
   du FAI / RIR   → 65 536    MAC ou aléatoire
                    subnets
```

| Préfixe | Qui | Ce que ça donne |
|---|---|---|
| **/32** | Attribution à un opérateur (RIR) | 65 536 sites en /48 |
| **/48** | Un site, une entreprise | **65 536 subnets** en /64 |
| **/56** | Un particulier (fibre) | 256 subnets en /64 |
| **/64** | **UN réseau, toujours** | 2⁶⁴ = 1,8 × 10¹⁹ hôtes |
| /127 | Lien point-à-point routeur↔routeur | RFC 6164 |
| /128 | Une adresse unique (loopback, route d'hôte) | — |

> ⚠️ **PIÈGE** — **On ne subnette jamais plus fin qu'un /64 sur un réseau d'hôtes.** SLAAC exige exactement
> 64 bits d'Interface ID : un /80 ou un /100 casse l'autoconfiguration. Un LAN de 3 machines prend un /64,
> comme un LAN de 10 000 — un seul /48 de site contient déjà 65 536 réseaux /64, il n'y a rien à économiser.

Les grandes plages :

| Plage | Nom | Équivalent IPv4 |
|---|---|---|
| **2000::/3** | GUA — Global Unicast (routable Internet) | adresses publiques |
| **fc00::/7** (en pratique **fd00::/8**) | ULA — Unique Local | RFC 1918 |
| **fe80::/10** (en pratique **fe80::/64**) | Link-local | 169.254.0.0/16 |
| **ff00::/8** | Multicast | 224.0.0.0/4 |
| `::1/128` | Loopback | 127.0.0.1 |

> 🧠 **MÉMO** — **« 2 = Internet, f-d = privé, f-e-8 = local au câble, f-f = multicast. »**
> Une adresse qui commence par `2` ou `3` est publique. Par `fd`, elle est privée. Par `fe80`, elle ne sort
> pas du lien. Par `ff`, c'est du multicast.

> ❓ **RETIENS ÇA** — Quelle est la taille de subnet standard en IPv6 pour un LAN, et pourquoi pas plus petit ?
> <details><summary>→ réponse</summary><br><b>/64</b>, toujours. Parce que SLAAC construit l'Interface ID sur exactement <b>64 bits</b>. Plus fin casse l'autoconfiguration et la détection d'adresse dupliquée.</details>

### 10.5 Link-local : l'adresse que tu ne peux pas ne pas avoir

Toute interface IPv6 active possède **automatiquement** une adresse `fe80::/64`, sans DHCP ni routeur. Elle
sert au dialogue local : découverte de voisins, annonces de routeur, protocoles de routage (OSPFv3 et BGP
peuvent s'appairer en link-local). Elle n'est **pas routable** — elle ne sort jamais du lien. Conséquence :
la même `fe80::1` peut exister sur dix interfaces, il faut donc préciser laquelle avec le suffixe `%` :

```bash
ping6 fe80::1%eth0        # « le fe80::1 qui est sur eth0 »
ssh user@[fe80::1%eth0]   # le "zone index" est obligatoire
```

> ⚠️ **PIÈGE** — Une interface IPv6 a **plusieurs adresses simultanément** et c'est normal : une link-local
> `fe80::…`, une ou plusieurs globales `2001:…`, éventuellement une ULA `fd…`, plus des adresses temporaires
> (RFC 4941) qui changent toutes les 24 h. En IPv4 on raisonne « une IP par interface » ; en IPv6, non.

### 10.6 SLAAC — l'autoconfiguration, étape par étape

Le problème : comment une machine obtient-elle une adresse sans serveur DHCP ?

```
  Machine                                             Routeur
     │                                                   │
     │ 1. Fabrique fe80::<InterfaceID>  (link-local)     │
     │                                                   │
     │ 2. DAD : NS vers ff02::1:ff<24 bits de son ID>    │
     │─────────────── ICMPv6 type 135 ─────────────────► │
     │    « quelqu'un utilise-t-il cette adresse ? »     │
     │    (pas de réponse = adresse libre) ✔             │
     │                                                   │
     │ 3. RS — Router Solicitation vers ff02::2          │
     │─────────────── ICMPv6 type 133 ─────────────────► │
     │    « y a-t-il un routeur ici ? »                  │
     │                                                   │
     │ 4. RA — Router Advertisement                      │
     │ ◄────────────── ICMPv6 type 134 ──────────────────│
     │    préfixe 2001:db8:1:42::/64, MTU, durée de vie, │
     │    flags M et O, et « je suis ta passerelle »     │
     │                                                   │
     │ 5. Adresse globale = préfixe reçu + InterfaceID   │
     │    Passerelle par défaut = fe80:: du routeur      │
     ▼                                                   ▼
```

Trois façons de fabriquer l'**Interface ID** de 64 bits :

- **EUI-64** (historique) : prendre la MAC de 48 bits, **insérer `fffe` au milieu**, **inverser le 7ᵉ bit**
  (bit U/L). MAC `00:1a:2b:3c:4d:5e` → `021a:2bff:fe3c:4d5e`. Problème : l'adresse trace la carte réseau
  partout dans le monde. **Vie privée nulle.**
- **Temporaires (RFC 4941)** : ID aléatoire renouvelé (24 h par défaut) pour le trafic sortant — le défaut
  des OS modernes. **Stable-privacy (RFC 7217)** : ID pseudo-aléatoire stable, différent par réseau.

Les **flags du RA** décident du modèle :

| Flag | Nom | Effet |
|---|---|---|
| **A** | Autonomous | La machine peut fabriquer son adresse depuis le préfixe (SLAAC pur). |
| **M** | Managed | Utilise **DHCPv6** pour l'adresse. |
| **O** | Other config | Prends l'adresse par SLAAC, mais **DNS et autres options via DHCPv6**. |

> ❓ **RETIENS ÇA** — Quels types ICMPv6 pour Router Solicitation et Router Advertisement ?
> <details><summary>→ réponse</summary><br><b>RS = 133</b>, <b>RA = 134</b>. Et pour NDP : <b>NS = 135</b> (Neighbor Solicitation, remplace la requête ARP), <b>NA = 136</b> (Neighbor Advertisement, la réponse). Mnémonique : 133-134-135-136 se suivent, RS→RA→NS→NA.</details>

> ⚠️ **PIÈGE** — **Bloquer tout ICMPv6 casse IPv6.** En IPv4, filtrer ICMP dégrade (PMTUD cassé) ; en IPv6,
> ça **empêche le réseau de fonctionner** : plus de NDP, donc plus de résolution d'adresse, plus de RA, donc
> plus d'adresse ni de route. La RFC 4890 liste ce qu'il faut impérativement laisser passer.

### 10.7 Dual-stack et cohabitation

La stratégie de transition dominante, c'est le **dual-stack** : deux piles, deux adresses, deux tables de
routage, et le choix se fait sur ce que renvoie le DNS — un enregistrement **A** (IPv4) et/ou **AAAA** (IPv6).
**Happy Eyeballs (RFC 8305)** lance les deux connexions presque en parallèle, avec une légère avance à IPv6,
et garde celle qui répond la première : c'est pour ça qu'un IPv6 cassé ne se voit plus (juste ~250 ms de
latence en plus). **NAT64/DNS64** sert au réseau IPv6-only qui doit joindre l'IPv4 : le DNS64 synthétise un
AAAA en `64:ff9b::/96`, la passerelle NAT64 traduit. C'est ce que fait un réseau mobile moderne.

> ❓ **RETIENS ÇA** — Quel type d'enregistrement DNS pour une adresse IPv6 ?
> <details><summary>→ réponse</summary><br><b>AAAA</b> (« quad-A »). A = 32 bits, AAAA = 4 × 32 = 128 bits. Le nom vient de là.</details>

---

## 11. ICMP — le canal de service d'IP

IP ne garantit rien : ni la livraison, ni l'ordre, ni la notification d'échec. **ICMP** (protocole **1**)
permet à un routeur de dire « ça n'est pas passé, et voici pourquoi ». Ce n'est pas de la couche 4 : ICMP est
encapsulé directement dans IP et n'a **aucun numéro de port**.

Un message ICMP contient toujours **l'en-tête IP du paquet fautif + les 8 premiers octets de sa charge** — de
quoi retrouver les ports TCP/UDP, donc la connexion concernée.

### 11.1 Les types à connaître

| Type | Code | Nom | Quand |
|---|---|---|---|
| **8** | 0 | Echo Request | `ping` sortant |
| **0** | 0 | Echo Reply | réponse au `ping` |
| **3** | 0 | Destination Unreachable — network | pas de route |
| **3** | 1 | — host | ARP sans réponse sur le dernier segment |
| **3** | 3 | — **port** | aucun processus n'écoute (UDP) |
| **3** | **4** | — **Fragmentation Needed and DF Set** | **PMTU Discovery** |
| **3** | 13 | — administratively prohibited | un pare-feu a REJETÉ (pas DROP) |
| **5** | 0/1 | Redirect | « passe plutôt par ce routeur » |
| **11** | **0** | **Time Exceeded — TTL exceeded in transit** | **traceroute** |
| 11 | 1 | — fragment reassembly time exceeded | fragment manquant |
| 12 | 0 | Parameter Problem | en-tête invalide |

> 🧠 **MÉMO** — **8 → 0** : la question part en 8, la réponse revient en 0. **11 = traceroute**
> (« onze sauts »). **3/4 = MTU**, la plus importante en production.

### 11.2 Ping

```
 ping 10.0.0.5
   ──► Echo Request (type 8) : ID, séquence, payload 56 o
       + 8 o d'en-tête ICMP + 20 o d'en-tête IP = 84 o de paquet IP
   ◄── Echo Reply   (type 0) : même payload recopié tel quel

 64 bytes from 10.0.0.5: icmp_seq=1 ttl=63 time=0.412 ms
                                       ^^^^^      ^^^^^^^^
                              64−63 = 1 saut     RTT aller-retour
```

Le « 64 bytes » de Linux compte 56 octets de payload + 8 d'en-tête ICMP. La taille par défaut de `-s` est
bien **56**, d'où un paquet IP de **84 octets** et une trame Ethernet de 98.

> ⚠️ **PIÈGE** — « Le ping ne passe pas donc le réseau est cassé. » Non. **ICMP est très souvent filtré**
> volontairement (clouds, pare-feux). Un service peut parfaitement répondre en TCP sur le port 443 alors que
> le ping est bloqué. Teste avec `nc -zv host port` ou `curl`, pas seulement avec `ping`.

### 11.3 Traceroute

L'astuce : envoyer des paquets avec un **TTL croissant** et écouter les ICMP *Time Exceeded* qui reviennent.

```
 TTL=1 ┌────┐        ┌────┐        ┌────┐        ┌──────┐
  ───► │ R1 │        │ R2 │        │ R3 │        │ Dest │
       └─┬──┘        └────┘        └────┘        └──────┘
         │ TTL→0 → ICMP type 11 depuis R1        Saut 1 identifié
         ▼
 TTL=2   ok ────────► TTL→0 → ICMP type 11 depuis R2   Saut 2
 TTL=3   ok ────────► ok ────────► ICMP 11 depuis R3   Saut 3
 TTL=4   ok ────────► ok ────────► ok ──────► Dest → ICMP type 3 code 3
                                              (port unreachable) = ARRIVÉ
```

Le traceroute Unix classique envoie de l'**UDP vers des ports improbables (33434+)** pour que la destination
réponde *port unreachable* et signale l'arrivée. Windows `tracert` et `traceroute -I` utilisent ICMP Echo,
`traceroute -T` du TCP SYN (le plus fiable à travers les pare-feux). Des `* * *` ne veulent **pas** dire que
le paquet est perdu : le routeur de ce saut ne génère pas d'ICMP ou le rate-limite. Si les sauts suivants
répondent, tout va bien.

> ❓ **RETIENS ÇA** — Sur quel mécanisme repose traceroute ?
> <details><summary>→ réponse</summary><br>L'incrémentation du <b>TTL</b> : chaque routeur qui décrémente à zéro renvoie un <b>ICMP Time Exceeded (type 11, code 0)</b> qui révèle son adresse.</details>

### 11.4 Path MTU Discovery — et le trou noir

Le mécanisme : (1) l'émetteur envoie ses paquets avec le bit **DF** à 1, à la taille de son MTU local (1500) ;
(2) un routeur dont le lien de sortie a un MTU plus petit (1450 sur un tunnel VXLAN) ne peut ni fragmenter
(DF=1) ni faire passer — il **jette** et renvoie **ICMP type 3 code 4** en indiquant le MTU du prochain saut ;
(3) l'émetteur mémorise ce PMTU pour cette destination et réduit ses paquets.

**Le trou noir de PMTU** est LA panne réseau la plus perverse pour un data engineer :

```
 Si l'ICMP 3/4 est FILTRÉ quelque part sur le chemin :
   handshake TCP (paquets de 60 o)   ✔ PASSE
   requête HTTP courte (200 o)       ✔ PASSE
   réponse volumineuse (1500 o)      ✘ JETÉE
   retransmission, même taille       ✘ JETÉE  → connexion FIGÉE, puis timeout

 Signature : « ping OK, ssh OK, mais le transfert de gros fichiers gèle »
```

**Le test manuel**, à connaître par cœur :

```bash
ping -M do -s 1472 8.8.8.8     # 1472 + 8 (ICMP) + 20 (IP) = 1500 exactement
# « Frag needed and DF set (mtu = 1450) » → ton PMTU réel est 1450
ping -M do -s 1422 8.8.8.8     # 1422 + 28 = 1450 → passe
```

**Le correctif** : abaisser le MTU des interfaces, ou faire du **MSS clamping**
(`iptables -t mangle -A FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu`), qui réécrit
l'option MSS dans le SYN pour que TCP ne demande jamais plus que ce qui passe. Les overheads à mémoriser :

| Encapsulation | Overhead | MTU interne sur un underlay 1500 |
|---|---|---|
| **VXLAN** | **50 o** | **1450** |
| GENEVE | ~50 o (variable) | ~1450 |
| GRE | 24 o | 1476 |
| IP-in-IP | 20 o | 1480 |
| IPsec ESP (tunnel) | ~50-60 o | ~1440 |
| WireGuard | 60 o (IPv4) · 80 o (IPv6) | 1440 en IPv4 · **1420** = défaut `wg-quick` (marge IPv6) |
| PPPoE | 8 o | 1492 |

Et les MSS : **MSS = MTU − 40** en IPv4 (20 IP + 20 TCP) → **1460** sur Ethernet standard.
En IPv6 : **MSS = MTU − 60** (40 IPv6 + 20 TCP) → **1440**.

> ❓ **RETIENS ÇA** — Quel message ICMP porte le PMTU en IPv4 ? Et en IPv6 ?
> <details><summary>→ réponse</summary><br>IPv4 : <b>ICMP type 3, code 4</b> (Destination Unreachable / Fragmentation Needed). IPv6 : <b>ICMPv6 type 2</b> (Packet Too Big). En IPv6 le PMTUD est <b>obligatoire</b> puisque les routeurs ne fragmentent pas.</details>

### 11.5 ICMPv6 — plus qu'un ICMP

| Type | Rôle |
|---|---|
| 1 | Destination Unreachable |
| **2** | **Packet Too Big** (PMTUD, obligatoire) |
| 3 | Time Exceeded (traceroute) |
| 4 | Parameter Problem |
| **128 / 129** | **Echo Request / Reply** (ping6) |
| **133 / 134** | **Router Solicitation / Advertisement** |
| **135 / 136** | **Neighbor Solicitation / Advertisement** (remplace ARP) |
| 137 | Redirect |

---

## 12. Ce qui casse en vrai

### 12.1 Le chevauchement de CIDR entre VPC

**Le scénario.** L'équipe data a un VPC `10.0.0.0/16` sur AWS. L'équipe plateforme a créé le sien il y a
deux ans, aussi en `10.0.0.0/16` (c'est la valeur par défaut proposée par la console). Un jour, il faut que
ton pipeline lise une base dans l'autre VPC. Tu demandes un peering.

**Le résultat** : le peering est **refusé**. AWS et GCP interdisent d'appairer deux VPC aux CIDR
chevauchants, parce que la table de routage serait ambiguë : quand une instance envoie vers `10.0.3.7`,
s'agit-il de la locale ou de la distante ? Le *longest prefix match* ne peut pas trancher.

```
 VPC-A 10.0.0.0/16 ──── ✘ PEERING IMPOSSIBLE ──── VPC-B 10.0.0.0/16

 Contournements :
  1. Re-adresser un des deux VPC            → propre, coûteux (tout redéployer)
  2. Ajouter un CIDR secondaire non chevauchant + y mettre les subnets exposés
  3. Transit Gateway / Cloud WAN            → ne règle PAS le chevauchement
  4. PrivateLink / Service Endpoint         → expose UN service : SOUVENT LA BONNE RÉPONSE
  5. NAT 1:1 derrière un boîtier            → ça marche, c'est illisible, ça se paie à vie
```

**La leçon métier** : le plan d'adressage est une **décision d'architecture**, prise une fois, documentée
dans une IPAM, jamais laissée à l'auto-complétion de la console. Règle qui sauve : un **/16 distinct par
environnement et par région** dans le `10.0.0.0/8`. Et n'utilise **jamais** `10.0.0.0/16` — c'est le défaut,
donc celui que tout le monde a déjà pris.

> ⚠️ **PIÈGE** — Le chevauchement n'a pas besoin d'être exact pour bloquer : `10.0.0.0/16` et `10.0.5.0/24`
> se chevauchent aussi. La règle est : **aucune intersection**, même partielle.

### 12.2 L'épuisement d'un /24 dans un cluster Kubernetes

**Le mécanisme.** Kubernetes attribue à chaque nœud un **podCIDR**, par défaut un **/24**
(`--node-cidr-mask-size`). Les pods du nœud puisent dedans.

```
 Cluster CIDR 10.244.0.0/16 (65 536 adr.) · podCIDR /24 par nœud (256 adr.)
 → nombre MAXIMUM de nœuds : 2^(24−16) = 256. Point.

 node-1  10.244.0.0/24  ·  node-2  10.244.1.0/24  ·  …  ·  node-256  10.244.255.0/24
 node-257 ✘ AUCUN CIDR LIBRE → nœud NotReady, aucun pod ne s'y planifie
```

**Les deux murs indépendants qu'on confond tout le temps :**

| Mur | Cause | Symptôme |
|---|---|---|
| **Cluster CIDR épuisé** | plus de /24 libre pour un nouveau nœud | le **nœud** reste `NotReady`, `CIDRNotAvailable` |
| **podCIDR d'un nœud épuisé** | trop de pods sur ce nœud | le **pod** reste `ContainerCreating`, « failed to allocate IP » |

Troisième limite, qui n'est pas une histoire d'IP : `maxPods` du kubelet vaut **110 par défaut**. Tu
n'atteindras donc jamais les 254 IP d'un /24 sans changer ce paramètre.

**Le cas AWS VPC CNI**, celui d'EKS : les pods reçoivent de **vraies IP du subnet VPC**, pas d'un overlay.
Donc **le nombre de pods est limité par la taille du subnet** et par le nombre d'ENI par type d'instance.

```
 pods max par nœud = (ENI max × (IP par ENI − 1)) + 2
   m5.large   : 3 × (10 − 1) + 2 =  29 pods
   m5.4xlarge : 8 × (30 − 1) + 2 = 234 pods (plafonné par maxPods à 110)

 Et chaque pod CONSOMME une IP du subnet :
   subnet /24 → 251 IP utilisables → ~8 nœuds m5.large avec leurs pods. C'est tout.
```

**Concrètement** : un job Spark demande 300 exécuteurs. Les 120 premiers pods démarrent, les autres restent
`Pending` avec `FailedCreatePodSandBox: failed to assign an IP address to container`. Le cluster a du CPU et
de la RAM libres — il n'a plus d'adresses. Tu cherches un problème de scheduling ; c'était du subnetting.

**Les correctifs** : **ajouter un CIDR secondaire** au VPC, y compris en `100.64.0.0/10` CGNAT (pratique
recommandée par AWS) ; activer le **prefix delegation** (chaque ENI reçoit un /28 d'un coup, densité de pods
×16 environ) ; ou passer à un CNI overlay (Calico VXLAN, Cilium) qui découple les IP de pods du VPC — au
prix des 50 octets de MTU vus plus haut.

> ❓ **RETIENS ÇA** — Cluster CIDR /16 et podCIDR /24 par nœud : combien de nœuds au maximum ?
> <details><summary>→ réponse</summary><br>2^(24−16) = <b>256 nœuds</b>. Le 257ᵉ ne recevra aucun podCIDR et restera NotReady.</details>

### 12.3 Latence : ce que le routage te coûte vraiment

Le subnetting ne change pas la latence, mais **la topologie L3 si**. Les ordres de grandeur à avoir en tête :

| Trajet | RTT typique | | Trajet | RTT typique |
|---|---|---|---|---|
| Loopback | < 0,05 ms | | Paris ↔ Francfort | ~10 ms |
| Même AZ | 0,1 – 0,5 ms | | Paris ↔ us-east-1 | 80 – 90 ms |
| Inter-AZ, même région | 0,5 – 2 ms | | Paris ↔ Singapour | 160 – 180 ms |
| Un saut de routeur en plus | 0,01 – 0,1 ms | | NAT Gateway / firewall | 0,1 – 1 ms |

Physique de base : la lumière dans la fibre parcourt ~200 000 km/s, soit **5 µs par kilomètre**.
**1000 km aller-retour = 10 ms incompressibles.** Si ton driver Spark est à Paris et tes exécuteurs en
Virginie, chaque aller-retour de contrôle coûte 85 ms, et un job en fait des milliers.

> 🧠 **MÉMO** — **« 5 microsecondes par kilomètre, dans un sens. »** Multiplie par 2 pour l'aller-retour,
> et ajoute 30 à 50 % pour les détours réels de la fibre.

---

## 13. Questions d'entretien

**1. Explique la différence entre une adresse MAC et une adresse IP, et pourquoi les deux existent.**
La MAC est plate, gravée dans la carte, et n'a de sens que sur un segment L2 : elle livre une trame au
prochain équipement. L'IP est hiérarchique (partie réseau + partie hôte), attribuée selon la topologie, et
identifie la destination finale de bout en bout. Aucune ne peut faire le travail de l'autre : router sur des
MAC exigerait une table mondiale de toutes les cartes réseau ; livrer sur un câble avec une IP obligerait
chaque technologie de lien à comprendre IP. Sur un trajet, les IP ne changent pas (sauf NAT), le couple de
MAC est réécrit à chaque saut.

**2. Un paquet part de 10.1.1.5 vers 172.20.4.9. Que change chaque routeur ?**
Il décrémente le **TTL** de 1, **recalcule le checksum d'en-tête** (obligatoire puisque le TTL a changé),
remplace complètement l'**en-tête de couche 2** (nouvelles MAC adaptées au lien de sortie), et fragmente si
le MTU de sortie est plus petit et que DF est à 0. Il ne touche ni aux adresses IP, ni aux ports, ni aux
données — sauf s'il fait du NAT, auquel cas il réécrit adresse et port source et doit corriger le checksum
TCP/UDP à cause du pseudo-en-tête.

**3. Qu'est-ce que le CIDR, et qu'a-t-il résolu ?**
CIDR (RFC 1519, 1993) supprime les classes A/B/C et rend la frontière réseau/hôte arbitraire, transportée
explicitement par un préfixe. Il a résolu deux crises simultanées : le gaspillage d'adresses (une entreprise
de 300 machines prenait une classe B de 65 534 adresses faute de taille intermédiaire) et l'explosion des
tables de routage, grâce à l'**agrégation** — annoncer quatre /24 contigus et alignés sous la forme d'un
seul /22. Sans CIDR, la table BGP mondiale aurait été ingérable dès les années 90.

**4. Combien d'hôtes utilisables dans un /26 ? Et pourquoi pas 64 ?**
62. Un /26 contient 2^(32−26) = 64 adresses, mais deux ne sont pas attribuables : la première (bits hôte à 0)
est l'**adresse réseau**, la dernière (bits hôte à 1) est le **broadcast dirigé**. Deux exceptions : le /31
(RFC 3021) utilise ses deux adresses sur un lien point-à-point où le broadcast n'a pas de sens, et le /32
désigne une route d'hôte. En cloud AWS, on retire 5 adresses et non 2.

**5. Donne le réseau, le broadcast et la plage utilisable de 192.168.37.201/26.**
Masque 255.255.255.192, octet intéressant le quatrième, taille de bloc 256 − 192 = 64. Les sous-réseaux
commencent en .0, .64, .128, .192 ; 201 tombe dans le dernier. Réseau **192.168.37.192/26**, broadcast
**192.168.37.255**, plage utilisable **.193 à .254**, 62 hôtes. Vérification binaire : 201 = 11001001, ET
avec 11000000 donne 192.

**6. Pourquoi tout est-il en /64 en IPv6 alors que c'est un gâchis apparent ?**
Parce que SLAAC construit l'Interface ID sur exactement 64 bits, par EUI-64 ou par tirage aléatoire, et que
la détection d'adresse dupliquée et le multicast sollicité reposent sur cette structure : un /80 casserait
l'autoconfiguration. Le « gâchis » n'en est pas un — un /48 de site contient 65 536 subnets /64, et la
contrainte n'est plus la quantité d'adresses mais la lisibilité du plan. Seule exception : les liens
point-à-point entre routeurs, en /127 (RFC 6164).

**7. Comment fonctionne traceroute ?**
Il exploite le TTL : une salve avec TTL = 1, le premier routeur décrémente à zéro, jette le paquet et renvoie
un ICMP Time Exceeded (type 11, code 0) qui révèle son adresse ; puis TTL = 2, et ainsi de suite. L'arrivée
se détecte autrement : le traceroute Unix vise des ports UDP improbables (33434+) et attend un ICMP Port
Unreachable (type 3, code 3). Les `* * *` signifient qu'un routeur ne génère pas d'ICMP ou le rate-limite,
pas que le paquet est perdu.

**8. Qu'est-ce qu'un trou noir de PMTU, comment le reconnaître, comment le corriger ?**
Un routeur intermédiaire a un MTU plus petit que l'émetteur, reçoit un paquet avec le bit DF, le jette et
renvoie un ICMP type 3 code 4 — mais cet ICMP est filtré par un pare-feu. L'émetteur n'apprend jamais le bon
MTU et retransmet indéfiniment des paquets trop gros. Signature caractéristique : le handshake TCP et les
petites requêtes passent, les gros transferts gèlent. On le confirme avec `ping -M do -s 1472 <cible>` en
descendant la taille. On le corrige par du MSS clamping ou en abaissant le MTU des interfaces — typiquement
1450 derrière du VXLAN, 1420 derrière WireGuard.

**9. Deux VPC ont le même CIDR 10.0.0.0/16. Que se passe-t-il et que fais-tu ?**
Le peering est refusé : avec des préfixes identiques la table de routage serait ambiguë, le *longest prefix
match* ne pouvant départager la destination locale de la distante. Les options, par ordre de propreté :
re-adresser l'un des deux VPC ; ajouter à l'un un CIDR secondaire non chevauchant et y déplacer les subnets
à exposer ; ou, souvent la bonne réponse en pratique, ne pas appairer du tout et exposer le seul service
concerné via PrivateLink, qui fonctionne malgré le chevauchement. La vraie leçon est en amont : le plan
d'adressage se décide une fois pour toute l'organisation et se documente dans une IPAM.

**10. Tu vois 169.254.10.3 sur une interface. Que conclus-tu ?**
Que la machine n'a pas obtenu de bail DHCP et s'est attribué une adresse APIPA (RFC 3927), link-local et non
routable. Le service DHCP est injoignable : câble débranché, mauvais VLAN, relais DHCP mal configuré, ou
serveur à court de baux. À ne pas confondre avec 169.254.169.254, l'adresse du service de métadonnées des
instances cloud — celle-là est normale et même vitale, puisque c'est par elle que l'instance récupère ses
credentials IAM.

---

## 14. Les 3 choses à retenir si tu ne retiens que ça

**1. Une adresse IP, c'est 32 bits coupés en deux par un masque — et le masque est la seule information qui
compte.** Sans lui, `10.4.130.9` ne veut rien dire : en /23 elle est voisine de `10.4.131.200`, en /24 non.
Tout le subnetting tient en trois gestes : **bloc = 256 − masque**, le réseau est le plus grand multiple du
bloc sous la valeur de l'octet, le broadcast est le multiple suivant moins un.

**2. Le routeur ne fait que trois choses à chaque paquet : décrémenter le TTL, recalculer le checksum,
réécrire l'en-tête L2 — et il choisit sa sortie par le *longest prefix match*.** L'IP survit au trajet, la
MAC est refaite à chaque saut, et c'est la route la **plus spécifique** qui gagne.

**3. En production, la couche 3 casse toujours de la même façon : chevauchement d'adresses, bloc épuisé, ou
MTU mal aligné.** Le plan d'adressage est une décision d'architecture, pas un réglage — un /16 choisi à la
légère coûte un re-adressage complet deux ans plus tard, un /24 de subnet EKS bloque un job Spark alors
qu'il reste du CPU. Surdimensionne, documente, et n'utilise jamais la valeur par défaut de la console.
