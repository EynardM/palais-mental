# R04 — Routage : table de routage, statique, OSPF

> **Ce que tu sauras faire à la fin**
> - Prendre une table de routage Linux ou Cisco, et dire **sans hésiter** par où sortira un paquet donné — en appliquant dans l'ordre *longest prefix match*, distance administrative, métrique.
> - Écrire, lire et déboguer une route statique, une route par défaut, une route flottante, une blackhole, un ECMP — dans les deux syntaxes.
> - Expliquer la différence de **nature** entre un protocole à vecteur de distance et un protocole à état de liens, et pourquoi l'un boucle et l'autre pas.
> - Dérouler OSPF de bout en bout : les 8 états d'adjacence, les 5 types de paquets, les 6 types de LSA, l'élection DR/BDR, le calcul du coût, et **exécuter Dijkstra à la main** sur une topologie de 7 routeurs.
> - Découper un réseau en aires, choisir entre stub / totally stubby / NSSA, redistribuer du statique sans créer de boucle, et isoler des clients dans des VRF.
> - Diagnostiquer les trois pannes de routage que tu verras vraiment : la route manquante d'un seul côté, le routage asymétrique qui tue un pare-feu à états, et le chemin qui part dans la mauvaise région.
>
> **Pourquoi ça compte dans ton poste**
> Un pipeline de données est une suite de connexions entre des machines qui ne sont **jamais** sur le même
> réseau : un job qui lit un bucket, écrit dans un entrepôt situé dans un autre VPC, appelle un service
> d'inférence dans une autre région, et le tout traverse un peering, un Transit Gateway et un cluster
> Kubernetes qui a son propre plan de routage. Quand ça ne marche pas, la question n'est presque jamais
> « le code est-il bon », c'est **« y a-t-il une route dans les deux sens »**. Le routage détermine aussi
> ta latence : entre deux régions, la route choisie fait la différence entre 20 ms et 150 ms de RTT — et
> à 150 ms de RTT, un million de petites requêtes séquentielles prennent 41 heures. Enfin, si tu fais de
> l'IA sur des données réseau, les tables de routage et les LSA **sont** tes sources : un modèle de
> détection d'anomalie de routage se nourrit d'annonces, de coûts et de temps de convergence.
>
> **Prérequis** : `R01` (modèle en couches, encapsulation), `R02` (Ethernet, MAC, ARP, MTU), `R03` (IPv4, CIDR, masques, ICMP, TTL).
> **Durée de lecture** : 80-95 min. Papier et crayon obligatoires — la section Dijkstra ne se lit pas, elle se fait.

---

## 1. Le problème : un paquet arrive, et maintenant ?

Un paquet IP atterrit sur une interface d'un routeur. Sa destination est `10.20.30.70`. Le routeur a huit
interfaces. **Par laquelle sort-il ?**

Il ne peut pas le savoir en regardant le paquet : l'adresse de destination ne contient aucune information
sur la topologie. Il ne peut pas non plus tester les huit sorties. Il lui faut donc une **connaissance
préalable** : une liste de « pour aller là, passe par ici ». C'est la table de routage.

Le point crucial, celui que 90 % des gens n'ont pas intégré :

```
   Un routeur ne connaît PAS le chemin.
   Il connaît UNIQUEMENT le prochain saut.

   A ──────► B ──────► C ──────► D
   « pour D,   « pour D,   « pour D,
    va vers B »  va vers C »  c'est moi »

   Personne n'a la carte complète du trajet dans sa table.
   Chaque routeur prend UNE décision locale, et la somme des décisions
   locales forme le chemin.
```

C'est le **routage saut par saut** (*hop-by-hop*). Analogie : tu demandes ta route dans une ville
inconnue. Le passant ne te décrit pas l'itinéraire complet — il te dit « deuxième à droite ». Puis tu
redemandes. Chaque passant ne connaît que la direction générale, et pourtant tu arrives.

La conséquence est brutale et il faut la sentir tout de suite : **si un seul routeur du chemin se trompe,
tout le trajet est cassé** — et si les routeurs A→D sont d'accord mais que ceux de D→A ne le sont pas, la
connexion ne s'établit pas non plus. Le routage est un accord collectif qui doit tenir dans les **deux
sens**.

> ❓ **RETIENS ÇA** — Que contient exactement une entrée de table de routage ?
> <details><summary>→ réponse</summary><br>Un <b>préfixe de destination</b> (réseau + masque) et un <b>prochain saut</b> (adresse du routeur suivant, ou interface de sortie). <b>Pas</b> le chemin complet. Plus, selon la plateforme : distance administrative, métrique, source de l'information, âge.</details>

Deux plans, à ne jamais confondre :

| Plan | Rôle | Où ça vit | Nom Cisco | Nom Linux |
|---|---|---|---|---|
| **Plan de contrôle** | *Apprendre* les routes (OSPF, BGP, config statique) | CPU, logiciel, lent (ms à s) | **RIB** (`show ip route`) | démon FRR/BIRD + `ip route` |
| **Plan de données** | *Commuter* les paquets à la vitesse du fil | ASIC, matériel, rapide (ns) | **FIB / CEF** (`show ip cef`) | FIB noyau (`ip route get`) |

Le plan de contrôle prend toutes les routes apprises, choisit la meilleure pour chaque préfixe, et **programme**
le résultat dans le plan de données. Un routeur qui a la bonne route dans sa RIB mais pas dans sa FIB
(bug, table matérielle pleine) jette les paquets tout en affichant une table parfaite. C'est rare, mais
c'est le genre de panne qui rend fou.

> 🧠 **MÉMO** — **RIB = ce que le routeur *sait*. FIB = ce que le routeur *fait*.** La RIB est le carnet
> d'adresses complet, la FIB est le post-it collé sur l'écran.

---

## 2. Les trois règles de décision, dans l'ordre

Trois critères, appliqués **strictement dans cet ordre**. C'est la question d'entretien la plus fréquente
du sujet, et l'erreur la plus fréquente est d'inverser 1 et 2.

```
┌──────────────────────────────────────────────────────────────────┐
│ Paquet pour 10.20.30.70                                          │
└───────────────────────────┬──────────────────────────────────────┘
                            ▼
   ① LONGEST PREFIX MATCH — le préfixe le PLUS SPÉCIFIQUE gagne
      (le plus grand /n qui contient la destination)
      → tranche AVANT tout le reste. Un /26 statique bat un /24 OSPF,
        et un /26 OSPF bat un /24 statique. Le protocole n'entre pas en jeu.
                            ▼
   ② DISTANCE ADMINISTRATIVE — à préfixe IDENTIQUE, la source la plus
      CRÉDIBLE gagne. Plus la valeur est basse, plus on lui fait confiance.
      Connecté 0 < Statique 1 < eBGP 20 < EIGRP 90 < OSPF 110 < RIP 120
                            ▼
   ③ MÉTRIQUE — à préfixe identique ET même protocole, le coût le plus
      BAS gagne. (coût OSPF, nb de sauts RIP, métrique composite EIGRP)
                            ▼
   ④ ÉGALITÉ PARFAITE → ECMP : on installe plusieurs chemins et on
      répartit les FLUX (pas les paquets) entre eux.
```

### 2.1 Longest prefix match — le plus spécifique gagne

Le routeur ne prend pas la première ligne qui correspond, ni la dernière : il prend **celle dont le masque
est le plus long** parmi toutes celles qui correspondent.

Analogie : sur ton bureau tu as trois consignes. « Tout le courrier → boîte A ». « Le courrier des impôts
→ boîte B ». « Le courrier des impôts de Paris 12e → boîte C ». Une lettre des impôts du 12e correspond
aux **trois**. Tu appliques la **plus précise**. La consigne générale ne disparaît pas, elle est simplement
recouverte.

```
Table :                                        Destination 10.20.30.70
 0.0.0.0/0        via 10.0.0.1   ← correspond   (0 bit vérifié)
 10.0.0.0/8       via 10.0.0.2   ← correspond   (8 bits)
 10.20.0.0/16     via 10.0.0.3   ← correspond   (16 bits)
 10.20.30.0/24    via 10.0.0.4   ← correspond   (24 bits)
 10.20.30.64/26   via 10.0.0.5   ← correspond   (26 bits)  ★ GAGNE
 10.20.30.128/25  via 10.0.0.6   ← NE correspond pas (.128-.255)

 Décision : sortir vers 10.0.0.5.
```

La route par défaut `0.0.0.0/0` est le cas limite : masque de longueur **zéro**, elle correspond à tout et
perd donc contre absolument tout le reste. C'est pour ça qu'on l'appelle *gateway of last resort* — le
recours quand rien d'autre ne matche.

> ⚠️ **PIÈGE** — « La route statique est prioritaire sur OSPF. » **Faux tel quel.** Une route statique
> `10.0.0.0/8` **perd** contre une route OSPF `10.20.30.0/24` pour la destination `10.20.30.70`, parce que
> le LPM tranche avant la distance administrative. La distance administrative ne départage **que des
> préfixes strictement identiques**. Redis-toi la phrase : *« la spécificité d'abord, la crédibilité
> ensuite »*.

> ❓ **RETIENS ÇA** — Une route statique `/16` et une route OSPF `/24` couvrent toutes deux la destination. Laquelle gagne ?
> <details><summary>→ réponse</summary><br>La route <b>OSPF /24</b>. Le longest prefix match s'applique en premier et il ne regarde ni le protocole ni la distance administrative. Le /24 est plus spécifique, il gagne.</details>

### 2.2 Distance administrative — à qui je fais confiance ?

Le routeur peut apprendre **le même préfixe exact** par plusieurs canaux : OSPF le lui annonce, et quelqu'un
a configuré une statique. Il ne peut en installer qu'une seule dans la FIB. Il tranche par la **distance
administrative** (AD) : une note de crédibilité de la *source*, pas de la route.

| AD (Cisco) | Source | Logique |
|---:|---|---|
| **0** | Interface connectée | Je le vois de mes yeux, c'est incontestable |
| **1** | Route statique | Un humain l'a écrit — présomption d'intention |
| 5 | Route résumée EIGRP | |
| **20** | eBGP | Info externe, mais explicite et policy-driven |
| **90** | EIGRP interne | |
| 100 | IGRP (mort) | |
| **110** | **OSPF** | |
| 115 | IS-IS | |
| **120** | **RIP** | Vecteur de distance : peu d'information, peu de confiance |
| 170 | EIGRP externe (redistribué) | |
| **200** | iBGP | |
| **255** | Inconnu / **jamais installé** | Sert à désactiver une route sans l'effacer |

Les valeurs à savoir absolument par cœur : **0, 1, 20, 90, 110, 120, 200, 255**.

> 🧠 **MÉMO** — Pour l'ordre `0 / 1 / 20 / 90 / 110 / 120`, une phrase : **« Ce Sacré Bébé Écoute Ou Râle »**
> → **C**onnecté 0, **S**tatique 1, e**B**GP 20, **E**IGRP 90, **O**SPF 110, **R**IP 120.
> Et retiens l'inversion contre-intuitive : **eBGP 20 < iBGP 200**. L'externe est plus crédible que
> l'interne, exactement l'inverse de l'intuition — parce qu'une route eBGP vient d'un voisin qui la possède
> vraiment, alors qu'une route iBGP a déjà été relayée à l'intérieur.

**Linux n'a pas de distance administrative.** Le noyau ne connaît qu'une **métrique** (`metric`, en interne
`priority`) et, à préfixe égal, prend la plus basse. C'est le démon de routage (FRR, BIRD) qui, lui,
implémente l'AD dans sa propre RIB et n'installe dans le noyau que le gagnant. Confondre les deux est
l'erreur classique quand on passe de Cisco à Linux.

> ❓ **RETIENS ÇA** — AD d'une route connectée, d'une statique, d'OSPF, de RIP ?
> <details><summary>→ réponse</summary><br><b>0 / 1 / 110 / 120</b>.</details>

