# R05 — BGP, systèmes autonomes, peering, MPLS

> **Ce que tu sauras faire à la fin**
> - Expliquer comment Internet se tient debout sans que personne n'en possède la carte : AS, IANA/RIR, numéros d'AS, et pourquoi le routage entre opérateurs n'est **pas** un problème technique mais un problème de **contrat**.
> - Dérouler une session BGP de bout en bout : les 6 états de la machine, les 5 messages, l'en-tête octet par octet, les timers, et lire un `show ip bgp summary` sans hésiter.
> - Appliquer **de mémoire et dans le bon ordre** les 10 critères de sélection du meilleur chemin, et prédire quelle route gagne dans un tableau de 4 candidates.
> - Distinguer eBGP et iBGP, comprendre pourquoi iBGP exige un maillage complet, et dimensionner une architecture à route reflectors.
> - Différencier peering et transit, expliquer l'économie d'un IXP, et poser les *local pref* d'une politique valley-free.
> - Reconnaître une fuite de routes d'un détournement, raconter 4 incidents réels, et dire exactement ce que RPKI protège — et ce qu'il ne protège pas.
> - Lire une pile de labels MPLS, suivre un paquet dans un LSP, et expliquer un VPN L3 MPLS avec RD, RT et double label.
> - Retrouver BGP là où tu vas vraiment le croiser : AWS Direct Connect, Calico/Cilium, MetalLB, l'anycast des load balancers.
>
> **Pourquoi ça compte dans ton poste**
> Tes pipelines ne restent pas dans un VPC. Ils traversent un Direct Connect, un peering inter-régions, un
> Transit Gateway, un cluster K8s dont le CNI parle BGP. Quand un job Spark voit son débit s'effondrer entre
> deux régions, la cause est souvent au-dessus de la couche 3 : un chemin BGP qui a basculé sur un transit
> à 180 ms au lieu d'un peering à 12 ms, ou un MTU rogné par une pile MPLS. Côté IA, les données de routage
> sont un **jeu de données massif et public** : les dumps MRT de RouteViews et RIPE RIS, les flux BMP,
> alimentent la détection d'anomalies et de détournements — c'est un des rares domaines où « réseau » et
> « modèle » se rencontrent pour de vrai. Enfin, une bonne moitié des questions d'entretien réseau d'un
> poste data/infra tape ici : BGP est le sujet qui sépare ceux qui ont lu la doc de ceux qui ont compris.
>
> **Prérequis** : `R01` (couches, encapsulation), `R02` (Ethernet, MAC, MTU), `R03` (IPv4, CIDR, longest prefix match), `R04` (table de routage, distance administrative, OSPF, IGP vs EGP).
> **Durée de lecture** : 75-90 min. Papier et crayon : la section 6 (sélection du meilleur chemin) se fait, elle ne se lit pas.

---

## 1. Le problème : personne n'a la carte d'Internet

Dans R04, OSPF construisait une carte complète du réseau : chaque routeur connaissait chaque lien, chaque
coût, et calculait Dijkstra sur le graphe entier. Ça marche parfaitement… jusqu'à quelques milliers de
routeurs.

Maintenant pose le problème à l'échelle d'Internet :

```
   Ce qu'il faudrait pour faire tourner OSPF sur Internet :

   ~ 75 000 organisations autonomes
   ~ 1 000 000 de préfixes IPv4 + ~ 200 000 IPv6
   ~ des millions de liens

   → Chaque routeur devrait stocker le graphe complet.
   → Chaque panne de lien à Jakarta déclencherait un Dijkstra à Paris.
   → Orange devrait publier sa topologie interne à Cogent.
   → Et il n'existe AUCUNE métrique commune : le « coût 10 » d'AT&T
     ne veut rien dire pour Free.

   Résultat : impossible techniquement, ET inacceptable commercialement.
```

Le vrai blocage n'est pas le calcul. C'est que **les opérateurs ne veulent pas coopérer**. Ils sont
concurrents, ils ont des contrats, des factures, des clients à protéger. Un protocole de routage entre
opérateurs doit donc permettre de dire « je peux atteindre ce préfixe » **sans** révéler comment, et de dire
« je ne veux pas router ton trafic vers lui » **sans** que ce soit une panne.

C'est exactement ce que fait BGP. Retiens la formule, elle explique tout le reste :

> **Un IGP (OSPF, IS-IS) cherche le chemin le plus court. BGP cherche le chemin le plus conforme à la
> politique.** Le plus court est un critère parmi dix, et il arrive en quatrième position.

Analogie : un IGP, c'est un GPS dans une ville que tu connais — il optimise les kilomètres. BGP, c'est le
transport international de marchandises : le trajet le plus court passe par un pays où tu n'as pas
d'accord douanier, donc tu passes par un autre, plus long, mais où tu as un contrat. Personne ne
t'expliquera l'intérieur des entrepôts par lesquels tu transites.

> ❓ **RETIENS ÇA** — Quelle est la différence de nature entre un IGP et BGP ?
> <details><summary>→ réponse</summary><br>Un <b>IGP</b> optimise une <b>métrique technique</b> (coût, bande passante) à l'intérieur d'une organisation qui se fait confiance à elle-même. <b>BGP</b> applique une <b>politique commerciale</b> entre organisations qui ne se font pas confiance ; la longueur du chemin n'est qu'un critère secondaire.</details>

---

## 2. Le système autonome : l'unité de souveraineté

### 2.1 Définition par le problème

Question : quelle est la plus petite chose qui puisse avoir une *politique de routage* ?

Pas un routeur (trop petit, il ne signe pas de contrats). Pas un pays (trop gros). C'est
**l'organisation qui contrôle un ensemble de routeurs sous une administration unique et une politique de
routage cohérente**. On l'appelle un **système autonome** (*Autonomous System*, AS).

Un AS, c'est : Orange, OVH, Google, ton université, une banque qui a deux fournisseurs Internet. Ce qui
en fait un AS, ce n'est pas la taille — c'est le fait de **décider soi-même** par où entre et sort son
trafic.

```
                        L'Internet, vu de haut

        AS 3356 (Lumen)                       AS 2914 (NTT)
              │  ╲                              ╱   │
              │   ╲──────── peering ───────────╱    │
          transit  ╲                          ╱   transit
              │     ╲                        ╱      │
              ▼      ▼                      ▼       ▼
        AS 3215 (Orange) ◄── peering ──► AS 16276 (OVH)
              │                                 │
          transit                           transit
              ▼                                 ▼
        AS 65001 (ta boîte)              AS 65002 (un client)

   Chaque bulle = une organisation, une politique, un contrat.
   Les flèches ne sont PAS des câbles : ce sont des RELATIONS.
```

### 2.2 Qui distribue les numéros ? IANA → RIR → LIR

Un AS a besoin d'un identifiant unique mondialement. La chaîne d'allocation est la même que pour les
adresses IP (R03) :

```
   IANA  (Internet Assigned Numbers Authority, sous l'ICANN)
     │   alloue des BLOCS aux 5 registres régionaux
     ▼
   RIR  ┌─ RIPE NCC   → Europe, Moyen-Orient, Asie centrale
        ├─ ARIN       → Amérique du Nord
        ├─ APNIC      → Asie-Pacifique
        ├─ LACNIC     → Amérique latine & Caraïbes
        └─ AFRINIC    → Afrique
     │   allouent aux LIR / utilisateurs finaux
     ▼
   LIR  = Local Internet Registry (souvent l'opérateur lui-même)
     │
     ▼
   TOI  = un numéro d'AS + un ou plusieurs préfixes IP
```

Pour obtenir un ASN public en Europe, il faut être membre du RIPE NCC ou passer par un LIR, et justifier
d'un **multihoming** (au moins deux connexions vers deux AS différents) ou d'une politique de routage
distincte. Un seul fournisseur = tu n'as pas besoin d'AS, ton fournisseur annonce ton préfixe pour toi.

### 2.3 Les numéros d'AS : 16 bits, puis 32

À l'origine, un ASN tient sur **16 bits** : 0 à 65 535. Réserve épuisée au cours des années 2010 (le
RIPE NCC n'alloue plus aucun ASN 16 bits depuis fin 2018). RFC 6793 a étendu le champ à **32 bits** :
0 à 4 294 967 295.

| Plage | Bits | Usage |
|---|---|---|
| `0` | 16 | Réservé, interdit d'annonce |
| `1 – 64 495` | 16 | **Publics**, alloués par les RIR |
| `64 496 – 64 511` | 16 | Documentation (RFC 5398) |
| `64 512 – 65 534` | 16 | **Privés** — usage interne, jamais sur Internet |
| `65 535` | 16 | Réservé |
| `23 456` | 16 | **AS_TRANS** : marqueur de compatibilité 16↔32 bits |
| `65 536 – 65 551` | 32 | Documentation |
| `65 552 – 4 199 999 999` | 32 | **Publics** |
| `4 200 000 000 – 4 294 967 294` | 32 | **Privés** 32 bits |
| `4 294 967 295` | 32 | Réservé |

Notation d'un ASN 32 bits : soit décimal plat (`AS131072`), soit **asdot** `x.y` (`AS2.0`) — la notation
plate est aujourd'hui la norme.

**AS_TRANS (23456)** mérite une explication, c'est un grand classique d'entretien. Quand un routeur qui ne
comprend que les ASN 16 bits reçoit une route dont le chemin contient un ASN 32 bits, il ne peut pas
l'encoder. Le routeur en amont remplace alors chaque ASN 32 bits par `23456` dans l'attribut AS_PATH
classique, et transporte le vrai chemin dans un attribut optionnel transitif `AS4_PATH`. Le routeur
16 bits voit un chemin avec des `23456` partout, mais la longueur est préservée — donc la sélection reste
correcte, et le routeur 32 bits en sortie reconstruit le vrai chemin.

> ❓ **RETIENS ÇA** — À quoi sert l'AS 23456 ?
> <details><summary>→ réponse</summary><br>C'est <b>AS_TRANS</b> : le substitut inséré dans l'AS_PATH à la place d'un ASN 32 bits, pour qu'un routeur ne comprenant que 16 bits puisse quand même traiter la route. Le vrai chemin voyage en parallèle dans l'attribut <code>AS4_PATH</code>.</details>

> ⚠️ **PIÈGE** — Un ASN privé (64512-65534) n'est pas « un AS de test ». C'est un ASN parfaitement
> fonctionnel, très utilisé : AWS Direct Connect, les CNI Kubernetes, les MetalLB, les data centers
> internes tournent massivement sur des ASN privés. Ce qui est interdit, c'est de le laisser **fuiter dans
> l'AS_PATH d'une annonce Internet** — les opérateurs sérieux les filtrent (`remove-private-as`).

> 🧠 **MÉMO** — Les plages privées d'ASN et d'IP se ressemblent volontairement : « **64 512** » est aux
> ASN ce que « **10.0.0.0/8** » est aux IP. Astuce de mémorisation : 65 534 = 65 536 − 2, exactement comme
> le nombre d'hôtes d'un /16. Le monde du réseau réutilise sans arrêt les mêmes bornes binaires.

---

## 3. BGP : le protocole

### 3.1 Path vector : le vecteur qui garde la trace

BGP n'est ni un vecteur de distance (RIP) ni un état de liens (OSPF). C'est un **vecteur de chemin**
(*path vector*) : chaque annonce transporte **la liste complète des AS traversés**.

Cette liste sert à deux choses, et la deuxième est la vraie raison d'être :

1. **Mesurer** la longueur du chemin (nombre d'AS, pas nombre de routeurs).
2. **Détecter les boucles de façon absolue** : si un routeur reçoit une annonce dont l'AS_PATH contient
   déjà son propre numéro d'AS, il la jette. Point. Pas de compteur d'infini, pas de split horizon
   fragile, pas de temps de convergence : la boucle est structurellement impossible.

```
   Propagation d'un préfixe et construction de l'AS_PATH

   AS 65010                AS 200            AS 300           AS 400
   ┌────────┐  eBGP    ┌────────┐  eBGP  ┌────────┐  eBGP ┌────────┐
   │ origine│─────────►│        │───────►│        │──────►│        │
   │203.0.113.0/24     │        │        │        │       │        │
   └────────┘          └────────┘        └────────┘       └────────┘
   AS_PATH:              65010          200 65010      300 200 65010
   (vide chez soi)

   Si AS 200 recevait ensuite « 203.0.113.0/24, AS_PATH = 300 200 65010 »
   → il voit son propre 200 dans le chemin → REJET IMMÉDIAT.
```

Chaque AS **préfixe** (prepend) son propre numéro à gauche quand il annonce en eBGP. Le chemin se lit donc
de droite à gauche dans le temps : le plus à droite est l'origine.

> ❓ **RETIENS ÇA** — Comment BGP détecte-t-il les boucles, et pourquoi est-ce supérieur à RIP ?
> <details><summary>→ réponse</summary><br>Un routeur rejette toute annonce dont l'<b>AS_PATH contient son propre ASN</b>. C'est une détection <b>déterministe et immédiate</b>, contrairement au « count to infinity » de RIP qui converge lentement et par approximation.</details>

### 3.2 La session : TCP 179, et ce que ça implique

BGP tourne **sur TCP, port 179**. C'est le seul protocole de routage majeur à faire ça (OSPF est
directement sur IP protocole 89, EIGRP 88, RIP sur UDP 520).

