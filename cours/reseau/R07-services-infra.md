# R07 — Services d'infrastructure : DNS, DHCP, NAT, load balancing

> **Ce que tu sauras faire à la fin**
> - Dérouler de mémoire une résolution DNS complète, du `getaddrinfo()` de ton process jusqu'au serveur autoritatif, en nommant chaque acteur, chaque cache et chaque TTL traversé.
> - Choisir le bon type d'enregistrement dans un cas réel (apex de zone, mail, découverte de service, reverse) et expliquer pourquoi un `CNAME` à l'apex est illégal.
> - Diagnostiquer les pannes DNS de Kubernetes : `ndots:5`, timeouts à 5 s, CoreDNS saturé, FQDN de service mal formé.
> - Expliquer DORA sans hésiter, dimensionner un pool DHCP, et dire pourquoi un relais est indispensable dès qu'il y a un routeur entre le client et le serveur.
> - Calculer un épuisement de ports NAT, lire une table de traduction, et nommer les 5 familles de protocoles que le NAT casse et pourquoi.
> - Arbitrer L4 contre L7 sur un cas concret, choisir un algorithme de répartition, dimensionner un health check, et expliquer le DSR et le hachage cohérent.
> - Relier tout ça à ce que tu vas vraiment toucher : VPC, Transit Gateway, NAT Gateway, Route 53, CoreDNS, kube-proxy, Envoy, MTU.
>
> **Pourquoi ça compte dans ton poste**
> Les modules R01→R06 t'ont donné la mécanique du transport. R07 te donne les **services qui rendent cette
> mécanique utilisable** — et ce sont eux qui tombent en production. Un pipeline data ne casse quasiment
> jamais sur « IP ne route pas » ; il casse sur un TTL DNS trop long après un failover, sur une NAT Gateway
> à court de ports quand 300 workers Spark ouvrent chacun 200 connexions vers S3, sur un load balancer qui
> coupe à 60 s une requête analytique qui en prend 90, sur `ndots:5` qui quadruple les requêtes DNS
> d'un cluster d'inférence. Côté IA, chaque appel à un endpoint de modèle commence par une résolution DNS
> et finit derrière un répartiteur : la latence p99 de ton service se joue autant ici que dans le modèle.
>
> **Prérequis** : `R01` (couches, encapsulation), `R02` (Ethernet, MAC, broadcast, MTU), `R03` (IPv4, CIDR, adresses privées), `R04` (table de routage, VPC peering), `R06` (TCP, UDP, ports éphémères, handshake, timeouts).
> **Durée de lecture** : 75-90 min. Les sections 4 (NAT) et 5 (load balancing) contiennent des calculs : papier et crayon.

---

## 1. Le problème commun aux quatre sujets

R01 à R06 ont construit une machine qui sait acheminer un paquet d'une adresse IP à une autre. Cette
machine a quatre trous béants, et ce module est exactement la liste de ces quatre trous.

```
   Ce que tu sais déjà faire            Ce qui manque encore
   ─────────────────────────            ─────────────────────
   Envoyer à 93.184.215.14         →    Personne ne connaît d'adresse IP par cœur.
                                        Il faut traduire des NOMS.            → DNS

   Configurer une IP à la main     →    Tu ne vas pas configurer 4 000 pods
                                        et 200 laptops à la main.             → DHCP

   Router une IP publique          →    Il n'y a pas assez d'IPv4 publiques
                                        pour toutes les machines du monde.    → NAT

   Joindre UN serveur              →    Un serveur ne tient pas la charge,
                                        et il tombe.                          → Load balancing
```

Les quatre partagent une propriété désagréable : **ce sont des points de passage obligés**. Une table de
routage cassée coupe une destination ; un DNS cassé coupe *tout*. Un load balancer mal réglé ne dégrade
pas un service, il l'éteint. C'est pour ça que ces quatre briques concentrent l'essentiel des incidents
d'infrastructure — et l'essentiel des questions d'entretien.

> 🧠 **MÉMO** — Les quatre services répondent à quatre questions, dans l'ordre de la vie d'un paquet :
> **« Qui es-tu ? » (DNS) · « Qui suis-je ? » (DHCP) · « Sous quel nom je sors ? » (NAT) · « Lequel d'entre eux ? » (LB)**.

---

## 2. DNS — l'annuaire d'Internet

### 2.1 Le problème : comment transformer un nom en adresse ?

Au début d'ARPANET, chaque machine avait un fichier `HOSTS.TXT` listant toutes les autres. Un fichier
unique, maintenu à Stanford, téléchargé par FTP. Ça a tenu jusqu'à quelques centaines de machines. Puis
trois choses ont cassé en même temps :

1. **Le volume** — le fichier grossit, chaque machine le retélécharge en entier.
2. **La fraîcheur** — entre deux téléchargements, tu travailles avec des données périmées.
3. **L'autorité** — qui décide du nom d'une machine ? Une seule équipe centrale devient un goulot
   d'étranglement administratif et un point de panne unique.

La solution de Paul Mockapetris (1983, RFC 882/883, puis 1034/1035 en 1987) : **déléguer**. Pas un
annuaire, mais un **arbre d'annuaires**, où chaque nœud délègue à ses enfants le droit de nommer ce qu'ils
contiennent.

Analogie : le DNS, c'est l'**état civil mondial**. Personne ne tient un registre de tous les humains. La
France délègue aux départements, qui délèguent aux mairies. Pour savoir qui est « Dupont, né à Rennes », tu
ne demandes pas à l'ONU : tu demandes à l'ONU **qui gère la France**, à la France **qui gère l'Ille-et-Vilaine**,
et tu finis à la mairie de Rennes, qui est la seule à faire **autorité** sur cette information.

### 2.2 L'espace de noms : un arbre lu de droite à gauche

```
                              .  (racine, label vide)
                              │
        ┌──────────┬──────────┼──────────┬───────────┐
       com        org        fr        arpa         io        ← TLD
        │                     │          │
   ┌────┴────┐           ┌────┴────┐  in-addr
 google   example       cnrs    gouv      │
   │                                    93 . in-addr . arpa
  www                                    ...

  Lecture d'un FQDN :   www . google . com .
                         └┬┘   └──┬─┘  └┬┘ └─ racine (le point final, souvent implicite)
                          │       │     └──── TLD
                          │       └────────── domaine de 2e niveau (la zone déléguée)
                          └────────────────── sous-domaine / hôte
```

Vocabulaire à ne pas mélanger :

| Terme | Définition exacte |
|---|---|
| **Label** | Un segment entre deux points. Max **63 octets**. |
| **FQDN** | Nom complet jusqu'à la racine, point final inclus. Max **255 octets** sur le fil. |
| **Domaine** | Un nœud de l'arbre **et tout son sous-arbre**. |
| **Zone** | La portion d'arbre **effectivement administrée par un serveur donné**, délégations exclues. |
| **Délégation** | Enregistrements `NS` chez le parent qui disent « ce sous-arbre, c'est eux ». |

La distinction **domaine ≠ zone** est celle qui tombe en entretien. `example.com` est un domaine qui
contient `eu.example.com` ; mais si `eu.example.com` est délégué à une autre équipe, il forme **sa propre
zone**, et la zone `example.com` s'arrête au point de délégation.

> ❓ **RETIENS ÇA** — Quelle est la différence entre un domaine et une zone ?
> <details><summary>→ réponse</summary><br>Un <b>domaine</b> est un nœud de l'arbre avec tout son sous-arbre — une notion logique, sans limite. Une <b>zone</b> est l'unité d'administration : ce qu'un serveur autoritatif donné sert réellement, <b>délégations retranchées</b>. Déléguer un sous-domaine le sort de la zone parente tout en le laissant dans le domaine parent.</details>

> ⚠️ **PIÈGE** — Un label fait 63 octets max, un FQDN 255 octets max — mais ces 255 octets comptent le
> **format sur le fil** : chaque label est précédé d'un octet de longueur, et la racine coûte 1 octet.
> Un nom « lisible » de 253 caractères est donc déjà à la limite. En Kubernetes, ça mord pour de vrai :
> un nom de StatefulSet + ordinal + service + namespace + `svc.cluster.local` peut dépasser.

### 2.3 Les quatre acteurs

C'est **la** figure du module. Redessine-la.

```
 ┌──────────────┐                                     ┌───────────────────┐
 │  TON PROCESS │  getaddrinfo("api.exemple.fr")      │  Serveurs RACINE  │
 │  (python,    │                                     │  a→m.root-servers │
 │   curl, jvm) │                                     └─────────┬─────────┘
 └──────┬───────┘                                            ①  ▲   │ « demande à .fr »
        │ 1. cache process (JVM 30 s, getaddrinfo NON caché)     │   ▼
        ▼                                                  ┌────┴────────────┐
 ┌──────────────┐                                          │  Serveurs TLD   │
 │ STUB RESOLVER│  (libc / systemd-resolved / nsswitch)    │  d.nic.fr, …    │
 │  /etc/resolv │                                          └────┬────────────┘
 └──────┬───────┘   requête RÉCURSIVE                         ② ▲   │ « demande à ns1 »
        │  « donne-moi la réponse finale »                       │   ▼
        ▼                                                  ┌────┴────────────┐
 ┌──────────────────────┐    3 requêtes ITÉRATIVES         │  AUTORITATIF    │
 │  RÉSOLVEUR RÉCURSIF  │ ───────────────────────────────► │  ns1.exemple.fr │
 │  (CoreDNS, unbound,  │ ◄─────────────────────────────── │  → 93.184.x.y   │
 │   8.8.8.8, 1.1.1.1)  │    « je ne sais pas, mais eux si »└─────────────────┘
 │  ★ LE CACHE QUI SERT │                                        ③
 └──────────────────────┘
```

