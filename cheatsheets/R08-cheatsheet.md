# R08 — Cheatsheet : HTTP, TLS/mTLS, gRPC, WebSocket

Référence opérationnelle. À garder ouverte pendant qu'on travaille.

---

## 1. Ports et identifiants ALPN

| Service | Transport | Port | ALPN |
|---|---|---|---|
| HTTP | TCP | **80** | `http/1.1` |
| HTTPS (HTTP/1.1, HTTP/2) | TCP + TLS | **443** | `http/1.1`, **`h2`** |
| HTTP/2 en clair (h2c) | TCP | 80 / autre | `h2c` (hors TLS) |
| **HTTP/3 (QUIC)** | **UDP** | **443** | **`h3`** |
| WebSocket `ws://` | TCP | 80 | — (upgrade depuis HTTP/1.1) |
| WebSocket `wss://` | TCP + TLS | 443 | `http/1.1` |
| gRPC (convention) | TCP + TLS | **50051** | **`h2`** obligatoire |
| DoT / DoQ | TCP+TLS / QUIC | 853 | `dot` / `doq` |

---

## 2. Codes de statut

| Famille | Sens | Rejouer ? |
|---|---|---|
| 1xx | informationnel | — |
| 2xx | succès | — |
| 3xx | redirection | suivre |
| **4xx** | **erreur du client** | **non** (sauf 408, 429) |
| **5xx** | **erreur du serveur** | **oui, avec backoff** |

| Code | Nom | Contexte |
|---|---|---|
| 100 | Continue | `Expect: 100-continue` — curl si corps > **1024 o**, attente **1 s** |
| 101 | Switching Protocols | **WebSocket** |
| 103 | Early Hints | `Link: rel=preload` — remplace le server push |
| 200 / 201 / 202 / 204 | OK / Created / Accepted / No Content | 201 → `Location:` ; 202 → job async |
| 206 | Partial Content | réponse à `Range:` |
| 301 / 302 | permanent / temporaire | ⚠ peuvent transformer POST → GET |
| **307 / 308** | temporaire / permanent | **conservent méthode + corps** |
| 304 | Not Modified | revalidation OK, **pas de corps** |
| 400 / 401 / 403 | malformé / **non authentifié** / non autorisé | 401 doit envoyer `WWW-Authenticate` |
| 404 / 405 / 409 | absent / méthode / conflit | 405 doit envoyer `Allow:` |
| 412 / 413 / 415 / 422 | `If-Match` KO / trop gros / type / validation | 413 : nginx `client_max_body_size 1m` |
| **429** | Too Many Requests | lire **`Retry-After`** |
| 499 | (nginx) client closed | **le client a raccroché** |
| 500 / 501 | plantage / non implémenté | |
| **502 / 503 / 504** | backend injoignable / surcharge / **trop lent** | 504 : ALB **60 s** |

---

## 3. En-têtes de cache

| En-tête / directive | Effet |
|---|---|
| `Cache-Control: max-age=N` | fraîche N s (tous caches) |
| `s-maxage=N` | idem, **caches partagés seulement**, écrase `max-age` |
| **`no-cache`** | **stocke mais revalide à chaque usage** |
| **`no-store`** | **ne stocke nulle part** |
| `private` / `public` | navigateur seul / cache partagé autorisé |
| `must-revalidate` | interdit de servir du périmé |
| `immutable` | ne revalide jamais (assets hashés) |
| `stale-while-revalidate=N` | sert le périmé N s pendant le rafraîchissement |
| `ETag: "x"` / `W/"x"` | empreinte forte / faible |
| `If-None-Match: "x"` | → **304** si inchangé |
| `If-Match: "x"` | → **412** si modifié (verrou optimiste) |
| `Last-Modified` / `If-Modified-Since` | granularité **1 seconde** |
| `Vary: Accept-Encoding, Origin` | axes de variation — **obligatoire** derrière un CDN |
| `Age: N` | secondes passées dans le cache partagé |

---

## 4. Cookies et CORS

