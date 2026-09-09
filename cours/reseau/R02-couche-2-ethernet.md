# R02 — Couche 2 : Ethernet, MAC, ARP, commutation, VLAN, STP

> **Ce que tu sauras faire à la fin**
> - Décoder à la main une trame Ethernet II en hexadécimal, champ par champ, tag 802.1Q compris.
> - Dérouler le dialogue ARP complet et reconnaître un ARP spoofing dans une capture.
> - Reconstituer la table CAM d'un switch après une séquence de trames, et dire quand il *floode*.
> - Distinguer domaine de collision et domaine de broadcast, et dire ce qu'un VLAN découpe exactement.
> - Faire une élection STP complète (root bridge, root ports, ports bloqués) sur une topologie donnée.
> - Diagnostiquer un transfert Spark ou un pod K8s qui bloque à cause du MTU, et calculer le bon MSS.
>
> **Pourquoi ça compte dans ton poste**
> Un pipeline de données, c'est du transfert de gros volumes. Tout ce qui casse *silencieusement* un gros
> transfert vit en couche 2 : un MTU désaligné entre le VPC et l'overlay K8s, un VLAN qui isole la prod de
> ton cluster de calcul, un LACP qui ne répartit rien parce qu'un flux TCP ne peut pas dépasser un lien.
> Quand ton job Spark part en `FetchFailedException` alors que le `ping` répond, la réponse est ici.
> Côté IA réseau : table CAM, taux d'ARP et compteurs d'interface sont exactement les signaux qu'on donne
> à manger à un détecteur d'anomalies.
>
> **Prérequis** : `R01` (modèle en couches OSI/TCP-IP, encapsulation, notion de PDU).
> **Durée de lecture** : 75-90 min, papier et crayon à côté.

---

## 1. Le problème que résout la couche 2

Tu as un câble. Dessus, plusieurs machines. L'une veut parler à **une** autre. Trois problèmes surgissent :
**délimitation** (où commence un message dans un flux de bits ?), **adressage** (comment dire « c'est pour
toi et pas pour toi » alors que tout le monde reçoit tout ?), **intégrité** (un bit a-t-il été inversé ?).

La couche 2 ne fait rien d'autre que répondre à ces trois questions, **sur un seul segment**. Elle ne route
pas, ne connaît pas Internet, ne va jamais plus loin que l'équipement suivant. C'est sa force : simple, donc
très rapide, donc implémentée en silicium.

> 🧠 **MÉMO** — La couche 2 est un **coursier d'immeuble** : il monte un pli du 2e au 5e étage, il ignore ce
> qu'il y a dedans et il ne sortira jamais de l'immeuble. Le facteur (IP, couche 3) fait le trajet
> inter-villes ; le coursier fait chaque étage.

```
    Trajet de bout en bout : PC-A  →  R1  →  R2  →  Serveur-B
    ┌────────────────────────────────────────────────────────────┐
 L3 │  IP source 10.0.0.5  →  IP destination 172.16.4.9          │  ← ne change JAMAIS
    └────────────────────────────────────────────────────────────┘
    ┌───────────────┬───────────────┬────────────────────────────┐
 L2 │ MAC A → MAC R1│ MAC R1→MAC R2 │      MAC R2 → MAC B        │  ← réécrit à CHAQUE saut
    └───────────────┴───────────────┴────────────────────────────┘
       segment 1         segment 2            segment 3
```

C'est **la** phrase qui structure tout le module : **l'IP survit au trajet, la MAC est recréée à chaque
saut.** Un routeur, c'est une machine qui jette l'en-tête L2, lit l'IP, et fabrique un nouvel en-tête L2.

> ❓ **RETIENS ÇA** — Combien de fois la MAC destination change-t-elle sur un trajet à 3 sauts ?
> <details><summary>→ réponse</summary><br>3 fois, une par segment. L'IP destination, elle, ne change pas (sauf NAT). MAC = local, IP = bout en bout.</details>

> ⚠️ **PIÈGE** — « Le serveur voit mon adresse MAC. » **Faux** dès qu'il y a un routeur entre vous : il voit
> la MAC de son routeur de dernier saut. D'où le fait qu'une MAC n'est pas un identifiant utilisable sur
> Internet, et que le filtrage par MAC ne vaut que sur le LAN local.

---

## 2. La trame Ethernet II, champ par champ

### 2.1 Le format

Ethernet II (ou DIX) est le format universel. Le 802.3 pur (avec en-tête LLC/SNAP) ne survit que pour
quelques protocoles de contrôle comme STP.

```
 ┌────────────┬─────┬──────────┬──────────┬────────┬───────────────┬──────┐
 │ Préambule  │ SFD │ MAC dest │ MAC src  │  Type  │   Données     │ FCS  │
 │  7 octets  │  1  │    6     │    6     │   2    │  46 à 1500    │  4   │
 └────────────┴─────┴──────────┴──────────┴────────┴───────────────┴──────┘
  └── hors trame ──┘ └──────────── la TRAME : 64 à 1518 octets ───────────┘
                                    + 12 octets d'IFG (silence) avant la suivante
  Préambule : 10101010 × 7  → synchronise l'horloge du récepteur
  SFD       : 10101011      → « la trame commence maintenant »
```

Le **payload** porte le paquet L3 et il est **bourré à 46 octets** s'il est plus court. Le **FCS** est un
CRC-32 de contrôle. L'**IFG** est un silence obligatoire entre deux trames.

### 2.2 Les chiffres à graver

| Grandeur | Valeur |
|---|---|
| Trame minimale (sans tag) | **64 octets**, FCS compris, préambule exclu |
| Trame minimale avec tag 802.1Q | **68 octets** |
| Trame maximale standard | **1518 octets** (1522 avec tag 802.1Q) |
| Payload max = **MTU** | **1500 octets** |
| Overhead L2 pur | **18 octets** (6+6+2+4) |
| Overhead total sur le fil | **38 octets** (18 + 8 préambule/SFD + 12 IFG) |
| IFG | 96 temps-bit = 12 octets = 96 ns à 1 Gbit/s (9,6 µs à 10 Mbit/s) |

**Pourquoi 64 octets minimum ?** Héritage de CSMA/CD : une station devait détecter une collision *pendant*
qu'elle émettait encore. Le temps aller-retour sur le plus grand segment autorisé valait 512 temps-bit
= 64 octets ; une trame plus courte se serait terminée avant que la collision ne remonte. D'où le
**bourrage (padding)** à 46 octets de payload.

**Pourquoi 1500 maximum ?** Compromis des années 1980 : mémoire des cartes et temps d'occupation du média
partagé (à 10 Mbit/s, 1500 octets monopolisent le câble 1,2 ms). Ce chiffre n'a jamais bougé.

> ❓ **RETIENS ÇA** — Taille totale minimale et maximale d'une trame Ethernet II non taguée ?
> <details><summary>→ réponse</summary><br>64 à 1518 octets, FCS compris, préambule et SFD exclus. Payload : 46 à 1500.</details>

> ⚠️ **PIÈGE** — MTU ≠ taille de trame. Le **MTU de 1500 désigne le payload**. Une interface à MTU 1500
> émet des trames de 1518 octets. `ip link set eth0 mtu 9000` parle du payload : la trame fera 9018 octets.

### 2.3 EtherType : type ou longueur ?

Le champ de 2 octets est ambigu par construction. Règle : valeur **≤ 1500 (0x05DC)** → c'est une
**longueur** (802.3 + LLC) ; valeur **≥ 1536 (0x0600)** → c'est un **EtherType** (Ethernet II).

| EtherType | Protocole | | EtherType | Protocole |
|---|---|---|---|---|
| `0x0800` | IPv4 | | `0x8809` | Slow protocols (LACP) |
| `0x0806` | ARP | | `0x88CC` | LLDP |
| `0x86DD` | IPv6 | | `0x8847` | MPLS unicast |
| `0x8100` | Tag VLAN 802.1Q | | `0x8863`/`0x8864` | PPPoE découverte / session |
| `0x88A8` | QinQ / 802.1ad | | | |

> 🧠 **MÉMO** — Les quatre du quotidien : **08 00 = IPv4**, **08 06 = ARP**, **86 DD = IPv6**,
> **81 00 = VLAN**. En capture, dès que tu vois `8100`, les 4 octets suivants sont un tag et le vrai
> EtherType est 4 octets plus loin.

### 2.4 Le FCS et ce qu'il ne fait pas

CRC-32 calculé de la MAC destination au dernier octet de payload. Le récepteur recalcule et compare.
En cas d'écart : **la trame est jetée en silence**. Pas de retransmission, pas de notification. C'est TCP
(couche 4) qui s'en apercevra.

Conséquence opérationnelle : un câble abîmé ou un SFP sale fait grimper `rx_crc_errors`, et le débit TCP
s'effondre — TCP interprète les pertes comme de la congestion et réduit sa fenêtre. C'est le premier
compteur à regarder quand un transfert est lent sans raison : `ethtool -S eth0 | grep -i crc`.

> ❓ **RETIENS ÇA** — Que fait Ethernet quand le FCS est faux ?
> <details><summary>→ réponse</summary><br>Rien : il jette la trame silencieusement. Aucune retransmission en couche 2. C'est TCP qui détecte le trou.</details>

### 2.5 Rendement : le prix du protocole

Chaque trame coûte 38 octets d'overhead sur le fil (18 + 8 + 12).

| Payload | Taille sur le fil | Rendement | Trames/s à 1 Gbit/s |
|---|---|---|---|
| 46 o (mini) | 84 o | 54,8 % | **1 488 095** |
| 1500 o (MTU standard) | 1538 o | 97,5 % | **81 274** |
| 9000 o (jumbo) | 9038 o | 99,6 % | **13 830** |