| Acteur | Ce qu'il fait | Ce qu'il ne fait **pas** |
|---|---|---|
| **Stub resolver** | Pose **une** question, attend **la** réponse. Code dans la libc. | Il ne parcourt jamais l'arbre. |
| **Résolveur récursif** | Parcourt l'arbre **à ta place**, cache tout. | Il ne fait autorité sur rien. |
| **Serveur racine** | Répond « voici les NS du TLD ». **13 noms** (`a` à `m`), anycast, ~1 900 instances physiques. | Il ne connaît aucun `www`. |
| **Serveur autoritatif** | Détient la zone, répond avec le bit **AA** à 1. | Il ne résout rien pour toi (sauf s'il est mal configuré : *open resolver*). |

> ❓ **RETIENS ÇA** — Quelle est la différence entre une requête récursive et une requête itérative ?
> <details><summary>→ réponse</summary><br><b>Récursive</b> : « débrouille-toi et rends-moi la réponse finale » — c'est ce que le stub demande au résolveur, avec le bit <b>RD</b> (Recursion Desired) à 1. <b>Itérative</b> : « donne-moi ce que tu sais, même si c'est juste un renvoi » — c'est ce que le résolveur pose aux racine/TLD/autoritatifs, qui répondent par une <b>délégation</b> (referral). Le travail récursif est fait par UNE machine ; les autres ne font qu'aiguiller.</details>

> 🧠 **MÉMO** — **Le stub est un client pressé, le résolveur est un stagiaire zélé, les autoritatifs sont
> des fonctionnaires** : ils répondent uniquement sur leur guichet et te renvoient au bon étage.

> ⚠️ **PIÈGE** — « Il y a 13 serveurs racine » est faux et vrai. Il y a **13 identités** (`a` à
> `m.root-servers.net`), limitées historiquement pour tenir dans une réponse UDP de 512 octets. Derrière
> chacune, l'**anycast** (R05) distribue des centaines d'instances. Un `dig` depuis Paris tape une instance
> parisienne de `k.root-servers.net`, pas un serveur unique quelque part.

### 2.4 Une résolution complète, pas à pas

Cible : `api.data.exemple.fr`, cache totalement froid.

```
 t=0.0 ms   process → stub : getaddrinfo("api.data.exemple.fr")
            /etc/nsswitch.conf → hosts: files dns
            → /etc/hosts consulté d'abord (pas de match)

 t=0.1 ms   stub → résolveur 10.0.0.2  [UDP:53]
            QNAME=api.data.exemple.fr  QTYPE=A  QCLASS=IN  RD=1

 t=0.2 ms   résolveur : cache vide → il part de la racine
 ─────────────────────────────────────────────────────────────────────
 ①  résolveur → k.root-servers.net   « A? api.data.exemple.fr »
    ← RÉPONSE : ANCOUNT=0, AA=0
      AUTHORITY : fr. NS d.nic.fr / e.ext.nic.fr / f.ext.nic.fr
      ADDITIONAL: d.nic.fr A 194.0.9.1     ← les GLUE RECORDS      (~15 ms)

 ②  résolveur → d.nic.fr            « A? api.data.exemple.fr »
    ← AUTHORITY : exemple.fr. NS ns1.exemple.fr / ns2.exemple.fr
      ADDITIONAL: ns1.exemple.fr A 51.x.y.z                        (~12 ms)

 ③  résolveur → ns1.exemple.fr      « A? api.data.exemple.fr »
    ← ANSWER : api.data.exemple.fr. 300 IN A 51.10.20.30
      AA=1  ← C'EST LUI L'AUTORITÉ                                 (~20 ms)
 ─────────────────────────────────────────────────────────────────────
 t≈47 ms    résolveur met en cache : A pour 300 s, NS .fr pour 172800 s,
            NS exemple.fr pour 86400 s → il ne repassera PLUS par la racine
 t≈47 ms    résolveur → stub : 51.10.20.30
 t≈47.1 ms  process : connect(51.10.20.30:443)

 La 2e requête, 10 secondes plus tard : ~0,3 ms. Facteur ~150.
```

Deux choses à graver :

1. **Le résolveur ne « descend » pas caractère par caractère.** À chaque étape il pose la **question
   complète** ; l'interlocuteur répond ce qu'il sait, c'est-à-dire souvent juste une délégation. (Sauf en
   *QNAME minimisation*, RFC 9156, où le résolveur ne révèle que le label suivant à chaque niveau — pour la
   vie privée. Unbound et CoreDNS le font par défaut aujourd'hui.)
2. **Les glue records existent pour casser une boucle.** Pour joindre `ns1.exemple.fr`, il faut son A ;
   mais son A est **dans** `exemple.fr`, la zone qu'on cherche justement à joindre. Le parent (`.fr`)
   publie donc l'adresse en section ADDITIONAL : c'est la **glue**. Elle n'est nécessaire que si le
   serveur de noms est *dans* la zone qu'il sert (**in-bailiwick**).

> ❓ **RETIENS ÇA** — À quoi sert un glue record, et quand est-il obligatoire ?
> <details><summary>→ réponse</summary><br>Il donne l'<b>adresse IP</b> d'un serveur de noms directement dans la réponse de délégation du parent. Obligatoire quand le NS d'une zone porte un nom <b>à l'intérieur de cette même zone</b> (<i>in-bailiwick</i>) : sans glue, il faudrait résoudre <code>ns1.exemple.fr</code> pour joindre <code>exemple.fr</code>, ce qui exige déjà de joindre <code>exemple.fr</code>. Boucle.</details>

> ⚠️ **PIÈGE** — `getaddrinfo()` **ne cache rien**. Aucun cache dans la glibc par défaut. Si ton process
> Python résout 10 000 fois le même nom, ce sont 10 000 appels au résolveur — sauf si `nscd`,
> `systemd-resolved` ou un cache applicatif s'interpose. La JVM, elle, cache : `networkaddress.cache.ttl`
> vaut **30 s** par défaut sur les JDK récents (**10 s** pour le cache négatif), et **elle ignore le TTL
> DNS**. C'est LA cause des « après le failover RDS, l'appli tape encore l'ancienne IP ».

### 2.5 Le format d'un message DNS

Même format pour la question et la réponse. **En-tête fixe de 12 octets.**

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                       ID  (16 bits)                           |  ← corrélation req/rép
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|QR|  Opcode   |AA|TC|RD|RA| Z|AD|CD|      RCODE    |             ← les drapeaux
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                    QDCOUNT   (nb de questions)                |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                    ANCOUNT   (nb de réponses)                 |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                    NSCOUNT   (nb d'enreg. d'autorité)         |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                    ARCOUNT   (nb d'enreg. additionnels)       |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|  QUESTION    : QNAME (labels) + QTYPE(2o) + QCLASS(2o)         |
|  ANSWER      : NAME + TYPE(2) + CLASS(2) + TTL(4) + RDLEN(2) + RDATA
|  AUTHORITY   : idem
|  ADDITIONAL  : idem  (+ pseudo-enregistrement OPT si EDNS0)
+---------------------------------------------------------------+
```

Les drapeaux qui servent vraiment :

| Bit | Nom | Sens |
|---|---|---|
| **QR** | Query/Response | 0 = question, 1 = réponse |
| **AA** | Authoritative Answer | La réponse vient du **détenteur de la zone** |
| **TC** | TruncCated | Réponse trop grosse pour l'UDP → **rejoue en TCP** |
| **RD** | Recursion Desired | Le client demande la récursion (stub → résolveur) |
| **RA** | Recursion Available | Le serveur accepte de la faire |
| **AD** | Authentic Data | DNSSEC validé par le résolveur |
| **CD** | Checking Disabled | « Ne valide pas DNSSEC, je le ferai moi-même » |

Codes de retour (RCODE) — les cinq à connaître :

| RCODE | Nom | Signification opérationnelle |
|---|---|---|
| **0** | NOERROR | OK. Attention : NOERROR + ANCOUNT=0 = **le nom existe, pas ce type** (NODATA). |
| 1 | FORMERR | Message malformé. |
| **2** | SERVFAIL | Le serveur a échoué : upstream injoignable, **ou échec de validation DNSSEC**. |
| **3** | NXDOMAIN | Le nom **n'existe pas**. Réponse négative, cachable. |
| 5 | REFUSED | Le serveur refuse (ACL, pas récursif pour toi). |

> ⚠️ **PIÈGE** — `NOERROR` avec 0 réponse ≠ `NXDOMAIN`. `NODATA` veut dire « ce nom existe, mais il n'a
> pas d'enregistrement de ce **type** ». Cas classique : tu demandes un `AAAA` sur un nom qui n'a qu'un
> `A`. Une appli qui traite NODATA comme NXDOMAIN produit des bugs incompréhensibles en dual-stack.

**Taille et transport.** UDP 53 par défaut. Sans EDNS0, la charge utile DNS est plafonnée à **512 octets** ;
au-delà, le serveur pose **TC=1** et le client **rejoue la requête en TCP 53**. EDNS0 (RFC 6891) ajoute un
pseudo-enregistrement **OPT (type 41)** en section ADDITIONAL, dans lequel le client annonce la taille UDP
qu'il accepte : historiquement 4096, aujourd'hui **1232 octets** recommandés (DNS Flag Day 2020) pour éviter
la fragmentation IP. DNSSEC rend cette question critique : les signatures font exploser la taille des
réponses.

> ❓ **RETIENS ÇA** — Que se passe-t-il quand une réponse DNS dépasse la taille UDP annoncée ?
> <details><summary>→ réponse</summary><br>Le serveur tronque, met le bit <b>TC=1</b> et renvoie un message incomplet. Le client doit alors <b>rejouer la même requête en TCP sur le port 53</b>. Conséquence pratique : un pare-feu qui n'ouvre que l'UDP/53 casse DNSSEC, les grosses réponses et les transferts de zone.</details>

> ❓ **RETIENS ÇA** — Quelle taille de charge utile UDP recommande-t-on d'annoncer en EDNS0 aujourd'hui ?
> <details><summary>→ réponse</summary><br><b>1232 octets</b> (DNS Flag Day 2020), choisi pour rester sous le MTU IPv6 minimal de 1280 en évitant la fragmentation. L'ancienne valeur 4096 provoquait des fragments IP souvent perdus ou filtrés.</details>

### 2.6 Les types d'enregistrement

| Type | N° | RDATA | À quoi ça sert | Piège |
|---|---|---|---|---|
| **A** | 1 | 4 octets | Nom → IPv4 | — |
| **AAAA** | 28 | 16 octets | Nom → IPv6 | Un AAAA cassé = 300 ms de Happy Eyeballs |
| **CNAME** | 5 | un nom | Alias : « ce nom, c'est en réalité celui-là » | **Interdit à l'apex**, et **exclusif** |
| **MX** | 15 | préf.(2o) + nom | Serveur de messagerie | **Préférence la plus BASSE = préféré** |
| **TXT** | 16 | chaînes ≤255 o | SPF, DKIM, DMARC, `_acme-challenge` | Une chaîne ≤ 255 o, concaténation possible |
| **SRV** | 33 | prio, poids, port, cible | Découverte de service **avec le port** | Nom en `_service._proto.domaine` |
| **PTR** | 12 | un nom | IP → nom (reverse) | Vit dans `in-addr.arpa` / `ip6.arpa` |
| **NS** | 2 | un nom | Délégation | Présent chez le **parent ET l'enfant** |
| **SOA** | 6 | 7 champs | Paramètres de la zone | Un seul par zone, à l'apex |
| **CAA** | 257 | flag, tag, valeur | Quelles AC peuvent émettre un certif | Vérifié par Let's Encrypt |
| **HTTPS/SVCB** | 65 / 64 | params | ALPN, IP hints, ECH — **et alias à l'apex** | Remplace peu à peu les bidouilles CNAME |
| DS / DNSKEY / RRSIG / NSEC3 | 43/48/46/50 | — | DNSSEC | voir §2.10 |

**Le SOA, champ par champ** — il pilote toute la réplication de la zone :

```
exemple.fr.  3600  IN  SOA  ns1.exemple.fr. hostmaster.exemple.fr. (
                2026090901   ; SERIAL   — l'esclave compare, ne recopie que si > 
                7200         ; REFRESH  — l'esclave revérifie toutes les 2 h
                3600         ; RETRY    — s'il échoue, il réessaie dans 1 h
                1209600      ; EXPIRE   — après 14 j sans contact, il ARRÊTE de servir
                300 )        ; MINIMUM  — TTL du CACHE NÉGATIF (NXDOMAIN)
```

Le dernier champ est un piège d'histoire : il s'appelait « TTL minimum », il ne veut **plus** dire ça
depuis la RFC 2308. Il définit la durée pendant laquelle un `NXDOMAIN` sur cette zone reste caché — en
pratique **min(SOA.MINIMUM, TTL de l'enregistrement SOA)**.

> ❓ **RETIENS ÇA** — Que définit le dernier champ du SOA ?
> <details><summary>→ réponse</summary><br>Le <b>TTL du cache négatif</b> : combien de temps un résolveur mémorise un <code>NXDOMAIN</code> pour cette zone. Ce n'est plus un « TTL par défaut » malgré son nom historique.</details>

> ⚠️ **PIÈGE — le CNAME.** Deux règles absolues :
> 1. Un nom qui porte un `CNAME` **ne peut porter aucun autre type**. Or l'apex d'une zone porte
>    obligatoirement un `SOA` et des `NS` → **`CNAME` impossible à l'apex** (`exemple.fr` tout court).
> 2. Un `MX` ou un `NS` **ne doit jamais pointer vers un CNAME**.
>
> Contournements : `ALIAS`/`ANAME` (propriétaire : Route 53 le nomme *Alias record*, gratuit, résolu côté
> serveur), *CNAME flattening* (Cloudflare), ou l'enregistrement standard **`HTTPS` (type 65)** qui, lui,
> est légal à l'apex.

**SRV, la découverte de service qui porte le port** — c'est le seul type qui répond « où **et sur quel
port** » :

```
_grpc._tcp.feature-store.prod.exemple.fr. 30 IN SRV 10 60 8443 node-a.prod.exemple.fr.
                                                    │  │   │    └── cible (doit avoir un A/AAAA)
                                                    │  │   └─────── PORT
                                                    │  └─────────── POIDS (répartition à prio égale)
                                                    └────────────── PRIORITÉ (le plus BAS d'abord)
```

Sémantique : on prend d'abord **toutes** les cibles de priorité la plus basse, on tire au sort entre elles
**proportionnellement au poids**, et on ne descend à la priorité suivante que si toutes ont échoué. C'est du
failover + pondération, gratuit, dans le DNS. Kubernetes publie un SRV par port nommé de chaque service.

**PTR et le reverse** — l'IP est écrite **à l'envers**, parce que le DNS délègue de droite à gauche alors
qu'une IP se lit de gauche à droite (le plus général en premier des deux côtés) :

```
   93.184.215.14         →   14.215.184.93.in-addr.arpa.   PTR   exemple.com.
   2001:db8::1           →   1.0.0.…0.8.b.d.0.1.0.0.2.ip6.arpa.   (32 nibbles inversés)
```

> ⚠️ **PIÈGE** — Il n'y a **aucune obligation de cohérence** entre A et PTR : le A est publié par le
> propriétaire du nom, le PTR par le propriétaire du **bloc d'adresses** (ton hébergeur). Sur une IP de
> cloud, tu ne peux souvent pas poser le PTR toi-même. C'est pour ça que le *forward-confirmed reverse DNS*
> (A → IP → PTR → même nom) est un contrôle anti-spam sérieux : il prouve que tu contrôles les deux.

### 2.7 TTL et cache — le seul paramètre que tu régleras vraiment

Le TTL est un entier de **32 bits en secondes**, porté par **chaque enregistrement**. Il dit : « tu peux
garder ça en cache pendant N secondes ». Le résolveur décrémente au fil du temps et sert la valeur restante.

```
   dig api.exemple.fr     →   api.exemple.fr.  300  IN  A  51.10.20.30
   … 120 s plus tard …    →   api.exemple.fr.  180  IN  A  51.10.20.30   ← le TTL fond
   … à 0 …                →   le résolveur repart interroger l'autoritatif
```

Le compromis, en une ligne : **TTL court = agilité, coût en requêtes et en latence. TTL long = performance,
mais tu es prisonnier de ton ancienne réponse.**

| TTL | Usage typique |
|---|---|
| **30-60 s** | Endpoints derrière failover, blue/green, enregistrements pilotés par health check |
| **300 s (5 min)** | Défaut raisonnable pour un service applicatif |
| **3600 s (1 h)** | Enregistrements stables |
| **86400 s (24 h)** | NS d'une zone, MX |
| **172800 s (48 h)** | Délégations de TLD chez la racine |

**La manœuvre de migration** (à connaître par cœur, elle tombe en entretien) :

```
 J-3  : baisser le TTL de 3600 → 60           ┐ il faut attendre que l'ANCIEN TTL
 J-2  : attendre 1 h (l'ancien TTL) minimum   ┘ ait expiré partout AVANT de basculer
 J-0  : basculer l'enregistrement vers la nouvelle IP
 J+0h : au pire 60 s de trafic résiduel sur l'ancienne cible → la garder vivante 15 min
 J+1  : remonter le TTL à 3600
```

> ❓ **RETIENS ÇA** — Pourquoi baisser un TTL **avant** une migration et pas au moment de la bascule ?
> <details><summary>→ réponse</summary><br>Parce que les résolveurs du monde entier ont déjà mis en cache l'<b>ancienne</b> valeur avec l'<b>ancien</b> TTL. Baisser le TTL au moment de la bascule ne change rien pour eux : ils ne reviendront qu'après expiration de ce qu'ils ont déjà. Il faut baisser le TTL, puis <b>attendre au moins la durée de l'ancien TTL</b>, et seulement ensuite basculer.</details>

> ⚠️ **PIÈGE** — Les caches ne respectent pas tous le TTL. La JVM cache 30 s en ignorant le TTL. Certains
> résolveurs FAI plafonnent (`max-cache-ttl`) ou **plancheront** un TTL trop court. `systemd-resolved`
> plafonne à 2 h. Le TTL est une **demande polie**, pas un contrat.

### 2.8 Répartir avec le DNS : round-robin, split-horizon, geo

**DNS round-robin** — tu publies plusieurs `A` sur le même nom, le serveur autoritatif fait tourner l'ordre :

```
   api.exemple.fr.  60  IN  A  51.10.20.30
   api.exemple.fr.  60  IN  A  51.10.20.31
   api.exemple.fr.  60  IN  A  51.10.20.32

   client 1 reçoit  [.30, .31, .32]      client 2 reçoit  [.31, .32, .30]  …
```

C'est **le plus simple des load balancers**, et le plus mauvais. Ses quatre défauts :

1. **Aucune notion de santé.** Une IP morte reste servie jusqu'à ce que tu la retires… et jusqu'à
   expiration des caches.
2. **Aucune notion de charge.** Une machine 4× plus puissante reçoit autant de trafic.
3. **La granularité est le résolveur, pas le client.** Un résolveur d'opérateur sert 500 000 abonnés :
   tous atterrissent sur la même IP tant que l'entrée est en cache.
4. **Le client fait ce qu'il veut** de la liste : les navigateurs appliquent Happy Eyeballs (RFC 8305), la
   glibc réordonne selon la RFC 6724, certaines libs prennent toujours la première.

Utilité réelle : **répartir sur plusieurs load balancers** (le niveau au-dessus), pas sur des serveurs
applicatifs. C'est ce que fait le DNS des ELB/ALB — le nom du LB renvoie plusieurs IP de nœuds.

**Split-horizon (vues)** — même nom, réponse différente **selon qui demande** :

```
   Depuis le VPC (10.0.0.0/16)      : db.exemple.fr → 10.0.4.12   (IP privée)
   Depuis Internet                  : db.exemple.fr → NXDOMAIN    (rien du tout)
```

Implémentations : `view` dans BIND, plugin `view` dans CoreDNS, **Route 53 Private Hosted Zone** associée à
un VPC, `dnsmasq` avec des adresses locales. Ça sert à (a) publier des adresses privées sans les exposer,
(b) court-circuiter la sortie Internet pour du trafic interne, (c) tester une bascule sur un périmètre.

**Routage geo / latence** — Route 53 et équivalents proposent : *simple*, *weighted* (canary à 5 %),
*latency-based* (mesures réelles vers les régions), *failover* (actif/passif adossé à un health check),
*geolocation* (conformité, RGPD, contenu localisé), *geoproximity*, *multivalue answer* (round-robin **avec**
health checks — la version corrigée du round-robin naïf).

> ⚠️ **PIÈGE** — Le DNS est **un mauvais mécanisme de failover rapide**. Même avec un TTL à 60 s, un
> incident se prolonge à cause des caches qui plafonnent, des JVM, des connexions déjà établies (le DNS
> n'a plus son mot à dire une fois le socket ouvert) et des clients qui ne re-résolvent jamais. Pour un
> basculement en secondes, il faut un **anycast** ou un **VIP** : on déplace l'adresse, pas le nom.

### 2.9 DNS dans Kubernetes — la partie qui te servira toutes les semaines

Dans un cluster, le résolveur est **CoreDNS** (successeur de kube-dns depuis K8s 1.13), déployé comme un
Deployment, exposé par un Service `kube-dns` sur une ClusterIP fixe — typiquement **10.96.0.10** quand le
CIDR des services est `10.96.0.0/12`.

**Le schéma de nommage** :

```
   Service normal (ClusterIP)
   ───────────────────────────────────────────────────────────────
   <service>.<namespace>.svc.cluster.local        → la ClusterIP (1 seul A)

   Service headless (clusterIP: None)
   ───────────────────────────────────────────────────────────────
   <service>.<namespace>.svc.cluster.local        → un A par POD prêt
   <pod-name>.<service>.<ns>.svc.cluster.local    → l'IP d'UN pod  (StatefulSet !)

   Port nommé
   ───────────────────────────────────────────────────────────────
   _<port>._<proto>.<service>.<ns>.svc.cluster.local   → SRV (prio, poids, PORT, cible)

   Pod (rarement utilisé)
   ───────────────────────────────────────────────────────────────
   10-1-2-3.<namespace>.pod.cluster.local
```

Le **service headless** est la brique qui fait marcher tous les systèmes distribués sur K8s : Kafka,
Cassandra, Elasticsearch, un anneau de workers Ray, un `StatefulSet` Spark. Chaque membre a un **nom stable
et individuel** — `kafka-0.kafka.data.svc.cluster.local` — indépendant de son IP, qui change à chaque
redémarrage. Sans headless, tu obtiendrais la ClusterIP et tu ne pourrais **jamais adresser un pair précis**.

**Le `/etc/resolv.conf` d'un pod, et le piège `ndots`** :

```
nameserver 10.96.0.10
search  data.svc.cluster.local  svc.cluster.local  cluster.local
options ndots:5
```

Règle : **si le nom demandé contient strictement moins de `ndots` points, on essaie d'abord tous les
suffixes de `search`, dans l'ordre, avant de tenter le nom tel quel.**

```
   Le pod demande :  s3.eu-west-3.amazonaws.com     (3 points  <  5)

   ①  s3.eu-west-3.amazonaws.com.data.svc.cluster.local   → NXDOMAIN
   ②  s3.eu-west-3.amazonaws.com.svc.cluster.local        → NXDOMAIN
   ③  s3.eu-west-3.amazonaws.com.cluster.local            → NXDOMAIN
   ④  s3.eu-west-3.amazonaws.com                          → ENFIN la réponse

   4 requêtes… × 2 car la libc envoie A et AAAA en parallèle  =  8 paquets
   pour UNE résolution. Sur 300 workers Spark qui écrivent sur S3 : CoreDNS meurt.
```

Les trois corrections, par ordre de préférence :

| Correction | Effet |
|---|---|
| **FQDN avec point final** : `s3.eu-west-3.amazonaws.com.` | Court-circuite `search` : 1 requête. Gratuit. |
| `dnsConfig: {options: [{name: ndots, value: "1"}]}` sur le pod | Supprime l'amplification pour ce pod. Casse les noms courts inter-namespace. |
| **NodeLocal DNSCache** (DaemonSet, écoute sur `169.254.20.10`) | Cache local par nœud, réponses en µs, et bascule en **TCP** vers CoreDNS. |

> ❓ **RETIENS ÇA** — Que fait `options ndots:5` dans un pod Kubernetes ?
> <details><summary>→ réponse</summary><br>Tout nom contenant <b>moins de 5 points</b> est d'abord essayé avec chacun des suffixes de <code>search</code> avant d'être essayé tel quel. Pour un nom externe court, ça produit 3 NXDOMAIN inutiles avant la bonne requête — multipliés par deux (A + AAAA). On l'évite avec un FQDN terminé par un point.</details>

> ⚠️ **PIÈGE — les timeouts DNS à exactement 5 secondes.** Symptôme : quelques pourcents des résolutions
> prennent pile 5,00 s. Cause : une **course dans conntrack** quand deux requêtes UDP (le A et le AAAA)
> partent du même port source vers la ClusterIP DNS et sont DNAT-ées « en même temps » — une des deux
> entrées est écrasée, la réponse est jetée, et le stub attend son `timeout:5` avant de réessayer.
> Contre-mesures : `single-request-reopen` dans `dnsConfig`, NodeLocal DNSCache (qui passe en TCP), ou
> kube-proxy en mode IPVS/nftables.

> 🧠 **MÉMO — le FQDN de service** : **« SErvice, NameSpace, SVC, CLUSTER.LOCAL »** → *SE-NS-SVC-CL*.
> Quatre étages, toujours dans cet ordre, du plus précis au plus général — comme une adresse postale.

### 2.10 DNSSEC — signer, pas chiffrer

Le DNS d'origine n'a **aucune authentification**. N'importe qui capable de répondre plus vite que le vrai
serveur, ou d'empoisonner un cache (attaque Kaminsky, 2008), redirige un nom. Les rustines historiques —
randomisation du port source, randomisation de casse (0x20) — augmentent l'entropie sans résoudre le
problème.

DNSSEC (RFC 4033-4035) apporte **l'authenticité et l'intégrité de l'origine**. Pas la confidentialité :
**une réponse DNSSEC circule toujours en clair**.

```
   Les 4 types, et à quoi ils servent
   ──────────────────────────────────────────────────────────────
   DNSKEY  (48)  la clé PUBLIQUE de la zone.
                 flag 257 = KSK (Key Signing Key, signe les DNSKEY)
                 flag 256 = ZSK (Zone Signing Key, signe les données)
   RRSIG   (46)  la SIGNATURE d'un ensemble d'enregistrements (RRset)
   DS      (43)  le HASH de la KSK de l'enfant, publié CHEZ LE PARENT
                 → c'est LUI qui fait la chaîne de confiance
   NSEC/NSEC3    la preuve d'ABSENCE (« entre alpha et gamma, il n'y a rien »)

   Chaîne de confiance
   ──────────────────────────────────────────────────────────────
   racine (trust anchor codé en dur dans le résolveur)
      │  signe le DS de  .fr
      ▼
    .fr  DNSKEY ── vérifie ──► signe le DS de exemple.fr
      │
      ▼
   exemple.fr DNSKEY ── vérifie ──► RRSIG de « api A 51.10.20.30 »   ✔
```

Algorithmes courants : **8** (RSASHA256), **13** (ECDSA P-256 / SHA-256, le plus déployé aujourd'hui pour la
compacité de ses signatures), **15** (Ed25519).

Ce que ça change en pratique :
- Une validation qui échoue donne **SERVFAIL**, pas une réponse fausse — « je préfère ne rien dire ».
- Le résolveur pose le bit **AD** quand il a validé ; le client peut poser **CD** pour valider lui-même.
- **Les réponses grossissent** : d'où EDNS0, le retour du TCP/53, et les échecs sur les pare-feux trop
  serrés.
- Un DS resté chez le parent après une rotation de KSK = **panne totale de la zone**, invisible pour ceux
  dont le résolveur ne valide pas. Signature de l'incident : ça marche depuis `1.1.1.1` avec `+cd`,
  SERVFAIL sans.

> ❓ **RETIENS ÇA** — DNSSEC chiffre-t-il les requêtes DNS ?
> <details><summary>→ réponse</summary><br><b>Non.</b> DNSSEC <b>signe</b> : il garantit que la réponse vient bien du détenteur de la zone et n'a pas été modifiée. Tout circule en clair et reste observable. La confidentialité, c'est le rôle de DoT/DoH/DoQ — problème orthogonal.</details>

> ❓ **RETIENS ÇA** — Quel enregistrement crée le lien de confiance entre une zone et son parent ?
> <details><summary>→ réponse</summary><br>Le <b>DS</b> (Delegation Signer) : c'est le <b>hash de la KSK de l'enfant, publié dans la zone du parent</b> et signé par le parent. C'est ce qu'on dépose chez le registrar. Sans DS à jour, la chaîne casse et la zone devient SERVFAIL pour tout résolveur validant.</details>

### 2.11 DoT, DoH, DoQ — chiffrer le transport

| | Port / transport | Reconnaissable ? | Où on le croise |
|---|---|---|---|
| **Do53** (classique) | UDP **53**, TCP 53 | oui, en clair | partout, par défaut |
| **DoT** (RFC 7858) | **TCP 853** + TLS | oui (port dédié) | Android « DNS privé », résolveurs d'entreprise |
| **DoH** (RFC 8484) | **HTTPS 443**, `POST/GET /dns-query` | **non** (noyé dans le HTTPS) | Firefox, Chrome, iOS |
| **DoQ** (RFC 9250) | **UDP 853** + QUIC | port dédié | récent, mobile |

L'arbitrage est politique autant que technique : DoT est chiffré mais **filtrable** (port 853 dédié) — ce
que veut un RSSI ; DoH est **indiscernable** du trafic web — ce que veut un utilisateur, et ce qui contourne
le split-horizon interne. Sur un poste d'entreprise, un navigateur en DoH ignore ton DNS interne et casse la
résolution des noms privés. La parade s'appelle le *canary domain* `use-application-dns.net` : s'il ne
résout pas, Firefox désactive DoH.

> 🧠 **MÉMO** — **DNSSEC = signature. DoT/DoH = enveloppe.** Une carte postale signée reste lisible par le
> facteur ; une lettre sous enveloppe non signée peut avoir été écrite par n'importe qui. Il faut les deux.

### 2.12 Diagnostiquer

```bash
dig api.exemple.fr A +noall +answer      # la réponse, rien d'autre
dig api.exemple.fr +trace                # refait la résolution DEPUIS LA RACINE
dig @ns1.exemple.fr api.exemple.fr       # interroge un autoritatif directement (court-circuite le cache)
dig exemple.fr SOA +short                # serial, TTL négatif
dig +dnssec exemple.fr                   # affiche les RRSIG, montre le bit AD
dig +tcp / +notcp / +bufsize=1232        # tester la troncature et EDNS0
dig -x 93.184.215.14                     # reverse : fabrique le in-addr.arpa pour toi
dig api.exemple.fr @10.96.0.10 +search   # depuis un pod, avec les search domains
```

Lire une sortie `dig` :

```
;; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 41235
;; flags: qr rd ra ad; QUERY: 1, ANSWER: 2, AUTHORITY: 0, ADDITIONAL: 1
                 │  │  │  └── ad  = DNSSEC validé
                 │  │  └───── ra  = le serveur fait la récursion
                 │  └──────── rd  = je l'ai demandée
                 └─────────── qr  = c'est une réponse
;; ANSWER SECTION:
api.exemple.fr.   287  IN  A  51.10.20.30
                   └── TTL restant : la valeur publiée est 300, il reste 287 → CACHE
;; Query time: 1 msec       ← 1 ms = cache. 40-150 ms = résolution complète.
```

> ⚠️ **PIÈGE** — `nslookup` est déprécié et **ment** : il masque les codes d'erreur, ne montre pas les
> drapeaux, et gère mal EDNS0/DNSSEC. Utilise `dig` (ou `kdig`, `drill`, `resolvectl query`). Et surtout :
> `ping` et `dig` **ne résolvent pas pareil** — `ping` passe par `getaddrinfo()`/NSS (donc `/etc/hosts`,
> mDNS, `search`), `dig` parle directement au serveur. Un nom qui « pingue » mais ne « digue » pas est
> presque toujours dans `/etc/hosts`.

### 2.13 Exercice corrigé — arithmétique des TTL

> **Énoncé.** `api.exemple.fr` a un TTL de 3600 s et pointe vers `51.10.20.30`. À 14 h 00, un résolveur
> d'opérateur met la réponse en cache. À 14 h 20, tu bascules l'enregistrement vers `51.10.20.99` et tu
> passes le TTL à 60 s.
> **(a)** À quelle heure au plus tard ce résolveur servira-t-il la nouvelle IP ?
> **(b)** Un client interroge ce résolveur à 14 h 50 : quel TTL voit-il, et quelle IP ?
> **(c)** Combien de temps dois-tu garder `51.10.20.30` en vie ?
> **(d)** Quelle procédure aurait ramené l'attente à 60 s ?

**Correction.**

**(a)** Le résolveur a mémorisé l'ancien enregistrement à 14 h 00 **avec son TTL de 3600 s**. Le fait
d'avoir changé le TTL côté autoritatif à 14 h 20 lui est totalement invisible : il ne reviendra pas
demander avant expiration. Expiration = 14 h 00 + 3600 s = **15 h 00**. C'est seulement à ce moment qu'il
repose la question et découvre `.99` avec le nouveau TTL de 60 s.

**(b)** À 14 h 50, l'entrée est en cache depuis 50 min = 3000 s. Il sert donc l'**ancienne** IP
`51.10.20.30`, avec un TTL restant de 3600 − 3000 = **600 s**. Ce client va lui-même garder l'ancienne
adresse jusqu'à 15 h 00.

**(c)** Au pire : dernier client servi juste avant l'expiration à 15 h 00, avec un TTL résiduel de 1 s, plus
la durée de vie des connexions déjà ouvertes et des caches applicatifs (JVM 30 s). Il faut garder l'ancienne
cible **jusqu'à 15 h 00 au minimum**, et en pratique **15 h 15 - 15 h 30** pour absorber la traîne.

**(d)** La procédure correcte : baisser le TTL de 3600 → 60 **d'abord**, puis attendre **au moins 3600 s**
que tous les caches ayant l'ancienne valeur l'aient purgée, **puis seulement** basculer l'IP. Fenêtre de
bascule ramenée à 60 s. Et remonter le TTL une fois la migration stabilisée.

> 🧠 **MÉMO** — **« On baisse le TTL une vieille-TTL à l'avance. »** Le changement de TTL ne rattrape jamais
> les caches déjà remplis ; il ne concerne que les résolutions futures.

---
## 3. DHCP — se faire attribuer une identité

### 3.1 Le problème : une machine qui vient de démarrer ne sait rien

Au démarrage, une machine a une adresse MAC (gravée) et **rien d'autre** : pas d'IP, pas de masque, pas de
passerelle, pas de DNS. Elle doit obtenir ces quatre informations… en communiquant sur un réseau IP, alors
qu'elle n'a pas d'adresse IP. Le paradoxe se résout par le **broadcast de couche 2** (R02) : `ff:ff:ff:ff:ff:ff`
n'exige aucune adresse IP pour être atteint.

Analogie : tu débarques dans un hôtel dont tu ne connais rien. Tu cries dans le hall « **quelqu'un aurait une
chambre ?** » ; plusieurs réceptionnistes répondent « chambre 214 » ; tu cries « **je prends la 214, celle de
Monsieur Dupont** » — assez fort pour que les autres réceptionnistes retirent leur offre ; et on te confirme,
avec la clé, le plan et l'heure du départ. C'est DORA, mot pour mot.

### 3.2 DORA

```
  CLIENT (0.0.0.0:68)                                   SERVEUR (:67)
        │                                                    │
        │───① DISCOVER ────────────────────────────────────► │  broadcast L2+L3
        │    src 0.0.0.0:68  dst 255.255.255.255:67          │  opt 53 = 1
        │    xid aléatoire, chaddr = ma MAC, opt 55 = liste  │
        │                                                    │
        │◄──② OFFER ──────────────────────────────────────── │  « je te propose yiaddr »
        │    yiaddr=10.0.5.42, opt 1/3/6/51, opt 54=serveur  │  opt 53 = 2
        │    (broadcast si le bit B est posé, sinon unicast) │
        │                                                    │
        │───③ REQUEST ─────────────────────────────────────► │  ENCORE EN BROADCAST :
        │    opt 50 = 10.0.5.42 , opt 54 = 10.0.5.1          │  les autres serveurs
        │    opt 53 = 3                                      │  retirent leur offre
        │                                                    │
        │◄──④ ACK ───────────────────────────────────────────│  opt 53 = 5, bail engagé
        │                                                    │  (ou NAK, opt 53=6, si conflit)
        │                                                    │
        ▼ ARP gratuit / ARP probe : « quelqu'un a déjà .42 ? »
          si oui → DECLINE (opt 53=4) et on recommence
```

Ce qu'il faut savoir dire sans hésiter :

| Détail | Valeur |
|---|---|
| Transport | **UDP**, client **68** ↔ serveur **67** (ports fixes des deux côtés, pas de port éphémère) |
| Base du format | **BOOTP** : partie fixe de **236 octets**, puis le magic cookie **0x63825363**, puis les options |
| Corrélation | `xid` (4 octets) — même xid pour les 4 messages |
| Champ d'adresse offerte | **`yiaddr`** (*your* address), pas `ciaddr` |
| Pourquoi le REQUEST est en broadcast | Pour que les **serveurs non retenus libèrent leur réservation** |
| Bit broadcast | `flags` 0x8000, posé par les clients incapables de recevoir un unicast avant d'avoir une IP |

> ❓ **RETIENS ÇA** — Pourquoi le message REQUEST de DORA est-il envoyé en broadcast alors que le client
> connaît déjà l'adresse du serveur ?
> <details><summary>→ réponse</summary><br>Pour informer <b>tous</b> les serveurs DHCP du segment de son choix. Ceux qui ne sont pas désignés (option 54, <i>server identifier</i>) libèrent immédiatement l'adresse qu'ils avaient réservée. Sans ce broadcast, chaque serveur d'un pool redondant immobiliserait une adresse par client.</details>

> 🧠 **MÉMO** — **D-O-R-A** : *Discover, Offer, Request, Acknowledge*. « **D**is-moi, **O**ffre-moi,
> **R**éclame, **A**ccepté. » Et les types d'option 53 dans le même ordre : **1, 2, 3, 5** — le **4**
> (DECLINE) est le raté qui te renvoie au début.

### 3.3 Le bail : T1, T2 et la ligne du temps

Une adresse n'est pas donnée, elle est **louée**. Le client doit la renouveler.

```
  0%                    50% (T1)              87,5% (T2)            100%
  ├──────────────────────┼──────────────────────┼────────────────────┤
  BOUND                RENEWING              REBINDING           EXPIRÉ
  je l'utilise      REQUEST en UNICAST     REQUEST en BROADCAST   je lâche l'IP
                    au serveur d'origine   à n'importe quel       → retour à DISCOVER
                                           serveur                → APIPA 169.254/16

  Bail 24 h (86400 s)  →  T1 = 43 200 s (12 h)   T2 = 75 600 s (21 h)
```

`T1 = 0,5 × bail` (option 58) et `T2 = 0,875 × bail` (option 59) — le serveur peut les imposer explicitement.
Le renouvellement réussi **ne repasse pas par DORA** : c'est un REQUEST/ACK, deux messages. Durées typiques :
**8 jours** par défaut sur Windows Server, **12 h ou 24 h** sur la plupart des serveurs Linux et box, quelques
minutes sur un réseau invité à fort renouvellement.

Dimensionner : un pool doit couvrir `pic de machines simultanées × (1 + marge)` **et** absorber les baux non
libérés (un laptop qui part sans RELEASE immobilise son adresse jusqu'à expiration). Bail court sur un réseau
volatil, bail long sur un réseau stable — un bail court multiplie le trafic DHCP et la charge du serveur.

### 3.4 Les options qui comptent

| Option | Nom | Contenu |
|---|---|---|
| **1** | Subnet mask | `255.255.255.0` |
| **3** | Router | la passerelle par défaut |
| **6** | DNS servers | liste ordonnée de résolveurs |
| 12 / 15 | Hostname / Domain name | nom, domaine |
| **26** | Interface MTU | **le levier MTU côté client** |
| 42 | NTP servers | l'heure — indispensable pour TLS et Kerberos |
| **51** | IP address lease time | durée du bail, en secondes |
| **53** | DHCP message type | **1 D, 2 O, 3 R, 4 DECLINE, 5 ACK, 6 NAK, 7 RELEASE, 8 INFORM** |
| **54** | Server identifier | **quel serveur** est retenu |
| **55** | Parameter request list | la liste des options que le client réclame |
| 58 / 59 | T1 / T2 | instants de renew / rebind |
| 66 / 67 | TFTP server / bootfile | **boot PXE** |
| **82** | Relay agent information | *circuit-id* / *remote-id*, posé par le relais |
| **121** | Classless static routes | routes supplémentaires poussées au client |
| 255 | End | fin des options |

> ⚠️ **PIÈGE** — Le client ne reçoit **que ce qu'il a demandé** dans l'option 55. Tu configures l'option 121
> côté serveur, elle n'apparaît pas chez le client : c'est presque toujours parce que son *parameter request
> list* ne la contient pas. Vérifie côté client avant d'accuser le serveur.

### 3.5 Le relais DHCP

Un broadcast ne franchit pas un routeur (R02/R03). Or les serveurs DHCP sont centralisés, un par datacenter,
pas un par VLAN. D'où le **relais** (`ip helper-address` chez Cisco, `dhcrelay` sous Linux) :

```
  VLAN 20 (10.0.20.0/24)                                   DC
  ┌────────┐  broadcast   ┌──────────────┐   UNICAST    ┌──────────┐
  │ client │─────────────►│   ROUTEUR    │─────────────►│ serveur  │
  └────────┘  255.255.…   │ = RELAIS DHCP│  vers 10.9.0.5│  DHCP    │
                          └──────────────┘              └──────────┘
   Ce que le relais modifie :
     • giaddr ← 10.0.20.1   (SON adresse sur le VLAN du client)
     • hops   ← hops + 1
     • option 82 (circuit-id / remote-id) ajoutée, si activée

   giaddr est LE champ décisif : le serveur DHCP y lit dans quel SCOPE piocher.
```

Sans `giaddr`, le serveur ne peut pas savoir de quel sous-réseau vient la demande et n'a aucune adresse de
retour. Retiens que le relais **ne fait pas que réémettre** : il **traduit un broadcast en unicast et signe
l'origine**.

> ❓ **RETIENS ÇA** — Quel champ permet au serveur DHCP de savoir dans quel pool piocher pour un client
> situé derrière un relais ?
> <details><summary>→ réponse</summary><br><b><code>giaddr</code></b> (<i>gateway IP address</i>), rempli par le relais avec sa propre adresse sur le segment du client. Le serveur choisit le scope dont le sous-réseau contient <code>giaddr</code>, et renvoie l'unicast à cette adresse.</details>

> ⚠️ **PIÈGE — le rogue DHCP.** N'importe qui branchant une box sur le LAN répond aussi vite (voire plus
> vite) que le serveur légitime, et devient la passerelle de tout le monde. Contre-mesure de couche 2 :
> **DHCP snooping**, qui n'autorise les OFFER/ACK que sur des ports déclarés *trusted*. En cloud, le
> problème n'existe pas : le DHCP est fourni par l'hyperviseur et l'adresse est imposée à l'ENI.

**DHCPv6 en une ligne** : ports **546** (client) / **547** (serveur), multicast `ff02::1:2`, séquence
**SOLICIT → ADVERTISE → REQUEST → REPLY** (SARR, l'équivalent de DORA), et coexistence avec **SLAAC** (l'auto-
configuration par Router Advertisement) — les drapeaux `M` et `O` du RA disent au client s'il doit passer par
DHCPv6.

---

## 4. NAT — parler sous un autre nom

### 4.1 Le problème : 4,3 milliards d'adresses, ça ne suffit pas

IPv4 offre 2³² = ~4,3 milliards d'adresses, dont une bonne part réservée. La RFC 1918 met de côté trois blocs
privés — `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` — **non routables sur Internet**. Tout le monde peut
les réutiliser ; c'est ce qui a sauvé IPv4. Mais un paquet dont la source est `10.0.5.42` ne peut pas revenir :
aucun routeur d'Internet ne sait où est ce `10.0.5.42`-là.

Le NAT (RFC 1631, puis 3022) résout ça en **réécrivant les adresses à la frontière**, et en mémorisant la
correspondance pour savoir défaire l'opération au retour.

Analogie : un **standard téléphonique d'entreprise**. Cent postes internes, un seul numéro public. Quand le
poste 42 appelle dehors, l'appelé voit le numéro de l'entreprise. Le standard note « ligne externe 3 ↔ poste
42 » et, quand la réponse arrive sur la ligne 3, il la bascule vers le 42. Le NAT, c'est ce carnet — et
**tout le problème du NAT est que ce carnet est fini, et que l'extérieur ne peut pas appeler un poste
directement**.

### 4.2 Les trois opérations

```
 SNAT — Source NAT (sortie) : on réécrit la SOURCE
 ───────────────────────────────────────────────────────────────────
   10.0.5.42:51234  ──►  [NAT]  ──►  203.0.113.7:51234  ──►  S3
        ▲ IP privée                     ▲ IP publique
   Retour : 203.0.113.7:51234 ──► [NAT consulte sa table] ──► 10.0.5.42:51234

 DNAT — Destination NAT (entrée) : on réécrit la DESTINATION
 ───────────────────────────────────────────────────────────────────
   client ──► 203.0.113.7:443  ──►  [NAT]  ──►  10.0.5.42:8443
   C'est ce que fait un port-forward, et ce que fait kube-proxy sur une ClusterIP.

 PAT / NAPT / « masquerade » : SNAT + réécriture du PORT SOURCE
 ───────────────────────────────────────────────────────────────────
   10.0.5.42:51234 ──┐
   10.0.6.11:51234 ──┼──► 203.0.113.7 :51234 / :51235 / :51236 …
   10.0.7.90:51234 ──┘     └── le PORT devient le discriminant
   → N machines derrière UNE adresse publique. C'est ce que fait ta box.
```

**La table de traduction** — chaque entrée est un **5-uplet** :

```
 proto  src orig         → src traduite      dst                état      ttl
 ──────────────────────────────────────────────────────────────────────────────
 tcp    10.0.5.42:51234  → 203.0.113.7:51234 52.95.128.10:443   ESTABLISHED 431990
 tcp    10.0.6.11:51234  → 203.0.113.7:51235 52.95.128.10:443   ESTABLISHED 431987
 udp    10.0.5.42:33001  → 203.0.113.7:33001 8.8.8.8:53         ASSURED         28
```

Sous Linux, c'est `nf_conntrack` : `conntrack -L`, compteur dans `/proc/sys/net/netfilter/nf_conntrack_count`,
plafond `nf_conntrack_max` (souvent 65 536 ou 262 144 selon la RAM). Timeouts par défaut à connaître :
**TCP established 432 000 s (5 jours)**, TCP `time_wait` **120 s**, **UDP 30 s** (180 s en flux établi),
ICMP 30 s. Un `nf_conntrack: table full, dropping packet` dans `dmesg` est un diagnostic, pas un avertissement.

> ❓ **RETIENS ÇA** — Quelle est la différence entre NAT et PAT ?
> <details><summary>→ réponse</summary><br>Le <b>NAT</b> « pur » traduit une adresse en une autre, 1 pour 1 — il ne réduit pas le besoin d'adresses publiques. Le <b>PAT</b> (aussi appelé NAPT, ou <i>masquerade</i>) traduit <b>adresse + port</b>, ce qui permet de multiplexer des milliers d'hôtes privés derrière une seule IP publique en se servant du port comme discriminant. Quand on dit « NAT » au quotidien, on parle presque toujours de PAT.</details>

### 4.3 Épuisement de ports — l'exercice corrigé

Le port source fait **16 bits** → 65 536 valeurs, dont on retire les ports bas : il reste en pratique
**~64 512 ports utilisables** (1024-65535) par adresse publique. Mais la vraie contrainte est plus subtile : ce
qui doit être unique, c'est le **5-uplet complet**.

> **Énoncé.** Un cluster Spark de 300 exécuteurs sort par une NAT Gateway avec **une** IP publique. Chaque
> exécuteur ouvre 200 connexions simultanées vers `s3.eu-west-3.amazonaws.com`.
> **(a)** Combien de connexions simultanées au total ?
> **(b)** Est-ce que ça passe si S3 était une IP unique sur le port 443 ?
> **(c)** Pourquoi, en pratique, ça passe quand même souvent ?
> **(d)** Le job passe à 900 exécuteurs. Que se passe-t-il, et comment le corriges-tu ?

**Correction.**

**(a)** 300 × 200 = **60 000 connexions simultanées**.

**(b)** Vers **une** destination unique (IP + port + protocole), le NAT doit attribuer 60 000 ports sources
distincts sur son unique IP publique. Il en a ~64 512. **Ça passe, mais à 93 % du plafond** — sans marge pour
les pics, les `TIME_WAIT` (120 s de rétention dans conntrack après fermeture !) ni les autres flux. AWS
documente d'ailleurs cette limite : **55 000 connexions simultanées par destination unique** et par NAT
Gateway, avec la métrique `ErrorPortAllocation` pour la surveiller. Donc **non, ça ne passe pas**.

**(c)** Parce que S3 n'est **pas** une IP unique : le service est servi par des dizaines d'adresses,
distribuées par le DNS. Chaque IP de destination différente **rouvre les 64 512 ports**. La contrainte
d'unicité porte sur le 5-uplet `(proto, IP src, port src, IP dst, port dst)`, pas sur le port seul. Un TTL DNS
court côté S3 est donc, involontairement, ce qui te sauve.

**(d)** À 900 exécuteurs : 180 000 connexions. Même en supposant 4 IP de destination distinctes, la
répartition n'est pas uniforme et tu franchis le plafond → `ErrorPortAllocation` monte, des connexions
échouent en `connect()` avec timeout, et les tâches Spark repartent en *retry* — le job s'effondre en cascade.
Les corrections, par ordre d'efficacité :

1. **Supprimer le NAT du chemin** : un **VPC Endpoint (Gateway) pour S3** fait sortir le trafic par une route
   directe, sans NAT du tout. C'est la bonne réponse en entretien.
2. **Plusieurs NAT Gateways** (une par AZ, ce qui est de toute façon la bonne pratique — et ça évite les
   frais de trafic inter-AZ).
3. **Réduire la concurrence** : pool de connexions HTTP réutilisées (keep-alive) plutôt qu'une connexion par
   requête. 200 connexions par exécuteur est un symptôme de client mal configuré.
4. Baisser les timeouts conntrack pour recycler plus vite — pansement, pas correction.

> 🧠 **MÉMO** — **« Le port n'est unique que dans son couloir. »** Le couloir, c'est le 5-uplet complet.
> Deux destinations différentes = deux couloirs = deux fois 64 512 ports.

### 4.4 Ce que le NAT casse, et pourquoi

Le NAT viole le **principe de bout en bout** : un intermédiaire modifie les en-têtes. Tout ce qui suppose que
l'adresse vue par l'émetteur est l'adresse vue par le récepteur casse.

| Ce qui casse | Pourquoi exactement |
|---|---|
| **FTP actif** | Le client envoie son IP **dans la charge utile** (commande `PORT`) ; le serveur essaie d'ouvrir une connexion vers une IP privée. Rustine : un *helper* ALG qui inspecte et réécrit le payload. FTP passif contourne. |
| **SIP / H.323 / WebRTC** | Idem : les adresses de flux média sont **dans le corps SDP**. D'où **STUN** (découvrir son IP publique), **TURN** (relayer si rien ne passe), **ICE** (essayer tous les chemins). |
| **IPsec AH** | L'authentification **couvre l'en-tête IP** : le réécrire invalide le hash. Sans issue. ESP s'en sort avec **NAT-T** : encapsulation dans **UDP 4500**. |
| **ICMP** | Pas de ports. Le NAT détourne l'`Identifier` de l'echo comme discriminant. Et pour les erreurs ICMP (`Fragmentation Needed`), il doit lire **le paquet original cité dedans** pour savoir à qui la rendre. |
| **P2P / connexions entrantes** | Personne ne peut initier vers l'intérieur : il n'y a pas d'entrée dans la table avant qu'un flux ne soit sorti. D'où le *hole punching*, l'UPnP, le PCP. |
| **Journalisation / attribution** | 5 000 abonnés derrière une IP publique (CGNAT) : identifier « qui » exige aussi le **port** et l'**horodatage**. |

**Hairpinning (ou NAT loopback)** — le cas où deux machines internes se parlent via le nom public :

```
       ┌────────────────── NAT / box ──────────────────┐
       │  IP publique 203.0.113.7  ── DNAT :443 → .42  │
       └───────────────────────────────────────────────┘
              ▲ ①                        ② │
   10.0.5.11 ─┘  « je vais sur 203.0.113.7:443 »  ▼ 10.0.5.42
   ③ La réponse part de 10.0.5.42 vers 10.0.5.11 EN DIRECT (même sous-réseau),
     avec pour source 10.0.5.42 — alors que le client attend une réponse
     de 203.0.113.7. Il la JETTE.  → connexion morte.

   Correction : le NAT doit AUSSI faire du SNAT sur le trajet interne, pour que
   la réponse repasse obligatoirement par lui. Beaucoup d'équipements ne le font pas.
```

La bonne parade n'est pas le hairpinning : c'est le **split-horizon DNS** (§2.8), qui fait résoudre le nom
public vers l'IP **privée** pour les clients internes. Le trafic ne monte jamais jusqu'au NAT.

> ❓ **RETIENS ÇA** — Pourquoi IPsec en mode AH est-il totalement incompatible avec le NAT ?
> <details><summary>→ réponse</summary><br>Parce que le condensat d'authentification d'AH <b>couvre les champs de l'en-tête IP</b>, y compris les adresses. Le NAT les modifie par construction, donc la vérification échoue toujours. ESP, lui, ne protège pas l'en-tête externe et peut traverser via <b>NAT-T</b>, qui encapsule dans UDP/4500.</details>

> ⚠️ **PIÈGE** — Le NAT **n'est pas un pare-feu**. Il bloque les connexions entrantes non sollicitées par
> **effet de bord** (pas d'entrée dans la table), pas par politique. Il ne filtre rien de ce qui sort, ne
> lit rien, ne journalise rien par défaut. Dire « on est derrière un NAT donc on est protégé » est une
> faute d'entretien.

**CGNAT** — quand l'opérateur lui-même est à court d'IPv4, il NAT ses abonnés une deuxième fois. La RFC 6598
réserve `100.64.0.0/10` pour ça. Conséquence : **double NAT**, aucun port entrant possible, et une IP publique
partagée entre des milliers d'abonnés.

---
## 5. Load balancing — un seul nom, plusieurs machines

### 5.1 Le problème : un serveur ne suffit jamais

Trois raisons, indépendantes, de mettre plusieurs machines derrière un point d'entrée : la **capacité** (une
machine plafonne), la **disponibilité** (une machine tombe), et le **déploiement** (retirer une machine du
trafic pour la mettre à jour sans coupure). Le DNS round-robin (§2.8) répond mal aux trois. Il faut un
équipement qui **voit l'état réel** des serveurs et décide **à chaque connexion**.

Vocabulaire : **VIP** (Virtual IP, l'adresse publique du service) → **pool / target group / upstream**
(l'ensemble des serveurs) → **backend / real server / endpoint** (une machine).

### 5.2 L4 contre L7 — l'arbitrage central

```
  LOAD BALANCER L4  (transport)              LOAD BALANCER L7  (application)
  ─────────────────────────────              ──────────────────────────────
  client ──TCP──► LB ──même TCP──► srv       client ──TCP①──► LB ──TCP②──► srv
         une seule connexion,                       DEUX connexions
         relayée / NAT-ée                           TERMINÉES de chaque côté

  Décide sur : IP src/dst, ports, proto      Décide sur : Host, path, en-têtes,
  Ne lit RIEN du contenu                     cookies, méthode, JWT, gRPC service
  TLS : passe à travers (passthrough)        TLS : TERMINÉ ici (déchiffré)
  Latence ajoutée : ~0,1-0,5 ms              Latence ajoutée : ~1-5 ms
  Débit : millions de pps                    Débit : dizaines de milliers de rps
  Retry : impossible                         Retry, timeout, circuit breaker : oui
  Granularité : la CONNEXION                 Granularité : la REQUÊTE
  Ex : NLB, IPVS, kube-proxy, Katran         Ex : ALB, nginx, HAProxy(http), Envoy, Traefik
```

Le point qui fait la différence en entretien : **avec HTTP/2 ou gRPC, un L4 ne répartit plus rien**. HTTP/2
multiplexe des milliers de requêtes dans **une seule connexion TCP** de longue durée ; un L4 la place sur un
backend et n'y touche plus. Résultat : 10 clients gRPC, 10 connexions, et un pool de 50 pods dont 40 restent
inactifs. Il faut un L7 (ou un client qui fait lui-même le *client-side LB*, ce que font gRPC et les mailles
de service).

> ❓ **RETIENS ÇA** — Pourquoi un load balancer L4 répartit-il mal du trafic gRPC ?
> <details><summary>→ réponse</summary><br>Parce qu'il répartit des <b>connexions</b>, pas des requêtes. gRPC s'appuie sur HTTP/2, qui multiplexe toutes les requêtes d'un client dans une <b>connexion TCP unique et persistante</b> : une fois placée sur un backend, toute la charge de ce client y reste. Il faut un LB L7 conscient de HTTP/2, ou un équilibrage côté client.</details>

> ⚠️ **PIÈGE** — Un L4 ne voit **pas** l'IP du client côté serveur si le trafic est NAT-é : le backend voit
> l'IP du LB. Les deux réponses : **PROXY protocol** (v1 texte / v2 binaire, un préambule inséré avant les
> octets applicatifs — il faut que le backend le comprenne, sinon il lit ça comme de la donnée) ou, en L7,
> les en-têtes `X-Forwarded-For` / `Forwarded` (RFC 7239).

### 5.3 Les algorithmes

| Algorithme | Principe | Quand c'est le bon choix | Défaut |
|---|---|---|---|
| **Round-robin** | chacun son tour | backends identiques, requêtes homogènes | ignore la charge réelle |
| **Weighted RR** | tour pondéré | parc hétérogène, canary (95/5) | poids à maintenir à la main |
| **Least connections** | le moins de connexions actives | durées de requête **très variables** | ignore le coût CPU d'une requête |
| **Least response time** | latence × connexions | sensibilité à la latence | oscille si mal amorti |
| **Random / P2C** | tirer 2 au hasard, garder le moins chargé | grands pools, LB **distribués** | quasi-optimal, sans état global |
| **Source IP hash** | `hash(IP src) mod N` | affinité sans cookie | **rehash total** si N change |
| **Hachage cohérent** | anneau / Maglev | **caches**, sharding, affinité stable | plus complexe |

**Pourquoi le hachage cohérent existe.** Avec `hash mod N`, passer de 10 à 11 backends déplace **~91 %** des
clés : chaque cache est vidé d'un coup, la base derrière prend tout. Avec un anneau cohérent, ajouter un
nœud à N n'en déplace que **1/(N+1)** — ici ~9 %.

```
   hash mod N,  N: 10 → 11        ~91 % des clés changent de backend   ✗
   anneau cohérent, 10 → 11       ~9 %  des clés changent              ✓
```

C'est **la** raison d'être du hachage cohérent, et c'est la question piège la plus fréquente sur ce chapitre.
Variantes de production : *ring hash* (nginx `hash ... consistent`, Envoy), **Maglev** (table de lookup de
taille première, Google) qui ajoute une bonne équité de répartition et une reconstruction rapide.

> ❓ **RETIENS ÇA** — Quel pourcentage de clés est redistribué quand on passe de 10 à 11 backends, en
> `hash mod N` puis en hachage cohérent ?
> <details><summary>→ réponse</summary><br><b>≈ 91 %</b> avec <code>hash mod N</code> (soit 10/11 : presque tout bouge). <b>≈ 9 %</b> avec un hachage cohérent, soit 1/(N+1) — seules les clés du nouveau nœud se déplacent.</details>

> 🧠 **MÉMO** — **RR pour l'uniforme, Least-conn pour l'irrégulier, Hash pour le collant.** Trois cas,
> trois algos. Si les requêtes durent toutes pareil → round-robin. Si certaines durent 200× plus longtemps
> (une requête analytique parmi des healthchecks) → least connections. S'il faut retomber sur la même
> machine → hachage, cohérent de préférence.

### 5.4 Health checks — et l'exercice de dimensionnement

Deux familles, complémentaires :

- **Actifs** : le LB sonde périodiquement (`GET /healthz`, ouverture TCP, requête SQL). Paramètres : `interval`,
  `timeout`, `rise` (succès consécutifs pour réintégrer), `fall` (échecs consécutifs pour éjecter).
- **Passifs** (*outlier detection*, *circuit breaking*) : le LB observe le **trafic réel** et éjecte un backend
  qui accumule des 5xx ou des timeouts. Réaction immédiate, aucun trafic de sonde.

Défauts à connaître : **HAProxy** `inter 2000ms`, `rise 2`, `fall 3` — **nginx** (passif) `max_fails=1`,
`fail_timeout=10s` — **AWS ALB** intervalle 30 s, timeout 5 s.

> **Énoncé.** HAProxy, `inter 2s`, `fall 3`, `rise 2`, `timeout check 1s`. Un backend gèle brutalement (il
> accepte le TCP mais ne répond plus).
> **(a)** Au bout de combien de temps est-il éjecté, au pire ?
> **(b)** Combien de requêtes clientes ont échoué pendant ce temps si le pool sert 4 000 rps sur 8 backends ?
> **(c)** Que se passe-t-il si tu descends à `inter 200ms`, `fall 2` ?
> **(d)** Pourquoi ne pas brancher le `/healthz` sur la base de données ?

**Correction.**

**(a)** Le gel peut survenir juste après un check réussi : on attend jusqu'à `inter` = 2 s avant le premier
check qui échoue, puis chaque check consomme `timeout check` = 1 s avant d'être compté en échec, et il en faut
`fall` = 3. Au pire, le chronomètre donne **2 (attente) + 1 (timeout, échec 1) + 2 + 1 (échec 2) + 2 + 1 (échec 3)
= 9 s**, soit `inter + fall × timeout + (fall − 1) × inter` = 2 + 3×1 + 2×2 = **9 s**. Ordre de grandeur à retenir : **`interval × fall` ≈ 6 s, jusqu'à ~9 s** avec les
timeouts. Formule d'entretien : **détection ≈ interval × fall (+ timeout)**.

**(b)** 4 000 rps sur 8 backends = 500 rps dirigés vers le backend mort. Sur ~9 s : **~4 500 requêtes en
erreur** (moins si le client rejoue et retombe ailleurs). C'est énorme — et c'est exactement l'argument pour
les health checks **passifs**, qui réagissent dès les premières erreurs réelles.

**(c)** Attention au piège : `timeout check` reste à **1 s**, et un backend *gelé* consomme ce timeout
entier à chaque sonde. La détection tombe à `0,2 + 1 + 0,2 + 1` ≈ **2,4 s**, pas à 0,4 s — pour descendre
sous la seconde il faudrait **aussi** baisser `timeout check`. (Un backend qui refuse franchement le TCP,
lui, échoue immédiatement : là on serait bien à `inter × fall` = 0,4 s.) Prix à payer : la fréquence des sondes passe de 0,5/s à 5/s **par
backend et par LB**. Avec 200 backends et 10 LB, ça fait **10 000 sondes/s** — un trafic parasite qui peut
dépasser le trafic utile, et surtout un risque de **faux positifs** : un micro-hoquet GC de 300 ms éjecte un
serveur sain, le trafic bascule sur les autres, qui saturent, et sont éjectés à leur tour. C'est la
**panne en cascade** classique.

**(d)** Parce qu'un `/healthz` qui teste une **dépendance partagée** transforme une panne partielle de cette
dépendance en **panne totale du service** : la base ralentit, les 200 backends échouent leur check **en même
temps**, le LB les éjecte **tous**, et il n'y a plus aucun backend sain — alors que 90 % du trafic n'avait pas
besoin de la base. Règle : le health check du LB (*liveness*/*readiness*) teste **ce que cette instance peut
faire seule**. Les dépendances se surveillent, elles ne s'éjectent pas.

> ⚠️ **PIÈGE** — La plupart des LB ont un **timeout d'inactivité** qui coupe silencieusement les longues
> requêtes : **ALB 60 s** par défaut, **NLB 350 s** (non modifiable historiquement), **nginx**
> `proxy_read_timeout 60s`. Une requête analytique de 90 s renvoie donc un **504** alors que la base a
> parfaitement répondu à 91 s. Les deux réponses : augmenter le timeout, ou passer en asynchrone
> (soumission + polling). Ne jamais laisser un pipeline dépendre d'une requête HTTP synchrone longue.

### 5.5 Persistance de session

| Méthode | Comment | Limite |
|---|---|---|
| **Source IP** | hash de l'IP client | s'effondre derrière un CGNAT (tout un opérateur = une IP) ; casse en mobilité |
| **Cookie inséré** | le LB pose son propre cookie (`SERVERID`, `AWSALB`) | L7 obligatoire ; le client doit accepter les cookies |
| **Cookie applicatif** | le LB apprend `JSESSIONID` | dépend de l'appli |
| **Session TLS** | ID / ticket de session | peu fiable avec la reprise de session moderne |
| **Hachage cohérent** | sur un en-tête, un JWT, un `user_id` | le bon choix quand il faut de l'affinité **stable** |

> ⚠️ **PIÈGE** — La persistance est un **aveu de dette technique** : elle existe parce que l'état est dans
> le serveur. Elle déséquilibre la répartition, empêche de retirer une machine proprement, et rend le
> scaling inutile pour les gros clients. La vraie correction est de **sortir l'état** (Redis, JWT signé,
> base). Garde la persistance pour ce qui la mérite vraiment : le *cache locality* (envoyer les mêmes clés
> au même nœud pour maximiser le taux de hit) — et là, hachage cohérent.

### 5.6 DSR — Direct Server Return

Quand la réponse est **beaucoup** plus grosse que la requête (streaming vidéo, téléchargement de datasets,
sortie de modèle), faire repasser tout le retour par le LB en fait un goulot d'étranglement.

```
   MODE PROXY / NAT classique          MODE DSR (Direct Server Return)
   ─────────────────────────           ────────────────────────────────
   client ──req──► LB ──req──► srv     client ──req──► LB ──req──► srv
   client ◄─rép─── LB ◄─rép─── srv     client ◄────────rép──────────┘
        tout passe par le LB                 le retour ÉVITE le LB

   Mécanique (L2 DSR) : le LB ne réécrit QUE l'adresse MAC de destination.
   IP source et IP destination (= la VIP) sont INCHANGÉES.
   Le serveur doit donc :
     • porter la VIP sur son interface loopback
     • ne PAS répondre aux ARP pour cette VIP
       (Linux : arp_ignore=1, arp_announce=2)
     • répondre au client avec la VIP en source
```

Coûts du DSR : LB et serveurs doivent être **sur le même segment L2** (ou en tunnel IPIP/GRE, mode « TUN » d'
IPVS), **aucun L7 possible** (le LB ne voit pas les réponses), pas de terminaison TLS, health checks limités,
et débogage franchement pénible. Gain : le LB ne traite que le trafic entrant — souvent **1/10 du volume**.

> ❓ **RETIENS ÇA** — En DSR, que réécrit le load balancer ?
> <details><summary>→ réponse</summary><br><b>Uniquement l'adresse MAC de destination</b> (en L2 DSR). Les adresses IP source et destination sont laissées intactes ; le serveur reçoit un paquet destiné à la VIP, qu'il porte sur sa loopback, et répond directement au client avec la VIP en adresse source. Le LB ne voit jamais le trafic de retour.</details>

### 5.7 Proxy, reverse proxy, load balancer

```
   PROXY DIRECT (forward)                REVERSE PROXY
   ──────────────────────                ───────────────
   clients internes ──► proxy ──► web    Internet ──► reverse proxy ──► mes serveurs
   Configuré par le CLIENT               Invisible du client
   Sert le CLIENT                        Sert le SERVEUR
   Sait qui est le client, pas le site   Sait quel site, pas qui est le client
   TLS : méthode CONNECT (tunnel)        TLS : terminé ici
   Cas : filtrage, cache d'entreprise,   Cas : LB L7, TLS offload, WAF, cache,
         sortie contrôlée d'un VPC             CDN, API gateway
```

Un **load balancer L7 est un reverse proxy** avec une politique de sélection de backend. Un reverse proxy avec
un seul backend reste un reverse proxy. La distinction n'est pas la technologie, c'est **de quel côté de la
conversation il est installé et qui l'a configuré**.

### 5.8 Tout ça dans Kubernetes

```
  Internet
     │
     ▼  ① Service type LoadBalancer → un NLB/ALB cloud (L4 ou L7)
  ┌────────────┐
  │  Ingress / │  ② Ingress Controller (nginx, Traefik) ou Gateway API
  │  Gateway   │     = un reverse proxy L7 DANS le cluster, routage Host/path
  └─────┬──────┘
        ▼  ③ Service ClusterIP  ← une VIP virtuelle qui n'existe sur AUCUNE interface
   ┌──────────────────────────────────────────────────────┐
   │  kube-proxy programme la règle de DNAT sur CHAQUE nœud│
   │   • mode iptables : chaînes probabilistes, O(n) règles│
   │   • mode IPVS     : table de hachage, O(1), + d'algos │
   │   • mode nftables : le remplaçant moderne d'iptables  │
   └──────────────────────────────────────────────────────┘
        ▼  ④ pods (Endpoints / EndpointSlices)
   ⑤ maille de service (Envoy sidecar) : mTLS, retry, P2C, outlier detection
```

Les cinq points à savoir dire :

1. Une **ClusterIP n'est portée par aucune machine**. C'est une entrée de règle NAT sur chaque nœud : le
   paquet est DNAT-é vers une IP de pod **au moment où il sort du pod émetteur**. Pinguer une ClusterIP ne
   prouve rien.
2. **`kube-proxy` est un load balancer L4**, sans health check applicatif : il retire un endpoint parce que le
   *readiness probe* du kubelet l'a marqué non prêt, pas parce qu'il a testé lui-même.
3. Le mode **iptables** insère des règles avec `statistic mode random probability` (1/n, puis 1/(n−1)…) : c'est
   du round-robin aléatoire. En mode **IPVS**, tu accèdes à `rr`, `wrr`, `lc`, `sh` — et à une complexité
   constante quand le nombre de services explose.
4. `externalTrafficPolicy: Local` **préserve l'IP source du client** (pas de SNAT au deuxième saut) mais ne
   route que vers les pods **du nœud d'entrée** — donc répartition déséquilibrée si les pods sont mal étalés.
   `Cluster` (défaut) équilibre bien mais SNAT et **perd l'IP source**.
5. Une **maille de service** (Istio/Linkerd) déplace le L7 dans un sidecar collé à chaque pod : équilibrage
   par requête (P2C par défaut dans Envoy), retries, timeouts, mTLS, et détection d'aberrants — au prix d'un
   saut supplémentaire (~0,3-1 ms) et de beaucoup de complexité.

> ⚠️ **PIÈGE — le MTU, encore.** Chaque encapsulation ampute le MTU utile : **VXLAN −50 o**, **GRE −24 o**,
> **WireGuard −60/−80 o**, **IPsec ESP −50 à −73 o**, un label MPLS −4 o. Sur un CNI en VXLAN, le MTU des pods
> tombe à **1450**. Si un équipement du chemin bloque les ICMP `Fragmentation Needed`, la **PMTUD** est
> aveugle : le handshake TCP passe (petits paquets) puis le transfert gèle dès la première grosse trame.
> Symptôme signature : « `curl` fonctionne, `kubectl logs` fonctionne, mais le téléchargement du modèle de
> 2 Go se fige à 0 % ». Correction : **MSS clamping** (`--clamp-mss-to-pmtu`) ou MTU cohérent de bout en bout.

---

## 6. Questions d'entretien

**1. Décris ce qui se passe entre le moment où je tape `curl https://api.exemple.fr` et l'ouverture du socket.**
La libc appelle `getaddrinfo()`, qui suit `/etc/nsswitch.conf` : `/etc/hosts` d'abord, puis DNS. Le stub
resolver lit `/etc/resolv.conf` et envoie une requête récursive en UDP/53 au résolveur, avec RD=1. Si le
résolveur n'a rien en cache, il interroge itérativement un serveur racine, qui le renvoie aux serveurs de
`.fr`, qui le renvoient aux autoritatifs de `exemple.fr`, lesquels répondent avec AA=1. Le résolveur cache
chaque réponse selon son TTL et rend l'adresse. Le client ouvre alors un TCP vers le port 443, puis fait le
handshake TLS avec SNI. Coût typique : 40-150 ms à froid, moins d'une milliseconde à chaud.

**2. `NXDOMAIN` et `NOERROR` avec zéro réponse : quelle différence ?**
`NXDOMAIN` signifie que le nom **n'existe pas du tout** dans la zone. `NOERROR` avec `ANCOUNT=0` — appelé
NODATA — signifie que le nom existe mais **ne porte pas d'enregistrement du type demandé** : typiquement un
`AAAA` demandé sur un nom qui n'a qu'un `A`. Les deux sont cachables négativement, pour la durée donnée par le
dernier champ du SOA de la zone. Confondre les deux produit des bugs en dual-stack, où une pile IPv6 conclut à
tort que le service est inexistant.

**3. Pourquoi ne peut-on pas mettre un CNAME à l'apex d'une zone ?**
Parce qu'un nom portant un `CNAME` ne peut porter aucun autre type d'enregistrement, et que l'apex porte
obligatoirement un `SOA` et des `NS`. La contradiction est structurelle, pas une limite d'implémentation. Les
contournements sont l'`ALIAS`/`ANAME` propriétaire — l'*Alias record* de Route 53, résolu côté serveur — le
*CNAME flattening* de Cloudflare, ou l'enregistrement standard `HTTPS` (type 65) qui est, lui, légal à l'apex.

**4. Un client DHCP ne reçoit pas d'adresse ; il est sur un VLAN distant. Que vérifies-tu ?**
D'abord si le `DISCOVER` sort : un `tcpdump -i any port 67 or 68` sur le switch d'accès. Ensuite le relais :
`ip helper-address` configuré sur l'interface SVI du VLAN, pointant vers le bon serveur. Puis `giaddr` dans le
paquet reçu côté serveur — s'il est à zéro, le relais ne fait pas son travail, et le serveur ne sait pas dans
quel scope piocher. Ensuite le scope lui-même : existe-t-il pour ce sous-réseau, reste-t-il des adresses
libres, y a-t-il des baux fantômes ? Enfin la route de retour vers `giaddr`, et un éventuel serveur pirate qui
répondrait plus vite.

**5. 300 workers derrière une seule NAT Gateway écrivent sur S3 et le job échoue par intermittence. Diagnostic ?**
Je suspecte l'épuisement de ports. La contrainte est l'unicité du 5-uplet : environ 64 512 ports par IP
publique et par destination unique — AWS documente 55 000 connexions simultanées par destination pour une NAT
Gateway. Je vérifie la métrique `ErrorPortAllocation`. La correction propre est de sortir le NAT du chemin
avec un VPC Endpoint de type Gateway pour S3 : le trafic ne passe plus du tout par la NAT Gateway, et c'est
aussi moins cher. Ensuite : une NAT Gateway par AZ, et surtout un client HTTP avec pool de connexions
réutilisées, parce que 200 connexions simultanées par worker est un symptôme de mauvaise configuration.

**6. Pourquoi le NAT casse-t-il le FTP actif, et pas le passif ?**
En FTP actif, le client transmet sa propre adresse IP et un port **dans la charge utile**, via la commande
`PORT` ; le serveur ouvre alors une connexion **vers le client**. Derrière un NAT, cette adresse est privée et
la connexion entrante n'a aucune entrée dans la table de traduction : elle échoue. En passif, c'est le
**client** qui initie la seconde connexion, vers une adresse et un port fournis par le serveur — donc un flux
sortant, que le NAT gère naturellement. Le remède historique pour l'actif est un helper ALG qui inspecte et
réécrit le payload, ce qui est fragile et incompatible avec le chiffrement.

**7. L4 ou L7 pour un service gRPC interne à fort débit ?**
Un L4 seul est un mauvais choix : gRPC repose sur HTTP/2, qui multiplexe toutes les requêtes dans une
connexion TCP persistante. Le L4 place cette connexion sur un backend une fois pour toutes, et l'équilibrage
disparaît — quelques pods saturés, le reste inactif. Il faut soit un L7 conscient de HTTP/2 qui répartit
requête par requête, soit un équilibrage côté client, ce que font le résolveur gRPC et les mailles de service.
Si la latence interdit un saut de proxy supplémentaire, la maille en sidecar est le bon compromis : elle fait
du L7 sans traverser le réseau une fois de plus.

**8. Comment dimensionner un health check ?**
Le temps de détection vaut approximativement `interval × fall`, plus le `timeout` du dernier check. Descendre
l'intervalle réduit la fenêtre d'erreurs mais augmente le trafic de sonde — il se multiplie par le nombre de
backends **et** par le nombre de load balancers — et surtout augmente le risque de faux positifs, qui éjectent
un serveur sain sur un hoquet GC et peuvent déclencher une panne en cascade. Je combine donc un check actif
modéré, de l'ordre de 2 s d'intervalle avec `fall 3`, et une détection passive d'aberrants qui réagit en
quelques requêtes réelles. Et je m'assure que l'endpoint de santé ne teste **aucune dépendance partagée**.

**9. Un pod met parfois exactement 5 secondes à résoudre un nom. Explication ?**
C'est la course conntrack sur le DNS de Kubernetes. Le stub envoie la requête `A` et la requête `AAAA` depuis
le **même port source** quasi simultanément ; les deux sont DNAT-ées vers la ClusterIP de CoreDNS, deux
entrées conntrack sont créées en parallèle, l'une écrase l'autre et une réponse est jetée. Le client attend
alors son `timeout` de 5 s avant de réessayer. Les remèdes : `single-request-reopen` via `dnsConfig`,
NodeLocal DNSCache — qui répond localement et parle en TCP à CoreDNS — ou kube-proxy en IPVS/nftables. J'en
profiterais pour vérifier `ndots:5`, qui quadruple souvent le volume de requêtes en amont.

**10. Un pipeline qui interroge une API interne renvoie des 504 sur les gros extraits, jamais sur les petits.**
Signature d'un **timeout d'inactivité du load balancer** : la requête longue dépasse le délai — 60 s par
défaut sur un ALB, `proxy_read_timeout 60s` sur nginx — et le LB coupe alors que le backend calcule encore.
Le 504 vient du LB, pas de l'application : je le confirme en comparant les logs du LB et ceux du backend, qui
montrera une requête terminée avec succès après la coupure. Deuxième hypothèse si les tailles sont en cause
plutôt que les durées : un problème de **MTU/PMTUD** sur un chemin encapsulé, qui gèle les gros transferts.
La bonne correction n'est pas seulement d'augmenter le timeout : c'est de rendre l'extraction asynchrone —
soumission, identifiant de job, récupération du résultat.

---

## 7. Les 3 choses à retenir si tu ne retiens que ça

**1. Le DNS n'est pas un annuaire, c'est une hiérarchie de délégations doublée d'un système de caches — et
c'est le cache qui gouverne ta vie.** Le résolveur récursif fait tout le travail, les autoritatifs ne font
qu'aiguiller, et chaque enregistrement porte un TTL qui décide combien de temps le monde entier gardera ta
vieille réponse. D'où la seule règle qui compte pour une migration : **on baisse le TTL une durée d'ancien TTL
à l'avance, puis seulement on bascule.** Et n'utilise jamais le DNS comme mécanisme de bascule rapide : pour
ça, on déplace une adresse (VIP, anycast), pas un nom.

**2. NAT et load balancing sont le même geste — réécrire des en-têtes et tenir une table d'état — avec deux
intentions différentes.** Le NAT réécrit la source pour économiser des adresses, le LB réécrit la destination
pour choisir une machine. Les deux ont donc les mêmes pathologies : une **table qui se remplit** (épuisement
de ports, conntrack plein), un **état à maintenir** que rien ne réplique, et une **rupture du bout en bout**
qui casse tout ce qui met une adresse dans sa charge utile — FTP actif, SIP, IPsec AH. Quand quelque chose ne
marche « que dans un sens », cherche l'entrée manquante dans une table de traduction.

**3. Les pannes d'infrastructure sont presque toujours des pannes de configuration par défaut.** `ndots:5` qui
quadruple tes requêtes DNS, le timeout à 60 s d'un ALB sur une requête de 90 s, la JVM qui cache 30 s en
ignorant ton TTL, le MTU à 1450 sur un CNI VXLAN, les 55 000 connexions d'une NAT Gateway, les 5 jours de
timeout conntrack sur du TCP établi. Aucun de ces chiffres n'est visible dans le code, aucun n'apparaît dans
un test d'intégration, et chacun produit une panne intermittente que personne ne relie à sa cause. **Connaître
ces valeurs par cœur est exactement ce qui sépare quelqu'un qui débogue en dix minutes de quelqu'un qui
débogue en trois jours.**
