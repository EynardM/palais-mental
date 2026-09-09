# R04 — CHEATSHEET : Routage, routes statiques, OSPF

Référence opérationnelle. À garder ouverte pendant qu'on travaille.

---

## 1. Ordre de décision

| Rang | Critère | Départage | Note |
|---:|---|---|---|
| 1 | **Longest prefix match** | Le `/n` le plus long | Écrase AD et métrique |
| 2 | **Distance administrative** | Préfixes **strictement identiques** | La plus basse gagne |
| 3 | **Métrique** | Même préfixe **et** même protocole | La plus basse gagne |
| 4 | **ECMP** | Égalité parfaite | Répartition **par flux** (hash) |

## 2. Distances administratives (Cisco)

| AD | Source | | AD | Source |
|---:|---|---|---:|---|
| 0 | Connecté (`C`, `L`) | | 110 | **OSPF** |
| 1 | Statique | | 115 | IS-IS |
| 5 | Résumé EIGRP | | 120 | **RIP** |
| 20 | **eBGP** | | 170 | EIGRP externe |
| 90 | EIGRP interne | | 200 | **iBGP** |
| 100 | IGRP | | 255 | Inconnu → **jamais installée** |

Changer une AD : `distance ospf intra-area 90` · `distance 200 <source> <wildcard> <ACL>` ·
`ip route <net> <mask> <nh> <AD>` (statique flottante).

## 3. Métriques par protocole

| Protocole | Métrique | Plage / défaut |
|---|---|---|
| RIP | Nombre de sauts | 1-15, **16 = infini** |
| OSPF | Coût = Σ (réf / BP interface) | min **1**, réf **10⁸ bit/s** |
| EIGRP | `256 × (10⁷/BW_min_kbps + Σdélais_µs/10)` | K1=K3=1, K2=K4=K5=0 |
| IS-IS | Coût par interface | défaut **10**, wide metrics 24 bits |
| BGP | 11 critères en cascade | weight, local-pref, AS-path… |

## 4. Linux — `ip route`

| Commande | Effet |
|---|---|
| `ip route show` / `ip -6 route show` | Table `main` |
| `ip route show table all` | Toutes les tables |
| `ip route show table local` | Adresses locales et broadcasts |
| `ip route show vrf <vrf>` | Table d'une VRF |
| **`ip route get <IP>`** | **La décision réelle** (LPM + src + dev) |
| `ip route get <IP> from <src>` | Teste une règle de politique |
| `ip route add <préfixe> via <nh> dev <if>` | Ajoute |
| `ip route add <préfixe> dev <if>` | Via interface (P2P uniquement) |
| `ip route add default via <gw>` | Route par défaut |
| `ip route replace …` | Remplace ou crée |
| `ip route del <préfixe>` | Supprime |
| `ip route flush cache` | Vide le cache |
| `ip -s route show` | Avec compteurs |

**Options d'une route** : `metric N` (défaut 0, la plus basse gagne) · `src <IP>` (source préférée) ·
`scope global|link|host` · `proto static|kernel|dhcp|boot|ospf|bgp` · `onlink` (next-hop hors subnet connecté) ·
`mtu N` · `advmss N` · `table N`.

**Types de routes** :

| Type | Comportement |
|---|---|
| `unicast` (défaut) | Route normale |
| `blackhole` | Jette, **aucun ICMP** |
| `unreachable` | Jette + ICMP **type 3 code 0** |
| `prohibit` | Jette + ICMP **type 3 code 13** |
| `throw` | Abandonne la table, passe à la règle suivante |
| `local` / `broadcast` | Table `local`, gérées par le noyau |

**ECMP** :
```bash
ip route add 10.20.0.0/16 nexthop via 192.168.1.253 weight 1 \
                          nexthop via 192.168.1.254 weight 1
```

## 5. Linux — tables et règles

| Table | ID | Contenu |
|---|---:|---|
| `local` | **255** | Adresses locales, broadcasts (noyau) |
| `main` | **254** | La table normale |
| `default` | **253** | Quasi toujours vide |

| Priorité | Règle par défaut |
|---:|---|
| 0 | `from all lookup local` |
| 32766 | `from all lookup main` |
| 32767 | `from all lookup default` |

