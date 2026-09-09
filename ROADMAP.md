# ROADMAP — 21 jours, du 09/09 au 30/09

**Point de départ** : ingénieur info spé IA, 1 an de pilotage / intégration software (peu de code).
**Cible** : Data Engineer, forte composante **réseau**, composante **IA**.
**Contrainte** : 1-3h en semaine, 4-10h le week-end. Capacité totale estimée **39h (bas) à 105h (haut)**.

---

## Le dimensionnement

47 modules, hiérarchisés pour que la charge s'adapte à ce que tu peux réellement donner :

| Priorité | Nombre | Sens | Coût cumulé |
|---|---|---|---|
| 🔴 **Noyau** | 35 | Non négociable. C'est le socle du poste. | ~40-50h |
| 🟠 **Important** | 11 | À faire si le rythme tient. Te fait passer de "je suis" à "je contribue". | ~+15h |
| 🟢 **Bonus** | 1 | Confort. Uniquement si tout le reste est en N3. | ~+2h |

**Si tu n'as que 39h : tu fais les 35 🔴 et c'est un succès complet.**
Le 🟠 et le 🟢 sont là pour absorber tes bons jours, pas pour te culpabiliser les mauvais.

---

## Vue d'ensemble par sprint

| Sprint | Dates | Thème | Modules | Pourquoi cet ordre |
|---|---|---|---|---|
| **1** | mer 09 → dim 13 | **Socle réseau + Linux** | 12 | Le réseau est ton différenciateur et il structure tout le reste (cloud, K8s, systèmes distribués). Linux est l'outil avec lequel tu l'observeras. |
| **2** | lun 14 → dim 20 | **Data cœur + conteneurs** | 14 | Le métier. Posé sur un socle réseau déjà en place, le distribué devient évident au lieu d'être magique. |
| **3** | lun 21 → dim 27 | **IA, plateforme, avancé** | 14 | L'IA prend son sens une fois que tu sais d'où viennent les données et comment elles circulent. Se termine sur l'IA appliquée au réseau : ton poste exact. |
| **4** | lun 28 → mar 29 | **Consolidation** | 0 nouveau | Deux jours sans rien apprendre de neuf. Uniquement rappels, Feynman, simulation. C'est ce qui transforme du N2 en N3. |

---

## SPRINT 1 — SOCLE RÉSEAU + LINUX (mer 09 → dim 13)

> **Objectif de sprint** : suivre de bout en bout le trajet d'un paquet, de la carte réseau
> jusqu'à la réponse HTTP, et savoir l'observer avec les outils Linux.

| Jour | Si 1h | Si 3h | Si 6h+ (WE) |
|---|---|---|---|
| **Mer 09** J-21 | Setup + `R01` | + `L01` | — |
| **Jeu 10** J-20 | `R02` | + `R03` | — |
| **Ven 11** J-19 | `R03` ou `R04` | + `D01` | — |
| **Sam 12** J-18 | — | — | `R04` `R06` `R07` `D01` (+ `R08`) |
| **Dim 13** J-17 | — | — | `R08` `D02` `D03` (+ `R05`) + **Atelier 1** |

**Modules du sprint :**

| ID | Titre | Prio |
|---|---|---|
| `R01` | Le modèle en couches : OSI, TCP/IP, encapsulation | 🔴 |
| `R02` | Couche 2 : Ethernet, MAC, ARP, commutation, VLAN, STP | 🔴 |
| `R03` | Couche 3 : IPv4, CIDR & subnetting, IPv6 | 🔴 |
| `R04` | Routage : table de routage, statique, OSPF | 🔴 |
| `R05` | BGP, systèmes autonomes, peering, MPLS | 🟠 |
| `R06` | Couche 4 : TCP en profondeur, UDP, QUIC | 🔴 |
| `R07` | Services d'infra : DNS, DHCP, NAT, load balancing | 🔴 |
| `R08` | Couche 7 : HTTP/1.1→3, TLS/mTLS, gRPC, WebSocket | 🔴 |
| `D01` | Linux : processus, fichiers, permissions, systemd | 🔴 |
| `D02` | Linux réseau & perf : ip, ss, nft, namespaces, /proc | 🔴 |
| `D03` | Bash & scripting robuste | 🔴 |
| `L01` | Python pour data engineering : typage, structures, packaging, tests | 🔴 |

