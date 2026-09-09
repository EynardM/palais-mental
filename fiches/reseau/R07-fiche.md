# R07 — Fiche : DNS, DHCP, NAT, load balancing

> Lis-la **avant** le cours (pretesting) puis **récite-la** aux rappels. Objectif : 3 minutes.

## Les 4 questions

**DNS** « qui es-tu ? » · **DHCP** « qui suis-je ? » · **NAT** « sous quel nom je sors ? » · **LB** « lequel d'entre eux ? »

## DNS — acteurs

| Acteur | Rôle | Ne fait pas |
|---|---|---|
| **Stub** (libc, `resolv.conf`) | pose **1** question, **RD=1** | ne parcourt jamais l'arbre |
| **Résolveur récursif** | parcourt l'arbre, **cache tout** | ne fait autorité sur rien |
| **Racine** (13 noms `a`→`m`, anycast) | renvoie les NS du TLD | ne connaît aucun `www` |
| **Autoritatif** | détient la zone, **AA=1** | ne résout pas pour toi |

**Récursif** = « rends-moi la réponse finale ». **Itératif** = « donne ce que tu sais, même un renvoi ».
**Domaine** = nœud + sous-arbre. **Zone** = ce qu'un serveur sert vraiment, **délégations retranchées**.
**Glue record** = A du NS publié par le **parent**, obligatoire si le NS est *in-bailiwick*.

## DNS — chiffres

Port **UDP/TCP 53** · DoT **TCP 853** · DoH **HTTPS 443** `/dns-query` · DoQ **UDP 853**.
En-tête **12 o** = ID(2) + flags(2) + QDCOUNT + ANCOUNT + NSCOUNT + ARCOUNT (2 chacun).
Label **≤ 63 o** · FQDN **≤ 255 o** · UDP sans EDNS0 **512 o** → **TC=1 → rejeu en TCP** · EDNS0 = OPT **type 41**, annoncer **1232 o**.
**Flags** : `QR | Opcode(4) | AA | TC | RD | RA | Z | AD | CD | RCODE(4)`.
**RCODE** : 0 NOERROR · 1 FORMERR · **2 SERVFAIL** (dont échec DNSSEC) · **3 NXDOMAIN** · 5 REFUSED.
⚠ **NOERROR + ANCOUNT=0 = NODATA** : le nom existe, pas ce type. ≠ NXDOMAIN.

| Type | N° | Contenu | Piège |
|---|---|---|---|
| A / AAAA | 1 / 28 | IPv4 / IPv6 | — |
| **CNAME** | 5 | alias | **interdit à l'apex**, exclusif de tout autre type |
| **MX** | 15 | préf + nom | **préférence la plus BASSE gagne**, cible ≠ CNAME |
| TXT | 16 | chaînes ≤255 o | SPF/DKIM/DMARC/ACME |
| **SRV** | 33 | prio, poids, **port**, cible | `_service._proto.domaine` |
| PTR | 12 | nom | `in-addr.arpa` (IPv4 inversée) / `ip6.arpa` (nibbles) |
| NS / SOA | 2 / 6 | délégation / params | SOA unique, à l'apex |
| HTTPS/SVCB | 65 / 64 | alias + ALPN | **légal à l'apex** |

