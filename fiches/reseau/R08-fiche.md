# R08 — Fiche : HTTP/1.1→3, TLS/mTLS, gRPC, WebSocket

> Lis-la **avant** le cours (pretesting) puis **récite-la** aux rappels. Objectif : 3 minutes.

## Le fil rouge

**HTTP** = donne-moi ce document · **TLS** = prouve qui tu es, parlons en privé · **gRPC** = appelle cette fonction chez toi · **WebSocket** = garde la ligne ouverte.

## HTTP — format

Requête `MÉTHODE CIBLE VERSION` · Réponse `VERSION CODE RAISON` · en-têtes `Nom: valeur` · **CRLF** (`\r\n`) · **ligne vide = fin des en-têtes**.
Fin du corps : `Content-Length` **ou** `Transfer-Encoding: chunked` (tailles en **hexa**, morceau **0** = fin). Les deux ensemble → *request smuggling*.
`Content-Encoding` (gzip/br/zstd) = la **ressource** · `Transfer-Encoding` = **ce saut-là** seulement.

## HTTP — méthodes

| | Sûre | Idempotente |
|---|---|---|
| GET, HEAD, OPTIONS, TRACE | ✅ | ✅ |
| PUT, DELETE | ❌ | ✅ |
| **POST, PATCH** | ❌ | **❌** |

**Idempotent = même ÉTAT final**, pas même réponse (`DELETE` → 204 puis 404 : idempotent).
Seules les idempotentes sont **rejouées d'office** (`urllib3` exclut POST). `POST` rejouable ⇒ `Idempotency-Key`.

## HTTP — codes

**1xx** reçu · **2xx** ok · **3xx** ailleurs/déjà · **4xx = TA faute** · **5xx = MA faute** (rejouable).
`100` Continue (curl si corps > 1024 o, attend **1 s**) · `101` **WebSocket** · `103` Early Hints (remplace le push).
`201` + `Location` · `202` async · `204` sans corps · `206` réponse à `Range`.
`301/302` peuvent transformer POST→GET · **`307/308` conservent méthode + corps**. `304` = revalidation ok, **0 octet**.
`401` = **non authentifié** · `403` = non autorisé (S3 : signature/horloge) · `409` conflit · `412` `If-Match` obsolète · `413` corps trop gros · `429` quota → lis **`Retry-After`**.
`499` nginx = **le client a raccroché** · **`502`** = backend injoignable/illisible · **`504`** = backend trop lent (**ALB 60 s**, nginx `proxy_read_timeout 60s`) · `503` = surcharge (S3 `SlowDown`).

## HTTP — cache

**Fraîcheur** (`max-age`) = 0 requête. **Validation** (`ETag`/`If-None-Match` → **304**) = 1 RTT, 0 corps.
**`no-cache` = revalide à chaque fois** ≠ **`no-store` = ne stocke rien**. `s-maxage` = caches partagés. `private` = navigateur seul. `immutable`, `stale-while-revalidate=N`.
`ETag "x"` fort · `W/"x"` faible · `Last-Modified` = granularité **1 s** (inférieur). `If-Match` → **412** = CAS HTTP.
**`Vary: Accept-Encoding`** obligatoire, sinon poison de cache. Contenu personnalisé sans `private` → fuite entre utilisateurs.

## HTTP — cookies & CORS

`Set-Cookie: k=v; Domain; Path; Max-Age; Secure; HttpOnly; SameSite=Lax|Strict|None`. **`Lax` par défaut** · `None` exige `Secure` · **~4096 o**/cookie · `HttpOnly` = invisible en JS.
**Origine = schéma + hôte + port** (les cookies, eux, **ignorent le port**).
**Pré-vol** `OPTIONS` dès que : méthode ≠ GET/HEAD/POST, ou `Content-Type` hors `form-urlencoded`/`multipart`/`text-plain`, ou en-tête custom.
`Access-Control-Allow-Origin/-Methods/-Headers/-Max-Age` · **`Allow-Credentials: true` incompatible avec `*`** → + `Vary: Origin`.
⚠ **CORS est appliqué par le NAVIGATEUR, protège l'utilisateur, PAS le serveur.** Un 500 s'affiche comme une erreur CORS.

## HTTP/1.1 → 2 → 3

