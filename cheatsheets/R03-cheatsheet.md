# R03 — Cheatsheet : IPv4, CIDR, subnetting, IPv6, ICMP

Référence opérationnelle. À garder ouverte pendant qu'on travaille.

---

## 1. Table des masques — la référence

| /n | Masque | Wildcard (ACL) | Adresses | Hôtes | Bloc | Dernier octet binaire |
|---|---|---|---|---|---|---|
| /8 | 255.0.0.0 | 0.255.255.255 | 16 777 216 | 16 777 214 | 1 (oct. 1) | — |
| /12 | 255.240.0.0 | 0.15.255.255 | 1 048 576 | 1 048 574 | 16 (oct. 2) | — |
| /16 | 255.255.0.0 | 0.0.255.255 | 65 536 | 65 534 | 1 (oct. 2) | — |
| /17 | 255.255.128.0 | 0.0.127.255 | 32 768 | 32 766 | 128 (oct. 3) | — |
| /18 | 255.255.192.0 | 0.0.63.255 | 16 384 | 16 382 | 64 (oct. 3) | — |
| /19 | 255.255.224.0 | 0.0.31.255 | 8 192 | 8 190 | 32 (oct. 3) | — |
| /20 | 255.255.240.0 | 0.0.15.255 | 4 096 | 4 094 | 16 (oct. 3) | — |
| /21 | 255.255.248.0 | 0.0.7.255 | 2 048 | 2 046 | 8 (oct. 3) | — |
| /22 | 255.255.252.0 | 0.0.3.255 | 1 024 | 1 022 | 4 (oct. 3) | — |
| /23 | 255.255.254.0 | 0.0.1.255 | 512 | 510 | 2 (oct. 3) | — |
| /24 | 255.255.255.0 | 0.0.0.255 | 256 | 254 | 1 (oct. 3) | 0000 0000 |
| /25 | 255.255.255.128 | 0.0.0.127 | 128 | 126 | 128 | 1000 0000 |
| /26 | 255.255.255.192 | 0.0.0.63 | 64 | 62 | 64 | 1100 0000 |
| /27 | 255.255.255.224 | 0.0.0.31 | 32 | 30 | 32 | 1110 0000 |
| /28 | 255.255.255.240 | 0.0.0.15 | 16 | 14 | 16 | 1111 0000 |
| /29 | 255.255.255.248 | 0.0.0.7 | 8 | 6 | 8 | 1111 1000 |
| /30 | 255.255.255.252 | 0.0.0.3 | 4 | 2 | 4 | 1111 1100 |
| /31 | 255.255.255.254 | 0.0.0.1 | 2 | 2 (RFC 3021) | 2 | 1111 1110 |
| /32 | 255.255.255.255 | 0.0.0.0 | 1 | 1 | 1 | 1111 1111 |

**Poids binaires d'un octet** : `128 64 32 16 8 4 2 1` — **BLOC = 256 − masque**.

### Conversion décimal ↔ binaire (octets fréquents)

| Déc | Bin | Déc | Bin | Déc | Bin |
|---|---|---|---|---|---|
| 0 | 0000 0000 | 128 | 1000 0000 | 240 | 1111 0000 |
| 1 | 0000 0001 | 192 | 1100 0000 | 248 | 1111 1000 |
| 10 | 0000 1010 | 200 | 1100 1000 | 252 | 1111 1100 |
| 64 | 0100 0000 | 224 | 1110 0000 | 254 | 1111 1110 |
| 100 | 0110 0100 | 226 | 1110 0010 | 255 | 1111 1111 |

---

## 2. Numéros de protocole IP (champ `Protocol`)

| N° | Nom | N° | Nom | N° | Nom |
|---|---|---|---|---|---|
| 1 | ICMP | 41 | IPv6 (6in4) | 58 | ICMPv6 |
| 2 | IGMP | 47 | GRE | 89 | OSPF |
| 4 | IP-in-IP | 50 | ESP | 112 | VRRP |
| 6 | TCP | 51 | AH | 132 | SCTP |
| 17 | UDP | | | −1 | « tous » (security group AWS) |

## 3. ICMP / ICMPv6

