# R02 — FICHE : Couche 2 (Ethernet, MAC, ARP, commutation, VLAN, STP)

> Lire **avant** le cours (pretesting), puis réciter de mémoire aux rappels. Cible : **3 minutes**.
> **L'IP survit au trajet, la MAC est recréée à chaque saut.** Le switch **apprend sur la MAC source**,
> **décide sur la MAC destination**, et ne dépasse jamais le segment local.

## Trame Ethernet II
```
[Préambule 7][SFD 1] [MAC dest 6][MAC src 6] ([Tag 4]) [Type 2][Payload 46-1500][FCS 4] (IFG 12)
 └─ hors trame ────┘  └──────────── trame : 64 à 1518 octets ────────────────────────┘
```

| Grandeur | Valeur | | Grandeur | Valeur |
|---|---|---|---|---|
| Trame min / max | **64 / 1518** o (68 / **1522** avec tag) | | Overhead L2 | **18** o (6+6+2+4) |
| Payload = MTU | **46 à 1500** o | | Sur le fil / IFG | **38** o / 12 o (96 temps-bit) |

**EtherType** : ≤ 1500 = longueur ; ≥ 1536 = type. `0800` IPv4 · `0806` ARP · `86DD` IPv6 · `8100` VLAN ·
`88A8` QinQ · `8809` LACP · `88CC` LLDP. **FCS faux → trame jetée en silence**, aucune retransmission L2.
**Rendement** : 1500 o → 97,5 % du fil, **81 274 trames/s à 1 Gbit/s** ; 64 o → **1,488 Mpps**.

## Adresses MAC
**48 bits** = **OUI 24 b** (constructeur) + **NIC 24 b**. Premier octet : bit 0 = **I/G** (0 unicast,
1 multicast) · bit 1 = **U/L** (1 = locally administered).

| 2e chiffre hexa | Sens | | MAC spéciale | Usage |
|---|---|---|---|---|
| 0,4,8,C | unicast universelle | | `ff:ff:ff:ff:ff:ff` | broadcast |
| **2,6,A,E** | unicast **locale** (VM, Docker) | | `01:80:c2:00:00:00` | BPDU STP |
| 1,5,9,D | multicast universelle | | `01:80:c2:00:00:02` | LACP |
| 3,7,B,F | multicast locale | | `01:80:c2:00:00:0e` | LLDP |

**Premier octet pair = unicast, impair = multicast.** Multicast IPv4 → `01:00:5e` + 23 bits bas de l'IP
(32 groupes par MAC) ; IPv6 → `33:33` + 32 bits bas.

## ARP — EtherType `0x0806`
**Requête = broadcast · Réponse = unicast.** En-tête **28 o** → trame 42 o **bourrée à 64**. Champs :
HTYPE, PTYPE, HLEN(6), PLEN(4), OPER (**1 req / 2 reply**), SHA, SPA, THA (**= 00:00:00:00:00:00** en
requête), TPA.

| Valeur | Défaut | | Notion | Définition |
|---|---|---|---|---|
| `base_reachable_time` Linux | **30 s** | | **Gratuitous ARP** | **SPA == TPA** : on annonce, on ne demande pas |
| `gc_stale_time` | 60 s | | Usages du GARP | doublon d'IP, bascule HA/VRRP, migration de VM |
| `gc_thresh1/2/3` | **128/512/1024** | | **ARP spoofing** | reply mensongère → MITM, aucune authentification |
| Cache ARP Cisco | **4 h** | | Défense | **DHCP snooping + DAI**, port security |

États : `INCOMPLETE → REACHABLE → STALE → DELAY → PROBE → FAILED` (+ `PERMANENT`). Piège K8s :
`gc_thresh3` à 1024 → `neighbor table overflow` sur un nœud dense.

## Commutation
```
Trame reçue sur P → 1) APPRENDRE (MAC src → P)   2) DÉCIDER sur MAC dest :
   broadcast/multicast → FLOOD | connue sur Q≠P → COMMUTE | connue sur P → FILTRE | inconnue → FLOOD
                        3) OUBLIER après l'aging time
```

| Élément | Valeur |
|---|---|
| **Aging time table CAM** | **300 s** — taille : ~8 000 (accès) à 500 000+ (datacenter) |
| Table CAM saturée | il **floode tout** → devient un hub (**MAC flooding**) ; défense : **port security** |
| Store-and-forward / cut-through | 2-10 µs (FCS vérifié) / 0,3-1 µs (non vérifié) |
| Unknown unicast flooding | CAM 300 s vs ARP Cisco 4 h → flood permanent d'un flux |

**Domaine de collision** : 1 par port de switch — mort en full-duplex. **Domaine de broadcast** : découpé
par un **routeur ou un VLAN**, jamais par le switch — max 200-500 hôtes (/24, /23).
Latences : **5 µs/km en fibre** · 1500 o à 10 Gbit/s = 1,2 µs de sérialisation · RTT intra-DC 50-500 µs.

## VLAN — 802.1Q
Tag de **4 o** après la MAC source : **TPID `0x8100`** (16 b) + **PCP** (3 b, QoS 802.1p) + **DEI** (1 b)
+ **VID** (**12 b**). VID **0** priority-tagged · **1** défaut · **4095** réservé → **4094 utilisables**.
Limite 12 bits → VXLAN et son **VNI de 24 bits** (16,7 M segments).

