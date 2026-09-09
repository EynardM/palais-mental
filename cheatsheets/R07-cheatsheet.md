# R07 — Cheatsheet : DNS, DHCP, NAT, load balancing

Référence opérationnelle. À garder ouverte pendant qu'on travaille.

---

## 1. Ports et transports

| Service | Transport | Port | Note |
|---|---|---|---|
| **DNS** | **UDP + TCP** | **53** | TCP obligatoire si TC=1, AXFR/IXFR, DNSSEC volumineux |
| **DoT** | TCP + TLS | **853** | filtrable (port dédié) |
| **DoH** | HTTPS | **443** | chemin `/dns-query`, indiscernable du web |
| **DoQ** | QUIC (UDP) | **853** | RFC 9250 |
| **mDNS** | UDP | 5353 | `.local`, multicast `224.0.0.251` |
| **LLMNR** | UDP | 5355 | Windows |
| **DHCPv4** | UDP | **67** serveur / **68** client | broadcast `255.255.255.255` |
| **DHCPv6** | UDP | **547** serveur / **546** client | multicast `ff02::1:2` |
| **TFTP** (PXE) | UDP | 69 | options DHCP 66/67 |
| **NTP** | UDP | 123 | option DHCP 42 |
| **IPsec IKE** | UDP | 500 | |
| **IPsec NAT-T** | UDP | **4500** | encapsulation ESP pour traverser un NAT |
| **STUN / TURN** | UDP/TCP | 3478 (TLS 5349) | contournement de NAT |
| **NodePort K8s** | TCP/UDP | **30000-32767** | plage par défaut |

---

## 2. `dig` — l'outil principal

| Commande | Ce qu'elle fait |
|---|---|
| `dig exemple.fr` | requête A, sortie complète |
| `dig exemple.fr +short` | juste la valeur |
| `dig exemple.fr +noall +answer` | juste la section ANSWER |
| `dig exemple.fr ANY` | souvent REFUSED aujourd'hui (RFC 8482) |
| `dig -x 93.184.215.14` | **reverse** : fabrique le `in-addr.arpa` |
| `dig @1.1.1.1 exemple.fr` | interroge un résolveur précis |
| `dig @ns1.exemple.fr exemple.fr` | interroge l'**autoritatif** → court-circuite tous les caches |
| `dig exemple.fr +trace` | refait la résolution **depuis la racine**, étape par étape |
| `dig exemple.fr +nssearch` | trouve et interroge tous les NS de la zone |
| `dig exemple.fr SOA +multiline` | SOA lisible, avec le serial |
| `dig +dnssec exemple.fr` | affiche RRSIG, montre le bit **ad** |
| `dig +cd exemple.fr` | **désactive** la validation DNSSEC → isole un SERVFAIL DNSSEC |
| `dig +tcp exemple.fr` / `+notcp` | force / interdit TCP |
| `dig +bufsize=1232 exemple.fr` | fixe la taille EDNS0 annoncée |
| `dig +noedns exemple.fr` | désactive EDNS0 (test des vieux pare-feux) |
| `dig +norecurse exemple.fr` | RD=0 : « réponds seulement si tu es autoritatif » |
| `dig +stats exemple.fr` | affiche `Query time`, serveur, taille du message |
| `dig AXFR exemple.fr @ns1...` | transfert de zone (refusé sauf ACL) |
| `dig +subnet=1.2.3.0/24` | teste le GeoDNS (EDNS Client Subnet) |

**Lire l'en-tête** : `status: NOERROR|NXDOMAIN|SERVFAIL|REFUSED` · `flags: qr aa rd ra ad tc` ·
`ANSWER: n`. **`aa`** = autoritatif · **`ad`** = DNSSEC validé · **`tc`** = tronqué · `Query time: 1 msec` = cache.

---

## 3. Autres outils DNS

```bash
host -a exemple.fr                     # rapide, verbeux
getent hosts exemple.fr                # passe par NSS : hosts + DNS, comme l'appli
getent ahostsv4 exemple.fr             # force IPv4
resolvectl query exemple.fr            # systemd-resolved
resolvectl status                      # quel DNS par interface, DNSSEC, DoT
resolvectl statistics ; resolvectl flush-caches
systemd-resolve --flush-caches         # (ancien nom)
kdig +tls @1.1.1.1 exemple.fr          # tester DoT
curl -H 'accept: application/dns-json' \
  'https://1.1.1.1/dns-query?name=exemple.fr&type=A'   # tester DoH (JSON Cloudflare)
delv exemple.fr                        # validation DNSSEC pas à pas
named-checkzone exemple.fr db.exemple.fr   # valider un fichier de zone
dnstop -l 3 eth0 ; tcpdump -ni any port 53 # observer le trafic DNS
```

**Fichiers** :

