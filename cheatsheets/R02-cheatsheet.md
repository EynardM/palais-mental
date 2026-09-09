# R02 — CHEATSHEET : Couche 2 (Ethernet, MAC, ARP, VLAN, STP, LACP, MTU)

Référence opérationnelle. À garder ouverte pendant qu'on travaille.

---

## 1. Tailles et offsets — trame Ethernet II

| Champ | Offset (o) | Taille | Note |
|---|---|---|---|
| Préambule | — | 7 o | hors trame, `AA`×7 |
| SFD | — | 1 o | `AB` |
| MAC destination | 0 | 6 o | |
| MAC source | 6 | 6 o | |
| *(Tag 802.1Q)* | *12* | *4 o* | *`8100` + TCI, si présent* |
| EtherType | 12 (ou 16) | 2 o | |
| Payload | 14 (ou 18) | 46 à 1500 o | bourré si < 46 |
| FCS | fin | 4 o | CRC-32 |
| IFG | après | 12 o | 96 temps-bit |

| Grandeur | Valeur |
|---|---|
| Trame min / max (sans tag) | 64 / 1518 o |
| Trame min / max (avec tag) | 68 / 1522 o |
| Overhead L2 / overhead fil | 18 o / 38 o |
| pps max à 1 Gbit/s — 64 o / 1518 o / 9018 o | 1 488 095 / 81 274 / 13 830 |
| pps max à 10 Gbit/s — 64 o | 14 880 952 |
| Rendement 1500 o / 9000 o | 97,5 % / 99,6 % |

## 2. EtherType

| Hexa | Protocole | | Hexa | Protocole |
|---|---|---|---|---|
| `0x0800` | IPv4 | | `0x8809` | Slow protocols (LACP) |
| `0x0806` | ARP | | `0x8847` / `0x8848` | MPLS unicast / multicast |
| `0x8035` | RARP | | `0x88A8` | QinQ / 802.1ad |
| `0x86DD` | IPv6 | | `0x88CC` | LLDP |
| `0x8100` | VLAN 802.1Q | | `0x8863` / `0x8864` | PPPoE discovery / session |

Règle : `≤ 0x05DC (1500)` = longueur (802.3) · `≥ 0x0600 (1536)` = EtherType (Ethernet II).

## 3. Adresses MAC

| Motif | Sens |
|---|---|
| bit 0 du 1er octet (I/G) | 0 = unicast · 1 = multicast |
| bit 1 du 1er octet (U/L) | 0 = universelle (OUI IEEE) · 1 = locally administered |
| 2e chiffre hexa `0 4 8 C` | unicast universelle |
| 2e chiffre hexa `2 6 A E` | unicast locale (VM, conteneur, spoof) |
| 2e chiffre hexa `1 5 9 D` / `3 7 B F` | multicast universelle / locale |

| Adresse | Usage | | OUI | Constructeur |
|---|---|---|---|---|
| `ff:ff:ff:ff:ff:ff` | broadcast | | `00:50:56` | VMware |
| `01:80:c2:00:00:00` | BPDU STP/RSTP | | `52:54:00` | QEMU / KVM |
| `01:80:c2:00:00:02` | LACP | | `02:42:xx` | Docker |
| `01:80:c2:00:00:0e` | LLDP | | `00:0c:29` | VMware (ESXi) |
| `01:00:0c:cc:cc:cc` | CDP / VTP (Cisco) | | `00:15:5d` | Hyper-V |
| `01:00:5e:xx:xx:xx` | multicast IPv4 (23 bits bas) | | | |
| `33:33:xx:xx:xx:xx` | multicast IPv6 (32 bits bas) | | | |

## 4. ARP — en-tête 28 octets

| Offset | Champ | Taille | Valeur usuelle |
|---|---|---|---|
| 0 | Hardware type | 2 | `0x0001` Ethernet |
| 2 | Protocol type | 2 | `0x0800` IPv4 |
| 4 / 5 | HLEN / PLEN | 1 / 1 | `06` / `04` |
| 6 | Opération | 2 | `0001` request · `0002` reply |
| 8 | SHA (MAC émetteur) | 6 | |
| 14 | SPA (IP émetteur) | 4 | |
| 18 | THA (MAC cible) | 6 | `00:…:00` dans une requête |
| 24 | TPA (IP cible) | 4 | |

