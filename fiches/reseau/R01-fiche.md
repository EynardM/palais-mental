# FICHE R01 — Modèle en couches : OSI, TCP/IP, encapsulation

## Les 7 couches OSI

| # | Nom | Rôle en 4 mots | PDU | Exemples |
|---|---|---|---|---|
| 7 | Application | Sens du message | Données | HTTP, DNS, SSH |
| 6 | Présentation | Format, chiffrement | Données | TLS, UTF-8, JPEG |
| 5 | Session | Dialogue, reprise | Données | RPC, SOCKS |
| 4 | Transport | Bout en bout, ports | **Segment** (TCP) / **Datagramme** (UDP) | TCP, UDP |
| 3 | Réseau | Adressage global, routage | **Paquet** | IP, ICMP, OSPF |
| 2 | Liaison | Un saut, MAC, FCS | **Trame** | Ethernet, Wi-Fi |
| 1 | Physique | Bits → signal | **Bit** | RJ45, fibre |

**Mnémo bas→haut** : *Pour Le Réseau, Tout Se Passe Automatiquement*
**Mnémo PDU bas→haut** : Bit, Trame, Paquet, Segment, Données → *Bien Traiter Petits Segments de Données*

## Correspondance OSI ↔ TCP/IP (4 couches)

| TCP/IP | OSI | Schéma « 1-1-1-3 » en partant du bas |
|---|---|---|
| Application | 5+6+7 | 3 couches OSI |
| Transport | 4 | 1 |
| Internet | 3 | 1 |
| Accès réseau | 1+2 | 2 couches OSI |

## Encapsulation — les chiffres

```
DATA  ->  [TCP 20]DATA  ->  [IP 20][TCP 20]DATA  ->  [Eth 14][IP][TCP]DATA[FCS 4]
segment                paquet                    trame
```

| Élément | Taille |
|---|---|
| Ethernet II / VLAN 802.1Q / FCS | **14 o** / +4 o / 4 o |
| IPv4 min-max / IPv6 fixe | **20**–60 o / **40 o** |
| TCP min-max / UDP | **20**–60 o / **8 o** |
| Charge utile Ethernet | 46 à **1500 o** |
| Trame complète | 64 à **1518 o** (1522 avec VLAN) |
| Sur le fil | 1538 o (+ préambule 8 + IFG 12) |

**Total en-têtes TCP/IPv4/Ethernet = 14 + 20 + 20 = 54 o.** Mnémo : **14 / 20 / 20 / 8**.

## Démultiplexage en remontant

| Passage | Champ | Valeurs |
|---|---|---|
| L2 → L3 | `EtherType` | 0x0800 IPv4 · 0x0806 ARP · 0x86DD IPv6 · 0x8100 VLAN |
| L3 → L4 | `Protocol` | 1 ICMP · 6 TCP · 17 UDP · 47 GRE · 50 ESP · 58 ICMPv6 |
| L4 → app | Port destination | 22 SSH · 53 DNS · 443 HTTPS · 5432 PG · 9092 Kafka |

## MTU / MSS / fragmentation

- **MTU** = taille max du **paquet IP** (en-tête IP compris). **N'inclut PAS** Ethernet ni FCS.
- **MSS = MTU − en-tête IP − en-tête TCP** → IPv4 : **1500 − 40 = 1460**. IPv6 : 1440. Souvent 1448 (option timestamps, 12 o).
- MSS **annoncé dans les options du SYN** par chaque côté.

| Contexte | MTU |
|---|---|
| Ethernet / jumbo | 1500 / 9000 |
| AWS VPC / sortie IGW | 9001 / 1500 |
| GCP VPC défaut | 1460 |
| VXLAN sur 1500 (−50 o) | **1450** |
| WireGuard sur 1500 (−80 o) | 1420 |
| Minimum IPv4 / IPv6 | 68 / **1280** |

**Fragmentation IPv4** : offset en **unités de 8 octets** → chaque fragment (sauf le dernier) est un multiple de 8. Flag **MF**=1 sauf sur le dernier, même **Identification**. **Réassemblage à la destination finale uniquement.**
**DF=1** → le routeur jette + **ICMP type 3 code 4** (*Fragmentation Needed*, avec Next-Hop MTU). IPv6 : **ICMPv6 type 2** (*Packet Too Big*), les routeurs IPv6 **ne fragmentent jamais**.
**Test** : `ping -M do -s 1472 <ip>` (1472 + 8 + 20 = 1500). Plus grand `-s` qui passe **+ 28** = PMTU.

