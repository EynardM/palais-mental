# D02 — Linux réseau & performance : ip, ss, nft, namespaces, /proc

> **Ce que tu sauras faire à la fin**
> - Diagnostiquer une panne réseau **dans l'ordre**, en 8 étages, sans jamais dire « ça marche pas » : interface, adresse, voisin, route, DNS, socket, filtrage, application.
> - Lire et écrire les commandes `ip link / addr / neigh / route / rule` et `ss`, et **interpréter chaque colonne** de leur sortie plutôt que la survoler.
> - Écrire un filtre BPF `tcpdump` juste du premier coup, savoir **où** dans la pile le paquet est capturé, et lire une trace ligne par ligne pour distinguer un drop de pare-feu d'un port fermé.
> - Réciter l'**ordre de traversée de Netfilter** (5 crochets, 5 tables, 10 étapes) et expliquer avec ça, exactement, ce que font Docker et kube-proxy sous le capot.
> - Fabriquer **à la main** ce que Docker fabrique pour toi : un network namespace, une paire veth, un bridge, du forwarding et du MASQUERADE — et savoir ce qui casse si tu oublies une étape.
> - Trouver le goulot d'étranglement d'une machine en 60 secondes (CPU / mémoire / disque / réseau) avec la méthode USE, `vmstat`, `iostat`, `ss -ti`, `nstat` et `/proc/pressure`.
>
> **Pourquoi ça compte dans ton poste**
> Un pipeline de données, c'est du réseau qui traverse des conteneurs. Kafka, Spark, Trino, un connecteur JDBC : tout
> ça vit dans des namespaces, sort par des veth, traverse un bridge, se fait NATer deux fois et finit dans une table
> conntrack. Quand un job qui prenait 20 minutes en prend 4 heures, la réponse est presque toujours dans une des
> commandes de ce module — et le seul moyen d'y arriver vite est de savoir **dans quel ordre** les taper. Côté IA,
> les compteurs `/proc/net/*`, `ss -ti` et conntrack sont exactement les séries temporelles que tu vas ingérer pour
> faire de la détection d'anomalie réseau : tu dois savoir ce qu'elles mesurent avant de les modéliser.
>
> **Prérequis** : `R01` (couches, encapsulation), `R02` (Ethernet, MAC, ARP, MTU), `R03` (IPv4, CIDR), `R04` (table de routage), `R06` (TCP, états, fenêtres), `R07` (DNS, NAT, LB), `D01` (processus, systemd, descripteurs de fichiers).
> **Durée de lecture** : 85-95 min. Les sections 20 et 24 se font **clavier sous les doigts**, pas en lisant.

---

## 1. Le problème : « ça ne marche pas », par où on commence

Un collègue te dit : « le worker n'arrive pas à joindre Kafka ». Tu as environ quinze causes possibles et
trois minutes avant qu'on te redemande où ça en est. Le réflexe du débutant est de taper `ping`, puis de
regarder les logs de l'application, puis de redémarrer quelque chose. Le réflexe du bon ingénieur est de
**descendre la pile dans l'ordre**, parce que chaque couche dépend de la précédente et qu'un test raté en
bas rend tous les tests du haut ininterprétables.

```
   QUESTION                                    OUTIL              SI ÇA CASSE ICI
 ┌────────────────────────────────────────┬──────────────────┬────────────────────┐
 │ 8. L'appli répond-elle correctement ?  │ curl -v          │ bug applicatif     │
 │ 7. Un filtre jette-t-il le paquet ?    │ nft list ruleset │ pare-feu           │
 │ 6. Le port écoute-t-il, sur QUELLE IP ?│ ss -lntp / nc -zv│ bind 127.0.0.1     │
 │ 5. Le nom se résout-il ?               │ getent / dig     │ DNS                │
 │ 4. Ai-je une ROUTE vers la cible ?     │ ip route get     │ passerelle absente │
 │ 3. Le voisin L2 répond-il ?            │ ip neigh         │ VLAN, ARP, câble   │
 │ 2. Ai-je une ADRESSE IP ?              │ ip -br addr      │ DHCP mort, 169.254 │
 │ 1. L'interface est-elle UP ?           │ ip -br link      │ NO-CARRIER, câble  │
 └────────────────────────────────────────┴──────────────────┴────────────────────┘
     ↑ on lit de BAS en HAUT : on ne monte que si l'étage du dessous est vert
     tcpdump n'est pas un étage : il traverse les étages 4 à 7 et dit OÙ le paquet disparaît
```

Ce module est la boîte à outils de ces huit lignes, plus la couche du dessous qui explique *pourquoi* elles
existent (Netfilter, namespaces, `/proc`), plus la méthode de perf pour quand ça marche mais que c'est lent.

> 🧠 **MÉMO** — **« I A V R D S F A »** : **I**nterface, **A**dresse, **V**oisin, **R**oute, **D**NS, **S**ocket,
> **F**iltre, **A**ppli. *« Il A Vraiment Rien Dit Sur Fanny Aujourd'hui »*. Huit étages, toujours dans cet ordre,
> jamais de saut. La moitié des pannes se règle aux étages 1 à 3.

---

## 2. iproute2 : pourquoi les vieilles commandes mentent

`ifconfig`, `route`, `netstat`, `arp` viennent du paquet **net-tools**, écrit dans les années 90. Ils sont
dépréciés depuis ~2001 et absents par défaut de la plupart des images de conteneurs. Ce n'est pas une
question de mode : **ils affichent une vision fausse du noyau moderne.**

La raison est technique. net-tools lit des **fichiers texte** dans `/proc/net/` (`/proc/net/dev`,
`/proc/net/route`, `/proc/net/tcp`), un format figé qui date d'avant les adresses multiples, les tables de
routage multiples et IPv6. iproute2 parle **netlink** (socket `AF_NETLINK`, famille `NETLINK_ROUTE`), l'API
binaire officielle du noyau : tout ce que le noyau sait, netlink le rend.

```
     net-tools (ifconfig, route, netstat)      iproute2 (ip, ss)
     ┌───────────────────────────┐             ┌───────────────────────────┐
     │  parse du TEXTE           │             │  messages BINAIRES        │
     │  /proc/net/dev            │             │  socket AF_NETLINK        │
     │  /proc/net/route          │             │  NETLINK_ROUTE / SOCK_DIAG│
     │  /proc/net/tcp  (O(n²))   │             │  filtrage côté NOYAU      │
     └───────────┬───────────────┘             └───────────┬───────────────┘
                 │  vision PARTIELLE, figée                │ vision COMPLÈTE
                 ▼                                         ▼
     ✗ 1 seule IP par interface (alias eth0:0)   ✓ N adresses par interface
     ✗ table "main" uniquement                   ✓ 2³² tables + ip rule
     ✗ pas de policy routing, pas de VRF         ✓ VRF, netns, mpls, xfrm
     ✗ IPv6 bricolé                              ✓ IPv6 de première classe
     ✗ netstat -a lent sur 100k sockets          ✓ ss instantané
```

| Ancien | Nouveau | Ce que l'ancien ne voit pas |
|---|---|---|
| `ifconfig` | `ip addr` / `ip link` | les adresses secondaires ajoutées par `ip`, les scopes, `valid_lft` |
| `ifconfig eth0 up` | `ip link set eth0 up` | — |
| `route -n` | `ip route` | les tables ≠ main, les routes de policy, les métriques |
| `arp -an` | `ip neigh` | l'**état** de l'entrée (STALE, PROBE…), IPv6/NDP |
| `netstat -tulpn` | `ss -tulpn` | rien, mais 100× plus lent à 50 000 sockets |
| `netstat -s` | `nstat` / `nstat -az` | `nstat` affiche les **deltas** depuis le dernier appel |
| `netstat -i` | `ip -s link` | — |
| `iptables` | `nft` | les règles écrites côté nftables natif |

Le point le plus dangereux : **`ifconfig` ne montre qu'UNE adresse par interface.** Si quelqu'un a fait
`ip addr add 10.0.5.7/24 dev eth0` en plus de l'adresse DHCP, `ifconfig` ne la voit pas. Tu peux passer une
heure à chercher « d'où vient cette IP » qui est sous ton nez.

> ❓ **RETIENS ÇA** — Pourquoi `ifconfig` peut-il afficher une seule IP alors que l'interface en porte trois ?
> <details><summary>→ réponse</summary><br>Parce que net-tools lit un format <code>/proc</code> hérité qui ne modélise qu'une adresse principale (+ des alias <code>eth0:0</code>), alors que le noyau, lui, stocke une <b>liste</b> d'adresses par interface, accessible seulement via <b>netlink</b> — donc via <code>ip addr</code>.</details>

> ⚠️ **PIÈGE** — `netstat -tulpn` sur une machine à 200 000 sockets peut prendre **plusieurs minutes** et
> charger un cœur à 100 %. Il lit et parse `/proc/net/tcp` en entier, ligne par ligne, en refaisant une
> recherche dans `/proc/*/fd` pour chaque socket afin de retrouver le processus. `ss` interroge le noyau via
> `sock_diag` avec le **filtre poussé dans le noyau** : le noyau ne renvoie que ce qui matche. Sur un nœud
> Kubernetes chargé, c'est la différence entre 0,2 s et 4 minutes.

**Options universelles d'`ip` — à connaître par cœur, elles changent la vie :**

| Option | Effet |
|---|---|
| `-br` | *brief* : une ligne par objet, colonnes alignées. Le mode qu'on veut 90 % du temps. |
| `-c` | couleurs (états UP/DOWN évidents) |
| `-4` / `-6` | ne montre que IPv4 / IPv6 |
| `-s` | statistiques (compteurs de paquets, erreurs) |
| `-d` | *details* : paramètres du type de device (VLAN id, VXLAN vni, bridge…) |
| `-j -p` | sortie **JSON** indentée → parsable dans un script/pipeline |
| `-n <ns>` | exécute dans le network namespace `<ns>` (= `ip netns exec <ns> ip …`) |

```bash
ip -c -br addr          # la commande la plus rentable du module
ip -j -p route | jq .   # routage en JSON, exploitable dans un collecteur
```

---

## 3. `ip link` — la couche 2 vue de l'hôte

**La question** : le câble (ou le vSwitch) est-il branché, et l'interface est-elle allumée ? Ce sont **deux
questions différentes**, et c'est là que 100 % des débutants se trompent.

```bash
$ ip -s link show eth0
2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc fq_codel state UP mode DEFAULT group default qlen 1000
    link/ether 06:1f:3a:9c:4e:22 brd ff:ff:ff:ff:ff:ff
    RX:  bytes        packets  errors  dropped overrun mcast
    148923847612      91238471 0       1043    0       82341
    TX:  bytes        packets  errors  dropped carrier collsns
    98234712398       78123094 0       0       0       0
```

Ligne par ligne :

- **`2:`** — l'*ifindex*, le numéro d'interface dans **ce** namespace. `lo` est toujours 1. Cet index est ce
  que tu retrouves dans les logs noyau et dans les veth (`eth0@if17` = « mon pair est l'ifindex 17 dans un
  autre namespace »). C'est la clé pour relier un conteneur à son veth côté hôte.
- **`<BROADCAST,MULTICAST,UP,LOWER_UP>`** — les *flags*. **`UP` = état administratif** : quelqu'un a fait
  `ip link set eth0 up`. **`LOWER_UP` = porteuse détectée**, il y a physiquement du signal. Les deux sont
  indépendants.