Gratuitous ARP : **SPA == TPA**. Trame ARP totale = 42 o → bourrée à 64 o.

## 5. Valeurs par défaut à connaître

| Paramètre | Défaut | Où |
|---|---|---|
| Aging time table CAM | **300 s** | switch |
| Cache ARP Cisco | **14 400 s (4 h)** | routeur/switch Cisco |
| `net.ipv4.neigh.default.base_reachable_time_ms` | **30000** | Linux |
| `…/gc_stale_time` | **60** | Linux |
| `…/gc_thresh1` / `gc_thresh2` / `gc_thresh3` | **128 / 512 / 1024** | Linux |
| `…/mcast_solicit` / `ucast_solicit` | **3 / 3** | Linux |
| Priorité de bridge STP | **32768** (pas de 4096) | switch |
| Hello / Forward Delay / Max Age | **2 s / 15 s / 20 s** | STP |
| Convergence 802.1D / 802.1w | **30-50 s / < 1 s** | STP |
| Période LACPDU slow / fast | **30 s / 1 s** (timeout ×3) | LACP |
| Liens actifs max par LAG (Cisco) | **8** | LACP |
| VLAN natif par défaut | **1** | trunk |
| MTU Ethernet / jumbo | **1500 / 9000** | partout |

## 6. Coûts STP (root path cost)

| Débit | Short (802.1D, défaut Cisco) | Long (802.1t) |
|---|---|---|
| 10 Mbit/s | 100 | 2 000 000 |
| 100 Mbit/s | **19** | 200 000 |
| 1 Gbit/s | **4** | 20 000 |
| 10 Gbit/s | **2** | 2 000 |
| 100 Gbit/s | 1 | 200 |

Départage : **coût cumulé → Bridge ID voisin → Port ID voisin → Port ID local.**
États 802.1D : Disabled → Blocking → Listening (15 s) → Learning (15 s) → Forwarding.
États RSTP : Discarding / Learning / Forwarding. Rôles : Root / Designated / Alternate / Backup.

## 7. MTU, MSS et encapsulations

| Encapsulation | Overhead | MTU interne sur underlay 1500 |
|---|---|---|
| 802.1Q | 4 o | 1500 |
| QinQ | 8 o | 1500 |
| **VXLAN** | **50 o** | **1450** |
| Geneve | 50 o + options | ≤ 1450 |
| GRE / IPIP | 24 o / 20 o | 1476 / 1480 |
| WireGuard | 60 o | 1420 |
| IPsec ESP tunnel | 54-73 o | ~1400 |

| Contexte | MTU | | Formule | Résultat |
|---|---|---|---|---|
| Ethernet, Internet | 1500 | | MSS IPv4 | MTU − 40 |
| AWS VPC (ENA) | **9001** | | MSS IPv6 | MTU − 60 |
| AWS Transit Gateway / IGW | 8500 / 1500 | | `ping -M do -s` | MTU − 28 |
| GCP VPC (défaut) | **1460** | | MTU 1500 | MSS 1460, ping 1472 |
| Azure VM | 1500 | | MTU 9000 | MSS 8960, ping 8972 |
| Pod K8s VXLAN / IPIP | 1450 / 1480 | | MTU 1450 | MSS 1410, ping 1422 |

## 8. Commandes Linux

### Interfaces

| Commande | Ce qu'elle donne |
|---|---|
| `ip link show` | état, MTU, MAC de toutes les interfaces |
| `ip -s link show eth0` | statistiques : paquets, erreurs, drops |
| `ip -d link show eth0` | détails du type : vlan, bond, bridge, vxlan |
| `ip link set dev eth0 mtu 9000` | changer le MTU |
| `ip link set dev eth0 address 02:11:22:33:44:55` | changer la MAC |
| `ip link set eth0 promisc on` | mode promiscuous |
| `ethtool eth0` | débit, duplex, auto-négociation |
| `ethtool -S eth0` | compteurs matériels (crc, pause, discards) |
| `ethtool -i eth0` | driver et version de firmware |
| `ethtool -k eth0` | offloads : GRO, GSO, TSO, LRO |
| `ethtool -P eth0` | MAC permanente gravée dans la carte |