| Fichier | Contenu |
|---|---|
| `/etc/resolv.conf` | `nameserver`, `search`, `domain`, `options ndots:N timeout:N attempts:N` |
| `/etc/nsswitch.conf` | `hosts: files dns` → l'**ordre** des sources |
| `/etc/hosts` | statique, **avant** le DNS |
| `/run/systemd/resolve/resolv.conf` | le vrai fichier quand systemd-resolved est actif |

Options utiles de `resolv.conf` : `timeout:5` (défaut **5 s**), `attempts:2` (défaut **2**),
`ndots:1`, `single-request-reopen`, `rotate`, `use-vc` (forcer TCP).

---

## 4. Types d'enregistrement et RCODE

| Type | N° | Type | N° | RCODE | Nom |
|---|---|---|---|---|---|
| A | 1 | SRV | 33 | 0 | NOERROR |
| NS | 2 | OPT (EDNS0) | 41 | 1 | FORMERR |
| CNAME | 5 | DS | 43 | **2** | **SERVFAIL** |
| SOA | 6 | RRSIG | 46 | **3** | **NXDOMAIN** |
| PTR | 12 | NSEC | 47 | 4 | NOTIMP |
| MX | 15 | DNSKEY | 48 | **5** | REFUSED |
| TXT | 16 | NSEC3 | 50 | 9 | NOTAUTH |
| AAAA | 28 | TLSA | 52 | | |
| SVCB / HTTPS | 64 / 65 | CAA | 257 | | |
| IXFR / AXFR | 251 / 252 | ANY | 255 | | |

**Syntaxes de RDATA à écrire de mémoire** :

```
exemple.fr.        3600 IN SOA  ns1.exemple.fr. hostmaster.exemple.fr. (
                                2026090901 7200 3600 1209600 300 )
exemple.fr.        3600 IN NS   ns1.exemple.fr.
exemple.fr.        3600 IN MX   10 mail.exemple.fr.        ; préférence la plus BASSE gagne
www                 300 IN CNAME api.exemple.fr.           ; JAMAIS à l'apex
api                 300 IN A     51.10.20.30
_grpc._tcp.svc       30 IN SRV   10 60 8443 node-a.exemple.fr.   ; prio poids PORT cible
exemple.fr.        3600 IN TXT   "v=spf1 include:_spf.google.com ~all"
exemple.fr.        3600 IN CAA   0 issue "letsencrypt.org"
14.215.184.93.in-addr.arpa. 3600 IN PTR exemple.com.
```

**Ordres de grandeur de latence** : cache local < 1 ms · résolveur en cache 1-5 ms ·
résolution complète à froid **40-150 ms** · même AZ 0,2-0,5 ms RTT · inter-AZ 0,5-2 ms ·
Paris↔Francfort ~10-12 ms · Paris↔Virginie ~80-90 ms · Paris↔Singapour ~160-180 ms.
Fibre : ~5 µs/km, soit **~0,5 ms pour 100 km aller** (≈ **1 ms aller-retour**).

---

## 5. DHCP

| Option | Nom | Option | Nom |
|---|---|---|---|
| **1** | Subnet mask | **53** | **Message type** |
| **3** | Router | **54** | Server identifier |
| **6** | DNS servers | **55** | Parameter request list |
| 12 / 15 | Hostname / Domain | 58 / 59 | T1 / T2 |
| **26** | Interface MTU | 60 / 61 | Vendor class / Client id |
| 28 | Broadcast address | 66 / 67 | TFTP server / Bootfile (PXE) |
| 42 | NTP servers | **82** | Relay agent info |
| 50 | Requested IP | **121** | Classless static routes |
| **51** | Lease time | 255 | End |

**Option 53** : `1` DISCOVER · `2` OFFER · `3` REQUEST · `4` DECLINE · `5` ACK · `6` NAK · `7` RELEASE · `8` INFORM.

```bash
dhclient -v eth0                 # demander un bail, en verbeux
dhclient -r eth0                 # RELEASE
dhclient -v -1 eth0              # un seul essai, échoue au lieu de boucler
cat /var/lib/dhcp/dhclient.leases        # baux obtenus (Debian/Ubuntu)
cat /var/lib/dhcpd/dhcpd.leases          # côté serveur ISC
nmcli con show <con> | grep -i dhcp      # options reçues via NetworkManager
networkctl status eth0                   # systemd-networkd
journalctl -u systemd-networkd -f
tcpdump -ni eth0 -vv 'port 67 or port 68'   # LE filtre à connaître
dhcpdump -i eth0                            # décodage lisible des options
nmap --script broadcast-dhcp-discover        # détecter un serveur pirate
```

Config relais Cisco : `interface Vlan20` → `ip helper-address 10.9.0.5`.
Linux : `dhcrelay -i eth0 -i eth1 10.9.0.5`.

