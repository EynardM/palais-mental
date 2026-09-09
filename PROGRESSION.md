# PROGRESSION — le tableau de bord

> Mets a jour ce fichier **a la fin de chaque seance**. C'est le seul endroit ou tu
> regardes pour savoir quoi faire : la ligne du jour te donne les rappels, la roadmap
> te donne les modules.


## Niveaux

`N0` pas vu · `N1` lu (Plongée faite) · `N2` restitué de mémoire · `N3` expliqué 3 min sans notes · `N4` appliqué

Un **Survol** seul (fiche lue avant le cours) ne fait pas passer à `N1` : il se note dans « Notes ».


**Objectif 29/09 : tous les 🔴 en N3, tous les 🟠 en N2.**


---

## Etat des modules


### Reseau

| ID | Module | Prio | Prévu | Vu le | Niveau | Notes |
|---|---|---|---|---|---|---|
| `R01` | Modele en couches : OSI, TCP/IP, encapsulation | 🔴 | 09/09 |  | `N0` | Survol 10/09 |
| `R02` | Couche 2 : Ethernet, MAC, ARP, VLAN, STP | 🔴 | 10/09 |  | `N0` | Survol 10/09 |
| `R03` | Couche 3 : IPv4, CIDR & subnetting, IPv6 | 🔴 | 10/09 |  | `N0` | |
| `R04` | Routage : table, statique, OSPF | 🔴 | 11/09 |  | `N0` | |
| `R06` | Couche 4 : TCP en profondeur, UDP, QUIC | 🔴 | 12/09 |  | `N0` | |
| `R07` | Services d'infra : DNS, DHCP, NAT, load balancing | 🔴 | 12/09 |  | `N0` | |
| `R08` | Couche 7 : HTTP/1.1-3, TLS/mTLS, gRPC, WebSocket | 🔴 | 12/09 |  | `N0` | |
| `R05` | BGP, AS, peering, MPLS | 🟠 | 13/09 |  | `N0` | |
| `R10` | Telemetrie reseau : tcpdump, SNMP, NetFlow/IPFIX, gNMI | 🔴 | 20/09 |  | `N0` | |
| `R11` | Reseau cloud & conteneurs : VPC, CNI, service mesh, eBPF | 🔴 | 26/09 |  | `N0` | |
| `R09` | Securite reseau : firewall, IPsec/VPN, zero-trust | 🟠 | bonus |  | `N0` | |

### DevOps

| ID | Module | Prio | Prévu | Vu le | Niveau | Notes |
|---|---|---|---|---|---|---|
| `D01` | Linux : processus, fichiers, permissions, systemd | 🔴 | 11/09 |  | `N0` | |
| `D02` | Linux reseau & perf : ip, ss, nft, namespaces | 🔴 | 13/09 |  | `N0` | |
| `D03` | Bash & scripting robuste | 🔴 | 13/09 |  | `N0` | |
| `D04` | Git avance & workflows d'equipe | 🔴 | 15/09 |  | `N0` | |
| `D05` | Docker : images, couches, reseau, volumes | 🔴 | 16/09 |  | `N0` | |
| `D06` | Kubernetes : objets, scheduling, reseau, Helm | 🔴 | 18/09 |  | `N0` | |
| `D08` | CI/CD : pipelines, artefacts, strategies de deploiement | 🔴 | 21/09 |  | `N0` | |
| `D09` | Observabilite : Prometheus/PromQL, Grafana, OTel, SLO | 🔴 | 22/09 |  | `N0` | |
| `D07` | IaC : Terraform & Ansible | 🟠 | 27/09 |  | `N0` | |
| `D10` | Cloud, IAM, secrets, supply chain | 🟠 | 27/09 |  | `N0` | |

### Data