Les **1,488 Mpps à 1 Gbit/s** (donc 14,88 Mpps à 10 Gbit/s) sont le chiffre de référence pour tester un
équipement à pleine charge en petites trames. Il tombe souvent en entretien.

---

## 3. Les adresses MAC

### 3.1 Structure

48 bits = 6 octets = 12 caractères hexa. Notée `00:1a:2b:3c:4d:5e` (Linux), `00-1A-2B-3C-4D-5E` (Windows),
`001a.2b3c.4d5e` (Cisco).

```
   00 : 1a : 2b : 3c : 4d : 5e
   └────┬─────┘   └────┬────┘
      OUI 24 bits    NIC 24 bits
   (le constructeur)  (le numéro de série)

   Zoom sur le PREMIER octet — 0x00 = 0000 0000
                                       ││
                                       │└─ bit I/G : 0 = unicast    1 = multicast
                                       └── bit U/L : 0 = universelle (OUI IEEE)
                                                     1 = locale (locally administered)
```

**OUI** : les 3 premiers octets, achetés à l'IEEE (`00:50:56` VMware, `52:54:00` QEMU/KVM, `02:42:ac`
Docker). **NIC** : les 3 derniers, attribués par le constructeur. Les deux bits de contrôle sont les deux
bits de poids faible du premier octet — donc lisibles dans le **deuxième chiffre hexadécimal** :

| 2e chiffre hexa | I/G | U/L | Signification |
|---|---|---|---|
| 0, 4, 8, C | 0 | 0 | Unicast, universelle (une vraie carte) |
| **2, 6, A, E** | 0 | 1 | Unicast, **locally administered** (VM, conteneur, MAC forgée) |
| 1, 5, 9, D | 1 | 0 | Multicast, universelle |
| 3, 7, B, F | 1 | 1 | Multicast, locale |

> 🧠 **MÉMO** — Le bit de poids faible du premier octet décide unicast/multicast : **premier octet pair =
> unicast, impair = multicast**. (`ff:ff:...` = 255, impair : le broadcast est bien le cas limite du
> multicast.) Et pour le locally administered : **2, 6, A, E**.

> ❓ **RETIENS ÇA** — `02:42:ac:11:00:02` : unicast ou multicast ? Universelle ou locale ?
> <details><summary>→ réponse</summary><br>02 = 0000 0010. Bit 0 = 0 → unicast. Bit 1 = 1 → locally administered. Typiquement une interface Docker.</details>

### 3.2 Les trois modes d'adressage

| Mode | Adresse | Qui reçoit | Traitement par le switch |
|---|---|---|---|
| **Unicast** | 1 destinataire | La carte concernée | Commuté vers le seul port utile |
| **Multicast** | Un groupe | Les cartes abonnées | Floodé (sauf IGMP snooping) |
| **Broadcast** | `ff:ff:ff:ff:ff:ff` | Tout le VLAN | Floodé sur tous les ports du VLAN |

| MAC multicast | Usage | | MAC multicast | Usage |
|---|---|---|---|---|
| `ff:ff:ff:ff:ff:ff` | Broadcast | | `01:00:0c:cc:cc:cc` | CDP / VTP (Cisco) |
| `01:80:c2:00:00:00` | BPDU STP / RSTP | | `01:00:5e:xx:xx:xx` | Multicast IPv4 mappé |
| `01:80:c2:00:00:02` | LACP | | `33:33:xx:xx:xx:xx` | Multicast IPv6 mappé |
| `01:80:c2:00:00:0e` | LLDP | | | |

**Mapping IPv4 multicast → MAC** : préfixe `01:00:5e`, bit 24 forcé à 0, puis les **23 bits de poids faible**
de l'IP. `224.0.0.1` → `01:00:5e:00:00:01`. L'IP multicast ayant 28 bits significatifs, **32 groupes IP
partagent la même MAC** — source réelle d'anomalies en multicast vidéo ou financier.
**IPv6** : préfixe `33:33` + les **32 bits de poids faible**. `ff02::1` → `33:33:00:00:00:01`.

> ⚠️ **PIÈGE** — Une carte filtre **en matériel** : elle ne remonte au système que sa propre MAC, les
> multicasts auxquels elle est abonnée, et le broadcast. Le **mode promiscuous** (ce que fait tcpdump)
> désactive ce filtre. Mais même en promiscuous, sur un switch tu ne vois pas le trafic des autres : il
> faut un **port mirroring / SPAN** ou un TAP.

### 3.3 MAC randomisée et MAC locale

Deux usages modernes du bit U/L. **Randomisation Wi-Fi** : Android, iOS et Windows génèrent une MAC locale
aléatoire par SSID pour empêcher le pistage — c'est ce qui a tué le filtrage par MAC. **Virtualisation** :
hyperviseurs et conteneurs fabriquent leurs MAC dans leur plage, uniques seulement localement — deux VM
clonées avec la même MAC sur un VLAN provoquent un *MAC flapping* qui rend le réseau erratique.

```bash
ip link show eth0                                   # link/ether + permaddr si spoofée
ip link set dev eth0 address 02:11:22:33:44:55
ethtool -P eth0                                     # adresse permanente gravée dans la carte
```

> ❓ **RETIENS ÇA** — Pourquoi le filtrage par MAC n'est-il pas une mesure de sécurité ?
> <details><summary>→ réponse</summary><br>Une MAC se change en une commande et circule en clair dans chaque trame : n'importe qui sur le segment peut la lire puis l'usurper.</details>

---

## 4. ARP : le pont entre l'IP et la MAC

### 4.1 Le problème

Ton application veut joindre `192.168.10.1`. La pile IP prépare le paquet, mais la carte a besoin d'une
**MAC destination** qu'elle n'a pas. Réponse : **on crie dans la pièce**. C'est ARP (RFC 826),
EtherType `0x0806`.

```
     PC-A                    (tout le VLAN)                    Routeur
  10.0.0.5                                                    10.0.0.1
     │──── ARP REQUEST, broadcast ff:ff:ff:ff:ff:ff ─────────────►│
     │     « Qui a 10.0.0.1 ? Dis-le à 10.0.0.5 / aa:bb:cc:00:00:05 »
     │     (tout le monde reçoit, seul 10.0.0.1 répond)          │
     │◄─── ARP REPLY, unicast vers aa:bb:cc:00:00:05 ─────────────│
     │     « 10.0.0.1, c'est moi : 11:22:33:44:55:66 »            │
   [cache ARP mis à jour] → le paquet IP part enfin
```

**La requête est un broadcast, la réponse est un unicast.** C'est pour ça qu'un LAN saturé d'ARP fait
souffrir tout le monde : chaque requête interrompt chaque CPU du domaine de broadcast.

### 4.2 Le format ARP, 28 octets

```
 ┌──────────────┬──────────────┬──────┬──────┬────────────┐
 │ Hardware Type│ Protocol Type│ HLEN │ PLEN │ Opération  │
 │    2 o (=1)  │ 2 o (=0x0800)│1 (=6)│1 (=4)│ 2 o (1 / 2)│
 ├──────────────┴──────────────┴──────┴──────┴────────────┤
 │ SHA — Sender Hardware Address             6 o          │
 │ SPA — Sender Protocol Address             4 o          │
 │ THA — Target Hardware Address             6 o          │
 │ TPA — Target Protocol Address             4 o          │
 └────────────────────────────────────────────────────────┘
   28 octets  →  trame = 14 + 28 = 42 o  →  bourrée à 60 + 4 de FCS = 64 o
   Opération : 1 = Request, 2 = Reply. Dans une requête, THA = 00:00:00:00:00:00.
```

> ❓ **RETIENS ÇA** — Taille de l'en-tête ARP et taille de la trame ARP sur le fil ?
> <details><summary>→ réponse</summary><br>En-tête ARP : 28 octets. Trame = 14 + 28 = 42 octets, donc bourrée à 64 (60 + 4 de FCS).</details>

### 4.3 Le cache ARP et la machine à états

```bash
ip neigh show          # 10.0.0.1 dev eth0 lladdr 11:22:33:44:55:66 REACHABLE
ip neigh flush all
ip neigh add 10.0.0.1 lladdr 11:22:33:44:55:66 dev eth0 nud permanent
```

```
     INCOMPLETE ──(reply reçue)──► REACHABLE ──(30 s sans preuve)──► STALE
         │                            ▲                                │
    (3 essais                         │                        (on doit émettre)
     sans reply)                      └────(reply)──── PROBE ◄──── DELAY
         ▼                                               │
       FAILED  ◄──────────────────────────────(3 échecs)─┘
```

| État | Sens | | Paramètre Linux | Défaut |
|---|---|---|---|---|
| `INCOMPLETE` | Requête envoyée, pas de réponse | | `base_reachable_time_ms` | **30 000 (30 s)**, tiré entre 0,5× et 1,5× |
| `REACHABLE` | Entrée fraîche et confirmée | | `gc_stale_time` | 60 s |
| `STALE` | Présente, non confirmée, utilisable | | `gc_thresh1/2/3` | **128 / 512 / 1024** |
| `DELAY` / `PROBE` | Attente, puis sondage unicast | | `mcast_solicit` / `ucast_solicit` | 3 / 3 |
| `FAILED` / `PERMANENT` | Ne répond pas / statique | | Cache ARP Cisco | **4 h (14 400 s)** |

> ⚠️ **PIÈGE — `gc_thresh3` en Kubernetes.** Un nœud dense (des centaines de pods, réseau plat) dépasse
> facilement 1024 voisins. Symptôme : `neighbour: arp_cache: neighbor table overflow!` dans `dmesg`, et des
> connexions qui échouent au hasard. Correctif : `net.ipv4.neigh.default.gc_thresh1/2/3` à 4096/8192/16384.
> Incident de production classique, et excellente réponse en entretien.