Conséquences directes, toutes examinables :

- **Fiabilité déléguée** : pas de retransmission, pas de séquencement, pas de fragmentation à gérer dans
  BGP — TCP s'en charge. C'est pourquoi BGP n'envoie **jamais** de mise à jour périodique complète : une
  route annoncée reste valable jusqu'à retrait explicite. Le trafic BGP en régime établi est quasi nul.
- **Voisins configurés à la main** : pas de découverte par multicast. Chaque session est déclarée des deux
  côtés avec l'IP et l'ASN attendus du pair. C'est volontaire — on ne veut pas d'un voisinage
  accidentel avec un concurrent.
- **Session unidirectionnelle à établir, bidirectionnelle en usage** : les deux côtés tentent de se
  connecter ; s'il y a collision de connexions, celui qui a le **BGP Identifier le plus élevé** garde sa
  connexion, l'autre est fermée.
- **Sécurité par TCP** : authentification MD5 de la session (RFC 2385, option TCP kind 19), aujourd'hui
  complétée par TCP-AO (RFC 5925). Et **GTSM** (RFC 5082, *ttl-security*) : on envoie avec TTL = 255 et on
  n'accepte que TTL ≥ 254, ce qui rend un spoof depuis Internet impossible sans être physiquement adjacent.

### 3.3 L'en-tête : 19 octets, toujours

Tout message BGP commence par le même en-tête de **19 octets** :

```
    0                   1                   2                   3
    0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
   +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
   |                                                               |
   |                    MARKER  (16 octets)                        |
   |               tous les bits à 1  (0xFF × 16)                  |
   |                                                               |
   +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
   |         LENGTH  (2 o)         |    TYPE (1 o) |
   +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+

   LENGTH : longueur TOTALE du message, en-tête compris.
            minimum 19, maximum 4096 (RFC 4271)
            → 65535 si les deux pairs négocient RFC 8654

   TYPE :  1 = OPEN        2 = UPDATE      3 = NOTIFICATION
           4 = KEEPALIVE   5 = ROUTE-REFRESH (RFC 2918)
```

Le MARKER à 1 est un vestige : il servait à la synchronisation et à l'authentification dans BGP-3. Il est
aujourd'hui purement décoratif — mais il reste, et il est vérifié.

> 🧠 **MÉMO** — **19 = 16 + 2 + 1**. Seize octets de marqueur, deux de longueur, un de type. Et
> **4096** est le plafond historique d'un message : le même 4 Ki qu'une page mémoire.

### 3.4 Les 5 messages

| # | Message | Taille | Rôle |
|---|---|---|---|
| 1 | **OPEN** | ≥ 29 o | Ouvre la session : version, ASN, hold time, router-ID, capacités |
| 2 | **UPDATE** | ≥ 23 o | Annonce et/ou retire des préfixes, porte les attributs |
| 3 | **NOTIFICATION** | ≥ 21 o | Signale une erreur **et ferme la session** |
| 4 | **KEEPALIVE** | 19 o | En-tête seul, garde la session vivante |
| 5 | **ROUTE-REFRESH** | 23 o | « Renvoie-moi tout », sans casser la session |