| | Access | Trunk |
|---|---|---|
| VLAN | 1 | plusieurs |
| Tag | aucun (le switch ajoute/retire) | 802.1Q, **sauf VLAN natif** |
| Vers | hôte | switch, routeur, hyperviseur |

**VLAN hopping (double tagging)** : l'attaquant sur le VLAN natif forge 2 tags, SW-1 retire le premier,
SW-2 délivre dans le VLAN visé. Parade : VLAN natif inutilisé, `switchport nonegotiate`, ports morts en
shut. Un VLAN, c'est de la **segmentation**, pas de la sécurité.

## STP / RSTP
**Pas de TTL en L2 → une boucle = tempête de broadcast exponentielle.** BPDU toutes les 2 s vers `01:80:c2:00:00:00`.

```
Bridge ID = [priorité 2 o, défaut 32768, pas de 4096][MAC 6 o]
1. ROOT BRIDGE = BID le plus faible (priorité, puis MAC la plus basse)
2. ROOT PORT   = coût cumulé le plus faible vers le root (1 par switch non-root)
3. DESIGNATED  = 1 par segment (tous les ports du root le sont)
4. le RESTE est bloqué        Départage : Coût → Bridge ID → Port ID
```

| Coût *short* | 10M=100 · **100M=19** · **1G=4** · **10G=2** | | Timer | Valeur |
|---|---|---|---|---|
| Coût *long* | 100M=200 000 · 1G=20 000 · 10G=2 000 · 100G=200 | | **Hello** | **2 s** |
| États 802.1D | Disabled→Blocking→**Listening 15 s**→**Learning 15 s**→Forwarding | | **Forward Delay** | **15 s** |
| États RSTP | **Discarding / Learning / Forwarding** | | **Max Age** | **20 s** |
| Rôles RSTP | Root / Designated / **Alternate** / **Backup** | | Converg. 802.1D | **30 à 50 s** |
| Variantes | 802.1D · **802.1w** RSTP · **802.1s** MSTP · PVST+ | | Converg. RSTP | **< 1 s** |

Protections : **PortFast + BPDU Guard** (toujours ensemble), Root Guard, Loop Guard, UDLD, storm control.
Datacenter : leaf-spine, L3 jusqu'au rack, overlay VXLAN/EVPN → STP n'est plus qu'un filet de sécurité.

## LACP — 802.3ad / 802.1AX
LACPDU `0x8809` vers `01:80:c2:00:00:02` · période **30 s** (slow) ou **1 s** (fast), timeout ×3 · **8 liens
actifs max** · modes `active`/`passive` (jamais passive des deux côtés). **Un LAG répartit, il ne découpe
pas : un flux TCP unique = un seul lien.** Hash `layer2` / `layer2+3` / **`layer3+4`** / `encap3+4`.
Bonding Linux : **mode 4 = 802.3ad**, mode 1 = active-backup.

## MTU
| Terme | Valeur | | Encapsulation | Coût |
|---|---|---|---|---|
| MTU standard | **1500** | | 802.1Q | 4 o (hors payload) |
| Jumbo | **9000** (MSS 8960) | | **VXLAN** | **50 o** → MTU interne **1450** |
| MSS IPv4 | **MTU − 40** → 1460 | | IPIP / GRE | 20 / 24 o |
| Test | **`ping -M do -s 1472`** (= MTU − 28) | | WireGuard | 60 o → 1420 |

**Trou noir PMTU** : petits paquets OK, gros bloqués → l'ICMP **type 3 code 4** est filtré. Correctifs :
aligner les MTU · débloquer l'ICMP · MSS clamping · baisser le MTU des pods. Cloud : AWS VPC **9001**
(TGW 8500, IGW 1500) · **GCP 1460** par défaut · pod K8s VXLAN **1450**. Gain jumbo : **+4,4 % de débit**
mais **÷ 5,9 sur les trames/s** — le gain est CPU.

**Diagnostic express** — `ip -s link` (erreurs) · `ip neigh` (voisins) · `ping -M do -s 1472` (MTU) · `tcpdump -e` (voir la L2) ·
`bridge fdb show` (CAM Linux) · `cat /proc/net/bonding/bond0` · `ethtool -S eth0 | grep crc`.

---

## Test express — 8 questions, réponses dans le cours
1. Taille min et max d'une trame Ethernet II non taguée, et taille du payload correspondant ?
2. Sur quelle adresse un switch apprend-il ? Sur laquelle décide-t-il ?
3. Qu'est-ce qui distingue un gratuitous ARP d'un ARP normal, et à quoi sert-il ?
4. Combien de bits pour le VID, et combien de VLAN utilisables ? Pourquoi VXLAN existe-t-il ?
5. Cite les 3 timers STP avec leurs valeurs, et le temps de convergence de 802.1D.
6. Un switch 24 ports en un seul VLAN : combien de domaines de collision, combien de broadcast ?
7. Agrégat LACP 4 × 10 Gbit/s : quel débit pour un seul flux TCP, et pourquoi ?
8. Quelle taille de `ping -M do -s` teste un MTU de 9000 ? Quel MSS en découle ?
