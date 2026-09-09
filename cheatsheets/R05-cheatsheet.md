# R05 — Cheatsheet : BGP, AS, peering, MPLS

Référence opérationnelle. À garder ouverte pendant qu'on travaille.

---

## 1. Ports, protocoles, distances

| Protocole | Transport | Port / n° | Note |
|---|---|---|---|
| **BGP** | TCP | **179** | sessions unicast, voisins déclarés à la main |
| **LDP** (découverte) | UDP | **646** | hello vers **224.0.0.2** |
| **LDP** (session) | TCP | **646** | échange de labels |
| **RSVP-TE** | IP | proto **46** | traffic engineering, FRR |
| **RPKI-RTR** | TCP | **323** | validateur → routeur |
| **BMP** | TCP | souvent **11019** | streaming de la table BGP |
| OSPF | IP | proto 89 | rappel R04 |
| BFD | UDP | 3784 (1 saut), 4784 (multi-saut) | détection < 1 s |

| Source de route | Distance adm. Cisco |
|---|---|
| Connecté | 0 |
| Statique | 1 |
| **eBGP** | **20** |
| EIGRP interne | 90 |
| OSPF | 110 |
| RIP | 120 |
| EIGRP externe | 170 |
| **iBGP** | **200** |

---

## 2. Numéros d'AS

| Plage | Bits | Usage |
|---|---|---|
| 0 | 16 | réservé |
| 1 – 64 495 | 16 | public |
| 64 496 – 64 511 | 16 | documentation (RFC 5398) |
| **64 512 – 65 534** | 16 | **privé** |
| 65 535 | 16 | réservé |
| **23 456** | 16 | **AS_TRANS** (compat. 32 bits) |
| 65 536 – 65 551 | 32 | documentation |
| 65 552 – 4 199 999 999 | 32 | public |
| **4 200 000 000 – 4 294 967 294** | 32 | **privé** |

**ASN publics utiles** : 3356 Lumen · 2914 NTT · 15169 Google · **16509 AWS** (+14618) · 8075 Microsoft ·
**12076 Azure ExpressRoute** · 13335 Cloudflare · 32934 Meta · 16276 OVH · 3215 Orange.

---

## 3. Format des messages BGP

```
En-tête (19 o) : | MARKER 16 o (0xFF×16) | LENGTH 2 o | TYPE 1 o |
LENGTH : 19 min, 4096 max (65535 si RFC 8654 négocié)
```

| Type | Message | Taille mini | Contenu |
|---|---|---|---|
| 1 | OPEN | 29 o | Version 1 o · My AS 2 o · Hold 2 o · BGP-ID 4 o · OptLen 1 o |
| 2 | UPDATE | 23 o | WdrLen 2 o · Withdrawn · AttrLen 2 o · Attributs · NLRI |
| 3 | NOTIFICATION | 21 o | Code 1 o · Subcode 1 o · Data — **ferme la session** |
| 4 | KEEPALIVE | 19 o | en-tête seul |
| 5 | ROUTE-REFRESH | 23 o | AFI 2 o · réservé 1 o · SAFI 1 o |

### Codes NOTIFICATION

| Code | Nom | Sous-codes fréquents |
|---|---|---|
| 1 | Message Header Error | 2 bad length · 3 bad type |
| 2 | OPEN Message Error | 1 version · **2 Bad Peer AS** · 3 bad BGP-ID · 4 param non supporté · 6 hold time |
| 3 | UPDATE Message Error | 1 attr list · 3 attr WK manquant · 11 AS_PATH malformé |
| 4 | **Hold Timer Expired** | — |
| 5 | FSM Error | — |
| 6 | **Cease** (RFC 4486) | **1 Maximum Prefixes** · 2 shutdown · 3 peer dé-configuré · 4 reset admin · 6 config change |

### Capacités (OPEN, param. optionnel type 2)

| Code | Capacité | RFC |
|---|---|---|
| 1 | Multiprotocol (MP-BGP) | 4760 |
| 2 | Route Refresh | 2918 |
| 64 | Graceful Restart | 4724 |
| **65** | **4-octet AS** | 6793 |
| 69 | ADD-PATH | 7911 |
| 70 | Enhanced Route Refresh | 7313 |

### AFI / SAFI

| AFI | SAFI | Famille |
|---|---|---|
| 1 | 1 | IPv4 unicast |
| 1 | 4 | IPv4 **labeled unicast** (MPLS) |
| **1** | **128** | **VPNv4 (VPN L3 MPLS)** |
| 2 | 1 | IPv6 unicast |
| 2 | 128 | VPNv6 |
| **25** | **70** | **L2VPN EVPN** |

---

## 4. Timers