| | 1.1 | 2 | 3 |
|---|---|---|---|
| Encodage | texte | **binaire, trames 9 o** | binaire |
| Parallélisme | **6 connexions**/origine | **flux multiplexés** | flux **QUIC** |
| En-têtes | répétés (500-800 o) | **HPACK** (table statique **61**) | **QPACK** (statique **99**) |
| Transport | TCP | TCP | **QUIC/UDP 443** |
| Handshake à froid | TCP+TLS | TCP+TLS | **1 RTT**, 0-RTT en reprise |

Trame H2 : `Longueur(24) | Type(8) | Flags(8) | R+StreamID(31)` = **9 o**. Préambule client **24 o** `PRI * HTTP/2.0…`.
IDs : **impairs = client, pairs = serveur, 0 = connexion**. `DATA 0x0 · HEADERS 0x1 · RST_STREAM 0x3 · SETTINGS 0x4 · GOAWAY 0x7 · WINDOW_UPDATE 0x8`.
Défauts H2 : table HPACK **4096 o** · **`INITIAL_WINDOW_SIZE 65535 o`** · `MAX_FRAME_SIZE 16384 o` · nginx 128 flux.
H2 : minuscules obligatoires, pseudo-en-têtes **`:method :scheme :authority :path :status`**, `Connection`/`Transfer-Encoding` **interdits**.
QUIC : **Connection ID** → survit au changement de réseau · presque tout chiffré · **espace utilisateur** (CPU +). Découverte : `Alt-Svc: h3=":443"` ou DNS **HTTPS (type 65)**. **0-RTT rejouable → idempotent uniquement.**

## Head-of-line blocking

1.1 pipeliné : réponses **dans l'ordre** → mort. H2 : réglé **dans l'appli**, **pas dans TCP** (1 perte gèle tous les flux). H3 : réglé **entre flux**, subsiste **dans** un flux. Formule : **ordre imposé + ressource partagée**.

## TLS

3 garanties : **confidentialité · intégrité · AUTHENTIFICATION** (la seule qui casse). Enregistrement : **5 o** d'en-tête, charge ≤ **16 384 o** (2¹⁴). `20 CCS · 21 alert · 22 handshake · 23 data`.
**Asymétrique = se mettre d'accord (lent) · symétrique = bosser (rapide).**

| | TLS 1.2 | TLS 1.3 |
|---|---|---|
| Coût | **2 RTT** | **1 RTT** (+0-RTT) |
| Preuve de clé privée | `ServerKeyExchange` | `CertificateVerify` |
| Certificat | **en clair** | **chiffré** |
| PFS | optionnelle | **obligatoire** |
| Suites | des dizaines | **5** |

**1.2** : ClientHello → ServerHello, Certificate, ServerKeyExchange, [CertificateRequest], ServerHelloDone → ClientKeyExchange, CCS, Finished → CCS, Finished.
**1.3** : ClientHello (**+key_share**) → ServerHello + {EncryptedExtensions, Certificate, CertificateVerify, Finished} → {Finished}.
**Supprimé en 1.3** : RSA statique, CBC, compression, renégociation, MD5/SHA-1, groupes DH custom. `TLS_AES_128_GCM_SHA256` · `TLS_AES_256_GCM_SHA384` · `TLS_CHACHA20_POLY1305_SHA256`.
**PFS** = clé privée volée demain ≠ trafic d'hier déchiffré (ECDHE éphémère ; la clé privée **signe** seulement).
**SNI = Nom** (en clair, choix du certificat, virtual hosting) · **ALPN = Protocole** (`h2`/`http/1.1`/`h3`, **sans RTT en plus**).
**RTT jusqu'au 1er octet** : TCP+1.2 = **3** · TCP+1.3 = **2** · QUIC = **1** · 0-RTT = **0**.

## Certificats

