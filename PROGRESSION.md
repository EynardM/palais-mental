# PROGRESSION — le tableau de bord

> Mets a jour ce fichier **a la fin de chaque seance**. C'est le seul endroit ou tu
> regardes pour savoir quoi faire : la ligne du jour te donne les rappels, la roadmap
> te donne les modules.


## Niveaux

`N0` pas vu - `N1` lu - `N2` restitue de memoire - `N3` explique 3 min sans notes - `N4` applique


**Objectif 29/09 : tous les 🔴 en N3, tous les 🟠 en N2.**


---

## Etat des modules


### Reseau

| ID | Module | Prio | Prevu | Niveau | Notes |
|---|---|---|---|---|---|
| `R01` | Modele en couches : OSI, TCP/IP, encapsulation | 🔴 | 09/09 | `N0` | |
| `R02` | Couche 2 : Ethernet, MAC, ARP, VLAN, STP | 🔴 | 10/09 | `N0` | |
| `R03` | Couche 3 : IPv4, CIDR & subnetting, IPv6 | 🔴 | 10/09 | `N0` | |
| `R04` | Routage : table, statique, OSPF | 🔴 | 11/09 | `N0` | |
| `R06` | Couche 4 : TCP en profondeur, UDP, QUIC | 🔴 | 12/09 | `N0` | |
| `R07` | Services d'infra : DNS, DHCP, NAT, load balancing | 🔴 | 12/09 | `N0` | |
| `R08` | Couche 7 : HTTP/1.1-3, TLS/mTLS, gRPC, WebSocket | 🔴 | 12/09 | `N0` | |
| `R05` | BGP, AS, peering, MPLS | 🟠 | 13/09 | `N0` | |
| `R10` | Telemetrie reseau : tcpdump, SNMP, NetFlow/IPFIX, gNMI | 🔴 | 20/09 | `N0` | |
| `R11` | Reseau cloud & conteneurs : VPC, CNI, service mesh, eBPF | 🔴 | 26/09 | `N0` | |
| `R09` | Securite reseau : firewall, IPsec/VPN, zero-trust | 🟠 | bonus | `N0` | |

### DevOps

| ID | Module | Prio | Prevu | Niveau | Notes |
|---|---|---|---|---|---|
| `D01` | Linux : processus, fichiers, permissions, systemd | 🔴 | 11/09 | `N0` | |
| `D02` | Linux reseau & perf : ip, ss, nft, namespaces | 🔴 | 13/09 | `N0` | |
| `D03` | Bash & scripting robuste | 🔴 | 13/09 | `N0` | |
| `D04` | Git avance & workflows d'equipe | 🔴 | 15/09 | `N0` | |
| `D05` | Docker : images, couches, reseau, volumes | 🔴 | 16/09 | `N0` | |
| `D06` | Kubernetes : objets, scheduling, reseau, Helm | 🔴 | 18/09 | `N0` | |
| `D08` | CI/CD : pipelines, artefacts, strategies de deploiement | 🔴 | 21/09 | `N0` | |
| `D09` | Observabilite : Prometheus/PromQL, Grafana, OTel, SLO | 🔴 | 22/09 | `N0` | |
| `D07` | IaC : Terraform & Ansible | 🟠 | 27/09 | `N0` | |
| `D10` | Cloud, IAM, secrets, supply chain | 🟠 | 27/09 | `N0` | |

### Data

| ID | Module | Prio | Prevu | Niveau | Notes |
|---|---|---|---|---|---|
| `T01` | Modelisation relationnelle, normalisation, etoile | 🔴 | 14/09 | `N0` | |
| `T02` | SQL avance : fenetrage, CTE, plans, index | 🔴 | 14/09 | `N0` | |
| `T03` | OLTP vs OLAP, stockage colonne, Parquet/Avro/ORC | 🔴 | 16/09 | `N0` | |
| `T04` | Warehouse, Lake, Lakehouse : Delta, Iceberg, Hudi | 🔴 | 17/09 | `N0` | |
| `T05` | Systemes distribues : CAP, consensus, partitionnement | 🔴 | 18/09 | `N0` | |
| `T06` | Spark : execution, shuffle, partitionnement, tuning | 🔴 | 19/09 | `N0` | |
| `T07` | Kafka : topics, partitions, offsets, semantiques | 🔴 | 19/09 | `N0` | |
| `T09` | Orchestration : Airflow, dbt, idempotence, backfill | 🔴 | 20/09 | `N0` | |
| `T10` | NoSQL & series temporelles : Cassandra, Redis, Influx | 🔴 | 20/09 | `N0` | |
| `T08` | Streaming : Flink, watermarks, fenetres, etat | 🟠 | 26/09 | `N0` | |
| `T11` | Qualite, gouvernance, lignage, RGPD | 🟠 | 27/09 | `N0` | |
| `T12` | Architectures : Lambda/Kappa, Data Mesh, cout | 🟠 | 27/09 | `N0` | |

### IA

| ID | Module | Prio | Prevu | Niveau | Notes |
|---|---|---|---|---|---|
| `A01` | ML fondamental : biais-variance, validation, metriques | 🔴 | 21/09 | `N0` | |
| `A02` | Modeles classiques & ensembles : arbres, boosting | 🔴 | 22/09 | `N0` | |
| `A04` | Transformers & LLM : attention, tokenisation, fine-tuning | 🔴 | 23/09 | `N0` | |
| `A05` | RAG, embeddings, bases vectorielles | 🔴 | 24/09 | `N0` | |
| `A06` | Series temporelles & detection d'anomalies | 🔴 | 25/09 | `N0` | |
| `A07` | MLOps : feature store, registry, drift, monitoring | 🔴 | 26/09 | `N0` | |
| `A08` | IA appliquee au reseau (AIOps) | 🔴 | 26/09 | `N0` | |
| `A03` | Deep learning : MLP, backprop, CNN, RNN/LSTM | 🟠 | bonus | `N0` | |