**Atelier 1 (dim 13)** — *Traverser la pile* : capturer un `curl https://...` au tcpdump et
identifier à la main chaque couche, du DNS au TLS jusqu'au GET. Le meilleur exercice
d'intégration réseau qui existe.

**✅ Validation du sprint** — tu dois savoir, sans notes :
- réciter les 7 couches et donner un protocole + un équipement par couche
- découper un `/22` en 4 sous-réseaux et donner les plages exactes
- raconter les 3 temps du handshake TCP puis ce que TLS ajoute par-dessus
- lire une sortie `ip route` et `ss -tulpn` et dire ce que fait la machine

---

## SPRINT 2 — DATA CŒUR + CONTENEURS (lun 14 → dim 20)

> **Objectif de sprint** : savoir concevoir un pipeline complet — ingestion, stockage,
> transformation, orchestration — et justifier chaque choix technique.

| Jour | Si 1h | Si 3h | Si 6h+ (WE) |
|---|---|---|---|
| **Lun 14** J-16 | `T01` | + `T02` | — |
| **Mar 15** J-15 | `T02` | + `D04` | — |
| **Mer 16** J-14 | `T03` | + `D05` | — |
| **Jeu 17** J-13 | `T04` | + `L03` | — |
| **Ven 18** J-12 | `T05` | + `D06` | — |
| **Sam 19** J-11 | — | — | `T06` `T07` `D06` `L03` (+ `D05`) |
| **Dim 20** J-10 | — | — | `T09` `T10` `R10` (+ `T08`) + **Atelier 2** |

**Modules du sprint :**

| ID | Titre | Prio |
|---|---|---|
| `T01` | Modélisation relationnelle, normalisation, étoile & flocon | 🔴 |
| `T02` | SQL avancé : fenêtrage, CTE, plans d'exécution, index | 🔴 |
| `T03` | OLTP vs OLAP, stockage colonne, Parquet / Avro / ORC | 🔴 |
| `T04` | Warehouse, Lake, Lakehouse : Delta, Iceberg, Hudi | 🔴 |
| `T05` | Systèmes distribués : CAP, consensus, partitionnement, réplication | 🔴 |
| `T06` | Spark : modèle d'exécution, shuffle, partitionnement, tuning | 🔴 |
| `T07` | Kafka : topics, partitions, offsets, sémantiques de livraison | 🔴 |
| `T09` | Orchestration : Airflow, dbt, idempotence, backfill | 🔴 |
| `T10` | NoSQL & séries temporelles : Cassandra, Redis, Mongo, Influx/Timescale | 🔴 |
| `R10` | Télémétrie réseau : tcpdump/Wireshark, SNMP, NetFlow/IPFIX, gNMI | 🔴 |
| `D04` | Git avancé & workflows d'équipe | 🔴 |
| `D05` | Docker : images, couches, réseau, volumes, compose | 🔴 |
| `D06` | Kubernetes : objets, scheduling, réseau, stockage, Helm | 🔴 |
| `L03` | SQL intensif : 40 exercices corrigés | 🔴 |

**Atelier 2 (dim 20)** — *Concevoir le pipeline de télémétrie réseau* : sur papier, de la
collecte NetFlow jusqu'aux dashboards. C'est très probablement la question d'entretien /
de première réunion de ton poste. `R10` est volontairement placé ici : c'est **la charnière
réseau × data**, le module qui fait le lien entre tes deux composantes.

**✅ Validation du sprint** — tu dois savoir, sans notes :
- écrire une requête à fenêtrage et expliquer son plan d'exécution
- dire pourquoi Parquet bat CSV sur de l'analytique, chiffres à l'appui
- expliquer un shuffle Spark et trois façons d'en réduire le coût
- expliquer comment Kafka garantit l'ordre, et à quelle échelle exactement
- dessiner de tête un pipeline batch + streaming complet

---

## SPRINT 3 — IA, PLATEFORME & AVANCÉ (lun 21 → dim 27)

> **Objectif de sprint** : relier la donnée au modèle, et arriver au module signature de ton
> poste — l'IA appliquée au réseau.

| Jour | Si 1h | Si 3h | Si 6h+ (WE) |
|---|---|---|---|
| **Lun 21** J-9 | `A01` | + `D08` | — |
| **Mar 22** J-8 | `A02` | + `D09` | — |
| **Mer 23** J-7 | `A04` | + `R11` | — |
| **Jeu 24** J-6 | `A05` | + `T08` | — |
| **Ven 25** J-5 | `A06` | + `D07` | — |
| **Sam 26** J-4 | — | — | `A07` `A08` `R11` `T08` (+ `R09`) |
| **Dim 27** J-3 | — | — | `T11` `T12` `D07` `D10` + **Atelier 3** |