> ❓ **RETIENS ÇA** — À quoi sert une AD de 255 ?
> <details><summary>→ réponse</summary><br>Une route d'AD 255 n'est <b>jamais installée</b> dans la table. On l'utilise pour neutraliser une route (souvent via une <i>distance</i> appliquée par route-map) sans supprimer sa configuration.</details>

### 2.3 Métrique — le coût du chemin

Même préfixe, même protocole, deux chemins : c'est la **métrique** du protocole qui départage. Elle n'a de
sens **qu'à l'intérieur d'un même protocole** — comparer un coût OSPF de 20 à une métrique EIGRP de 3072 n'a
aucun sens, ce sont des unités différentes.

| Protocole | Métrique | Portée |
|---|---|---|
| RIP | **Nombre de sauts**, max 15 (16 = infini) | grossier : une ligne à 64 kbit/s vaut un 10 Gbit/s |
| OSPF | **Coût** = somme des coûts des interfaces de sortie | proportionnel à l'inverse de la bande passante |
| EIGRP | **Composite** : bande passante minimale + délai cumulé | plus fine, mais propriétaire à l'origine |
| BGP | Pas de métrique unique : **11 critères** en cascade (AS-path, local-pref…) | politique, pas performance |

### 2.4 ECMP — l'égalité parfaite