**SOA** = MNAME · RNAME · **SERIAL** · REFRESH · RETRY · EXPIRE · **MINIMUM = TTL du cache NÉGATIF**.
**DNSSEC** : **DNSKEY**(48, KSK flag 257 / ZSK 256) · **RRSIG**(46) · **DS**(43, hash de la KSK **chez le parent**) · NSEC/NSEC3 (preuve d'absence). Algo 8 RSASHA256, **13 ECDSA P-256**, 15 Ed25519. **Signe, ne chiffre pas.** Échec → **SERVFAIL**. Bit **AD** = validé, **CD** = ne valide pas.
**TTL** : 30-60 s failover · 300 s appli · 3600 s stable · 86400 s NS/MX · 172800 s délégations TLD.
**Migration** : baisser le TTL → **attendre l'ANCIEN TTL** → basculer → remonter. La JVM cache **30 s** (négatif **10 s**) en **ignorant** le TTL. `getaddrinfo()` **ne cache rien**.

## DNS dans Kubernetes

`<svc>.<ns>.svc.cluster.local` → ClusterIP · **headless** (`clusterIP: None`) → 1 A par pod prêt · `<pod>.<svc>.<ns>.svc.cluster.local` (StatefulSet) · SRV `_<port>._<proto>.<svc>.<ns>.svc.cluster.local`.
CoreDNS sur la ClusterIP **10.96.0.10** · `search ns.svc.cluster.local svc.cluster.local cluster.local` · **`options ndots:5`**.
⚠ **ndots:5** : nom à < 5 points → 3 essais search AVANT le vrai → ×2 (A+AAAA) = **8 paquets**. Fix : **FQDN avec point final**, `ndots:1`, **NodeLocal DNSCache** (169.254.20.10, + TCP).
⚠ **Timeout DNS de 5,00 s** = course conntrack A/AAAA sur le même port source → `single-request-reopen`, NodeLocal, IPVS.

## DHCP

**UDP 68 (client) ↔ 67 (serveur)** · base BOOTP (fixe **236 o**) + magic cookie **0x63825363** · `xid` corrèle.
**D**ISCOVER(53=1) bcast → **O**FFER(2) `yiaddr` → **R**EQUEST(3) **en broadcast** (les autres libèrent) → **A**CK(5). NAK=6, DECLINE=4, RELEASE=7.
**Bail** : `T1 = 50 %` (RENEW **unicast**) · `T2 = 87,5 %` (REBIND **broadcast**) · 100 % → DISCOVER. Défauts : 8 j (Windows), 12-24 h (Linux/box).
**Options** : 1 masque · 3 routeur · 6 DNS · **26 MTU** · 42 NTP · **51 bail** · **53 type** · **54 server id** · **55 param request list** · 58/59 T1/T2 · 66/67 PXE · **82 relay info** · 121 routes statiques · 255 end.
**Relais** (`ip helper-address`) : pose **`giaddr`** = son IP sur le VLAN client (→ choix du scope), `hops++`, opt 82. Sans giaddr, rien ne marche.
DHCPv6 : **546/547**, `ff02::1:2`, **SOLICIT-ADVERTISE-REQUEST-REPLY**.

## NAT

**SNAT** réécrit la source (sortie) · **DNAT** la destination (entrée) · **PAT/masquerade** = SNAT + **port**.
Entrée = **5-uplet** (proto, IP src, port src, IP dst, port dst). ~**64 512 ports** (1024-65535) **par IP publique ET par destination unique**.
Linux `nf_conntrack` : TCP établi **432 000 s (5 j)** · `time_wait` **120 s** · **UDP 30 s** (180 s en flux) · ICMP 30 s. `nf_conntrack_max` 65 536 / 262 144.
AWS NAT GW : **55 000 conn. simultanées par destination**, métrique **`ErrorPortAllocation`**, idle **350 s**. Fix = **VPC Endpoint**, 1 NAT GW/AZ, keep-alive.
**Ce que le NAT casse** : FTP **actif** (`PORT` dans le payload) · SIP/WebRTC (SDP → STUN/TURN/ICE) · **IPsec AH** (le hash couvre l'en-tête IP ; ESP passe via **NAT-T UDP 4500**) · ICMP · P2P entrant · attribution/logs.
**Hairpinning** : interne → IP publique → retour direct src ≠ attendue → paquet jeté. Vraie parade = **split-horizon DNS**.
⚠ Le NAT **n'est pas un pare-feu**. CGNAT = `100.64.0.0/10` (RFC 6598), double NAT.

## Load balancing

| | **L4** | **L7** |
|---|---|---|
| Décide sur | IP/port | Host, path, en-têtes, cookies |
| Connexions | 1, relayée | **2**, terminées |
| TLS | passthrough | terminé |
| Latence | ~0,1-0,5 ms | ~1-5 ms |
| Retry/timeout | non | oui |
| Granularité | **connexion** | **requête** |

⚠ **HTTP/2 & gRPC** : 1 connexion multiplexée → un **L4 n'équilibre plus rien**. → L7 ou LB côté client.
**Algos** : RR (uniforme) · **least conn** (durées variables) · P2C/random (grands pools) · **hash** (affinité).
**`hash mod N`, 10→11 backends = ~91 % de clés déplacées. Hachage cohérent = ~9 % = 1/(N+1).**
**Health checks** : détection ≈ **`interval × fall` (+ timeout)**. HAProxy `inter 2s / rise 2 / fall 3` · nginx passif `max_fails=1 fail_timeout=10s` · ALB 30 s / 5 s. ⚠ Ne jamais tester une **dépendance partagée** → éjection totale.
**Timeouts d'inactivité** : **ALB 60 s** · **NLB 350 s** · nginx `proxy_read_timeout 60s`. → 504 sur requête longue.
**Persistance** : source IP (casse en CGNAT) · cookie inséré (`AWSALB`) · cookie appli · hachage cohérent. C'est une dette : sors l'état.
**DSR** : le LB réécrit **seulement la MAC de destination**, IP inchangées ; VIP sur la **loopback** du serveur, `arp_ignore=1 arp_announce=2`. Retour direct → **pas de L7, pas de TLS**, même L2 requis.
**Proxy direct** = configuré par le client, le sert · **reverse proxy** = invisible du client, sert le serveur. Un LB L7 **est** un reverse proxy.
**K8s** : ClusterIP = règle DNAT sur chaque nœud (portée par **aucune** interface) · kube-proxy = **L4** (iptables probabiliste / IPVS hash / nftables) · NodePort **30000-32767** · `externalTrafficPolicy: Local` **garde l'IP source** mais déséquilibre.
**MTU** : VXLAN **−50** (→1450) · GRE −24 · WireGuard −60/−80 · IPsec −50/73 · MPLS −4. ICMP bloqué → **PMTUD aveugle** → gros transferts qui gèlent. Fix : **MSS clamping**.

## Test express

1. Quelle est la différence entre une zone et un domaine ?
2. Que se passe-t-il quand une réponse DNS dépasse la taille UDP annoncée ?
3. Pourquoi un CNAME est-il impossible à l'apex d'une zone ?
4. Que définit le dernier champ du SOA ?
5. Pourquoi le REQUEST de DORA part-il en broadcast ?
6. Quel champ dit au serveur DHCP dans quel scope piocher derrière un relais ?
7. Combien de connexions simultanées peut porter une IP publique NAT vers **une** destination unique ?
8. Combien de clés bougent en `hash mod N` quand on passe de 10 à 11 backends ?