```
Set-Cookie: k=v; Domain=x.fr; Path=/; Max-Age=3600; Secure; HttpOnly; SameSite=Lax
```

| Attribut | Valeur / défaut |
|---|---|
| `SameSite` | **`Lax` par défaut** · `None` **exige** `Secure` · `Strict` |
| taille | **~4096 o** par cookie, ~50 par domaine |
| `Domain` absent | hôte **exact** (plus strict — le bon défaut) |

| En-tête CORS | Rôle |
|---|---|
| `Origin` | envoyé par le navigateur |
| `Access-Control-Request-Method / -Headers` | dans le **pré-vol** `OPTIONS` |
| `Access-Control-Allow-Origin` | `*` ou origine exacte |
| `Access-Control-Allow-Methods / -Headers` | réponse au pré-vol |
| `Access-Control-Allow-Credentials: true` | **incompatible avec `*`** → + `Vary: Origin` |
| `Access-Control-Expose-Headers` | rendre un en-tête lisible en JS |
| `Access-Control-Max-Age` | cache du pré-vol (**Chrome plafonne à 7200 s**) |

Pré-vol déclenché si : méthode ∉ {GET, HEAD, POST} **ou** `Content-Type` ∉ {`application/x-www-form-urlencoded`, `multipart/form-data`, `text/plain`} **ou** en-tête personnalisé.

---

## 5. HTTP/2 — trames et réglages

```
+----------------------------------+--------+
| Length (24)                      |Type(8) |
+--------+-------------------------+--------+
|Flags(8)|R|   Stream Identifier (31)       |
+--------+--------------------------------- +   → 9 octets d'en-tête
```

| Type | Nom | | Type | Nom |
|---|---|---|---|---|
| `0x0` | DATA | | `0x5` | PUSH_PROMISE |
| `0x1` | HEADERS | | `0x6` | PING |
| `0x2` | PRIORITY | | `0x7` | GOAWAY |
| `0x3` | RST_STREAM | | `0x8` | WINDOW_UPDATE |
| `0x4` | SETTINGS | | `0x9` | CONTINUATION |

| SETTINGS | ID | Défaut |
|---|---|---|
| `HEADER_TABLE_SIZE` | 0x1 | **4096** |
| `ENABLE_PUSH` | 0x2 | 1 |
| `MAX_CONCURRENT_STREAMS` | 0x3 | non borné (nginx **128**, Go **250**) |
| **`INITIAL_WINDOW_SIZE`** | 0x4 | **65535** ⚠ |
| `MAX_FRAME_SIZE` | 0x5 | **16384** (max 16777215) |
| `MAX_HEADER_LIST_SIZE` | 0x6 | non borné |

Préambule client : `PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n` (**24 o**). Stream **impair = client**, **pair = serveur**, **0 = connexion**.
Pseudo-en-têtes : `:method :scheme :authority :path` (requête), `:status` (réponse). Noms en **minuscules**. `Connection`, `Keep-Alive`, `Transfer-Encoding`, `Upgrade` **interdits**.

**Débit max d'un flux = fenêtre / RTT.** 65535 o / 100 ms = **5,24 Mb/s**.

---

## 6. TLS

| Version | Année | Coût | Statut |
|---|---|---|---|
| SSL 3.0 | 1996 | — | mort (POODLE) |
| TLS 1.0 / 1.1 | 1999 / 2006 | 2 RTT | **dépréciées (RFC 8996)** |
| **TLS 1.2** | 2008 | **2 RTT** | acceptable en ECDHE+AEAD |
| **TLS 1.3** | 2018 | **1 RTT** (0-RTT en reprise) | recommandée |

Enregistrement TLS : `Type(1) | Version(2) | Longueur(2)` = **5 o**, charge ≤ **16384 o**.
Types : `20` change_cipher_spec · `21` alert · `22` handshake · `23` application_data.

| Suites TLS 1.3 (les 3 utilisées) |
|---|
| `TLS_AES_128_GCM_SHA256` |
| `TLS_AES_256_GCM_SHA384` |
| `TLS_CHACHA20_POLY1305_SHA256` (mobile, sans AES-NI) |