Chaîne **feuille → intermédiaire(s) → racine** (auto-signée, dans le magasin). Le serveur envoie **feuille + intermédiaires**, jamais la racine.
Vérif : **chaîne · signatures + `CA:TRUE` · dates · SAN · `EKU serverAuth` · révocation** (CRL/OCSP/**agrafage**). **Le CN n'est plus lu** (Chrome 58) → sans SAN = invalide. Public **≤ 398 j** · Let's Encrypt **90 j**.
**C-N-D-V** = **C**haîne, **N**om, **D**ate, **V**ersion.
`unable to get local issuer certificate` → **intermédiaire manquant** (navigateur le récupère par **AIA**, pas curl/JVM) → servir **`fullchain.pem`**. Alertes : **40** handshake_failure · **48** unknown_ca · **112** unrecognized_name · **116** certificate_required.

## mTLS

Serveur envoie **`CertificateRequest`** → client renvoie `Certificate` + **`CertificateVerify`**. Identité établie **avant** le 1er octet HTTP, **aucun secret partagé volable** (≠ jeton Bearer).
Maille : sidecar Envoy, mTLS transparent, certificats **~24 h** rotatifs, identité **`spiffe://cluster.local/ns/<ns>/sa/<sa>`**. ⚠ mTLS = identité de **charge de travail**, pas d'**utilisateur** (→ JWT en plus).

## gRPC

**HTTP/2 + protobuf + codegen**. Chemin = `/package.Service/Method` · `content-type: application/grpc+proto` · `te: trailers` · **`grpc-timeout`** · cadrage **1 o compressé + 4 o longueur BE**.
⚠ **`:status` toujours 200** ; l'erreur est dans les **trailers** `grpc-status`/`grpc-message`.
Codes : `0 OK · 3 INVALID_ARGUMENT · 4 DEADLINE_EXCEEDED · 5 NOT_FOUND · 7 PERMISSION_DENIED · 8 RESOURCE_EXHAUSTED (>4 Mio) · 12 UNIMPLEMENTED · 14 UNAVAILABLE (le seul rejoué) · 16 UNAUTHENTICATED`.
**4 modes** : unaire · **serveur**-streaming · **client**-streaming · **bidirectionnel**.
Protobuf : balise = **`(numéro << 3) | type`** · types `0 VARINT · 1 I64 · 2 LEN · 5 I32` · **champs 1-15 = 1 octet** de balise. Numéros **gravés à vie** (`reserved`), **noms libres**. ~**5-6× plus petit** que JSON.
**Deadline absolu propagé** → annule toute la chaîne. ⚠ **LB L4 + gRPC = déséquilibre** (1 connexion épinglée) → L7/Envoy, LB **côté client**, ou `MAX_CONNECTION_AGE`. Navigateur → **gRPC-Web + proxy**.

## WebSocket

`GET` + `Upgrade: websocket` + `Connection: Upgrade` + `Sec-WebSocket-Key` (16 o b64) + `Version: 13` → **`101 Switching Protocols`** + `Sec-WebSocket-Accept = b64(SHA1(key + GUID))`.
Trame : `FIN|RSV3|opcode(4)|MASK|len(7/+16/+64)` → en-tête **2-14 o**. `0x1 texte · 0x2 binaire · 0x8 close · 0x9 ping · 0xA pong`. **Masquage client→serveur obligatoire** (anti-empoisonnement de proxy).
`1000` normal · **`1006` anormal = coupé sans close** (timeout d'inactivité du LB → **ping toutes les 20-30 s**).
Unidirectionnel serveur→client ⇒ **SSE**, pas WebSocket.

## Choisir

**REST = documents · gRPC = fonctions · GraphQL = requêtes.** Public/navigateur → REST · service↔service volumineux → gRPC · clients hétérogènes → GraphQL · **gros volumes → 202 + URL présignée + `Range`, jamais dans le corps**.

## Chiffres pipeline

RTT : intra-DC 0,5 ms · Paris↔Francfort **10 ms** · Paris↔Virginie **85 ms** · Paris↔Singapour **170 ms**.
`boto3 max_pool_connections` = **10** · `requests pool_maxsize` = **10** → étranglent un job à 64 threads.
Fenêtre H2 **65 535 o** / RTT **100 ms** = **5,24 Mb/s** max, quel que soit le lien.

## Test express

1. Comment le client sait-il qu'une réponse HTTP est finie ?
2. `DELETE` renvoie 404 au 2ᵉ appel : est-il encore idempotent ? Pourquoi ?
3. Différence exacte entre 502 et 504 ?
4. Différence entre `no-cache` et `no-store` ?
5. CORS protège-t-il le serveur ?
6. Pourquoi HTTP/2 n'élimine-t-il pas tout le head-of-line blocking ?
7. Où le serveur prouve-t-il qu'il détient la clé privée, en TLS 1.2 puis en 1.3 ?
8. Quel code HTTP renvoie un appel gRPC en erreur, et où est le vrai code ?
