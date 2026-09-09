# R04 — FICHE : Routage (table, statique, OSPF)

> Lire **avant** le cours (pretesting), puis réciter de mémoire aux rappels. Cible : **3 minutes**.
> **Un routeur ne connaît pas le chemin, seulement le prochain saut.** La décision = 3 filtres en cascade :
> **préfixe le plus long → distance administrative → métrique**. Et il faut une route dans **les deux sens**.

## Les 3 règles, dans l'ordre
```
① LONGEST PREFIX MATCH  le /n le plus long gagne. Écrase tout : un /26 RIP bat un /24 statique.
② DISTANCE ADMIN        à préfixe IDENTIQUE, source la plus crédible (valeur la plus BASSE).
③ MÉTRIQUE              à préfixe ET protocole identiques, coût le plus bas.
④ ÉGALITÉ → ECMP        plusieurs chemins, répartition par FLUX (hash), pas par paquet.
```
`0.0.0.0/0` = masque de longueur **0** → correspond à tout, **perd contre tout**. RIB = ce qu'il *sait*,
FIB/CEF = ce qu'il *fait*.

## Distances administratives
| AD | Source | | AD | Source |
|---:|---|---|---:|---|
| **0** | Connecté | | **110** | **OSPF** |
| **1** | Statique | | 115 | IS-IS |
| 5 | Résumé EIGRP | | **120** | **RIP** |
| **20** | **eBGP** | | 170 | EIGRP externe |
| **90** | EIGRP interne | | **200** | **iBGP** |

**« Ce Sacré Bébé Écoute Ou Râle »** = 0·1·20·90·110·120. **255 = jamais installée.** **eBGP 20 < iBGP 200.**
**Linux n'a pas d'AD** : seulement `metric` (la plus basse gagne).

## Table Linux
`default via 192.168.1.1 dev eth0 proto dhcp src 192.168.1.42 metric 100`
**pas de `via`** = connecté · `proto kernel` = créée en posant l'IP · `scope link` = joignable en 1 saut ·
`src` = IP source quand la machine émet · `metric` défaut **0**.
Tables : `local` **255** · `main` **254** · `default` **253**. Règles : 0 / 32766 / 32767.
**`ip route get <IP>` = la décision** (`show` = la carte). Routage : `net.ipv4.ip_forward=1`.
Spéciales : `blackhole` (silence) · `unreachable` (ICMP 3/1) · `prohibit` (ICMP 3/13) · `throw`. Cisco = `Null0`.

## Table Cisco
`O IA  10.3.0.0/16 [110/138] via 10.1.1.2, 00:09:02, Gi0/0` → **[AD / métrique]**, toujours cet ordre.
Codes : `C` connecté · `L` locale /32 · `S` statique · `O` intra · `O IA` inter-aire · `O E1/E2` externe ·
`D` EIGRP · `R` RIP · `B` BGP · `S*` candidate default.
**Route flottante** = statique à AD forcée (130 > 110) : secours silencieux. `ip route <net> <mask> <nh> 130`.
**Piège** : statique par interface sur Ethernet → ARP pour chaque destination. Toujours donner le next-hop.
**Piège** : tunnel + `0/0 via tun0` → boucle récursive. Parade : statique /32 vers l'endpoint.