| ICMPv4 | Code | Signification |
|---|---|---|
| 0 | 0 | Echo Reply |
| 3 | 0 / 1 / 2 / 3 | net / host / protocol / **port** unreachable |
| 3 | **4** | **Fragmentation needed and DF set** → PMTUD |
| 3 | 13 | Communication administratively prohibited (REJECT) |
| 5 | 0 / 1 | Redirect (réseau / hôte) |
| 8 | 0 | Echo Request |
| 11 | **0** | **TTL exceeded in transit** → traceroute |
| 11 | 1 | Fragment reassembly time exceeded |
| 12 | 0 | Parameter problem |

| ICMPv6 | Signification | ICMPv6 | Signification |
|---|---|---|---|
| 1 | Destination Unreachable | 133 | Router Solicitation |
| **2** | **Packet Too Big** (PMTUD) | 134 | Router Advertisement |
| 3 | Time Exceeded | 135 | Neighbor Solicitation (≈ ARP req) |
| 4 | Parameter Problem | 136 | Neighbor Advertisement (≈ ARP rep) |
| 128 / 129 | Echo Request / Reply | 137 | Redirect |

## 4. Plages réservées

| IPv4 | Rôle | IPv6 | Rôle |
|---|---|---|---|
| 0.0.0.0/8 | « cet hôte » | ::/128 | non spécifiée |
| 10.0.0.0/8 | privée RFC 1918 | ::1/128 | loopback |
| 100.64.0.0/10 | CGNAT RFC 6598 | 64:ff9b::/96 | NAT64 |
| 127.0.0.0/8 | loopback | 2000::/3 | global unicast |
| 169.254.0.0/16 | APIPA link-local | 2001:db8::/32 | documentation |
| 172.16.0.0/12 | privée (→ 172.31.255.255) | fc00::/7 (fd00::/8) | ULA |
| 192.0.2.0/24 | documentation TEST-NET-1 | fe80::/10 | link-local |
| 192.168.0.0/16 | privée RFC 1918 | ff00::/8 | multicast |
| 198.51.100.0/24 · 203.0.113.0/24 | documentation | ff02::1 / ff02::2 | tous nœuds / tous routeurs |
| 224.0.0.0/4 | multicast | ff02::1:ffXX:XXXX | solicited-node |
| 240.0.0.0/4 | réservé | | |
| 255.255.255.255 | broadcast limité | | |

---

## 5. Commandes — adressage et routes (Linux, iproute2)

| Commande | Effet |
|---|---|
| `ip -br -c addr show` | toutes les adresses, format bref et coloré |
| `ip addr show dev eth0` | adresses d'une interface |
| `ip -4 addr` / `ip -6 addr` | filtrer par famille |
| `ip addr add 10.0.0.5/24 dev eth0` | ajouter une adresse |
| `ip addr del 10.0.0.5/24 dev eth0` | retirer |
| `ip route` / `ip -6 route` | table de routage principale |
| `ip route get 8.8.8.8` | **quelle route ET quelle IP source** seraient utilisées |
| `ip route add 10.9.0.0/16 via 10.0.0.1 dev eth0` | route statique |
| `ip route add default via 10.0.0.1` | route par défaut |
| `ip route show table all` | toutes les tables (policy routing) |
| `ip rule show` | règles de sélection de table |
| `ip neigh show` | table ARP / NDP (voisins) |
| `ip -s link show eth0` | compteurs d'interface (erreurs, drops) |
| `ip link set eth0 mtu 1450` | changer le MTU |
| `hostname -I` | toutes les IP de la machine, une ligne |

Anciennes commandes (`net-tools`) qu'on croise encore : `ifconfig`, `route -n`, `arp -an`, `netstat -rn`.

## 6. Commandes — diagnostic