### 4.4 Gratuitous ARP

Un ARP que personne n'a demandé : une requête (ou réponse) où **SPA == TPA**, envoyée en broadcast.
Trois usages :

1. **Détection de conflit d'adresse** au démarrage.
2. **Bascule de haute disponibilité** — une IP virtuelle (VRRP, keepalived, failover PostgreSQL) change de
   machine. Le nouveau porteur émet un GARP : tous les caches ARP du VLAN et toutes les tables CAM se
   mettent à jour **immédiatement** au lieu d'attendre l'expiration. Sans GARP, la bascule prend des
   minutes ; avec, une seconde.
3. **Migration à chaud de VM** — l'hyperviseur émet un GARP pour que les switchs réapprennent le port.

```bash
arping -U -I eth0 -c 3 10.0.0.50    # -U = gratuitous (annonce non sollicitée)
arping -D -I eth0 -c 2 10.0.0.50    # -D = duplicate address detection
```

> ❓ **RETIENS ÇA** — Qu'est-ce qui distingue un gratuitous ARP d'un ARP normal ?
> <details><summary>→ réponse</summary><br>SPA == TPA : l'émetteur demande sa propre adresse. Il n'attend pas de réponse, il annonce. Usage principal : mise à jour immédiate des caches après une bascule HA ou une migration de VM.</details>

### 4.5 ARP spoofing (empoisonnement de cache)

ARP n'a **aucune authentification**. N'importe qui peut répondre à la place de n'importe qui, et même sans
qu'on ait rien demandé. La dernière réponse reçue écrase le cache.

```
         AVANT                                  APRÈS l'empoisonnement
  PC ──────────────► Routeur              PC ───────► ATTAQUANT ───────► Routeur
  cache PC :                              cache PC     : 10.0.0.1 → MAC_attaquant  ← mensonge
   10.0.0.1 → MAC_routeur                 cache routeur: 10.0.0.5 → MAC_attaquant  ← mensonge
                                          → l'attaquant relaie et lit tout (MITM)
```

L'attaquant envoie en boucle deux replies mensongères et active `ip_forward` pour que le trafic continue :
la victime ne voit rien, sinon quelques millisecondes de latence. **Signaux de détection** — ce sont les
features d'un détecteur d'anomalies : une IP associée à deux MAC dans un court intervalle ; un volume
anormal de replies non sollicitées ; un débit d'ARP/s hors distribution ; une MAC qui saute de port en port.

| Défense | Où | Efficacité |
|---|---|---|
| Entrées ARP statiques | Sur l'hôte | Forte mais ingérable à l'échelle |
| **DHCP Snooping + Dynamic ARP Inspection (DAI)** | Sur le switch | **La vraie réponse en entreprise** |
| Port security (limite de MAC/port) | Sur le switch | Limite MAC flooding et flapping |
| Chiffrement de bout en bout (TLS, mTLS) | Applicatif | Rend l'écoute inutile |

Principe de DAI : le switch construit une table de liaisons IP↔MAC↔port à partir du DHCP snooping, puis
**jette toute trame ARP qui la contredit** sur un port non fiable.

> ⚠️ **PIÈGE** — On croit qu'un switch protège du sniffing. Il protège du sniffing **passif** (il ne te
> copie pas le trafic des autres), pas de l'ARP spoofing, qui est une attaque **active** : la victime
> t'envoie son trafic volontairement, parce qu'elle croit que tu es le routeur.

---

## 5. Le switch : table CAM, apprentissage, flooding

### 5.1 L'algorithme complet — trois règles, c'est tout

Un hub recopie chaque trame sur tous les ports : tout le monde reçoit tout et le débit se divise. Comment
n'envoyer que sur le port utile, sans configuration ? Le switch **apprend en écoutant**.

```
Pour chaque trame reçue sur le port P :

  1) APPRENDRE : associer (MAC_source → port P) dans la table CAM. Rafraîchir le timer.

  2) DÉCIDER selon la MAC destination :
       ├─ broadcast / multicast              → FLOODER sur tous les ports du VLAN sauf P
       ├─ unicast connue, port = P           → FILTRER (jeter : même segment)
       ├─ unicast connue, port = Q ≠ P       → COMMUTER vers Q uniquement
       └─ unicast INCONNUE                   → FLOODER (unknown unicast flooding)

  3) OUBLIER : purger toute entrée non rafraîchie depuis l'aging time (300 s par défaut).
```

> 🧠 **MÉMO** — Le switch **apprend par la source, décide par la destination**. Phrase à réciter. Il apprend
> toujours, même si ensuite il jette la trame.

> ❓ **RETIENS ÇA** — Sur quelle adresse le switch apprend-il, sur laquelle décide-t-il ?
> <details><summary>→ réponse</summary><br>Il apprend sur la MAC source, il décide (commute ou floode) sur la MAC destination.</details>

### 5.2 Déroulé pas à pas

```
        ┌─────────────────────────────┐
   A ───┤ P1                       P3 ├─── C     Table CAM vide au départ
        │        SWITCH               │
   B ───┤ P2                       P4 ├─── D
        └─────────────────────────────┘
```

| # | Événement | Apprentissage | Décision | Table CAM après |
|---|---|---|---|---|
| 1 | A → B (B inconnue) | A ↔ P1 | **Flood** P2, P3, P4 | A:P1 |
| 2 | B → A (réponse) | B ↔ P2 | **Commute** vers P1 | A:P1, B:P2 |
| 3 | C → A | C ↔ P3 | **Commute** vers P1 | A:P1, B:P2, C:P3 |
| 4 | A → broadcast | (A déjà là) | **Flood** P2, P3, P4 | inchangée |
| 5 | D → A | D ↔ P4 | **Commute** vers P1 | table complète |

Le tout premier échange est **toujours** floodé, mais la réponse suffit à peupler la table : un LAN converge
en deux trames.

### 5.3 La table CAM en pratique

| Propriété | Valeur |
|---|---|
| Autres noms | MAC address table, FDB (*forwarding database*) |
| Contenu d'une entrée | VLAN, MAC, type (dynamique/statique), port |
| **Aging time par défaut** | **300 s (5 minutes)** |
| Taille — switch d'accès (Catalyst 2960) | ~8 000 entrées |
| Taille — switch datacenter | 100 000 à 500 000+ entrées |
| Technologie | TCAM : recherche en **un cycle**, quelle que soit la taille |

```
show mac address-table          # Cisco          bridge fdb show        # Linux / conteneurs / OVS
show mac address-table aging-time                bridge fdb show br0
```

**Pourquoi 300 s ?** Compromis : plus long, une machine déplacée reste injoignable ; plus court, on refloode
trop. Le désalignement avec le cache ARP Cisco à 4 h crée le **unknown unicast flooding** : l'entrée CAM
expire (300 s) alors que le cache ARP tient encore (14 400 s), l'émetteur continue sans refaire d'ARP, et le
switch **floode chaque trame du flux sur tout le VLAN**. Sur une réplication à 1 Gbit/s, tout le VLAN
encaisse 1 Gbit/s de trafic parasite.

> ⚠️ **PIÈGE** — « Un switch est en couche 2, il ne regarde jamais l'IP. » Vrai d'un switch L2 pur, faux de
> tout le matériel moderne : un switch L3 route entre VLAN, fait de l'IGMP snooping (il lit de l'IP
> multicast pour ne pas flooder) et applique des ACL sur des ports TCP. La frontière est commerciale.

### 5.4 Attaque : le MAC flooding

La table CAM est finie. Un attaquant génère des milliers de trames à MAC source aléatoire (`macof` en
produit ~150 000/minute). La table sature, le switch ne peut plus apprendre et **floode tout l'unicast
inconnu** : il redevient un hub. Défense : **port security**
(`switchport port-security maximum 2` + `violation restrict|shutdown`).

> ❓ **RETIENS ÇA** — Que devient un switch dont la table CAM est saturée ?
> <details><summary>→ réponse</summary><br>Il floode tout le trafic unicast inconnu sur tous les ports du VLAN : il se comporte comme un hub. C'est le but du MAC flooding. Défense : port security.</details>

### 5.5 Store-and-forward vs cut-through, et les latences

| Mode | Fonctionnement | Latence ajoutée | FCS |
|---|---|---|---|
| **Store-and-forward** | Reçoit toute la trame, vérifie le FCS, retransmet | 2-10 µs | Vérifié |
| **Cut-through** | Décide dès les 6 premiers octets lus | **0,3-1 µs** | Non vérifié |
| **Fragment-free** | Attend 64 octets | Intermédiaire | Partiel |

Le cut-through est le choix du trading haute fréquence et de certains clusters HPC/IA. Le store-and-forward
est le défaut ailleurs, et **obligatoire** dès qu'on change de débit (un port 1 G vers 10 G doit tamponner).

| Contribution à la latence | Ordre de grandeur |
|---|---|
| Sérialisation de 1500 o à 1 Gbit/s → 10 Gbit/s | 12 µs → 1,2 µs |
| **Propagation dans la fibre** | **5 µs par km** (≈ 200 000 km/s) |
| RTT intra-datacenter | 50 - 500 µs |
| RTT entre deux AZ d'une même région cloud | 0,5 - 2 ms |
| RTT Paris ↔ Francfort / Paris ↔ Virginie | ~10 ms / ~80 ms |

> 🧠 **MÉMO LATENCE** — « **5 µs par km**, dans la fibre, toujours. » Distance à vol d'oiseau × 2 (A/R)
> × 1,4 (le câble ne va pas droit) × 5 µs → tu tombes à ±20 % du RTT réel.