**Ligne du temps du bail** : `T1 = 0,5 × bail` (RENEW unicast) · `T2 = 0,875 × bail` (REBIND broadcast) ·
expiration → DISCOVER → sinon **APIPA `169.254.0.0/16`**.

---

## 6. NAT sous Linux

```bash
# --- iptables (legacy mais omniprésent) ---
iptables -t nat -L -n -v --line-numbers          # lire les règles NAT
iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE            # PAT dynamique (IP variable)
iptables -t nat -A POSTROUTING -s 10.0.0.0/24 -o eth0 \
         -j SNAT --to-source 203.0.113.7                        # SNAT statique (plus rapide)
iptables -t nat -A PREROUTING -i eth0 -p tcp --dport 443 \
         -j DNAT --to-destination 10.0.5.42:8443                # port forward
iptables -t mangle -A FORWARD -p tcp --tcp-flags SYN,RST SYN \
         -j TCPMSS --clamp-mss-to-pmtu                          # MSS clamping (MTU !)

# --- nftables (le remplaçant) ---
nft list ruleset
nft add table nat ; nft add chain nat post '{ type nat hook postrouting priority 100 ; }'
nft add rule nat post oifname eth0 masquerade

# --- conntrack : la table de traduction ---
conntrack -L                          # lister les connexions suivies
conntrack -L -p tcp --dport 443 | wc -l
conntrack -S                          # stats par CPU : insert_failed, drop, early_drop
conntrack -D -s 10.0.5.42             # supprimer les entrées d'une source
cat /proc/sys/net/netfilter/nf_conntrack_count
sysctl net.netfilter.nf_conntrack_max
dmesg | grep -i conntrack             # "table full, dropping packet"
```

| Paramètre sysctl | Défaut | Sens |
|---|---|---|
| `net.netfilter.nf_conntrack_max` | 65 536 / 262 144 | taille de la table |
| `nf_conntrack_tcp_timeout_established` | **432 000 s (5 j)** | TCP établi |
| `nf_conntrack_tcp_timeout_time_wait` | **120 s** | TIME_WAIT |
| `nf_conntrack_udp_timeout` | **30 s** | UDP simple |
| `nf_conntrack_udp_timeout_stream` | **180 s** | UDP établi |
| `nf_conntrack_icmp_timeout` | 30 s | ICMP |
| `net.ipv4.ip_local_port_range` | **32768-60999** | ports éphémères locaux |
| `net.ipv4.ip_forward` | 0 | **1 obligatoire** pour router/NAT |