### ARP / voisinage

| Commande | Effet |
|---|---|
| `ip neigh show` | table de voisinage complète |
| `ip neigh show dev eth0 nud reachable` | seulement les entrées confirmées |
| `ip neigh flush all` | vider la table (diagnostic) |
| `ip neigh add 10.0.0.1 lladdr aa:bb:cc:dd:ee:ff dev eth0 nud permanent` | entrée statique |
| `ip neigh del 10.0.0.1 dev eth0` | supprimer une entrée |
| `arping -I eth0 -c 3 10.0.0.1` | joignabilité L2 pure (sans IP routing) |
| `arping -U -I eth0 -c 3 10.0.0.50` | **gratuitous ARP** (annonce) |
| `arping -D -I eth0 -c 2 10.0.0.50` | détection de doublon d'adresse |
| `sysctl -w net.ipv4.neigh.default.gc_thresh3=16384` | agrandir la table (K8s) |

### VLAN

| Commande | Effet |
|---|---|
| `ip link add link eth0 name eth0.100 type vlan id 100` | sous-interface taguée VLAN 100 |
| `ip link set eth0.100 up` | activer |
| `ip link del eth0.100` | supprimer |
| `ip -d link show eth0.100` | vérifier `vlan protocol 802.1Q id 100` |
| `cat /proc/net/vlan/config` | toutes les sous-interfaces VLAN |
| `bridge vlan show` | VLAN par port sur un bridge Linux |

### Bridge / table CAM

| Commande | Effet |
|---|---|
| `bridge link show` | ports du bridge et leur état STP |
| `bridge fdb show` | **la table CAM du bridge Linux** |
| `bridge fdb show br br0` | filtrée sur un bridge |
| `ip link add br0 type bridge` / `ip link set eth0 master br0` | créer / rattacher |

### Bonding / LACP

| Commande | Effet |
|---|---|
| `cat /proc/net/bonding/bond0` | mode, hash, liens actifs, partenaire LACP |
| `ip -d link show bond0` | détails du bond |
| `cat /sys/class/net/bond0/bonding/xmit_hash_policy` | politique de hachage |
| `cat /sys/class/net/bond0/bonding/mode` | mode courant |

Modes : `0` balance-rr · `1` active-backup · `2` balance-xor · `3` broadcast · **`4` 802.3ad (LACP)** ·
`5` balance-tlb · `6` balance-alb.
Hash : `layer2` · `layer2+3` · **`layer3+4`** · `encap2+3` · `encap3+4`.

### MTU / PMTU

| Commande | Effet |
|---|---|
| `ping -M do -s 1472 <ip>` | teste un MTU de 1500 |
| `ping -M do -s 8972 <ip>` | teste un MTU de 9000 |
| `ping -M do -s 1422 <ip>` | teste un MTU de 1450 (pod VXLAN) |
| `tracepath <ip>` | MTU découvert saut par saut |
| `ip route get <ip>` | MTU retenu pour cette destination |
| `ip route add 10.0.0.0/8 dev eth0 mtu 9000` | MTU par route |
| `iptables -t mangle -A FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu` | MSS clamping |

### Capture

| Commande | Effet |
|---|---|
| `tcpdump -e -n -i eth0` | **`-e` = affiche l'en-tête Ethernet** (MAC, tag) |
| `tcpdump -e -n -i eth0 arp` | trafic ARP |
| `tcpdump -e -n -i eth0 vlan` / `vlan 100` | trafic tagué / VLAN 100 |
| `tcpdump -e -n -i eth0 'ether broadcast'` | tout le broadcast |
| `tcpdump -e -n -i eth0 'ether host aa:bb:cc:dd:ee:ff'` | une MAC précise |
| `tcpdump -e -n -i eth0 'ether proto 0x88cc'` | LLDP |
| `tcpdump -e -n -i eth0 'stp'` | BPDU |
| `lldpcli show neighbors` | à quel port de quel switch suis-je branché ? |