---

## 6. Domaine de collision et domaine de broadcast

C'est **la** confusion numéro un du sujet. Prends trois minutes ici.

| | **Domaine de collision** | **Domaine de broadcast** |
|---|---|---|
| Question posée | Qui peut entrer en collision avec moi ? | Qui reçoit mes broadcasts ? |
| Délimité par | **Chaque port de switch**, et un routeur | **Un routeur** ou **une frontière de VLAN** |
| Le switch… | **le découpe** (1 par port) | **ne le découpe pas** (1 par VLAN) |
| Le hub… | ne le découpe pas | ne le découpe pas |
| Encore d'actualité ? | **Non** en full-duplex | **Oui**, c'est le concept vivant |

```
                    ┌──────────────────────────────────────────┐
                    │            DOMAINE DE BROADCAST          │
   ┌────┐           │                 (= 1 VLAN)               │
   │ R  ├───────────┼──┬────┬───┬────┬───┬────┬───┬────┐       │
   └────┘           │  │ SW ├───┤ SW ├───┤ SW ├───┤ SW │       │
      ↑             │  └─┬──┘   └─┬──┘   └─┬──┘   └─┬──┘       │
   frontière        │   [c]      [c]      [c]      [c]         │
   de broadcast     └──────────────────────────────────────────┘
                         [c] = un domaine de collision PAR PORT
```

**Pourquoi les collisions ont disparu.** En full-duplex, une paire de fils émet, une autre reçoit : plus de
média partagé, donc plus de CSMA/CD. Un compteur de collisions non nul sur une interface moderne signale un
**duplex mismatch** (un côté full, l'autre half) : le débit s'effondre à quelques % du nominal alors que le
lien est « up ». Vérifie avec `ethtool eth0`.

**Pourquoi les broadcasts restent un problème d'échelle.** Chaque broadcast est traité par le CPU de
**chaque** machine du domaine : sur un VLAN de 1000 machines, ARP + DHCP + mDNS coûtent des points de CPU
partout. Règle de terrain : **pas plus de 200 à 500 hôtes par domaine de broadcast** (un /24 ou un /23).

> ❓ **RETIENS ÇA** — Un switch 24 ports, tous dans le même VLAN : combien de domaines de collision et de
> domaines de broadcast ?
> <details><summary>→ réponse</summary><br>24 domaines de collision (un par port) et 1 seul domaine de broadcast. Ajoute un second VLAN et tu passes à 2 domaines de broadcast, sans changer le nombre de ports.</details>

---

## 7. VLAN : découper un switch en plusieurs switchs

### 7.1 Le problème

Un seul switch physique, trois environnements à séparer : prod, préprod, dev. Comment obtenir **trois
réseaux étanches sur un seul équipement**, et propager cette séparation aux autres switchs ? Le **VLAN**.

Un VLAN est un **domaine de broadcast logique**. Deux ports dans deux VLAN différents ne peuvent pas se
parler en couche 2, même côte à côte dans le même châssis. Pour communiquer, il faut **passer par un
routeur** (ou un switch L3) — donc traverser un point où on peut filtrer.

> 🧠 **MÉMO** — Un VLAN, c'est une **cloison amovible dans un open space**. Même bâtiment, même moquette,
> mais on ne s'entend plus d'un côté à l'autre. Pour passer il faut sortir par la porte (le routeur), et
> c'est là qu'on met le vigile (le firewall).

### 7.2 Le tag 802.1Q

Le tag fait **4 octets**, inséré **après la MAC source, avant l'EtherType d'origine**.

```
  Trame TAGUÉE 802.1Q (comparer avec le format nu du §2.1) :
  ┌──────────┬──────────┬────────┬────────┬────────┬──────────────┬─────┐
  │ MAC dest │ MAC src  │ 0x8100 │  TCI   │ 0x0800 │   Payload    │ FCS │
  └──────────┴──────────┴────────┴────────┴────────┴──────────────┴─────┘
                        └─── tag 4 octets ───┘          trame max 1522 octets

  Détail du tag :
   ┌───────────────────────────────┬─────┬─┬───────────────────┐
   │   TPID = 0x8100   (16 bits)   │ PCP │D│   VID (12 bits)   │
   └───────────────────────────────┴─────┴─┴───────────────────┘
                                    3 bits 1b       0 à 4095
```

| Sous-champ | Bits | Rôle |
|---|---|---|
| **TPID** | 16 | `0x8100` : marqueur de tag (`0x88A8` pour le tag externe QinQ) |
| **PCP** | 3 | Classe de service 802.1p, 0 à 7. **C'est la QoS de couche 2.** |
| **DEI** (ex-CFI) | 1 | *Drop Eligible Indicator* : « jetable en premier si congestion » |
| **VID** | 12 | Numéro de VLAN, 0 à 4095 |

VID `0` = *priority-tagged* (pas d'appartenance VLAN, seul le PCP compte) ; VID `1` = VLAN par défaut sortie
d'usine ; VID `4095` = réservé. **Utilisables : 1 à 4094, soit 4094 VLAN.** Les 12 bits sont la limite
structurelle de 802.1Q — c'est **la** raison d'être de VXLAN, dont le **VNI de 24 bits** offre 16 777 216
segments, indispensable en datacenter multi-locataires ou en Kubernetes.

> ❓ **RETIENS ÇA** — Combien de bits pour le VLAN ID, et combien de VLAN utilisables ?
> <details><summary>→ réponse</summary><br>12 bits → 4096 valeurs, mais 0 et 4095 sont réservés → 4094 VLAN utilisables (1 à 4094). C'est la limite qui a fait naître VXLAN et ses 24 bits de VNI.</details>

### 7.3 Port access vs port trunk

```
   VLAN 10 (prod)   VLAN 20 (dev)
        │                │
   ┌────┴────────────────┴────┐          TRUNK (tagué)          ┌──────────────┐
   │  P1:access10  P2:access20│═══════════════════════════════► │    SW-2      │
   │        SWITCH 1          │  transporte VLAN 10, 20, 30...  │              │
   └──────────────────────────┘  chaque trame porte son tag     └──────────────┘
```

| | **Access** | **Trunk** |
|---|---|---|
| Nombre de VLAN | 1 (+ éventuel voice VLAN) | Plusieurs |
| Tag sur le fil | Aucun | 802.1Q, sauf VLAN natif |
| Vers quoi | Poste, imprimante, serveur simple | Autre switch, routeur, hyperviseur |
| Config Cisco | `switchport mode access` + `switchport access vlan 10` | `switchport mode trunk` + `switchport trunk allowed vlan 10,20` |

En une phrase : **en entrée sur un port access le switch ajoute le tag, en sortie il le retire**. Le tag
n'existe qu'à l'intérieur du réseau commuté ; l'hôte final ne le voit jamais, sauf s'il est lui-même trunké.

### 7.4 VLAN natif et attaque par double tag

Sur un trunk, **un** VLAN circule **sans tag** : le **VLAN natif** (par défaut le VLAN 1), héritage de
compatibilité. C'est aussi une faille — le **VLAN hopping par double tagging** :

```
  L'attaquant est sur un port ACCESS en VLAN 1 (= le VLAN natif du trunk).
  Il forge une trame avec DEUX tags :
  ┌──────┬──────┬───────────┬────────────┬────────┬─────────┐
  │ dest │ src  │ tag VLAN 1│ tag VLAN 20│ 0x0800 │ payload │
  └──────┴──────┴───────────┴────────────┴────────┴─────────┘
  SW-1 : port natif VLAN 1 → il RETIRE le premier tag et envoie sur le trunk.
  SW-2 : il lit le tag restant → VLAN 20 → il délivre dans le VLAN 20.
  → injection dans un VLAN interdit. Unidirectionnel, mais suffisant.
```

**Les trois règles de durcissement :** (1) VLAN natif = un VLAN **inutilisé et sans hôte**, jamais le
VLAN 1 ; (2) `switchport nonegotiate` pour désactiver DTP ; (3) ports inutilisés en `shutdown` dans un VLAN
poubelle.

> ⚠️ **PIÈGE** — « Un VLAN, c'est de la sécurité. » C'est de la **segmentation**. Un VLAN empêche la
> communication accidentelle, pas un attaquant qui a un pied sur le switch. La sécurité vient du filtrage au
> point de passage inter-VLAN (firewall, ACL, NetworkPolicy), pas de la cloison.

### 7.5 VLAN sous Linux

```bash
ip link add link eth0 name eth0.100 type vlan id 100     # sous-interface taguée VLAN 100
ip addr add 10.100.0.5/24 dev eth0.100 && ip link set eth0.100 up
ip -d link show eth0.100        # -d affiche "vlan protocol 802.1Q id 100"
tcpdump -e -i eth0 vlan 100     # -e est INDISPENSABLE pour voir MAC et tag
```

> ❓ **RETIENS ÇA** — Quelle option de tcpdump affiche l'en-tête Ethernet (MAC et tag VLAN) ?
> <details><summary>→ réponse</summary><br>-e. Sans -e, tcpdump commence l'affichage à la couche 3 et tu es aveugle en couche 2.</details>

---

## 8. STP et RSTP : survivre aux boucles

### 8.1 Pourquoi une boucle L2 est mortelle

Tu veux de la redondance : deux switchs, deux câbles. Tu viens de créer une **boucle**. Or la trame Ethernet
**n'a pas de TTL**. En IP, un paquet qui tourne meurt au bout de 64 sauts. En Ethernet, il tourne
**pour toujours**.

```
   ┌──────┐   lien A    ┌──────┐     t0 : PC envoie 1 broadcast à SW1
   │ SW1  ├─────────────┤ SW2  │     t1 : SW1 floode sur A et B          → 2 copies
   │      ├─────────────┤      │     t2 : SW2 refloode chaque copie      → 4 copies
   └──────┘   lien B    └──────┘     t3 : 8 ... t4 : 16 ... EXPONENTIEL
                                     → saturation du lien en quelques millisecondes
```

Trois effets : **tempête de broadcast** (liens à 100 %, CPU des switchs à 100 %, plus aucune console
joignable — il faut débrancher physiquement) ; **MAC flapping** (la même MAC arrive alternativement par
deux ports, la table CAM est réécrite des milliers de fois par seconde) ; **duplication des unicasts**.

> 🧠 **MÉMO** — « **Pas de TTL en couche 2.** » C'est toute la justification de STP. Une boucle IP ralentit.
> Une boucle Ethernet **tue**.

> ❓ **RETIENS ÇA** — Pourquoi une boucle L2 est-elle bien plus grave qu'une boucle L3 ?
> <details><summary>→ réponse</summary><br>Parce que la trame Ethernet n'a pas de champ TTL : rien ne détruit une trame qui tourne, elle est dupliquée à chaque tour → croissance exponentielle → tempête de broadcast et effondrement du réseau.</details>

### 8.2 L'algorithme en 4 étapes

STP (IEEE **802.1D**) construit un **arbre couvrant** : il garde tous les liens branchés mais en **bloque
logiquement** juste assez pour qu'il ne reste **qu'un seul chemin actif entre deux points**. Si un lien
actif tombe, un lien bloqué est réactivé. L'échange se fait par des **BPDU** émises toutes les **2 s**
(Hello) vers la MAC multicast **`01:80:c2:00:00:00`**.

**Étape 0 — le Bridge ID (8 octets) :**

```
 ┌────────────────┬──────────────────────────────┐
 │  Priorité      │   Adresse MAC du switch      │   défaut 32768,
 │   2 octets     │        6 octets              │   pas de 4096
 └────────────────┴──────────────────────────────┘   (+ n° de VLAN si extended system-id)
```

**Étape 1 — élire le ROOT BRIDGE** : Bridge ID le plus faible. On compare la priorité, puis en cas
d'égalité **la MAC la plus basse**. Priorité identique partout par défaut → **c'est le switch le plus vieux
qui gagne**, souvent le plus lent et le plus mal placé. **On force donc toujours le root manuellement** :
`spanning-tree vlan 10 priority 4096`.

**Étape 2 — sur chaque switch non-root, élire le ROOT PORT** : le port au **coût cumulé le plus faible vers
le root**. Un seul par switch.

| Débit | Coût *short* (802.1D, défaut Cisco) | Coût *long* (802.1t) |
|---|---|---|
| 10 Mbit/s | 100 | 2 000 000 |
| 100 Mbit/s | **19** | 200 000 |
| 1 Gbit/s | **4** | 20 000 |
| 10 Gbit/s | **2** | 2 000 |
| 100 Gbit/s | 1 (saturé) | 200 |

**Étape 3 — sur chaque segment, élire le DESIGNATED PORT** : celui du switch au plus faible coût vers le
root. **Tous les ports du root bridge sont designated.**

**Étape 4 — bloquer le reste** : tout port ni root ni designated passe en *blocking* (802.1D) ou
*alternate/discarding* (802.1w).

**Ordre de départage, à réciter :** 1) coût cumulé le plus faible → 2) Bridge ID du voisin le plus faible
→ 3) Port ID du voisin le plus faible → 4) Port ID local le plus faible.