| Timer | Défaut | Note |
|---|---|---|
| **Hold time** | **90 s** | négocié = **min** des deux OPEN ; 0 = pas de keepalive |
| **Keepalive** | **30 s** | = hold / 3 |
| ConnectRetry | 120 s | avant nouvelle tentative TCP |
| MRAI eBGP | 30 s | souvent ramené à 0 aujourd'hui |
| MRAI iBGP | 5 s | idem |
| Scan / import | 60 s (Cisco) | revalidation des next-hops |
| BFD (typique) | 300 ms × 3 | détection ≈ 900 ms |

**Dampening (RFC 2439, désactivé par défaut)** : pénalité **1000** par flap · half-life **15 min** ·
suppress **2000** · reuse **750** · max suppress **60 min**. Déconseillé par le RIPE en configuration
agressive.

---

## 5. Attributs — table de référence

| Type | Nom | Catégorie | Défaut | Sens |
|---|---|---|---|---|
| 1 | ORIGIN | WK mandatory | — | 0 IGP `i` / 1 EGP `e` / 2 INCOMPLETE `?` — **min** |
| 2 | AS_PATH | WK mandatory | — | **min** ; AS_SET = 1 |
| 3 | NEXT_HOP | WK mandatory | — | doit être joignable |
| 4 | MED | opt. non-trans. | 0 | **min**, même AS voisin |
| 5 | LOCAL_PREF | WK discretionary | **100** | **max**, AS local |
| 6 | ATOMIC_AGGREGATE | WK discretionary | — | info perdue par agrégation |
| 7 | AGGREGATOR | opt. trans. | — | ASN + router-ID de l'agrégateur |
| 8 | COMMUNITY | opt. trans. | — | 4 o |
| 9 | ORIGINATOR_ID | opt. non-trans. | — | anti-boucle RR |
| 10 | CLUSTER_LIST | opt. non-trans. | — | anti-boucle RR |
| 14 | MP_REACH_NLRI | opt. non-trans. | — | annonces multiprotocoles |
| 15 | MP_UNREACH_NLRI | opt. non-trans. | — | retraits multiprotocoles |
| 16 | Extended Communities | opt. trans. | — | 8 o — **Route Target** |
| 32 | Large Communities | opt. trans. | — | 12 o |
| — | **WEIGHT** | **non-attribut, Cisco** | **0** / **32768** si local | **max**, 0-65535, local au routeur |

**Octet de flags** : `0x80` Optional · `0x40` Transitive · `0x20` Partial · `0x10` Extended Length.

**Segments AS_PATH** : 1 AS_SET (compte 1) · 2 AS_SEQUENCE (compte n) · 3 AS_CONFED_SEQUENCE (compte 0) ·
4 AS_CONFED_SET (compte 0).

---

## 6. Sélection du meilleur chemin

```
0. NEXT_HOP joignable ?      → sinon éliminée
1. WEIGHT              max   (Cisco, local au routeur)
2. LOCAL_PREF          max   (défaut 100)
3. Originée localement       (network / aggregate / redistribute)
4. AS_PATH             min
5. ORIGIN              min   (IGP 0 < EGP 1 < INCOMPLETE 2)
6. MED                 min   (même AS voisin uniquement)
7. eBGP > iBGP
8. Métrique IGP → NEXT_HOP   min   (hot potato)
9. eBGP le + ancien → router-ID min → cluster-list min → IP voisin min
```
`N W L O A O M E I R` — « **N**os **W**agons **L**ivrent **O**nze **A**nanas **O**range, **M**ais **E**lle **I**gnore **R**obert. »