```bash
ip rule show                                        # lister
ip rule add from 192.168.2.0/24 table 200 priority 100
ip rule add to 10.50.0.0/16 table 201 priority 101
ip rule add fwmark 0x1 table 202                    # après marquage iptables/nft
ip rule del priority 100
echo "200 datapath" >> /etc/iproute2/rt_tables      # nommer une table
```

## 6. Linux — sysctl liés au routage

| Paramètre | Défaut | Rôle |
|---|---|---|
| `net.ipv4.ip_forward` | **0** (poste) | Active le routage IPv4 |
| `net.ipv6.conf.all.forwarding` | 0 | Idem IPv6 |
| `net.ipv4.conf.all.rp_filter` | **selon distro** | 0 off · **1 strict** · **2 loose**. Effectif = **max(all, if)** |
| `net.ipv4.fib_multipath_hash_policy` | **0** | 0 = L3 · 1 = L4 (5-tuple) · 2/3 = champs internes |
| `net.ipv4.conf.all.accept_redirects` | 1 (hôte) | Accepter les ICMP redirect |
| `net.ipv4.conf.all.send_redirects` | 1 | Émettre des ICMP redirect |
| `net.ipv4.route.max_size` | grand | Taille max de la FIB |

## 7. VRF Linux

```bash
ip link add vrf-prod type vrf table 100
ip link set vrf-prod up
ip link set eth1 master vrf-prod
ip route add default via 10.0.0.1 vrf vrf-prod
ip route show vrf vrf-prod
ip link show vrf vrf-prod
ip vrf show
ip vrf exec vrf-prod <commande>     # exécuter dans la VRF
ip route get 10.0.0.5 vrf vrf-prod
```

## 8. Cisco — routes statiques

```
ip route <réseau> <masque> <next-hop | interface> [AD] [name <texte>]
ip route 10.20.0.0 255.255.0.0 192.168.1.254            ! AD 1
ip route 10.20.0.0 255.255.0.0 192.168.1.253 130        ! flottante
ip route 0.0.0.0 0.0.0.0 203.0.113.1                    ! défaut
ip route 10.10.0.0 255.255.248.0 Null0                  ! anti-boucle de résumé
ip route vrf PROD 0.0.0.0 0.0.0.0 10.0.0.254            ! dans une VRF
ipv6 route 2001:db8::/32 2001:db8:0:1::1
```

**Masque ↔ wildcard** : wildcard = `255.255.255.255 − masque`.

| Préfixe | Masque | Wildcard |
|---|---|---|
| /8 | 255.0.0.0 | 0.255.255.255 |
| /16 | 255.255.0.0 | 0.0.255.255 |
| /21 | 255.255.248.0 | 0.0.7.255 |
| /24 | 255.255.255.0 | 0.0.0.255 |
| /30 | 255.255.255.252 | 0.0.0.3 |
| /32 | 255.255.255.255 | 0.0.0.0 |

## 9. Cisco — codes de `show ip route`

| Code | Sens | | Code | Sens |
|---|---|---|---|---|
| `C` | Connecté | | `O` | OSPF intra-aire |
| `L` | Locale /32 | | `O IA` | OSPF inter-aire |
| `S` | Statique | | `O E1` / `O E2` | OSPF externe type 1 / 2 |
| `S*` | Candidate default | | `O N1` / `O N2` | OSPF NSSA externe 1 / 2 |
| `R` | RIP | | `D` / `D EX` | EIGRP interne / externe |
| `B` | BGP | | `i` `L1` `L2` `ia` | IS-IS |

Format : `<code> <préfixe> [AD/métrique] via <next-hop>, <âge>, <interface>`

## 10. OSPF — valeurs de référence