> 🧠 **MÉMO STP** — « **Root, Route, Reste** » : **R**oot bridge (le plus petit BID) → **R**oot port (le
> moins cher vers le root) → **R**este bloqué. Départage : **Coût, Bridge ID, Port ID** → « **C-B-P** ».

### 8.3 Les états de port

```
  802.1D — 5 états :
  Disabled ──► Blocking ──► Listening ──► Learning ──► Forwarding
   (admin)     20 s max      15 s          15 s       (opérationnel)
              (max age)   (fwd delay)   (fwd delay)

   État       │ Reçoit BPDU │ Émet BPDU │ Apprend MAC │ Transmet données
   ───────────┼─────────────┼───────────┼─────────────┼──────────────────
   Disabled   │     non     │    non    │     non     │       non
   Blocking   │     OUI     │    non    │     non     │       non
   Listening  │     OUI     │    OUI    │     non     │       non
   Learning   │     OUI     │    OUI    │     OUI     │       non
   Forwarding │     OUI     │    OUI    │     OUI     │       OUI
```

**Convergence 802.1D : 30 s** (listening 15 + learning 15), **jusqu'à 50 s** s'il faut d'abord expirer le
Max Age (20 + 15 + 15). Trente secondes de coupure sur un cluster de bases, ce sont des dizaines de timeouts.

| Timer 802.1D | Défaut | Rôle |
|---|---|---|
| **Hello** | **2 s** | Période d'émission des BPDU |
| **Forward Delay** | **15 s** | Durée de listening, puis de learning |
| **Max Age** | **20 s** | Durée de conservation d'une BPDU avant péremption |

**802.1w (RSTP)** réduit à **3 états** — *Discarding* (fusion de disabled+blocking+listening), *Learning*,
*Forwarding* — et définit **4 rôles** : **Root** (chemin vers le root), **Designated** (chemin vers l'aval),
**Alternate** (secours du root port, via un autre switch), **Backup** (secours d'un designated sur le même
segment). Il converge en **moins d'une seconde** grâce au mécanisme **proposal/agreement** (accord explicite
entre voisins au lieu de timers), aux **edge ports** (équivalent PortFast, forwarding immédiat vers un
hôte), et au fait que chaque switch **émet ses propres BPDU** toutes les 2 s — **3 Hello manqués = 6 s** et
le lien est déclaré mort.

> ❓ **RETIENS ÇA** — Les 3 timers de STP et leurs valeurs par défaut ?
> <details><summary>→ réponse</summary><br>Hello = 2 s, Forward Delay = 15 s, Max Age = 20 s. Convergence 802.1D : 30 à 50 s. RSTP : moins d'une seconde.</details>