- **`mtu 1500`** — la taille utile maximale d'une trame. 1500 sur Ethernet standard, 65536 sur `lo`, 8951 ou
  9001 en jumbo cloud, **1450** derrière un VXLAN (50 octets d'encapsulation), 1420-1440 derrière WireGuard.
- **`qdisc fq_codel`** — la discipline de file d'attente en sortie. Défaut moderne des distributions,
  remplace `pfifo_fast`. Un bridge ou `lo` affiche `noqueue` (pas de file, remise directe).
- **`state UP`** — l'état *opérationnel* consolidé. `DOWN` = éteint administrativement. **`NO-CARRIER`** = tu
  l'as allumée mais il n'y a pas de signal : câble débranché, SFP mort, port du switch désactivé, ou côté
  conteneur, **le pair de la veth n'est pas monté**.
- **`qlen 1000`** — `txqueuelen`, profondeur de la file d'émission. Défaut 1000 sur Ethernet, 0 sur les
  interfaces virtuelles sans file.
- **`link/ether 06:1f:...`** — l'adresse MAC. Un premier octet avec le bit 2 à 1 (`02`, `06`, `0a`, `0e`…)
  signale une MAC **administrée localement** : c'est la signature d'une interface virtuelle (VM cloud,
  veth, tap), pas d'une carte physique.

**Les compteurs** (colonne `errors` vs `dropped`, distinction essentielle) :

| Compteur | Sens | Cause typique |
|---|---|---|
| `RX errors` | trame **abîmée** : CRC faux, trop longue, désalignée | câble, SFP, duplex, EMI |
| `RX dropped` | trame **saine mais jetée** par l'hôte | buffer plein, VLAN inconnu, pas de socket, `netdev_max_backlog` atteint |
| `RX overrun` | le ring buffer NIC a débordé | trafic en rafale > capacité de traitement, IRQ mal réparties |
| `TX carrier` | perte de porteuse à l'émission | lien instable, négociation |
| `TX dropped` | jeté par la qdisc | file pleine, shaping |

> ❓ **RETIENS ÇA** — Quelle différence entre `UP` et `LOWER_UP` dans les flags d'une interface ?
> <details><summary>→ réponse</summary><br><code>UP</code> = état <b>administratif</b> (on a allumé l'interface). <code>LOWER_UP</code> = <b>porteuse physique présente</b>. <code>UP</code> sans <code>LOWER_UP</code> donne <code>NO-CARRIER</code> : allumée mais rien au bout du câble.</details>

> ❓ **RETIENS ÇA** — `RX errors` à 0 mais `RX dropped` qui grimpe : où chercher ?
> <details><summary>→ réponse</summary><br>Pas dans le câble. La trame est arrivée intacte : c'est l'<b>hôte</b> qui la jette — buffer socket plein, backlog noyau saturé, VLAN non configuré, ou aucun socket en écoute. Regarde <code>/proc/net/softnet_stat</code> et <code>ss -lnt</code>.</details>

**Créer et manipuler des interfaces** (c'est la base de la section 19) :

```bash
ip link set eth0 up                          # allumer
ip link set eth0 mtu 9000                    # jumbo frames
ip link add br0 type bridge                  # switch virtuel
ip link add veth0 type veth peer name veth1  # câble virtuel (toujours par PAIRE)
ip link set veth1 master br0                 # brancher veth1 sur le switch br0
ip link add link eth0 name eth0.42 type vlan id 42   # sous-interface VLAN
ip link set eth0 promisc on                  # mode promiscuous (ce que fait tcpdump)
ip -d link show vxlan0                       # -d révèle vni, port, remote…
```

> 🧠 **MÉMO** — **`link` = le câble. `addr` = le nom sur la boîte aux lettres. `neigh` = le carnet d'adresses
> des voisins. `route` = le plan de la ville.** Quatre sous-commandes, quatre couches de la même question :
> « comment ce paquet sort d'ici ? »

---

## 4. `ip addr` — les adresses, les scopes, les baux

```bash
$ ip -br addr
lo               UNKNOWN        127.0.0.1/8 ::1/128
eth0             UP             10.0.1.12/24 fe80::41f:3aff:fe9c:4e22/64
docker0          DOWN           172.17.0.1/16

$ ip addr show eth0
2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc fq_codel state UP group default qlen 1000
    link/ether 06:1f:3a:9c:4e:22 brd ff:ff:ff:ff:ff:ff
    inet 10.0.1.12/24 brd 10.0.1.255 scope global dynamic eth0
       valid_lft 2591643sec preferred_lft 2591643sec
    inet 10.0.1.99/32 scope global secondary eth0
    inet6 fe80::41f:3aff:fe9c:4e22/64 scope link
       valid_lft forever preferred_lft forever
```

- **`/24` n'est pas décoratif.** Le préfixe attaché à l'adresse dit au noyau **quelle plage est directement
  joignable en L2**, et déclenche automatiquement l'installation d'une route « connected » vers
  `10.0.1.0/24`. Mettre `/32` au lieu de `/24` est l'erreur classique : plus aucun voisin n'est considéré
  comme local, tout doit passer par une route explicite.
- **`scope`** — la portée de validité :

| Scope | Sens | Exemple |
|---|---|---|
| `global` | routable, utilisable partout | `10.0.1.12` |
| `link` | valable seulement sur ce lien | `fe80::/10`, `169.254.0.0/16` |
| `host` | ne quitte jamais la machine | `127.0.0.1` |

- **`dynamic` + `valid_lft`** — l'adresse vient d'un **bail DHCP** (ou d'un RA IPv6). `valid_lft 2591643sec`
  ≈ 30 jours. Si tu vois `valid_lft` descendre vers 0 et personne pour renouveler, l'adresse **disparaîtra**
  et la machine tombera du réseau.
- **`secondary`** — adresse supplémentaire sur la même interface. Invisible pour `ifconfig`.
- **`brd 10.0.1.255`** — l'adresse de diffusion, dérivée du préfixe.

```bash
ip addr add 10.0.1.99/24 dev eth0            # ajouter (non persistant : perdu au reboot)
ip addr del 10.0.1.99/24 dev eth0            # retirer
ip addr flush dev eth0                       # tout enlever (attention en SSH…)
ip -4 -br addr | awk '{print $1, $3}'        # inventaire scriptable
```

> ⚠️ **PIÈGE** — Tout ce que tu fais avec `ip` est **en RAM et volatile**. Un `reboot`, un `systemctl restart
> systemd-networkd`, un `netplan apply` et c'est effacé. La persistance vit ailleurs : `/etc/netplan/*.yaml`,
> `/etc/NetworkManager/`, `/etc/systemd/network/*.network`, `/etc/sysconfig/network-scripts/`. En incident,
> `ip` est parfait pour **tester** ; ensuite tu écris la conf.

> ❓ **RETIENS ÇA** — Que se passe-t-il si tu configures `10.0.1.12/32` au lieu de `10.0.1.12/24` ?
> <details><summary>→ réponse</summary><br>Le noyau n'installe plus la route connectée <code>10.0.1.0/24 dev eth0</code>. Plus aucun voisin du LAN n'est joignable directement : même la passerelle devient inaccessible (« Network is unreachable »), sauf à ajouter une route <code>onlink</code> explicite.</details>

---

## 5. `ip neigh` — la table de voisinage et sa machine à états

**La question** : j'ai un paquet pour `10.0.1.1`, qui est sur mon LAN. Pour construire la trame Ethernet il
me faut sa **MAC**. Où je la trouve, et pendant combien de temps je la garde ?

C'est ARP en IPv4 (`R02`), NDP/ICMPv6 en IPv6. Sous Linux, les deux alimentent **la même table**, celle
qu'affiche `ip neigh`.

```bash
$ ip neigh
10.0.1.1   dev eth0 lladdr 0a:58:0a:00:01:01 REACHABLE
10.0.1.44  dev eth0 lladdr 06:2b:19:77:c1:03 STALE
10.0.1.77  dev eth0  FAILED
172.17.0.2 dev docker0 lladdr 02:42:ac:11:00:02 PERMANENT
```

La table n'est pas un simple cache : c'est une **machine à états**, et savoir la lire évite des heures
d'errance.

```
                       paquet à envoyer, MAC inconnue
                                   │
                                   ▼
                            ┌─────────────┐   3 ARP sans réponse (1/s)
                            │ INCOMPLETE  │──────────────────────────► FAILED
                            └──────┬──────┘                            (nettoyée)
                        réponse ARP│
                                   ▼
   trafic entrant confirmant  ┌─────────────┐
   ◄───────────────────────── │  REACHABLE  │  ~30 s (base_reachable_time)
                              └──────┬──────┘
                          délai écoulé│
                                   ▼
                            ┌─────────────┐  entrée VALIDE, on continue à s'en servir
                            │   STALE     │  → pas de trafic pendant gc_stale_time (60 s) : GC
                            └──────┬──────┘
                       on s'en sert│
                                   ▼
                            ┌─────────────┐  5 s d'attente d'une confirmation implicite
                            │    DELAY    │
                            └──────┬──────┘
                       pas confirmé│
                                   ▼
                            ┌─────────────┐  3 sondes unicast
                            │    PROBE    │────► REACHABLE si réponse, sinon FAILED
                            └─────────────┘
```

| État | Sens opérationnel |
|---|---|
| `INCOMPLETE` | requête ARP partie, aucune réponse encore. Si ça reste bloqué là : mauvais VLAN, IP inexistante, ARP filtré. |
| `REACHABLE` | confirmé récemment. Tout va bien. |
| `STALE` | vieux mais **utilisable** — on envoie quand même, et on revalidera au prochain usage. Voir `STALE` partout est **normal**, ce n'est pas une panne. |
| `DELAY` | on attend 5 s une confirmation gratuite venue des couches hautes (un ACK TCP suffit). |
| `PROBE` | sondes ARP unicast en cours. |
| `FAILED` | l'IP ne répond pas. Là, il y a un vrai problème. |
| `PERMANENT` | entrée statique, jamais expirée (`ip neigh add … nud permanent`). |
| `NOARP` | pas de résolution nécessaire (tunnels, `lo`). |

**Les paramètres qui comptent** (`/proc/sys/net/ipv4/neigh/default/`) :

| Paramètre | Défaut | Rôle |
|---|---|---|
| `base_reachable_time_ms` | 30000 | durée de `REACHABLE` (le noyau tire aléatoirement entre 0,5× et 1,5×) |
| `gc_stale_time` | 60 | au bout de combien de temps une entrée `STALE` inutilisée est éligible au GC |
| `delay_first_probe_time` | 5 | durée de `DELAY` |
| `mcast_solicit` / `ucast_solicit` | 3 / 3 | nombre de requêtes avant `FAILED` |
| `gc_thresh1 / 2 / 3` | **128 / 512 / 1024** | seuils du garbage collector : en dessous de 1 on ne nettoie pas ; à 2 on nettoie doucement ; à **3 c'est un plafond dur** |

> ⚠️ **PIÈGE** — `neighbour: arp_cache: neighbor table overflow!` dans `dmesg` : tu as dépassé
> **`gc_thresh3` = 1024** voisins. Ça arrive dès qu'on met un hôte dans un grand domaine L2 (VLAN plat de
> 2000 machines, hôte Kubernetes avec beaucoup de pods, hyperviseur). Symptôme : des connexions qui échouent
> **au hasard**, sans logique apparente. Remède : multiplier les trois seuils par 8
> (`net.ipv4.neigh.default.gc_thresh1=1024`, `gc_thresh2=4096`, `gc_thresh3=8192`).

```bash
ip neigh flush dev eth0            # purger (utile après un changement de MAC de la gateway)
ip neigh add 10.0.1.1 lladdr 0a:58:0a:00:01:01 dev eth0 nud permanent
ip -s neigh | grep FAILED          # tous les voisins morts
```

> ❓ **RETIENS ÇA** — Une entrée `STALE` dans `ip neigh`, c'est un problème ?
> <details><summary>→ réponse</summary><br>Non. <code>STALE</code> = valide mais non confirmée récemment ; le noyau l'utilise telle quelle et revalide à l'usage. C'est l'état le plus fréquent sur une machine normale. Le vrai signal d'alarme, c'est <code>FAILED</code> ou <code>INCOMPLETE</code> persistant.</details>

---

## 6. `ip route` — la décision de routage

**La question** : j'ai un paquet pour `52.94.236.248`. Par quelle interface il sort, et à qui je le donne ?

```bash
$ ip route
default via 10.0.1.1 dev eth0 proto dhcp src 10.0.1.12 metric 100
10.0.1.0/24 dev eth0 proto kernel scope link src 10.0.1.12 metric 100
172.17.0.0/16 dev docker0 proto kernel scope link src 172.17.0.1 linkdown
10.244.2.0/24 via 10.0.1.31 dev eth0 proto bird metric 32
```

Décodage, champ par champ :

| Champ | Sens |
|---|---|
| `default` | équivaut à `0.0.0.0/0` : la route de dernier recours |
| `via 10.0.1.1` | **next-hop** : à qui je remets la trame (sa MAC ira dans l'en-tête Ethernet) |
| `dev eth0` | interface de sortie |
| `proto kernel` | qui a installé la route : `kernel` (déduite d'une IP), `dhcp`, `static`, `boot`, `bird`/`bgp` (démon de routage), `ra` (IPv6) |
| `scope link` | la destination est **directement joignable** : pas de `via`, on ARP la destination elle-même |
| `src 10.0.1.12` | l'IP source que le noyau choisira pour les paquets **émis localement** par cette route |
| `metric 100` | coût ; à préfixe **égal**, la métrique **la plus faible** gagne |
| `linkdown` | la route existe mais l'interface est morte (ici : docker0 sans conteneur) |

**La règle de sélection, dans l'ordre :**

```
 1. LONGEST PREFIX MATCH  — le masque le plus LONG gagne, toujours, quoi qu'il arrive
       /32 > /24 > /16 > /8 > /0
 2. à préfixe égal : la MÉTRIQUE la plus BASSE
 3. à métrique égale : ECMP (hash du quintuplet) si nexthop multiple
```

Une route `/32` bat toujours une `default`, même avec une métrique de 9999. **La métrique n'arbitre qu'entre
routes de même longueur de préfixe.** C'est la confusion n°1 du sujet.

> ❓ **RETIENS ÇA** — Table de routage : `10.0.0.0/8 metric 10` et `10.0.1.0/24 metric 500`. Quelle route pour `10.0.1.77` ?
> <details><summary>→ réponse</summary><br><b>La /24</b>, malgré sa métrique 50× pire. Le longest prefix match tranche <b>avant</b> toute comparaison de métrique.</details>

**L'outil décisif : `ip route get`.** Il ne lit pas la table, il **demande au noyau de faire la décision**,
policy routing et règles comprises. C'est la réponse définitive à « par où ça sort ? ».

```bash
$ ip route get 52.94.236.248
52.94.236.248 via 10.0.1.1 dev eth0 src 10.0.1.12 uid 1000
    cache

$ ip route get 10.244.2.15
10.244.2.15 via 10.0.1.31 dev eth0 src 10.0.1.12 uid 1000
    cache

$ ip route get 8.8.8.8 from 10.0.1.99          # simuler une autre source
$ ip route get 8.8.8.8 oif eth1                # forcer l'interface de sortie
```

Le champ `src` est très important : c'est **l'IP source** que prendra la connexion. Un `src` inattendu est
la cause n°1 des drops côté serveur distant (filtre sur IP source) et des retours asymétriques.

**Manipuler :**

```bash
ip route add 10.20.0.0/16 via 10.0.1.254 dev eth0
ip route add default via 10.0.1.1 metric 200         # route de secours
ip route del 10.20.0.0/16
ip route replace 10.20.0.0/16 via 10.0.1.253         # add-ou-modifie, idempotent
ip route add 10.30.0.0/16 dev eth0 onlink via 192.168.99.1   # nexthop hors sous-réseau
ip route flush cache
```

### 6bis. `ip rule` et les tables multiples

Une seule table de routage suppose que la décision ne dépend **que** de la destination. Faux dès qu'on a
deux liens (un lien opérateur + un VPN), un VRF, ou du routage par source. Linux gère **jusqu'à 2^32
tables**, et une liste de **règles** qui dit laquelle consulter.

```bash
$ ip rule
0:      from all lookup local
32766:  from all lookup main
32767:  from all lookup default
```

| Priorité | Table | ID | Contenu |
|---|---|---|---|
| 0 | `local` | **255** | adresses locales et broadcasts — gérée par le noyau, on n'y touche pas |
| 32766 | `main` | **254** | ce que montre `ip route` tout court |
| 32767 | `default` | **253** | vide par défaut |

Les règles sont évaluées **par priorité croissante**, et la **première qui matche et qui trouve une route**
gagne. On insère les siennes entre 1 et 32765.

```bash
echo "100 vpn" >> /etc/iproute2/rt_tables
ip route add default via 10.8.0.1 dev tun0 table vpn
ip rule add from 10.0.1.99 lookup vpn priority 100
ip route show table vpn
ip rule add fwmark 0x1 lookup vpn priority 101   # routage sur marque Netfilter
```

C'est **exactement** le mécanisme utilisé par les VRF, par Cilium/Calico pour isoler le trafic des pods, et
par les CNI multi-interfaces. Savoir lire `ip rule` te distingue immédiatement.

> ⚠️ **PIÈGE** — Tu ajoutes une route, elle n'a aucun effet. Réflexe : `ip route get <dest>`. Si la réponse
> ignore ta route, une **règle de priorité plus basse** a envoyé le paquet dans une autre table. `ip route`
> seul te ment par omission : il n'affiche que `main`.

> 🧠 **MÉMO** — **Routage = « le plus précis gagne ».** Comme une adresse postale : « Jean Dupont, 3 rue
> Machin » bat « toute la France ». Et la métrique, c'est le prix du timbre : elle ne compte que pour départager
> **deux enveloppes portant exactement la même adresse**.

---

## 7. `ss` — l'état des sockets

`ss` (*socket statistics*) parle au noyau via `NETLINK_SOCK_DIAG` : le filtre est appliqué **dans le noyau**,
la réponse est binaire. Il remplace `netstat` intégralement.

```bash
$ ss -lntp
State   Recv-Q  Send-Q   Local Address:Port    Peer Address:Port  Process
LISTEN  0       4096         127.0.0.1:5432         0.0.0.0:*      users:(("postgres",pid=921,fd=6))
LISTEN  0       511            0.0.0.0:80           0.0.0.0:*      users:(("nginx",pid=1204,fd=8))
LISTEN  129     128            0.0.0.0:8080         0.0.0.0:*      users:(("java",pid=3311,fd=42))
LISTEN  0       4096              [::]:9092            [::]:*      users:(("java",pid=2280,fd=118))
```

**La lecture qui compte : `Recv-Q` et `Send-Q` n'ont pas le même sens selon l'état.**

| État | `Recv-Q` | `Send-Q` |
|---|---|---|
| **`LISTEN`** | connexions **établies en attente d'`accept()`** (backlog courant) | **taille max** de l'accept queue = `min(backlog de listen(), somaxconn)` |
| **`ESTAB`** | octets reçus **pas encore lus** par l'application | octets envoyés **pas encore acquittés** par le pair |

Sur la 3ᵉ ligne, `Recv-Q 129` avec `Send-Q 128` : **l'accept queue déborde**. L'application Java n'appelle pas
`accept()` assez vite (pool de threads saturé, GC), et le noyau commence à jeter des connexions déjà
établies. Le client voit un timeout ou un RST, et ne comprend rien.

Sur la 1ʳᵉ ligne, `127.0.0.1:5432` : PostgreSQL n'écoute **que sur la loopback**. Aucune machine distante ne
pourra le joindre, quel que soit le pare-feu. C'est la cause n°1 de « le port ne répond pas ».

```bash
$ nstat -az | grep -E 'ListenOverflows|ListenDrops'
TcpExtListenOverflows           14238   0.0
TcpExtListenDrops               14238   0.0
```

Ces deux compteurs qui montent **confirment** le débordement d'accept queue. Le remède est dans cet ordre :
corriger l'appli, puis augmenter le backlog de `listen()` **dans le code**, puis `net.core.somaxconn`.

**Les options à connaître :**

| Option | Effet |
|---|---|
| `-t` `-u` `-x` | TCP · UDP · sockets Unix |
| `-l` / `-a` | en écoute seulement / tout |
| `-n` | pas de résolution DNS ni de `/etc/services` (**toujours**, sinon c'est lent et trompeur) |
| `-p` | processus propriétaire (root requis pour voir ceux des autres) |
| `-i` | infos TCP internes : cwnd, rtt, retrans… |
| `-e` | infos étendues : uid, inode, cgroup (**identifie le conteneur**) |
| `-m` | mémoire du socket (`skmem`) |
| `-s` | résumé global |
| `-o` | timers (retransmission, keepalive, TIME_WAIT restant) |
| `-K` | **tue** le socket (root) — utile pour libérer un port bloqué |

**Le langage de filtre** — c'est ça qui rend `ss` supérieur :

```bash
ss -t state established '( dport = :9092 or sport = :9092 )'
ss -t dst 10.244.0.0/16                    # tout le trafic vers les pods
ss -tn state time-wait | wc -l             # combien de TIME_WAIT
ss -tn state syn-sent                      # connexions qui n'aboutissent pas
ss -tu sport = :53                         # DNS
ss -t -o state established '( dport = :443 )' | head
ss -tp state close-wait                    # ← fuite de descripteurs dans TON appli
```

États utilisables : `established`, `syn-sent`, `syn-recv`, `fin-wait-1`, `fin-wait-2`, `time-wait`,
`closed`, `close-wait`, `last-ack`, `listening`, `closing`, plus les raccourcis `connected`, `synchronized`,
`bucket` (time-wait + syn-recv), `big`.

**`ss -ti` : la radiographie d'une connexion.**

```bash
$ ss -tin dst 10.0.3.7
ESTAB 0 0  10.0.1.12:52344  10.0.3.7:9092
     cubic wscale:7,7 rto:204 rtt:3.412/1.203 ato:40 mss:1448 pmtu:1500
     cwnd:24 ssthresh:18 bytes_sent:1843200 bytes_acked:1843200 bytes_received:94210
     segs_out:1420 segs_in:880 send 81.5Mbps lastsnd:12 lastrcv:12
     pacing_rate 97.8Mbps delivery_rate 42.1Mbps retrans:0/37 rcv_space:14480 minrtt:2.981
```

| Champ | Lecture |
|---|---|
| `cubic` | algorithme de congestion en vigueur |
| `wscale:7,7` | facteur de *window scale* envoyé,reçu → fenêtre max 65535 × 2⁷ ≈ 8,4 Mo |
| `rto:204` | timeout de retransmission courant, en ms (min Linux : 200 ms) |
| `rtt:3.412/1.203` | RTT lissé / variance, en ms |
| `mss:1448` | 1500 − 20 (IP) − 20 (TCP) − 12 (option Timestamps) |
| `cwnd:24` | fenêtre de congestion, **en segments** |
| `retrans:0/37` | retransmissions en cours / **cumulées**. 37 sur 1420 segments = 2,6 %, c'est beaucoup. |
| `send 81.5Mbps` | débit instantané = `cwnd × mss × 8 / rtt` = 24 × 1448 × 8 / 0,003412 |
| `minrtt:2.981` | le meilleur RTT jamais vu → la latence **incompressible** du chemin |

> ❓ **RETIENS ÇA** — Sur un socket `LISTEN`, que signifient `Recv-Q = 129` et `Send-Q = 128` ?
> <details><summary>→ réponse</summary><br>La file d'<code>accept()</code> est <b>pleine</b> : 129 connexions déjà établies attendent que l'appli les ramasse, pour une capacité de 128. Le noyau jette les suivantes → <code>TcpExtListenOverflows</code> monte. L'appli est trop lente à <code>accept()</code>, ce n'est pas un problème réseau.</details>

> ❓ **RETIENS ÇA** — À quoi correspond le débit affiché par `send` dans `ss -ti` ?
> <details><summary>→ réponse</summary><br>À <code>cwnd × mss × 8 / rtt</code> : le débit que permet la fenêtre de congestion actuelle sur le RTT actuel. C'est un <b>plafond théorique instantané</b>, pas une mesure du trafic réel (voir <code>delivery_rate</code> pour ça).</details>

> ⚠️ **PIÈGE** — Beaucoup de `CLOSE_WAIT` sur **ta** machine = **ton** bug : ton application a reçu un FIN et
> n'a jamais appelé `close()`. Les descripteurs fuient jusqu'à `EMFILE`. Beaucoup de `FIN_WAIT_2` = le bug est
> **chez le pair**. Ne cherche pas un problème réseau, cherche un `finally { conn.close(); }` manquant.

---

## 8. La méthode : les 8 étages, avec les commandes

Voilà la séquence complète, celle que tu déroules en incident sans réfléchir. Cible : `kafka.data.svc:9092`.

```
ÉTAGE 1 — INTERFACE
  $ ip -c -br link
  eth0  UP   06:1f:3a:9c:4e:22 <BROADCAST,MULTICAST,UP,LOWER_UP>
  ✗ NO-CARRIER → câble/veth/port switch.  ✗ DOWN → ip link set eth0 up

ÉTAGE 2 — ADRESSE
  $ ip -c -br -4 addr
  eth0  UP   10.0.1.12/24
  ✗ pas d'IP → DHCP mort, conf absente.   ✗ 169.254.x.x → APIPA = DHCP a échoué

ÉTAGE 3 — VOISIN L2 (uniquement si la cible est sur le LAN, ou pour la gateway)
  $ ip neigh show 10.0.1.1
  10.0.1.1 dev eth0 lladdr 0a:58:0a:00:01:01 REACHABLE
  ✗ FAILED/INCOMPLETE → mauvais VLAN, IP inexistante, ARP filtré, MTU absurde

ÉTAGE 4 — ROUTE
  $ ip route get 10.0.3.7
  10.0.3.7 via 10.0.1.1 dev eth0 src 10.0.1.12
  ✗ "Network is unreachable" → pas de route.  ⚠ src inattendu → asymétrie, filtre distant

ÉTAGE 5 — DNS
  $ getent hosts kafka.data.svc        # ← passe par NSS, comme l'application
  10.0.3.7  kafka.data.svc
  ✗ rien → /etc/resolv.conf, /etc/nsswitch.conf, search domain, résolveur mort

ÉTAGE 6 — SOCKET DISTANT
  $ nc -zv -w 3 10.0.3.7 9092
  Connection to 10.0.3.7 9092 port [tcp/*] succeeded!
  ✗ "Connection refused" → RST : la machine est là, RIEN N'ÉCOUTE (ou écoute sur 127.0.0.1)
  ✗ "Connection timed out"  → silence : PARE-FEU qui DROP, ou route retour absente

ÉTAGE 7 — FILTRAGE (des deux côtés)
  $ nft list ruleset | head -40          # ou: iptables -L -n -v
  $ conntrack -S | grep -E 'drop|insert_failed'
  Regarde les COMPTEURS des règles : une règle DROP dont le compteur monte, c'est la coupable.

ÉTAGE 8 — APPLICATION
  $ curl -v -o /dev/null -w 'dns=%{time_namelookup} tcp=%{time_connect} tls=%{time_appconnect} ttfb=%{time_starttransfer} total=%{time_total}\n' https://api.interne/health
  ✗ 200 mais lent → TTFB élevé = le serveur réfléchit ; time_connect élevé = réseau
```

**Le test discriminant du module** — apprends-le tel quel :

| Symptôme de `nc -zv` | Ce que le réseau a répondu | Cause |
|---|---|---|
| `succeeded` | SYN+ACK | tout va bien jusqu'à L4 |
| `Connection refused` | **RST** | l'IP est joignable, **aucun processus** sur ce port (ou bind sur `127.0.0.1`) |
| `Connection timed out` | **rien du tout** | un `DROP` quelque part, ou pas de route de retour |
| `No route to host` | **ICMP host unreachable** | routeur intermédiaire qui n'a pas de route, ou `REJECT --reject-with icmp-host-unreachable` |

> 🧠 **MÉMO** — **RST = « il n'y a personne à cette porte ». Silence = « quelqu'un a muré le couloir ».**
> Un pare-feu bien configuré `DROP` (silence, l'attaquant perd du temps) ; une machine saine `REJECT`/RST
> (échec immédiat, on ne fait pas attendre son propre réseau). Le **temps de réponse** te dit tout : instantané
> = RST, 2 minutes = DROP + retransmissions SYN.

> ❓ **RETIENS ÇA** — `telnet`/`nc` qui rend la main instantanément avec « refused » vs qui met 2 minutes : différence ?
> <details><summary>→ réponse</summary><br>« Refused » instantané = un <b>RST</b> est revenu : le paquet a atteint la pile TCP distante, rien n'écoute. 2 minutes = <b>aucune</b> réponse : les SYN sont retransmis (6 fois, backoff exponentiel ≈ 127 s) puis abandon. Silence = filtrage ou trou de routage.</details>

---

## 9. DNS côté client : `getent`, `dig`, `resolv.conf`

**Le piège fondateur** : `dig` et ton application **ne résolvent pas de la même façon**.

```
        TON APPLICATION (Python, Java, curl)        DIG
                    │                                │
             getaddrinfo()                           │
                    │                                │
        /etc/nsswitch.conf : "hosts: files dns"       │
           ├─► /etc/hosts        ← court-circuit !   │
           └─► /etc/resolv.conf ─┐                   │
                                 └───────────────────┴──► serveur DNS
```

`dig` ignore `/etc/hosts` et `/etc/nsswitch.conf` : il lit `resolv.conf` et parle directement au résolveur.
Donc **« ça pingue mais dig ne trouve rien »** (ou l'inverse) est parfaitement normal, et c'est le premier
indice à exploiter.

```bash
getent hosts kafka.data.svc      # ← LA commande : exactement ce que fait l'appli
getent ahostsv4 example.com      # ordre de tri v4 uniquement
dig +short A example.com
dig @10.0.0.10 kafka.data.svc    # forcer un résolveur précis
dig +trace example.com           # descendre depuis la racine, sans cache
dig +norecurse @ns1.example.com example.com   # tester un serveur faisant autorité
dig -x 10.0.3.7                  # PTR (reverse)
resolvectl status                # systemd-resolved : le vrai résolveur par interface
```

Lecture d'une réponse `dig` :

```
;; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 51544
;; flags: qr rd ra; QUERY: 1, ANSWER: 2, AUTHORITY: 0, ADDITIONAL: 1
;; ANSWER SECTION:
example.com.   287  IN  A  93.184.216.34
;; Query time: 3 msec
;; SERVER: 10.0.0.10#53(10.0.0.10) (UDP)
```

| Élément | Sens |
|---|---|
| `NOERROR` + ANSWER ≥ 1 | ça marche |
| `NOERROR` + ANSWER = 0 | le nom existe mais **pas dans ce type** (ex. AAAA absent) |
| `NXDOMAIN` | le nom **n'existe pas**. Faute de frappe, ou `search` domain manquant. |
| `SERVFAIL` | le résolveur a planté : zone cassée, DNSSEC invalide, upstream injoignable |
| `REFUSED` | le serveur refuse de te répondre (ACL) |
| `flags: aa` | *authoritative answer* — réponse d'un serveur faisant autorité |
| `flags: ra` | *recursion available* — le serveur accepte de récurser |
| `287` | **TTL restant** dans le cache. S'il décroît d'appel en appel, tu lis un cache. |

`/etc/resolv.conf` :

```
nameserver 10.0.0.10
search data.svc.cluster.local svc.cluster.local cluster.local
options ndots:5 timeout:2 attempts:2 single-request-reopen
```

| Directive | Sens et défaut |
|---|---|
| `nameserver` | jusqu'à **3** pris en compte ; les suivants sont ignorés |
| `search` | suffixes essayés en cascade |
| `options ndots:N` | si le nom contient **moins de N points**, on essaie d'abord les suffixes `search`. Défaut **1**, mais **5 dans Kubernetes** |
| `timeout:` / `attempts:` | défaut **5 s** et **2** essais → une panne de résolveur coûte 10 s par requête |

> ⚠️ **PIÈGE** — `ndots:5` en Kubernetes : `api.stripe.com` a 2 points < 5, donc le pod essaie d'abord
> `api.stripe.com.data.svc.cluster.local`, puis `.svc.cluster.local`, puis `.cluster.local`, **puis** le nom
> réel. Quatre requêtes ×2 (A et AAAA) = **8 requêtes DNS** pour une résolution externe. Sur un pipeline qui
> ouvre 500 connexions/s, c'est la première cause de latence inexpliquée. Remède : le point final absolu
> (`api.stripe.com.`) ou un `dnsConfig` avec `ndots:2`.

> ❓ **RETIENS ÇA** — Un nom « pingue » mais `dig` répond NXDOMAIN. Explication ?
> <details><summary>→ réponse</summary><br>Le nom est dans <code>/etc/hosts</code>. <code>ping</code> passe par <code>getaddrinfo()</code>/NSS qui lit les fichiers d'abord ; <code>dig</code> saute NSS et interroge le résolveur, qui ne connaît pas ce nom.</details>

---

## 10. `curl -v`, les timings, et `netcat`

`curl -v` te donne les 4 étages (DNS, TCP, TLS, HTTP) en une commande.

```bash
$ curl -v https://api.interne/health
* Host api.interne:443 was resolved.
* IPv4: 10.0.3.20                          ← étage DNS OK
*   Trying 10.0.3.20:443...
* Connected to api.interne (10.0.3.20) port 443    ← étage TCP OK
* ALPN: server accepted h2                 ← HTTP/2 négocié
* SSL connection using TLSv1.3 / TLS_AES_128_GCM_SHA256   ← étage TLS OK
* Server certificate: subject: CN=api.interne  expire date: Mar 14 09:12:00 2027 GMT
> GET /health HTTP/2
< HTTP/2 200
```

**La mesure qui sert vraiment** — décomposer la latence :

```bash
curl -sS -o /dev/null -w '\
 dns:     %{time_namelookup}s\n\
 tcp:     %{time_connect}s\n\
 tls:     %{time_appconnect}s\n\
 ttfb:    %{time_starttransfer}s\n\
 total:   %{time_total}s\n\
 speed:   %{speed_download} B/s\n' https://api.interne/health
```

Les valeurs sont **cumulatives depuis le début**, pas des durées individuelles. Donc :

| Durée réelle | Calcul | Ce que ça accuse |
|---|---|---|
| Résolution | `time_namelookup` | DNS |
| Handshake TCP | `time_connect − time_namelookup` | ≈ 1 RTT. Si >> RTT ping : perte de SYN |
| Handshake TLS | `time_appconnect − time_connect` | 1 RTT (TLS 1.3) ou 2 (TLS 1.2) + coût CPU |
| Réflexion serveur | `time_starttransfer − time_appconnect` | **l'application** (requête SQL lente, GC…) |
| Transfert | `time_total − time_starttransfer` | bande passante, fenêtre TCP |

```bash
curl --resolve api.interne:443:10.0.3.21 https://api.interne/health   # tester UN backend précis
curl -v --http1.1 …            # forcer HTTP/1.1
curl -k …                      # ignorer la validation du certificat (diagnostic seulement)
curl -x http://proxy:3128 …    # via proxy
```

**netcat** — le couteau suisse L4 :

```bash
nc -zv -w 3 10.0.3.7 9092                # test de port (z = zéro I/O, w = timeout)
nc -zv -w 1 10.0.3.7 9090-9100           # balayage de plage
nc -l 9000                               # serveur d'écoute jetable (BSD netcat)
nc -lu 9999                              # écoute UDP
echo -n "ping" | nc -u -w1 10.0.3.9 8125 # envoyer un datagramme StatsD
nc 10.0.3.7 9092 < /dev/zero             # générateur de trafic brut
```

Sans `nc` dans une image minimale (le cas standard en conteneur), bash suffit :

```bash
timeout 3 bash -c 'cat < /dev/null > /dev/tcp/10.0.3.7/9092' && echo OUVERT || echo FERME
```

> ⚠️ **PIÈGE** — `nc -zv` sur un port **UDP** ne prouve rien. UDP n'a pas de handshake : l'absence de réponse
> peut vouloir dire « ouvert et silencieux » aussi bien que « filtré ». Seul un **ICMP port unreachable** prouve
> que c'est fermé — et il est souvent filtré. Pour tester de l'UDP, il faut envoyer une **requête applicative
> valide** (`dig @serveur`, une commande Redis, un paquet StatsD) et regarder la réponse.

---

## 11. `traceroute` et `mtr`

`traceroute` exploite le **TTL** : il envoie des paquets avec TTL=1, 2, 3… Chaque routeur qui décrémente à 0
renvoie un **ICMP Time Exceeded** en révélant son IP.

```
  TTL=1 ──► R1 : TTL→0, ICMP Time Exceeded  ←── on apprend R1
  TTL=2 ──► R1 ──► R2 : TTL→0, ICMP TE      ←── on apprend R2
  TTL=3 ──► R1 ──► R2 ──► DEST : ICMP Port Unreachable / SYN+ACK  ←── arrivé
```

Sous Linux, `traceroute` envoie par défaut de l'**UDP vers des ports élevés** (33434+), ce qui est très
souvent filtré. Utilise plutôt :

```bash
traceroute -I 8.8.8.8          # ICMP echo (comme Windows tracert)
traceroute -T -p 443 api.com   # SYN TCP sur 443 → traverse les pare-feux applicatifs
mtr -n -T -P 9092 10.0.3.7     # mtr en TCP, sans DNS
mtr --report --report-cycles 100 -n 10.0.3.7   # rapport batch, exploitable
```

`mtr` = traceroute + ping en continu. C'est **l'outil** pour prouver une perte de paquets.

```
                              Loss%   Snt   Last   Avg  Best  Wrst StDev
 1. 10.0.1.1                   0.0%   100    0.4   0.5   0.3   1.2   0.1
 2. 100.64.0.1                42.0%   100    2.1   2.4   1.9   9.8   0.9   ← ICMP dépriorisé
 3. 195.12.4.9                 0.0%   100    9.8  10.1   9.5  14.2   0.6
 4. 10.0.3.7                   0.0%   100   10.4  10.9  10.2  16.0   0.7
```

> ⚠️ **PIÈGE — LE plus important de la section.** Une perte à un **saut intermédiaire** qui **ne se propage
> pas** aux sauts suivants n'est **pas** une perte réelle. Ce routeur se contente de limiter le débit des
> ICMP qu'il génère (fonction de contrôle, basse priorité) tout en commutant parfaitement le trafic transit.
> **Seule la dernière ligne mesure ta vraie perte.** Une vraie perte réseau apparaît au saut N **et à tous les
> suivants**.

Autre limite : le chemin **retour** peut être différent, et `mtr` ne le voit pas. Une latence qui explose à un
saut mais redescend ensuite = artefact. Une latence qui monte et **reste** haute = vrai point de bascule.

> ❓ **RETIENS ÇA** — `mtr` affiche 40 % de perte au saut 2 et 0 % au saut final. Verdict ?
> <details><summary>→ réponse</summary><br>Aucun problème. Le routeur du saut 2 limite le débit de ses réponses ICMP ; il transporte le trafic sans perte. Seule la <b>dernière ligne</b> compte.</details>

---

## 12. `tcpdump` : où il capture, comment on le filtre, comment on le lit

### 12.1 Où exactement il branche sa sonde

`tcpdump` ouvre un socket `AF_PACKET` et se greffe sur le **device layer**, sous IP et sous Netfilter. Cette
position a deux conséquences qu'il faut connaître par cœur :

```
        RÉCEPTION                                ÉMISSION
   NIC ──► driver ──► [TAP tcpdump] ──► IP    processus ──► IP ──► netfilter
                             │                                       │
                             ▼                                       ▼
                        netfilter                             [TAP tcpdump] ──► qdisc ──► NIC

   ⇒ EN RX : tu vois le paquet MÊME S'IL VA ÊTRE DROPPÉ par le pare-feu (adresses AVANT DNAT)
   ⇒ EN TX : tu vois le paquet APRÈS le SNAT/MASQUERADE (adresses de sortie, déjà traduites)
```

C'est **le** raisonnement qui règle les incidents NAT : si tu vois le SYN arriver en RX mais rien en TX côté
serveur, ce n'est pas le réseau — c'est un `DROP` local. Et si le serveur distant se plaint d'une IP source
que tu ne connais pas, c'est celle que tu vois en TX, après MASQUERADE.

### 12.2 La syntaxe BPF

Un filtre = des **primitives** combinées par **and / or / not**. Une primitive a trois dimensions :
un **type** (`host`, `net`, `port`, `portrange`), une **direction** (`src`, `dst`, rien = les deux), un
**protocole** (`ip`, `ip6`, `arp`, `tcp`, `udp`, `icmp`, `ether`, `vlan`).

```bash
tcpdump -i eth0 host 10.0.3.7
tcpdump -i eth0 src net 10.244.0.0/16 and dst port 9092
tcpdump -i any 'tcp port 443 and not host 10.0.1.5'
tcpdump -i eth0 'icmp or arp'
tcpdump -i eth0 'vlan 42 and host 10.0.3.7'        # ⚠ décale tous les offsets de 4 o
tcpdump -i eth0 'greater 1400'                     # trames > 1400 octets
tcpdump -i eth0 'ether host 06:1f:3a:9c:4e:22'
```

**L'accès aux octets bruts** `proto[offset:taille]` — c'est ce qui fait la différence en entretien :

| Filtre | Ce qu'il attrape |
|---|---|
| `tcp[tcpflags] & tcp-syn != 0` | tout paquet avec le bit SYN |
| `tcp[tcpflags] == tcp-syn` | les SYN **purs** (pas les SYN+ACK) → **les tentatives de connexion** |
| `tcp[tcpflags] & (tcp-syn\|tcp-fin\|tcp-rst) != 0` | ouvertures et fermetures : le squelette des connexions |
| `tcp[tcpflags] & tcp-rst != 0` | les RST → « qui coupe mes connexions ? » |
| `ip[8] < 5` | TTL < 5 (paquets près de l'expiration) |
| `ip[6] & 0x20 != 0` | flag *More Fragments* → fragmentation en cours |
| `ip[6:2] & 0x1fff != 0` | fragments **non initiaux** |
| `udp[10:2] = 0x0100` | requêtes DNS (les 2 octets de **flags** DNS, après l'en-tête UDP de 8 o et l'ID de 2 o ; `udp[10] & 0x80 = 0` = toute question) |
| `tcp[((tcp[12] & 0xf0) >> 2):4] = 0x47455420` | payload commençant par `GET ` (0x47='G') |

Le dernier mérite son décodage : `tcp[12]` contient le *data offset* dans ses 4 bits hauts ; `& 0xf0 >> 2`
convertit ce nombre de mots de 32 bits en **octets** ; on lit 4 octets à ce décalage = le début des données.

Les noms symboliques disponibles : `tcp-syn` (0x02), `tcp-ack` (0x10), `tcp-fin` (0x01), `tcp-rst` (0x04),
`tcp-push` (0x08), `tcp-urg` (0x20), `tcp-ece` (0x40), `tcp-cwr` (0x80).

> ⚠️ **PIÈGE** — Les filtres `tcp port 443` ne matchent **que le premier fragment** d'un paquet IP fragmenté :
> les suivants n'ont pas d'en-tête TCP. Idem, `tcp[...]` échoue silencieusement sur un fragment. Si tu
> soupçonnes de la fragmentation (MTU, VPN), filtre sur `host` seul.

### 12.3 Les options

| Option | Effet | À savoir |
|---|---|---|
| `-i eth0` / `-i any` | interface | `any` utilise l'encapsulation *Linux cooked* (SLL) : les filtres `ether` **ne marchent plus** |
| `-n` / `-nn` | pas de DNS / ni DNS ni noms de services | **toujours** : sinon tcpdump génère lui-même du trafic DNS |
| `-e` | affiche l'en-tête Ethernet (MAC, VLAN) | indispensable pour un souci L2 |
| `-c 100` | s'arrête après 100 paquets | évite de noyer le terminal |
| `-w f.pcap` / `-r f.pcap` | écrire / relire | **toujours capturer en `-w`**, analyser ensuite |
| `-s 96` | *snaplen* | défaut **262144** (paquet entier). `-s 96` = en-têtes seulement, capture plus légère |
| `-A` / `-X` / `-XX` | payload ASCII / hexa+ASCII / avec en-tête L2 | |
| `-Q in\|out` | sens uniquement | sépare émission et réception |
| `-ttt` | delta de temps entre paquets | mesurer un RTT dans la trace |
| `-G 60 -W 10 -w cap-%H%M.pcap` | rotation horaire | capture longue durée sans remplir le disque |
| `-Z nobody` | abandon des privilèges après ouverture | bonne pratique |

### 12.4 Lire la sortie, ligne par ligne

```
10:21:33.123456 IP 10.0.1.12.52344 > 10.0.3.7.9092: Flags [S], seq 1481625301,
                win 64240, options [mss 1460,sackOK,TS val 991 ecr 0,nop,wscale 7], length 0
10:21:33.126891 IP 10.0.3.7.9092 > 10.0.1.12.52344: Flags [S.], seq 3021994711, ack 1481625302,
                win 65160, options [mss 1460,sackOK,TS val 44 ecr 991,nop,wscale 7], length 0
10:21:33.126930 IP 10.0.1.12.52344 > 10.0.3.7.9092: Flags [.], ack 1, win 502, length 0
10:21:33.127402 IP 10.0.1.12.52344 > 10.0.3.7.9092: Flags [P.], seq 1:52, ack 1, win 502, length 51
10:21:33.131010 IP 10.0.3.7.9092 > 10.0.1.12.52344: Flags [.], ack 52, win 509, length 0
10:21:38.442009 IP 10.0.3.7.9092 > 10.0.1.12.52344: Flags [R], seq 3021994712, win 0, length 0
```

- `10:21:33.123456` — horodatage à la microseconde. Les **deltas** sont l'information : 3,4 ms entre le SYN et
  le SYN+ACK = le RTT.
- `10.0.1.12.52344 > 10.0.3.7.9092` — le port est collé à l'IP après un point. `.52344` = port éphémère,
  `.9092` = Kafka.
- **`Flags [...]`** : `S`=SYN, `S.`=SYN+ACK (le point signifie ACK), `.`=ACK seul, `P.`=PSH+ACK (données),
  `F.`=FIN+ACK, `R`=RST, `W`=CWR, `E`=ECE.
- `seq 1:52 … length 51` — après le premier paquet, tcpdump passe en **numéros relatifs** : octets 1 à 51.
- `win 502` — la **valeur brute** du champ Window de l'en-tête TCP. **tcpdump n'applique PAS le window
  scale** : la fenêtre réelle vaut ici `502 × 2⁷ = 64 256` octets. (C'est Wireshark, pas tcpdump, qui affiche
  une « calculated window size ». D'où le contraste apparent entre le `win 64240` du SYN — avant que le
  scaling ne soit négocié — et le `win 502` des paquets suivants.)
- La dernière ligne : un **RST 5,3 s après** le dernier échange. Ce n'est pas le réseau : quelque chose a
  décidé de couper — timeout d'un load balancer, `idle timeout` de NAT, ou l'application qui ferme brutalement.

**Les trois signatures à reconnaître instantanément :**

```
① SYN, SYN, SYN (1 s, 2 s, 4 s d'écart), rien en retour
   → DROP silencieux. Pare-feu, security group, ou pas de route retour.

② SYN → RST immédiat
   → Rien n'écoute sur ce port. Ou bind sur 127.0.0.1. Ou REJECT explicite.

③ Handshake OK, données, puis [R] plusieurs secondes plus tard sans FIN
   → Coupure par un intermédiaire (NAT/LB idle timeout) ou crash applicatif.
```

> ⚠️ **PIÈGE** — Tu vois `length 4344` sur une interface à MTU 1500. Impossible ? Non : c'est le **GRO/TSO**.
> La carte réseau agrège les segments en réception (GRO) et découpe en émission (TSO), et tcpdump se branche
> **du côté noyau** de l'offload. Pour voir la réalité du fil :
> `ethtool -K eth0 gro off gso off tso off lro off` (attention : ça coûte du CPU, à remettre après).

> ❓ **RETIENS ÇA** — Sur une machine qui fait du MASQUERADE, quelle IP source montre `tcpdump -i eth0` en émission ?
> <details><summary>→ réponse</summary><br>L'IP <b>après</b> traduction (celle de l'hôte), car la sonde TX est placée après POSTROUTING. Pour voir l'IP source d'origine, capture sur l'interface d'<b>entrée</b> (veth, bridge, docker0).</details>

> 🧠 **MÉMO** — **Entrée = avant le filtre. Sortie = après le NAT.** « On voit tout le monde entrer, on ne voit
> sortir que les gens déjà déguisés. »

---

## 13. Netfilter : les 5 crochets et l'ordre de traversée

**La question** : à quels moments précis de la vie d'un paquet le noyau me laisse-t-il intervenir ?

Réponse : à **5 points d'accroche** (*hooks*) plantés dans la pile IP. Tout — pare-feu, NAT, Docker,
Kubernetes, VPN — n'est que du code branché sur ces 5 crochets.

```
                          ┌─────────────────────────┐
                          │   PROCESSUS LOCAL       │
                          └────▲───────────────┬────┘
                        LOCAL_IN         LOCAL_OUT
                               │               │
                   ┌───────────┴──┐     ┌──────▼───────┐
   NIC ──► PRE_ROUTING ──► [ROUTAGE] ──► FORWARD ──► POST_ROUTING ──► NIC
              (1)             ?             (3)          (5)
                                                          ▲
                                            (4) LOCAL_OUT ┘ + re-routage
```

| # | Crochet | Quand |
|---|---|---|
| 1 | `PREROUTING` | dès l'arrivée, **avant** toute décision de routage → **DNAT ici** |
| 2 | `INPUT` (LOCAL_IN) | le routage a dit « c'est pour moi » |
| 3 | `FORWARD` | le routage a dit « c'est pour quelqu'un d'autre » |
| 4 | `OUTPUT` (LOCAL_OUT) | paquet produit localement, juste après le routage initial |
| 5 | `POSTROUTING` | juste avant la sortie physique → **SNAT ici** |

**Les 5 tables** ne sont que des groupes de règles avec une **priorité**. Plus la priorité est basse, plus on
passe tôt :

| Table | Priorité | Crochets | Rôle |
|---|---:|---|---|
| `raw` | **−300** | PRE, OUT | agir **avant conntrack** (`NOTRACK`) |
| *(conntrack)* | **−200** | PRE, OUT | suivi de connexion (ce n'est pas une table, c'est le module) |
| `mangle` | **−150** | les 5 | modifier TOS, TTL, poser des `MARK` |
| `nat` | **−100** (dnat) / **+100** (snat) | PRE, IN, OUT, POST | traduction d'adresses |
| `filter` | **0** | IN, FWD, OUT | accepter / jeter |
| `security` | **+50** | IN, FWD, OUT | SELinux |

**L'ordre complet pour un paquet forwardé** (la liste ordonnée du module, celle du palais mental) :

```
  1. arrivée NIC + sonde tcpdump RX
  2. raw PREROUTING            (-300)   NOTRACK ?
  3. conntrack                 (-200)   NEW / ESTABLISHED / RELATED / INVALID
  4. mangle PREROUTING         (-150)   MARK, TOS
  5. nat PREROUTING / DNAT     (-100)   ← LA DESTINATION CHANGE ICI
  6. ══ DÉCISION DE ROUTAGE ══          pour moi (→ INPUT) ou à travers (→ FORWARD) ?
  7. mangle + filter FORWARD   (-150, 0)  ← LE PARE-FEU DE TRANSIT
  8. mangle POSTROUTING        (-150)
  9. nat POSTROUTING / SNAT    (+100)   ← LA SOURCE CHANGE ICI
 10. qdisc + sortie NIC + sonde tcpdump TX
```

Pour un paquet **destiné à la machine**, on remplace 7 par `mangle INPUT` puis `filter INPUT` puis
`nat INPUT`, et on s'arrête. Pour un paquet **émis localement** : `raw OUTPUT` → conntrack → `mangle OUTPUT`
→ `nat OUTPUT` (DNAT possible) → **re-vérification de routage** → `filter OUTPUT` → POSTROUTING.

> ❓ **RETIENS ÇA** — Pourquoi le DNAT se fait-il obligatoirement en PREROUTING et le SNAT en POSTROUTING ?
> <details><summary>→ réponse</summary><br>Le DNAT change la <b>destination</b> : il doit avoir lieu <b>avant</b> la décision de routage, sinon le noyau route vers la mauvaise cible. Le SNAT change la <b>source</b> : il doit avoir lieu <b>après</b> le choix de l'interface de sortie, puisque l'adresse à mettre dépend de cette interface.</details>

> ⚠️ **PIÈGE** — Une règle `DROP` en `INPUT` **ne protège pas** un port publié par Docker. Le paquet subit un
> DNAT en PREROUTING vers `172.17.0.2`, donc le routage l'envoie en **FORWARD**, pas en INPUT : ta règle n'est
> jamais évaluée. C'est pour ça que `ufw deny 8080` ne bloque rien si le conteneur publie `-p 8080:80`. La
> bonne place est la chaîne **`DOCKER-USER`** (voir §16).

> 🧠 **MÉMO** — **« Rare Conne Mange Nos Filtres »** : **R**aw, **C**onntrack, **M**angle, **N**at, **F**ilter.
> Et pour les crochets : **PRE → ROUTAGE → (IN | FORWARD) → POST**, avec OUTPUT qui se greffe juste avant POST.

---

## 14. `conntrack` : la mémoire des connexions

**La question** : IP est sans état. Comment un pare-feu peut-il dire « laisse passer les réponses à ce que
**j'ai** demandé » ?

Réponse : une table de hachage dans le noyau, `nf_conntrack`, qui stocke une entrée par flux. C'est ce qui
rend possibles à la fois le pare-feu à état et **tout le NAT**.

```bash
$ conntrack -L | head -3
tcp 6 431995 ESTABLISHED src=10.244.1.7 dst=10.96.0.1 sport=41250 dport=443 \
    src=10.0.1.31 dst=10.244.1.7 sport=6443 dport=41250 [ASSURED] mark=0 use=1
udp 17 25 src=10.244.1.7 dst=10.96.0.10 sport=51203 dport=53 \
    src=10.244.2.4 dst=10.244.1.7 sport=53 dport=51203 mark=0 use=1
```

Chaque entrée stocke **deux tuples** : le sens **ORIGINAL** et le sens **REPLY** attendu. Le NAT n'est rien
d'autre qu'un tuple REPLY qui n'est pas l'inverse exact du tuple ORIGINAL — ici la destination `10.96.0.1:443`
(ClusterIP Kubernetes) répond depuis `10.0.1.31:6443` : un DNAT a eu lieu.

| État `ct state` | Sens |
|---|---|
| `NEW` | premier paquet, pas d'entrée existante |
| `ESTABLISHED` | du trafic a circulé **dans les deux sens** |
| `RELATED` | connexion **fille** : erreur ICMP liée à un flux connu, canal de données FTP |
| `INVALID` | ne correspond à rien de cohérent (souvent : ACK arrivé après expiration de l'entrée) |
| `UNTRACKED` | marqué `NOTRACK` dans la table `raw` |

`[ASSURED]` = flux confirmé dans les deux sens ; les entrées **non** assured sont sacrifiées en premier quand
la table sature.

**Les timeouts** (`/proc/sys/net/netfilter/`) — le premier est un piège célèbre :

| Paramètre | Défaut | Remarque |
|---|---|---|
| `nf_conntrack_tcp_timeout_established` | **432000 s = 5 jours** | une connexion inactive occupe une entrée **5 jours** |
| `nf_conntrack_tcp_timeout_time_wait` | 120 | |
| `nf_conntrack_tcp_timeout_close_wait` | 60 | |
| `nf_conntrack_tcp_timeout_syn_sent` | 120 | |
| `nf_conntrack_udp_timeout` | 30 | |
| `nf_conntrack_udp_timeout_stream` | 120 | |
| `nf_conntrack_icmp_timeout` | 30 | |

```bash
sysctl net.netfilter.nf_conntrack_count      # occupation actuelle
sysctl net.netfilter.nf_conntrack_max        # plafond (souvent 65536 à 262144 selon la RAM — VÉRIFIE)
sysctl net.netfilter.nf_conntrack_buckets    # taille de la table de hachage
conntrack -S                                 # compteurs par CPU : drop, insert_failed, invalid
conntrack -D -s 10.244.1.7                   # supprimer les entrées d'une IP
dmesg | grep conntrack
```

> ⚠️ **PIÈGE** — `nf_conntrack: table full, dropping packet` dans `dmesg` : la table est pleine, et le noyau
> **jette du trafic au hasard**. Symptôme : des timeouts erratiques, jamais reproductibles, sur une passerelle
> ou un nœud K8s chargé. Surveillance : `nf_conntrack_count / nf_conntrack_max` doit être un dashboard
> permanent. Dimensionnement : ≈ **300 octets par entrée** → 1 million d'entrées ≈ **300 Mo de RAM noyau**.
> Règle : `nf_conntrack_max = 4 × nf_conntrack_buckets`.

> ⚠️ **PIÈGE (spécial data/K8s)** — Le compteur `insert_failed` de `conntrack -S` qui monte sur un cluster
> Kubernetes est la signature de la **course conntrack sur les requêtes DNS UDP** : deux requêtes (A et AAAA)
> partent du même socket au même instant vers le même ClusterIP, et une des deux insertions échoue. Résultat :
> des résolutions DNS à **exactement 5 secondes** (le `timeout:5` de `resolv.conf`). Sur un pipeline qui ouvre
> des milliers de connexions, ça multiplie les latences par 10. Atténuations : `single-request-reopen`,
> `use-vc` (DNS en TCP), NodeLocal DNSCache.

> ❓ **RETIENS ÇA** — Combien de temps une connexion TCP inactive occupe-t-elle une entrée conntrack par défaut ?
> <details><summary>→ réponse</summary><br><b>432 000 s = 5 jours</b> (<code>nf_conntrack_tcp_timeout_established</code>). C'est ce qui fait saturer les tables des passerelles NAT : les entrées mortes s'accumulent bien plus vite qu'elles n'expirent.</details>

---

## 15. NAT : DNAT, SNAT, MASQUERADE

```
   DNAT (PREROUTING)                        SNAT / MASQUERADE (POSTROUTING)
   « change la DESTINATION »                « change la SOURCE »
   publier un service, load-balancer        sortir un réseau privé vers Internet
   c'est ce que fait -p 8080:80             c'est ce que fait un routeur box
```

| Cible | Table/chaîne | Ce qu'elle fait |
|---|---|---|
| `DNAT --to 10.10.0.2:80` | nat PREROUTING (ou OUTPUT) | réécrit IP/port **destination** |
| `REDIRECT --to-port 3128` | nat PREROUTING/OUTPUT | DNAT vers **la machine elle-même** (proxy transparent) |
| `SNAT --to 203.0.113.9` | nat POSTROUTING | réécrit l'IP **source**, adresse **fixe** connue à l'avance |
| `MASQUERADE` | nat POSTROUTING | comme SNAT mais prend **l'IP courante de l'interface de sortie** |

**SNAT vs MASQUERADE** — la question d'entretien : `MASQUERADE` interroge l'interface à chaque nouveau flux
(un peu plus coûteux) mais fonctionne avec une **IP dynamique** ; en prime, il **purge les entrées conntrack**
quand l'interface tombe, ce qui évite de garder des traductions vers une IP qui n'existe plus. `SNAT` est plus
rapide et prévisible, mais impose une IP statique.

**La règle d'or** : la traduction n'est décidée que sur le **premier paquet** de la connexion (`ct state NEW`).
Tous les paquets suivants sont traduits **automatiquement par conntrack**, sans jamais retraverser la table
`nat`. C'est pour ça que modifier une règle NAT ne casse pas les connexions en cours — et aussi pourquoi ça
ne les corrige pas non plus.

> ❓ **RETIENS ÇA** — Une règle de la table `nat` s'applique-t-elle à chaque paquet d'une connexion ?
> <details><summary>→ réponse</summary><br>Non : uniquement au <b>premier</b> (état <code>NEW</code>). Ensuite, conntrack applique la même traduction à tous les paquets du flux, dans les deux sens, sans consulter la table nat.</details>

---

## 16. `iptables` et `nftables` en pratique

Sur toutes les distributions récentes, la commande `iptables` est en réalité **`iptables-nft`** : une couche
de compatibilité qui écrit dans le moteur nftables. `iptables -V` te le dit : `(nf_tables)` ou `(legacy)`.
**Ne mélange jamais les deux back-ends sur une même machine** — chacun ignore les règles de l'autre.

```bash
iptables -L -n -v --line-numbers            # -n OBLIGATOIRE (sinon reverse DNS = très lent)
iptables -t nat -L -n -v
iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
iptables -A INPUT -i lo -j ACCEPT
iptables -A INPUT -p tcp --dport 22 -j ACCEPT
iptables -P INPUT DROP
iptables -t nat -A POSTROUTING -s 10.10.0.0/24 -o eth0 -j MASQUERADE
iptables -t nat -A PREROUTING -i eth0 -p tcp --dport 8080 -j DNAT --to-destination 10.10.0.2:80
iptables-save > /etc/iptables/rules.v4       # persistance
```

**nftables**, l'équivalent moderne — une seule commande pour IPv4/IPv6/ARP/bridge, des `set`, des `map`, et
surtout un **rechargement atomique** :

```nft
#!/usr/sbin/nft -f
flush ruleset

table inet filter {
  set autorises { type ipv4_addr; flags interval; elements = { 10.0.0.0/8, 192.168.0.0/16 } }

  chain input {
    type filter hook input priority filter; policy drop;
    ct state established,related accept
    ct state invalid drop counter
    iif lo accept
    ip protocol icmp accept
    ip saddr @autorises tcp dport { 22, 9092 } accept
    tcp dport { 80, 443 } accept
    counter comment "tout le reste est jeté"
  }
  chain forward { type filter hook forward priority filter; policy drop; }
  chain output  { type filter hook output  priority filter; policy accept; }
}

table ip nat {
  chain prerouting  { type nat hook prerouting priority dstnat; policy accept;
                      iifname "eth0" tcp dport 8080 dnat to 10.10.0.2:80 }
  chain postrouting { type nat hook postrouting priority srcnat; policy accept;
                      oifname "eth0" ip saddr 10.10.0.0/24 masquerade }
}
```

| Notion | iptables | nftables |
|---|---|---|
| familles | 4 binaires (`iptables`, `ip6tables`, `arptables`, `ebtables`) | 1 binaire, familles `ip ip6 inet arp bridge netdev` |
| tables/chaînes | fixes, imposées | **créées par toi**, avec crochet et priorité choisis |
| ensembles d'IP | module externe `ipset` | `set` / `map` natifs, O(1) |
| rechargement | règle par règle (fenêtre d'incohérence) | `nft -f fichier` = **atomique** |
| compteurs | toujours actifs | **optionnels** (`counter`) → plus rapide |

```bash
nft list ruleset                       # tout
nft -a list ruleset                    # avec les "handle" (nécessaires pour supprimer)
nft delete rule inet filter input handle 7
nft -f /etc/nftables.conf              # rechargement atomique
nft monitor trace                      # tracer un paquet à travers les règles
iptables-translate -A INPUT -p tcp --dport 22 -j ACCEPT   # convertir sa syntaxe
```

> ⚠️ **PIÈGE** — En debug, **lis les compteurs**, pas les règles. `iptables -L -n -v` ou `nft list ruleset`
> affichent `pkts bytes` par règle. Envoie 5 paquets, regarde quel compteur a bougé de 5 : tu as trouvé la
> règle coupable en 10 secondes au lieu de relire 300 lignes.

---

## 17. Docker et kube-proxy : ce n'est **que** du Netfilter

### Docker

Au démarrage, Docker crée le bridge `docker0` (**172.17.0.1/16** par défaut), met
`net.ipv4.ip_forward=1`, et installe ses chaînes. Un `docker run -p 8080:80` produit exactement ceci :

```
# nat / PREROUTING → DOCKER
DNAT       tcp  --  0.0.0.0/0   0.0.0.0/0   tcp dpt:8080 to:172.17.0.2:80
# nat / POSTROUTING
MASQUERADE all  --  172.17.0.0/16  0.0.0.0/0                    ← sortie des conteneurs
MASQUERADE tcp  --  172.17.0.2  172.17.0.2  tcp dpt:80          ← hairpin (conteneur → lui-même)
# filter / FORWARD
DOCKER-USER  all  --  0.0.0.0/0  0.0.0.0/0                      ← ★ TES règles vont ICI
DOCKER-ISOLATION-STAGE-1 …                                       ← isole les bridges entre eux
ACCEPT     all  --  0.0.0.0/0  0.0.0.0/0  ctstate RELATED,ESTABLISHED
DOCKER     all  --  0.0.0.0/0  0.0.0.0/0
# filter / DOCKER
ACCEPT     tcp  --  0.0.0.0/0  172.17.0.2  tcp dpt:80
```

Trois choses à retenir : (1) la publication de port est un **DNAT**, pas un proxy ; (2) le trafic passe donc
par **FORWARD**, ce qui court-circuite les règles `INPUT` (et donc `ufw`) ; (3) la seule chaîne où poser tes
règles est **`DOCKER-USER`**, parce qu'elle est évaluée en premier et que Docker ne la réécrit pas.

```bash
iptables -I DOCKER-USER -i eth0 ! -s 10.0.0.0/8 -j DROP   # n'exposer qu'au réseau interne
```

### kube-proxy

Un Service `ClusterIP` est une **IP qui n'existe sur aucune interface** : c'est une entrée de table NAT
présente sur **chaque nœud**. Le DNAT est fait par le nœud d'origine, avant même que le paquet ne parte.

```
-A KUBE-SERVICES -d 10.96.0.10/32 -p tcp --dport 53 -j KUBE-SVC-TCOU7JCQXEZGVUNU
-A KUBE-SVC-TCOU7… -m statistic --mode random --probability 0.33333333349 -j KUBE-SEP-A
-A KUBE-SVC-TCOU7… -m statistic --mode random --probability 0.50000000000 -j KUBE-SEP-B
-A KUBE-SVC-TCOU7… -j KUBE-SEP-C
-A KUBE-SEP-A -p tcp -j DNAT --to-destination 10.244.1.5:53
```

La répartition est **probabiliste séquentielle** : pour 3 endpoints, 1/3 · puis 1/2 du reste · puis le
reliquat = 1/3 chacun. Pour N endpoints, la kᵉ règle porte la probabilité **1/(N−k+1)**.

| Mode | Structure | Complexité | Quand |
|---|---|---|---|
| `iptables` | chaînes linéaires | **O(n)** par paquet, mise à jour O(n²) | défaut historique ; s'écroule vers 5 000-10 000 Services |
| `ipvs` | table de hachage noyau | **O(1)**, algos rr/lc/sh/dh | grands clusters |
| `nftables` | sets/maps natifs | O(1) | mode récent (alpha en 1.29, beta en 1.31) |

Le trafic sortant d'un pod est ensuite `MASQUERADE`é (marque `0x4000`) pour que la réponse revienne par le
bon nœud. Tout cela justifie que Kubernetes exige `net.bridge.bridge-nf-call-iptables=1` : sans ça, le trafic
qui traverse un **bridge** ne remonte pas à Netfilter et les Services ne fonctionnent pas.

> ❓ **RETIENS ÇA** — Sur quelle interface est configurée l'adresse ClusterIP d'un Service Kubernetes ?
> <details><summary>→ réponse</summary><br><b>Aucune.</b> Elle n'existe nulle part en tant qu'adresse : c'est uniquement une règle DNAT (iptables/IPVS/nftables) installée par kube-proxy sur chaque nœud. Un <code>ping</code> vers un ClusterIP ne répond donc pas, alors que le Service fonctionne.</details>

---

## 18. Les network namespaces

**La question** : comment donner à un conteneur sa propre pile réseau — ses interfaces, ses IP, ses routes,
son pare-feu, ses ports — sans lui donner une machine ?

Un **namespace** est une copie isolée d'une ressource globale du noyau. Linux en a 8 :

| Namespace | Isole |
|---|---|
| `mnt` | l'arborescence de montage |
| `pid` | les numéros de processus (PID 1 dans le conteneur) |
| `net` | **interfaces, IP, routes, ARP, ports, netfilter, conntrack, /proc/net, sysctl net.\*** |
| `ipc` | files de messages, sémaphores |
| `uts` | hostname et domainname |
| `user` | les UID/GID (root dans le conteneur ≠ root sur l'hôte) |
| `cgroup` | la vue de la hiérarchie cgroup |
| `time` | les horloges monotone et boottime |

**Un conteneur = un ensemble de namespaces + des cgroups (limites) + un rootfs.** Rien de plus. Il n'y a pas
de « machine virtuelle légère » : c'est un processus ordinaire dont le noyau ment sur ce qu'il voit.

Chaque netns possède : sa `lo` (**qui démarre DOWN**), sa table de routage, sa table ARP, ses règles nftables,
**sa propre table conntrack**, ses propres valeurs de `sysctl net.*`, et **son propre espace de ports** — deux
conteneurs peuvent écouter sur `:80` sans conflit.

```bash
ip netns add ns1                  # crée + monte /var/run/netns/ns1
ip netns list
ip netns exec ns1 ip -br addr     # exécuter une commande dedans
ip -n ns1 route                   # raccourci équivalent
lsns -t net                       # tous les netns avec leurs processus
ls -l /proc/$$/ns/                # les namespaces du shell courant
nsenter -t 4211 -n ip addr        # entrer dans le netns du PID 4211
```

> ⚠️ **PIÈGE** — `ip netns list` ne montre **rien** sur une machine pleine de conteneurs Docker. Normal :
> `ip netns` ne liste que les namespaces **liés à un fichier** dans `/var/run/netns/`, et Docker n'en crée pas.
> Le pont :
> ```bash
> pid=$(docker inspect -f '{{.State.Pid}}' mon-conteneur)
> mkdir -p /var/run/netns && ln -sf /proc/$pid/ns/net /var/run/netns/mon-conteneur
> ip netns exec mon-conteneur ss -lntp      # ou plus direct : nsenter -t $pid -n ss -lntp
> ```
> Ça vaut de l'or : ça te permet de faire `tcpdump` **dans** un conteneur qui n'a ni tcpdump ni shell.

**La veth** : une paire d'interfaces virtuelles reliées dos à dos. Ce qui entre d'un côté ressort de l'autre.
C'est un **câble RJ45 virtuel**, et il est toujours créé **par paire**. Sur l'hôte, `eth0@if17` dans un
conteneur signifie « mon pair est l'ifindex 17 de l'hôte » — c'est comme ça qu'on relie un veth à son
conteneur.

```
     NETNS ns1                        HÔTE (netns racine)
  ┌──────────────────┐            ┌──────────────────────────────┐
  │  lo (127.0.0.1)  │            │   br0  10.10.0.1/24          │
  │  ceth0           │            │    │                         │
  │  10.10.0.2/24  ══╪════════════╪═ veth0 (master br0)          │
  │  default via     │  paire     │                              │
  │    10.10.0.1     │  veth      │   eth0 10.0.1.12/24 ─► LAN   │
  └──────────────────┘            └──────────────────────────────┘
                                     ip_forward=1 + MASQUERADE
```

---

## 19. Atelier corrigé : fabriquer Docker à la main

Objectif : un namespace qui joint Internet. **Fais-le vraiment**, sur une VM, en root. C'est l'exercice qui
transforme Docker de magie en mécanique.

```bash
# ── 1. Le namespace, et sa loopback
ip netns add ns1
ip netns exec ns1 ip link set lo up               # ← OUBLIER ÇA casse tout ce qui parle à 127.0.0.1

# ── 2. Le switch virtuel
ip link add br0 type bridge
ip addr add 10.10.0.1/24 dev br0                  # br0 devient la passerelle du réseau
ip link set br0 up

# ── 3. Le câble
ip link add veth0 type veth peer name ceth0
ip link set veth0 master br0                      # un bout dans le switch
ip link set veth0 up
ip link set ceth0 netns ns1                       # l'autre bout DANS le namespace

# ── 4. Configurer le côté conteneur
ip netns exec ns1 ip addr add 10.10.0.2/24 dev ceth0
ip netns exec ns1 ip link set ceth0 up
ip netns exec ns1 ip route add default via 10.10.0.1

# ── 5. Faire de l'hôte un routeur
sysctl -w net.ipv4.ip_forward=1

# ── 6. Traduire la source en sortie (le réseau 10.10.0.0/24 n'existe pas sur le LAN)
nft add table ip nat
nft 'add chain ip nat postrouting { type nat hook postrouting priority srcnat; }'
nft add rule ip nat postrouting ip saddr 10.10.0.0/24 oifname "eth0" masquerade

# ── 7. Vérifier, étage par étage
ip netns exec ns1 ping -c1 10.10.0.1        # étage 2-3 : le bridge répond ?
ip netns exec ns1 ping -c1 10.0.1.1         # étage 4 : le forwarding marche ?
ip netns exec ns1 ping -c1 1.1.1.1          # étage 4+7 : le MASQUERADE marche ?
ip netns exec ns1 getent hosts example.com  # étage 5 : DNS (⚠ /etc/resolv.conf est partagé !)
```

**Ce qui casse si tu sautes une étape — apprends ce tableau, c'est le corrigé du diagnostic :**

| Étape oubliée | Symptôme exact |
|---|---|
| 1 (`lo up`) | `ping 127.0.0.1` → *Network is unreachable* ; toute appli qui se parle à elle-même casse |
| 2 (IP sur `br0`) | pas de passerelle : `ping 10.10.0.1` échoue |
| 3 (`veth0 up`) | l'interface du namespace reste **NO-CARRIER** : un seul bout monté ne suffit pas |
| 4 (route par défaut) | LAN OK, Internet → *Network is unreachable* |
| 5 (`ip_forward`) | le ping atteint `br0` mais **rien ne sort** : `tcpdump -i eth0` est muet |
| 6 (`masquerade`) | `tcpdump -i eth0` montre des paquets partir avec `src=10.10.0.2` — et **rien ne revient**, personne ne sait router 10.10.0.0/24 |

Ajouter un deuxième « conteneur » : refais 3-4 avec `veth1/ceth1` et `10.10.0.3/24`. Les deux se parlent via
`br0` **sans passer par le routage** — c'est un domaine L2. Exactement le `docker0` par défaut.

> ❓ **RETIENS ÇA** — Après avoir mis un bout de veth dans un netns et l'avoir monté, l'interface reste `NO-CARRIER`. Pourquoi ?
> <details><summary>→ réponse</summary><br>Une veth n'a de « porteuse » que si <b>ses deux extrémités</b> sont UP. Il faut aussi <code>ip link set veth0 up</code> côté hôte.</details>

> ❓ **RETIENS ÇA** — Que fait exactement `net.ipv4.ip_forward=1` ?
> <details><summary>→ réponse</summary><br>Il autorise le noyau à <b>relayer</b> un paquet dont la destination n'est pas une de ses adresses locales, au lieu de le jeter. Sans lui, la machine n'est pas un routeur : aucun conteneur ne sort. C'est pour ça que Docker le force au démarrage.</details>

---

## 20. `/proc`, `/sys`, `sysctl`

`/proc` est un **système de fichiers virtuel** : chaque lecture appelle du code noyau, il n'y a rien sur le
disque. Historiquement pour les processus, il a accumulé tout l'état du noyau. `/sys` (sysfs) est son
successeur propre : un fichier = une valeur, arborescence structurée par le modèle de périphériques.

| Chemin | Contenu |
|---|---|
| `/proc/net/dev` | compteurs par interface (source de `ip -s link`) |
| `/proc/net/tcp`, `/udp` | sockets en **hexadécimal little-endian** (source historique de `netstat`) |
| `/proc/net/sockstat` | nombre de sockets par état, mémoire TCP utilisée |
| `/proc/net/snmp`, `/proc/net/netstat` | tous les compteurs RFC (source de `nstat`) |
| `/proc/net/nf_conntrack` | la table conntrack en clair |
| `/proc/net/softnet_stat` | par CPU : traités · **jetés (col. 2)** · time_squeeze (col. 3) |
| `/proc/interrupts`, `/proc/softirqs` | répartition des IRQ / softirqs `NET_RX`, `NET_TX` par cœur |
| `/proc/sys/net/…` | **= sysctl** |
| `/proc/<pid>/net/` | le `/proc/net` **du namespace de ce PID** |
| `/proc/<pid>/fd/`, `/limits`, `/status` | descripteurs, `RLIMIT_NOFILE`, mémoire du processus |
| `/proc/pressure/{cpu,io,memory}` | **PSI** : temps perdu à attendre une ressource (noyau ≥ 4.20) |
| `/sys/class/net/eth0/` | `mtu`, `address`, `operstate`, `speed`, `statistics/*` |

```bash
cat /sys/class/net/eth0/speed              # 10000  (Mbit/s)
cat /sys/class/net/eth0/statistics/rx_dropped
awk '{print $2}' /proc/net/softnet_stat    # drops par CPU : doit rester à 0
cat /proc/pressure/io                      # some avg10=… full avg10=…
grep -c . /proc/1234/fd 2>/dev/null; ls /proc/1234/fd | wc -l   # fuite de FD ?
```

> ❓ **RETIENS ÇA** — Pourquoi `/proc/net/dev` d'un conteneur n'affiche-t-il pas les interfaces de l'hôte ?
> <details><summary>→ réponse</summary><br>Parce que <code>/proc/net</code> est un lien vers <code>/proc/self/net</code>, qui est <b>relatif au network namespace</b> du processus qui lit. Chaque netns a son propre <code>/proc/net</code>.</details>

### Les `sysctl` réseau qui comptent vraiment

```bash
sysctl -a | grep -E 'somaxconn|tcp_rmem|ip_forward'
sysctl -w net.core.somaxconn=8192           # temporaire
echo 'net.core.somaxconn = 8192' > /etc/sysctl.d/99-net.conf && sysctl --system   # persistant
```

| Paramètre | Défaut | Rôle · quand y toucher |
|---|---|---|
| `net.core.somaxconn` | **4096** (128 avant 5.4) | plafond de l'accept queue. Symptôme : `ListenOverflows` |
| `net.ipv4.tcp_max_syn_backlog` | 1024-2048 selon RAM | file des demi-connexions (SYN_RECV) |
| `net.ipv4.tcp_syncookies` | **1** | survit à un SYN flood en abandonnant la file SYN |
| `net.core.netdev_max_backlog` | **1000** | file entre le driver et la pile IP. Trop bas → drops dans `softnet_stat` |
| `net.ipv4.ip_forward` | **0** | routage / conteneurs |
| `net.ipv4.tcp_rmem` | `4096 131072 6291456` | min · **défaut** · max du buffer de réception (auto-tuning entre les deux bornes) |
| `net.ipv4.tcp_wmem` | `4096 16384 4194304` | idem en émission |
| `net.core.rmem_max` / `wmem_max` | **212992** | plafond de `SO_RCVBUF`/`SO_SNDBUF` demandé explicitement par l'appli |
| `net.ipv4.tcp_congestion_control` | `cubic` | `bbr` sur les longs liens à perte |
| `net.ipv4.ip_local_port_range` | `32768 60999` (28 232 ports) | épuisement de ports côté client |
| `net.ipv4.tcp_tw_reuse` | 2 (loopback seulement) | réutiliser les TIME_WAIT sortants. **`tcp_tw_recycle` n'existe plus** (supprimé en 4.12) |
| `net.ipv4.tcp_fin_timeout` | **60** | durée de FIN_WAIT_2 |
| `net.ipv4.tcp_keepalive_time` / `_intvl` / `_probes` | **7200 / 75 / 9** | 2 h avant la 1ʳᵉ sonde : **inutile** face à un NAT qui coupe à 350 s → descendre à 300 |
| `net.ipv4.conf.all.rp_filter` | 0, 1 ou 2 selon distro | vérification du chemin inverse : à **1**, tue le routage asymétrique |
| `net.ipv4.tcp_mtu_probing` | **0** | à **1** si PMTUD est cassé (ICMP filtré) : les gros transferts cessent de geler |
| `net.netfilter.nf_conntrack_max` | dépend de la RAM | à surveiller **et** à dimensionner sur les passerelles |
| `net.bridge.bridge-nf-call-iptables` | 1 si `br_netfilter` chargé | **prérequis Kubernetes** |
| `fs.file-max`, `nr_open`, `vm.max_map_count` | — | limites côté descripteurs / mmap (Elastic exige 262144) |

> ⚠️ **PIÈGE** — `tcp_rmem` et `rmem_max` ne servent pas la même chose. `tcp_rmem` pilote l'**auto-tuning**
> du noyau (min/défaut/max). `rmem_max` plafonne ce qu'une application peut demander via `setsockopt(SO_RCVBUF)`.
> Et dès que l'appli fixe `SO_RCVBUF` explicitement, **l'auto-tuning est désactivé** pour ce socket. C'est
> pour ça qu'un client mal réglé plafonne à 6 Mbit/s sur un lien à 10 Gbit/s : sa fenêtre est figée trop petite
> pour le BDP.

> ⚠️ **PIÈGE** — Dans un conteneur, seuls les `sysctl` **namespacés** (`net.*` essentiellement) peuvent être
> changés ; `vm.*`, `fs.file-max` sont globaux à l'hôte. `docker run --sysctl net.core.somaxconn=4096 …`, ou
> `securityContext.sysctls` en Kubernetes (avec la liste des « safe sysctls »).

---

## 21. Méthode d'analyse de performance : où est le goulot ?

Quatre ressources, jamais plus : **CPU, mémoire, disque, réseau** (+ les verrous applicatifs). La méthode
**USE** de Brendan Gregg : pour chaque ressource, mesure **U**tilisation, **S**aturation, **E**rreurs.

| Ressource | Utilisation | **Saturation** (le signal utile) | Erreurs |
|---|---|---|---|
| CPU | `%us + %sy` (`mpstat -P ALL 1`) | `r` de `vmstat` > nb de cœurs ; `/proc/pressure/cpu` | — |
| Mémoire | `free -m` (regarde `available`) | `si/so` de `vmstat` ≠ 0 ; OOM dans `dmesg` | `dmesg \| grep -i oom` |
| Disque | `%util` (`iostat -xz 1`) | `aqu-sz`, `await` ↑ ; `b` de `vmstat` | erreurs I/O dans `dmesg` |
| Réseau | `sar -n DEV 1` (débit / capacité NIC) | `retrans` de `ss -ti` ; `dropped` de `ip -s link` ; `softnet_stat` col. 2 | `RX errors`, `TX carrier` |

**Le checklist 60 secondes** — dans cet ordre :

```bash
uptime                    # 1. load 1/5/15 : la tendance (ça monte ou ça descend ?)
dmesg -T | tail -30       # 2. OOM killer, erreurs I/O, conntrack full, neighbor overflow
vmstat 1 5                # 3. r, b, si/so, wa, st  ← la vue d'ensemble la plus rentable
mpstat -P ALL 1 3         # 4. un seul cœur à 100 % ? (mono-thread, ou softirq réseau non réparti)
pidstat 1 3               # 5. QUI consomme
iostat -xz 1 3            # 6. await, aqu-sz, %util par disque
free -m                   # 7. available, pas "free"
sar -n DEV 1 3            # 8. débit par interface
ss -s ; nstat             # 9. sockets, retransmissions, overflows
cat /proc/pressure/{cpu,io,memory}   # 10. PSI : le meilleur indicateur de saturation
```

**Lire `vmstat 1` :**

```
procs -----------memory---------- ---swap-- -----io---- -system-- ------cpu-----
 r  b   swpd   free   buff  cache   si   so    bi    bo   in   cs us sy id wa st
 9  2      0 210344  81232 2914112    0    0  4212  1180 9241 21044 74 12  6  8  0
```

| Colonne | Lecture |
|---|---|
| `r` | processus **prêts à tourner**. `r` durablement > nb de cœurs = **saturation CPU** |
| `b` | processus bloqués en I/O ininterruptible (état D) |
| `si`/`so` | swap in/out. **Doit être 0.** Sinon la latence explose |
| `wa` | temps CPU à attendre le disque → goulot **I/O** |
| `st` | *steal* : l'hyperviseur t'a pris du CPU → **voisin bruyant** sur la VM |
| `cs` | changements de contexte : 21 000/s pour 9 runnables = beaucoup de contention/IRQ |

> ⚠️ **PIÈGE** — Sous Linux, le **load average compte aussi les processus en état D** (attente disque
> ininterruptible), contrairement aux autres Unix. Un load de 40 sur 8 cœurs peut vouloir dire « CPU saturé »
> **ou** « NFS qui ne répond plus » — deux mondes. Ne conclus jamais sur le seul load : regarde `r` et `b`
> séparément dans `vmstat`, ou mieux, `/proc/pressure/*` qui distingue proprement CPU, I/O et mémoire.

> ⚠️ **PIÈGE** — `%util = 100 %` dans `iostat` **ne veut pas dire disque saturé** sur un SSD/NVMe. Le compteur
> mesure « le temps pendant lequel au moins une requête était en vol » ; un NVMe traite 32 requêtes en
> parallèle et affiche 100 % à 5 % de sa capacité réelle. Les indicateurs valides sont `await` (latence, en ms)
> et `aqu-sz` (profondeur moyenne de file).

**L'échelle de latence à connaître par cœur** — c'est elle qui te dit si un chiffre est absurde :

| Opération | Ordre de grandeur |
|---|---|
| Accès cache L1 | ~1 ns |
| Accès RAM | ~100 ns |
| Appel système | 0,3 - 1 µs |
| Changement de contexte | 1 - 5 µs |
| Aller-retour loopback | 30 - 50 µs |
| Lecture NVMe 4 Ko | 20 - 100 µs |
| Lecture SSD SATA | ~150 µs |
| RTT même rack | 0,1 - 0,2 ms |
| RTT inter-AZ, même région | 0,5 - 2 ms |
| Seek disque mécanique | 5 - 10 ms |
| RTT Paris ↔ Francfort | ~10 ms |
| RTT Europe ↔ US-Est | 75 - 90 ms |
| RTT Europe ↔ Singapour | ~160 ms |

**Règle du pouce** : **≈ 1 ms de RTT par 100 km** de fibre (la lumière va à ~200 000 km/s dans le verre,
aller-retour compris). Si un ping intra-datacenter affiche 40 ms, ce n'est pas de la distance : c'est de la
file d'attente, du CPU ou du GC.

> 🧠 **MÉMO** — **« Le load ne dit pas QUI, il dit COMBIEN. »** Séquence mentale : `vmstat` te dit **quelle
> ressource** (r → CPU, b/wa → disque, si/so → mémoire, rien de tout ça → réseau ou verrous) ; `pidstat` te dit
> **quel processus** ; puis l'outil spécialisé te dit **pourquoi**.

> ❓ **RETIENS ÇA** — CPU à 30 %, disque à 10 %, mémoire libre, et pourtant le débit plafonne. Où regarder ?
> <details><summary>→ réponse</summary><br>Le réseau ou la sérialisation applicative : <code>ss -ti</code> (cwnd, rtt, retrans), <code>nstat</code> (retransmissions, overflows), <code>ip -s link</code> (dropped). Un plafond « propre » sans consommation de ressource = fenêtre TCP trop petite pour le BDP, ou un seul thread bloquant.</details>

---

## 22. Exercices intégralement corrigés

### Exercice 1 — Sélection de route

```
default via 10.0.1.1 dev eth0 metric 100
10.0.0.0/8 via 10.0.1.254 dev eth0 metric 10
10.0.3.0/24 via 10.0.1.9 dev eth0 metric 600
10.0.3.7 via 10.0.1.50 dev eth0 metric 900
192.168.0.0/16 dev eth1 scope link metric 50
```
Par où sortent `10.0.3.7`, `10.0.3.99`, `10.5.0.1`, `192.168.4.4`, `8.8.8.8` ?

**Correction.** On applique le *longest prefix match* **avant** toute métrique.
- `10.0.3.7` → matche `/0`, `/8`, `/24` et `/32`. Le plus long est le **/32** → **via 10.0.1.50**, malgré sa métrique 900. *La métrique ne départage que des préfixes de longueur égale.*
- `10.0.3.99` → matche `/0`, `/8`, `/24`. Pas le /32 (adresse différente). Le plus long = **/24 → via 10.0.1.9**.
- `10.5.0.1` → matche `/0` et `/8`. → **via 10.0.1.254**.
- `192.168.4.4` → matche `/0` et `/16`. Le /16 est `scope link` : pas de `via`, on **ARP directement 192.168.4.4** sur `eth1`.
- `8.8.8.8` → seule la `default` matche → **via 10.0.1.1**.

Vérification systématique en une commande : `ip route get 10.0.3.99`.

### Exercice 2 — Dimensionner conntrack sur une passerelle

Passerelle NAT, 12 000 nouvelles connexions/s, durée moyenne d'une connexion active 4 s, protocole TCP.
`nf_conntrack_max = 262144`. Est-ce suffisant ? Et si les clients ferment mal ?

**Correction.**
1. **Régime nominal** (loi de Little : `N = λ × T`) : `12 000 × 4 = 48 000` entrées simultanées.
   48 000 / 262 144 = **18 %**. Confortable.
2. **Mais** : une connexion fermée proprement passe en `TIME_WAIT` côté conntrack pendant
   `nf_conntrack_tcp_timeout_time_wait = 120 s`. Donc en réalité `12 000 × 120 = 1 440 000` entrées.
   **5,5× le plafond → table pleine, drops aléatoires.**
3. **Pire cas** : des connexions qui ne se ferment jamais proprement (client tué, RST perdu) restent
   `ESTABLISHED` pendant **432 000 s = 5 jours**. Même 1 % de fuite = `120 × 432 000 = 51 840 000` entrées.
4. **Mémoire** : à ≈ 300 octets/entrée, 1 440 000 entrées ≈ **432 Mo** de RAM noyau non swappable.

**Conclusion opérationnelle** : monter `nf_conntrack_max` à 2 097 152 (avec `nf_conntrack_buckets` = max/4 ≈
524 288) coûte ~600 Mo ; **réduire `tcp_timeout_established` à 3 600 s et `time_wait` à 30 s** est bien plus
efficace ; et pour un flux massif connu (réplication, backup), le mettre en `NOTRACK` dans la table `raw`
supprime le problème à la racine.

### Exercice 3 — Diagnostiquer une capture

```
09:12:04.100211 IP 10.244.1.7.44012 > 10.96.0.20.8080: Flags [S], seq 91002, win 64240, length 0
09:12:05.101880 IP 10.244.1.7.44012 > 10.96.0.20.8080: Flags [S], seq 91002, win 64240, length 0
09:12:07.105940 IP 10.244.1.7.44012 > 10.96.0.20.8080: Flags [S], seq 91002, win 64240, length 0
09:12:11.113998 IP 10.244.1.7.44012 > 10.96.0.20.8080: Flags [S], seq 91002, win 64240, length 0
```

**Correction.** Quatre observations, dans l'ordre :
1. **Même `seq 91002`** et même port source : ce sont des **retransmissions** du même SYN, pas 4 tentatives.
2. Intervalles **1 s, 2 s, 4 s** : le *backoff exponentiel* canonique de Linux. Il ira jusqu'à
   `tcp_syn_retries = 6`, soit ≈ **127 s** avant `ETIMEDOUT`.
3. **Aucun SYN+ACK et aucun RST** : le paquet est jeté **en silence**. Un port fermé aurait produit un RST
   immédiat ; un routeur sans route aurait produit un ICMP.
4. `10.96.0.20` est un **ClusterIP** Kubernetes.

**Verdict** : soit le DNAT n'a pas eu lieu (Service sans endpoint prêt → kube-proxy n'installe aucune règle
`KUBE-SEP`, et le paquet est jeté par `KUBE-SERVICES`), soit une NetworkPolicy DROP. **Test discriminant** :
capturer sur le **nœud du pod cible**. Si le SYN n'y arrive pas → problème d'origine (endpoints, policy) ; s'il
y arrive et meurt → filtrage local sur la destination. Commandes : `kubectl get endpointslices`, puis
`iptables -t nat -L KUBE-SERVICES -n -v | grep 10.96.0.20`.

### Exercice 4 — Fenêtre TCP et buffers

Transfert S3 entre l'Europe et us-east-1 : RTT **80 ms**, lien 10 Gbit/s, débit observé **6,5 Mbit/s**. Que
régler ?

**Correction.**
1. Débit = fenêtre / RTT ⇒ fenêtre effective = `6,5e6 × 0,080 / 8` = **65 000 octets ≈ 65 535**. C'est
   **exactement** le champ Window de 16 bits **sans window scaling**. Diagnostic : le scaling est absent ou
   la fenêtre est figée par un `SO_RCVBUF` explicite.
2. **BDP nécessaire** pour saturer 10 Gbit/s : `10e9 × 0,080 / 8` = **100 Mo**. Irréaliste ; visons 1 Gbit/s :
   `1e9 × 0,080 / 8` = **10 Mo**.
3. Réglages : `net.ipv4.tcp_rmem = 4096 131072 33554432` et `net.core.rmem_max = 33554432` (32 Mo), idem en
   écriture. Vérifier `wscale` ≥ 8 dans `ss -ti` (`65535 × 2⁸ = 16,7 Mo`).
4. **Vérifier que l'application ne fixe pas `SO_RCVBUF`** : si elle le fait, l'auto-tuning est neutralisé et
   les sysctl ne servent à rien. C'est le cas de beaucoup de SDK (paramètre `socket.receive.buffer.bytes` chez
   Kafka : `-1` = laisser l'OS décider, c'est presque toujours le bon choix).
5. Si `retrans` est élevé dans `ss -ti`, passer en `bbr` (`net.ipv4.tcp_congestion_control=bbr`) : CUBIC
   s'effondre sur les longs liens à faible perte résiduelle.

---

## 23. Questions d'entretien

**1. Pourquoi `ip` plutôt qu'`ifconfig` ?**
> Parce que net-tools lit des formats `/proc` figés des années 90 alors qu'`ip` parle **netlink**, l'API
> officielle du noyau. Conséquence concrète : `ifconfig` ne montre qu'une adresse par interface, ignore les
> tables de routage secondaires, le policy routing, les VRF, et gère mal IPv6. `ip` voit tout ce que le noyau
> sait. Même logique pour `ss` vs `netstat` : `ss` filtre **dans le noyau** via `sock_diag`, `netstat` parse
> `/proc/net/tcp` en entier — sur 200 000 sockets, c'est quelques centaines de millisecondes contre plusieurs
> minutes.

**2. Un service n'est pas joignable. Ta démarche ?**
> Je descends la pile dans l'ordre, sans sauter d'étage : `ip -br link` (interface UP, pas NO-CARRIER),
> `ip -br addr` (une IP, pas du 169.254), `ip neigh` (la passerelle répond en ARP), `ip route get <dst>` (route
> et IP source attendue), `getent hosts` (le DNS tel que le voit l'application, pas `dig`), `nc -zv` (refused
> vs timeout), `ss -lntp` côté serveur (écoute-t-il sur 0.0.0.0 ou seulement sur 127.0.0.1 ?), enfin
> `tcpdump` des deux côtés pour savoir de quel côté le paquet disparaît, et les compteurs des règles de
> filtrage. La distinction clé est **RST immédiat = personne n'écoute**, **silence = quelque chose DROPpe**.

**3. Décris l'ordre de traversée de Netfilter.**
> Cinq crochets : PREROUTING, INPUT, FORWARD, OUTPUT, POSTROUTING. En entrée : `raw` (−300), conntrack (−200),
> `mangle` (−150), `nat`/DNAT (−100), puis **la décision de routage**, qui envoie soit vers INPUT soit vers
> FORWARD, où `filter` (0) s'applique, puis POSTROUTING avec `mangle` puis `nat`/SNAT (+100). Le DNAT est
> forcément **avant** le routage puisqu'il change la destination ; le SNAT forcément **après** puisque l'adresse
> à poser dépend de l'interface de sortie choisie. Les paquets émis localement passent par OUTPUT avec une
> re-vérification de routage si un DNAT ou un MARK les a modifiés.

**4. Comment un conteneur obtient-il son réseau ?**
> Il reçoit un **network namespace** : sa propre pile — interfaces, routes, ARP, ports, netfilter, conntrack.
> On y pousse un bout d'une **paire veth**, l'autre bout étant branché sur un **bridge** de l'hôte (`docker0`)
> qui sert de switch et de passerelle. L'hôte a `ip_forward=1` et une règle **MASQUERADE** pour que le réseau
> privé du conteneur puisse sortir. La publication de port `-p 8080:80` n'est pas un proxy : c'est une règle
> **DNAT** en PREROUTING. On peut reproduire tout ça à la main en six commandes `ip`.

**5. À quoi sert conntrack et que se passe-t-il quand la table est pleine ?**
> C'est la table d'état du noyau : un flux = une entrée avec son tuple d'origine et son tuple de réponse
> attendu. Elle permet le pare-feu à état (`ct state established,related accept`) et **tout le NAT**, puisque la
> traduction n'est calculée que sur le premier paquet et rejouée ensuite par conntrack. Quand elle sature, le
> noyau logue `table full, dropping packet` et **jette du trafic au hasard** : des timeouts erratiques et
> irreproductibles. On surveille `nf_conntrack_count / nf_conntrack_max`, on compte ~300 octets par entrée, et
> on corrige d'abord les **timeouts** (5 jours par défaut sur `ESTABLISHED`) avant d'augmenter le plafond.

**6. `Recv-Q` non nul sur un socket en LISTEN, ça veut dire quoi ?**
> Que des connexions **déjà établies** attendent que l'application appelle `accept()`. Sur un LISTEN, `Recv-Q`
> est la longueur courante de l'accept queue et `Send-Q` sa capacité (`min(backlog, somaxconn)`). Si `Recv-Q`
> atteint `Send-Q`, le noyau jette les connexions suivantes et `TcpExtListenOverflows` monte dans `nstat`. Ce
> n'est **pas** un problème réseau : c'est l'application qui n'accepte pas assez vite — threads bloqués, GC,
> pool épuisé. Augmenter `somaxconn` ne fait que décaler le problème.

**7. Différence entre SNAT et MASQUERADE ?**
> Les deux réécrivent l'adresse source en POSTROUTING. `SNAT` prend une adresse **fixe** que tu fournis :
> rapide et déterministe, mais il faut une IP statique. `MASQUERADE` prend **l'IP courante de l'interface de
> sortie**, ce qui le rend indispensable en IP dynamique (DHCP, ADSL) ; il coûte un peu plus cher car il
> interroge l'interface, et il **purge les entrées conntrack** quand l'interface tombe — ce qui évite de garder
> des traductions vers une adresse disparue.

**8. `tcpdump` ne montre rien alors que le client dit qu'il envoie. Pistes ?**
> Dans l'ordre : mauvaise interface (essayer `-i any`, et penser aux veth/bridge côté conteneur) ; filtre BPF
> trop restrictif ou faux (retirer le filtre et regarder brut) ; le trafic est **fragmenté** et le filtre de port
> ne matche que le premier fragment ; le paquet ne sort pas du tout du client (mauvaise route, `ip route get`) ;
> le trafic passe par une autre machine (ECMP, deuxième interface) ; ou l'on capture **dans le mauvais network
> namespace** — cas très fréquent avec Docker/K8s, où il faut `nsenter -t <pid> -n tcpdump`.

**9. À quoi sert `net.ipv4.ip_forward` et pourquoi Docker le met à 1 ?**
> Il autorise le noyau à relayer un paquet dont la destination n'est pas une adresse locale, au lieu de le
> jeter — c'est-à-dire à se comporter en routeur. Docker en a besoin parce que le trafic d'un conteneur arrive
> sur `docker0` avec une destination externe : sans forwarding, il meurt là. C'est aussi pour ça que les règles
> qui protègent des ports publiés doivent aller dans la chaîne **FORWARD** (`DOCKER-USER`) et pas dans INPUT.

**10. Comment décides-tu si un problème est CPU, mémoire, disque ou réseau ?**
> Méthode USE : pour chaque ressource, utilisation / saturation / erreurs — et la **saturation** est le signal
> utile, pas l'utilisation. En pratique, `vmstat 1` en premier : `r` > nombre de cœurs = CPU ; `b` et `wa`
> élevés = disque ; `si/so` ≠ 0 = mémoire ; `st` = voisin bruyant sur la VM. Si rien de tout ça ne bouge et que
> ça plafonne quand même, c'est le réseau ou de la sérialisation applicative : `ss -ti` (cwnd, rtt, retrans),
> `nstat`, `ip -s link`. Je regarde aussi `/proc/pressure/*`, qui sépare proprement les trois pressions là où
> le load average de Linux mélange CPU et attente disque.

---

## 24. Les 3 choses à retenir si tu ne retiens que ça

**① On diagnostique de bas en haut, jamais autrement.**
Interface → Adresse → Voisin → Route → DNS → Socket → Filtre → Appli. Huit étages, huit commandes
(`ip -br link`, `ip -br addr`, `ip neigh`, `ip route get`, `getent hosts`, `nc -zv`/`ss -lntp`,
`nft list ruleset`, `curl -v`). Et un test qui tranche tout de suite : **RST immédiat = personne n'écoute ;
silence = quelque chose DROPpe.**

**② Netfilter est le squelette, tout le reste est du décor.**
5 crochets, l'ordre `raw → conntrack → mangle → nat → routage → filter → nat`. **DNAT avant le routage, SNAT
après.** Docker, kube-proxy, les VPN, les CNI ne font rien d'autre qu'écrire dans ces chaînes. Quand tu sais
lire `iptables -t nat -L -n -v`, tu débogues Kubernetes.

**③ Un conteneur, c'est un namespace + une veth + un bridge + du MASQUERADE.**
Rien de magique : tu peux le refaire en six commandes `ip`. Et pour la performance, une seule séquence :
`vmstat` dit **quelle ressource**, `pidstat` dit **quel processus**, l'outil spécialisé dit **pourquoi** — en
te souvenant que le load average de Linux compte aussi l'attente disque, et que `%util` à 100 % sur un NVMe ne
veut rien dire.