Lecture d'une suite 1.2 : `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256` = échange **ECDHE** · auth **RSA** · chiffrement **AES-128-GCM** · PRF **SHA256**.

| Alerte | N° | Cause typique |
|---|---|---|
| `handshake_failure` | **40** | aucune version/suite/groupe en commun |
| `bad_certificate` | 42 | certificat illisible |
| `certificate_expired` | 45 | date, ou **horloge du client** |
| `unknown_ca` | **48** | l'autre bout ne connaît pas ta CA (fréquent en **mTLS**) |
| `decrypt_error` | 51 | signature de handshake invalide |
| `unrecognized_name` | **112** | **SNI** absent ou inconnu |
| `certificate_required` | **116** | mTLS exigé, aucun certificat client (TLS 1.3) |

| Durée de validité | Valeur |
|---|---|
| Certificat public | **≤ 398 jours** |
| Let's Encrypt | **90 jours** |
| Maille de services (Istio/Linkerd) | **~24 h**, rotation auto |

---

## 7. `openssl` — diagnostic TLS

| Commande | Ce qu'elle donne |
|---|---|
| `openssl s_client -connect h:443 -servername h </dev/null` | handshake complet ; lire `Verify return code` |
| `... -showcerts` | **toute la chaîne envoyée** → compter les `BEGIN CERTIFICATE` |
| `... -alpn h2,http/1.1` | affiche `ALPN protocol: h2` |
| `... -tls1_2` / `-tls1_3` | forcer une version (test de compatibilité) |
| `... -cipher 'ECDHE+AESGCM'` | forcer des suites |
| `... -cert c.crt -key c.key` | **mTLS** côté client |
| `... -CAfile ca.pem` | valider contre une CA précise |
| `... -status` | vérifier l'**agrafage OCSP** |
| `openssl x509 -in c.pem -noout -text` | tout le certificat |
| `openssl x509 -in c.pem -noout -subject -issuer -dates` | l'essentiel |
| `openssl x509 -in c.pem -noout -ext subjectAltName` | **les SAN** |
| `openssl verify -CAfile r.pem -untrusted i.pem f.pem` | la chaîne remonte-t-elle ? |
| `openssl crl2pkcs7 -nocrl -certfile chain.pem \| openssl pkcs7 -print_certs -noout` | lister une chaîne |
| `openssl rsa -in k.pem -noout -modulus \| openssl md5` | la clé correspond-elle au certificat ? (comparer avec `x509 -modulus`) |
| `openssl s_time -connect h:443` | handshakes par seconde |

```bash
# Le one-liner à retenir : dates + SAN + émetteur d'un site distant
openssl s_client -connect api.exemple.fr:443 -servername api.exemple.fr </dev/null 2>/dev/null \
 | openssl x509 -noout -subject -issuer -dates -ext subjectAltName

# Expiration en masse
for h in a.fr b.fr c.fr; do
  echo -n "$h "; echo | openssl s_client -connect $h:443 -servername $h 2>/dev/null \
    | openssl x509 -noout -enddate
done
```

---

## 8. `curl` — les options utiles

| Option | Effet |
|---|---|
| `-v` / `-vvv` | en-têtes + détail TLS |
| `-sSI` | en-têtes seuls (HEAD), silencieux mais montre les erreurs |
| `-o /dev/null` | jeter le corps |
| `--http1.1` / `--http2` / `--http2-prior-knowledge` / `--http3` | forcer la version |
| `-k` / `--insecure` | ⚠ **désactive la vérification** — diagnostic uniquement |
| `--cacert ca.pem` | CA de confiance explicite |
| `--cert c.pem --key k.pem` | **mTLS** |
| `--resolve h:443:10.0.0.5` | forcer l'IP en gardant SNI + `Host` (test d'un backend précis) |
| `--connect-to h:443:autre:443` | rediriger la connexion |
| `-H 'Header: v'` | en-tête |
| `-L` | suivre les redirections |
| `--compressed` | envoie `Accept-Encoding` et décompresse |
| `-r 0-1023` | requête `Range:` → 206 |
| `--retry 5 --retry-delay 1 --retry-all-errors` | rejeu |
| `-w '%{...}'` | métriques (ci-dessous) |