Si deux chemins sortent à égalité sur les trois critères, on garde les deux : c'est l'**ECMP** (*Equal Cost
Multi-Path*). Cisco IOS en installe **4 par défaut** (`maximum-paths`, jusqu'à 16 ou 32 selon la plateforme).

Le point à comprendre : la répartition se fait **par flux, pas par paquet**. Le routeur calcule un hachage
sur des champs stables (IP source, IP destination, et selon la configuration les ports L4) et envoie tout le
flux sur le même chemin. Sinon les paquets d'une même connexion TCP arriveraient dans le désordre, avec des
RTT différents, et TCP interpréterait ça comme de la congestion.

```
   Flux A (hash → 0) ──────────► lien 1 ─┐
   Flux B (hash → 1) ──────────► lien 2 ─┼──► destination
   Flux C (hash → 0) ──────────► lien 1 ─┘

   4 × 10 Gbit/s en ECMP ≠ 40 Gbit/s pour UN flux.
   Un flux TCP unique reste plafonné à 10 Gbit/s.
```

Sous Linux, la politique de hachage se règle avec `net.ipv4.fib_multipath_hash_policy` : `0` = L3 (IP src/dst,
**défaut**), `1` = L4 (5-tuple, meilleure répartition), `2`/`3` = champs internes pour le trafic encapsulé.

> ⚠️ **PIÈGE** — C'est le même piège que l'agrégation LACP vue en R02, à un étage au-dessus. Un job de
> réplication qui ouvre **une seule connexion TCP** entre deux datacenters n'utilisera jamais qu'un seul
> lien ECMP, quel que soit le nombre de liens. La parade est applicative : **paralléliser en N connexions**
> (`--parallel`, `spark.sql.shuffle.partitions`, multipart upload), pas réseau.

---

## 3. Lire une table de routage Linux, ligne par ligne

```bash
$ ip route show
default via 192.168.1.1 dev eth0 proto dhcp src 192.168.1.42 metric 100
10.0.0.0/8 via 192.168.1.254 dev eth0 proto static metric 100
172.17.0.0/16 dev docker0 proto kernel scope link src 172.17.0.1 linkdown
192.168.1.0/24 dev eth0 proto kernel scope link src 192.168.1.42 metric 100
```

Décodage champ par champ :

| Champ | Valeur ici | Ce que ça veut dire |
|---|---|---|
| `default` | = `0.0.0.0/0` | Le préfixe. `default` est juste l'alias du /0 |
| `via 192.168.1.1` | prochain saut | **Absent** = destination directement connectée (pas de routeur intermédiaire) |
| `dev eth0` | interface de sortie | Où poser la trame |
| `proto` | `dhcp` / `static` / `kernel` / `boot` / `ospf` / `bgp` | **Qui** a créé cette route. `kernel` = créée automatiquement en posant une IP sur l'interface |
| `scope` | `global` (défaut) / `link` / `host` | Portée : `link` = joignable en un saut sur ce lien ; `host` = c'est moi |
| `src 192.168.1.42` | source préférée | Quelle IP mettre en source quand *ce routeur* émet lui-même par cette route |
| `metric 100` | 100 | Départage à préfixe égal — **la plus basse gagne**. Défaut 0 |
| `linkdown` | | Le lien est down, la route est conservée mais inutilisable |

Trois choses non évidentes :

1. **Une route connectée n'a pas de `via`.** `192.168.1.0/24 dev eth0 scope link` signifie : « tout ce
   /24 est atteignable directement, résous l'adresse en ARP et envoie ». C'est la brique de base : sans
   route connectée, aucune autre route ne peut se résoudre.
2. **`proto kernel` = créée par le simple fait d'avoir posé une adresse**. `ip addr add 192.168.1.42/24 dev
   eth0` crée automatiquement la route `192.168.1.0/24 dev eth0`. Tu ne l'écris jamais toi-même.
3. **`src` change la source des paquets que la machine émet**, pas la route. Utile sur une machine
   multi-homée où tu veux que le trafic sortant porte une IP précise.

### 3.1 Les tables multiples et les règles

Linux n'a pas *une* table de routage, il en a plusieurs, consultées dans l'ordre d'une liste de **règles** :

```bash
$ ip rule show
0:      from all lookup local
32766:  from all lookup main
32767:  from all lookup default
```

| Table | ID | Contenu |
|---|---:|---|
| `local` | **255** | Adresses de la machine et broadcasts. Gérée par le noyau, **on n'y touche pas** |
| `main` | **254** | La table « normale », celle que montre `ip route` sans argument |
| `default` | **253** | Quasi toujours vide |

Le noyau parcourt les règles **par priorité croissante** ; la première table qui donne un résultat gagne.
On ajoute ses propres tables (`/etc/iproute2/rt_tables`) pour faire du **routage par politique** —
router selon la **source**, pas selon la destination :

```bash
# Tout ce qui vient de 192.168.2.0/24 sort par la passerelle secondaire
ip route add default via 192.168.2.1 dev eth1 table 200
ip rule add from 192.168.2.0/24 table 200 priority 100
```

C'est exactement la parade au routage asymétrique d'une machine à deux cartes réseau (section 12).

```bash
$ ip route show table local | head -4
local 192.168.1.42 dev eth0 proto kernel scope host src 192.168.1.42
broadcast 192.168.1.255 dev eth0 proto kernel scope link src 192.168.1.42
local 127.0.0.0/8 dev lo proto kernel scope host src 127.0.0.1
```

> ❓ **RETIENS ÇA** — Quelles sont les trois tables de routage Linux par défaut et leurs numéros ?
> <details><summary>→ réponse</summary><br><code>local</code> = <b>255</b>, <code>main</code> = <b>254</b>, <code>default</code> = <b>253</b>. Consultées dans l'ordre des priorités de <code>ip rule</code> : 0 (local), 32766 (main), 32767 (default).</details>

### 3.2 La commande qui répond vraiment : `ip route get`

`ip route show` te montre la table. `ip route get` te montre **la décision** — le résultat du LPM, la source
choisie, l'interface. C'est celle qu'il faut lancer en premier dans un diagnostic.

```bash
$ ip route get 10.20.30.70
10.20.30.70 via 192.168.1.254 dev eth0 src 192.168.1.42 uid 1000
    cache

$ ip route get 8.8.8.8 from 192.168.2.10          # teste une règle de politique
$ ip route get 10.0.0.5 vrf vrf-data              # teste dans une VRF
```

> 🧠 **MÉMO** — **`show` te donne la carte, `get` te donne l'itinéraire.** Quand quelqu'un te dit « la route
> est pourtant là », réponds `ip route get`.

### 3.3 Et le routeur, il route ?

Une machine Linux avec deux interfaces ne route **rien** par défaut. Il faut l'activer :

```bash
sysctl net.ipv4.ip_forward          # 0 par défaut sur un poste, 1 sur un routeur / nœud K8s
sysctl -w net.ipv4.ip_forward=1     # volatile
# persistant : /etc/sysctl.d/99-forward.conf → net.ipv4.ip_forward = 1
```

> ⚠️ **PIÈGE** — Panne classique en lab et en cloud : les routes sont parfaites, le ping ne traverse pas.
> `ip_forward = 0`. Sur les nœuds Kubernetes, c'est le CNI qui le met à 1 ; si un durcissement CIS le
> repasse à 0, tout le cluster tombe.

---

## 4. Lire une table de routage Cisco

```
R1# show ip route
Codes: L - local, C - connected, S - static, R - RIP, B - BGP
       D - EIGRP, EX - EIGRP external, O - OSPF, IA - OSPF inter area
       E1 - OSPF external type 1, E2 - OSPF external type 2
       N1 - OSPF NSSA external type 1, N2 - OSPF NSSA external type 2
       i - IS-IS, * - candidate default

Gateway of last resort is 203.0.113.1 to network 0.0.0.0

S*    0.0.0.0/0 [1/0] via 203.0.113.1
      10.0.0.0/8 is variably subnetted, 4 subnets, 3 masks
C        10.1.1.0/24 is directly connected, GigabitEthernet0/0
L        10.1.1.1/32 is directly connected, GigabitEthernet0/0
O        10.2.2.0/24 [110/65] via 10.1.1.2, 00:14:33, GigabitEthernet0/0
O IA     10.3.0.0/16 [110/138] via 10.1.1.2, 00:09:02, GigabitEthernet0/0
D        172.16.0.0/16 [90/3072] via 10.1.1.5, 01:22:10, GigabitEthernet0/1
O E2     192.0.2.0/24 [110/20] via 10.1.1.2, 00:03:41, GigabitEthernet0/0
```

Anatomie d'une ligne :

```
 O IA     10.3.0.0/16   [110/138]   via 10.1.1.2,  00:09:02,  GigabitEthernet0/0
 │  │        │             │  │        │             │              │
 │  │        │             │  │        │             │              └─ interface de sortie
 │  │        │             │  │        │             └─ âge de la route (hh:mm:ss)
 │  │        │             │  │        └─ prochain saut
 │  │        │             │  └─ MÉTRIQUE (coût OSPF ici)
 │  │        │             └─ DISTANCE ADMINISTRATIVE
 │  │        └─ préfixe
 │  └─ sous-type : IA = inter-area
 └─ source : O = OSPF
```

**`[AD/métrique]`** — l'ordre est toujours celui-là, et c'est une question d'entretien à part entière.

Trois particularités Cisco à connaître :

- **`L` = route locale /32** : depuis IOS 15, chaque IP d'interface crée en plus de la route connectée `C` une
  route hôte `L` en /32. C'est l'équivalent de la table `local` de Linux.
- **`is variably subnetted, 4 subnets, 3 masks`** : la ligne parent classful, purement cosmétique. Elle
  indique juste que plusieurs masques coexistent dans ce bloc.
- **`S*`** : l'astérisque marque la *candidate default route*, celle qui alimente le « gateway of last resort ».

Les commandes de lecture qui comptent :

```
show ip route 10.3.0.5          # LE LPM pour cette destination + résolution récursive
show ip route ospf              # filtrer par protocole
show ip route | include 10.2    # grep
show ip protocols               # quels protocoles tournent, quels réseaux, quelles AD
show ip cef 10.3.0.5            # la FIB : ce qui sera VRAIMENT fait
```

> ❓ **RETIENS ÇA** — Dans `[110/138]`, que valent 110 et 138 ?
> <details><summary>→ réponse</summary><br><b>110 = distance administrative</b> (donc OSPF), <b>138 = métrique</b> (coût OSPF cumulé). Toujours dans cet ordre : <code>[AD/métrique]</code>.</details>

> ❓ **RETIENS ÇA** — Que signifie le code `O IA` ?
> <details><summary>→ réponse</summary><br>Route OSPF <b>inter-area</b> : le préfixe est dans une autre aire, il t'a été annoncé par un ABR via une LSA de type 3.</details>

---

## 5. Les types de routes

### 5.1 La route connectée — la fondation

Elle apparaît toute seule dès qu'une interface a une adresse **et** est `up`. Elle est la seule route dont
la véracité est garantie physiquement, d'où son AD de **0**. Toutes les autres routes en dépendent :
un prochain saut n'est utilisable que s'il tombe dans une route connectée (ou se résout récursivement
jusqu'à une route connectée).

### 5.2 La route statique

Un humain écrit « pour aller là, passe par ici ». Simple, déterministe, **et aveugle** : elle ne sait pas
que le chemin est cassé, sauf si l'interface de sortie tombe.

```bash
# Linux
ip route add 10.20.0.0/16 via 192.168.1.254 dev eth0            # via un routeur
ip route add 10.30.0.0/16 dev tun0                              # via une interface (P2P)
ip route add default via 192.168.1.1                            # route par défaut
ip route add 10.20.0.0/16 via 192.168.1.254 metric 200          # métrique explicite
ip route replace 10.20.0.0/16 via 192.168.1.253                 # remplace ou crée
ip route del 10.20.0.0/16                                       # supprime
```

```
! Cisco
ip route 10.20.0.0 255.255.0.0 192.168.1.254           ! AD 1 par défaut
ip route 10.20.0.0 255.255.0.0 GigabitEthernet0/1      ! par interface (P2P uniquement)
ip route 0.0.0.0 0.0.0.0 203.0.113.1                   ! route par défaut
ip route 10.20.0.0 255.255.0.0 192.168.1.253 130       ! FLOTTANTE : AD forcée à 130
```

> ⚠️ **PIÈGE** — Une statique **par interface** sur un lien multi-accès (Ethernet) fait croire au routeur
> que **toute** la destination est directement connectée : il envoie un ARP pour chaque destination
> distante. Ça « marche » avec du proxy ARP, ça écroule le réseau sans. Sur Ethernet, **donne toujours
> l'adresse du prochain saut**, pas seulement l'interface.

### 5.3 La route flottante — le secours

Une statique avec une AD **artificiellement élevée** (130 > 110) : elle reste dans la RIB mais n'est pas
installée tant que la route OSPF existe. Quand OSPF perd le préfixe, la statique prend le relais
automatiquement. C'est le mécanisme de secours le plus simple et le plus utilisé du métier.

```
 État normal :   OSPF  10.20.0.0/16 [110/65]  ← INSTALLÉE
                 Static 10.20.0.0/16 [130/0]  ← en attente, invisible dans show ip route

 OSPF tombe :    Static 10.20.0.0/16 [130/0]  ← INSTALLÉE en quelques ms
```

### 5.4 Les routes spéciales Linux

```bash
ip route add blackhole 10.6.6.0/24        # jette en silence, aucun ICMP
ip route add unreachable 10.7.7.0/24      # jette + ICMP type 3 code 0 (net unreachable)
ip route add prohibit 10.8.8.0/24         # jette + ICMP type 3 code 13 (admin prohibited)
ip route add throw 10.9.9.0/24 table 100  # abandonne cette table, continue avec la règle suivante
```

L'équivalent Cisco de `blackhole` est **`ip route 10.6.6.0 255.255.255.0 Null0`**. Ce n'est pas cosmétique :
c'est la technique standard pour **absorber une route résumée** et éviter une boucle (section 10.3), et
pour du *RTBH* (blackholing anti-DDoS).

### 5.5 ECMP côté Linux

```bash
ip route add 10.20.0.0/16 \
    nexthop via 192.168.1.253 dev eth0 weight 1 \
    nexthop via 192.168.1.254 dev eth0 weight 1
```

### 5.6 La résolution récursive

Quand tu écris `ip route 10.20.0.0 255.255.0.0 172.16.9.9` et que `172.16.9.9` **n'est pas** sur un réseau
connecté, le routeur doit d'abord chercher comment joindre `172.16.9.9`. C'est la **résolution récursive**.

```
   Route voulue :  10.20.0.0/16  → next-hop 172.16.9.9
                                        │  « et 172.16.9.9, il est où ? »
                                        ▼
   Table :         172.16.0.0/16 → next-hop 192.168.1.254 dev eth0
                                        │  « et 192.168.1.254 ? »
                                        ▼
                   192.168.1.0/24 dev eth0 (CONNECTÉ)  ✅ résolution terminée
```

> ⚠️ **PIÈGE** — **La boucle de routage récursive du tunnel.** Tu montes un tunnel GRE/IPsec vers
> `203.0.113.9`, puis tu pousses `0.0.0.0/0 via tun0`. Le routeur veut joindre `203.0.113.9`… et consulte
> sa table : le meilleur match est maintenant la route par défaut, qui pointe *dans le tunnel*. Le tunnel
> s'effondre, remonte, s'effondre (*flapping*). La parade : une **statique hôte** `203.0.113.9/32` vers la
> vraie passerelle physique, plus spécifique que le /0.

---

## 6. Routage dynamique : pourquoi, et les deux familles

Avec 5 routeurs, le statique tient. Avec 50 routeurs et 200 préfixes, il faudrait écrire et maintenir des
milliers de lignes, et **rien** ne se reconfigure quand un lien tombe. Le routage dynamique règle deux
problèmes : la **découverte** (je n'écris plus les routes) et la **convergence** (le réseau se répare seul).

Deux familles, deux philosophies radicalement différentes.

| | **Vecteur de distance** (RIP, EIGRP) | **État de liens** (OSPF, IS-IS) |
|---|---|---|
| Ce qu'on échange | « Voilà **mes routes** et leur distance » | « Voilà **mes liens** et leur état » |
| Ce que chacun connaît | Une liste de destinations. **Pas la topologie** | La **carte complète** de l'aire |
| Analogie | Des panneaux routiers : « Lyon 460 km » | Une carte routière dans chaque voiture |
| Calcul | Bellman-Ford, distribué, incrémental | **Dijkstra**, local, sur la carte complète |
| Diffusion | À ses voisins seulement, périodiquement | **Inondation** de toute l'aire, à l'événement |
| Boucles | **Structurellement possibles** → parades | Structurellement impossibles (chacun voit tout) |
| Convergence | Lente (dizaines de s en RIP) | Rapide (< 1 s à quelques s) |
| CPU / RAM | Faibles | Élevés (LSDB + SPF) |
| Passage à l'échelle | Limité | Excellent (grâce aux **aires**) |

Le cœur de la différence, en une image : **le vecteur de distance croit ce qu'on lui dit ; l'état de liens
vérifie par lui-même**. Un routeur RIP qui reçoit « je connais X à 3 sauts » n'a aucun moyen de savoir si le
chemin de son voisin repasse par lui-même. Un routeur OSPF, lui, reconstruit le graphe entier et voit la
boucle avant de calculer.

> ❓ **RETIENS ÇA** — Qu'échangent respectivement un protocole à vecteur de distance et un protocole à état de liens ?
> <details><summary>→ réponse</summary><br>Vecteur de distance : <b>des routes</b> (destination + distance), uniquement à ses voisins directs. État de liens : <b>l'état de ses propres liens</b> (LSA), inondé à toute l'aire — chacun reconstruit la topologie complète et calcule Dijkstra localement.</details>

### 6.1 RIP, et le comptage à l'infini

RIP est mort en production, mais il faut savoir **pourquoi** il est mort : la démonstration est le meilleur
argument en faveur d'OSPF.

Chiffres RIP : métrique = **nombre de sauts**, maximum **15**, **16 = infini/inatteignable**. Mise à jour
toutes les **30 s** en UDP **520** (RIPng : **521**), multicast **224.0.0.9** en v2. AD **120**.
Timers : *update* 30 s, *invalid* 180 s, *holddown* 180 s, *flush* 240 s.

Le **comptage à l'infini** :

```
   A ──── B ──── C        C annonce le réseau X.
                          B : « X à 1 saut via C ». A : « X à 2 sauts via B ».

   Le lien B—C tombe :
   t0  B perd X. Mais AVANT que B ne prévienne A, A envoie sa mise à jour
       périodique : « je connais X à 2 sauts ».
   t1  B croit A : « X à 3 sauts via A ».  ← LA BOUCLE EST NÉE
   t2  A voit B à 3 → A passe à 4. B passe à 5. A à 6…
   …   jusqu'à 16 = infini. Pendant tout ce temps, les paquets pour X
       font l'aller-retour A↔B jusqu'à expiration du TTL.
```

Parades empilées par RIP : **split horizon** (ne pas réannoncer une route sur l'interface d'où elle vient),
**poison reverse** (la réannoncer avec métrique 16), **triggered updates** (annoncer immédiatement une
perte), **holddown** (ignorer les bonnes nouvelles pendant 180 s). Empilées, elles limitent les dégâts.
Elles ne les suppriment pas — et surtout, la convergence se compte alors en **minutes**.

### 6.2 EIGRP, le vecteur de distance qui ne boucle pas

EIGRP (Cisco, ouvert depuis la RFC 7868) garde l'échange de routes mais ajoute **DUAL**, qui interdit
structurellement la boucle.

- Protocole IP **88**, multicast **224.0.0.10**. Hello **5 s** / hold **15 s** sur liens rapides
  (60 s / 180 s sur liens lents type NBMA ≤ T1). AD **90** interne, **170** externe, **5** pour un résumé.
- Métrique composite : `256 × (10⁷/BW_min_kbps + Σdélais_µs/10)` avec les K par défaut **K1=K3=1,
  K2=K4=K5=0** — c'est-à-dire bande passante minimale du chemin + délai cumulé.
- **FD** (*Feasible Distance*) : mon coût total vers la destination. **RD/AD** (*Reported Distance*) : le
  coût annoncé par le voisin.
- **Condition de faisabilité : RD_voisin < FD_actuelle.** Si elle est vraie, ce voisin est un **feasible
  successor** — un chemin de secours **garanti sans boucle**, prêt en RAM. Bascule en **millisecondes**,
  sans recalcul.

> 🧠 **MÉMO** — La condition de faisabilité en une phrase : **« mon secours doit être plus près de la
> destination que je ne le suis moi-même »**. S'il était plus loin, son chemin pourrait repasser par moi —
> donc boucle.

---

## 7. OSPF — vue d'ensemble

**OSPF** = *Open Shortest Path First*. OSPFv2 = **RFC 2328** (IPv4), OSPFv3 = **RFC 5340** (IPv6, et
IPv4 aussi via des familles d'adresses). C'est le protocole IGP par défaut du métier.

Les chiffres d'identité, à connaître froid :

| Élément | Valeur |
|---|---|
| Protocole IP | **89** (directement sur IP — ni TCP ni UDP) |
| Multicast *AllSPFRouters* | **224.0.0.5** (MAC `01:00:5e:00:00:05`) |
| Multicast *AllDRouters* | **224.0.0.6** (MAC `01:00:5e:00:00:06`) |
| TTL des paquets | **1** (voisins directs uniquement) |
| Distance administrative | **110** |
| En-tête OSPF | **24 octets** (OSPFv3 : 16) |
| Hello / Dead (broadcast, P2P) | **10 s / 40 s** (dead = 4 × hello) |
| Hello / Dead (NBMA, P2MP) | **30 s / 120 s** |
| MaxAge d'une LSA | **3600 s** (1 h) |
| Refresh d'une LSA | **1800 s** (30 min) |
| Bande passante de référence par défaut | **10⁸ bit/s = 100 Mbit/s** |
| ECMP par défaut (IOS) | **4** chemins |

### 7.1 L'en-tête OSPF (24 octets)

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|  Version (=2) |     Type      |        Packet length          |   4 o
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                       Router ID                               |   4 o
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                        Area ID                                |   4 o
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|          Checksum             |            AuType             |   4 o
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                     Authentication (8 octets)                 |   8 o
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
                                                        TOTAL : 24 o
```

Le **Router ID** est un identifiant sur 32 bits **écrit comme une IP mais qui n'en est pas une**. Ordre de
sélection : (1) `router-id` configuré à la main, (2) la plus haute IP d'une **loopback** active, (3) la plus
haute IP d'une interface physique active. En production on le fixe **toujours** à la main — sinon il change
au reboot si une interface a changé, et l'adjacence casse.

### 7.2 Les 5 types de paquets

| Type | Nom | Rôle |
|---:|---|---|
| **1** | **Hello** | Découvrir les voisins, maintenir l'adjacence, élire DR/BDR |
| **2** | **DBD** (*Database Description*) | S'échanger la **liste** (les en-têtes) des LSA qu'on possède |
| **3** | **LSR** (*Link State Request*) | « Envoie-moi les LSA que je n'ai pas » |
| **4** | **LSU** (*Link State Update*) | Le contenu réel des LSA (c'est le paquet qui porte la donnée) |
| **5** | **LSAck** | Accusé de réception d'une LSU (OSPF est fiable, il refait sans TCP) |

> 🧠 **MÉMO** — Ordre 1→5 : **« Hello, Décris, Demande, Donne, Dis merci »**.
> Hello · DBD · LSR · LSU · LSAck.

Le Hello porte les paramètres qui **doivent être identiques** pour que l'adjacence se forme :

```
 Hello : masque réseau | HelloInterval | Options | Priorité | DeadInterval
         | DR | BDR | liste des voisins vus

 DOIVENT correspondre :  Area ID · HelloInterval · DeadInterval · masque réseau
                         (sur lien broadcast) · authentification · flag de stub
 NE doivent PAS correspondre : Router ID (unique !) · priorité · coût · process-id
```

Le champ « liste des voisins vus » est ce qui permet la bidirectionnalité : quand R1 voit **son propre
Router ID** dans le Hello de R2, il sait que la communication passe dans les deux sens → état **2-Way**.

> ⚠️ **PIÈGE** — Le **process-id** OSPF (`router ospf 1`) est **purement local**. Deux routeurs avec
> `router ospf 1` et `router ospf 77` s'appairent parfaitement. Ce qui doit correspondre, c'est l'**Area
> ID**, pas le process-id. Erreur de débutant classique.

### 7.3 Les 8 états d'adjacence

C'est **la** machine à états à connaître par cœur — et l'objet du palais mental de ce module.

```
  DOWN
   │  reçoit un Hello
   ▼
  ATTEMPT (NBMA uniquement : on envoie des Hello unicast à un voisin configuré)
   │
   ▼
  INIT        j'ai reçu un Hello, mais je ne m'y vois pas encore
   │  je vois MON Router ID dans son Hello
   ▼
  2-WAY       bidirectionnel confirmé. ★ ÉLECTION DR/BDR ICI ★
   │          Deux DROTHER sur un lien broadcast RESTENT ICI. C'est normal.
   ▼
  EXSTART     élection maître/esclave (le plus grand Router ID = maître),
   │          échange du numéro de séquence initial. ★ CONTRÔLE DU MTU ★
   ▼
  EXCHANGE    échange des DBD : les EN-TÊTES des LSA (le catalogue, pas les livres)
   │
   ▼
  LOADING     LSR / LSU / LSAck pour récupérer les LSA manquantes
   │
   ▼
  FULL        LSDB identiques. Adjacence complète. → Dijkstra peut tourner.
```

Les deux états où l'on **reste bloqué** en vrai, et leur cause :

| Bloqué en | Cause quasi certaine |
|---|---|
| **INIT** | Trafic unidirectionnel : ACL, mauvais VLAN, authentification asymétrique |
| **EXSTART / EXCHANGE** | **MTU différent** des deux côtés. OSPF compare le MTU dans les DBD et refuse |
| **2-WAY** persistant | Normal entre deux DROTHER. Anormal s'il n'y a que 2 routeurs — vérifie les priorités |

> ❓ **RETIENS ÇA** — Deux routeurs OSPF restent bloqués en ExStart. Quelle est la cause de loin la plus probable ?
> <details><summary>→ réponse</summary><br>Un <b>MTU différent</b> entre les deux interfaces. OSPF compare le MTU dans les paquets DBD et refuse de passer en Exchange s'il diffère. Contournement : <code>ip ospf mtu-ignore</code> — mais la vraie correction est d'aligner les MTU.</details>

> ❓ **RETIENS ÇA** — À quel état l'élection DR/BDR a-t-elle lieu ?
> <details><summary>→ réponse</summary><br>En <b>2-Way</b>, juste après la confirmation de bidirectionnalité et avant ExStart.</details>

### 7.4 DR et BDR — pourquoi, et comment

Sur un segment multi-accès (un switch avec 6 routeurs), si tout le monde s'appairait avec tout le monde, ça
ferait **n(n−1)/2 = 15** adjacences, donc 15 copies de chaque LSA. Ça n'échelonne pas.

Solution : un **DR** (*Designated Router*) et un **BDR** (secours). Tout le monde s'appaire avec DR et BDR,
et **seulement** avec eux. Le nombre d'adjacences passe à **2n − 3**.

```
   SANS DR : n(n-1)/2            AVEC DR/BDR : 2n-3
   6 routeurs → 15 adjacences    6 routeurs → 9 adjacences
                                 20 routeurs → 190 vs 37

        R2   R3                        R2   R3
         \\ //                          \   /
    R1 ═══╬═══ R4                  R1 ── DR ── R4     (+ liens vers le BDR)
         // \\                          /   \
        R5   R6                        R5   R6

   Trafic : DROTHER → 224.0.0.6 (AllDRouters, écouté par DR et BDR)
            DR      → 224.0.0.5 (AllSPFRouters, écouté par tous)
```

**Élection** : (1) la **priorité** la plus haute (défaut **1**, plage 0-255, **0 = ne sera jamais DR**) ;
(2) à égalité, le **Router ID** le plus haut. Elle est **non préemptive** : un routeur qui arrive avec une
priorité de 255 alors qu'un DR est déjà élu **ne prend pas la place**. Il faudra un `clear ip ospf process`
ou une coupure. C'est voulu — la stabilité prime.

Le DR n'est **pas** un routeur central du trafic de données : il ne fait que centraliser la synchronisation
des LSA. Les paquets, eux, vont toujours en direct.

> ⚠️ **PIÈGE** — Sur un lien entre deux routeurs, une élection DR/BDR est du gaspillage pur : 40 s d'attente
> au démarrage, et une LSA de type 2 inutile. Force le type de réseau : `ip ospf network point-to-point`.
> C'est une des optimisations les plus rentables d'OSPF, et une bonne réponse en entretien.

### 7.5 Les types de réseaux OSPF

| Type | DR/BDR ? | Hello / Dead | Cas d'usage |
|---|:--:|---|---|
| **broadcast** | **Oui** | **10 / 40** | Ethernet — le défaut |
| **point-to-point** | Non | **10 / 40** | Liens série, tunnels, et **Ethernet entre 2 routeurs** (à forcer) |
| non-broadcast (NBMA) | Oui | **30 / 120** | Frame Relay, ATM (historique) |
| point-to-multipoint | Non | **30 / 120** | Hub-and-spoke, DMVPN |
| loopback | — | — | Annoncée en **/32** quoi qu'on fasse |

> ❓ **RETIENS ÇA** — Valeurs par défaut des timers Hello et Dead sur un lien Ethernet OSPF ?
> <details><summary>→ réponse</summary><br><b>Hello 10 s, Dead 40 s</b> (Dead = 4 × Hello). Sur NBMA et point-to-multipoint : <b>30 s / 120 s</b>. Les deux voisins doivent avoir les <b>mêmes</b> valeurs, sinon pas d'adjacence.</details>

---

## 8. La LSDB et les LSA

### 8.1 L'idée

Chaque routeur décrit **ses propres liens** dans une LSA, et **inonde** cette LSA dans toute l'aire. Chaque
routeur collectionne toutes les LSA reçues : c'est la **LSDB** (*Link State Database*). Dans une aire,
**tous les routeurs ont une LSDB rigoureusement identique** — c'est l'invariant fondamental d'OSPF. Puis
chacun exécute Dijkstra **sur sa copie**, avec lui-même comme racine, et obtient des résultats différents
(sa propre table) à partir de données identiques.

Analogie : chaque habitant d'une ville affiche le plan de **sa** rue au tableau central. Le tableau complet
(la LSDB) est photocopié à l'identique pour tout le monde. Ensuite chacun trace **son** itinéraire depuis
**sa** maison. Même carte, itinéraires différents.

> 🧠 **MÉMO** — **Même LSDB pour tous, table de routage différente pour chacun.** Si deux routeurs de la
> même aire n'ont pas la même LSDB, c'est un bug ou une adjacence incomplète — jamais une situation normale.

### 8.2 Les types de LSA

| Type | Nom | Généré par | Portée d'inondation | Contient |
|---:|---|---|---|---|
| **1** | **Router LSA** | **Tous** les routeurs | **L'aire** | Mes liens, leurs coûts, leurs types |
| **2** | **Network LSA** | Le **DR** | **L'aire** | La liste des routeurs sur ce segment multi-accès |
| **3** | **Summary LSA** | **ABR** | Les **autres aires** | Un préfixe d'une autre aire + son coût |
| **4** | **ASBR Summary** | **ABR** | Les autres aires | *Où* se trouve l'ASBR (comment le joindre) |
| **5** | **AS External** | **ASBR** | **Tout l'AS** sauf aires stub | Un préfixe venu d'un autre protocole |
| **7** | **NSSA External** | ASBR dans une **NSSA** | La NSSA seule, puis converti en type 5 par l'ABR | Un externe injecté dans une aire stub-like |

Le type 6 (MOSPF) est abandonné. Les types **9/10/11** sont les *opaque LSA* (portée lien / aire / AS),
utilisées par MPLS-TE et le Segment Routing. En OSPFv3, les types **8** (Link LSA) et **9** (Intra-Area
Prefix LSA) séparent la topologie de l'adressage.

> 🧠 **MÉMO** — **1 = moi, 2 = nous, 3 = ailleurs, 4 = la porte de sortie, 5 = le dehors.**
> *Moi* (mes liens) → *nous* (le segment partagé) → *ailleurs* (autre aire) → *la porte* (l'ASBR) →
> *le dehors* (hors OSPF).

Chaque LSA porte un **numéro de séquence** commençant à `0x80000001`, incrémenté à chaque changement, un
**âge** (0 → **3600 s = MaxAge**), et un **checksum**. À MaxAge la LSA est purgée de toute l'aire. Une LSA
inchangée est **rafraîchie toutes les 1800 s** (30 min) — c'est le seul trafic périodique lourd d'OSPF, et
c'est pour ça qu'OSPF est dit « événementiel ».

```
$ show ip ospf database
            OSPF Router with ID (1.1.1.1) (Process ID 1)

                Router Link States (Area 0)
Link ID         ADV Router      Age   Seq#        Checksum Link count
1.1.1.1         1.1.1.1         412   0x80000007  0x00A1B2  3
2.2.2.2         2.2.2.2         389   0x8000000C  0x004F19  4

                Net Link States (Area 0)
Link ID         ADV Router      Age   Seq#        Checksum
10.1.1.2        2.2.2.2         389   0x80000003  0x00C3D4

                Summary Net Link States (Area 0)
10.3.0.0        3.3.3.3         120   0x80000002  0x0077AA
```

> ❓ **RETIENS ÇA** — Qui génère une LSA de type 2, et pourquoi ?
> <details><summary>→ réponse</summary><br>Le <b>DR</b> d'un segment multi-accès. Elle décrit la liste des routeurs attachés à ce segment, ce qui permet de représenter le segment comme un <b>pseudo-nœud</b> dans le graphe au lieu d'un maillage complet.</details>

> ❓ **RETIENS ÇA** — MaxAge et intervalle de rafraîchissement d'une LSA ?
> <details><summary>→ réponse</summary><br>MaxAge = <b>3600 s (1 h)</b>, rafraîchissement = <b>1800 s (30 min)</b>.</details>

---

## 9. Le coût OSPF et Dijkstra

### 9.1 Le calcul du coût

```
                bande passante de référence          10⁸ bit/s (défaut)
   coût  =  ──────────────────────────────────  =  ─────────────────────
              bande passante de l'interface        bande passante réelle

   Division ENTIÈRE (troncature), minimum 1.
```

| Interface | Coût (réf. 100 Mbit/s, défaut) | Coût (réf. 100 Gbit/s) |
|---|---:|---:|
| 64 kbit/s | 1562 | 1 562 500 |
| T1 (1,544 Mbit/s) | **64** | 64 766 |
| E1 (2,048 Mbit/s) | 48 | 48 828 |
| 10 Mbit/s | **10** | 10 000 |
| 100 Mbit/s | **1** | **1000** |
| 1 Gbit/s | **1** ⚠️ | **100** |
| 10 Gbit/s | **1** ⚠️ | **10** |
| 100 Gbit/s | **1** ⚠️ | **1** |

> ⚠️ **PIÈGE** — **La référence par défaut (100 Mbit/s) date de 1998 et est aujourd'hui absurde.** Avec
> elle, un lien à 100 Mbit/s, un à 10 Gbit/s et un à 100 Gbit/s ont **tous un coût de 1** : OSPF ne peut
> plus les départager et enverra allègrement le trafic sur le lien saturé. C'est **le** défaut de
> configuration le plus fréquent dans les réseaux réels.
>
> Correction : `auto-cost reference-bandwidth 100000` (valeur **en Mbit/s**, donc 100 Gbit/s), à appliquer
> **sur tous les routeurs de l'AS**. Une référence non uniforme produit des calculs incohérents et des
> boucles temporaires.

Le coût s'applique sur l'interface de **sortie** et le coût d'un chemin est la **somme** des coûts des
interfaces traversées à l'aller. Un coût d'entrée n'existe pas. On peut le forcer sur une interface :
`ip ospf cost 15` — ce qui écrase le calcul automatique.

> ❓ **RETIENS ÇA** — Formule du coût OSPF et bande passante de référence par défaut ?
> <details><summary>→ réponse</summary><br><b>coût = bande passante de référence / bande passante de l'interface</b>, division entière, minimum 1. Référence par défaut : <b>10⁸ bit/s = 100 Mbit/s</b>. Conséquence : tout ce qui est ≥ 100 Mbit/s a un coût de 1.</details>

### 9.2 Dijkstra — l'algorithme, en 4 lignes

```
1. Racine = moi, distance 0. Tous les autres à ∞.
2. Deux ensembles : CONNUS (distance définitive) et CANDIDATS (distance provisoire).
3. Répéter : prendre le CANDIDAT de plus petite distance → il devient CONNU (sa
   distance est définitive). Pour chacun de ses voisins encore candidats :
   si distance(connu) + coût(lien) < distance(candidat), METTRE À JOUR + noter le parent.
4. S'arrêter quand il n'y a plus de candidat.
```

L'intuition qui rend l'algorithme évident : **le plus proche des candidats ne peut plus être amélioré**.
Tout autre chemin vers lui passerait par un candidat encore plus lointain, donc serait plus long. C'est
pour ça qu'on peut le figer définitivement. (Et pour ça que Dijkstra ne supporte pas les coûts négatifs.)

Le **prochain saut** ne se lit pas dans les distances : il se lit en **remontant les parents** jusqu'à
tomber sur un voisin direct de la racine. C'est ce voisin qui entre dans la table de routage.

### 9.3 Exercice corrigé — Dijkstra sur 7 routeurs

Topologie (coûts sur les liens) :

```
              1          2
        A ────────► B ────────► G
        │           │
      2 │           │ 5
        ▼           ▼
        C ────────► D ────────► F
             1      │     6
                    │ 1
                3   ▼
        C ─────────► E ────────► F
                            2
   Liens (non orientés) et coûts :
   A-B 1 · A-C 2 · B-C 2 · B-D 5 · B-G 2 · C-D 1 · C-E 3 · D-E 1 · D-F 6 · E-F 2
```

**Déroulé, table de travail** (on note `distance/parent`) :

| Étape | Nœud figé | A | B | C | D | E | F | G |
|---|---|---|---|---|---|---|---|---|
| Init | — | **0** | ∞ | ∞ | ∞ | ∞ | ∞ | ∞ |
| 1 | **A** (0) | ✔ | 1/A | 2/A | ∞ | ∞ | ∞ | ∞ |
| 2 | **B** (1) | ✔ | ✔ | 2/A (1+2=3 ✗) | 6/B | ∞ | ∞ | 3/B |
| 3 | **C** (2) | ✔ | ✔ | ✔ | **3/C** (2+1) | 5/C | ∞ | 3/B |
| 4 | **D** (3) | ✔ | ✔ | ✔ | ✔ | **4/D** (3+1) | 9/D | 3/B |
| 5 | **G** (3) | ✔ | ✔ | ✔ | ✔ | 4/D | 9/D | ✔ |
| 6 | **E** (4) | ✔ | ✔ | ✔ | ✔ | ✔ | **6/E** (4+2) | ✔ |
| 7 | **F** (6) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |

Détail des trois décisions non triviales :

- **Étape 2** : depuis B (dist 1), C vaudrait 1+2 = **3**. Mais C est déjà à **2** via A directement.
  3 > 2 → on **ne met pas à jour**. Le lien A-C reste le bon.
- **Étape 3** : depuis C (dist 2), D vaudrait 2+1 = **3**, contre **6** via B. 3 < 6 → **mise à jour**,
  parent de D = C. Le chemin A-B-D est abandonné.
- **Étape 6** : depuis E (dist 4), F vaudrait 4+2 = **6**, contre **9** via D. → mise à jour.

**Remontée des parents pour trouver le prochain saut :**

| Dest | Coût | Chaîne de parents | Chemin | **Next-hop** |
|---|---:|---|---|---|
| B | 1 | B←A | A-B | **B** |
| C | 2 | C←A | A-C | **C** |
| D | 3 | D←C←A | A-C-D | **C** |
| E | 4 | E←D←C←A | A-C-D-E | **C** |
| F | 6 | F←E←D←C←A | A-C-D-E-F | **C** |
| G | 3 | G←B←A | A-B-G | **B** |

Deux prochains sauts seulement (**B** et **C**) pour six destinations : c'est toujours comme ça. Le nombre
de prochains sauts est borné par le nombre de **voisins directs**, jamais par le nombre de destinations.

**Variante ECMP.** Passe le coût A-C de 2 à **3**. Alors C vaut 3 via A **et** 3 via B (1+2) : égalité.
OSPF installe **deux** chemins vers C, et **tout ce qui passe par C hérite des deux prochains sauts** :
D (4), E (5), F (7) sortent en ECMP par B **et** C. Un seul lien recalculé, six routes changées — c'est
la définition même de la sensibilité d'un IGP.

> ❓ **RETIENS ÇA** — Pourquoi Dijkstra peut-il figer définitivement le candidat de plus petite distance ?
> <details><summary>→ réponse</summary><br>Parce que tout autre chemin vers lui devrait passer par un candidat de distance <b>supérieure ou égale</b>, donc serait au moins aussi long. Avec des coûts positifs, sa distance provisoire est déjà optimale.</details>

### 9.4 Coût et ordre de préférence des routes OSPF

À l'intérieur d'OSPF, le **type** de route l'emporte sur le coût. L'ordre :

```
   O (intra-aire)  >  O IA (inter-aire)  >  E1 / N1  >  E2 / N2
   ─────────────────────────────────────────────────────────────►
                    préférence décroissante

   Une route intra-aire de coût 500 BAT une route inter-aire de coût 10.
```

**E1 vs E2** — la seule vraie subtilité de la redistribution :

| | **E2** (défaut) | **E1** |
|---|---|---|
| Coût affiché | **La métrique externe seule** (défaut **20**) | Métrique externe **+ coût interne** jusqu'à l'ASBR |
| Effet | Le coût est le même partout dans l'AS | Le coût grandit à mesure qu'on s'éloigne de l'ASBR |
| Quand l'utiliser | Un seul point de sortie | **Plusieurs ASBR** : E1 choisit le plus proche |

> ⚠️ **PIÈGE** — Avec deux ASBR et des routes en **E2**, tous les routeurs voient le même coût (20) et
> choisissent l'ASBR de plus petit Router ID ou selon un départage arbitraire — pas le plus proche. Le
> trafic peut traverser tout le réseau pour sortir. Avec **E1**, chacun sort par l'ASBR le plus proche.
> C'est la question piège classique en entretien.

---

## 10. Aires, ABR, ASBR

### 10.1 Pourquoi des aires

Dijkstra est en `O(L·log N)` — pas un problème. Le problème est ailleurs : **chaque changement de lien
déclenche une inondation et un recalcul complet chez tous les routeurs de l'aire**. Avec 300 routeurs et
un lien instable, le réseau passe son temps à recalculer.

L'aire est un **pare-feu à instabilité** : une LSA de type 1 ou 2 ne sort **jamais** de son aire. Un lien
qui bat dans l'aire 10 ne fait pas recalculer l'aire 20 — l'ABR ne réannonce que le préfixe résumé
(type 3), et seulement s'il change.

```
                     ┌───────────── AIRE 0 (BACKBONE) ─────────────┐
                     │                                             │
          ┌──────────┤   R2 ══════════ R3 ══════════ R4            │
          │          │   (ABR)         (ASBR) ─── BGP/statique     │
          │          └──────┬──────────────────────────────────────┘
     AIRE 10                │                          AIRE 20
   ┌───────────┐            │                     ┌───────────┐
   │  R1 ── R5 │◄───────────┘                     │ R6 ── R7  │
   └───────────┘                                  └───────────┘

   RÈGLE D'OR : toute aire non-backbone DOIT toucher l'aire 0.
                Aire 10 → Aire 20 passe OBLIGATOIREMENT par l'aire 0.
                Pas de raccourci, même s'il existe un câble.
```

| Rôle | Définition | Ce qu'il produit |
|---|---|---|
| **Routeur interne** | Toutes ses interfaces dans une seule aire | Type 1 |
| **ABR** (*Area Border Router*) | Au moins une interface dans l'aire 0 **et** une ailleurs | Types **3** et **4** ; tient **une LSDB par aire** |
| **ASBR** (*AS Boundary Router*) | Redistribue des routes venues d'ailleurs (statique, BGP, EIGRP) | Type **5** (ou **7** en NSSA) |
| **Backbone** | Aire **0** / `0.0.0.0` | Transit obligatoire entre aires |

Si une aire est physiquement coupée du backbone, on rétablit avec un **lien virtuel** (`area X
virtual-link <router-id>`) à travers une aire de transit. C'est un pansement, pas une architecture : à
signaler comme tel en entretien.

### 10.2 Les types d'aires spéciales

Le principe : moins un routeur de bordure a besoin de détail, moins on lui en envoie. Une aire terminale
n'a besoin que d'une route par défaut.

| Type d'aire | Type 3 (inter-aire) | Type 4/5 (externe) | Type 7 | Défaut injectée |
|---|:--:|:--:|:--:|:--:|
| **Standard** | ✅ | ✅ | ❌ | non |
| **Stub** | ✅ | ❌ | ❌ | ✅ (type 3) |
| **Totally stubby** (Cisco) | ❌ | ❌ | ❌ | ✅ |
| **NSSA** | ✅ | ❌ | ✅ | optionnelle |
| **Totally NSSA** | ❌ | ❌ | ✅ | ✅ |

**NSSA** = *Not-So-Stubby Area* : une aire stub qui contient malgré tout un ASBR. Comme les type 5 y sont
interdites, l'ASBR émet des **type 7**, que l'ABR **convertit en type 5** à la sortie. C'est le seul rôle
du type 7 — et c'est une question d'entretien fréquente.

```
! Cisco — toutes les aires stub doivent être déclarées sur TOUS les routeurs de l'aire
router ospf 1
 area 10 stub                    ! sur tous les routeurs de l'aire 10
 area 10 stub no-summary         ! sur l'ABR seulement → totally stubby
 area 30 nssa
```

> ⚠️ **PIÈGE** — Le flag « stub » est dans le **Hello**. Si un seul routeur de l'aire ne l'a pas, **aucune
> adjacence ne se forme** avec lui. Symptôme : « j'ai configuré `area 10 stub` sur l'ABR et j'ai perdu tous
> mes voisins ». Le backbone (aire 0) ne peut jamais être stub.

> ❓ **RETIENS ÇA** — À quoi sert exactement une LSA de type 7 ?
> <details><summary>→ réponse</summary><br>À transporter une route externe <b>à l'intérieur d'une NSSA</b>, où les LSA de type 5 sont interdites. L'ABR de la NSSA la <b>convertit en type 5</b> pour le reste de l'AS.</details>

### 10.3 Résumé de routes et route de rejet

Résumer, c'est remplacer plusieurs préfixes par un seul plus court. Effet : moins d'entrées, et surtout
**moins d'événements** — la disparition d'un /24 interne ne se voit plus depuis l'extérieur.

```
! Sur l'ABR : résumer les routes INTRA-aire à la sortie de l'aire 10
router ospf 1
 area 10 range 10.10.0.0 255.255.248.0        ! 10.10.0.0/21 = les /24 de .0 à .7

! Sur l'ASBR : résumer les routes EXTERNES redistribuées
 summary-address 192.0.2.0 255.255.254.0
```

> ⚠️ **PIÈGE** — Le **trou noir du résumé**. Tu annonces `10.10.0.0/21` mais `10.10.5.0/24` n'existe plus.
> Le trafic pour `10.10.5.7` arrive chez toi (tu l'as annoncé), tu n'as pas de route spécifique, tu le
> renvoies par ta **route par défaut**… vers celui qui te l'a envoyé. **Boucle** jusqu'au TTL.
> La parade est automatique chez Cisco quand on résume (route `Null0` installée), et à faire **à la main**
> partout ailleurs : `ip route 10.10.0.0 255.255.248.0 Null0` ou `ip route add blackhole 10.10.0.0/21`.

### 10.4 Configuration OSPF minimale

```
! Cisco — méthode classique (network + wildcard)
router ospf 1
 router-id 1.1.1.1
 auto-cost reference-bandwidth 100000
 passive-interface default
 no passive-interface GigabitEthernet0/0
 network 10.1.1.0 0.0.0.255 area 0        ! wildcard = masque INVERSÉ
 network 10.10.0.0 0.0.255.255 area 10

! Cisco — méthode moderne (par interface, préférée)
interface GigabitEthernet0/0
 ip ospf 1 area 0
 ip ospf network point-to-point
 ip ospf cost 10
 ip ospf priority 0
 ip ospf authentication message-digest
 ip ospf message-digest-key 1 md5 <clé>
```

```
# FRR (Linux) — /etc/frr/frr.conf
router ospf
 ospf router-id 1.1.1.1
 auto-cost reference-bandwidth 100000
 passive-interface default
 network 10.1.1.0/24 area 0
!
interface eth0
 no ip ospf passive
 ip ospf network point-to-point
 ip ospf hello-interval 1
 ip ospf dead-interval 4
```

**`passive-interface`** : l'interface **cesse d'envoyer des Hello** (donc plus d'adjacence possible) mais son
préfixe **continue d'être annoncé**. C'est exactement ce qu'on veut sur les interfaces vers les serveurs :
on annonce le LAN sans risquer d'appairer avec n'importe quoi. La bonne pratique est
`passive-interface default` puis on ouvre explicitement les liens d'infrastructure.

> ❓ **RETIENS ÇA** — Que fait `passive-interface` ?
> <details><summary>→ réponse</summary><br>Elle arrête l'émission des Hello sur l'interface (donc aucune adjacence) <b>mais le réseau de cette interface reste annoncé</b> dans OSPF. Sécurité de base sur toutes les interfaces utilisateur/serveur.</details>

---

## 11. Convergence

**Converger** = tous les routeurs ont de nouveau une vision cohérente et des tables sans boucle. Le temps
de convergence se décompose :

```
 T_convergence = T_détection + T_inondation + T_délai_SPF + T_calcul + T_installation_FIB
                 ├──────────┤  ├──────────┤  ├──────────┤  ├──────┤   ├───────────────┤
                 0 ms (perte    qq ms par     5 s (défaut   qq ms      qq ms à qq s
                 de porteuse)   saut          IOS)                     (grosse FIB)
                 à 40 s (dead
                 timer) !
```

**La détection domine tout le reste.** Deux cas :

- **Le lien tombe physiquement** (perte de porteuse) : détection **immédiate**, quelques millisecondes.
- **Le lien reste up mais le voisin est mort** (crash logiciel, boucle L2, VM figée, fibre coupée derrière
  un convertisseur média) : il faut attendre le **dead timer = 40 s**. Une éternité.

Les trois leviers, du moins au plus recommandé :

1. **Baisser les timers** : `ip ospf hello-interval 1` / `dead-interval 4`. Ça descend à ~4 s mais ça
   charge le CPU et ça crée des faux positifs sous charge.
2. **`dead-interval minimal hello-multiplier 4`** (Cisco) : Hello sub-seconde, dead à 1 s.
3. **BFD** — *Bidirectional Forwarding Detection*, la vraie réponse. Un protocole minimaliste dédié à la
   détection, souvent en matériel : intervalle **50 à 300 ms**, multiplicateur **3** → détection en
   **150 ms à 900 ms**, sans charger le processus OSPF. `ip ospf bfd` / `bfd interval 300 min_rx 300
   multiplier 3`.

Côté calcul, IOS applique un **throttling exponentiel** pour ne pas s'effondrer sur un lien qui bat :
`timers throttle spf 5000 10000 10000` (premier calcul après 5 s, puis attente croissante jusqu'à 10 s) et
`timers throttle lsa all 0 5000 5000`. En lab on descend à `timers throttle spf 50 200 5000`.

> ❓ **RETIENS ÇA** — Combien de temps OSPF met-il à détecter un voisin mort dont le lien reste up, et comment fait-on mieux ?
> <details><summary>→ réponse</summary><br><b>40 s</b> (le dead interval par défaut). On fait mieux avec <b>BFD</b> : intervalle 50-300 ms × multiplicateur 3 → détection en <b>150-900 ms</b>, sans charger OSPF.</details>

> 🧠 **MÉMO** — **OSPF sait très bien recalculer. Il sait très mal s'apercevoir qu'il faut recalculer.**
> C'est pour ça que BFD existe.

---

## 12. Redistribution et VRF

### 12.1 Redistribuer

Faire passer des routes d'un protocole à un autre. Le problème : les métriques ne sont pas comparables, il
faut donc une **métrique de départ** (*seed metric*).

```
router ospf 1
 redistribute static subnets metric 100 metric-type 1
 redistribute bgp 65000 subnets route-map BGP-VERS-OSPF
 default-information originate            ! annonce MA route par défaut dans OSPF
 default-information originate always     ! l'annonce même si je n'en ai pas
```

Chiffres à connaître : la métrique de départ par défaut en redistribution **vers OSPF** est **20**
(sauf depuis BGP : **1**), et le type par défaut est **E2**. Le mot-clé `subnets` était obligatoire avant
IOS 15.x pour ne pas se limiter aux réseaux classful — sans lui, seuls les préfixes classful passaient,
panne silencieuse classique.

> ⚠️ **PIÈGE** — **La redistribution mutuelle crée des boucles.** Si OSPF et EIGRP se redistribuent l'un
> dans l'autre en deux points, une route peut faire le tour et revenir avec une AD plus basse que
> l'originale. Trois parades : **filtrer** (route-map + prefix-list), **taguer** à l'entrée et rejeter le
> tag à la sortie (`set tag 100` / `match tag 100`), **augmenter l'AD** des routes redistribuées.
> Règle simple : ne redistribue **jamais** sans filtre, et si possible **dans un seul sens**.

### 12.2 VRF — plusieurs tables de routage dans un routeur

**VRF** = *Virtual Routing and Forwarding*. Un routeur physique qui contient **plusieurs tables de routage
totalement étanches**. Analogie : les VLAN font ça en couche 2 (plusieurs domaines de diffusion dans un
switch), la VRF fait la même chose en couche 3.

Deux clients peuvent alors utiliser **le même `10.0.0.0/8`** sans se voir. C'est ce qui rend possible le
MPLS L3VPN des opérateurs, et c'est de plus en plus utilisé en datacenter pour séparer *management*,
*production* et *stockage*.

```
   ┌──────────────── UN SEUL ROUTEUR ────────────────┐
   │  VRF PROD     │  VRF DEV      │  VRF MGMT       │
   │  10.0.0.0/8   │  10.0.0.0/8   │  192.168.0.0/16 │  ← MÊME préfixe, aucun conflit
   │  table 100    │  table 200    │  table 300      │
   └───────────────┴───────────────┴─────────────────┘
      Aucune fuite entre VRF sans route-leaking EXPLICITE.
```

```bash
# Linux (VRF-lite, noyau ≥ 4.3)
ip link add vrf-prod type vrf table 100
ip link set vrf-prod up
ip link set eth1 master vrf-prod
ip route add default via 10.0.0.1 vrf vrf-prod
ip route show vrf vrf-prod
ip vrf exec vrf-prod curl https://warehouse.interne     # exécuter DANS la VRF
```

```
! Cisco
vrf definition PROD
 rd 65000:100                       ! Route Distinguisher : rend le préfixe unique dans MP-BGP
 address-family ipv4
  route-target export 65000:100     ! Route Target : contrôle qui importe quoi
  route-target import 65000:100
interface Gi0/1
 vrf forwarding PROD                ! ⚠ efface l'adresse IP : la reconfigurer APRÈS
 ip address 10.0.0.1 255.255.255.0
ip route vrf PROD 0.0.0.0 0.0.0.0 10.0.0.254
show ip route vrf PROD
```

> ❓ **RETIENS ÇA** — Différence entre Route Distinguisher et Route Target ?
> <details><summary>→ réponse</summary><br>Le <b>RD</b> (64 bits) rend un préfixe <b>unique</b> dans MP-BGP quand plusieurs VRF utilisent le même adressage — c'est un préfixe technique. Le <b>RT</b> est une communauté étendue qui décide <b>quelle VRF importe quelle route</b> — c'est la politique. RD = unicité, RT = politique.</details>

---

## 13. Ce qu'un data engineer voit vraiment

### 13.1 « Mon job n'atteint pas le cluster distant »

L'ordre de diagnostic, du moins cher au plus cher — ne saute jamais une étape :

```
 1. ip route get <IP_cible>     → y a-t-il une route ? laquelle ? quelle source ?
 2. ping <IP_cible>             → ICMP passe-t-il ? (souvent bloqué : non concluant si KO)
 3. traceroute -T -p 443 <IP>   → jusqu'où ça va, et par où
 4. curl -v --connect-timeout 5 → SYN sans réponse = réseau ; RST = quelque chose refuse
 5. ss -tanp | grep <IP>        → SYN-SENT bloqué = pas de retour
 6. tcpdump -ni any host <IP>   → DES DEUX CÔTÉS. Le seul juge de paix.
```

Le point de bascule est l'étape 6 : si tu vois le SYN **arriver** côté serveur et le SYN-ACK **partir**,
mais que rien ne revient côté client, le problème est **la route de retour** ou un pare-feu sur le chemin
de retour. Ce n'est jamais l'application.

**Les cinq causes réelles, par fréquence :**

| # | Cause | Signature |
|---|---|---|
| 1 | **Route dans un seul sens** (VPC A connaît B, B ne connaît pas A) | SYN arrive, SYN-ACK part, rien ne revient |
| 2 | **Security group / NACL / firewall** | SYN sans réponse, rien dans le tcpdump distant |
| 3 | **Chevauchement de CIDR** entre les deux VPC | Peering refusé, ou trafic qui reste local |
| 4 | **Peering non transitif** : A↔B et B↔C, mais A ne joint pas C | `ip route get` sort bien, mais ça meurt au 2ᵉ saut |
| 5 | **Route par défaut absente** dans le subnet privé (pas de NAT GW) | Sortie Internet KO, interne OK |

> ⚠️ **PIÈGE** — **Le peering VPC n'est pas transitif, et ça n'est pas un bug.** A↔B et B↔C ne donnent
> jamais A↔C : chaque table de routage ne contient que ses pairs directs. La transitivité exige un
> **Transit Gateway** (ou du routage explicite via une appliance). C'est la question qu'on pose en
> entretien cloud, et elle découle directement du modèle saut par saut de la section 1.

### 13.2 Lire un traceroute

```
$ traceroute -n -T -p 443 warehouse.example.com
 1  10.0.1.1        0.412 ms   0.389 ms   0.401 ms     ← passerelle du subnet
 2  10.0.0.1        1.203 ms   1.180 ms   1.199 ms     ← routeur de VPC / TGW
 3  * * *                                              ← ne répond pas en ICMP
 4  100.65.4.9      2.9 ms     3.1 ms     2.8 ms
 5  203.0.113.17   18.4 ms    18.9 ms    18.2 ms       ← saut inter-région (+15 ms)
 6  198.51.100.3   19.1 ms    18.7 ms    19.0 ms
 7  10.20.30.70    19.5 ms    19.3 ms    19.4 ms       ← arrivée
```

Ce qu'il faut lire, et **surtout** ce qu'il ne faut pas conclure :

- **`* * *` ne veut PAS dire « paquet perdu ».** Ça veut dire « ce routeur ne génère pas d'ICMP Time
  Exceeded » — filtrage, ou *rate-limiting* du plan de contrôle. Si les sauts suivants répondent, tout va
  bien. **Ne t'alarme que si TOUS les sauts après un point sont muets.**
- **Un RTT qui augmente puis redescend est normal.** Le RTT du saut N mesure le traitement ICMP du
  routeur N (basse priorité, fait par le CPU), pas la latence de transit. Seul le RTT **de la
  destination** est fiable.
- **Un bond brutal de latence (+15 ms ici) = un changement géographique.** ~1 ms de RTT pour 100 km de
  fibre (la lumière fait 200 000 km/s dans le verre). +15 ms ≈ 1500 km : tu viens de changer de région.
- **Le traceroute ne montre que l'ALLER.** Le retour peut passer ailleurs. C'est le point suivant.
- Utilise `-T -p 443` (TCP SYN) plutôt que l'UDP par défaut : c'est ce que fait vraiment ton application, et
  ça traverse les pare-feux qui bloquent l'UDP. `mtr -T -P 443 <cible>` donne en plus la perte par saut.

### 13.3 Le routage asymétrique et le pare-feu à états

**Le grand classique.** Un pare-feu à états mémorise les connexions qu'il a vues démarrer. S'il voit
passer un **SYN-ACK sans avoir vu le SYN**, il le jette : pour lui, c'est un paquet hors session.

```
   ALLER :   Client ──► R1 ──► [FW-A] ──► Serveur      SYN vu par FW-A, état créé ✅

   RETOUR :  Serveur ──► R2 ──► [FW-B] ──► Client      SYN-ACK arrive chez FW-B
                                  │                     qui n'a JAMAIS vu le SYN
                                  └──► ❌ DROP

   Symptôme : la connexion reste en SYN_SENT côté client et meurt au timeout.
              Le ping (sans état) passe très bien. tcpdump côté serveur montre
              le SYN reçu ET le SYN-ACK émis. Personne ne comprend.
```

Causes typiques : deux passerelles sur la même machine, deux liens vers deux fournisseurs, un peering et un
VPN vers la même destination, une route plus spécifique d'un seul côté.

Les parades, par ordre de propreté :

1. **Rendre le routage symétrique** — corriger la route en trop ou en moins. La seule vraie solution.
2. **Routage par politique** sur la machine multi-homée (`ip rule from <IP> table N`) pour que le retour
   sorte par l'interface d'entrée.
3. **Synchronisation d'état** entre les deux pare-feux (cluster actif/actif).
4. Désactiver l'inspection à états pour ce flux — dernier recours, et on perd la sécurité.

Côté Linux, le même piège existe **dans le noyau** : `net.ipv4.conf.*.rp_filter` (*Reverse Path Filtering*,
RFC 3704). En mode **strict (1)**, le noyau jette un paquet entrant si la route de retour vers sa source ne
sort pas par cette même interface — c'est-à-dire exactement le cas asymétrique. Le mode **loose (2)**
accepte si une route existe par **n'importe quelle** interface. Le défaut varie selon les distributions :
**vérifie-le, ne le suppose pas.**

```bash
sysctl net.ipv4.conf.all.rp_filter net.ipv4.conf.eth0.rp_filter
# la valeur EFFECTIVE est le MAX de 'all' et de celle de l'interface
```

> ⚠️ **PIÈGE** — La valeur retenue de `rp_filter` est le **maximum** entre `all` et l'interface. Mettre
> `eth0.rp_filter=0` ne sert à rien si `all.rp_filter=1`. Beaucoup de gens perdent une heure là-dessus.

> ❓ **RETIENS ÇA** — Pourquoi un routage asymétrique casse-t-il une connexion TCP alors que le ping passe ?
> <details><summary>→ réponse</summary><br>Parce qu'un <b>pare-feu à états</b> (ou <code>rp_filter</code> en mode strict) sur le chemin de retour voit un SYN-ACK sans avoir vu le SYN correspondant, et le jette comme paquet hors session. Le ping ICMP, lui, ne crée pas d'état et traverse.</details>

### 13.4 Routage, latence et coût d'un pipeline

Ordres de grandeur à avoir en tête quand tu conçois un job :

| Trajet | RTT typique |
|---|---:|
| Même hôte (loopback) | < 0,05 ms |
| Même AZ / même rack | 0,1 - 0,5 ms |
| Entre AZ d'une même région | 0,5 - 2 ms |
| Paris ↔ Francfort | ~ 10 ms |
| Europe ↔ côte est US | ~ 75 - 90 ms |
| Europe ↔ Singapour | ~ 160 - 190 ms |
| Plancher physique | ~ **1 ms de RTT par 100 km** de fibre |

La conséquence est arithmétique et impitoyable : **10⁶ requêtes séquentielles à 80 ms de RTT = 22 heures**,
quelle que soit la bande passante. La bande passante ne guérit jamais la latence. Les seules parades sont
le **batching**, la **parallélisation** (N connexions, cf. ECMP en 2.4), le **pipelining**, et surtout
**rapprocher le calcul de la donnée** plutôt que l'inverse.

### 13.5 Routage dans Kubernetes

Deux plans qu'on confond tout le temps :

- **Les IP de pods sont routées.** Chaque nœud reçoit un sous-bloc du *pod CIDR* (par défaut un **/24** par
  nœud, `--node-cidr-mask-size=24`, alors que kubelet plafonne à **110 pods** par nœud par défaut). Une
  route existe pour chaque nœud, soit via un tunnel (VXLAN, overhead **50 octets** → MTU **1450**), soit en
  routage pur si le réseau sous-jacent connaît les préfixes de pods (Calico en mode BGP, ou *native
  routing* dans le cloud).
- **Les IP de services (ClusterIP) ne sont PAS routées.** Aucune machine ne les possède. C'est
  `kube-proxy` (iptables ou IPVS) qui fait de la **DNAT** vers une IP de pod à la sortie. Chercher une
  ClusterIP dans une table de routage est une perte de temps garantie.

```bash
# sur un nœud : voir les routes de pods
ip route | grep -E 'cni|flannel|cali|tunl'
# 10.244.1.0/24 via 10.0.0.12 dev flannel.1 onlink
# 10.244.2.0/24 via 10.0.0.13 dev flannel.1 onlink

# dans un pod : le défaut pointe vers la veth du nœud
kubectl exec -it mon-pod -- ip route
# default via 10.244.0.1 dev eth0
```

> ⚠️ **PIÈGE** — Un pod qui joint les autres pods mais pas une base de données hors cluster : neuf fois sur
> dix, la route de **retour** de la base vers le pod CIDR n'existe pas dans le réseau d'entreprise. Le
> réseau externe ne connaît pas `10.244.0.0/16`. Deux solutions : annoncer le pod CIDR en BGP (Calico), ou
> masquer les pods derrière l'IP du nœud (`masquerade`/SNAT) — c'est ce que fait le défaut, et c'est
> pourquoi ça marche… jusqu'à ce qu'on désactive le masquerade pour préserver l'IP source.

---

## 14. Trois exercices corrigés

### Exercice 1 — Longest prefix match

Table :

```
 S    0.0.0.0/0        [1/0]     via 203.0.113.1
 O    10.0.0.0/8       [110/20]  via 10.1.1.2
 D    10.20.0.0/16     [90/3072] via 10.1.1.5
 S    10.20.30.0/24    [1/0]     via 10.1.1.9
 O    10.20.30.128/25  [110/30]  via 10.1.1.2
 C    10.1.1.0/24                GigabitEthernet0/0
```

Prochain saut pour : (a) `10.20.30.200` (b) `10.20.30.5` (c) `10.20.40.1` (d) `10.99.0.1` (e) `8.8.8.8` (f) `10.1.1.7` ?

**Corrigé.**

(a) `10.20.30.200` : le /25 `10.20.30.128` couvre **.128 à .255**. 200 y est. Candidats : /0, /8, /16, /24,
/25 → **le /25 gagne** (le plus long). → **via 10.1.1.2**. *Noter que l'AD 110 d'OSPF ne l'empêche pas de
battre une statique d'AD 1 : le LPM passe avant.*

(b) `10.20.30.5` : le /25 couvre .128-.255, **5 n'y est pas**. Le plus long restant est le /24. →
**via 10.1.1.9**.

(c) `10.20.40.1` : hors du /24 (`10.20.30.x`). Le /16 `10.20.0.0` couvre `10.20.0.0`-`10.20.255.255`. →
**via 10.1.1.5**.

(d) `10.99.0.1` : hors du /16. Le /8 couvre tout `10.x`. → **via 10.1.1.2**.

(e) `8.8.8.8` : rien ne matche sauf `0.0.0.0/0`. → **via 203.0.113.1**.

(f) `10.1.1.7` : le /24 connecté `10.1.1.0/24` est le plus long match. Route **connectée** → pas de prochain
saut, **ARP direct sur Gi0/0**.

### Exercice 2 — Distance administrative et route flottante

`192.168.50.0/24` est appris :
- par OSPF, coût 65, via `10.1.1.2` ;
- par une statique `ip route 192.168.50.0 255.255.255.0 10.1.1.9` ;
- par une statique flottante `ip route 192.168.50.0 255.255.255.0 10.1.1.20 130`.

**(a) Qu'y a-t-il dans la table ? (b) Que se passe-t-il si l'interface vers `10.1.1.9` tombe ? (c) Puis si OSPF perd le préfixe ?**

**Corrigé.**

(a) Même préfixe exact pour les trois → le LPM ne départage pas, on passe à l'**AD**. Statique = **1**,
OSPF = **110**, flottante = **130**. La plus basse gagne : **la statique via 10.1.1.9**, affichée
`S 192.168.50.0/24 [1/0] via 10.1.1.9`. Les deux autres restent en attente, invisibles dans
`show ip route`.

(b) La statique perd son interface de sortie → elle est retirée. Il reste OSPF (110) et la flottante (130).
**OSPF gagne** : `O 192.168.50.0/24 [110/65] via 10.1.1.2`.

(c) OSPF disparaît → il ne reste que la flottante. **Elle s'installe** :
`S 192.168.50.0/24 [130/0] via 10.1.1.20`. C'est précisément le rôle d'une route flottante : un secours de
dernier rang, silencieux tant qu'il n'est pas nécessaire.

### Exercice 3 — Coût OSPF sur un chemin

Chemin `A → B → C → D`. Interfaces de sortie : A→B en **1 Gbit/s**, B→C en **100 Mbit/s**, C→D en
**10 Mbit/s**. Coût total du chemin A vers le réseau de D :

**(a) avec la référence par défaut ? (b) avec `auto-cost reference-bandwidth 100000` ?**

**Corrigé.**

(a) Référence = 10⁸ = 100 Mbit/s.
- A→B : 10⁸ / 10⁹ = 0,1 → tronqué à 0, mais **minimum 1** → **1**
- B→C : 10⁸ / 10⁸ = **1**
- C→D : 10⁸ / 10⁷ = **10**
- **Total = 1 + 1 + 10 = 12.**

(b) Référence = 100 000 Mbit/s = 10¹¹.
- A→B : 10¹¹ / 10⁹ = **100**
- B→C : 10¹¹ / 10⁸ = **1000**
- C→D : 10¹¹ / 10⁷ = **10 000**
- **Total = 100 + 1000 + 10 000 = 11 100.**

**Ce que ça démontre** : en (a) le lien à 1 Gbit/s et celui à 100 Mbit/s ont **le même coût de 1** — OSPF
est aveugle à un facteur 10 de bande passante. En (b) le rapport est correctement reflété (100 contre 1000).
Et si un routeur du chemin gardait la référence par défaut, les coûts calculés seraient incohérents d'un
routeur à l'autre : chemins asymétriques, micro-boucles pendant la convergence. **La référence doit être
identique partout, sans exception.**

---

## 15. Questions d'entretien

**1. Comment un routeur choisit-il une route ? Donne l'ordre exact des critères.**
Trois critères, strictement dans cet ordre. D'abord le *longest prefix match* : parmi toutes les entrées qui
contiennent l'adresse de destination, celle dont le masque est le plus long gagne — et ce critère écrase
tous les autres, un /26 OSPF bat un /24 statique. Ensuite, à préfixe rigoureusement identique, la
**distance administrative**, c'est-à-dire la crédibilité de la source : connecté 0, statique 1, eBGP 20,
EIGRP 90, OSPF 110, RIP 120, iBGP 200. Enfin, à préfixe et protocole identiques, la **métrique** du
protocole. Si tout est à égalité, on installe plusieurs chemins en ECMP, réparti par flux via un hachage.

**2. Distance administrative vs métrique : quelle est la différence ?**
La distance administrative compare des **sources** différentes pour un même préfixe : elle répond à « à qui
je fais confiance ». Elle est locale au routeur, jamais transmise. La métrique compare des **chemins** à
l'intérieur d'un même protocole : elle répond à « quel chemin est le meilleur ». Les métriques de deux
protocoles ne sont pas comparables — un coût OSPF de 65 et une métrique EIGRP de 3072 n'ont pas la même
unité, c'est exactement pour ça que l'AD existe.

**3. Vecteur de distance ou état de liens : explique la différence et la conséquence.**
Un protocole à vecteur de distance annonce à ses voisins **ses routes** avec leur distance ; personne ne
connaît la topologie, chacun croit ce qu'on lui dit. D'où la possibilité de boucles et le comptage à
l'infini, qu'on limite par split horizon, poison reverse et holddown, au prix d'une convergence lente. Un
protocole à état de liens annonce **l'état de ses propres liens** dans des LSA inondées à toute l'aire :
chaque routeur reconstruit la carte complète, identique chez tous, et calcule Dijkstra dessus. Les boucles
sont structurellement impossibles en régime stable et la convergence est rapide, au prix de CPU et de RAM.

**4. Décris les états d'adjacence OSPF, et dis-moi où ça se bloque en vrai.**
Down, Attempt (NBMA seulement), Init, 2-Way, ExStart, Exchange, Loading, Full. Init signifie que je reçois
des Hello mais que je ne me vois pas dans la liste de voisins de l'autre ; 2-Way signifie bidirectionnel, et
c'est là que se fait l'élection DR/BDR ; ExStart élit le maître et vérifie le MTU ; Exchange échange les
en-têtes de LSA ; Loading récupère les LSA manquantes ; Full signifie LSDB synchronisées. En pratique on se
bloque en Init quand le trafic est unidirectionnel (ACL, VLAN, authentification asymétrique), et en
ExStart/Exchange quand les **MTU diffèrent** — c'est de très loin la cause n°1. Rester en 2-Way entre deux
DROTHER sur un segment broadcast est parfaitement normal.

**5. À quoi servent le DR et le BDR, et comment sont-ils élus ?**
Sur un segment multi-accès, appairer tout le monde avec tout le monde coûterait n(n−1)/2 adjacences. Le DR
centralise la synchronisation des LSA : chacun ne s'appaire qu'avec le DR et le BDR, ce qui ramène à 2n−3.
Élection par priorité la plus haute (défaut 1, 0 = jamais DR), puis Router ID le plus haut à égalité. Elle
est **non préemptive** : un routeur mieux placé qui arrive après ne prend pas la place, il faut relancer le
processus. Le DR ne route pas le trafic de données, il n'est qu'un point de synchronisation, et sur un lien
entre deux routeurs on l'élimine avec `ip ospf network point-to-point`.

**6. Cite les types de LSA et qui les génère.**
Type 1 Router LSA, généré par tous les routeurs, décrit leurs liens, ne sort pas de l'aire. Type 2 Network
LSA, généré par le DR, décrit les routeurs d'un segment multi-accès, ne sort pas de l'aire. Type 3 Summary,
généré par l'ABR, porte les préfixes inter-aires. Type 4, généré par l'ABR, indique comment joindre un
ASBR. Type 5, généré par l'ASBR, porte les routes externes et est inondé dans tout l'AS sauf les aires stub.
Type 7, généré par un ASBR situé dans une NSSA où le type 5 est interdit, converti en type 5 par l'ABR à
la sortie. Les types 9 à 11 sont les opaques, utilisées par MPLS-TE et le Segment Routing.

**7. Comment se calcule le coût OSPF, et quel est le piège ?**
Coût = bande passante de référence divisée par la bande passante de l'interface, division entière, minimum 1,
et le coût d'un chemin est la somme des coûts des interfaces de sortie. La référence par défaut est
10⁸ bit/s, soit 100 Mbit/s, ce qui date de 1998 : aujourd'hui un lien à 100 Mbit/s, un à 10 Gbit/s et un à
100 Gbit/s ont tous un coût de 1 et OSPF ne peut plus les départager. On corrige avec
`auto-cost reference-bandwidth 100000`, à appliquer **sur tous les routeurs** — une référence hétérogène
produit des calculs incohérents et des micro-boucles pendant la convergence.

**8. Pourquoi des aires, et pourquoi tout doit-il passer par l'aire 0 ?**
L'aire limite la portée de l'inondation : les LSA de type 1 et 2 n'en sortent jamais, donc un lien instable
ne fait recalculer que son aire. L'ABR ne réexporte que des préfixes (type 3), éventuellement résumés, ce qui
réduit la taille des LSDB et le nombre d'événements. L'obligation de passer par l'aire 0 vient du fait
qu'OSPF ne fait de calcul de plus court chemin **complet** qu'à l'intérieur d'une aire : entre aires, il
raisonne en vecteur de distance sur les type 3, et une topologie inter-aires arbitraire pourrait boucler.
La hiérarchie en étoile autour du backbone rend ces boucles impossibles. Si une aire est coupée du
backbone, on rétablit par un lien virtuel, mais c'est un pansement.

**9. Un job dans le VPC A n'atteint pas une base dans le VPC C, alors que A↔B et B↔C sont appairés. Pourquoi ?**
Parce que le peering **n'est pas transitif**. Chaque table de routage de VPC ne contient que les préfixes de
ses pairs directs : la table de A n'a pas de route vers le CIDR de C, et celle de C n'a pas de route
retour vers A. C'est la conséquence directe du routage saut par saut — le VPC B n'a aucune raison de
relayer. La solution est un Transit Gateway, qui fournit une table de routage centrale, ou une appliance de
routage explicite. Et je vérifierais aussi les CIDR : s'ils se chevauchent, aucune de ces solutions ne
marchera sans re-adressage.

**10. Une connexion TCP reste en SYN_SENT, mais le ping passe. Que se passe-t-il ?**
La signature typique du **routage asymétrique face à un pare-feu à états**. L'aller passe par un chemin, le
retour par un autre ; le pare-feu du chemin de retour voit un SYN-ACK sans avoir vu le SYN, le considère
hors session et le jette. Le ping passe parce qu'ICMP echo ne crée pas d'état. Je confirme avec un tcpdump
simultané des deux côtés : le SYN arrive côté serveur, le SYN-ACK part, rien ne revient côté client. Même
symptôme possible sur Linux avec `rp_filter` en mode strict, dont la valeur effective est le maximum entre
`all` et l'interface. La correction propre est de rendre le routage symétrique, ou du routage par politique
sur la machine multi-homée, ou une synchronisation d'état entre pare-feux.

**11. Comment accélérer la convergence OSPF sous la seconde ?**
Le temps de convergence est dominé par la **détection**. Si le lien tombe physiquement, la perte de porteuse
est instantanée ; si le voisin meurt en laissant le lien up, il faut attendre les 40 s du dead interval.
Baisser les timers à 1 s / 4 s aide mais charge le CPU et crée des faux positifs. La bonne réponse est
**BFD** : un protocole de détection dédié, souvent implémenté en matériel, avec un intervalle de 50 à
300 ms et un multiplicateur de 3, donc une détection en 150 à 900 ms sans toucher au processus OSPF.
Ensuite on ajuste le throttling SPF, qui attend 5 s par défaut avant le premier calcul.

**12. Qu'est-ce qu'une VRF et à quoi ça sert chez toi ?**
Une VRF est une table de routage indépendante à l'intérieur d'un même équipement : l'équivalent en couche 3
de ce que le VLAN fait en couche 2. Deux VRF peuvent utiliser exactement le même plan d'adressage sans se
voir, et rien ne fuit de l'une à l'autre sans route-leaking explicite. C'est la base du MPLS L3VPN des
opérateurs, et en datacenter ça sert à séparer management, production et stockage, ou à isoler des
environnements clients. Sous Linux c'est `ip link add vrf-x type vrf table 100` et `ip vrf exec` ; côté
Cisco on ajoute un Route Distinguisher qui rend le préfixe unique dans MP-BGP et des Route Targets qui
décident quelle VRF importe quelles routes.

---

## 16. Les 3 choses à retenir si tu ne retiens que ça

**1. La décision de routage est une cascade de trois filtres, dans cet ordre : préfixe le plus long,
puis distance administrative, puis métrique.** Le *longest prefix match* écrase tout le reste — un /26
appris par le protocole le moins fiable bat un /24 configuré à la main. La distance administrative ne
départage **que** des préfixes strictement identiques. Si tu sais dire ça sans hésiter, tu as la moitié
du module.

**2. Un vecteur de distance croit ce qu'on lui dit, un état de liens vérifie par lui-même.** RIP
répète des routes et peut boucler jusqu'à 16 ; OSPF inonde l'état de ses liens (LSA), tous les routeurs
d'une aire finissent avec **la même LSDB**, et chacun calcule Dijkstra depuis sa propre racine — même
carte, itinéraires différents. Le reste d'OSPF n'est que de l'ingénierie autour de ce principe : le DR
pour réduire les adjacences à 2n−3, les aires pour confiner l'inondation, le coût pour pondérer le graphe.

**3. En production, le routage casse presque toujours de la même façon : il manque la route de
retour.** Route dans un seul sens, peering non transitif, chemin asymétrique face à un pare-feu à états,
`rp_filter` strict. Le réflexe qui te fera gagner des heures : `ip route get` des deux côtés, puis
`tcpdump` **simultané** des deux côtés. Si le SYN arrive et que le SYN-ACK part sans jamais revenir, le
problème est sur le chemin de retour — et ce n'est jamais l'application.