**Le message OPEN**, champ par champ (10 octets après l'en-tête, plus les options) :

```
   +---------------+
   | Version   1 o |  toujours 4 (BGP-4 depuis 1994)
   +---------------+
   | My AS     2 o |  ASN de l'émetteur — 23456 si ASN 32 bits
   +---------------+
   | Hold Time 2 o |  proposition ; défaut 90 s ; 0 = pas de keepalive
   +---------------+
   | BGP Id    4 o |  router-ID, 32 bits, unique — souvent une loopback
   +---------------+
   | OptLen    1 o |  longueur des paramètres optionnels
   +---------------+
   | Optional Parameters (capacités, RFC 5492) ...
   +---------------+
```

Le **Hold Time négocié est le minimum des deux propositions**. Le keepalive est envoyé à **1/3 du hold
time** — d'où la paire canonique **hold 90 s / keepalive 30 s**. Si aucun message (KEEPALIVE ou UPDATE)
n'arrive pendant le hold time, la session tombe : NOTIFICATION code 4 (*Hold Timer Expired*).

**Les capacités** échangées dans l'OPEN (paramètre optionnel type 2) sont ce qui rend BGP extensible :

| Code | Capacité | Sert à |
|---|---|---|
| 1 | Multiprotocol (MP-BGP, RFC 4760) | Transporter autre chose que de l'IPv4 unicast |
| 2 | Route Refresh | Redemander la table sans reset |
| 64 | Graceful Restart | Garder la FIB pendant le redémarrage du process BGP |
| 65 | 4-octet AS (RFC 6793) | Parler ASN 32 bits nativement |
| 69 | ADD-PATH (RFC 7911) | Annoncer plusieurs chemins pour un même préfixe |

> ⚠️ **PIÈGE** — Un **NOTIFICATION ferme toujours la session**. Il n'existe pas de « notification
> d'avertissement » en BGP. Si tu vois des NOTIFICATION dans les logs, tu vois des sessions qui tombent, et
> chaque chute déclenche un retrait massif de routes chez le voisin.

**Codes d'erreur NOTIFICATION** (à reconnaître dans les logs) :

| Code | Signification | Sous-codes utiles |
|---|---|---|
| 1 | Message Header Error | 2 = mauvaise longueur, 3 = type inconnu |
| 2 | OPEN Message Error | 1 = version, **2 = Bad Peer AS**, 3 = Bad BGP Identifier, 6 = hold time inacceptable |
| 3 | UPDATE Message Error | attribut malformé, AS_PATH invalide |
| 4 | **Hold Timer Expired** | — (le classique : le lien est mort) |
| 5 | FSM Error | message reçu dans un état illégal |
| 6 | **Cease** | **1 = Maximum Prefixes atteint**, 2 = shutdown admin, 4 = reset admin |

Le duo à mémoriser : **`Bad Peer AS`** = tu t'es trompé d'ASN dans la config. **`Cease / Maximum Prefixes`**
= ton voisin t'a envoyé plus de préfixes que la limite fixée, et c'est *exactement le mécanisme qui te
protège d'une fuite de routes*.

### 3.5 La machine à états : 6 états

```
              ┌────────┐
      ┌──────►│  IDLE  │◄──────── toute erreur revient ici
      │       └───┬────┘          (ConnectRetry ≈ 120 s, backoff)
      │           │ start
      │           ▼
      │       ┌─────────┐   TCP échoue    ┌────────┐
      │       │ CONNECT │────────────────►│ ACTIVE │
      │       └────┬────┘◄────────────────└───┬────┘
      │            │ TCP OK                   │ retente TCP
      │            ▼                          │
      │       ┌──────────┐◄──────────────────-┘
      │       │ OPENSENT │   envoi de l'OPEN, attente de l'OPEN pair
      │       └────┬─────┘
      │            │ OPEN reçu et valide → répond KEEPALIVE
      │            ▼
      │      ┌─────────────┐
      └──────│ OPENCONFIRM │  attend le KEEPALIVE du pair
             └──────┬──────┘
                    │ KEEPALIVE reçu
                    ▼
             ┌──────────────┐
             │ ESTABLISHED  │  ← les UPDATE circulent ici, et ici seulement
             └──────────────┘
```

Le diagnostic pratique tient en trois lignes :

- Bloqué en **Idle** → la config locale est fausse, ou une route vers le voisin manque, ou le voisin est
  administrativement éteint.
- Bloqué en **Active** → **c'est le piège de tous les débutants**. « Active » ne veut pas dire « ça
  marche » ; ça veut dire « je tente une connexion TCP et elle échoue ». ACL, pare-feu, mauvaise IP,
  routage absent vers le voisin.
- Bloqué en **OpenSent / OpenConfirm** → TCP passe, mais les paramètres BGP sont incompatibles : ASN
  attendu ≠ ASN reçu, router-ID identique des deux côtés, hold time incohérent, MD5 différent.

> ⚠️ **PIÈGE** — L'état **`Active` est un état d'échec.** Dans un `show ip bgp summary`, la colonne
> `State/PfxRcd` affiche soit un **nombre** (session établie, nombre de préfixes reçus), soit un **nom
> d'état** (session non établie). Un nombre = bon signe. `Active` ou `Idle` = mauvais signe.

> ❓ **RETIENS ÇA** — Dans quel état, et dans lui seul, les messages UPDATE circulent-ils ?
> <details><summary>→ réponse</summary><br><b>ESTABLISHED</b>. Dans tous les autres états, aucune route n'est échangée.</details>

> 🧠 **MÉMO** — Les 6 états dans l'ordre : « **I**l **C**onduit **A**vec **O**bstination, **O**bstinément
> **É**tabli » → **I**dle, **C**onnect, **A**ctive, **O**penSent, **O**penConfirm, **E**stablished.

### 3.6 Le message UPDATE

C'est le seul message qui transporte de l'information de routage. Sa structure :

```
   +--------------------------------------+
   | Withdrawn Routes Length      (2 o)   |  0 si rien à retirer
   +--------------------------------------+
   | Withdrawn Routes             (var.)  |  préfixes RETIRÉS
   +--------------------------------------+
   | Total Path Attribute Length  (2 o)   |  0 s'il n'y a que des retraits
   +--------------------------------------+
   | Path Attributes              (var.)  |  ORIGIN, AS_PATH, NEXT_HOP, ...
   +--------------------------------------+
   | NLRI                         (var.)  |  préfixes ANNONCÉS
   +--------------------------------------+

   NLRI = Network Layer Reachability Information
        = liste de (longueur du préfixe sur 1 octet, préfixe tronqué)
          10.0.0.0/8   →  08 0A          (2 octets !)
          192.0.2.0/24 →  18 C0 00 02    (4 octets)
```

Deux points qui comptent :

1. **Un seul jeu d'attributs par UPDATE**, mais **plusieurs préfixes** dans le NLRI. Tous les préfixes
   d'un UPDATE partagent donc exactement le même AS_PATH, le même NEXT_HOP, etc. C'est ce qui rend BGP
   efficace : annoncer 5 000 préfixes qui partagent un chemin tient dans quelques messages.
2. **L'encodage NLRI est compact** : seuls les octets significatifs du préfixe sont transmis. Un `/8` tient
   sur 2 octets au lieu de 5.

> ❓ **RETIENS ÇA** — Combien de jeux d'attributs peut porter un message UPDATE, et combien de préfixes ?
> <details><summary>→ réponse</summary><br><b>Un seul</b> jeu d'attributs, mais <b>autant de préfixes qu'on veut</b> dans le NLRI. Tous partagent ces attributs. Les retraits, eux, n'ont pas d'attributs du tout.</details>

---

## 4. eBGP et iBGP : le même protocole, deux comportements

### 4.1 Le problème

Tu as reçu une route d'un opérateur voisin sur ton routeur de bordure de Paris. Ton routeur de Marseille
doit la connaître aussi. Tu ne vas pas la redistribuer dans OSPF — un million de routes ferait exploser ton
IGP. Il faut donc que BGP parle **aussi à l'intérieur** de ton AS.

Même protocole, même port 179, même messages. Mais dès que les deux pairs ont **le même ASN**, BGP change
plusieurs comportements. On appelle ça iBGP (interne) par opposition à eBGP (externe).

### 4.2 Le tableau des différences — à connaître par cœur

| | **eBGP** | **iBGP** |
|---|---|---|
| ASN des deux pairs | **différents** | **identiques** |
| Adjacence physique | requise (TTL = 1 par défaut) | **non** : n'importe où dans l'AS |
| Source de session typique | IP de l'interface directe | **loopback** (`update-source`) |
| AS_PATH | **son ASN est prepend** | **inchangé** |
| NEXT_HOP en sortie | réécrit par soi-même | **inchangé** (d'où `next-hop-self`) |
| LOCAL_PREF | **non transmis** | transmis |
| MED | transmis (1 saut d'AS) | transmis en interne |
| Distance administrative (Cisco) | **20** | **200** |
| Re-annonce d'une route apprise… | à tout le monde | **jamais à un autre pair iBGP** |
| Nécessite un IGP sous-jacent | non | **oui**, pour atteindre les loopbacks |

### 4.3 La règle qui explique tout : le split horizon iBGP

> **Une route apprise d'un pair iBGP n'est JAMAIS ré-annoncée à un autre pair iBGP.**

Pourquoi ? Parce qu'à l'intérieur de l'AS, l'AS_PATH ne change pas — il ne peut donc pas détecter de
boucle. Sans une règle de propagation stricte, une route tournerait indéfiniment entre routeurs internes.

La conséquence est lourde : pour que tous les routeurs BGP de ton AS connaissent toutes les routes, il faut
un **maillage complet** (*full mesh*) de sessions iBGP.

```
   Full mesh iBGP : n routeurs → n(n−1)/2 sessions

        R1────R2              n = 4  →  6 sessions
        │╲   ╱│               n = 10 →  45 sessions
        │ ╲ ╱ │               n = 20 →  190 sessions
        │  ╳  │               n = 50 →  1 225 sessions  ← ingérable
        │ ╱ ╲ │
        R3────R4

   Chaque session = de la config, de la RAM, une copie de la table.
```

À 20 routeurs c'est déjà pénible. À 100, impossible. D'où les **route reflectors** (§8).

> ❓ **RETIENS ÇA** — Pourquoi le full mesh iBGP est-il obligatoire ?
> <details><summary>→ réponse</summary><br>Parce qu'une route apprise en iBGP n'est jamais ré-annoncée à un autre pair iBGP (l'AS_PATH ne changeant pas à l'intérieur de l'AS, il ne protégerait pas des boucles). Chaque routeur doit donc entendre chaque route <b>directement</b> de son émetteur.</details>

### 4.4 Le piège du NEXT_HOP

C'est **la** panne iBGP classique. Regarde :

```
   AS 200                          │  AS 100 (le tien)
                                   │
   ┌─────┐  eBGP   ┌──────┐  iBGP  │  ┌──────┐
   │  X  │────────►│  R1  │────────┼─►│  R2  │
   └─────┘10.1.1.1 └──────┘        │  └──────┘
     .1      .2                    │
                                   │
   R1 apprend 203.0.113.0/24, NEXT_HOP = 10.1.1.1  (l'IP de X)
   R1 transmet à R2 en iBGP : NEXT_HOP reste 10.1.1.1

   R2 : « pour atteindre 203.0.113.0/24, je dois joindre 10.1.1.1 »
        → mais 10.1.1.1 est le lien externe, pas dans mon IGP !
        → NEXT_HOP INACCESSIBLE → route marquée invalide,
          jamais installée, jamais annoncée.
```

La route apparaît dans `show ip bgp` **sans l'astérisque de validité**. Deux corrections possibles :

1. **`neighbor R2 next-hop-self`** sur R1 : R1 réécrit le NEXT_HOP avec sa propre adresse (sa loopback),
   que R2 sait joindre via l'IGP. **C'est la solution normale, à faire par réflexe.**
2. Injecter le réseau du lien externe dans l'IGP — possible, mais on met du préfixe externe dans son IGP,
   ce qui est sale.

> ⚠️ **PIÈGE** — La règle générale : **BGP n'installe une route que si son NEXT_HOP est joignable par
> une autre source** (IGP, statique, connecté). C'est la toute première étape de la sélection, avant même
> le weight. Une route BGP « présente mais pas utilisée » a 80 % de chances d'être un problème de
> next-hop.

> 🧠 **MÉMO** — **eBGP réécrit, iBGP conserve.** Le NEXT_HOP change quand on franchit une frontière d'AS,
> et seulement là. Corollaire : `next-hop-self` se configure **sur le routeur de bordure, vers ses pairs
> internes** — jamais l'inverse.

---

## 5. Les attributs : la matière première de la décision

Chaque route BGP arrive accompagnée d'attributs. Ils sont encodés en TLV avec un octet de flags :

```
   +-------+-------+-------+-------+
   | Flags | Type  | Length| Value |
   | 1 o   | 1 o   |1 ou 2 |  ...  |
   +-------+-------+-------+-------+

   Octet de FLAGS, bit par bit :
   ┌───┬───┬───┬───┬───┬───┬───┬───┐
   │ O │ T │ P │ E │ 0 │ 0 │ 0 │ 0 │
   └───┴───┴───┴───┴───┴───┴───┴───┘
     │   │   │   └── 0x10 Extended Length : Length sur 2 octets
     │   │   └────── 0x20 Partial : un routeur du chemin ne l'a pas compris
     │   └────────── 0x40 Transitive : à transmettre même si non compris
     └────────────── 0x80 Optional : 0 = well-known, 1 = optionnel
```

**Les quatre catégories** — c'est l'ossature, apprends-la avant les attributs eux-mêmes :

| Catégorie | Doit être compris ? | Doit être présent ? | Retransmis si non compris ? |
|---|---|---|---|
| **Well-known mandatory** | oui | **oui, toujours** | — |
| **Well-known discretionary** | oui | non | — |
| **Optional transitive** | non | non | **oui**, avec le bit Partial |
| **Optional non-transitive** | non | non | **non**, silencieusement jeté |

### 5.1 La table des attributs

| Type | Nom | Catégorie | Portée | Notes |
|---|---|---|---|---|
| **1** | **ORIGIN** | WK mandatory | globale | 0 = IGP (`i`), 1 = EGP (`e`), 2 = INCOMPLETE (`?`) |
| **2** | **AS_PATH** | WK mandatory | globale | segments : AS_SEQUENCE (2), AS_SET (1) |
| **3** | **NEXT_HOP** | WK mandatory | 1 saut d'AS | réécrit en eBGP |
| **4** | **MED** | Optional non-trans. | **1 AS voisin** | plus petit = mieux ; défaut 0 |
| **5** | **LOCAL_PREF** | WK discretionary | **AS local** | plus grand = mieux ; défaut **100** |
| **6** | ATOMIC_AGGREGATE | WK discretionary | globale | « j'ai agrégé, de l'info a été perdue » |
| **7** | AGGREGATOR | Optional trans. | globale | qui a agrégé (ASN + router-ID) |
| **8** | **COMMUNITY** | Optional trans. | globale | 32 bits, RFC 1997 |
| **9** | ORIGINATOR_ID | Optional non-trans. | AS local | anti-boucle route reflector |
| **10** | CLUSTER_LIST | Optional non-trans. | AS local | anti-boucle route reflector |
| **14** | MP_REACH_NLRI | Optional non-trans. | — | IPv6, VPNv4, EVPN (RFC 4760) |
| **15** | MP_UNREACH_NLRI | Optional non-trans. | — | retraits multiprotocoles |
| **16** | Extended Communities | Optional trans. | globale | 8 octets — **Route Target MPLS** |
| **32** | Large Communities | Optional trans. | globale | 12 octets — **pour ASN 32 bits** |

**WEIGHT** n'est PAS dans cette table : ce n'est **pas un attribut BGP**. C'est une valeur **propriétaire
Cisco**, purement locale au routeur, jamais transmise nulle part. Défaut : **0** pour une route apprise,
**32 768** pour une route originée localement. Plage 0 – 65 535.

> ⚠️ **PIÈGE** — Trois confusions à ne jamais faire :
> - **WEIGHT** : local au **routeur**, jamais transmis, Cisco uniquement.
> - **LOCAL_PREF** : local à l'**AS**, transmis en iBGP, jamais en eBGP.
> - **MED** : franchit **une** frontière d'AS, et n'est comparé qu'entre routes venant du **même AS voisin**.
>
> Et le sens : **LOCAL_PREF le plus GRAND gagne, MED le plus PETIT gagne.**

> 🧠 **MÉMO** — « **Local pref = je sors par là** ; **MED = entre par là**. » LOCAL_PREF contrôle le trafic
> **sortant** (c'est ta décision, tu l'imposes chez toi). MED est une **suggestion** faite au voisin pour
> influencer le trafic **entrant** — et il a parfaitement le droit de l'ignorer.

### 5.2 ORIGIN : la petite lettre qui traîne

Dans `show ip bgp`, chaque route se termine par `i`, `e` ou `?`.

- `i` = **IGP** : le préfixe a été injecté par une commande `network` → l'origine est propre.
- `e` = **EGP** : vestige du protocole EGP, tu ne le verras jamais.
- `?` = **INCOMPLETE** : le préfixe a été **redistribué** depuis un IGP ou du statique → l'origine est
  moins fiable.

Ordre de préférence : **IGP (0) < EGP (1) < INCOMPLETE (2)**, et le **plus petit gagne**. En pratique,
c'est un départage rarement atteint — mais il tombe en entretien.

### 5.3 AS_PATH : plus qu'un compteur

L'AS_PATH est une liste de **segments**, chacun typé :

| Type | Nom | Compte pour |
|---|---|---|
| 1 | AS_SET | **1**, quel que soit le nombre d'AS dedans |
| 2 | AS_SEQUENCE | son nombre d'éléments |
| 3 | AS_CONFED_SEQUENCE | **0** (invisible hors confédération) |
| 4 | AS_CONFED_SET | **0** |

L'AS_SET apparaît lors d'une agrégation : on résume 4 préfixes venant de 4 AS différents, l'agrégat porte
`{100 200 300 400}` en AS_SET — et cet ensemble ne compte que pour **1** dans la longueur.

Manipulation de traffic engineering la plus courante : **l'AS-path prepending**. Tu annonces ton préfixe
deux fois, une fois par fournisseur, et sur celui que tu veux voir moins utilisé tu ajoutes ton propre ASN
2 ou 3 fois :

```
   Ton préfixe 198.51.100.0/24, AS 65001, deux fournisseurs

   vers FAI-A :  AS_PATH = 65001                    ← chemin court
   vers FAI-B :  AS_PATH = 65001 65001 65001        ← prepend ×3

   Le reste du monde compare : 1 AS contre 3 AS
   → l'entrant privilégie FAI-A.
```

> ⚠️ **PIÈGE** — Le prepending est **faible et imprécis**. Il n'agit qu'au critère n°4, donc n'importe quel
> AS distant ayant posé un LOCAL_PREF (critère n°2) l'écrase totalement. Prepender au-delà de 3 ou 4 ne
> sert quasiment à rien, et certains opérateurs filtrent les chemins trop prependés.

---

## 6. La sélection du meilleur chemin — le cœur du module

BGP peut connaître 5, 10, 30 chemins pour un même préfixe. Il en installe **un seul** dans la table de
routage (sauf multipath explicite), et n'annonce **que celui-là** à ses voisins.

L'ordre des critères est fixe, séquentiel, et s'arrête au premier qui départage.

### 6.1 L'algorithme

```
  ┌──────────────────────────────────────────────────────────────┐
  │ 0. NEXT_HOP joignable ?          sinon → route ÉLIMINÉE      │
  ├──────────────────────────────────────────────────────────────┤
  │ 1. WEIGHT le plus GRAND          local au routeur, Cisco     │
  │                                  défaut 0 / 32768 si local   │
  ├──────────────────────────────────────────────────────────────┤
  │ 2. LOCAL_PREF le plus GRAND      défaut 100, portée = l'AS   │
  ├──────────────────────────────────────────────────────────────┤
  │ 3. Route ORIGINÉE LOCALEMENT     network / aggregate /       │
  │    (préférée)                     redistribute sur CE routeur│
  ├──────────────────────────────────────────────────────────────┤
  │ 4. AS_PATH le plus COURT         AS_SET compte pour 1        │
  ├──────────────────────────────────────────────────────────────┤
  │ 5. ORIGIN le plus BAS            IGP(0) < EGP(1) < INC.(2)   │
  ├──────────────────────────────────────────────────────────────┤
  │ 6. MED le plus PETIT             ⚠ seulement entre routes    │
  │                                   du MÊME AS voisin          │
  ├──────────────────────────────────────────────────────────────┤
  │ 7. eBGP préféré à iBGP           un externe bat un interne   │
  ├──────────────────────────────────────────────────────────────┤
  │ 8. Métrique IGP vers le NEXT_HOP la plus BASSE               │
  │    ("hot potato routing" : sors au plus vite de chez toi)    │
  ├──────────────────────────────────────────────────────────────┤
  │ 9. Départages finaux :                                       │
  │    a) chemin eBGP le plus ANCIEN (stabilité)                 │
  │    b) plus petit ROUTER-ID du voisin                         │
  │    c) plus courte CLUSTER_LIST                               │
  │    d) plus petite IP de voisin                               │
  └──────────────────────────────────────────────────────────────┘
```

> 🧠 **MÉMO** — Les initiales : **N W L O A O M E I R**
> **N**ext-hop · **W**eight · **L**ocal pref · **O**riginée localement · **A**S-path · **O**rigin ·
> **M**ED · **E**xterne (eBGP) · **I**GP metric · **R**outer-ID
>
> Phrase absurde à retenir : « **N**os **W**agons **L**ivrent **O**nze **A**nanas **O**range, **M**ais
> **E**lle **I**gnore **R**obert. »
>
> Et pour le sens : les **deux premiers** (weight, local pref) veulent le **plus GRAND**. Tous les autres
> chiffres veulent le **plus PETIT**. Retiens : *« les deux préférences montent, tout le reste descend. »*

> ❓ **RETIENS ÇA** — Quel attribut est comparé en 2ᵉ, et dans quel sens ?
> <details><summary>→ réponse</summary><br><b>LOCAL_PREF</b>, et c'est la <b>plus grande</b> qui gagne. Défaut 100. Portée : l'AS local uniquement.</details>

> ❓ **RETIENS ÇA** — À quelle position exacte l'AS_PATH intervient-il ?
> <details><summary>→ réponse</summary><br>En <b>4ᵉ</b>, après weight, local pref et « route originée localement ». C'est pour ça que le prepending est un outil faible.</details>

> ❓ **RETIENS ÇA** — Quelle est la restriction majeure sur la comparaison du MED ?
> <details><summary>→ réponse</summary><br>Par défaut, le MED n'est comparé qu'entre <b>chemins reçus du même AS voisin</b>. Pour le comparer entre AS différents il faut <code>bgp always-compare-med</code> — ce qui est risqué et peut créer des oscillations.</details>

### 6.2 Exercice corrigé n°1 — qui gagne ?

Ton routeur R1 (AS 65100) connaît 4 chemins vers `198.51.100.0/24` :

| # | Voisin | Type | Weight | Local pref | AS_PATH | Origin | MED | Métrique IGP vers NH |
|---|---|---|---|---|---|---|---|---|
| A | 10.0.0.1 | eBGP | 0 | 100 | 200 300 400 | i | 50 | 10 |
| B | 10.0.0.2 | eBGP | 0 | 150 | 200 300 400 500 600 | i | 0 | 20 |
| C | 192.168.0.3 | iBGP | 0 | 150 | 200 300 | ? | 0 | 5 |
| D | 192.168.0.4 | iBGP | 0 | 150 | 200 300 | i | 30 | 30 |

**Déroulé, critère par critère :**

- **0. NEXT_HOP joignable** — on suppose que oui pour les 4. Aucune élimination.
- **1. Weight** — tous à 0. Égalité, on continue.
- **2. Local pref** — A = 100, B/C/D = 150. **A est éliminée.** Il reste B, C, D.
  *Note : A avait le chemin le plus court et le meilleur IGP. Ça ne sert à rien : le local pref passe
  avant. C'est la leçon n°1 de BGP.*
- **3. Originée localement** — aucune ne l'est. Égalité.
- **4. AS_PATH** — B = 5 AS, C = 2 AS, D = 2 AS. **B est éliminée.** Il reste C et D.
- **5. ORIGIN** — C = `?` (INCOMPLETE = 2), D = `i` (IGP = 0). Le plus petit gagne → **C est éliminée.**

**Réponse : D gagne.** Le critère décisif est l'**ORIGIN**, atteint en 5ᵉ position.

Remarque importante : on n'a **jamais** regardé le MED, ni le type eBGP/iBGP, ni la métrique IGP. Dès qu'un
critère départage, l'algorithme s'arrête. Et note que la route gagnante, D, est la **pire** sur la métrique
IGP (30). C'est parfaitement normal : BGP n'optimise pas la distance.

### 6.3 Exercice corrigé n°2 — le MED qui ne s'applique pas

R1 (AS 65100) connaît 2 chemins vers `203.0.113.0/24` :

| # | Reçu de | AS_PATH | MED |
|---|---|---|---|
| X | AS 200 | `200 900` | 10 |
| Y | AS 300 | `300 900` | 5 |

Question : Y gagne-t-elle parce que son MED est plus petit ?

**Non.** Les deux chemins viennent d'**AS voisins différents** (200 et 300). Par défaut, le MED n'est
comparé **qu'entre chemins reçus du même AS voisin**. Le critère 6 est donc **sauté**.

On passe au critère 7 (eBGP vs iBGP) : les deux sont eBGP, égalité. Puis 8 (métrique IGP vers le
next-hop), puis les départages : chemin eBGP le plus ancien, puis plus petit router-ID du voisin.

**Réponse : le MED n'entre pas en jeu ; c'est la stabilité (chemin le plus ancien) ou le router-ID qui
tranche.** C'est *la* question piège classique en entretien.

### 6.4 Exercice corrigé n°3 — hot potato vs cold potato

Ton AS a deux sorties vers le même contenu, à Paris et à Marseille. Un utilisateur à Lille demande la
donnée.

```
   Lille ─── IGP coût 10 ──► PE-Paris ──eBGP──► contenu
     │
     └────── IGP coût 80 ──► PE-Marseille ──eBGP──► même contenu

   Tout est égal jusqu'au critère 8 (métrique IGP vers le NEXT_HOP).
   → 10 < 80 → sortie par PARIS.
```

C'est le **hot potato routing** (« patate chaude ») : je me débarrasse du trafic le plus vite possible en
le confiant à un autre AS. C'est le comportement **par défaut**, et c'est économiquement rationnel — porter
du trafic coûte.

Le **cold potato** est l'inverse : je garde le trafic sur mon propre réseau le plus longtemps possible pour
maîtriser la qualité, et je le remets au plus près de la destination. On l'obtient en forçant le
LOCAL_PREF (critère 2), qui écrase la métrique IGP.

**Ce que ça implique pour toi :** l'asymétrie de routage n'est pas une anomalie, c'est la règle. Un paquet
aller peut sortir par Paris et le retour rentrer par Marseille, parce que ton AS et l'AS distant appliquent
chacun *leur* hot potato. D'où deux conséquences très concrètes en data engineering :

- **Les mesures de latence aller-retour ne se décomposent pas en deux moitiés égales.** Un RTT de 60 ms
  peut être 15 ms à l'aller et 45 ms au retour.
- **Les pare-feu à états et les NAT cassent** si les deux sens ne passent pas par le même équipement. C'est
  la panne « le handshake TCP passe, le transfert gèle ».

---

## 7. Les communities : les étiquettes qui pilotent la politique

### 7.1 Le problème

Tu es un client d'un gros opérateur. Tu veux dire : « ce préfixe-là, ne l'annonce pas à Cogent », ou
« baisse mon local pref chez toi pour ce préfixe, c'est ma route de secours ». Tu ne peux pas appeler
l'opérateur à chaque changement, et il ne va pas te configurer une route-map sur mesure.

Solution : il publie une **grille d'étiquettes**, et tu tags tes annonces. C'est une **community**.

### 7.2 Format

Une community est un **entier de 32 bits**, noté conventionnellement `ASN:valeur` (16 bits : 16 bits).
`65001:100` = ASN 65001, valeur 100. Une route peut porter **plusieurs** communities.

Trois familles :

| Type | Taille | RFC | Usage |
|---|---|---|---|
| **Standard** | 4 o (32 b) | 1997 | politique classique, `ASN16:valeur16` |
| **Extended** | 8 o (64 b) | 4360 | typée — **Route Target** des VPN MPLS |
| **Large** | 12 o (96 b) | 8092 | `ASN32:valeur32:valeur32` — indispensable avec les ASN 32 bits |

Les **Large Communities** existent pour une raison simple et parlante : avec un ASN 32 bits, tu remplis
déjà toute la partie gauche d'une community standard, il ne reste rien pour la valeur. La large community
donne trois champs de 32 bits : `AS global : fonction : paramètre`.

### 7.3 Les well-known communities

| Nom | Valeur | Effet |
|---|---|---|
| **NO_EXPORT** | `0xFFFFFF01` | Ne pas annoncer **hors de l'AS** (ni de la confédération) |
| **NO_ADVERTISE** | `0xFFFFFF02` | Ne l'annoncer **à personne**, même pas en interne |
| **NO_EXPORT_SUBCONFED** | `0xFFFFFF03` | Ne pas sortir du **sous-AS** de confédération |
| **GRACEFUL_SHUTDOWN** | `65535:0` (RFC 8326) | « je vais couper cette session, dévie ton trafic maintenant » |
| **BLACKHOLE** | `65535:666` (RFC 7999) | « jette ce trafic » — anti-DDoS |

`65535:666` est celle que tu utiliseras vraiment un jour : sous attaque DDoS, tu annonces le /32 attaqué
à ton opérateur avec cette community, et il le jette **chez lui**, avant que ton lien ne sature. Tu
sacrifies une IP pour sauver le reste.

> ❓ **RETIENS ÇA** — Quelle est la différence entre NO_EXPORT et NO_ADVERTISE ?
> <details><summary>→ réponse</summary><br><b>NO_EXPORT</b> : la route circule dans l'AS mais ne sort pas vers un autre AS. <b>NO_ADVERTISE</b> : la route n'est réannoncée à <b>aucun</b> voisin, ni interne ni externe — elle meurt sur le routeur qui la reçoit.</details>

> 🧠 **MÉMO** — « **EXPORT** = franchir la frontière de l'**AS**. **ADVERTISE** = franchir le **routeur**. »
> ADVERTISE est plus restrictif qu'EXPORT, comme un routeur est plus petit qu'un AS.

### 7.4 Communities d'opérateur : la grille type

Chaque opérateur publie sa propre grille. Le motif est presque toujours le même :

```
   ASN:1xx  → action sur le LOCAL_PREF chez le fournisseur
              ASN:110 = local pref 110 (préféré)
              ASN:80  = local pref 80  (secours)
   ASN:2xx  → NE PAS annoncer à l'AS xx
   ASN:3xx  → prepend 1× vers l'AS xx
   ASN:4xx  → prepend 2× vers l'AS xx
   ASN:9xx  → n'annoncer qu'à une région géographique
```

> ⚠️ **PIÈGE** — Sur Cisco, les communities ne sont **pas envoyées par défaut**. Il faut
> `neighbor x.x.x.x send-community` (ou `send-community both` pour standard + extended). Tu configures ta
> politique, tu ne comprends pas pourquoi elle n'a aucun effet : c'est ça. Sur FRR/BIRD elles partent par
> défaut.

**Pour toi, data engineer :** AWS Direct Connect utilise exactement ce mécanisme. Sur une *public virtual
interface*, tu tags tes annonces avec `7224:7100` / `7224:7200` / `7224:7300` pour demander un local pref
bas / moyen / haut côté Amazon, et `7224:9100` / `7224:9200` / `7224:9300` pour limiter la portée de tes
propres préfixes à la région locale, au continent ou au monde entier. Dans l'autre sens, ce sont **AWS
qui étiquette ses annonces vers toi** avec `7224:8100` (routes de la même région) et `7224:8200` (routes
du même continent) — à toi de les filtrer. C'est ta seule prise pour influencer le trafic **entrant**
depuis AWS.

---

## 8. Route reflectors : casser le full mesh

### 8.1 Le problème et l'idée

50 routeurs iBGP → 1 225 sessions. Inacceptable. L'idée du **route reflector** (RR, RFC 4456) : on désigne
un routeur autorisé à **violer** la règle de split horizon iBGP, et on lui rattache les autres en étoile.

```
   AVANT : full mesh 6 routeurs = 15 sessions

       R1───R2         APRÈS : 2 RR + 6 clients
       │╳╳╳│                    = 12 sessions clients + 1 RR-RR
       R3─╳─R4              ┌────RR1════RR2────┐
       │╳╳╳│                │   ╱ │ ╲  ╱ │ ╲   │
       R5───R6              R1  R2  R3 R4  R5  R6
                            (chaque client : 2 sessions)
```

### 8.2 Les règles de réflexion — à savoir exactement

Un RR classe ses pairs iBGP en **clients** et **non-clients**. Puis :

| Route reçue de… | Réfléchie vers |
|---|---|
| un **client** | tous les clients **et** tous les non-clients |
| un **non-client** (iBGP normal) | **les clients seulement** |
| un pair **eBGP** | tout le monde (clients + non-clients) |

> ❓ **RETIENS ÇA** — Une route apprise d'un non-client est réfléchie vers qui ?
> <details><summary>→ réponse</summary><br><b>Vers les clients uniquement.</b> Les non-clients sont supposés être en full mesh entre eux, ils l'ont déjà reçue directement.</details>

### 8.3 Anti-boucle : deux attributs nouveaux

Puisqu'on a cassé le split horizon, il faut un autre garde-fou. Deux attributs, non transitifs, invisibles
hors de l'AS :

- **ORIGINATOR_ID** (type 9) : le router-ID du routeur qui a introduit la route dans l'AS. Un routeur qui
  reçoit une route portant **son propre** ORIGINATOR_ID la jette.
- **CLUSTER_LIST** (type 10) : chaque RR préfixe son **cluster-ID** (par défaut son router-ID). Un RR qui
  voit **son** cluster-ID dans la liste jette la route.

C'est exactement le rôle que jouait l'AS_PATH en eBGP, transposé à l'intérieur de l'AS.

> ⚠️ **PIÈGE** — Un RR **ne modifie pas** LOCAL_PREF, MED, AS_PATH ni NEXT_HOP quand il réfléchit. Il est
> transparent sur les attributs. Conséquence : le RR choisit **son** meilleur chemin (selon **sa** position
> IGP) et ne réfléchit que celui-là. Ses clients peuvent donc recevoir un chemin qui n'est pas optimal
> **pour eux** — c'est la perte de diversité de chemins des architectures RR. Les remèdes : ADD-PATH
> (RFC 7911), ou placer les RR de façon topologiquement représentative.

### 8.4 L'alternative : les confédérations

Les **confédérations BGP** (RFC 5065) découpent un gros AS en **sous-AS** (souvent des ASN privés). À
l'intérieur d'un sous-AS : full mesh iBGP, mais petit. Entre sous-AS : de l'eBGP « intra-confédération »,
qui utilise les segments `AS_CONFED_SEQUENCE` — invisibles à l'extérieur, et ne comptant pas dans la
longueur de l'AS_PATH.

En pratique : **les route reflectors ont gagné**, ils sont plus simples. Les confédérations survivent dans
quelques très gros réseaux historiques et… en question d'entretien.

---

## 9. Peering et transit : l'économie du routage

### 9.1 Les deux relations fondamentales

```
   TRANSIT (« je paie »)              PEERING (« on échange »)

        Fournisseur                     AS-X ◄────────► AS-Y
             ▲  │                       même niveau, pas de facture
        €€€  │  │ annonce TOUT           (settlement-free)
             │  ▼ Internet
          Client                      AS-X annonce : ses préfixes
                                                   + ceux de ses clients
   Client annonce : ses préfixes      AS-X n'annonce PAS :
                  + ses clients                 les routes de son transit
   Client reçoit : TOUT Internet      → chacun ne joint que l'autre
                                        et ses clients
```

La différence tient en une phrase : **le transit donne accès à tout Internet, le peering ne donne accès
qu'au réseau du pair et à ses clients.** Le peering **n'est pas transitif** — si A peer avec B et B peer
avec C, A n'atteint pas C par B.

> ⚠️ **PIÈGE** — C'est *exactement* la règle du **VPC peering** dans AWS/GCP : le peering de VPC n'est pas
> transitif non plus. VPC-A ↔ VPC-B et VPC-B ↔ VPC-C ne donne pas A ↔ C. Ce n'est pas une limitation
> arbitraire du cloud, c'est le modèle BGP repris tel quel. La solution cloud (Transit Gateway, Cloud
> Router) est l'équivalent d'acheter du transit à un tiers central.

### 9.2 La politique valley-free

De la relation économique découle mécaniquement une politique de LOCAL_PREF. Convention très répandue :

| Origine de la route | LOCAL_PREF typique | Logique économique |
|---|---|---|
| **Client** (il me paie) | **200** | Je gagne de l'argent → je privilégie |
| **Peer** (gratuit) | **100** | Neutre → deuxième choix |
| **Transit** (je paie) | **50** | Ça me coûte → dernier recours |

Et la règle de propagation, dite **valley-free** (modèle de Gao-Rexford) :

```
   Une route apprise d'un CLIENT      → annoncée à TOUT LE MONDE
   Une route apprise d'un PEER        → annoncée aux CLIENTS SEULEMENT
   Une route apprise d'un TRANSIT     → annoncée aux CLIENTS SEULEMENT
```

**Toute violation de cette règle est une fuite de routes.** Retiens ce raccourci : « on ne monte jamais
deux fois » — un chemin valide monte vers un transit, éventuellement traverse un peering au sommet, puis
redescend. Jamais de « vallée ».

> ❓ **RETIENS ÇA** — En une phrase, qu'est-ce qu'une fuite de routes (*route leak*) ?
> <details><summary>→ réponse</summary><br>L'annonce de routes apprises d'un <b>peer ou d'un transit</b> vers un <b>autre peer ou transit</b>. L'AS devient involontairement transitaire pour du trafic qui n'a rien à faire chez lui, et s'effondre sous la charge.</details>

### 9.3 Les points d'échange (IXP)

Un **IXP** (*Internet Exchange Point*) est un commutateur Ethernet géant, neutre, dans un datacenter. Tu
loues un port (10G, 100G, 400G), tu te connectes à un VLAN partagé, et tu montes des sessions BGP avec les
autres membres.

```
   ┌──────────────────────────────────────────────────┐
   │        IXP  —  fabric Ethernet L2 partagée       │
   │  ┌─────────────── un seul subnet /23 ─────────┐  │
   │  │  .1      .2      .3      .4       .254     │  │
   └──┼──┬───────┬───────┬───────┬─────────┬───────┼──┘
      │  │       │       │       │         │       │
     FAI-A   FAI-B   CDN-C   Hébergeur  ROUTE SERVER
      │       │       │       │              │
      └───────┴───────┴───────┴──────────────┘
        sessions BGP bilatérales (peering privé)
        OU une seule session vers le route server
           qui redistribue à tous (peering multilatéral)
```

Deux modèles :

- **Bilatéral** : une session BGP par pair. Contrôle fin, mais n sessions à négocier.
- **Multilatéral via route server** : une seule session vers le RS, qui te donne les routes de tous les
  membres qui y participent. Le RS **ne s'insère pas dans l'AS_PATH** (il est transparent) et ne route
  aucun paquet — il ne fait que du plan de contrôle.

Grands IXP : **DE-CIX** (Francfort, trafic de pointe de l'ordre de 15-20 Tbit/s), **AMS-IX**
(Amsterdam), **LINX** (Londres), **France-IX** (Paris). L'économie est imparable : un port d'IXP coûte un
prix **fixe** mensuel, alors que le transit se paie **au Mbit/s consommé**. Dès qu'un volume est
significatif, peerer coûte moins cher que transiter — et donne en prime **moins de sauts d'AS, donc moins
de latence**.

Un **Tier 1** est un AS qui n'achète de transit à personne et atteint tout Internet uniquement par
peering : Lumen (3356), NTT (2914), Arelion, Cogent, GTT, Tata, Zayo, Orange, Deutsche Telekom, PCCW…
Une dizaine d'acteurs.

> ❓ **RETIENS ÇA** — Un route server d'IXP apparaît-il dans l'AS_PATH des routes qu'il distribue ?
> <details><summary>→ réponse</summary><br><b>Non.</b> Il est transparent : il ne prepend pas son ASN, et il ne transporte aucun paquet de données. Il ne fait que du plan de contrôle.</details>

**Pourquoi ça t'intéresse concrètement :** la différence entre « ton flux passe par un peering direct » et
« ton flux passe par deux transits » se lit en millisecondes et en euros. Un `traceroute -A` (qui affiche
les ASN) sur le chemin de ton bucket S3 vers ton datacenter te dit lequel des deux tu vis. Et un
`aws s3 sync` à 40 ms de RTT au lieu de 12 ms, sur des millions de petits objets, c'est un job qui triple
de durée.

---

## 10. Quand ça casse : fuites et détournements

### 10.1 Le péché originel de BGP

BGP a été conçu en 1989 entre gens qui se connaissaient. **Il n'a aucune vérification native de la
légitimité d'une annonce.** Si un AS annonce `8.8.8.0/24`, ses voisins le croient — parce qu'il n'existe
aucun moyen, dans le protocole, de vérifier qu'il en est le propriétaire.

Deux familles d'accidents, à ne surtout pas confondre :

| | **Fuite de routes** (*route leak*) | **Détournement** (*hijack*) |
|---|---|---|
| Ce qui est annoncé | des préfixes **légitimes** | des préfixes **qui ne t'appartiennent pas** |
| Ce qui est faux | la **direction** de propagation | l'**origine** du préfixe |
| Cause typique | erreur de filtre, BGP optimizer | erreur de frappe, ou attaque |
| Effet | congestion massive, détour | interception, blackhole, vol |
| Intention | presque toujours accidentelle | accidentelle **ou** malveillante |

### 10.2 L'arme absolue du détournement : le préfixe plus spécifique

Rappelle-toi R03 : le **longest prefix match** l'emporte sur tout. Ce n'est pas un critère BGP, c'est la
règle de la table de routage — donc elle passe **avant** l'algorithme de sélection.

```
   Légitime  : Google annonce  8.8.8.0/24   depuis AS15169
   Attaquant : annonce         8.8.8.0/25 + 8.8.8.128/25  depuis AS66666

   Un routeur qui reçoit les deux :
     → ce ne sont PAS des chemins concurrents pour le même préfixe
     → ce sont DEUX préfixes différents, tous deux installés
     → un paquet vers 8.8.8.8 matche le /25, plus spécifique
     → il part chez l'attaquant. L'algorithme BGP n'a rien à dire.
```

C'est pour cela que les opérateurs **filtrent les préfixes plus longs que /24 en IPv4 et /48 en IPv6** :
sans ce plafond conventionnel, n'importe qui pourrait détourner n'importe quoi avec des /32.

> ⚠️ **PIÈGE** — Beaucoup croient qu'un détournement « bat » l'annonce légitime dans l'algorithme BGP. Faux.
> Le détournement par plus-spécifique **court-circuite l'algorithme** : les deux routes coexistent, et
> c'est le longest prefix match de la FIB qui tranche. Le seul détournement qui passe par l'algorithme
> BGP est celui **à préfixe égal**, et là il ne gagne que localement, près de l'attaquant.

### 10.3 Cinq incidents à savoir raconter

**AS7007, 25 avril 1997 — l'incident fondateur.** Un routeur mal configuré chez un petit opérateur de
Floride réannonce la table Internet entière découpée en /24, avec lui-même en origine. Sa longueur d'AS_PATH
étant minimale et les préfixes très spécifiques, une grande partie d'Internet lui envoie son trafic. Le
réseau mondial est perturbé plusieurs heures. C'est l'événement qui a créé la notion de filtre de préfixes.

**Pakistan Telecom / YouTube, 24 février 2008.** Ordonné de bloquer YouTube dans le pays, Pakistan Telecom
(AS17557) annonce en interne `208.65.153.0/24` — plus spécifique que le `208.65.152.0/22` de YouTube —
pour la router vers un trou noir. Sauf que l'annonce **fuite** vers son transitaire PCCW, qui la propage
mondialement. YouTube est inaccessible depuis une grande partie du monde pendant environ **deux heures**.
Cas d'école : un blackhole interne qui devient un détournement mondial.

**Google → Verizon, 25 août 2017.** Google fuite un très grand nombre de routes apprises en transit vers
Verizon. Le trafic japonais (NTT OCN, KDDI) est massivement redirigé à travers l'infrastructure Google, qui
ne peut pas l'absorber. **Internet au Japon est dégradé pendant environ 40 minutes.** Une fuite pure : les
préfixes étaient légitimes, seule la direction était fausse.

**Amazon Route 53 / MyEtherWallet, 24 avril 2018 — le hijack criminel.** AS10297 annonce des préfixes
appartenant aux serveurs DNS d'Amazon. Les requêtes DNS pour `myetherwallet.com` sont détournées vers un
serveur pirate, qui répond une fausse IP ; les utilisateurs atterrissent sur un site clone avec un certificat
TLS auto-signé (l'avertissement du navigateur a été cliqué par des milliers de gens). Environ **150 000 $**
en cryptomonnaie volés en deux heures. Leçon : **un détournement BGP casse le DNS avant de casser le web**.

**Facebook, 4 octobre 2021 — le retrait volontaire.** Ce n'est **ni** une fuite **ni** un détournement. Une
commande de maintenance coupe la connectivité du backbone. Les serveurs DNS autoritaires de Facebook, ne
voyant plus le réseau interne, **retirent** leurs annonces BGP par sécurité. Les préfixes disparaissent
d'Internet : plus de DNS, donc plus rien — et les outils internes, badges et systèmes d'accès étant sur
le même domaine, les ingénieurs ne peuvent plus entrer dans les datacenters. **Environ 6 heures de panne
mondiale.** Leçon : quand tu retires un préfixe BGP, tu ne « coupes » pas un service, tu **effaces
l'existence** du réseau.

Ajoute **le 12 août 2014, « 512k day »** : la table IPv4 globale franchit **512 000 routes**. Des milliers
de Cisco Catalyst 6500 / 7600 avaient une allocation TCAM par défaut de 512k entrées ; débordement, crash
ou basculement en commutation logicielle. Des pannes dans le monde entier, causées par un simple
**franchissement de seuil de croissance**. C'est le rappel que la taille de la table est une contrainte
matérielle, pas une abstraction.

> ❓ **RETIENS ÇA** — Quelle est la différence de nature entre une fuite et un détournement ?
> <details><summary>→ réponse</summary><br>La <b>fuite</b> annonce des préfixes légitimes dans une <b>direction interdite</b> (violation valley-free). Le <b>détournement</b> annonce des préfixes dont on n'est <b>pas propriétaire</b>. Fuite = mauvaise direction ; hijack = mauvaise origine.</details>

---

## 11. Sécuriser BGP : filtres, IRR, RPKI

### 11.1 Les trois couches de défense

```
   ┌─ 1. LIMITES DE SESSION ───────────────────────────────┐
   │   maximum-prefix : coupe la session au-delà de N       │
   │   → ta protection ultime contre la fuite du voisin     │
   │   → NOTIFICATION code 6 sous-code 1                    │
   ├─ 2. FILTRES DE PRÉFIXES ───────────────────────────────┤
   │   prefix-list / as-path filter générés depuis l'IRR    │
   │   (RIPE DB, RADB…) avec bgpq4 → objets route:/as-set:  │
   │   → indispensable, mais l'IRR n'est pas authentifié    │
   ├─ 3. RPKI / ROV ────────────────────────────────────────┤
   │   validation cryptographique de l'ORIGINE              │
   └────────────────────────────────────────────────────────┘
```

### 11.2 RPKI : comment ça marche vraiment

**RPKI** = *Resource Public Key Infrastructure*. Une PKI où les RIR sont les autorités de certification, et
où chaque titulaire de préfixe peut signer un objet appelé **ROA** (*Route Origin Authorization*).

Un ROA contient exactement **trois choses** :

```
   ROA = ( préfixe , maxLength , ASN autorisé )

   Exemple :  ( 203.0.113.0/24 , 24 , AS64500 )
   → « seul l'AS64500 a le droit d'annoncer 203.0.113.0/24,
      et aucun préfixe plus spécifique que /24 »
```

Le routeur ne fait pas la crypto lui-même. Un **validateur** (Routinator, rpki-client, FORT, OctoRPKI)
télécharge et vérifie les dépôts des 5 RIR, en extrait une liste de VRP (*Validated ROA Payloads*), et la
sert au routeur par le protocole **RTR** (*RPKI-to-Router*, RFC 6810/8210), sur **TCP port 323**.

```
   RIR (dépôts signés)          Ton infra
   ┌──────────┐   rsync/RRDP   ┌────────────┐   RTR / TCP 323   ┌─────────┐
   │ RIPE ARIN│───────────────►│ VALIDATEUR │──────────────────►│ ROUTEUR │
   │ APNIC ...│  toutes les    │ Routinator │  liste de VRP     │  BGP    │
   └──────────┘  ~10 min       └────────────┘  (préfixe,max,AS) └─────────┘
                                                                     │
                          pour chaque annonce reçue ─────────────────┘
                          → VALID / INVALID / NOT FOUND
```

**Les trois verdicts** :

| Verdict | Condition | Action recommandée |
|---|---|---|
| **VALID** | un ROA couvre le préfixe, longueur ≤ maxLength, origine = ASN autorisé | accepter (souvent local pref +) |
| **INVALID** | un ROA couvre le préfixe **mais** l'origine ou la longueur ne colle pas | **rejeter** |
| **NOT FOUND** | aucun ROA ne couvre le préfixe | accepter (majorité historique) |

> ⚠️ **PIÈGE** — Le **maxLength trop permissif** est l'erreur de configuration la plus fréquente. Si tu
> publies `(203.0.113.0/24, 32, AS64500)`, tu autorises n'importe qui annonçant depuis un AS_PATH forgé à
> découper ton /24 en /32. **Règle : maxLength = longueur du préfixe**, sauf besoin explicite de
> désagrégation.

> ⚠️ **PIÈGE** — **RPKI ne valide que l'ORIGINE, jamais le CHEMIN.** Un attaquant peut annoncer ton préfixe
> avec un AS_PATH forgé se terminant par ton vrai ASN : le ROA dit « VALID », et le détournement passe. La
> protection du chemin, c'est **BGPsec** (RFC 8205) — signature de chaque saut — pratiquement pas déployée
> à cause du coût en CPU et de l'obligation d'être déployée de bout en bout. Et RPKI ne protège **pas non
> plus contre les fuites de routes**, qui n'altèrent ni l'origine ni le préfixe (travaux ASPA en cours).

> ❓ **RETIENS ÇA** — Que contient un ROA ?
> <details><summary>→ réponse</summary><br>Trois champs : le <b>préfixe</b>, la <b>maxLength</b> (longueur maximale autorisée des annonces plus spécifiques) et l'<b>ASN d'origine autorisé</b>. Signé cryptographiquement par le titulaire via son RIR.</details>

> ❓ **RETIENS ÇA** — RPKI protège-t-il contre une fuite de routes ?
> <details><summary>→ réponse</summary><br><b>Non.</b> Une fuite propage des préfixes légitimes avec une origine légitime — le ROA les valide parfaitement. RPKI ne couvre que l'origine, pas la direction ni le chemin.</details>

### 11.3 Exercice corrigé n°4 — validation RPKI

ROA publié : **`(192.0.2.0/22 , maxLength 24 , AS64500)`**

Détermine le verdict de chaque annonce :

| # | Annonce | Origine |
|---|---|---|
| a | `192.0.2.0/22` | AS64500 |
| b | `192.0.2.0/24` | AS64500 |
| c | `192.0.2.0/25` | AS64500 |
| d | `192.0.2.0/23` | AS64501 |
| e | `198.51.100.0/24` | AS64500 |

**Corrigé :**

- **a → VALID.** Préfixe couvert, longueur 22 ≤ 24, origine correcte. ✔
- **b → VALID.** Couvert par le /22, longueur 24 ≤ maxLength 24, origine correcte. ✔
- **c → INVALID.** Couvert, origine correcte, **mais 25 > maxLength 24**. Un ROA existe et interdit cette
  longueur → invalide (pas « not found » : le préfixe *est* couvert).
- **d → INVALID.** Couvert, longueur OK, **mais l'origine AS64501 ≠ AS64500**.
- **e → NOT FOUND.** Aucun ROA ne couvre `198.51.100.0/24`. Pas d'information ⇒ pas d'invalidité.

**Le point clé du corrigé** : *INVALID* ne signifie pas « je ne connais pas ». Il signifie « je connais, et
ça ne colle pas ». Le préfixe non couvert est *NOT FOUND*, et il est accepté.

---

## 12. MPLS : commuter des étiquettes plutôt que router des adresses

### 12.1 Le problème historique — et le vrai problème d'aujourd'hui

Au milieu des années 90, faire un *longest prefix match* sur une table de 50 000 routes à chaque paquet
était coûteux. L'idée de MPLS : décider **une seule fois**, à l'entrée du réseau, et coller au paquet une
**étiquette** de longueur fixe ; les routeurs suivants ne regardent plus l'adresse IP, ils lisent
l'étiquette dans une table indexée directement.

Cette raison-là est morte : les ASIC modernes font le longest prefix match à la vitesse du fil. **Mais MPLS
est partout**, pour trois autres raisons, qui sont les vraies :

1. **Les VPN L3** : un opérateur transporte les réseaux privés de 5 000 clients, avec des plans
   d'adressage qui se chevauchent tous (tout le monde a du `10.0.0.0/8`), sans que les routeurs du cœur
   n'aient à connaître une seule de leurs routes.
2. **Le traffic engineering** : forcer un flux à emprunter un chemin précis, ce qu'un IGP ne sait pas faire.
3. **La protection rapide** : *Fast Reroute*, bascule sur un chemin de secours pré-calculé en **moins de
   50 ms**, sans attendre la convergence de l'IGP.

### 12.2 Le label : 32 bits, quatre champs

```
     0                   1                   2                   3
     0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
    |               LABEL  (20 bits)            | TC  |S|    TTL    |
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+

    LABEL : 20 b  → 0 à 1 048 575 ; 0-15 RÉSERVÉS, usage à partir de 16
    TC    :  3 b  → Traffic Class (ex-EXP), la QoS — 8 classes
    S     :  1 b  → Bottom of Stack : 1 = dernier label de la pile
    TTL   :  8 b  → décrémenté comme un TTL IP, anti-boucle

    Où ça se place :
    ┌────────────┬──────────────┬─────────────┬─────────┐
    │ En-tête L2 │ LABEL(S) 4 o │ En-tête IP  │ Données │
    │ (Ethernet) │  pile MPLS   │             │         │
    └────────────┴──────────────┴─────────────┴─────────┘
     EtherType = 0x8847 (unicast MPLS) / 0x8848 (multicast)
     → « couche 2,5 » : au-dessus d'Ethernet, sous IP
```

> 🧠 **MÉMO** — **20 – 3 – 1 – 8**. Lis-le comme une heure : « **20 h 31, 8 secondes** ». Label 20 bits,
> TC 3 bits, S 1 bit, TTL 8 bits. Somme = 32. Et **4 octets par label empilé** : c'est le chiffre à sortir
> quand on te parlera de MTU.

**Labels réservés** à connaître :

| Label | Nom | Effet |
|---|---|---|
| **0** | IPv4 Explicit NULL | « dépile et traite en IPv4 » (garde la QoS du TC) |
| 1 | Router Alert | équivalent de l'option IP Router Alert |
| **2** | IPv6 Explicit NULL | idem pour IPv6 |
| **3** | **Implicit NULL** | « **dépile avant de me l'envoyer** » → déclenche le PHP |

### 12.3 Le chemin : LSP, et les trois opérations

Un **LSP** (*Label Switched Path*) est un tunnel unidirectionnel de bout en bout. Trois rôles :

- **LER / PE** (*Label Edge Router*, ingress) : **PUSH** — colle le label sur un paquet IP.
- **LSR / P** (*Label Switch Router*, cœur) : **SWAP** — remplace le label entrant par un label sortant.
- **Egress** : **POP** — retire le label et route normalement.

```
   PE1 ──────► P1 ──────► P2 ──────► PE2 ──────► destination
   PUSH 100    SWAP       POP        lookup IP normal
               100→200    (PE2 lui a annoncé le label 3)

   Paquet sur le fil :
   PE1→P1 : [Eth][L=100][IP]
   P1→P2  : [Eth][L=200][IP]
   P2→PE2 : [Eth][IP]              ← plus de label !

   PENULTIMATE HOP POPPING (PHP) :
   PE2 a annoncé le label 3 (implicit null) à P2.
   P2 comprend « dépile toi-même », et envoie de l'IP pur.
   → PE2 économise une double consultation (dépiler PUIS router).
```

> ❓ **RETIENS ÇA** — Que signifie le label 3, et quel comportement déclenche-t-il ?
> <details><summary>→ réponse</summary><br><b>Implicit NULL</b>. Le routeur de sortie l'annonce à son voisin précédent pour lui dire « dépile le label avant de m'envoyer le paquet ». C'est le <b>Penultimate Hop Popping (PHP)</b>, qui évite au routeur de sortie une consultation supplémentaire.</details>

### 12.4 Qui distribue les labels ?

| Protocole | Transport | Usage |
|---|---|---|
| **LDP** (RFC 5036) | découverte **UDP 646** (multicast 224.0.0.2), session **TCP 646** | le cas général : un label par préfixe IGP |
| **RSVP-TE** | IP protocole **46** | traffic engineering, réservation de bande passante, FRR |
| **MP-BGP** | TCP 179 | labels de **service** : VPN L3, 6PE, EVPN |
| **Segment Routing** | **aucun** — labels portés par l'IGP | remplace LDP/RSVP ; SRGB Cisco par défaut **16000-23999** |

Segment Routing est la direction actuelle : plus aucun protocole de distribution de labels, le chemin est
encodé dans une **pile de labels par le routeur d'entrée**, et le cœur est sans état. C'est ce qui est
déployé aujourd'hui dans les nouveaux réseaux d'opérateurs et de grands clouds.

> ❓ **RETIENS ÇA** — Sur quels ports LDP travaille-t-il ?
> <details><summary>→ réponse</summary><br><b>UDP 646</b> pour la découverte des voisins (hello vers 224.0.0.2), <b>TCP 646</b> pour la session d'échange de labels.</details>

### 12.5 Le VPN L3 MPLS (RFC 4364) — le produit phare

Le problème : ton opérateur relie les 40 sites d'une banque, les 200 magasins d'un distributeur, et
3 000 autres clients. **Tous utilisent `10.0.0.0/8` en interne.** Comment router des adresses identiques
appartenant à des clients différents, sans conflit, et sans mettre 3 millions de routes clientes dans le
cœur ?

Trois mécanismes s'empilent :

**1. La VRF** — *Virtual Routing and Forwarding*. Une table de routage séparée par client, sur le PE.
Le `10.0.0.0/8` de la banque et celui du distributeur vivent dans deux VRF distinctes. Rien de partagé.

**2. Le Route Distinguisher (RD)** — 8 octets préfixés à l'adresse IPv4 pour la rendre **unique** dans
MP-BGP :

```
   RD (8 o)  +  préfixe IPv4 (4 o)  =  route VPNv4 (12 o = 96 bits)

   Banque       : RD 65000:1  + 10.1.0.0/16 → 65000:1:10.1.0.0/16
   Distributeur : RD 65000:2  + 10.1.0.0/16 → 65000:2:10.1.0.0/16
   → deux routes DIFFÉRENTES pour BGP. Le conflit disparaît.
```

**3. Le Route Target (RT)** — une **extended community** (8 octets) qui pilote **l'import et l'export**
entre VRF. Le PE exporte les routes de la VRF « banque » avec `RT 65000:100`, et toutes les VRF « banque »
des autres PE importent ce RT.

> ⚠️ **PIÈGE** — **Le RD ne sert PAS à décider où va la route.** Il ne fait que rendre le préfixe unique.
> C'est le **RT** qui décide de l'import/export. C'est la question d'entretien la plus fréquente sur MPLS,
> et l'erreur la plus courante. Preuve par l'usage : les topologies hub-and-spoke et les extranets se font
> en jouant sur les RT, avec un RD identique partout si on veut.

> 🧠 **MÉMO** — **RD = Différencier. RT = Trier.** Le D de RD comme « distinguer/dédoublonner », le T de RT
> comme « trier/transférer vers la bonne VRF ».

**4. Les deux labels.** C'est le mécanisme central, celui à savoir dessiner :

```
   CE ──── PE1 ═══════ P ═══════ P ═══════ PE2 ──── CE
   (client) (bord)     (cœur, ne connaît AUCUNE route client)

   Paquet PE1 → P :
   ┌──────────┬────────────┬────────────┬─────────────┬──────────┐
   │ Ethernet │ LABEL EXT. │ LABEL INT. │ En-tête IP  │ Données  │
   │          │ transport  │    VPN     │  du client  │          │
   │          │  S=0       │   S=1      │             │          │
   └──────────┴────────────┴────────────┴─────────────┴──────────┘
                   │             │
                   │             └── donné par MP-BGP (PE2 → PE1)
                   │                 = « quelle VRF chez PE2 »
                   └── donné par LDP/SR = « comment atteindre PE2 »

   Les routeurs P ne lisent QUE le label externe.
   Ils ne voient jamais le label VPN, ni l'IP du client.
   → le cœur reste vide : il ne connaît que les loopbacks des PE.
```

Le transport MP-BGP de ces routes utilise **AFI 1 / SAFI 128** (VPN-IPv4). Le mode L2 équivalent est
l'**EVPN** (RFC 7432, AFI 25 / SAFI 70), qui est aujourd'hui la brique standard des fabriques de
datacenter avec VXLAN.

> ❓ **RETIENS ÇA** — Combien de labels dans un paquet de VPN L3 MPLS, et que fait chacun ?
> <details><summary>→ réponse</summary><br><b>Deux.</b> Le label <b>externe (transport)</b>, appris par LDP/SR, sert à traverser le cœur jusqu'au PE distant. Le label <b>interne (VPN)</b>, appris par MP-BGP, indique au PE distant dans quelle VRF livrer le paquet.</details>

### 12.6 Exercice corrigé n°5 — MTU et pile de labels

Ton opérateur te livre un VPN L3 MPLS. Le cœur a un MTU de **1500 octets** sur les liens. Tes serveurs
émettent des paquets IP de **1500 octets** avec le bit DF.

**Question : ça passe ?**

Calcul :
```
   Paquet IP client                       1500 o
   + label VPN                            +  4 o
   + label transport                      +  4 o
   ────────────────────────────────────────────
   Trame MPLS à transporter               1508 o   > 1500 ✘
```
**Non.** Le PE d'entrée doit fragmenter — impossible avec DF — donc il jette et renvoie un ICMP type 3
code 4 (*Fragmentation Needed*). Si ce message est filtré par un pare-feu, tu obtiens un **trou noir de
PMTU** (vu en R03) : les petites requêtes passent, les gros transferts gèlent.

**Les trois corrections, par ordre de propreté :**
1. L'opérateur configure un **MTU de 1508 ou 1512** sur ses liens de cœur (« baby giants ») — c'est ce que
   font tous les opérateurs sérieux, et c'est pourquoi tu peux normalement envoyer 1500 dans un VPN MPLS.
2. Tu abaisses le MTU de tes interfaces à **1492 ou 1450**.
3. Tu fais du **MSS clamping** sur tes routeurs : `ip tcp adjust-mss 1452` — TCP négocie alors des segments
   plus petits, et le problème disparaît pour TCP (mais pas pour UDP ni pour QUIC mal réglé).

**Transposition immédiate à ton métier :** c'est exactement le même calcul dans le cloud. VXLAN coûte
**50 octets** (d'où le MTU 1450 classique des CNI Kubernetes), WireGuard **60 à 80**, IPsec **50 à 73**,
GRE **24**. Un pod K8s en `MTU 1500` derrière du VXLAN sur un réseau `MTU 1500` produit exactement la même
panne. Réflexe : **quand un gros transfert gèle alors que le ping passe, compte les octets d'encapsulation.**

---

## 13. BGP là où tu vas vraiment le rencontrer

### 13.1 AWS Direct Connect / Azure ExpressRoute / GCP Interconnect

Un lien physique dédié entre ton datacenter et le cloud. **Le plan de contrôle est du BGP, point.**

```
   Ton DC                    Colocation             AWS
   ┌────────┐   fibre    ┌──────────────┐      ┌──────────┐
   │ routeur│───────────►│ DX location  │─────►│  région  │
   └────────┘  802.1Q    └──────────────┘      └──────────┘
       │        VLAN par « virtual interface »
       │
       ├─ private VIF   → un VPC (via VGW), routes privées
       ├─ transit VIF   → un Transit Gateway, plusieurs VPC
       └─ public VIF    → les préfixes publics AWS (S3, DynamoDB…)

   Ce que tu configures :
   • ton ASN (public, ou privé 64512-65534)
   • une session BGP par VIF, sur un /30 ou /31 d'adresses de tunnel
   • éventuellement une clé MD5
   • BFD, pour détecter une panne en < 1 s au lieu du hold time de 90 s
```

Points opérationnels à savoir :

- Le préfixe le plus spécifique gagne, puis l'AS_PATH. **Un Direct Connect est préféré à un VPN
  IPsec** pour un préfixe équivalent.
- Tu peux **prepender ton ASN** pour désigner un lien de secours, et poser des communities
  (`7224:7100/7200/7300`) sur une public VIF pour agir sur le local pref côté Amazon.
- AWS annonce ses préfixes publics sur Internet depuis l'**AS 16509** (et 14618). Côté Direct Connect,
  l'ASN Amazon est paramétrable, **64512 par défaut** sur une passerelle privée virtuelle.
- Microsoft utilise l'**AS 12076** pour le peering ExpressRoute. Google annonce depuis l'**AS 15169**.
- Il y a des **limites de préfixes** (de l'ordre de la centaine par VIF/VGW) : agrège tes annonces, ou la
  session est refusée.

**Pourquoi ça te concerne :** ta latence entre un job on-premise et un bucket S3 dépend directement de la
route choisie. Une bascule silencieuse de Direct Connect (12 ms) vers VPN de secours (60 ms + chiffrement)
ne déclenche aucune alerte applicative — mais ton pipeline nocturne double de durée. **Le signal à
surveiller, c'est le nombre de préfixes reçus par session BGP et l'état de la session, pas seulement le
débit.**

### 13.2 Kubernetes : ton cluster fait tourner BGP sans que tu le saches

**Calico.** Chaque nœud fait tourner un démon BGP (BIRD historiquement) et annonce le sous-réseau de pods
qu'il possède. Par défaut : **node-to-node mesh** — chaque nœud peer avec chaque autre nœud. C'est un full
mesh iBGP, avec le même problème d'échelle : **au-delà d'une centaine de nœuds, on désactive le mesh et on
met des route reflectors** (souvent 2 ou 3 nœuds dédiés, ou les switches ToR du rack). L'ASN par défaut est
`64512`. Sans BGP vers le réseau physique, Calico encapsule en IPIP ou VXLAN (et tu reperds du MTU).

**Cilium** a un *BGP Control Plane* (basé sur GoBGP) qui annonce les pod CIDR et les IP de services
LoadBalancer aux routeurs du rack.

**MetalLB en mode BGP.** Dans un cluster bare-metal, il n'y a pas de load balancer cloud. MetalLB monte
une session BGP avec tes routeurs, et annonce l'IP d'un service `type: LoadBalancer` **depuis plusieurs
nœuds à la fois**. Le routeur fait de l'**ECMP** vers ces nœuds : tu obtiens un load balancing L3 gratuit,
sans appliance.

```
   Routeur du rack (AS 65000)
        │  ECMP sur 3 chemins vers 203.0.113.50/32
   ┌────┼────┬────────┐
   ▼    ▼    ▼        │
  node1 node2 node3   │  chacun annonce le VIP du service en BGP
   (AS 65001, MetalLB / Calico / Cilium)
```

> ⚠️ **PIÈGE** — L'ECMP par défaut hache l'en-tête (IP src/dst, ports) : si un nœud tombe, le nombre de
> chemins change, **le hachage se redistribue, et TOUTES les connexions existantes peuvent changer de
> nœud** — ce qui les casse si le service est à état. Le remède est le hachage cohérent (*resilient
> hashing*) côté routeur. C'est la panne « quand un pod redémarre, des connexions sans rapport tombent ».

### 13.3 L'anycast : une IP, plusieurs endroits

Le même préfixe est annoncé en BGP depuis 20 datacenters différents. Chaque utilisateur atteint
« naturellement » le plus proche au sens BGP. C'est le fondement de `8.8.8.8`, `1.1.1.1`, des CDN, et des
racines DNS.

Deux propriétés à savoir :

- **La proximité BGP n'est pas la proximité géographique.** Le chemin le plus court en nombre d'AS peut
  traverser un océan. C'est une source classique de latence inexpliquée.
- **L'anycast est sans état.** Une bascule BGP peut renvoyer un client vers un autre site en cours de
  session ; c'est indolore pour du DNS/UDP, mais casse une connexion TCP longue. D'où : anycast pour le
  DNS et les requêtes courtes, unicast pour les sessions longues.

### 13.4 BGP comme source de données

Le sujet qui touche directement ta double casquette :

| Source | Format | Ce qu'on en fait |
|---|---|---|
| **RouteViews**, **RIPE RIS** | dumps **MRT** (RFC 6396), toutes les 5-15 min | historique complet des annonces, jeu d'entraînement |
| **BMP** (RFC 7854) | flux TCP depuis le routeur (port souvent 11019) | vue **pré-politique** et post-politique, en temps réel |
| **bgp.tools**, RIPEstat, Looking Glass | API/web | vérification ponctuelle d'un préfixe |
| **IRR** (RADB, RIPE DB) | objets `route:`, `as-set:` | génération de filtres avec `bgpq4` |

La détection d'anomalies BGP par apprentissage est un domaine actif : on modélise la série temporelle des
annonces/retraits par préfixe, la stabilité de l'origine, la longueur d'AS_PATH, et on lève une alerte sur
un changement d'origine ou une explosion de préfixes plus spécifiques. **Les features sont exactement les
attributs de la section 5** — c'est pour ça qu'il faut les connaître par cœur, pas seulement les
reconnaître.

> ❓ **RETIENS ÇA** — Quelle est la différence entre un dump MRT et un flux BMP ?
> <details><summary>→ réponse</summary><br><b>MRT</b> est un format de <b>fichier</b>, publié périodiquement par des collecteurs (RouteViews, RIS) : c'est de l'historique, différé. <b>BMP</b> est un <b>protocole de streaming</b> depuis le routeur lui-même, en temps réel, et il expose la table <b>avant</b> application des politiques (Adj-RIB-In pré-policy), ce qu'aucun collecteur externe ne peut voir.</details>

---

## 14. Diagnostic : la séquence à dérouler

```
   « Un préfixe n'est pas joignable »

   1. La session est-elle UP ?
      show ip bgp summary          → un NOMBRE dans State/PfxRcd = OK
                                     "Active"/"Idle" = KO → TCP/config
   2. Ai-je reçu la route ?
      show ip bgp 203.0.113.0/24   → présente ? avec quels attributs ?
      show ip bgp neighbors X received-routes   (nécessite soft-reconfig
                                                 ou route-refresh)
   3. Est-elle VALIDE ?
      → l'astérisque « * » manque = NEXT_HOP injoignable
      → ping / show ip route <next-hop>
   4. Est-elle la MEILLEURE ?
      → le « > » manque = une autre route gagne
      → dérouler N W L O A O M E I R sur les candidates
   5. Est-elle ANNONCÉE au voisin ?
      show ip bgp neighbors X advertised-routes
      → absente ? c'est un filtre sortant, une route-map,
        une community NO_EXPORT, ou la règle iBGP split horizon
   6. Le chemin est-il celui que je crois ?
      traceroute -A      (affiche les ASN traversés)
      mtr --aslookup
```

**Lire un `show ip bgp` :**

```
   Status codes: s suppressed, d damped, h history, * valid, > best, i - internal

      Network          Next Hop        Metric LocPrf Weight Path
   *>i203.0.113.0/24   10.0.0.1            0    150      0 200 300 i
   *  203.0.113.0/24   10.0.0.2            0    100      0 200 400 500 i
   *> 198.51.100.0/24  10.0.0.2           30    100      0 200 i

      │││
      ││└── i = apprise en iBGP (rien = eBGP)
      │└─── > = c'est LE meilleur chemin, installé dans la RIB
      └──── * = valide (next-hop joignable)

   La 2e ligne a « * » sans « > » : valide mais pas retenue.
   Ici à cause du LocPrf (150 > 100), critère n°2.
```

> ⚠️ **PIÈGE** — `show ip bgp neighbors X received-routes` renvoie souvent **vide** : par défaut le routeur
> ne garde pas les routes reçues avant filtrage. Il faut soit `soft-reconfiguration inbound` (coûteux en
> mémoire), soit la capacité **Route Refresh** (négociée par défaut sur tout équipement moderne), et
> utiliser `show ip bgp neighbors X routes` pour ce qui a survécu aux filtres.

---

## 15. Questions d'entretien

**1. Pourquoi BGP utilise-t-il TCP alors qu'OSPF est directement sur IP ?**
Parce que BGP échange un volume énorme d'information une seule fois, puis presque rien : il a besoin de
fiabilité, de séquencement et de contrôle de flux, mais pas de rapidité de détection. TCP lui donne tout ça
gratuitement, ce qui permet à BGP de ne jamais envoyer de mise à jour périodique — une route reste valable
jusqu'à retrait explicite. Le prix à payer est une détection de panne lente : le hold time par défaut est
de 90 secondes, d'où l'usage systématique de BFD en complément pour descendre sous la seconde. OSPF, lui,
doit détecter vite et inonder en multicast à beaucoup de voisins d'un coup : TCP serait un handicap.

**2. Donne l'ordre de sélection du meilleur chemin BGP.**
D'abord la validité : le NEXT_HOP doit être joignable, sinon la route est écartée. Ensuite, dans l'ordre :
weight le plus grand (local au routeur, propriétaire Cisco), local preference la plus grande (défaut 100,
portée de l'AS), préférence à une route originée localement, AS_PATH le plus court, ORIGIN le plus bas
(IGP < EGP < incomplete), MED le plus petit — mais uniquement entre chemins reçus du même AS voisin —,
eBGP préféré à iBGP, puis métrique IGP la plus faible vers le next-hop. En cas d'égalité totale : chemin
eBGP le plus ancien, puis plus petit router-ID du voisin, puis plus courte cluster-list, puis plus petite
IP de voisin. Le point à souligner : les deux premiers critères veulent la valeur la plus grande, tous les
suivants la plus petite.

**3. Pourquoi le full mesh iBGP est-il nécessaire, et comment s'en passer ?**
Parce qu'une route apprise d'un pair iBGP n'est jamais réannoncée à un autre pair iBGP. Cette règle existe
faute de mécanisme anti-boucle à l'intérieur de l'AS : l'AS_PATH n'y est pas modifié, donc il ne détecte
rien. Chaque routeur doit donc entendre chaque route directement, soit n(n−1)/2 sessions — 1 225 pour
50 routeurs. On s'en passe avec des route reflectors, qui sont autorisés à réfléchir, et qui utilisent
deux nouveaux attributs anti-boucle, ORIGINATOR_ID et CLUSTER_LIST. L'alternative historique est la
confédération, qui découpe l'AS en sous-AS ; elle a perdu, les RR sont plus simples.

**4. Quelle est la différence entre une fuite de routes et un détournement BGP ?**
Une fuite propage des préfixes parfaitement légitimes dans une direction interdite : typiquement, un AS
réannonce vers un transitaire les routes apprises d'un autre transitaire, violant le principe valley-free.
Il devient transitaire malgré lui et s'effondre sous le trafic — c'est Google/Verizon en 2017. Un
détournement, lui, annonce des préfixes dont on n'est pas titulaire : c'est Pakistan Telecom sur YouTube en
2008, ou le vol sur MyEtherWallet en 2018. Le résumé : fuite = mauvaise direction, hijack = mauvaise
origine. Conséquence importante : RPKI n'arrête que le second.

**5. Que contient un ROA, et qu'est-ce que RPKI ne protège pas ?**
Un ROA contient trois champs signés : le préfixe, la maxLength autorisée, et l'ASN d'origine autorisé. Un
validateur télécharge les dépôts des RIR et alimente le routeur par le protocole RTR sur TCP 323 ; chaque
annonce est alors valide, invalide ou non trouvée, et on rejette les invalides. Ce que ça ne protège pas :
le chemin. Un attaquant peut forger un AS_PATH se terminant par le bon ASN d'origine et obtenir un verdict
valide. La signature de chemin, c'est BGPsec, quasiment pas déployée. RPKI ne protège pas non plus des
fuites, qui conservent une origine légitime.

**6. Un préfixe est reçu, visible dans `show ip bgp`, mais absent de la table de routage. Pourquoi ?**
Le suspect numéro un est un NEXT_HOP injoignable, et c'est presque toujours du iBGP sans `next-hop-self` :
le routeur de bordure a transmis en interne l'adresse du routeur externe, que l'IGP ne connaît pas. La
route apparaît alors sans l'astérisque de validité. Les autres causes : une autre route pour le même
préfixe gagne (il manque le `>`), une route de meilleure distance administrative existe déjà — BGP externe
est à 20 mais BGP interne à 200, donc OSPF à 110 gagne contre de l'iBGP —, ou la route est supprimée par un
agrégat, ou amortie par du route dampening.

**7. Comment influences-tu le trafic entrant vers ton AS, et pourquoi est-ce plus dur que le sortant ?**
Le trafic sortant est facile : le LOCAL_PREF est le critère 2, il est chez toi, il écrase tout le reste, tu
décides. Le trafic entrant est une supplique adressée aux autres. Trois leviers, du plus faible au plus
fort : le MED, qui ne fonctionne qu'entre deux sessions vers le même AS voisin et que le voisin peut
ignorer ; l'AS-path prepending, qui n'agit qu'au critère 4 et que le moindre local pref distant annule ; et
les communities publiées par ton fournisseur, qui vont directement modifier son local pref à lui — c'est le
seul levier vraiment efficace. Le levier ultime, brutal mais imparable, est la désagrégation : annoncer des
préfixes plus spécifiques d'un côté, puisque le longest prefix match passe avant tout BGP. C'est mal vu :
ça pollue la table globale.

**8. Explique un VPN L3 MPLS à quelqu'un qui connaît IP mais pas MPLS.**
L'opérateur crée pour chaque client une table de routage séparée sur les routeurs de bordure, la VRF, ce
qui permet à mille clients d'utiliser tous 10.0.0.0/8 sans conflit. Pour transporter ces routes en BGP
entre les bordures, il préfixe chaque adresse d'un Route Distinguisher de 8 octets qui la rend unique — la
route VPNv4 fait alors 12 octets. Un Route Target, qui est une extended community, décide dans quelles VRF
distantes la route est importée. Dans le plan de données, le paquet porte deux labels : l'externe, appris
par LDP ou Segment Routing, sert à traverser le cœur jusqu'au bon routeur de bordure ; l'interne, appris
par MP-BGP, dit à ce routeur dans quelle VRF livrer. Les routeurs de cœur ne lisent que le label externe et
ne connaissent aucune route client — c'est ça qui rend le modèle scalable.

**9. Quelle est la différence entre RD et RT ? C'est la question qui élimine.**
Le Route Distinguisher rend un préfixe unique dans MP-BGP, et rien d'autre : il ne dit à personne où
envoyer la route. Le Route Target est la communauté étendue qui pilote l'import et l'export entre VRF :
c'est lui, et lui seul, qui construit la topologie du VPN. La preuve par l'usage : on fait du hub-and-spoke
ou de l'extranet en jouant sur les RT, avec un RD identique si on veut. En pratique on met souvent un RD
différent par PE pour un même client, ce qui donne des routes distinctes pour un même préfixe et permet à
un route reflector de conserver plusieurs chemins — c'est un bénéfice de diversité, pas une obligation
fonctionnelle.

**10. Ton cluster Kubernetes utilise Calico avec BGP. Qu'est-ce qui casse à 200 nœuds ?**
Le mode par défaut est le node-to-node mesh, c'est-à-dire un full mesh iBGP : à 200 nœuds, cela fait
19 900 sessions BGP, chacune consommant de la mémoire et du CPU sur chaque nœud, avec des temps de
convergence qui explosent au moindre redémarrage. La solution est la même qu'en réseau opérateur :
désactiver le mesh et déployer des route reflectors, soit deux ou trois nœuds dédiés, soit les switches
top-of-rack qui font déjà du BGP. Au passage, si Calico ne peut pas peerer avec le réseau physique, il
encapsule en IPIP ou VXLAN, et il faut alors abaisser le MTU des pods — typiquement 1450 derrière VXLAN.

**11. `show ip bgp summary` affiche `Active` pour un voisin. Que fais-tu ?**
Je retiens d'abord qu'`Active` est un état d'échec, pas de succès : le routeur essaie d'ouvrir la connexion
TCP et n'y arrive pas. Je vérifie donc dans l'ordre : est-ce que je joins l'adresse du voisin, avec la
bonne adresse source si `update-source` est configuré ; est-ce que le port 179 est ouvert dans les deux
sens sur les ACL et pare-feu ; est-ce que l'ASN configuré correspond à celui du voisin ; et pour de l'eBGP
non directement connecté, est-ce que `ebgp-multihop` est présent puisque le TTL est à 1 par défaut. Si la
session monte puis retombe périodiquement, je regarde le code de NOTIFICATION : Hold Timer Expired pointe
un problème de lien ou de CPU, Cease avec sous-code 1 signifie que la limite `maximum-prefix` a été
atteinte.

---

## 16. Les 3 choses à retenir si tu ne retiens que ça

**1. BGP ne cherche pas le chemin le plus court, il applique une politique — et l'ordre des critères est
tout.** `N W L O A O M E I R` : next-hop joignable, weight, local pref, route locale, AS_PATH, origin, MED,
eBGP sur iBGP, métrique IGP, router-ID. Les deux premières préférences veulent la valeur la plus **grande**,
tout le reste la plus **petite**. L'AS_PATH n'arrive qu'en quatrième : c'est pour ça que le prepending est
un outil faible et que le LOCAL_PREF est le vrai levier. Corollaire pratique : **tu maîtrises facilement ton
trafic sortant, difficilement ton trafic entrant.**

**2. Le peering n'est pas transitif, et il ne l'est ni sur Internet ni dans ton cloud.** Un AS n'annonce à
un peer que ses propres routes et celles de ses clients — jamais celles apprises d'un transit. Violer cette
règle valley-free, c'est une fuite de routes, et c'est ce qui a mis le Japon hors ligne en 2017. La même
règle explique pourquoi VPC-A ↔ VPC-B et VPC-B ↔ VPC-C ne te donnent pas A ↔ C, et pourquoi le Transit
Gateway existe. Et BGP ne vérifie rien nativement : la seule défense réelle tient en trois couches, une
limite `maximum-prefix` sur chaque session, des filtres de préfixes générés depuis l'IRR, et RPKI — qui
valide l'origine, jamais le chemin.

**3. Chaque label MPLS coûte 4 octets, et l'encapsulation finit toujours par te rattraper par le MTU.**
Label = 20 bits d'étiquette, 3 de classe, 1 de fin de pile, 8 de TTL. Un VPN L3 en porte deux : le transport
pour traverser le cœur, le VPN pour désigner la VRF d'arrivée — et le cœur ne connaît aucune route client,
c'est là toute l'astuce. Le même raisonnement s'applique mot pour mot à tes pipelines : VXLAN coûte
50 octets, WireGuard 60 à 80, IPsec jusqu'à 73. **Quand le ping passe mais que le gros transfert gèle,
ce n'est pas le code : compte les octets d'encapsulation.**