```bash
# LA commande de budget de latence
curl -o /dev/null -sS -w \
 'dns:%{time_namelookup} tcp:%{time_connect} tls:%{time_appconnect} ttfb:%{time_starttransfer} tot:%{time_total} ver:%{http_version} code:%{http_code}\n' \
 https://api.exemple.fr/health
```

| Variable `-w` | Mesure (cumulée depuis le départ) |
|---|---|
| `time_namelookup` | fin du DNS |
| `time_connect` | fin du handshake **TCP** |
| `time_appconnect` | fin du handshake **TLS** |
| `time_pretransfer` | prêt à envoyer la requête |
| `time_starttransfer` | **TTFB** — premier octet reçu |
| `time_total` | fin |

**Lecture** : `appconnect − connect` = coût TLS · `starttransfer − appconnect` = temps serveur · `total − starttransfer` = transfert.

---

## 9. gRPC

| Élément | Valeur |
|---|---|
| Chemin | `/package.Service/Method` |
| `content-type` | `application/grpc`, `application/grpc+proto`, `+json` |
| En-têtes obligatoires | `te: trailers`, `:method: POST` |
| Deadline | `grpc-timeout: 100m` (`H`,`M`,`S`,`m`,`u`,`n`) |
| Cadrage message | `1 o` (compressé 0/1) + `4 o` longueur **big-endian** + charge |
| Statut | **`:status: 200` toujours** ; vrai code dans les **trailers** `grpc-status` / `grpc-message` |
| Taille max reçue | **4 Mio** par défaut (`grpc.max_receive_message_length`) |

| Code | Nom | Code | Nom |
|---|---|---|---|
| 0 | OK | 8 | RESOURCE_EXHAUSTED |
| 1 | CANCELLED | 9 | FAILED_PRECONDITION |
| 2 | UNKNOWN | 10 | ABORTED |
| 3 | INVALID_ARGUMENT | 11 | OUT_OF_RANGE |
| **4** | **DEADLINE_EXCEEDED** | **12** | **UNIMPLEMENTED** |
| 5 | NOT_FOUND | 13 | INTERNAL |
| 6 | ALREADY_EXISTS | **14** | **UNAVAILABLE** (rejouable) |
| 7 | PERMISSION_DENIED | 16 | UNAUTHENTICATED |

**Protobuf — types de fil**

| N° | Nom | Encode | Balise |
|---|---|---|---|
| 0 | VARINT | int32/64, uint, sint, bool, enum | `(champ << 3) \| 0` |
| 1 | I64 | fixed64, sfixed64, double | `\| 1` |
| 2 | LEN | string, bytes, message, `repeated` packé | `\| 2` |
| 5 | I32 | fixed32, sfixed32, float | `\| 5` |

Champs **1→15** : balise **1 octet**. **16→2047** : 2 octets. Varint : **7 bits utiles/octet**.
✅ ajouter un champ, renommer · ❌ changer un numéro, réutiliser un numéro (`reserved 4, 7;`), changer un type.

```bash
grpcurl -plaintext localhost:50051 list                    # services (réflexion)
grpcurl -plaintext localhost:50051 list pkg.Service        # méthodes
grpcurl -plaintext localhost:50051 describe pkg.Message    # schéma
grpcurl -d '{"id":42}' -H 'authorization: Bearer x' h:443 pkg.Service/Method
grpcurl -cacert ca.pem -cert c.pem -key k.pem h:443 list   # mTLS
grpc_health_probe -addr=localhost:50051                    # sonde de santé K8s
protoc --python_out=. --grpc_python_out=. api.proto        # génération
protoc --decode_raw < message.bin                          # décoder sans le .proto
```

---

## 10. WebSocket