**Modules du sprint :**

| ID | Titre | Prio |
|---|---|---|
| `A01` | ML fondamental : biais-variance, validation, métriques | 🔴 |
| `A02` | Modèles classiques & ensembles : arbres, gradient boosting, features | 🔴 |
| `A04` | Transformers & LLM : attention, tokenisation, fine-tuning | 🔴 |
| `A05` | RAG, embeddings, bases vectorielles | 🔴 |
| `A06` | Séries temporelles & détection d'anomalies | 🔴 |
| `A07` | MLOps : feature store, registry, drift, monitoring, CI/CD ML | 🔴 |
| `A08` | **IA appliquée au réseau (AIOps)** : trafic, anomalies, root cause | 🔴 |
| `R11` | Réseau cloud & conteneurs : VPC, SDN, CNI, service mesh, eBPF | 🔴 |
| `T08` | Streaming temps réel : Flink, watermarks, fenêtres, état | 🟠 |
| `T11` | Qualité, gouvernance, lignage, RGPD | 🟠 |
| `T12` | Architectures : Lambda / Kappa, Data Mesh, coût & performance | 🟠 |
| `D07` | Infrastructure as Code : Terraform & Ansible | 🟠 |
| `D08` | CI/CD : pipelines, artefacts, stratégies de déploiement | 🔴 |
| `D09` | Observabilité : Prometheus/PromQL, Grafana, logs, OpenTelemetry, SLO | 🔴 |
| `D10` | Cloud, IAM, secrets, sécurité de la chaîne d'approvisionnement | 🟠 |

**Atelier 3 (dim 27)** — *Détection d'anomalies sur trafic réseau* : de la feature
engineering sur des flux jusqu'au choix du modèle et à sa mise en production. La synthèse
des trois composantes de ton poste en un seul exercice.

**✅ Validation du sprint** — tu dois savoir, sans notes :
- choisir une métrique et la défendre sur un cas déséquilibré (99,9 % de trafic normal)
- expliquer l'attention en 3 minutes, sans équation
- proposer une architecture de détection d'anomalies sur du NetFlow temps réel
- écrire une requête PromQL et définir un SLO qui tient debout

---

## SPRINT 4 — CONSOLIDATION (lun 28 → mar 29)

> **Aucun module nouveau.** C'est délibéré et c'est le sprint le plus rentable des quatre.
> Apprendre jusqu'à la veille laisse 40 modules en N1-N2. Deux jours de consolidation
> en amènent l'essentiel en N3 — le seul niveau qui tienne en conversation.

**Lun 28 (J-2)**
1. Rappel intégral : les 47 fiches, en mode récitation, ~3 min chacune.
2. Marquer sans complaisance les ⚠️.
3. Reprise ciblée des ⚠️ uniquement.

**Mar 29 (J-1)**
1. Simulation d'entretien technique : 30 questions, à voix haute, chronométrées.
2. Parcours complet des palais mentaux.
3. Rédaction de `PREMIER-JOUR.md` : les 10 questions à poser à ton équipe le 30.
4. **Arrêt à 20h.** Une nuit courte coûte plus qu'un module de plus n'apporte.

---

## Modules hors planning (rattrapage / bonus)

À insérer les jours où tu déborde, ou après la prise de poste.

| ID | Titre | Prio |
|---|---|---|
| `R05` | BGP, AS, peering, MPLS | 🟠 |
| `R09` | Sécurité réseau : firewall, IPsec/VPN, zero-trust, IDS/IPS | 🟠 |
| `A03` | Deep learning : MLP, rétropropagation, CNN, RNN/LSTM | 🟠 |
| `L02` | Python avancé : asyncio, concurrence, pandas vs polars | 🟠 |
| `L04` | Go : les bases orientées réseau & infra | 🟠 |
| `L05` | YAML / HCL / Jinja : la configuration as code | 🟠 |
| `L06` | Scala / Java : survivre dans une codebase Spark | 🟢 |

---

## Le tableau de bord

L'avancement réel se suit dans **`PROGRESSION.md`** : niveau par module, table de rappel
espacé, et la ligne du jour qui te dit quoi faire sans avoir à y réfléchir.