**Ports disponibles pour le PAT** : 1024-65535 = **~64 512 par IP publique ET par destination unique**
(l'unicité porte sur le 5-uplet). AWS NAT Gateway : **55 000 conn./destination**, métrique
`ErrorPortAllocation`, timeout d'inactivité **350 s**.

**Blocs à connaître** : `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` (RFC 1918) ·
**`100.64.0.0/10` CGNAT** (RFC 6598) · `169.254.0.0/16` link-local/APIPA ·
`169.254.169.254` métadonnées cloud (AWS/GCP), `169.254.169.253` DNS AWS, `168.63.129.16` Azure ·
DNS d'un VPC AWS = **base du VPC + 2** (ex. `10.0.0.2`).

---

## 7. Load balancing

**HAProxy** (backend type) :

```
backend api
    balance roundrobin            # | leastconn | source | hdr(host) | uri
    option httpchk GET /healthz
    http-check expect status 200
    cookie SRVID insert indirect nocache
    default-server inter 2s rise 2 fall 3 maxconn 200
    server s1 10.0.5.11:8080 check cookie s1
    server s2 10.0.5.12:8080 check cookie s2 weight 200
```

**nginx** (upstream) :

```
upstream api {
    least_conn;                 # | ip_hash; | hash $arg_user consistent;
    keepalive 32;               # pool de connexions réutilisées vers l'amont
    server 10.0.5.11:8080 max_fails=3 fail_timeout=10s;
    server 10.0.5.12:8080 backup;
}
proxy_read_timeout 60s;  proxy_connect_timeout 5s;  proxy_next_upstream error timeout http_502;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
```

| Défauts à connaître | Valeur |
|---|---|
| HAProxy `inter` / `rise` / `fall` | **2000 ms / 2 / 3** |
| nginx `max_fails` / `fail_timeout` | **1 / 10 s** |
| nginx `proxy_read_timeout` / `keepalive_timeout` | **60 s / 75 s** |
| AWS ALB health check intervalle / timeout | **30 s / 5 s** |
| AWS **ALB** idle timeout | **60 s** |
| AWS **NLB** idle timeout (TCP) | **350 s** |
| Détection d'un backend mort | ≈ **`interval × fall` (+ timeout)** |

**Codes renvoyés par un LB** : **502** amont injoignable / réponse invalide · **503** aucun backend sain ·
**504** amont trop lent (timeout). Sur ALB : **460** client parti avant la réponse, **463** trop d'IP dans
`X-Forwarded-For`.

**En-têtes** : `X-Forwarded-For`, `X-Forwarded-Proto`, `X-Forwarded-Host`, `Forwarded` (RFC 7239).
En L4 : **PROXY protocol** v1 (texte) / v2 (binaire), à activer **des deux côtés**.

**IPVS / kube-proxy** :

```bash
ipvsadm -Ln                    # règles IPVS, backends et compteurs
ipvsadm -Lnc                   # connexions suivies
ipvsadm -Ln --stats
# Modes IPVS : NAT (masq) | DR (direct routing = DSR) | TUN (IPIP)
# Algos IPVS : rr wrr lc wlc lblc sh dh sed nq
```

**DSR côté serveur (Linux)** :

```bash
ip addr add 203.0.113.7/32 dev lo            # la VIP sur la loopback
sysctl -w net.ipv4.conf.all.arp_ignore=1     # ne pas répondre aux ARP pour la VIP
sysctl -w net.ipv4.conf.all.arp_announce=2
```

---

## 8. Kubernetes — diagnostic

```bash
kubectl get svc -A                              # ClusterIP, type, ports
kubectl get endpointslices -n data              # QUELS pods reçoivent vraiment le trafic
kubectl describe svc api -n data | grep -i endpoints
kubectl -n kube-system get cm coredns -o yaml   # le Corefile
kubectl -n kube-system logs -l k8s-app=kube-dns -f
kubectl -n kube-system top pod -l k8s-app=kube-dns

# depuis un pod jetable
kubectl run dbg --rm -it --image=nicolaka/netshoot -- bash
  cat /etc/resolv.conf
  dig api.data.svc.cluster.local
  dig +short api.data.svc.cluster.local
  dig SRV _http._tcp.api.data.svc.cluster.local
  dig s3.eu-west-3.amazonaws.com.        # AVEC le point final : évite ndots
  for i in $(seq 50); do dig +tries=1 +time=1 api.data.svc.cluster.local >/dev/null || echo KO; done
```

| Nom | Résout vers |
|---|---|
| `<svc>.<ns>.svc.cluster.local` | ClusterIP (ou tous les pods si headless) |
| `<pod>.<svc>.<ns>.svc.cluster.local` | un pod précis d'un StatefulSet |
| `_<port>._<proto>.<svc>.<ns>.svc.cluster.local` | SRV (prio, poids, **port**, cible) |
| `<ip-avec-tirets>.<ns>.pod.cluster.local` | un pod par son IP |

**Réglages anti-`ndots`** dans un pod :

```yaml
dnsConfig:
  options:
    - name: ndots
      value: "1"
    - name: single-request-reopen      # contre les timeouts de 5 s
```

---

## 9. Diagnostic transverse

```bash
ss -tanp state established | wc -l          # connexions établies
ss -s                                        # résumé par état, dont TIME-WAIT
ss -tan state time-wait | wc -l
ss -tulpn                                    # qui écoute quoi
curl -sS -o /dev/null -w \
 'dns=%{time_namelookup} tcp=%{time_connect} tls=%{time_appconnect} ttfb=%{time_starttransfer} tot=%{time_total}\n' \
 https://api.exemple.fr/          # DÉCOMPOSE la latence : DNS vs TCP vs TLS vs appli
curl --resolve api.exemple.fr:443:10.0.5.42 https://api.exemple.fr/   # bypasser le DNS
mtr -rw api.exemple.fr                       # chemin + perte par saut
tracepath api.exemple.fr                     # découvre le PMTU sans droits root
ping -M do -s 1472 8.8.8.8                   # 1472 + 28 = 1500 : teste le MTU
tcpdump -ni any 'port 53' -c 20
tcpdump -ni any 'port 67 or port 68' -vv
tcpdump -ni any 'icmp[icmptype] == 3 and icmp[icmpcode] == 4'   # Fragmentation Needed
```

**Calcul MTU/MSS** : `MSS = MTU − 40` (IPv4 20 + TCP 20) → **1460** sur 1500.
Surcoût d'encapsulation : **VXLAN 50** (MTU 1450) · **GRE 24** · **WireGuard 60 (v4) / 80 (v6)** ·
**IPsec ESP 50-73** · **MPLS 4 par label** · PPPoE 8 (MTU 1492).

**Le réflexe en 4 gestes quand « ça ne marche pas »** :
`getent hosts <nom>` (le nom résout-il **comme l'appli** ?) → `curl -w` (où part le temps ?) →
`ss -tan` (les connexions s'établissent-elles ?) → `tcpdump` des deux côtés (qui ne répond pas ?).