> ⚠️ **PIÈGE** — Ne confonds pas **états** et **rôles**. *Discarding / learning / forwarding* sont des
> **états** (ce que le port fait maintenant) ; *root / designated / alternate / backup* sont des **rôles**
> (sa fonction dans l'arbre). Un port alternate est en état discarding. La question tombe en entretien.

### 8.4 Protections, variantes, et le datacenter moderne

| Fonction | Ce qu'elle fait | Où |
|---|---|---|
| **PortFast / edge port** | Forwarding immédiat, sans les 30 s | Ports vers les hôtes uniquement |
| **BPDU Guard** | Coupe le port (`err-disable`) s'il reçoit une BPDU | Toujours **avec** PortFast |
| **Root Guard** | Refuse qu'un voisin devienne root sur ce port | Ports vers l'accès |
| **Loop Guard** | Bloque si les BPDU cessent sur un port non-designated | Liens fibre point-à-point |
| **UDLD** | Détecte un lien unidirectionnel (TX fibre coupée) | Liens fibre |
| **Storm control** | Limite le % de broadcast/multicast par port | Ports d'accès |

PortFast **sans** BPDU Guard est une faute : quelqu'un branche un petit switch, émet des BPDU et devient
root du réseau. Les deux vont toujours ensemble.

| Variante | Norme | Idée |
|---|---|---|
| STP | 802.1D | Un seul arbre pour tout le réseau |
| RSTP | 802.1w | Même arbre, convergence < 1 s |
| **MSTP** | 802.1s | Plusieurs arbres, un par **groupe** de VLAN — l'approche scalable |
| PVST+ / Rapid-PVST+ | Cisco | Un arbre **par VLAN** : répartition de charge, coûteux en CPU |

**Où est passé STP dans le datacenter ?** On l'a évacué de la topologie : en *leaf-spine* moderne on route
dès le leaf (**L3 jusqu'au rack**, souvent en BGP) et on porte la couche 2 dans un overlay **VXLAN/EVPN**,
donc **tous les liens sont actifs** en ECMP contre 50 % gaspillés avec STP. STP reste configuré partout
comme **filet de sécurité** : le jour où quelqu'un rebranche deux ports du même switch, c'est lui qui sauve
le datacenter.

---

## 9. Agrégation de liens : LACP

Un lien 10 Gbit/s ne suffit plus, tu en branches quatre — sans mécanisme, STP en bloque trois (c'est une
boucle). Solution : les faire voir comme **un seul lien logique**. C'est l'agrégation (*port-channel*,
*EtherChannel*, *bond*, *LAG*), normalisée **802.3ad** puis **802.1AX**, négociée par **LACP**.

```
   ┌──────┐  ═════ 10G ═════  ┌──────┐
   │ SW1  │  ═════ 10G ═════  │ SW2  │   → vu par STP comme UN SEUL lien de 40 Gbit/s,
   │      │  ═════ 10G ═════  │      │      aucun port bloqué
   └──────┘  ═════ 10G ═════  └──────┘     Po1 (port-channel 1)
```

| Élément | Valeur |
|---|---|
| Norme | IEEE 802.3ad → renommée **802.1AX** |
| LACPDU | EtherType `0x8809`, MAC `01:80:c2:00:00:02` |
| Période LACPDU | **30 s** (*slow*, défaut) ou **1 s** (*fast*) |
| Timeout | **3 × la période** → 90 s ou **3 s** |
| Liens actifs max (Cisco) | **8** actifs (16 configurés, 8 en attente) |
| Modes | `active` (parle en premier) / `passive` (répond seulement) |

Deux ports `passive` des deux côtés ne forment **jamais** de bundle : il faut au moins un `active`.

**La limite qui compte pour toi : le hachage.** Un agrégat ne coupe pas les flux, il les **répartit**. Pour
chaque trame on calcule un hash et on en déduit le lien. **Toutes les trames d'un même flux prennent donc
le même lien** — sinon TCP recevrait ses segments dans le désordre.

| Politique de hash | Champs | Quand |
|---|---|---|
| `layer2` | MAC src + dst | Beaucoup de machines dialoguant entre elles |
| `layer2+3` | MAC + IP | Défaut raisonnable |
| **`layer3+4`** | IP + ports TCP/UDP | **Le bon choix en data** : plusieurs connexions par couple d'hôtes |
| `encap3+4` | IP/ports **internes** au tunnel | Indispensable si tout est encapsulé (VXLAN, GRE) |

> ⚠️ **PIÈGE MAJEUR POUR TOI** — « J'ai 4 × 10 G, donc mon transfert ira à 40 Gbit/s. » **Non.** Un **seul
> flux TCP** (un `scp`, une réplication, un transfert HDFS unique) plafonne à **10 Gbit/s** : le hash le
> fige sur un lien. Tu n'exploites les 40 G qu'avec **au moins autant de flux distincts que de liens** et un
> hash `layer3+4`. C'est exactement pour ça qu'on parallélise (`distcp -m 16`, plusieurs partitions Spark) :
> ce n'est pas que du CPU, c'est du hachage de LAG.

**Modes de bonding Linux** : `0 balance-rr` (casse l'ordre TCP), `1 active-backup` (le mode sûr, sans config
switch), `2 balance-xor`, **`4 802.3ad` = LACP**, `5/6 balance-tlb/alb`. État complet :
`cat /proc/net/bonding/bond0`.

> ❓ **RETIENS ÇA** — Agrégat LACP de 4 × 10 Gbit/s : débit max pour **un seul** flux TCP ?
> <details><summary>→ réponse</summary><br>10 Gbit/s. Le hash fige un flux donné sur un lien unique pour préserver l'ordre des segments. Le débit agrégé ne s'obtient qu'avec plusieurs flux distincts.</details>

---

## 10. MTU et jumbo frames — la section qui te sauvera en production

### 10.1 Définitions et calculs

| Terme | Définition |
|---|---|
| **MTU** | Taille max du **payload** d'une trame = taille max du paquet IP. Standard : **1500** |
| **Jumbo frame** | Payload > 1500. Convention de fait : **MTU 9000** |
| **Baby giant** | 1600-2000 : juste de quoi absorber MPLS ou VXLAN |
| **MSS** | *Maximum Segment Size* : payload TCP max. IPv4 sans option : **MTU − 40** |
| **Path MTU** | Le **plus petit** MTU du trajet. C'est lui qui décide |

```
   MTU 1500 → MSS = 1500 − 20 (IP) − 20 (TCP) = 1460
   MTU 9000 → MSS = 9000 − 40                 = 8960
   MTU 1500 en IPv6 → MSS = 1500 − 40 − 20    = 1440
   VXLAN sur underlay 1500 → MTU interne = 1450 → MSS = 1410
```

| Encapsulation | Overhead | MTU interne si underlay = 1500 |
|---|---|---|
| VLAN 802.1Q | 4 o | 1500 (le tag ne mange pas le payload) |
| **VXLAN** (Eth interne 14 + VXLAN 8 + UDP 8 + IP 20) | **50 o** | **1450** |
| Geneve | 50 o + options | ≤ 1450 |
| IPIP / GRE | 20 o / 24 o | 1480 / 1476 |
| **WireGuard** | 60 o | **1420** |
| IPsec ESP (tunnel, AES) | 54 à 73 o | ~1400 |

> 🧠 **MÉMO** — « **VXLAN = 50** ». Chiffre à sortir sans réfléchir. Donc **pod MTU = 1450** sur un underlay
> standard. Presque tous les incidents MTU en Kubernetes tiennent dans ces deux nombres.

> ❓ **RETIENS ÇA** — Quel MSS TCP annoncer sur une interface à MTU 9000 en IPv4 ?
> <details><summary>→ réponse</summary><br>8960 = 9000 − 20 (en-tête IPv4) − 20 (en-tête TCP).</details>

### 10.2 Le trou noir PMTU — l'incident qui hante les data engineers

**Le scénario.** Ton job Spark lit ici et écrit là. Le `ping` répond, le `telnet` sur le port passe, les
petites requêtes marchent. Mais dès qu'il y a du volume : **blocage puis timeout**.

```
  Émetteur (MTU 9000)                     Lien intermédiaire (MTU 1500)
        │── paquet 9000 o, flag DF=1 ───────────────►│ 9000 > 1500 et DF=1 → je JETTE
        │◄── ICMP type 3 code 4 ─────────────────────│ « Fragmentation Needed, MTU=1500 »
        └─ l'émetteur réduit à 1500 → ça repasse

  ★ MAIS si un firewall bloque l'ICMP (ce que font beaucoup de règles « deny icmp ») :
        │── paquet 9000, DF=1 ──────────────────────►│  jeté, aucun message ne revient
        │── retransmission ─────────────────────────►│  jeté ... et ainsi de suite
        → TROU NOIR PMTU : la connexion s'établit (petits paquets) puis se fige.
```

**Signature clinique** : `ping` normal OK, `ping -s 8972 -M do` échec, handshake TCP OK (les SYN sont
petits), transfert de volume bloqué puis `Connection timed out` ou `FetchFailedException`. Coupable
fréquent : ICMP filtré + MTU hétérogène sur le chemin.

```bash
# -M do : interdit la fragmentation (positionne DF). -s : payload ICMP.
# payload ICMP + 8 (ICMP) + 20 (IP) = MTU testé   →   taille = MTU − 28
ping -M do -s 1472 10.0.0.1     # teste MTU 1500
ping -M do -s 8972 10.0.0.1     # teste MTU 9000
tracepath 10.0.0.1              # découvre le MTU saut par saut
ip route get 10.0.0.1           # MTU retenu pour cette destination
```

> 🧠 **MÉMO** — « **1472 et 8972** ». Les deux tailles de `ping -M do` à retenir. Et la soustraction :
> **MTU − 28**, où 28 = 20 (IP) + 8 (ICMP).

> ❓ **RETIENS ÇA** — Quelle taille de `ping -M do -s` teste un MTU de 9000 ?
> <details><summary>→ réponse</summary><br>8972 = 9000 − 20 (en-tête IP) − 8 (en-tête ICMP).</details>

**Correctifs, par ordre de préférence :** (1) **aligner les MTU** sur tout le chemin, la vraie solution ;
(2) **débloquer l'ICMP type 3 code 4** dans les firewalls, non négociable pour que PMTUD fonctionne ;
(3) **MSS clamping** sur le routeur —
`iptables -t mangle -A FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu` ;
(4) baisser le MTU des pods/VM au plus petit dénominateur commun.

### 10.3 Jumbo frames : le vrai gain

Sur un lien 1 Gbit/s :

| | MTU 1500 | MTU 9000 | Effet |
|---|---|---|---|
| Débit utile TCP | 949 Mbit/s | 991 Mbit/s | **+4,4 %** seulement |
| Trames/s | 81 274 | 13 830 | **÷ 5,9** |
| Interruptions CPU | proportionnelles | ÷ 6 | **le vrai gain** |

Le gain de bande passante est marginal, le gain **CPU** est massif : six fois moins d'interruptions, de
traversées de pile et de copies mémoire — plusieurs cœurs libérés sur un nœud qui ingère à 25 Gbit/s. D'où
l'activation des jumbo sur les réseaux de stockage (iSCSI, NFS, Ceph) et de shuffle. **Règle d'or : tout ou
rien.** Le jumbo doit être actif sur **tout** le chemin — les deux hôtes, tous les switchs et routeurs, et
le MTU de l'interface *et* de la route. Un seul maillon à 1500 : fragmentation (lent) ou trou noir (cassé).

| Contexte | MTU |
|---|---|
| Ethernet standard, Internet | **1500** |
| **AWS** — instances dans un même VPC (ENA) | **9001** |
| AWS — via Internet Gateway / Transit Gateway | 1500 / 8500 |
| **GCP** — VPC, valeur par défaut historique | **1460** (configurable jusqu'à 8896) |
| Azure — VM standard | 1500 |
| Tunnel VPN IPsec typique | ~1400 |
| **Pod K8s, overlay VXLAN** (Flannel, Calico VXLAN) | **1450** |
| Pod K8s, Calico IPIP / sans encapsulation | 1480 / 1500 |

> ⚠️ **PIÈGE CLOUD** — GCP et son MTU de **1460** par défaut casse des hypothèses partout : un conteneur à
> 1500 sur un VPC GCP à 1460 et tu retrouves le trou noir. C'est un des écarts inter-cloud les plus vicieux,
> et le citer en entretien montre que tu as déjà mis les mains dedans.

---

## 11. Ce qu'un data engineer voit vraiment

```
                        ┌───────────┐   ┌───────────┐
        SPINE           │  Spine 1  │   │  Spine 2  │      L3 / BGP, ECMP,
                        └─────┬─────┘   └─────┬─────┘      tous les liens actifs
                        ╱     │  ╲          ╱ │     ╲
              ┌────┴───┐  ┌───┴────┐  ┌──┴─────┐  ┌────┴───┐
   LEAF (ToR) │ Leaf 1 │  │ Leaf 2 │  │ Leaf 3 │  │ Leaf 4 │   ← la couche 2 s'arrête ICI
              └───┬────┘  └───┬────┘  └───┬────┘  └───┬────┘
                 rack1       rack2       rack3       rack4
   → Toute paire de serveurs est à exactement 2 sauts : latence uniforme et prévisible.
   → C'est cette prévisibilité qui rend le shuffle Spark et l'all-reduce de training viables.
```

Concrètement : la **localité de rack** n'est presque plus un levier (contrairement à HDFS et son *rack
awareness*) ; le goulot s'est déplacé vers la **NIC du serveur** et le **CPU** qui traite les trames ; la
couche 2 pure est **confinée au rack**. Un VLAN étendu à tout le datacenter est une faute d'architecture.

**Les cinq situations où la couche 2 te tombe dessus :**

| Situation | Symptôme | Cause L2 | Réflexe |
|---|---|---|---|
| Shuffle Spark qui échoue | `FetchFailedException` sur les grosses partitions seulement | MTU incohérent overlay/underlay | `ping -M do -s 1472` entre exécuteurs |
| Pod K8s : DNS OK, gros POST figés | Petit OK, volume bloqué | MTU pod 1500 + VXLAN sur underlay 1500 | Passer le pod à 1450 |
| Réplication Kafka lente sans perte | Débit bloqué à ~1/N du LAG | Un flux TCP figé sur un lien du bond | Plus de partitions, hash `layer3+4` |
| Bascule de master de base | 2-5 min d'indispo au lieu de 2 s | Pas de gratuitous ARP | `arping -U` sur la VIP |
| Cluster injoignable après intervention | Tout tombe, CPU switch à 100 % | Boucle L2 sans BPDU Guard | Débrancher, `show spanning-tree` |

**Le réseau comme source de données pour l'IA** — c'est la composante IA de ton poste :

| Source | Nature | Usage modèle |
|---|---|---|
| Compteurs d'interface (SNMP, gNMI, `ethtool -S`) | Séries temporelles : octets, paquets, CRC, discards | Détection d'anomalie, prédiction de panne de SFP |
| Table CAM / FDB | Graphe MAC ↔ port ↔ temps | MAC flapping, équipement non autorisé |
| Trafic ARP | Taux, ratio request/reply, IP↔MAC | ARP spoofing, inventaire fantôme |
| Événements STP (TCN) | Changements de topologie | Corrélation avec les incidents applicatifs |
| Flux NetFlow / IPFIX / sFlow | Échantillons de flux | Classification, planification de capacité |

Le point technique : ces données sont **haute fréquence et haute cardinalité** (une série par port × par
compteur × par équipement — vite des millions de séries). C'est un problème de data engineering avant d'être
un problème de modèle. Et un compteur d'interface est **cumulatif** : il faut le **dériver** et gérer les
**wrap-around** (les compteurs 32 bits rebouclent à 4,29 milliards — d'où SNMPv2 en 64 bits, puis gNMI en
streaming).

> 🧠 **MÉMO OUTILS** — Trois commandes couvrent 80 % du diagnostic L2 : **`ip -s link`** (est-ce que ça
> compte des erreurs ?), **`ip neigh`** (est-ce que je résous mes voisins ?), **`ping -M do -s 1472`**
> (est-ce que le MTU passe ?). Le reste est dans la cheatsheet.

---

## 12. Exercices intégralement corrigés

### Exercice 1 — Décoder une trame ARP en hexadécimal

```
ff ff ff ff ff ff 00 1a 2b 3c 4d 5e 08 06 00 01
08 00 06 04 00 01 00 1a 2b 3c 4d 5e c0 a8 0a 0b
00 00 00 00 00 00 c0 a8 0a 01
```

| Offset | Octets | Champ | Interprétation |
|---|---|---|---|
| 0-5 | `ff ff ff ff ff ff` | MAC destination | **Broadcast** |
| 6-11 | `00 1a 2b 3c 4d 5e` | MAC source | OUI `00:1a:2b` — unicast, universelle (2e chiffre = 0) |
| 12-13 | `08 06` | EtherType | **ARP** |
| 14-15 | `00 01` | Hardware type | Ethernet |
| 16-17 | `08 00` | Protocol type | IPv4 |
| 18-19 | `06` `04` | HLEN / PLEN | 6 octets de MAC, 4 octets d'IP |
| 20-21 | `00 01` | Opération | **1 = REQUEST** |
| 22-27 | `00 1a 2b 3c 4d 5e` | SHA | identique à la MAC source : cohérent |
| 28-31 | `c0 a8 0a 0b` | SPA | `192.168.10.11` |
| 32-37 | `00 00 00 00 00 00` | THA | **inconnu — c'est ce qu'on cherche** |
| 38-41 | `c0 a8 0a 01` | TPA | `192.168.10.1` |

Conversion : `c0`=192, `a8`=168, `0a`=10, `0b`=11.
**Lecture** : `192.168.10.11` demande en broadcast qui a `192.168.10.1` — presque certainement sa passerelle
par défaut. **Taille** : 14 + 28 = 42 octets → la carte ajoutera **18 octets de bourrage** puis 4 de FCS
pour atteindre le minimum de 64. **`SPA == TPA` ?** Non (`.11` ≠ `.1`) → ce n'est **pas** un gratuitous ARP.

### Exercice 2 — Décoder un tag 802.1Q

```
00 50 56 aa bb cc   00 1a 2b 3c 4d 5e   81 00   20 64   08 00 ...
```

1. `00 50 56 aa bb cc` : MAC destination. OUI `00:50:56` = **VMware**. Premier octet `00`, pair → unicast.
2. `00 1a 2b 3c 4d 5e` : MAC source.
3. `81 00` : pas un EtherType final, c'est le **TPID 802.1Q** → les 2 octets suivants sont le TCI.
4. `20 64` = `0010 0000 0110 0100` :
   - **PCP** = 3 premiers bits = `001` = **1** — vérification : `0x2064 >> 13` = 8292 / 8192 = **1** ✔
   - **DEI** = bit suivant = `0`
   - **VID** = 12 bits restants — vérification : `0x2064 AND 0x0FFF` = `0x064` = 6×16 + 4 = **100** ✔
5. `08 00` : le **vrai** EtherType → IPv4.

**Lecture** : trame IPv4 taguée **VLAN 100**, priorité 802.1p = 1, à destination d'un hôte VMware — on est
très probablement sur un trunk vers un hyperviseur ESXi.

### Exercice 3 — Élection STP complète

```
                 ┌────────┐
                 │  SW-C  │  priorité 4096,  MAC ...0C
                 └─┬────┬─┘
            1 Gb/s │    │ 1 Gb/s
                 ┌─┴──┐ └─┬──┐      A : prio 32768, MAC ...0A
                 │SW-A│   │SW-B│    B : prio 32768, MAC ...0B
                 └─┬──┘   └─┬──┘    D : prio 32768, MAC ...0D
         100 Mb/s  │        │ 1 Gb/s
                   └───┬────┘
                    ┌──┴───┐
                    │ SW-D │
                    └──────┘
```

**1) Root bridge ?** On compare les Bridge ID (priorité puis MAC). SW-C a 4096 contre 32768.
→ **SW-C est root**, tous ses ports sont **designated**.

**2) Coûts** (mode short : 1 Gb/s = 4, 100 Mb/s = 19) :