| Commande | Effet |
|---|---|
| `ping -c 4 10.0.0.5` | 4 échos |
| `ping -M do -s 1472 cible` | **test PMTU** : DF activé, 1472+28 = 1500 |
| `ping -I eth0 cible` | forcer l'interface source |
| `ping -i 0.2 -f cible` | intervalle 0,2 s / flood (root) |
| `ping6 fe80::1%eth0` | link-local : **le `%interface` est obligatoire** |
| `traceroute -n cible` | UDP 33434+, sans résolution DNS |
| `traceroute -I cible` | mode ICMP Echo |
| `traceroute -T -p 443 cible` | **TCP SYN** — passe les pare-feux |
| `traceroute -6 cible` | IPv6 |
| `tracepath cible` | traceroute + **découverte du PMTU**, sans root |
| `mtr -rwbzc 100 cible` | traceroute continu + pertes par saut, rapport de 100 cycles |
| `arping -I eth0 10.0.0.1` | tester un voisin en L2 (détecte les doublons d'IP) |
| `ip neigh flush all` | vider le cache ARP/NDP |
| `ss -tulpn` | sockets en écoute (TCP/UDP, PID) |
| `ss -tn state established` | connexions établies |
| `nc -zv cible 5432` | **le port répond-il ?** (à préférer au ping) |
| `curl -v --resolve h:443:1.2.3.4 https://h/` | forcer l'IP cible d'un test HTTPS |
| `dig +short A nom` / `dig +short AAAA nom` | résolution IPv4 / IPv6 |
| `getent hosts nom` | résolution via la stack système (nsswitch) |
| `tcpdump -ni eth0 icmp` | voir les ICMP en direct |
| `tcpdump -ni eth0 'net 10.42.0.0/16'` | filtrer par préfixe |
| `tcpdump -ni any -c 5 -vv 'ip[6] & 0x40 != 0'` | paquets avec **DF** positionné |
| `tcpdump -ni eth0 'icmp[icmptype]==3 and icmp[icmpcode]==4'` | **capter les « frag needed »** |
| `nmap -sn 10.0.5.0/24` | balayage d'hôtes actifs d'un subnet |

## 7. Commandes — calcul de subnet

```bash
ipcalc 192.168.37.201/26          # réseau, broadcast, plage, écriture binaire
sipcalc 10.10.0.0/22 -s 24        # découpe le /22 en /24
sipcalc -a 2001:db8::1            # toutes les formes d'une adresse IPv6
netmask -c 192.168.8.0:192.168.11.255   # plage → préfixes CIDR
whois -h whois.cymru.com " -v 8.8.8.8"  # à quel AS / préfixe appartient une IP
```

**Python — le plus fiable, toujours disponible** :

```python
import ipaddress as ip

n = ip.ip_network("192.168.37.192/26")
n.network_address          # 192.168.37.192
n.broadcast_address        # 192.168.37.255
n.netmask                  # 255.255.255.192
n.num_addresses            # 64
list(n.hosts())[0], list(n.hosts())[-1]   # .193 , .254

ip.ip_interface("192.168.37.201/26").network      # 192.168.37.192/26
ip.ip_address("10.4.130.9") in ip.ip_network("10.4.128.0/23")   # False

list(ip.ip_network("10.20.4.0/22").subnets(new_prefix=24))      # les 4 /24
list(ip.collapse_addresses([ip.ip_network(f"192.168.{i}.0/24")
                            for i in (8, 9, 10, 11)]))          # → 192.168.8.0/22

a, b = ip.ip_network("10.0.0.0/16"), ip.ip_network("10.0.5.0/24")
a.overlaps(b)              # True → peering impossible

ip.ip_address("2001:db8::1").exploded    # forme longue
ip.ip_address("2001:0db8:0000::1").compressed
```

## 8. MTU, MSS, encapsulations

| Contexte | MTU | MSS TCP (IPv4) |
|---|---|---|
| Ethernet standard | 1500 | 1460 |
| Jumbo frames (AWS intra-VPC) | 9001 | 8961 |
| PPPoE (ADSL) | 1492 | 1452 |
| **VXLAN** (+50 o) | **1450** | 1410 |
| GENEVE (~50 o) | ~1450 | ~1410 |
| GRE (+24 o) | 1476 | 1436 |
| IP-in-IP (+20 o) | 1480 | 1440 |
| **WireGuard** (+60 o IPv4 / +80 o IPv6) | 1440 · **1420** (défaut `wg-quick`) | 1400 · 1380 |
| IPsec ESP tunnel | ~1440 | ~1400 |
| **Minimum garanti IPv6** | **1280** | 1220 |

`MSS = MTU − 40` (IPv4 : 20 IP + 20 TCP) · `MSS = MTU − 60` (IPv6 : 40 IPv6 + 20 TCP).

```bash
# MSS clamping (routeur / nœud NAT)
iptables -t mangle -A FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu
# cache PMTU du noyau
ip route get 8.8.8.8            # affiche « mtu ... » s'il en a appris un
ip route flush cache
```

## 9. sysctl utiles

| Paramètre | Défaut | Effet |
|---|---|---|
| `net.ipv4.ip_forward` | 0 | routage IPv4 (à 1 sur un nœud K8s / NAT) |
| `net.ipv6.conf.all.forwarding` | 0 | routage IPv6 |
| `net.ipv4.ip_default_ttl` | 64 | TTL initial |
| `net.ipv4.ip_local_port_range` | 32768 60999 | ports éphémères |
| `net.ipv4.icmp_echo_ignore_all` | 0 | 1 = ne plus répondre au ping |
| `net.ipv4.conf.all.rp_filter` | selon distro | anti-spoofing par route inverse (0 off, 1 strict, 2 lâche) |
| `net.ipv6.conf.eth0.accept_ra` | 1 | accepter les RA (0 si l'interface route) |
| `net.ipv6.conf.all.use_tempaddr` | 0/2 | adresses temporaires RFC 4941 |
| `net.ipv4.tcp_mtu_probing` | 0 | 1 = contourne les trous noirs de PMTU |

## 10. Cloud & Kubernetes

| Élément | Valeur |
|---|---|
| CIDR de VPC AWS | /16 à /28 · **CIDR de subnet immuable** |
| IP réservées par subnet | **AWS 5** (.0, .1, .2, .3, dernière) · Azure 5 · GCP 4 |
| /28 AWS | **11** IP utilisables (et non 14) |
| Metadata instance | `169.254.169.254` (IMDSv2 : token via `PUT`) |
| Pod CIDR K8s par nœud | `--node-cidr-mask-size`, défaut **/24** |
| Nœuds max | 2^(taille podCIDR − taille cluster CIDR) |
| `maxPods` kubelet | **110** par défaut |
| Service CIDR kubeadm | `10.96.0.0/12` |
| Pod CIDR flannel | `10.244.0.0/16` |
| Bridge Docker par défaut | `172.17.0.0/16` |
| NodePort | 30000–32767 |
| AWS VPC CNI, pods/nœud | `(ENI max × (IP/ENI − 1)) + 2` ; prefix delegation → /28 par ENI |

```bash
aws ec2 describe-vpcs --query 'Vpcs[].[VpcId,CidrBlock]' --output table
aws ec2 describe-subnets --filters Name=vpc-id,Values=vpc-xxxx \
  --query 'Subnets[].[SubnetId,CidrBlock,AvailabilityZone,AvailableIpAddressCount]' --output table
aws ec2 describe-route-tables --query 'RouteTables[].Routes[]' --output table

kubectl get nodes -o custom-columns=NAME:.metadata.name,POD_CIDR:.spec.podCIDR
kubectl cluster-info dump | grep -m1 cluster-cidr
kubectl get pods -A -o wide --field-selector status.phase=Pending
kubectl describe pod <p> | grep -i -A3 'failed to assign\|FailedCreatePodSandBox'
```

## 11. Réflexes de diagnostic

| Symptôme | Piste |
|---|---|
| IP en `169.254.x.x` | DHCP injoignable (câble, VLAN, relais) |
| `Destination Host Unreachable` local | pas d'ARP/NDP : voisin absent ou mauvais subnet |
| `Network is unreachable` | **pas de route** — regarde `ip route get <cible>` |
| Timeout total | DROP par pare-feu / security group / route absente |
| `Connection refused` | ça arrive, **personne n'écoute** (problème applicatif) |
| Ping OK, gros transferts figés | **trou noir de PMTU** → `ping -M do -s ...` |
| Peering cloud refusé | **CIDR chevauchants** → `a.overlaps(b)` |
| Pod `ContainerCreating`, « failed to allocate IP » | subnet ou podCIDR **épuisé** |
| Nœud `NotReady`, `CIDRNotAvailable` | **cluster CIDR épuisé** |
| Latence stable ×2 après migration | changement de région/AZ — 5 µs/km |