### Langages

| ID | Module | Prio | Prevu | Niveau | Notes |
|---|---|---|---|---|---|
| `L01` | Python pour data engineering | 🔴 | 09/09 | `N0` | |
| `L03` | SQL intensif : 40 exercices corriges | 🔴 | 17/09 | `N0` | |
| `L02` | Python avance : asyncio, concurrence, polars | 🟠 | bonus | `N0` | |
| `L04` | Go : bases orientees reseau & infra | 🟠 | bonus | `N0` | |
| `L05` | YAML / HCL / Jinja : configuration as code | 🟠 | bonus | `N0` | |
| `L06` | Scala / Java : codebase Spark | 🟢 | bonus | `N0` | |

---

## Calendrier de rappel espace

Chaque module vu au jour J revient a **J+1, J+3, J+7, J+14**.
Un rappel = 2-5 min : reciter la fiche de memoire, puis verifier.
Coche ✅ si c'est venu tout seul, ⚠️ si ca a coince (un ⚠️ remet le module a J+1).

| Date | Rappels du jour | Fait |
|---|---|---|
| **Jeu 10/09** | `R01(J+1)` - `L01(J+1)` | |
| **Ven 11/09** | `R02(J+1)` - `R03(J+1)` | |
| **Sam 12/09** | `R01(J+3)` - `L01(J+3)` - `R04(J+1)` - `D01(J+1)` | |
| **Dim 13/09** | `R02(J+3)` - `R03(J+3)` - `R06(J+1)` - `R07(J+1)` - `R08(J+1)` | |
| **Lun 14/09** | `R04(J+3)` - `D01(J+3)` - `D02(J+1)` - `D03(J+1)` - `R05(J+1)` | |
| **Mar 15/09** | `R06(J+3)` - `R07(J+3)` - `R08(J+3)` - `T01(J+1)` - `T02(J+1)` | |
| **Mer 16/09** | `R01(J+7)` - `L01(J+7)` - `D02(J+3)` - `D03(J+3)` - `R05(J+3)` - `D04(J+1)` | |
| **Jeu 17/09** | `R02(J+7)` - `R03(J+7)` - `T01(J+3)` - `T02(J+3)` - `T03(J+1)` - `D05(J+1)` | |
| **Ven 18/09** | `R04(J+7)` - `D01(J+7)` - `D04(J+3)` - `T04(J+1)` - `L03(J+1)` | |
| **Sam 19/09** | `R06(J+7)` - `R07(J+7)` - `R08(J+7)` - `T03(J+3)` - `D05(J+3)` - `T05(J+1)` - `D06(J+1)` | |
| **Dim 20/09** | `D02(J+7)` - `D03(J+7)` - `R05(J+7)` - `T04(J+3)` - `L03(J+3)` - `T06(J+1)` - `T07(J+1)` | |
| **Lun 21/09** | `T01(J+7)` - `T02(J+7)` - `T05(J+3)` - `D06(J+3)` - `T09(J+1)` - `T10(J+1)` - `R10(J+1)` | |
| **Mar 22/09** | `D04(J+7)` - `T06(J+3)` - `T07(J+3)` - `A01(J+1)` - `D08(J+1)` | |
| **Mer 23/09** | `R01(J+14)` - `L01(J+14)` - `T03(J+7)` - `D05(J+7)` - `T09(J+3)` - `T10(J+3)` - `R10(J+3)` - `A02(J+1)` - `D09(J+1)` | |
| **Jeu 24/09** | `R02(J+14)` - `R03(J+14)` - `T04(J+7)` - `L03(J+7)` - `A01(J+3)` - `D08(J+3)` - `A04(J+1)` | |
| **Ven 25/09** | `R04(J+14)` - `D01(J+14)` - `T05(J+7)` - `D06(J+7)` - `A02(J+3)` - `D09(J+3)` - `A05(J+1)` | |
| **Sam 26/09** | `R06(J+14)` - `R07(J+14)` - `R08(J+14)` - `T06(J+7)` - `T07(J+7)` - `A04(J+3)` - `A06(J+1)` | |
| **Dim 27/09** | `D02(J+14)` - `D03(J+14)` - `R05(J+14)` - `T09(J+7)` - `T10(J+7)` - `R10(J+7)` - `A05(J+3)` - `A07(J+1)` - `A08(J+1)` - `R11(J+1)` - `T08(J+1)` | |
| **Lun 28/09** | `T01(J+14)` - `T02(J+14)` - `A01(J+7)` - `D08(J+7)` - `A06(J+3)` - `T11(J+1)` - `T12(J+1)` - `D07(J+1)` - `D10(J+1)` | |
| **Mar 29/09** | `D04(J+14)` - `A02(J+7)` - `D09(J+7)` - `A07(J+3)` - `A08(J+3)` - `R11(J+3)` - `T08(J+3)` | |

---

## Journal de bord

Trois lignes par jour dans `journal/AAAA-MM-JJ.md` :
ce qui est entre tout seul / ce qui resiste / une question ouverte.

Relis la colonne "ce qui resiste" chaque dimanche : elle revele les vrais points
faibles, ceux que le ressenti a chaud masque.