| Switch | Chemin | Coût cumulé |
|---|---|---|
| SW-A | direct vers C | **4** |
| SW-B | direct vers C | **4** |
| SW-D | via SW-B : 4 + 4 | **8** |
| SW-D | via SW-A : 4 + 19 | 23 |

**3) Root ports** : SW-A → port vers C (4) ; SW-B → port vers C (4) ; SW-D → port vers B (8 < 23).

**4) Segment A–D** : on compare le coût vers le root des deux extrémités. SW-A = 4, SW-D = 8 → le plus
faible gagne. **Le port de SW-A vers D est designated**, donc **le port de SW-D vers A est bloqué**
(*alternate / discarding* en RSTP). Topologie active finale : C au sommet, A et B en dessous, D raccroché
par B seulement — le lien A–D reste branché mais bloqué.

**5) Si le lien B–D tombe ?** SW-D perd son root port ; son port vers A, en *alternate*, devient root port
avec un coût de 23. En **802.1D** : listening 15 s + learning 15 s → **~30 s de coupure**. En **802.1w** :
le rôle de secours est pré-calculé, bascule **< 1 s**.

### Exercice 4 — MTU, MSS et trou noir

**Situation.** Cluster K8s sur AWS, underlay VPC à MTU 1500, CNI Calico en mode VXLAN. Un ingénieur a forcé
le MTU des pods à 1500 « pour optimiser ». Un job Spark plante en `FetchFailedException` sur les grosses
partitions ; les petites passent.

**1) Taille d'un paquet de 1500 octets une fois encapsulé ?**
```
   1500 (paquet IP interne) + 14 (en-tête Eth interne, encapsulé) + 8 (VXLAN) + 8 (UDP) + 20 (IP externe) = 1550
   → c'est la taille du PAQUET IP EXTERNE ; l'en-tête Ethernet externe, lui, ne compte pas dans le MTU.
   L'underlay accepte 1500 → 1550 > 1500 → le paquet est JETÉ.
```
**2) Pourquoi les petits transferts marchent ?** Le handshake TCP et les petites requêtes tiennent sous la
limite : la connexion s'établit, l'application croit tout aller bien. C'est le transfert de volume — qui
utilise des segments de taille maximale — qui est intégralement jeté.

**3) MTU à régler sur les pods ?** `1500 − 50` = **1450**. **4) MSS correspondant ?** `1450 − 40` = **1410**.