## Vecteur de distance vs état de liens
| | Vecteur (RIP, EIGRP) | État de liens (OSPF, IS-IS) |
|---|---|---|
| Échange | **ses routes** aux voisins | **ses liens** (LSA) inondés à l'aire |
| Connaît | une liste, pas la topologie | la **carte complète** |
| Calcul | Bellman-Ford | **Dijkstra** local |
| Boucles | possibles (comptage à l'infini) | impossibles en régime stable |

**RIP** : sauts, max **15**, **16 = infini** · update **30 s**, invalid 180, holddown 180, flush 240 ·
UDP **520** (RIPng 521) · `224.0.0.9` · AD 120. Parades : split horizon, poison reverse, triggered, holddown.
**EIGRP** : proto **88**, `224.0.0.10`, hello **5**/hold **15**, AD **90/170/5**, DUAL, K1=K3=1.
Faisabilité : **RD_voisin < FD** → feasible successor (secours sans boucle, bascule en ms).

## OSPF — chiffres
| | | | | |
|---|---|---|---|---|
| Protocole IP | **89** | | Hello/Dead broadcast, P2P | **10 / 40 s** |
| AllSPFRouters | **224.0.0.5** | | Hello/Dead NBMA, P2MP | **30 / 120 s** |
| AllDRouters | **224.0.0.6** | | MaxAge LSA | **3600 s** |
| AD | **110** | | Refresh LSA | **1800 s** |
| En-tête | **24 o** (v3 : 16) | | Bande passante de référence | **10⁸ = 100 Mbit/s** |
| TTL | **1** | | ECMP défaut IOS | **4** |

**Paquets 1→5** : Hello · DBD · LSR · LSU · LSAck → *« Hello, Décris, Demande, Donne, Dis merci »*.
**Doivent correspondre** : Area ID, Hello, Dead, masque, auth, flag stub. **Pas** : Router ID, priorité, coût, **process-id**.
Router ID : configuré > plus haute IP de loopback > plus haute IP physique.

## OSPF — 8 états
`DOWN → ATTEMPT → INIT → 2-WAY → EXSTART → EXCHANGE → LOADING → FULL`
**2-Way** = élection DR/BDR · **ExStart** = maître/esclave + **contrôle du MTU**.
Bloqué **INIT** = trafic unidirectionnel · bloqué **EXSTART/EXCHANGE** = **MTU différent** (cause n°1) ·
**2-Way** entre DROTHER = **normal**.

**DR/BDR** : réduit `n(n-1)/2` → **2n-3** adjacences. Priorité la plus haute (défaut **1**, **0 = jamais DR**),
puis Router ID. **Non préemptive.** Le DR ne route pas les données. Entre 2 routeurs : `ip ospf network point-to-point`.

## OSPF — LSA et coût
| Type | Nom | Généré par | Portée |
|---:|---|---|---|
| **1** | Router | tous | l'aire |
| **2** | Network | **DR** | l'aire |
| **3** | Summary | **ABR** | autres aires |
| **4** | ASBR Summary | ABR | autres aires |
| **5** | AS External | **ASBR** | tout l'AS sauf stub |
| **7** | NSSA External | ASBR en NSSA | la NSSA → converti en 5 par l'ABR |

**1 = moi, 2 = nous, 3 = ailleurs, 4 = la porte, 5 = le dehors.** LSDB **identique** dans l'aire, table **différente**.

**Coût = référence / bande passante**, division entière, **min 1**, somme des interfaces de **sortie**.
Défaut : 10 Mbit/s = **10** · 100 Mbit/s = **1** · 1 G / 10 G / 100 G = **1** ⚠️ · T1 = **64**.
Correction : `auto-cost reference-bandwidth 100000` (en Mbit/s), **sur tous les routeurs**.
Préférence : **O > O IA > E1 > E2**. Seed metric par défaut **20** (BGP : 1), type **E2**.
**E2** = coût externe seul · **E1** = externe + interne (choisit l'ASBR le plus proche).

**Aires** : type 1/2 ne sortent jamais de l'aire. Toute aire **doit toucher l'aire 0**.
Stub : pas de type 5 · Totally stubby : ni 3 ni 5 · NSSA : type 7 autorisé. Flag stub dans le **Hello**.
**Piège résumé** : annoncer un /21 dont un /24 n'existe plus → boucle. Parade : **Null0 / blackhole**.
`passive-interface` : plus de Hello, **mais le réseau reste annoncé**.

## Convergence · VRF
Détection domine : lien down = **ms** · voisin mort, lien up = **40 s** (dead). Puis SPF delay **5 s** (IOS).
**BFD** : intervalle **50-300 ms** × multiplicateur **3** → détection **150-900 ms**.
**VRF** = plusieurs tables étanches dans un routeur (le VLAN de la couche 3). **RD = unicité** (MP-BGP),
**RT = politique** (qui importe quoi). Linux : `ip link add vrf-x type vrf table 100` · `ip vrf exec`.

## Ce qui casse en vrai
**Il manque la route de RETOUR** — dans l'ordre : route d'un seul sens · SG/NACL · CIDR qui se chevauchent ·
**peering non transitif** (A↔B, B↔C ⇒ **pas** A↔C, il faut un Transit Gateway) · pas de route par défaut.
**Asymétrique + pare-feu à états** : SYN-ACK sans SYN → drop. Ping OK, TCP en **SYN_SENT**.
Linux : `rp_filter` strict (1) fait pareil — valeur retenue = **max(all, interface)**.
**Traceroute** : `* * *` = pas d'ICMP généré, **pas** une perte · RTT non monotone = normal · **aller seulement** ·
**~1 ms de RTT / 100 km**. Latences : même AZ 0,1-0,5 ms · inter-AZ 0,5-2 ms · Europe↔US-est **75-90 ms**.
**10⁶ requêtes séquentielles à 80 ms = 22 h** — la bande passante ne guérit pas la latence.
**K8s** : IP de pods **routées** (/24 par nœud, 110 pods max) · **ClusterIP non routée** (DNAT kube-proxy).

**Diagnostic express** — `ip route get <IP>` · `ip rule show` · `traceroute -T -p 443` · `mtr -T -P 443` ·
`ss -tanp` · `tcpdump -ni any host <IP>` **des deux côtés** · `show ip route <IP>` · `show ip ospf neighbor` ·
`show ip ospf database` · `sysctl net.ipv4.ip_forward net.ipv4.conf.all.rp_filter`.

---

## Test express — 8 questions, réponses dans le cours
1. Donne les 3 critères de sélection d'une route, dans l'ordre. Lequel écrase les autres ?
2. Une statique /16 et une route OSPF /24 couvrent la destination. Laquelle gagne, et pourquoi ?
3. AD de : connecté, statique, eBGP, OSPF, RIP, iBGP ? Que fait une AD de 255 ?
4. Cite les 8 états d'adjacence OSPF dans l'ordre. Où se fait l'élection DR/BDR ? Où le MTU est-il vérifié ?
5. Formule du coût OSPF, référence par défaut, et coût d'un lien 10 Gbit/s. Quel est le problème ?
6. Qui génère les LSA de type 1, 2, 3, 5 et 7 ? Laquelle ne sort jamais de son aire ?
7. Combien de temps OSPF met-il à voir un voisin mort dont le lien reste up ? Comment fait-on mieux ?
8. Le ping passe mais TCP reste en SYN_SENT. Diagnostic, et deux façons de corriger ?