| Élément | Valeur |
|---|---|
| Protocole IP | **89** |
| Multicast AllSPFRouters / AllDRouters | **224.0.0.5** / **224.0.0.6** |
| MAC multicast correspondantes | `01:00:5e:00:00:05` / `01:00:5e:00:00:06` |
| TTL des paquets | **1** |
| Distance administrative | **110** |
| Taille de l'en-tête | **24 o** (OSPFv3 : 16 o) |
| Hello / Dead — broadcast, point-to-point | **10 s / 40 s** |
| Hello / Dead — NBMA, point-to-multipoint | **30 s / 120 s** |
| RxmtInterval / InfTransDelay | 5 s / 1 s |
| Wait timer (élection DR) | = dead interval (**40 s**) |
| LSA MaxAge / LSRefreshTime | **3600 s** / **1800 s** |
| Numéro de séquence initial d'une LSA | `0x80000001` |
| Priorité d'interface (défaut / jamais DR) | **1** / **0** |
| Bande passante de référence | **10⁸ bit/s = 100 Mbit/s** |
| SPF throttle IOS (start / hold / max) | 5000 / 10000 / 10000 ms |
| LSA throttle IOS | 0 / 5000 / 5000 ms |
| `maximum-paths` (ECMP) IOS | **4** |
| RFC | **2328** (v2) · **5340** (v3) |

## 11. OSPF — paquets, états, LSA

| Type de paquet | Nom | Rôle |
|---:|---|---|
| 1 | Hello | Voisinage, keepalive, élection DR/BDR |
| 2 | DBD | En-têtes des LSA (catalogue) |
| 3 | LSR | Demande de LSA manquantes |
| 4 | LSU | Contenu des LSA |
| 5 | LSAck | Accusé de réception |

`DOWN → ATTEMPT → INIT → 2-WAY → EXSTART → EXCHANGE → LOADING → FULL`
DR/BDR élus en **2-Way** · MTU vérifié en **ExStart/Exchange**.

| LSA | Nom | Généré par | Portée |
|---:|---|---|---|
| 1 | Router | tous | l'aire |
| 2 | Network | **DR** | l'aire |
| 3 | Summary | **ABR** | autres aires |
| 4 | ASBR Summary | ABR | autres aires |
| 5 | AS External | **ASBR** | AS sauf stub |
| 7 | NSSA External | ASBR en NSSA | NSSA → type 5 par l'ABR |
| 9/10/11 | Opaque | — | lien / aire / AS |

| Type d'aire | T3 | T4/T5 | T7 | Défaut |
|---|:--:|:--:|:--:|:--:|
| Standard | ✅ | ✅ | ❌ | non |
| Stub | ✅ | ❌ | ❌ | ✅ |
| Totally stubby | ❌ | ❌ | ❌ | ✅ |
| NSSA | ✅ | ❌ | ✅ | option |
| Totally NSSA | ❌ | ❌ | ✅ | ✅ |

## 12. OSPF — table de coûts

| Bande passante | Réf. 100 Mbit/s (défaut) | Réf. 100 Gbit/s |
|---|---:|---:|
| 56 kbit/s | 1785 | — |
| 64 kbit/s | 1562 | 1 562 500 |
| 512 kbit/s | 195 | — |
| T1 — 1,544 Mbit/s | **64** | 64 766 |
| E1 — 2,048 Mbit/s | 48 | 48 828 |
| 10 Mbit/s | **10** | 10 000 |
| 100 Mbit/s | **1** | **1000** |
| 1 Gbit/s | **1** | **100** |
| 10 Gbit/s | **1** | **10** |
| 100 Gbit/s | **1** | **1** |

Préférence interne : **O > O IA > E1/N1 > E2/N2**. Seed metric redistribuée : **20** (depuis BGP : **1**), type **E2**.

## 13. OSPF — configuration

```
! Cisco
router ospf 1
 router-id 1.1.1.1
 auto-cost reference-bandwidth 100000        ! en Mbit/s → 100 Gbit/s
 passive-interface default
 no passive-interface GigabitEthernet0/0
 network 10.1.1.0 0.0.0.255 area 0           ! wildcard
 area 10 stub [no-summary]                   ! no-summary = totally stubby (ABR seul)
 area 30 nssa
 area 10 range 10.10.0.0 255.255.248.0       ! résumé inter-aire (ABR)
 summary-address 192.0.2.0 255.255.254.0     ! résumé externe (ASBR)
 redistribute static subnets metric 100 metric-type 1
 default-information originate [always]
 maximum-paths 8
 timers throttle spf 50 200 5000
!
interface GigabitEthernet0/0
 ip ospf 1 area 0                            ! méthode moderne
 ip ospf network point-to-point
 ip ospf cost 10
 ip ospf priority 0                          ! 0 = jamais DR
 ip ospf hello-interval 10
 ip ospf dead-interval 40
 ip ospf dead-interval minimal hello-multiplier 4
 ip ospf mtu-ignore                          ! contournement, pas correction
 ip ospf authentication message-digest
 ip ospf message-digest-key 1 md5 <clé>
 ip ospf bfd
```

