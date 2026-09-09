# R05 — Fiche : BGP, AS, peering, MPLS

> Lis-la **avant** le cours (pretesting) puis **récite-la** aux rappels. Objectif : 3 minutes.

## Systèmes autonomes

| Plage ASN | Usage |
|---|---|
| 0 · 65535 | réservés |
| 1 – 64 495 | **publics 16 bits** |
| 64 512 – 65 534 | **privés 16 bits** (Calico, AWS DX, K8s) |
| **23 456** | **AS_TRANS** — substitut d'un ASN 32 bits pour un pair 16 bits |
| 65 552 – 4 199 999 999 | publics 32 bits |
| 4 200 000 000 – 4 294 967 294 | privés 32 bits |

**Chaîne** : IANA → 5 RIR (RIPE NCC · ARIN · APNIC · LACNIC · AFRINIC) → LIR → toi.
**Ordres** : ~75 000 AS visibles · ~1 M routes IPv4 · ~200 k IPv6 · Tier 1 ≈ 10 acteurs (n'achètent aucun transit).

## BGP — le protocole

**TCP port 179** · path vector · anti-boucle = **son propre ASN dans l'AS_PATH → rejet**.
En-tête **19 o** = Marker 16 (tout à 1) + Length 2 + Type 1. Message max **4096 o** (65535 si RFC 8654).

| Type | Message | Taille |
|---|---|---|
| 1 | OPEN (version 4, ASN, hold, router-ID, capacités) | ≥ 29 o |
| 2 | UPDATE (withdrawn + attributs + NLRI) | ≥ 23 o |
| 3 | NOTIFICATION → **ferme la session** | ≥ 21 o |
| 4 | KEEPALIVE (en-tête seul) | 19 o |
| 5 | ROUTE-REFRESH | 23 o |

**Timers** : hold **90 s** (négocié = min des deux) · keepalive **30 s** = hold/3 · ConnectRetry ≈ 120 s.
**États (6)** : `Idle → Connect → Active → OpenSent → OpenConfirm → Established`.
⚠ **`Active` = ÉCHEC TCP**, pas « ça marche ». UPDATE seulement en `Established`.
**Erreurs** : 2/2 Bad Peer AS · **4 Hold Timer Expired** · **6/1 Cease Maximum Prefixes**.
**Capacités** : 1 MP-BGP · 2 route refresh · 64 graceful restart · 65 ASN 32 bits · 69 ADD-PATH.

## eBGP vs iBGP

| | eBGP | iBGP |
|---|---|---|
| ASN | différents | identiques |
| TTL | **1** (sinon `ebgp-multihop`) | quelconque, via **loopback** |
| AS_PATH | prepend son ASN | inchangé |
| NEXT_HOP | réécrit | **inchangé** → `next-hop-self` |
| LOCAL_PREF | non transmis | transmis |
| Distance adm. | **20** | **200** |
| Ré-annonce iBGP→iBGP | — | **JAMAIS** → full mesh **n(n−1)/2** |

## Attributs

| # | Attribut | Catégorie | Portée | Sens |
|---|---|---|---|---|
| 1 | ORIGIN | WK mandatory | globale | `i`(0) < `e`(1) < `?`(2), **petit gagne** |
| 2 | AS_PATH | WK mandatory | globale | AS_SET compte pour **1** |
| 3 | NEXT_HOP | WK mandatory | 1 saut d'AS | — |
| 4 | MED | opt. non-trans. | **1 AS voisin** | **petit gagne**, défaut 0 |
| 5 | LOCAL_PREF | WK discretionary | AS local | **grand gagne**, défaut **100** |
| 8 / 16 / 32 | COMMUNITY / Extended / Large | opt. trans. | globale | 4 / **8** / 12 octets |
| 9 / 10 | ORIGINATOR_ID / CLUSTER_LIST | opt. non-trans. | AS local | anti-boucle **RR** |

**WEIGHT** : pas un attribut, Cisco, **local au routeur**, défaut **0** (appris) / **32768** (local), max 65535.
**Flags** 0x80 Optional · 0x40 Transitive · 0x20 Partial · 0x10 Extended Length.

## Sélection du meilleur chemin — `N W L O A O M E I R`

```
0 NEXT_HOP joignable   1 WEIGHT ↑   2 LOCAL_PREF ↑   3 Originée localement
4 AS_PATH ↓            5 ORIGIN ↓   6 MED ↓ (même AS voisin !)
7 eBGP > iBGP          8 métrique IGP ↓   9 + ancien, router-ID ↓, cluster-list ↓, IP ↓
```
« **N**os **W**agons **L**ivrent **O**nze **A**nanas **O**range, **M**ais **E**lle **I**gnore **R**obert. » —
**les 2 premières préférences MONTENT, tout le reste DESCEND.**

## Communities

| Nom | Valeur | Effet |
|---|---|---|
| NO_EXPORT | `0xFFFFFF01` | ne sort pas de l'**AS** |
| NO_ADVERTISE | `0xFFFFFF02` | ne sort pas du **routeur** |
| GRACEFUL_SHUTDOWN | `65535:0` | RFC 8326 |
| **BLACKHOLE** | **`65535:666`** | RFC 7999, anti-DDoS |

⚠ Cisco : `send-community` obligatoire, sinon rien n'est envoyé.

## Route reflectors

| Route reçue de | Réfléchie vers |
|---|---|
| **client** | clients **+** non-clients |
| **non-client** | **clients seulement** |
| **eBGP** | tout le monde |

Anti-boucle : **ORIGINATOR_ID** (9) + **CLUSTER_LIST** (10). Le RR ne modifie aucun attribut.

## Peering / transit

**Transit = accès à tout Internet, payant. Peering = pair + ses clients, gratuit, NON TRANSITIF.**
Local pref type : **client 200 > peer 100 > transit 50**.
**Valley-free** : route de client → à tous · route de peer/transit → **aux clients seulement**.
IXP : L2 partagé, peering bilatéral ou via **route server** (transparent, absent de l'AS_PATH, ne route rien).

## Incidents & sécurité

**Fuite** = préfixes légitimes, **mauvaise direction**. **Hijack** = **mauvaise origine**.
AS7007 1997 · Pakistan/YouTube 2008 (/24 plus spécifique, ~2 h) · Google→Verizon 2017 (Japon, ~40 min) ·
MyEtherWallet 2018 (DNS AWS, ~150 k$) · Facebook 2021 (retrait BGP, ~6 h) · 512k day 2014 (TCAM).
**Hijack par plus spécifique bat tout** : c'est le longest prefix match, pas l'algo BGP.
**ROA = (préfixe, maxLength, ASN)** → validateur → **RTR TCP 323** → VALID / INVALID / NOT FOUND.
⚠ RPKI valide **l'origine seule** : ni le chemin (→ BGPsec), ni les fuites. Filtre max **/24** v4, **/48** v6.

## MPLS

```
| LABEL 20 b | TC 3 b | S 1 b | TTL 8 b |   = 32 bits = 4 octets   → « 20 h 31, 8 s »
```
EtherType **0x8847** · labels 0-15 réservés : **0** IPv4 null · **2** IPv6 null · **3 Implicit NULL → PHP**.
**PUSH** (ingress PE) → **SWAP** (P) → **POP** (egress). LDP **UDP 646** hello / **TCP 646** session · RSVP-TE IP proto 46 · SR : pas de protocole de labels, SRGB Cisco 16000-23999.

**VPN L3 (RFC 4364)** : VRF + **RD 8 o** (unicité seule) + **RT** extended community (import/export).
VPNv4 = RD 8 o + IPv4 4 o = **12 o**. MP-BGP **AFI 1 / SAFI 128**. EVPN = AFI 25 / SAFI 70.
**2 labels** : externe = transport (LDP/SR, atteindre le PE) · interne = VPN (quelle VRF). Le cœur ne voit que l'externe.
**MTU** : +4 o par label. VXLAN +50 · WireGuard +60/80 · IPsec +50/73 · GRE +24.

## Cloud

DX/ExpressRoute/Interconnect = **BGP sur VLAN 802.1Q** · AWS public AS **16509** · Azure **12076** · DX communities `7224:7100/7200/7300` (local pref demandé à AWS), `7224:9100/9200/9300` (portée de TES annonces) ; `7224:8100/8200` = étiquettes posées PAR AWS sur ses propres annonces (région / continent).
Calico : node-to-node mesh (= full mesh iBGP, AS 64512) → **RR au-delà de ~100 nœuds**. MetalLB BGP : annonce le VIP depuis n nœuds → **ECMP** ; ⚠ rehash à la panne casse les sessions.
Données : **MRT** (fichiers RouteViews/RIS, différé) vs **BMP** (streaming routeur, pré-policy).

## Test express

1. Quel est le 3ᵉ critère de sélection du meilleur chemin ?
2. Pourquoi une route iBGP apparaît-elle sans `*` dans `show ip bgp` ?
3. Quelle est la restriction par défaut sur la comparaison du MED ?
4. Que réfléchit un RR quand il reçoit une route d'un **non-client** ?
5. Combien d'octets fait une route VPNv4, et de quoi est-elle composée ?
6. Que déclenche le label 3 ?
7. Un ROA `(10.0.0.0/16, 16, AS100)` : quel verdict pour `10.0.0.0/24` annoncé par AS100 ?
8. Pourquoi le VPC peering AWS n'est-il pas transitif ?