| Modificateur | Effet |
|---|---|
| `bgp always-compare-med` | compare le MED entre AS voisins différents (risque d'oscillation) |
| `bgp deterministic-med` | groupe les chemins par AS avant comparaison |
| `bgp bestpath as-path ignore` | saute le critère 4 |
| `bgp bestpath compare-routerid` | force le départage par router-ID plutôt que par ancienneté |
| `maximum-paths N` | installe N chemins (ECMP) — eBGP ; `ibgp N` pour l'interne |

---

## 7. Communities

| Nom | Valeur hex | Valeur `ASN:x` |
|---|---|---|
| INTERNET | 0 | — |
| **NO_EXPORT** | `0xFFFFFF01` | 65535:65281 |
| **NO_ADVERTISE** | `0xFFFFFF02` | 65535:65282 |
| NO_EXPORT_SUBCONFED | `0xFFFFFF03` | 65535:65283 |
| GRACEFUL_SHUTDOWN | `0xFFFF0000` | **65535:0** |
| **BLACKHOLE** | `0xFFFF029A` | **65535:666** |

| Famille | Taille | Notation | RFC |
|---|---|---|---|
| Standard | 4 o | `ASN16:val16` | 1997 |
| Extended | 8 o | typée (RT, RD, SoO) | 4360 |
| Large | 12 o | `ASN32:val32:val32` | 8092 |

**AWS Direct Connect (public VIF)** — ce que **tu** poses sur tes annonces : `7224:7100` local pref bas ·
`7224:7200` moyen · `7224:7300` haut · `7224:9100` portée région locale · `7224:9200` continent ·
`7224:9300` global.
Ce qu'**AWS** pose sur les annonces qu'il t'envoie (à filtrer chez toi) : `7224:8100` route de la même
région · `7224:8200` route du même continent · sans tag = global.

---

## 8. MPLS

```
| LABEL (20 b) | TC (3 b) | S (1 b) | TTL (8 b) |   → 32 bits = 4 octets
   0 à 1048575    QoS      1 = fond   anti-boucle
EtherType : 0x8847 unicast · 0x8848 multicast
```

| Label | Nom | Effet |
|---|---|---|
| **0** | IPv4 Explicit NULL | dépiler, traiter en IPv4 |
| 1 | Router Alert | vers le plan de contrôle |
| **2** | IPv6 Explicit NULL | dépiler, traiter en IPv6 |
| **3** | **Implicit NULL** | annoncé pour déclencher le **PHP** |
| 13 | GAL | OAM |
| 14 | OAM Alert | OAM |
| **16 – 1 048 575** | plage utilisable | — |

| Rôle | Sigle | Opération |
|---|---|---|
| Ingress / bordure | **LER**, **PE** | **PUSH** |
| Cœur | **LSR**, **P** | **SWAP** |
| Egress | LER, PE | **POP** (ou PHP par l'avant-dernier) |
| Client | **CE** | aucune notion de MPLS |

**VPN L3 (RFC 4364)** : VRF · **RD 8 o** = unicité seule · **RT** (ext. community 8 o) = import/export ·
route VPNv4 = **12 o** · MP-BGP AFI 1 / SAFI 128 · **2 labels** (externe transport, interne VPN).
**SRGB Cisco par défaut** : 16000 – 23999.

### Surcoût d'encapsulation (mémo MTU)

| Encapsulation | Octets ajoutés | MTU interne typique |
|---|---|---|
| 1 label MPLS | **4** | 1496 |
| 2 labels (VPN L3) | **8** | 1492 |
| VLAN 802.1Q | 4 | 1496 |
| GRE | 24 | 1476 |
| **VXLAN** | **50** | **1450** |
| IPsec ESP (tunnel) | 50 – 73 | 1400 – 1450 |
| WireGuard | 60 – 80 | 1420 – 1440 |
| PPPoE | 8 | 1492 |

---

## 9. RPKI

| Élément | Détail |
|---|---|
| **ROA** | `(préfixe, maxLength, ASN d'origine)`, signé |
| Validateurs | Routinator · rpki-client · FORT · OctoRPKI |
| Transport dépôts | RRDP (HTTPS) ou rsync, rafraîchi ≈ 10 min |
| **RTR** | RFC 6810 / 8210, **TCP 323** |
| Verdicts | **VALID** · **INVALID** (rejeter) · **NOT FOUND** |
| Ne protège pas | le **chemin** (→ BGPsec RFC 8205) · les **fuites** (→ ASPA) |
| IRR | RADB, RIPE DB — objets `route:` `route6:` `as-set:` |
| Filtres conventionnels | accepter au plus **/24** IPv4, **/48** IPv6 |

```bash
# Générer un filtre de préfixes depuis l'IRR
bgpq4 -4 -l PREFIXES-CUSTOMER AS-CUSTOMER          # Cisco prefix-list
bgpq4 -6 -l PREFIXES6-CUSTOMER AS-CUSTOMER
bgpq4 -J -l customer AS-CUSTOMER                   # sortie JunOS
bgpq4 -f 65001 -l AS-PATH AS-CUSTOMER              # filtre as-path
```

---

## 10. Commandes — Cisco IOS

```
! ---- configuration de base
router bgp 65001
 bgp router-id 10.0.0.1
 bgp log-neighbor-changes
 no bgp default ipv4-unicast
 network 203.0.113.0 mask 255.255.255.0
 neighbor 198.51.100.2 remote-as 64500          ! eBGP
 neighbor 198.51.100.2 password S3cr3t          ! MD5 (RFC 2385)
 neighbor 198.51.100.2 maximum-prefix 200 90 restart 15
 neighbor 198.51.100.2 ttl-security hops 1      ! GTSM
 neighbor 10.0.0.2 remote-as 65001              ! iBGP
 neighbor 10.0.0.2 update-source Loopback0
 neighbor 10.0.0.2 next-hop-self                ! LE réflexe iBGP
 neighbor 10.0.0.2 route-reflector-client
 neighbor 10.0.0.2 send-community both          ! sinon RIEN n'est envoyé
 neighbor 198.51.100.2 route-map IN  in
 neighbor 198.51.100.2 route-map OUT out
 maximum-paths 4
 bgp bestpath as-path multipath-relax
```

```
! ---- diagnostic
show ip bgp summary                       ! État + PfxRcd — un NOMBRE = OK
show ip bgp neighbors 198.51.100.2        ! détail, capacités, compteurs
show ip bgp                               ! table complète (codes * > i)
show ip bgp 203.0.113.0/24                ! tous les chemins + pourquoi le best
show ip bgp regexp ^64500_                ! routes originées par le voisin direct
show ip bgp regexp _15169$                ! routes originées par AS15169
show ip bgp community 65001:100
show ip bgp neighbors X routes             ! reçues APRÈS filtres
show ip bgp neighbors X received-routes    ! AVANT filtres (soft-reconfig requis)
show ip bgp neighbors X advertised-routes  ! ce que J'ENVOIE
show ip route bgp
show ip bgp rpki table / show ip bgp rpki servers
clear ip bgp * soft                        ! sans casser la session
clear ip bgp 198.51.100.2 soft in|out
```

**Regex AS_PATH** : `^$` routes locales · `^64500$` voisin direct uniquement · `_64500_` traverse 64500 ·
`^64500_` apprises via 64500 · `.*` tout.

---

## 11. Commandes — FRR / vtysh (Linux, ce que tu verras vraiment)

```
vtysh -c "show bgp summary"
vtysh -c "show bgp ipv4 unicast 203.0.113.0/24"
vtysh -c "show bgp neighbors 10.0.0.2 advertised-routes"
vtysh -c "show bgp ipv4 unicast statistics"
vtysh -c "show ip route bgp"
```

```
! configuration FRR (/etc/frr/frr.conf)
router bgp 65001
 neighbor 10.0.0.2 remote-as internal
 address-family ipv4 unicast
  neighbor 10.0.0.2 next-hop-self
  neighbor 10.0.0.2 soft-reconfiguration inbound
  network 203.0.113.0/24
 exit-address-family
```

**BIRD** : `birdc show protocols all bgp1` · `birdc show route protocol bgp1` ·
`birdc show route for 203.0.113.5 all`.

---

## 12. Diagnostic depuis un hôte Linux

```bash
ss -tnp state established '( dport = :179 or sport = :179 )'   # sessions BGP vivantes
tcpdump -ni eth0 tcp port 179 -vv                              # capture BGP
tcpdump -ni eth0 mpls                                          # trafic MPLS

traceroute -A 8.8.8.8          # affiche les ASN traversés
mtr --aslookup --report 8.8.8.8
tracepath 8.8.8.8              # découvre le PMTU sans root

# Qui possède cette IP / ce préfixe ?
whois -h whois.cymru.com " -v 8.8.8.8"
whois -h whois.radb.net 203.0.113.0/24
whois AS15169

# Test de MTU (voir R03)
ping -M do -s 1472 10.0.0.1    # 1472 + 28 = 1500
```

| Outil web / API | Usage |
|---|---|
| **bgp.tools** | vue d'un préfixe/AS, upstreams, IX |
| **RIPEstat** | historique d'annonces, RPKI, whois |
| **RouteViews / RIPE RIS** | dumps **MRT** (RFC 6396) pour analyse hors ligne |
| **PeeringDB** | où un AS est présent, ports IXP, politique de peering |
| Looking Glass opérateur | `show ip bgp` depuis le réseau d'un tiers |

---

## 13. Table de décision rapide — symptôme → cause

| Symptôme | Cause la plus probable | Vérification |
|---|---|---|
| Voisin en `Idle` | route absente vers le voisin, session admin down | `show ip route <voisin>` |
| Voisin en **`Active`** | **TCP 179 bloqué**, mauvaise IP, `update-source` absent | ACL, `ss -tn dport 179` |
| Bloqué en `OpenSent` | ASN attendu ≠ ASN reçu, router-ID dupliqué, MD5 | `debug ip bgp` |
| Session qui flappe | Hold Timer Expired : lien, CPU, MTU | compteurs d'erreurs, BFD |
| Session coupée d'un coup | Cease/1 **maximum-prefix** | log `%BGP-3-NOTIFICATION` |
| Route dans `show ip bgp`, pas de `*` | **NEXT_HOP injoignable** → `next-hop-self` | `show ip route <next-hop>` |
| Route avec `*` sans `>` | une autre gagne | dérouler `N W L O A O M E I R` |
| Route non annoncée au voisin | filtre out, NO_EXPORT, split horizon iBGP | `... advertised-routes` |
| Route BGP masquée par OSPF | AD iBGP 200 > OSPF 110 | `show ip route <préfixe>` |
| Gros transferts qui gèlent | MTU / pile de labels ou VXLAN | `ping -M do -s ...` |
| Latence x3 sans alerte | bascule DX → VPN, ou peering → transit | `traceroute -A`, PfxRcd |