```
# FRR — /etc/frr/frr.conf
router ospf
 ospf router-id 1.1.1.1
 auto-cost reference-bandwidth 100000
 passive-interface default
 network 10.1.1.0/24 area 0
 redistribute connected
!
interface eth0
 no ip ospf passive
 ip ospf network point-to-point
 ip ospf hello-interval 1
 ip ospf dead-interval 4
```

## 14. Diagnostic

| Commande | Ce que ça donne |
|---|---|
| `ip route get <IP>` | **La décision** : LPM, next-hop, dev, src |
| `ip rule show` | Ordre de consultation des tables |
| `ip -s link` | Compteurs d'erreurs d'interface |
| `ss -tanp \| grep <IP>` | `SYN-SENT` bloqué = pas de retour |
| `traceroute -n -T -p 443 <IP>` | Chemin **aller** en TCP (traverse les FW) |
| `mtr -T -P 443 <IP>` | Chemin + perte par saut, en continu |
| `tracepath <IP>` | Chemin + découverte de PMTU, sans root |
| `tcpdump -ni any host <IP>` | **Des deux côtés** : le juge de paix |
| `sysctl net.ipv4.ip_forward` | Le routage est-il activé |
| `sysctl net.ipv4.conf.all.rp_filter` | Reverse path filtering (max avec l'interface) |
| `vtysh -c "show ip ospf neighbor"` | Voisins FRR et leur état |

```
! Cisco
show ip route <IP>                 ! LPM + résolution récursive
show ip route ospf | static | connected
show ip protocols                  ! protocoles actifs, réseaux, AD
show ip cef <IP>                   ! la FIB
show ip ospf neighbor              ! états d'adjacence
show ip ospf interface brief       ! coût, aire, DR/BDR, timers
show ip ospf database [router|network|summary|external]
show ip ospf border-routers
show ip ospf statistics            ! fréquence des SPF
debug ip ospf adj                  ! formation d'adjacence
debug ip ospf hello
clear ip ospf process              ! force une réélection DR (COUPE le trafic)
```

## 15. Ports, protocoles et multicast des protocoles de routage

| Protocole | Transport | Multicast | AD |
|---|---|---|---:|
| **OSPFv2** | IP **89** | `224.0.0.5` / `224.0.0.6` | 110 |
| **OSPFv3** | IP 89 | `ff02::5` / `ff02::6` | 110 |
| **EIGRP** | IP **88** | `224.0.0.10` | 90 / 170 |
| **RIPv2** | UDP **520** | `224.0.0.9` | 120 |
| **RIPng** | UDP **521** | `ff02::9` | 120 |
| **BGP** | TCP **179** | — (unicast) | 20 / 200 |
| **IS-IS** | directement sur L2 | — | 115 |
| **BFD** | UDP **3784** (control), 3785 (echo) | — | — |
| **VRRP** | IP **112** | `224.0.0.18` | — |
| **HSRP** | UDP 1985 (v1) / 2029 (v2) | `224.0.0.2` / `224.0.0.102` | — |

## 16. Latence — ordres de grandeur

| Trajet | RTT |
|---|---:|
| Loopback | < 0,05 ms |
| Même AZ / rack | 0,1 - 0,5 ms |
| Inter-AZ, même région | 0,5 - 2 ms |
| Paris ↔ Francfort | ~ 10 ms |
| Europe ↔ US-est | ~ 75 - 90 ms |
| Europe ↔ Singapour | ~ 160 - 190 ms |
| **Plancher physique** | **~ 1 ms de RTT / 100 km** de fibre |

`10⁶ requêtes séquentielles × 80 ms = 22 h`. Batcher, paralléliser, rapprocher le calcul de la donnée.
