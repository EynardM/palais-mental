# R03 — Fiche : Couche 3 (IPv4, CIDR, IPv6)

> Lis-la **avant** le cours (pretesting) puis **récite-la** aux rappels. Objectif : 3 minutes.

## En-tête IPv4 — 20 o mini, 60 o maxi

| Champ | Taille | À retenir |
|---|---|---|
| Version | 4 b | 4 → 1er octet `0x45` en pratique |
| IHL | 4 b | en **mots de 4 o** : 5 → 20 o, max 15 → 60 o |
| DSCP + ECN | 6 + 2 b | EF = **46** (voix) · CS6 = 48 · ECN `11` = CE |
| Total Length | 16 b | **en-tête + données**, max 65 535 |
| Identification | 16 b | même valeur pour tous les fragments |
| Flags | 3 b | rés. · **DF** (Don't Fragment) · **MF** (More Fragments) |
| Fragment Offset | 13 b | **en unités de 8 octets** |
| TTL | 8 b | −1 par routeur ; 0 → ICMP 11 |
| Protocol | 8 b | **1 ICMP · 6 TCP · 17 UDP** · 47 GRE · 58 ICMPv6 · 89 OSPF |
| Header Checksum | 16 b | **en-tête seul**, recalculé à chaque saut |
| Src / Dst | 32 b ×2 | inchangées sauf NAT |

**TTL initiaux** : Linux/macOS **64** · Windows **128** · Cisco **255**.
**Ce que fait un routeur** : TTL −1 · checksum recalculé · en-tête L2 réécrit · IP/ports inchangés.

## Masques

| /n | Masque | Adr. | Hôtes | | /n | Masque | Adr. | Hôtes |
|---|---|---|---|---|---|---|---|---|
| /16 | 255.255.0.0 | 65 536 | 65 534 | | /26 | 255.255.255.192 | 64 | 62 |
| /20 | 255.255.240.0 | 4 096 | 4 094 | | /27 | 255.255.255.224 | 32 | 30 |
| /22 | 255.255.252.0 | 1 024 | 1 022 | | /28 | 255.255.255.240 | 16 | 14 |
| /23 | 255.255.254.0 | 512 | 510 | | /29 | 255.255.255.248 | 8 | 6 |
| /24 | 255.255.255.0 | 256 | 254 | | /30 | 255.255.255.252 | 4 | **2** |
| /25 | 255.255.255.128 | 128 | 126 | | /31 | 255.255.255.254 | 2 | 2 (P2P) |

**Valeurs légales d'un octet de masque** : `128 · 192 · 224 · 240 · 248 · 252 · 254 · 255`. Rien d'autre.
**Formules** : adresses = 2^(32−n) · hôtes = 2^(32−n) − 2 (pas de −2 en IPv6, ni en /31, ni en /32).

## Méthode de calcul (5 gestes)

```
 1. OCTET INTÉRESSANT = celui où le masque n'est ni 255 ni 0
 2. BLOC = 256 − valeur du masque dans cet octet
 3. Multiples du bloc : 0, bloc, 2×bloc, …
 4. RÉSEAU  = plus grand multiple ≤ valeur de l'IP dans cet octet
 5. BROADCAST = réseau suivant − 1  ·  utile = réseau+1 → broadcast−1
```

Repères d'alignement : /23 → 3ᵉ octet **pair** · /22 → multiple de **4** · /21 → **8** · /20 → **16**.
**VLSM** : trier du **plus gros au plus petit**, allouer en séquence, chaque bloc aligné sur sa taille.
**Agrégation** : plus long préfixe binaire commun, bloc aligné (8-9-10-11 → /22 ✔ ; 9-12 ✘).

## Adresses spéciales

| Plage | Sens |
|---|---|
| 10.0.0.0/8 · 172.16.0.0/**12** · 192.168.0.0/16 | privées RFC 1918 (172.16 → **172.31**) |
| 127.0.0.0/8 | loopback |
| **169.254.0.0/16** | APIPA → **le DHCP a échoué** |
| 169.254.169.254 | metadata cloud (credentials IAM) |
| 100.64.0.0/10 | CGNAT RFC 6598 |
| 224.0.0.0/4 | multicast (224.0.0.1 hôtes, 224.0.0.2 routeurs) |
| 255.255.255.255 | broadcast limité (DHCP DISCOVER) |
| 0.0.0.0/0 | route par défaut |

**Classes historiques** : A 1-126 /8 · B 128-191 /16 · C 192-223 /24 · D 224-239 multicast · E 240+.
**Routage** : *longest prefix match* — **le préfixe le plus long gagne**, toujours.

## IPv6

En-tête **40 o fixes** : Version · Traffic Class (8 b) · Flow Label (20 b) · Payload Length (**hors en-tête**)
· Next Header · Hop Limit · Src 128 b · Dst 128 b. **Pas de checksum. Pas de fragmentation par les routeurs.**
MTU minimum **1280**. Pas de broadcast.

Abréviation : zéros de tête supprimés + **une seule** suite nulle → `::`.
`2001:0db8:0000:0000:0000:ff00:0042:8329` → `2001:db8::ff00:42:8329`. URL : `http://[2001:db8::1]:8080/`.

| Plage | Rôle | | Préfixe | Usage |
|---|---|---|---|---|
| 2000::/3 | global unicast | | /32 | opérateur |
| fd00::/8 (fc00::/7) | ULA (≈ RFC 1918) | | /48 | un site → 65 536 /64 |
| **fe80::/10** | link-local (toujours présent) | | /56 | un particulier |
| ff00::/8 | multicast (ff02::1, ff02::2) | | **/64** | **un réseau, toujours** |
| ::1 / :: | loopback / non spécifiée | | /127 | lien P2P routeurs |

**SLAAC** : fe80:: → **DAD** (NS) → **RS (133)** → **RA (134)** → adresse globale = préfixe + Interface ID.
**NDP** : NS **135** / NA **136** remplacent ARP. Flags RA : **A** autonome · **M** DHCPv6 · **O** options.
Interface ID : EUI-64 (`fffe` inséré + 7ᵉ bit inversé) ou aléatoire (RFC 4941/7217).
DNS : **AAAA**. Dual-stack + **Happy Eyeballs** (RFC 8305). NAT64/DNS64 → `64:ff9b::/96`.

## ICMP

| Type/Code | Sens | | ICMPv6 | Sens |
|---|---|---|---|---|
| **8 / 0** | Echo Request / Reply | | 128 / 129 | Echo Request / Reply |
| 3/0, 3/1, 3/3 | net / host / **port** unreachable | | 1 | Destination Unreachable |
| **3 / 4** | **Frag needed + DF → PMTUD** | | **2** | **Packet Too Big** |
| 3 / 13 | administrativement interdit (REJECT) | | 3 | Time Exceeded |
| **11 / 0** | **TTL exceeded → traceroute** | | 133-136 | RS / RA / NS / NA |

Ping : payload **56 o** → 84 o de paquet IP. Traceroute Unix : UDP **33434+**, arrivée = ICMP 3/3.
**Bloquer tout ICMPv6 casse IPv6** (plus de NDP, plus de RA).

## MTU / MSS

`MSS = MTU − 40` (IPv4) → **1460** · `MSS = MTU − 60` (IPv6) → **1440**.
Overheads : **VXLAN 50 → 1450** · GRE 24 → 1476 · IP-in-IP 20 → 1480 · WireGuard 60 → **1420** · PPPoE → 1492.
Test : `ping -M do -s 1472 cible` (1472 + 8 + 20 = 1500). Correctif : MSS clamping ou MTU abaissé.
**Signature du trou noir PMTU** : handshake OK, petites requêtes OK, **gros transferts figés**.

## Cloud & K8s

- **AWS réserve 5 IP par subnet** (.0, .1 routeur, .2 DNS, .3 futur, dernière) → un /28 donne **11** utilisables.
- Un CIDR de subnet AWS est **immuable** après création.
- **CIDR chevauchants = peering impossible.** Contournement propre : PrivateLink, ou CIDR secondaire.
- Cluster CIDR /16 + podCIDR /24 par nœud → **256 nœuds max**. `maxPods` kubelet = **110** par défaut.
- AWS VPC CNI : pods max = `(ENI max × (IP/ENI − 1)) + 2` ; chaque pod **consomme une IP du VPC**.
- Latences : même AZ 0,1-0,5 ms · inter-AZ 0,5-2 ms · Paris↔Francfort 10 ms · Paris↔us-east-1 85 ms.
  Fibre : **5 µs/km** → 1000 km aller-retour = **10 ms**.

---

## Test express (réponses dans le cours)

1. En quelle unité s'exprime le champ Fragment Offset, et pourquoi cette unité ?
2. Un datagramme de 4000 o traverse un lien MTU 1500 : combien de fragments, quels offsets ?
3. Réseau, broadcast et plage utilisable de `172.22.145.77/19` ?
4. `10.4.130.9/23` et `10.4.129.200/23` sont-elles dans le même réseau ? Pourquoi ?
5. Quelles sont les 8 valeurs légales d'un octet de masque, dans l'ordre ?
6. Où s'arrête exactement `172.16.0.0/12` ?
7. Pourquoi un subnet IPv6 fait-il toujours /64, même pour 3 machines ?
8. Quel message ICMP porte le PMTU en IPv4, et lequel en IPv6 ?