**5) Confirmation en 30 secondes depuis un pod :**
```bash
ping -M do -s 1422 <ip_pod_distant>   # 1422 + 8 + 20 = 1450  → doit PASSER
ping -M do -s 1472 <ip_pod_distant>   # 1472 + 8 + 20 = 1500  → doit ÉCHOUER
```
**6) Pourquoi PMTUD n'a-t-il pas corrigé seul ?** Parce que l'ICMP « Fragmentation Needed » (type 3, code 4)
est filtré par un Security Group ou une NACL. Sans ce message, l'émetteur ne sait pas qu'il doit réduire et
retransmet indéfiniment le même paquet trop gros.

### Exercice 5 — Rendement Ethernet et gain du jumbo à 10 Gbit/s

```
 MTU 1500 : fil = 1500 + 18 (L2) + 8 (préamb./SFD) + 12 (IFG) = 1538 o = 12 304 bits
            trames/s = 1e10 / 12 304 = 812 743 | payload TCP = 1500 − 40 = 1460 o
            débit utile = 812 743 × 1460 × 8 = 9,49 Gbit/s  →  94,9 %
 MTU 9000 : fil = 9000 + 18 + 8 + 12 = 9038 o = 72 304 bits
            trames/s = 1e10 / 72 304 = 138 305 | payload TCP = 9000 − 40 = 8960 o
            débit utile = 138 305 × 8960 × 8 = 9,91 Gbit/s  →  99,1 %
```

**À réutiliser en entretien** : « +4,4 % de bande passante utile seulement, mais le nombre de trames par
seconde est divisé par 5,9, de 812 000 à 138 000. Le vrai gain est CPU. »

---

## 13. Questions d'entretien

**1) Que se passe-t-il, couche par couche, quand tu tapes `ping 10.0.0.1` sur une machine du même LAN ?**
> La pile IP construit le paquet ICMP echo request. Pour l'émettre il lui faut une MAC destination : elle
> consulte le cache de voisinage. S'il est vide elle émet une requête ARP en broadcast — « qui a 10.0.0.1 ? ».
> Tout le VLAN reçoit, seule la bonne machine répond en unicast ; le cache passe en `REACHABLE`, 30 s par
> défaut sous Linux. La trame est construite avec EtherType `0x0800` et le switch la commute vers le seul
> port utile grâce à sa table CAM. La réponse revient sans nouvel ARP : le destinataire a appris la MAC
> source au passage.

**2) Différence entre domaine de collision et domaine de broadcast ?**
> Le domaine de collision regroupe les machines qui peuvent entrer en conflit d'émission sur un média
> partagé ; un switch en crée un par port, donc en full-duplex la notion est morte. Le domaine de broadcast
> regroupe celles qui reçoivent un `ff:ff:ff:ff:ff:ff` ; il est délimité par un routeur ou une frontière de
> VLAN. Le point clé : un switch découpe les domaines de collision mais **pas** ceux de broadcast. En
> pratique on s'y limite à quelques centaines d'hôtes, sinon ARP et multicast coûtent du CPU partout.

**3) Pourquoi une boucle en couche 2 est-elle bien plus grave qu'une boucle en couche 3 ?**
> Parce que la trame Ethernet n'a pas de champ TTL. En IP un paquet qui tourne meurt au bout de 64 sauts.
> En Ethernet rien ne le détruit : la trame est dupliquée à chaque passage et le nombre de copies croît
> exponentiellement. En quelques millisecondes on a une tempête de broadcast qui sature les liens, met le
> CPU des switchs à 100 % et rend la table CAM instable puisque la même MAC arrive par plusieurs ports.
> C'est exactement ce que STP résout, en bloquant logiquement les liens redondants.

**4) Comment se déroule l'élection du root bridge en STP ?**
> Chaque switch a un Bridge ID de 8 octets : 2 octets de priorité (32768 par défaut, pas de 4096) puis ses
> 6 octets de MAC. Le plus faible devient root : on compare la priorité, puis à égalité la MAC la plus basse
> — donc sans intervention c'est le switch le plus ancien, rarement le mieux placé. D'où la règle : fixer la
> priorité manuellement sur le switch de cœur, typiquement 4096, et 8192 sur son secours. Ensuite chaque
> switch non-root prend comme root port celui de moindre coût cumulé, chaque segment élit un designated
> port, et tout le reste est bloqué.

**5) Différence entre un port access et un port trunk ?**
> Un port access appartient à un seul VLAN et transmet des trames non taguées : l'hôte branché ignore
> l'existence des VLAN, c'est le switch qui ajoute le tag à l'entrée et le retire à la sortie. Un trunk
> transporte plusieurs VLAN et tague chaque trame avec un en-tête 802.1Q de 4 octets, sauf le VLAN natif.
> Access vers les hôtes, trunk entre switchs ou vers un hyperviseur multi-VLAN. Vigilance : le VLAN natif
> doit être un VLAN inutilisé, sinon on ouvre la porte au VLAN hopping par double tagging.

**6) Qu'est-ce qu'un gratuitous ARP, et à quoi ça sert en production ?**
> C'est un ARP où l'IP source est égale à l'IP cible : l'émetteur annonce sa propre adresse au lieu de poser
> une question. Trois usages : la détection de doublon d'adresse au démarrage ; surtout la bascule de haute
> disponibilité — quand une IP virtuelle change de serveur (keepalived, VRRP, failover PostgreSQL), le
> nouveau porteur émet un GARP qui met à jour instantanément les caches ARP du VLAN et les tables CAM, là où
> sans lui la bascule prendrait des minutes ; enfin la migration à chaud de VM.

**7) J'ai un agrégat LACP de 4 × 10 Gbit/s, mon transfert plafonne à 10 Gbit/s. Pourquoi ?**
> Parce qu'un LAG ne découpe pas les flux, il les répartit. Pour chaque trame l'équipement calcule un hash —
> sur les MAC, les IP, ou les IP et les ports selon la politique — et en déduit le lien. Toutes les trames
> d'un même flux prennent donc le même lien, pour que TCP ne reçoive pas ses segments dans le désordre : un
> flux TCP unique est plafonné à un membre. Pour exploiter les 40 Gbit/s il faut au moins autant de flux
> distincts que de liens et un hash `layer3+4`. C'est une des raisons pour lesquelles on parallélise les
> transferts de données.

**8) Un job Spark échoue en `FetchFailedException` mais le ping passe. Ta démarche ?**
> Mon premier réflexe est le MTU : la signature est typique, les petits paquets passent et les gros non. Je
> teste `ping -M do -s 1472` entre deux exécuteurs, puis je descends jusqu'à la limite réelle et je la
> compare au MTU des interfaces. La cause la plus fréquente est une encapsulation oubliée : VXLAN coûte
> 50 octets, donc sur un underlay à 1500 le MTU interne doit être 1450. La deuxième est un ICMP
> « Fragmentation Needed » bloqué par un Security Group, qui casse PMTUD et crée un trou noir. Correctifs :
> aligner les MTU, débloquer l'ICMP type 3 code 4, ou faire du MSS clamping.

**9) À quoi sert la table CAM, et que se passe-t-il quand elle est pleine ?**
> C'est la table qui associe une MAC à un port et à un VLAN. Le switch la remplit en observant la MAC source
> de chaque trame entrante et s'en sert pour décider où envoyer selon la MAC destination ; les entrées
> expirent au bout de 300 s par défaut et une destination inconnue est floodée sur tout le VLAN. Saturée,
> elle ne peut plus apprendre : le switch floode tout l'unicast inconnu et se comporte comme un hub. C'est
> le principe du MAC flooding, où l'attaquant génère des milliers de MAC sources aléatoires pour écouter le
> trafic des autres. Défense : le port security.

**10) Comment détecterais-tu un ARP spoofing avec un modèle ?**
> Les features naturelles : le nombre d'ARP replies non sollicitées par seconde et par source, le nombre de
> MAC distinctes associées à une même IP sur une fenêtre glissante, la fréquence de changement de
> l'association IP↔MAC, et le MAC flapping vu depuis la table CAM. Le signal le plus discriminant reste la
> contradiction avec la table DHCP snooping : une IP annoncée avec une MAC qui ne correspond pas au bail.
> Cela dit, avant le modèle, la vraie réponse en entreprise est déterministe — DHCP snooping plus Dynamic
> ARP Inspection, qui **jette** la trame contradictoire. Le modèle sert là où DAI n'est pas déployable.


## 14. Les 3 choses à retenir si tu ne retiens que ça

1. **L'IP survit au trajet, la MAC est recréée à chaque saut.** Le switch **apprend sur la source** et
   **décide sur la destination** ; il ne connaît que le segment local et floode ce qu'il ignore. Tout le
   reste de la couche 2 découle de ces deux phrases.

2. **La couche 2 n'a pas de TTL, donc une boucle tue le réseau.** C'est l'unique justification de STP :
   bloquer juste assez de liens pour qu'il ne reste qu'un chemin. Root bridge = Bridge ID le plus faible
   (priorité 32768 par défaut, puis MAC). Timers : Hello 2 s, Forward Delay 15 s, Max Age 20 s. RSTP
   converge en moins d'une seconde, 802.1D en 30 à 50 s.

3. **Le MTU est ce qui casse tes pipelines.** Standard 1500, jumbo 9000, VXLAN coûte 50 octets donc pod à
   1450. Signature du trou noir : le `ping` passe, le gros transfert bloque. Test : **`ping -M do -s 1472`**
   (= MTU − 28). Et un LAG ne fait jamais aller un flux TCP unique plus vite qu'un seul lien.

---

*Module suivant : `R03` — Couche 3 : IPv4, CIDR & subnetting, IPv6.*