| ID | Module | Prio | Prévu | Vu le | Niveau | Notes |
|---|---|---|---|---|---|---|
| `T01` | Modelisation relationnelle, normalisation, etoile | 🔴 | 14/09 |  | `N0` | |
| `T02` | SQL avance : fenetrage, CTE, plans, index | 🔴 | 14/09 |  | `N0` | |
| `T03` | OLTP vs OLAP, stockage colonne, Parquet/Avro/ORC | 🔴 | 16/09 |  | `N0` | |
| `T04` | Warehouse, Lake, Lakehouse : Delta, Iceberg, Hudi | 🔴 | 17/09 |  | `N0` | |
| `T05` | Systemes distribues : CAP, consensus, partitionnement | 🔴 | 18/09 |  | `N0` | |
| `T06` | Spark : execution, shuffle, partitionnement, tuning | 🔴 | 19/09 |  | `N0` | |
| `T07` | Kafka : topics, partitions, offsets, semantiques | 🔴 | 19/09 |  | `N0` | |
| `T09` | Orchestration : Airflow, dbt, idempotence, backfill | 🔴 | 20/09 |  | `N0` | |
| `T10` | NoSQL & series temporelles : Cassandra, Redis, Influx | 🔴 | 20/09 |  | `N0` | |
| `T08` | Streaming : Flink, watermarks, fenetres, etat | 🟠 | 26/09 |  | `N0` | |
| `T11` | Qualite, gouvernance, lignage, RGPD | 🟠 | 27/09 |  | `N0` | |
| `T12` | Architectures : Lambda/Kappa, Data Mesh, cout | 🟠 | 27/09 |  | `N0` | |

### IA

| ID | Module | Prio | Prévu | Vu le | Niveau | Notes |
|---|---|---|---|---|---|---|
| `A01` | ML fondamental : biais-variance, validation, metriques | 🔴 | 21/09 |  | `N0` | |
| `A02` | Modeles classiques & ensembles : arbres, boosting | 🔴 | 22/09 |  | `N0` | |
| `A04` | Transformers & LLM : attention, tokenisation, fine-tuning | 🔴 | 23/09 |  | `N0` | |
| `A05` | RAG, embeddings, bases vectorielles | 🔴 | 24/09 |  | `N0` | |
| `A06` | Series temporelles & detection d'anomalies | 🔴 | 25/09 |  | `N0` | |
| `A07` | MLOps : feature store, registry, drift, monitoring | 🔴 | 26/09 |  | `N0` | |
| `A08` | IA appliquee au reseau (AIOps) | 🔴 | 26/09 |  | `N0` | |
| `A03` | Deep learning : MLP, backprop, CNN, RNN/LSTM | 🟠 | bonus |  | `N0` | |

### Langages

| ID | Module | Prio | Prévu | Vu le | Niveau | Notes |
|---|---|---|---|---|---|---|
| `L01` | Python pour data engineering | 🔴 | 09/09 |  | `N0` | |
| `L03` | SQL intensif : 40 exercices corriges | 🔴 | 17/09 |  | `N0` | |
| `L02` | Python avance : asyncio, concurrence, polars | 🟠 | bonus |  | `N0` | |
| `L04` | Go : bases orientees reseau & infra | 🟠 | bonus |  | `N0` | |
| `L05` | YAML / HCL / Jinja : configuration as code | 🟠 | bonus |  | `N0` | |
| `L06` | Scala / Java : codebase Spark | 🟢 | bonus |  | `N0` | |

---

## Calendrier de rappel espacé

Chaque module **effectivement traité** au jour J revient à **J+1, J+3, J+7, J+14**.
Un rappel = 2-5 min : réciter la fiche de mémoire, puis vérifier.
Coche ✅ si c'est venu tout seul, ⚠️ si ça a coincé (un ⚠️ remet le module à J+1).

> Ce calendrier est **calculé à partir de la colonne « Vu le »**, pas des dates prévues.
> Renseigne « Vu le » quand tu termines la **Plongée** d'un module, puis lance
> `./outils/rappels.py` : la table ci-dessous est régénérée sur tes dates réelles.
> Un décalage d'une journée ne désynchronise donc plus rien.

<!-- RAPPELS:DEBUT -->
| Date | Rappels du jour | Fait |
|---|---|---|
| — | _Aucun module traité : renseigne la colonne « Vu le »._ | |
<!-- RAPPELS:FIN -->

## Journal de bord

Trois lignes par jour dans `journal/AAAA-MM-JJ.md` :
ce qui est entre tout seul / ce qui resiste / une question ouverte.

Relis la colonne "ce qui resiste" chaque dimanche : elle revele les vrais points
faibles, ceux que le ressenti a chaud masque.