```
GET /stream HTTP/1.1        →   HTTP/1.1 101 Switching Protocols
Upgrade: websocket              Upgrade: websocket
Connection: Upgrade             Connection: Upgrade
Sec-WebSocket-Key: <16 o b64>   Sec-WebSocket-Accept: b64(SHA1(key+GUID))
Sec-WebSocket-Version: 13       GUID = 258EAFA5-E914-47DA-95CA-C5AB0DC85B11
```

| Opcode | Sens | | Code close | Sens |
|---|---|---|---|---|
| `0x0` | continuation | | 1000 | normal |
| `0x1` | texte (UTF-8) | | 1001 | départ |
| `0x2` | binaire | | 1002 | erreur de protocole |
| `0x8` | close | | **1006** | **anormal, aucune trame close** |
| `0x9` | ping | | 1011 | erreur serveur |
| `0xA` | pong | | 1013 | réessaie plus tard |

En-tête de trame **2 à 14 o**. Masquage **client → serveur obligatoire** (4 o de clé XOR).

```bash
websocat -v wss://api.exemple.fr/stream
websocat -H='Authorization: Bearer x' wss://api.exemple.fr/stream
wscat -c wss://api.exemple.fr/stream
```

---

## 11. Réglages serveurs et clients

| Produit | Réglage | Défaut |
|---|---|---|
| nginx | `keepalive_timeout` | **75 s** |
| nginx | `proxy_read_timeout` | **60 s** |
| nginx | `client_max_body_size` | **1 m** |
| nginx | `http2_max_concurrent_streams` | 128 |
| ALB (AWS) | idle timeout | **60 s** |
| NLB (AWS) | idle timeout | **350 s** |
| `boto3` | `max_pool_connections` | **10** |
| `requests` / urllib3 | `pool_connections` / `pool_maxsize` | **10 / 10** |
| urllib3 `Retry` | `allowed_methods` | idempotentes uniquement (**pas POST**) |
| Go `http.Transport` | `MaxIdleConnsPerHost` | **2** ⚠ |
| gRPC | message reçu max | **4 Mio** |
| Navigateurs | connexions HTTP/1.1 par origine | **6** |

---

## 12. Table de décision protocole

| Situation | Choix |
|---|---|
| API publique, clients inconnus | **REST/JSON sur HTTP/2** |
| Service ↔ service, fort débit, contrat strict | **gRPC** |
| Un client, beaucoup de vues différentes | **GraphQL** |
| Serveur → client, unidirectionnel, texte | **SSE** (`text/event-stream`) |
| Duplex temps réel navigateur | **WebSocket** |
| Transfert de gros volumes | **202 + URL présignée + `Range`** ou **Arrow Flight** |
| Inter-services chiffré + authentifié sans toucher au code | **mTLS via maille de services** |

---

## 13. Réflexes de diagnostic

| Symptôme | Première hypothèse | Commande |
|---|---|---|
| `unable to get local issuer certificate` | **intermédiaire manquant** | `s_client -showcerts \| grep -c BEGIN` |
| Marche dans le navigateur, pas en curl/Java | idem (AIA) | idem |
| `certificate has expired` mais le certificat est bon | **horloge du client** | `date -u` |
| Handshake TLS qui **gèle toujours au même point** | **MTU / PMTUD** (R03/R06) | `ping -M do -s 1400`, MSS clamping |
| 504 sur les requêtes longues seulement | **timeout d'inactivité du LB** | logs LB vs logs backend |
| WebSocket coupé à 60 s | idem + pas de ping | ping applicatif 20-30 s |
| gRPC : 90 % du trafic sur un pod | **LB L4 + connexion épinglée** | passer L7 / LB client / `MAX_CONNECTION_AGE` |
| gRPC `UNIMPLEMENTED` inexplicable | proxy qui **mange les trailers** | tester en direct, sans proxy |
| Transfert cross-région lent, lien non saturé | **fenêtre H2 65535** ou fenêtre TCP | relever les deux, ou `Range` parallèle |
| « blocked by CORS » | souvent un **500** sous-jacent | rejouer en `curl -v` |
| Beaucoup de handshakes TLS dans les traces | **pool de connexions trop petit** | `max_pool_connections`, `Session` |