## Équipements

| Couche | Équipement | Décide sur |
|---|---|---|
| 1 | Hub / répéteur | rien |
| 2 | Switch (table CAM, aging 300 s) | MAC destination |
| 3 | Routeur (longest prefix match) | IP destination |
| 4 | Pare-feu stateful, NAT, NLB | 5-tuple IP+port+proto |
| 7 | Reverse proxy, ALB, WAF, Ingress | URL, Host, cookie, SNI |

**Le switch coupe les collisions, le routeur coupe les broadcasts.**

## Traversée d'un routeur

| | Avant | Après |
|---|---|---|
| MAC src/dst | A / routeur | routeur / B — **CHANGÉES** |
| IP src/dst | A / B | A / B — **IDENTIQUES** (sauf NAT) |
| Ports TCP | x / y | x / y — **IDENTIQUES** |
| TTL | 64 | 63 — **−1** |
| Checksum IP | — | **recalculé** |

**« L'IP c'est la destination du voyage, la MAC c'est le prochain arrêt. »**
ARP se fait pour la **passerelle**, jamais pour une destination hors sous-réseau (ARP = broadcast local, ne traverse pas un routeur).
**TTL initiaux** : Linux 64 · Windows 128 · Cisco 255.

## Où le modèle fuit

| Fuite | Nature |
|---|---|
| Checksum TCP/UDP | pseudo-en-tête → L4 lit la L3 (d'où recalcul par le NAT) |
| TLS | au-dessus de L4, sous L7 → « couche 6 » par convention |
| VXLAN | trame L2 dans de l'UDP, port **4789**, VNI **24 bits**, **−50 o** |
| QUIC | transport complet en **espace utilisateur** sur UDP 443 = HTTP/3 |
| LB L7 | termine TCP et en rouvre une autre : fin du end-to-end |

## Chiffres data engineer

| Quantité | Valeur |
|---|---|
| RTT intra-AZ / inter-AZ | 0,1–0,5 ms / 0,5–2 ms |
| RTT Paris↔Francfort / ↔us-east-1 / ↔Singapour | 10 ms / 80-90 ms / 160-180 ms |
| Lumière en fibre | 5 µs/km → **10 ms aller-retour pour 1000 km** |
| **Débit TCP = Fenêtre / RTT** | sans window scaling : 65 535 o / 80 ms ≈ **6,5 Mb/s** |
| BDP 10 Gb/s × 80 ms | **100 Mo** de fenêtre nécessaires |
| Handshake TCP / +TLS1.3 / QUIC | 1 RTT / 2 RTT / 1 RTT (0-RTT en reprise) |
| Plage éphémère Linux | **32768–60999** |
| NodePort K8s | 30000–32767 |

## Diagnostic en 3 réflexes

- `Connection refused` immédiat → **ça arrive, personne n'écoute** (L7/app).
- `Connection timed out` → **ça n'arrive pas** (DROP, security group, route).
- Handshake OK mais **gros transferts figés** → **MTU / PMTU black hole**.

---

## Test express (réponses dans le cours)

1. Quelle est la première couche de bout en bout, et pourquoi les routeurs ne la lisent-ils pas ?
2. Taille d'un en-tête IPv6, et pourquoi n'a-t-il pas de checksum ?
3. Un datagramme IPv4 de 4000 o traverse un lien MTU 1500 : combien de fragments, quels offsets ?
4. Le MTU inclut-il l'en-tête Ethernet ? Que vaut la trame complète pour MTU 1500 ?
5. Pourquoi une machine fait-elle un ARP pour sa passerelle et non pour la destination ?
6. Quel message ICMP porte l'information de PMTU en IPv4 ? Et en IPv6 ?
7. Débit max d'une connexion TCP unique avec 64 KiB de fenêtre et 80 ms de RTT ?
8. Combien d'octets d'overhead ajoute VXLAN, et quel MTU interne sur un underlay à 1500 ?