## 9. Commandes Cisco IOS (lecture de sortie)

| Commande | Ce qu'on y lit |
|---|---|
| `show mac address-table` | VLAN, MAC, type, port |
| `show mac address-table aging-time` | 300 par défaut |
| `show vlan brief` | VLAN existants et ports access |
| `show interfaces trunk` | trunks, VLAN autorisés, **VLAN natif** |
| `show interfaces status` | up/down, duplex, vitesse, VLAN |
| `show spanning-tree` | root bridge, coûts, rôles, états |
| `show spanning-tree vlan 10` | l'arbre d'un VLAN (PVST+) |
| `show spanning-tree summary` | nombre de ports bloqués par VLAN |
| `show etherchannel summary` | état du LAG (`P` = bundled, `s` = suspended) |
| `show cdp neighbors` / `show lldp neighbors` | voisins et ports |
| `show interfaces gi0/1 counters errors` | CRC, runts, giants, collisions |

Configuration type :

```
! port access
interface gi0/1
 switchport mode access
 switchport access vlan 10
 spanning-tree portfast
 spanning-tree bpduguard enable
 switchport port-security maximum 2
 switchport port-security violation restrict
! trunk
interface gi0/24
 switchport mode trunk
 switchport trunk native vlan 999
 switchport trunk allowed vlan 10,20,30
 switchport nonegotiate
! root bridge
spanning-tree vlan 10 priority 4096
```

## 10. Symptômes → cause probable

| Symptôme | Cause L2 la plus probable | Vérification |
|---|---|---|
| Ping OK, gros transfert bloqué | MTU / trou noir PMTU | `ping -M do -s 1472` |
| `FetchFailedException` Spark sur grosses partitions | MTU overlay ≠ underlay | idem, entre exécuteurs |
| Débit effondré, `rx_crc_errors` en hausse | câble / SFP / fibre sale | `ethtool -S eth0 \| grep crc` |
| Compteur de collisions non nul | duplex mismatch | `ethtool eth0` |
| `neighbor table overflow` dans `dmesg` | `gc_thresh3` trop bas | `sysctl net.ipv4.neigh.default.gc_thresh3` |
| Tout le VLAN reçoit un flux qui ne le concerne pas | unknown unicast flooding (CAM 300 s vs ARP 4 h) | `show mac address-table` |
| Bascule HA de 3 minutes au lieu de 2 s | pas de gratuitous ARP | `tcpdump -e -i eth0 arp` |
| Réseau entier figé, CPU switch à 100 % | boucle L2 / tempête de broadcast | `show spanning-tree summary` |
| LAG à 4 liens plafonné à 1 lien | hash figé sur un flux TCP unique | `cat /proc/net/bonding/bond0` |
| Une MAC alterne entre deux ports | MAC flapping (boucle, VM clonée, spoofing) | logs du switch |

## 11. Conversion hexadécimale rapide

| Hex | Déc | Bin | | Hex | Déc | Bin |
|---|---|---|---|---|---|---|
| `0` | 0 | 0000 | | `8` | 8 | 1000 |
| `1` | 1 | 0001 | | `9` | 9 | 1001 |
| `2` | 2 | 0010 | | `A` | 10 | 1010 |
| `3` | 3 | 0011 | | `B` | 11 | 1011 |
| `4` | 4 | 0100 | | `C` | 12 | 1100 |
| `5` | 5 | 0101 | | `D` | 13 | 1101 |
| `6` | 6 | 0110 | | `E` | 14 | 1110 |
| `7` | 7 | 0111 | | `F` | 15 | 1111 |

Octet IP courant : `c0`=192 · `a8`=168 · `0a`=10 · `ac`=172 · `10`=16 · `ff`=255 · `7f`=127.
Décoder un TCI 802.1Q : `PCP = TCI >> 13` · `DEI = (TCI >> 12) & 1` · `VID = TCI & 0x0FFF`.
