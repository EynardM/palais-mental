# R08 — Couche 7 : HTTP/1.1→3, TLS/mTLS, gRPC, WebSocket

> **Ce que tu sauras faire à la fin**
> - Lire une requête et une réponse HTTP brutes ligne par ligne, nommer chaque en-tête et dire qui le consomme (client, cache, proxy, serveur).
> - Choisir un code de statut juste, expliquer pourquoi une méthode idempotente peut être rejouée automatiquement et pas une autre, et dimensionner un cache avec `Cache-Control` + `ETag`.
> - Dérouler de mémoire la différence HTTP/1.1 → HTTP/2 → HTTP/3, et dire **à quel étage** le blocage de tête de file survit à chaque version.
> - Raconter un handshake TLS 1.2 puis un TLS 1.3 message par message, chiffrer le coût en RTT, et expliquer ce que 1.3 a supprimé et pourquoi.
> - Diagnostiquer une erreur de certificat en trois commandes `openssl` et nommer la cause : intermédiaire manquant, SAN qui ne correspond pas, expiration, CA inconnue, horloge décalée.
> - Expliquer mTLS, l'identité SPIFFE et pourquoi une maille de services le fait à ta place ; savoir pourquoi un load balancer L4 casse l'équilibrage gRPC.
> - Arbitrer REST / gRPC / GraphQL / WebSocket sur un cas concret, avec les vrais arguments et les vrais chiffres.
>
> **Pourquoi ça compte dans ton poste**
> Tout ce que tu vas écrire comme data engineer parle HTTP, même quand ça ne s'appelle pas HTTP. S3 est une
> API HTTP. BigQuery, Snowflake, l'API de ton fournisseur de modèles, les webhooks, les endpoints d'inférence :
> HTTP sur TLS. Spark Connect, Arrow Flight, etcd, Envoy, Triton, la maille de services de ton cluster : gRPC
> sur HTTP/2 sur TLS. Quand un job crache `SSLError: unable to get local issuer certificate` à 3 h du matin,
> quand ton extraction cross-région plafonne à 5 Mb/s sans que le lien soit saturé, quand ton service gRPC
> envoie 90 % du trafic sur un seul pod — la cause est dans ce module, et nulle part ailleurs.
>
> **Prérequis** : `R01` (couches, encapsulation), `R03` (IP, MTU), `R06` (TCP : handshake, RTT, BDP, fenêtre, QUIC en survol), `R07` (DNS, load balancing L4/L7, timeouts d'inactivité).
> **Durée de lecture** : 80-95 min. Les sections 12 et 24 contiennent des calculs : papier et crayon.

---

## 1. Le problème : on a un tuyau, il faut une langue

R06 t'a laissé avec un tuyau d'octets fiable entre deux machines. TCP ne sait rien de ce qui circule
dedans : pour lui, `GET /index.html` et une photo de chat sont la même chose, une suite d'octets ordonnée.

Il manque trois choses pour que deux programmes se comprennent :

```
   Ce que TCP fournit               Ce qu'il manque encore
   ──────────────────               ──────────────────────
   Un flux d'octets ordonné    →    Où finit mon message et où commence
                                    le suivant ?                → CADRAGE

   Un tuyau anonyme            →    Qu'est-ce que je demande, et
                                    qu'est-ce qu'on me répond ? → SÉMANTIQUE

   Un tuyau EN CLAIR           →    Qui est en face, et qui écoute
                                    au milieu ?                 → SÉCURITÉ (TLS)
```

HTTP répond aux deux premières questions, TLS à la troisième. gRPC et WebSocket sont deux façons de
détourner HTTP pour faire ce qu'il ne sait pas faire nativement : appeler une fonction distante, et
pousser des données sans qu'on les demande.

Toute la suite du module est une variation sur une seule tension : **HTTP a été conçu en 1991 pour
récupérer un document texte**, et on lui demande aujourd'hui de transporter 40 To de Parquet, des flux
d'inférence en continu et l'authentification de 4 000 pods. Chaque version d'HTTP est une réponse à un
symptôme de cet écart.

> 🧠 **MÉMO** — Les quatre protocoles de ce module en une phrase chacun :
> **HTTP** = « donne-moi ce document » · **TLS** = « prouve-moi qui tu es et parlons en privé » ·
> **gRPC** = « appelle cette fonction chez toi » · **WebSocket** = « garde la ligne ouverte, on se
> reparle quand on veut ».

---

## 2. HTTP : anatomie d'un échange

### 2.1 Le format brut

HTTP/1.1 est un protocole **texte**, lisible à l'œil nu. C'est sa force pédagogique et sa faiblesse
technique. Une requête :

```
GET /api/v1/datasets?limit=50 HTTP/1.1␍␊      ← ligne de requête : MÉTHODE CIBLE VERSION
Host: data.exemple.fr␍␊                       ← en-têtes, un par ligne, "Nom: valeur"
User-Agent: python-requests/2.32.3␍␊
Accept: application/json␍␊
Authorization: Bearer eyJhbGci...␍␊
Accept-Encoding: gzip, br␍␊
␍␊                                            ← LIGNE VIDE = fin des en-têtes
(corps éventuel)
```

La réponse a exactement la même forme, sauf la première ligne :

```
HTTP/1.1 200 OK␍␊                             ← ligne de statut : VERSION CODE RAISON
Content-Type: application/json; charset=utf-8␍␊
Content-Length: 1523␍␊
Cache-Control: max-age=300, public␍␊
ETag: "a3f5c9"␍␊
␍␊
{"datasets":[...]}
```

`␍␊` = `\r\n` = CRLF = 2 octets, `0x0D 0x0A`. Ce n'est pas un détail cosmétique : un serveur qui accepte
`\n` seul là où la norme veut `\r\n` ouvre la porte au *request smuggling*, où deux équipements en chaîne
découpent le flux différemment et où un attaquant fait passer une requête cachée dans le corps d'une autre.

**Comment le récepteur sait-il où finit le corps ?** Trois mécanismes, et un seul à la fois :

| Mécanisme | En-tête | Usage |
|---|---|---|
| Longueur annoncée | `Content-Length: 1523` | le cas normal, taille connue à l'avance |
| Découpage en morceaux | `Transfer-Encoding: chunked` | taille inconnue (flux généré, export SQL) |
| Fermeture de connexion | ni l'un ni l'autre (HTTP/1.0) | obsolète, indistinguable d'une coupure |

Le format `chunked` : chaque morceau est précédé de sa **taille en hexadécimal**, et un morceau de taille
zéro termine le corps.

```
Transfer-Encoding: chunked
␍␊
16␍␊                    ← 0x16 = 22 octets suivent
{"row": 1, "ok": true}␍␊
8␍␊                     ← 0x8 = 8 octets
,{"r":2}␍␊
0␍␊                     ← morceau vide = FIN
␍␊
```

> ❓ **RETIENS ÇA** — Comment le client sait-il qu'une réponse HTTP est terminée ?
> <details><summary>→ réponse</summary><br>Par <code>Content-Length</code> (nombre d'octets annoncé), ou par <code>Transfer-Encoding: chunked</code> (morceaux préfixés de leur taille en hexa, terminés par un morceau de taille <b>0</b>). Les deux ensemble sont interdits : c'est exactement la faille du <i>request smuggling</i>.</details>

> ⚠️ **PIÈGE** — `Content-Encoding` ≠ `Transfer-Encoding`. `Content-Encoding: gzip` décrit la **ressource
> elle-même** (elle est compressée, l'ETag porte sur le contenu compressé, `Content-Length` compte les
> octets compressés). `Transfer-Encoding` décrit le **transport sur ce saut-là** et disparaît au proxy
> suivant. En pratique, tout le monde utilise `Content-Encoding` (`gzip`, `br`, `zstd`).

### 2.2 Sans état, et pourquoi

HTTP est **sans état** : chaque requête est indépendante, le serveur n'est censé rien retenir entre deux.
C'est ce qui permet de mettre 50 serveurs derrière un load balancer sans se poser de question.

Le prix : **tout le contexte doit être renvoyé à chaque requête** — cookies, jeton d'authentification,
en-têtes de négociation. Sur une API interne, ça peut faire 600 à 1 500 octets d'en-têtes répétés à
l'identique des milliers de fois par seconde. Cette redondance est exactement le problème que HTTP/2
résout avec HPACK (section 10).

---

## 3. Les méthodes : sûr, idempotent, cacheable

### 3.1 Le tableau à connaître par cœur

| Méthode | Sûre ? | Idempotente ? | Corps requête | Cacheable |
|---|---|---|---|---|
| `GET` | ✅ | ✅ | non | ✅ |
| `HEAD` | ✅ | ✅ | non | ✅ |
| `OPTIONS` | ✅ | ✅ | non | ❌ |
| `TRACE` | ✅ | ✅ | non | ❌ |
| `PUT` | ❌ | ✅ | oui | ❌ |
| `DELETE` | ❌ | ✅ | rare | ❌ |
| `POST` | ❌ | ❌ | oui | ~ (rarement) |
| `PATCH` | ❌ | ❌ | oui | ❌ |
| `CONNECT` | ❌ | ❌ | — | ❌ |

**Sûre** = ne modifie rien côté serveur (lecture seule). **Idempotente** = l'exécuter N fois produit le
même état final qu'une fois. Ce n'est **pas** « renvoie la même réponse » : `DELETE /job/42` renvoie 204
la première fois et 404 la deuxième, il reste idempotent parce que l'**état final** est identique.

**Analogie.** Idempotent, c'est l'interrupteur de position : « mets la lumière sur ON ». Tu appuies dix
fois, la lumière est allumée. Non idempotent, c'est le bouton poussoir « inverse la lumière » : dix
pressions ne donnent pas le même résultat qu'une. `PUT /config = {x:1}` est un interrupteur.
`POST /orders` est un bouton poussoir : dix appels, dix commandes.

### 3.2 Pourquoi ça compte vraiment

C'est la propriété qui décide si une bibliothèque a le droit de **rejouer automatiquement** une requête
après un timeout. `urllib3` / `requests` ne rejouent par défaut que les méthodes idempotentes
(`DELETE, GET, HEAD, OPTIONS, PUT, TRACE`) — `POST` est exclu de `allowed_methods`. nginx en reverse proxy
bascule par défaut sur un autre backend sur `error` **et** `timeout` (`proxy_next_upstream error timeout`),
mais **refuse de rejouer une requête non idempotente** (`POST`, `PATCH`, `LOCK`) déjà transmise à l'amont —
il faut ajouter explicitement le paramètre `non_idempotent` pour l'y forcer. Même logique, autre mécanisme :
ce n'est pas la nature de l'erreur qui protège, c'est la méthode.

> ❓ **RETIENS ÇA** — `DELETE` renvoie 404 au deuxième appel. Est-il encore idempotent ?
> <details><summary>→ réponse</summary><br><b>Oui.</b> L'idempotence porte sur l'<b>état du serveur</b>, pas sur le code de réponse. Après un ou dix <code>DELETE /job/42</code>, la ressource est absente : même état final. Ce qui casse l'idempotence, c'est <code>POST</code>, qui crée une ressource de plus à chaque appel.</details>

> ⚠️ **PIÈGE** — Une API qui fait `POST /increment` n'est pas rejouable, mais une API qui fait
> `POST /orders` avec un en-tête `Idempotency-Key: <uuid>` **le redevient** : le serveur mémorise la clé
> et renvoie la réponse d'origine au lieu de re-créer. C'est le motif standard (Stripe, AWS
> `ClientRequestToken`) et la bonne réponse en entretien quand on te demande « comment rends-tu un
> paiement sûr à rejouer ? ».

---

## 4. Les codes de statut, famille par famille

Le premier chiffre porte toute l'information de routage d'erreur. Apprends les familles d'abord, les
codes ensuite.

```
 1xx  ── j'ai reçu, continue           (informationnel, rare)
 2xx  ── c'est bon                     (succès)
 3xx  ── va voir ailleurs / t'as déjà  (redirection ET cache)
 4xx  ── TU t'es trompé                (erreur client — ne rejoue pas tel quel)
 5xx  ── JE me suis trompé             (erreur serveur — rejouer peut marcher)
```

> 🧠 **MÉMO** — **4 = ta faute, 5 = ma faute.** Un client bien écrit **rejoue** les 5xx (avec backoff)
> et **ne rejoue jamais** un 4xx, sauf 429 (attends) et 408 (timeout de requête).

### 4.1 Les codes réellement utiles

| Code | Nom | Le cas réel où tu le vois |
|---|---|---|
| **100** | Continue | `curl` envoie `Expect: 100-continue` sur un corps > 1 024 o et attend **1 s** max |
| **101** | Switching Protocols | la réponse à un upgrade **WebSocket** |
| **103** | Early Hints | le remplaçant du server push HTTP/2 |
| **200** | OK | — |
| **201** | Created | création, avec `Location:` vers la ressource créée |
| **202** | Accepted | traitement **asynchrone** accepté : la bonne réponse pour un job long |
| **204** | No Content | succès sans corps (`DELETE`, `PUT` de config) |
| **206** | Partial Content | réponse à un `Range:` — téléchargement parallèle S3 |
| **301** | Moved Permanently | déplacement définitif, **mis en cache par le navigateur, très difficile à annuler** |
| **302** | Found | temporaire, historiquement transforme le `POST` en `GET` |
| **303** | See Other | « va chercher le résultat là-bas en GET » (motif POST-redirect-GET) |
| **304** | Not Modified | revalidation réussie : **pas de corps**, ton cache est bon |
| **307** | Temporary Redirect | comme 302 mais **conserve la méthode et le corps** |
| **308** | Permanent Redirect | comme 301 mais **conserve la méthode et le corps** |
| **400** | Bad Request | requête malformée (JSON invalide, en-tête cassé) |
| **401** | Unauthorized | mal nommé : **non authentifié**. Doit renvoyer `WWW-Authenticate` |
| **403** | Forbidden | authentifié mais **pas le droit**. Aussi : S3 sur une signature expirée |
| **404** | Not Found | — |
| **405** | Method Not Allowed | doit renvoyer `Allow: GET, POST` |
| **409** | Conflict | conflit d'état : écriture concurrente, version obsolète |
| **412** | Precondition Failed | ton `If-Match` ne colle plus → verrouillage optimiste |
| **413** | Content Too Large | corps trop gros (`client_max_body_size 1m` par défaut sur nginx) |
| **415** | Unsupported Media Type | mauvais `Content-Type` |
| **422** | Unprocessable Content | syntaxe bonne, sémantique invalide (validation métier) |
| **429** | Too Many Requests | quota. Lis `Retry-After` **avant** de coder ton backoff |
| **499** | (nginx) Client Closed Request | **le client a raccroché le premier** — souvent ton timeout, pas le serveur |
| **500** | Internal Server Error | l'application a explosé |
| **501** | Not Implemented | méthode inconnue du serveur |
| **502** | Bad Gateway | le proxy n'a **pas pu parler** au backend (mort, refus, réponse illisible) |
| **503** | Service Unavailable | surcharge / maintenance. S3 : `SlowDown`. Souvent avec `Retry-After` |
| **504** | Gateway Timeout | le backend **n'a pas répondu à temps** — ALB 60 s, nginx `proxy_read_timeout 60s` |

> ❓ **RETIENS ÇA** — Différence entre 502 et 504 ?
> <details><summary>→ réponse</summary><br><b>502</b> : le proxy a joint (ou tenté de joindre) le backend et n'a rien obtenu d'exploitable — connexion refusée, backend mort, réponse malformée. <b>504</b> : la connexion au backend a réussi, mais la réponse n'est pas arrivée dans le délai imparti. 502 = « il ne répond pas au téléphone », 504 = « il a décroché et n'a rien dit pendant 60 s ».</details>

> ❓ **RETIENS ÇA** — Différence entre 301/302 et 308/307 ?
> <details><summary>→ réponse</summary><br>Les anciens (301/302) autorisent — et en pratique déclenchent — la transformation d'un <code>POST</code> en <code>GET</code> avec perte du corps. Les nouveaux (308/307) <b>préservent méthode et corps</b>. Si tu rediriges une API, utilise 307/308 ; sinon un <code>POST</code> devient silencieusement un <code>GET</code> et le corps disparaît.</details>

> ⚠️ **PIÈGE** — **401 = non authentifié, 403 = non autorisé.** Le nom `Unauthorized` du 401 est une erreur
> historique de la RFC, gravée dans le marbre. Sur S3, un 403 signifie très souvent une signature expirée
> ou une horloge décalée, pas un vrai problème de droits.

---

## 5. Les en-têtes qui comptent vraiment

| En-tête | Sens | Détail à retenir |
|---|---|---|
| `Host` | nom demandé | **obligatoire en HTTP/1.1**, c'est lui qui permet le virtual hosting |
| `Content-Type` | type du corps | `application/json`, `application/grpc+proto`, `text/event-stream` |
| `Accept` | ce que je sais lire | négociation de contenu, avec facteurs `q=` |
| `Accept-Encoding` | compressions supportées | `gzip, br, zstd` |
| `Authorization` | identité | `Bearer <jwt>`, `Basic base64(user:pass)`, `AWS4-HMAC-SHA256 ...` |
| `Range` / `Content-Range` | portion | `Range: bytes=0-1048575` → 206. La base du téléchargement parallèle |
| `Connection` | gestion du lien | `keep-alive` / `close`. **Interdit en HTTP/2 et 3** |
| `Retry-After` | attends | secondes ou date HTTP. À respecter, pas à ignorer |
| `X-Forwarded-For` | IP client d'origine | ajoutée par chaque proxy, **falsifiable** si tu ne fais pas confiance au premier saut |
| `X-Request-Id` / `traceparent` | corrélation | `traceparent` est le standard W3C, celui qu'OpenTelemetry propage |
| `Vary` | axes de variation du cache | oublié = poison de cache garanti (voir 6.4) |

> 🧠 **MÉMO** — Les en-têtes se rangent en 4 sacs : **qui je suis** (`Host`, `Authorization`,
> `User-Agent`), **ce que je veux** (`Accept*`, `Range`), **comment on transporte** (`Content-Length`,
> `Transfer-Encoding`, `Connection`), **combien de temps on garde** (`Cache-Control`, `ETag`, `Vary`).

---

## 6. Le cache HTTP

### 6.1 Le problème

Un pipeline qui interroge le même référentiel de métadonnées 200 fois par minute paie 200 fois le
round-trip, 200 fois le calcul serveur, 200 fois la bande passante. Comment éviter de redemander ce
qu'on a déjà, **sans risquer de travailler sur du périmé** ?

Deux stratégies, et il faut connaître la différence :

```
   FRAÎCHEUR (freshness)              VALIDATION
   ─────────────────────              ──────────
   "valable 300 s"                    "j'ai la version a3f5c9, encore bonne ?"
   → ZÉRO requête réseau              → 1 requête, mais réponse 304 sans corps
   Cache-Control: max-age=300         ETag / If-None-Match
                                      Last-Modified / If-Modified-Since
```

La fraîcheur économise le **round-trip entier**. La validation n'économise que le **corps** — mais elle
est sûre.

### 6.2 `Cache-Control`, directive par directive

| Directive | Effet |
|---|---|
| `max-age=N` | fraîche pendant N secondes (pour tous les caches) |
| `s-maxage=N` | idem mais **uniquement pour les caches partagés** (CDN, proxy) ; écrase `max-age` |
| `no-cache` | stocke, mais **revalide obligatoirement avant chaque usage**. Ce n'est PAS « ne cache pas » |
| `no-store` | **ne stocke rien**, nulle part. Le vrai « ne cache pas » |
| `private` | seul le cache du navigateur peut stocker (réponse personnalisée) |
| `public` | un cache partagé peut stocker, même avec `Authorization` |
| `must-revalidate` | une fois périmée, interdiction de servir en mode dégradé |
| `immutable` | ne revalide jamais, même sur F5 (assets versionnés par hash) |
| `stale-while-revalidate=N` | sers le périmé jusqu'à N s pendant que tu rafraîchis en arrière-plan |

> ❓ **RETIENS ÇA** — Différence entre `no-cache` et `no-store` ?
> <details><summary>→ réponse</summary><br><code>no-cache</code> = « tu peux le garder, mais tu dois me demander à chaque fois s'il est encore bon » (revalidation systématique, réponse 304 possible). <code>no-store</code> = « n'écris ça nulle part, ni disque ni mémoire ». Pour un relevé bancaire ou un jeton, c'est <code>no-store</code>. Le nom <code>no-cache</code> est le piège le plus fréquent d'HTTP.</details>

### 6.3 ETag et revalidation

L'`ETag` est une empreinte opaque de la représentation. Le client la renvoie dans `If-None-Match`.

```
   1er appel                          2e appel (après expiration)
   ─────────                          ───────────────────────────
   GET /datasets                      GET /datasets
                                      If-None-Match: "a3f5c9"
   ← 200 OK                           ← 304 Not Modified
     ETag: "a3f5c9"                     ETag: "a3f5c9"
     Content-Length: 1523               (aucun corps — 0 octet de payload)
```

- `ETag: "a3f5c9"` = **fort** : octet pour octet identique.
- `ETag: W/"a3f5c9"` = **faible** : sémantiquement équivalent (une pub qui change, un timestamp interne).
- `Last-Modified` + `If-Modified-Since` : même principe, mais granularité **à la seconde** — deux
  modifications dans la même seconde deviennent invisibles. L'ETag est strictement supérieur.

Le même ETag sert au **verrouillage optimiste en écriture** : `If-Match: "a3f5c9"` sur un `PUT` →
**412 Precondition Failed** si quelqu'un a modifié entre-temps. C'est du *compare-and-swap* HTTP, et c'est
exactement ce que fait S3 avec `If-Match` / `x-amz-copy-source-if-match`.

> ❓ **RETIENS ÇA** — Que renvoie le serveur quand `If-None-Match` correspond toujours ?
> <details><summary>→ réponse</summary><br><b>304 Not Modified</b>, <b>sans corps</b>. Le client réutilise sa copie locale. Le round-trip est payé, mais pas le transfert ni le calcul.</details>

### 6.4 `Vary`, le poison de cache

Une même URL peut avoir plusieurs représentations : `gzip` ou non, français ou anglais, JSON ou CSV.
`Vary` liste les en-têtes de **requête** qui changent la réponse.

```
Vary: Accept-Encoding, Accept-Language
```

Sans `Vary: Accept-Encoding`, un CDN peut servir une réponse gzip à un client qui n'a pas annoncé gzip →
octets illisibles. Avec `Vary: User-Agent`, le taux de succès du cache s'effondre (des milliers de
variantes). Avec `Vary: *`, rien n'est jamais mis en cache.

> ⚠️ **PIÈGE** — Une réponse personnalisée (donc dépendante de `Authorization` ou d'un cookie) mise en
> cache **partagé** sans `private` fait fuiter les données d'un utilisateur à un autre. C'est une des
> failles de CDN les plus fréquentes. Règle : contenu personnalisé → `Cache-Control: private, no-store`.

---

## 7. Cookies : rendre l'état possible

Un cookie, c'est le serveur qui écrit une note et demande au client de la lui rendre à chaque visite.

```
← Set-Cookie: session=abc123; Domain=exemple.fr; Path=/; Max-Age=3600;
              Secure; HttpOnly; SameSite=Lax
→ Cookie: session=abc123
```

| Attribut | Effet |
|---|---|
| `Domain` | portée. **Absent = hôte exact uniquement** (plus strict, et c'est le bon défaut) |
| `Path` | préfixe de chemin. **N'est pas une frontière de sécurité** |
| `Expires` / `Max-Age` | durée. Sans les deux : cookie de session, mort à la fermeture |
| `Secure` | envoyé **uniquement en HTTPS** |
| `HttpOnly` | **invisible depuis JavaScript** → protège du vol par XSS |
| `SameSite=Strict` | jamais envoyé sur une navigation venue d'un autre site |
| `SameSite=Lax` | **valeur par défaut** des navigateurs modernes : envoyé sur navigation GET de haut niveau |
| `SameSite=None` | envoyé partout — **exige `Secure`**, sinon rejeté |

Taille : ~**4 096 octets** par cookie (nom + valeur + attributs), une cinquantaine par domaine. Les
cookies partent sur **chaque** requête du domaine, images comprises : 3 Ko de cookies × 80 ressources =
240 Ko d'en-têtes montants par page.

> ⚠️ **PIÈGE** — Les cookies **ignorent le port** et suivent des règles de domaine plus larges que
> l'origine. `http://exemple.fr:8080` et `https://exemple.fr` sont deux origines différentes pour CORS,
> mais partagent les cookies. Le modèle de sécurité des cookies et celui des origines ne coïncident pas :
> c'est la source de la moitié des vulnérabilités web.

---

## 8. CORS : pourquoi ton `fetch()` échoue alors que `curl` marche

### 8.1 Le problème

Le navigateur applique la **politique de même origine** : un script chargé depuis `app.exemple.fr` ne peut
pas lire la réponse d'une requête vers `api.autre.fr`. Sinon, n'importe quel site pourrait, depuis ton
onglet, lire ta boîte mail — avec **tes cookies**, qui partent automatiquement.

Une **origine** = `schéma + hôte + port`. Trois éléments, tous les trois doivent coïncider.

```
   https://app.exemple.fr:443/x   contre :
   ┌────────────────────────────────────────────────┬───────────┐
   │ https://app.exemple.fr/y                       │ MÊME      │
   │ http://app.exemple.fr/x     (schéma différent) │ DIFFÉRENTE│
   │ https://api.exemple.fr/x    (hôte différent)   │ DIFFÉRENTE│
   │ https://app.exemple.fr:8443 (port différent)   │ DIFFÉRENTE│
   └────────────────────────────────────────────────┴───────────┘
```

CORS est le mécanisme par lequel le serveur **déclare des exceptions**.

### 8.2 Requête simple contre pré-vol

Une requête est « simple » (pas de pré-vol) si : méthode `GET`, `HEAD` ou `POST`, **et** `Content-Type`
parmi `application/x-www-form-urlencoded`, `multipart/form-data`, `text/plain`, **et** aucun en-tête
personnalisé.

Dès que tu envoies du `application/json` ou un `Authorization` custom — c'est-à-dire **toujours**, en
pratique — le navigateur déclenche un **pré-vol** :

```
   Navigateur                                   Serveur API
       │                                             │
       │  OPTIONS /v1/jobs  HTTP/1.1                 │   ← PRÉ-VOL
       │  Origin: https://app.exemple.fr             │
       │  Access-Control-Request-Method: POST        │
       │  Access-Control-Request-Headers: content-type, authorization
       │────────────────────────────────────────────►│
       │  204 No Content                             │
       │  Access-Control-Allow-Origin: https://app.exemple.fr
       │  Access-Control-Allow-Methods: POST, GET    │
       │  Access-Control-Allow-Headers: content-type, authorization
       │  Access-Control-Max-Age: 600                │   ← cache du pré-vol
       │◄────────────────────────────────────────────│
       │                                             │
       │  POST /v1/jobs  (la vraie requête)          │
       │────────────────────────────────────────────►│
```

Points durs :
- `Access-Control-Allow-Credentials: true` (cookies) est **incompatible avec `Allow-Origin: *`**. Il faut
  renvoyer l'origine exacte, et donc ajouter `Vary: Origin`.
- Pour lire un en-tête de réponse non standard en JS, le serveur doit l'exposer :
  `Access-Control-Expose-Headers: X-Total-Count`.
- `Access-Control-Max-Age` est **plafonné par le navigateur** (Chrome : 7 200 s).

> ❓ **RETIENS ÇA** — CORS protège-t-il le serveur ?
> <details><summary>→ réponse</summary><br><b>Non.</b> CORS est appliqué <b>par le navigateur</b>, et uniquement par lui. <code>curl</code>, Python et n'importe quel client hors navigateur ignorent complètement CORS. CORS protège l'<b>utilisateur</b> contre un site tiers qui exploiterait ses cookies. La sécurité du serveur, c'est l'authentification et l'autorisation, pas CORS.</details>

> ⚠️ **PIÈGE** — Un backend qui plante en **500** ne renvoie généralement plus les en-têtes CORS. Le
> navigateur affiche alors « blocked by CORS policy » et masque le vrai problème. Devant une erreur CORS,
> **rejoue la requête en `curl -v`** : si tu vois un 500, ton problème n'est pas CORS.

---

## 9. HTTP/1.1 : keep-alive, pipelining, et l'échec

### 9.1 Le coût d'une connexion par requête

HTTP/1.0 fermait la connexion après chaque réponse. Sur une page à 80 ressources, c'est 80 handshakes
TCP (+ 80 handshakes TLS). HTTP/1.1 rend **`keep-alive` le défaut** : la connexion reste ouverte, on
enchaîne les requêtes. `Connection: close` pour la fermer explicitement.

```
   SANS keep-alive (HTTP/1.0)            AVEC keep-alive (HTTP/1.1)
   SYN,SYN-ACK,ACK  [1 RTT]              SYN,SYN-ACK,ACK      [1 RTT]
   GET /a → réponse [1 RTT]              GET /a → réponse     [1 RTT]
   FIN...                                GET /b → réponse     [1 RTT]
   SYN,SYN-ACK,ACK  [1 RTT]              GET /c → réponse     [1 RTT]
   GET /b → réponse [1 RTT]              ...
   → 2 RTT par ressource                 → 1 RTT par ressource, handshake amorti
```

### 9.2 Le pipelining et pourquoi il est mort

Idée : envoyer `GET /a`, `GET /b`, `GET /c` **sans attendre** les réponses. Le serveur doit répondre
**dans le même ordre**. Et là, le drame :

```
   Client :   GET /a (une requête lente : 2 s)
              GET /b (rapide : 5 ms)
              GET /c (rapide : 5 ms)

   Serveur :  ┌─────────── réponse /a ──────────┐ /b │ /c │
              0                                2s   2s   2s
                                                ▲
                          /b et /c étaient prêts depuis 2 secondes.
                          Ils attendent /a. C'est le HEAD-OF-LINE BLOCKING.
```

**Analogie.** Une caisse de supermarché unique où l'on doit servir les clients dans l'ordre d'arrivée :
le monsieur avec 3 chariots et un chèque bloque les huit personnes derrière qui ont une bouteille d'eau.

Ajoute des proxys buggés qui perdent le compte des réponses, et le pipelining est désactivé **par défaut
dans tous les navigateurs**. La parade réelle : ouvrir **6 connexions TCP par origine** (limite de fait des
navigateurs) et, quand ça ne suffisait pas, le *domain sharding* (`img1.exemple.fr`, `img2.exemple.fr`…) —
un bricolage qui multiplie handshakes et handshakes TLS.

> ❓ **RETIENS ÇA** — Pourquoi le pipelining HTTP/1.1 a-t-il échoué ?
> <details><summary>→ réponse</summary><br>Parce que les réponses doivent revenir <b>dans l'ordre des requêtes</b>. Une réponse lente bloque toutes les suivantes, même déjà prêtes : c'est le <b>head-of-line blocking applicatif</b>. Ajouté à des proxys intermédiaires qui géraient mal l'enchaînement, ça l'a rendu inutilisable — tous les navigateurs le désactivent.</details>

> 🧠 **MÉMO** — **HTTP/1.1 = une file d'attente unique par connexion.** Toute la suite de l'histoire
> d'HTTP consiste à casser cette file en plusieurs files indépendantes, et à descendre ce découpage de
> plus en plus bas dans la pile : d'abord dans HTTP (h2), puis dans le transport (h3/QUIC).

---

## 10. HTTP/2 : le binaire et le multiplexage

HTTP/2 (RFC 7540, 2015, remplacé par la RFC 9113) **ne change pas la sémantique** : mêmes méthodes, mêmes
codes, mêmes en-têtes. Il change **l'encodage et le transport**.

### 10.1 Trames et flux

Tout devient une **trame binaire** de 9 octets d'en-tête suivie d'une charge utile :

```
    0                   1                   2                   3
    0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
   +-----------------------------------------------+---------------+
   |                 Length (24 bits)              |   Type (8)    |
   +---------------+-----------------------------------------------+
   |   Flags (8)   |R|        Stream Identifier (31 bits)          |
   +---------------+-----------------------------------------------+
   |                     Payload (Length octets)                   |
   +---------------------------------------------------------------+
        9 octets d'en-tête au total
```

| Type | Nom | Rôle |
|---|---|---|
| `0x0` | DATA | le corps |
| `0x1` | HEADERS | les en-têtes, compressés HPACK |
| `0x3` | RST_STREAM | annule **un** flux sans tuer la connexion |
| `0x4` | SETTINGS | paramètres de connexion |
| `0x5` | PUSH_PROMISE | server push |
| `0x6` | PING | mesure de RTT / keepalive |
| `0x7` | GOAWAY | arrêt propre : « je ne prends plus de nouveaux flux au-dessus de l'ID N » |
| `0x8` | WINDOW_UPDATE | contrôle de flux |

Un **flux** (stream) est une conversation requête/réponse indépendante, identifiée par un entier sur
31 bits. **IDs impairs = ouverts par le client, pairs = par le serveur, 0 = la connexion elle-même.**

```
   UNE connexion TCP, TROIS flux entrelacés :

   ─►│H1│D1│H3│D5│D1│H5│D3│D5│D1│D3│─►     H = HEADERS, D = DATA
      └─flux1─┘  └─flux5 ┘
            └─flux3─┘
   Les trames de flux différents s'interleavent librement.
   Une réponse lente sur le flux 1 n'empêche PAS le flux 3 de finir.
```

### 10.2 Valeurs par défaut à connaître

| Paramètre | Défaut | Conséquence |
|---|---|---|
| `SETTINGS_HEADER_TABLE_SIZE` | **4 096 o** | taille de la table dynamique HPACK |
| `SETTINGS_MAX_CONCURRENT_STREAMS` | non borné par la RFC, **≥ 100 recommandé** ; nginx : **128** | plafond de requêtes en vol |
| `SETTINGS_INITIAL_WINDOW_SIZE` | **65 535 o** | ⚠️ le plafond de débit longue distance (voir 24.2) |
| `SETTINGS_MAX_FRAME_SIZE` | **16 384 o** | taille max d'une trame |

La connexion s'ouvre par un **préambule client de 24 octets** : `PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n`, choisi
pour faire planter proprement tout intermédiaire HTTP/1.x qui ne comprendrait pas.

### 10.3 HPACK : ne plus répéter 700 octets

Les en-têtes d'une API interne sont quasi identiques d'une requête à l'autre. HPACK (RFC 7541) exploite ça :

- une **table statique de 61 entrées** prédéfinies (`:method: GET` = index 2, `:path: /` = index 4…) ;
- une **table dynamique** partagée entre les deux extrémités : la première fois, `authorization: Bearer …`
  est envoyé en entier et **indexé** ; ensuite, on n'envoie **que son index** — 1 à 2 octets ;
- un codage **Huffman** pour les littéraux restants (≈ 30 % de gain).

En HTTP/2, les en-têtes sont en **minuscules obligatoires**, et les métadonnées de la ligne de requête
deviennent des **pseudo-en-têtes** commençant par `:` — `:method`, `:scheme`, `:authority`, `:path` pour
la requête, `:status` pour la réponse. `Connection`, `Keep-Alive`, `Transfer-Encoding` et `Upgrade` sont
**interdits**.

> ❓ **RETIENS ÇA** — Que fait HPACK, concrètement, à la deuxième requête d'une connexion ?
> <details><summary>→ réponse</summary><br>Il n'envoie plus les en-têtes identiques : il envoie leurs <b>index</b> dans la table (statique de 61 entrées, ou dynamique construite au fil de la connexion). Un bloc d'en-têtes de ~700 octets tombe à quelques dizaines d'octets. Les littéraux restants sont codés en Huffman.</details>

> ⚠️ **PIÈGE** — HPACK impose un **état partagé et ordonné** entre les deux bouts : si une trame HEADERS
> arrive dans le désordre, la table dynamique diverge et la connexion est irrécupérable. C'est
> précisément pour ça que HTTP/3 ne peut **pas** utiliser HPACK et a dû inventer QPACK.

### 10.4 Server push : la fonctionnalité morte

L'idée : le serveur envoie `PUSH_PROMISE` pour du CSS que le client n'a pas encore demandé. En pratique,
le serveur ignore ce que le client a déjà en cache et gaspille de la bande passante. **Chrome l'a retiré
en 2022.** Le remplaçant est **`103 Early Hints`** : une réponse informationnelle envoyée avant la vraie
réponse, avec des `Link: </style.css>; rel=preload` — le client décide.

### 10.5 Ce que HTTP/2 ne résout pas

HTTP/2 supprime le head-of-line blocking **applicatif**. Mais toutes les trames voyagent dans **une seule
connexion TCP**, et TCP livre **dans l'ordre**. Un segment perdu bloque la remise de **tout ce qui suit**,
tous flux confondus.

```
   Segment TCP perdu ─┐
   ─►│D1│D3│ ✗ │D5│D3│D1│      TCP garde D5, D3, D1 en tampon noyau
                                jusqu'à retransmission du segment perdu.
   L'application ne reçoit RIEN, même pour les flux 3 et 5 intacts.
   → HEAD-OF-LINE BLOCKING AU NIVEAU TRANSPORT.
```

Pire qu'en HTTP/1.1 sur réseau très dégradé : là où 6 connexions TCP isolaient les pertes, une seule
connexion les propage à tout le monde.

> ❓ **RETIENS ÇA** — HTTP/2 supprime-t-il le head-of-line blocking ?
> <details><summary>→ réponse</summary><br>Il supprime celui de la <b>couche application</b> (les réponses ne sont plus obligées de revenir dans l'ordre). Il <b>ne supprime pas</b> celui de <b>TCP</b> : une seule perte de segment gèle la remise de tous les flux multiplexés, parce que TCP livre strictement dans l'ordre. C'est la raison d'être de HTTP/3.</details>

---

## 11. HTTP/3 et QUIC : descendre le multiplexage dans le transport

### 11.1 L'idée

Puisque le problème est dans TCP, on change de transport. **QUIC** (RFC 9000) est un transport fiable,
ordonné **par flux**, construit **sur UDP**, avec TLS 1.3 **intégré** au protocole. HTTP/3 (RFC 9114) est
la mise en correspondance d'HTTP sur QUIC.

```
   HTTP/2                         HTTP/3
   ┌─────────────┐                ┌─────────────┐
   │   HTTP/2    │                │   HTTP/3    │
   ├─────────────┤                ├─────────────┤
   │   TLS 1.2/3 │                │    QUIC     │  ← flux + fiabilité + TLS 1.3
   ├─────────────┤                ├─────────────┤     dans une seule couche
   │     TCP     │                │     UDP     │
   ├─────────────┤                ├─────────────┤
   │      IP     │                │      IP     │
   └─────────────┘                └─────────────┘
```

### 11.2 Ce que ça change concrètement

| Point | HTTP/2 sur TCP+TLS | HTTP/3 sur QUIC |
|---|---|---|
| Handshake à froid | 1 RTT (TCP) + 1 RTT (TLS 1.3) = **2 RTT** | **1 RTT** (fusionné) |
| Reprise de session | 1 + 0 = 1 RTT | **0-RTT** possible |
| Perte de paquet | bloque **tous** les flux | bloque **seulement** le flux concerné |
| Changement de réseau (Wi-Fi→4G) | connexion morte, tout à refaire | **Connection ID** → migration transparente |
| Compression d'en-têtes | HPACK | **QPACK** (RFC 9204, table statique de **99** entrées, flux d'encodeur/décodeur séparés) |
| Où vit le code | noyau (TCP) | **espace utilisateur** → déployable sans mise à jour d'OS, mais **plus coûteux en CPU** |
| Chiffrement | en-têtes TCP en clair | **presque tout chiffré**, y compris les numéros de paquet |

Le **Connection ID** est l'idée la plus élégante : une connexion QUIC n'est pas identifiée par le
quadruplet IP/ports (comme TCP) mais par un identifiant explicite jusqu'à 20 octets. Change de réseau,
change d'IP : la connexion survit. Ton téléphone qui passe du Wi-Fi à la 4G en plein téléchargement ne
recommence pas.

Découverte : le serveur annonce `Alt-Svc: h3=":443"; ma=86400` sur sa réponse HTTP/2, ou publie un
enregistrement DNS **HTTPS (type 65)** — vu en R07.

> ❓ **RETIENS ÇA** — Sur quel transport et quel port tourne HTTP/3 ?
> <details><summary>→ réponse</summary><br><b>QUIC sur UDP, port 443</b> (par convention, comme HTTPS). C'est ce qui explique la première panne classique : un pare-feu d'entreprise qui bloque l'UDP sortant sauf le 53. Le client bascule alors silencieusement en HTTP/2 — ou reste bloqué s'il n'a pas de repli.</details>

> ⚠️ **PIÈGE** — Le **0-RTT** de QUIC (et de TLS 1.3) est **rejouable par un attaquant** : les données
> précoces ne sont pas protégées contre le rejeu. On ne l'utilise donc que pour des requêtes
> **idempotentes** — jamais un `POST /transfer`. Retiens le lien : 0-RTT ↔ idempotence (section 3).

> 🧠 **MÉMO** — **HTTP/2 = plusieurs files dans un seul camion. HTTP/3 = plusieurs camions sur la même
> route.** Si le camion unique tombe en panne (perte TCP), tout s'arrête. Si un camion sur dix cale,
> les neuf autres continuent.

---

## 12. Le head-of-line blocking, à tous les étages

C'est le fil rouge du module et une question d'entretien quasi certaine. Le même phénomène apparaît à
cinq niveaux différents.

```
 NIVEAU              MÉCANISME DU BLOCAGE                        RÉSOLU PAR
 ────────────────────────────────────────────────────────────────────────────────
 HTTP/1.1 sans       une seule requête en vol par connexion      keep-alive + 6 conn.
 pipelining                                                       (contournement)

 HTTP/1.1 avec       les réponses doivent revenir DANS L'ORDRE   HTTP/2 (flux)
 pipelining

 HTTP/2 (TCP)        une perte de segment gèle TOUS les flux     HTTP/3 (QUIC)
                     (TCP livre dans l'ordre)

 TLS sur TCP         un enregistrement TLS doit être COMPLET     enregistrements
                     pour être déchiffré                        plus petits

 QUIC, dans un flux  l'ordre reste garanti À L'INTÉRIEUR         rien : c'est voulu
                     d'un même flux
```

Et le même schéma mental resservira ailleurs dans ton métier : une **partition Kafka** bloque de la même
façon (un message empoisonné bloque tous les suivants de la partition, pas des autres partitions), et une
tâche Spark lente bloque son étage entier. **Head-of-line blocking = ordre imposé + ressource partagée.**
Pour le supprimer : casse l'ordre, ou casse le partage.

> ❓ **RETIENS ÇA** — HTTP/3 supprime-t-il *tout* le head-of-line blocking ?
> <details><summary>→ réponse</summary><br>Non. Il le supprime <b>entre flux</b>. À l'<b>intérieur</b> d'un flux QUIC, l'ordre reste garanti : un octet perdu au milieu d'une réponse bloque toujours la suite de <b>cette</b> réponse. C'est nécessaire — une réponse HTTP doit arriver dans l'ordre.</details>

---

## 13. TLS : le problème, et les deux cryptographies

### 13.1 Trois garanties, pas une

Sans TLS, tout ce qui circule est lisible et modifiable par chaque équipement traversé — ton Wi-Fi, ton
FAI, chaque routeur, chaque proxy transparent. TLS apporte **trois** choses, et il faut les nommer
séparément :

| Garantie | Réponse à | Mécanisme |
|---|---|---|
| **Confidentialité** | « qui peut lire ? » | chiffrement symétrique (AES-GCM, ChaCha20) |
| **Intégrité** | « quelqu'un a-t-il modifié ? » | AEAD (le tag d'authentification) |
| **Authentification** | « à qui je parle vraiment ? » | certificat X.509 + signature |

L'authentification est la plus importante et la plus oubliée. Chiffrer avec un attaquant ne sert à rien.
C'est exactement pourquoi désactiver la vérification (`verify=False`, `curl -k`, `InsecureSkipVerify`)
détruit **toute** la sécurité tout en gardant le cadenas — et pourquoi c'est la mauvaise réponse
universelle en entretien.

### 13.2 Symétrique et asymétrique : pourquoi les deux

| | Symétrique (AES-256-GCM) | Asymétrique (RSA-2048, ECDSA P-256) |
|---|---|---|
| Clés | une seule, partagée | une paire : publique / privée |
| Vitesse | ~1-10 Go/s (AES-NI matériel) | ~1 000 à 10 000 opérations/s |
| Écart | **plusieurs ordres de grandeur plus rapide** | lent |
| Problème | comment partager la clé ? | trop lent pour un flux de données |

**Analogie.** L'asymétrique est le **coffre-fort blindé** de l'entrée : lent à manœuvrer, mais on peut y
déposer sans avoir la clé de sortie. Le symétrique est le **coursier rapide** de l'intérieur. TLS utilise
le coffre une seule fois, au début, pour transmettre la clé du coursier — puis tout passe par le coursier.

> 🧠 **MÉMO** — **TLS = asymétrique pour se mettre d'accord, symétrique pour bosser.** Le handshake est
> tout ce qui coûte cher ; c'est pour ça que réutiliser une connexion TLS (keep-alive, pool) est le
> premier levier de performance d'un client HTTP.

### 13.3 La couche d'enregistrement

Sous les messages du handshake et sous HTTP, TLS a une couche de cadrage minimaliste :

```
   ┌────────┬────────────┬──────────┬─────────────────────────┐
   │  Type  │  Version   │ Longueur │        Charge utile     │
   │  1 o   │    2 o     │   2 o    │      ≤ 16 384 octets    │
   └────────┴────────────┴──────────┴─────────────────────────┘
     20 = change_cipher_spec   22 = handshake
     21 = alert                23 = application_data
   → 5 octets d'en-tête. Taille max d'un enregistrement en clair : 2¹⁴ = 16 384 o.
```

---

## 14. Le handshake TLS 1.2, message par message

Version ECDHE (la seule encore acceptable en 1.2). **Coût : 2 RTT avant le premier octet applicatif.**

```
   CLIENT                                                    SERVEUR
     │                                                          │
     │──── ClientHello ────────────────────────────────────────►│  RTT 1
     │     • client_random (32 o)                               │
     │     • liste de suites cryptographiques                    │
     │     • extensions : SNI, ALPN, supported_groups,           │
     │       signature_algorithms                                │
     │                                                          │
     │◄─── ServerHello ─────────────────────────────────────────│
     │     • server_random (32 o), suite CHOISIE                │
     │◄─── Certificate  (chaîne : feuille + intermédiaires)     │
     │◄─── ServerKeyExchange (clé publique ECDHE + SIGNATURE)   │
     │◄─── [CertificateRequest]   ← seulement en mTLS           │
     │◄─── ServerHelloDone                                       │
     │                                                          │
     │──── [Certificate]  ← mTLS ──────────────────────────────►│  RTT 2
     │──── ClientKeyExchange (clé publique ECDHE du client) ───►│
     │──── [CertificateVerify]  ← mTLS, APRÈS ClientKeyExchange►│
     │──── ChangeCipherSpec ───────────────────────────────────►│
     │──── Finished (chiffré, hash de TOUT le handshake) ──────►│
     │                                                          │
     │◄─── ChangeCipherSpec ────────────────────────────────────│
     │◄─── Finished ────────────────────────────────────────────│
     │                                                          │
     │════ application_data (HTTP) ════════════════════════════►│  enfin.
```

Ce qu'il faut comprendre, pas seulement mémoriser :

1. Les deux `random` (32 octets chacun) garantissent que **deux handshakes ne produisent jamais les mêmes
   clés**, même avec les mêmes parties.
2. Le `ServerKeyExchange` porte une **signature** faite avec la clé privée du certificat. C'est **là** que
   le serveur prouve qu'il possède la clé privée — pas dans l'envoi du certificat, qui est public.
3. Client et serveur calculent **chacun de leur côté** le secret partagé ECDHE, puis dérivent le
   `master_secret`, puis les clés de session. Le secret ne circule **jamais** sur le fil.
4. `Finished` contient un hash de **tous** les messages précédents : si un attaquant a modifié un octet du
   handshake (par exemple pour forcer une suite faible), les hash divergent et la connexion casse. C'est
   la protection contre le *downgrade*.

> ❓ **RETIENS ÇA** — Où, dans le handshake TLS, le serveur prouve-t-il qu'il possède la clé privée ?
> <details><summary>→ réponse</summary><br>Dans la <b>signature</b> qu'il produit : <code>ServerKeyExchange</code> en TLS 1.2, <code>CertificateVerify</code> en TLS 1.3. L'envoi du <code>Certificate</code> ne prouve rien — un certificat est public, n'importe qui peut le copier. Ce qui authentifie, c'est la signature d'un contenu frais (incluant les aléas) avec la clé privée correspondante.</details>

---

## 15. Le handshake TLS 1.3 : un RTT, et le grand ménage

TLS 1.3 (RFC 8446, 2018) fait le pari suivant : au lieu de **négocier** le groupe de clés puis de
l'utiliser, le client **devine** et envoie sa part de clé dès le premier message.

```
   CLIENT                                                    SERVEUR
     │──── ClientHello ────────────────────────────────────────►│
     │     • key_share  ← LA CLÉ PUBLIQUE ÉPHÉMÈRE, DÈS LE 1er  │
     │     • supported_versions, SNI, ALPN, cipher suites       │   RTT 1
     │                                                          │
     │◄─── ServerHello (key_share du serveur) ──────────────────│
     │     ╔═══ à partir d'ici, TOUT est chiffré ═══╗           │
     │◄─── {EncryptedExtensions}   ← ALPN caché ici             │
     │◄─── {[CertificateRequest]}  ← mTLS                       │
     │◄─── {Certificate}           ← LA CHAÎNE EST CHIFFRÉE     │
     │◄─── {CertificateVerify}     ← signature du transcript    │
     │◄─── {Finished}                                            │
     │                                                          │
     │──── {[Certificate + CertificateVerify]} ← mTLS ─────────►│
     │──── {Finished} ─────────────────────────────────────────►│
     │════ application_data ═══════════════════════════════════►│  1 RTT.
```

### 15.1 Ce que 1.3 a supprimé — et pourquoi

| Supprimé | Raison |
|---|---|
| Échange de clés **RSA statique** | pas de PFS : voler la clé privée déchiffre **tout le trafic passé** |
| Modes **CBC**, RC4, 3DES | attaques BEAST, Lucky13, padding oracle |
| **Compression** TLS | attaque CRIME |
| **Renégociation** | attaques de type triple handshake |
| MD5, SHA-1 en signature | collisions |
| Groupes DH personnalisés | Logjam ; 1.3 impose des groupes nommés (x25519, secp256r1…) |

Résultat : **5 suites cryptographiques** seulement en TLS 1.3, contre plusieurs dizaines en 1.2. Et le
nom change de forme, parce que la suite ne décrit plus **ni** l'échange de clés **ni** l'authentification :

```
   TLS 1.2 : TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256
             └─┬──┘ └┬┘      └──────┬──────┘ └──┬──┘
             échange auth        chiffrement    PRF/hash

   TLS 1.3 : TLS_AES_128_GCM_SHA256      ← plus que chiffrement + hash
                                            (l'échange est TOUJOURS éphémère)
   Les 3 principales : TLS_AES_128_GCM_SHA256
                       TLS_AES_256_GCM_SHA384
                       TLS_CHACHA20_POLY1305_SHA256  (mobile, sans AES-NI)
```

### 15.2 PFS — la propriété qui justifie tout ça

**Perfect Forward Secrecy** : compromettre la clé privée du serveur **aujourd'hui** ne permet pas de
déchiffrer les sessions **enregistrées hier**. C'est possible parce que les clés de session viennent d'un
échange **éphémère** (ECDHE : une paire jetable par connexion), et que la clé privée du certificat sert
seulement à **signer**, jamais à chiffrer.

**Analogie.** Sans PFS, la clé du serveur est le passe-partout de l'hôtel : celui qui le vole ouvre toutes
les chambres, y compris celles des clients partis. Avec PFS, chaque chambre a une serrure fondue à la
sortie du client ; le passe-partout ne sert plus qu'à prouver qu'on est bien le réceptionniste.

**En TLS 1.3, la PFS est obligatoire** : c'est le sens de la suppression de l'échange RSA statique.

> ❓ **RETIENS ÇA** — Combien de RTT avant le premier octet applicatif, en HTTPS à froid ?
> <details><summary>→ réponse</summary><br><b>TCP + TLS 1.2</b> = 1 + 2 = <b>3 RTT</b>. <b>TCP + TLS 1.3</b> = 1 + 1 = <b>2 RTT</b>. <b>QUIC/HTTP/3</b> = <b>1 RTT</b>. <b>QUIC en 0-RTT</b> (reprise) = <b>0 RTT</b>, les données partent avec le premier paquet. Le DNS s'ajoute par-dessus s'il n'est pas en cache.</details>

> ⚠️ **PIÈGE** — En TLS 1.3, un `ChangeCipherSpec` traîne encore dans les captures. Il ne sert **plus à
> rien** : c'est un message factice conservé uniquement pour que les boîtiers intermédiaires prennent la
> session pour du TLS 1.2 et ne la cassent pas. Même raison pour laquelle `ClientHello` annonce
> `version: TLS 1.2` et met la vraie version dans l'extension `supported_versions`.

### 15.3 SNI et ALPN : deux extensions à ne pas confondre

- **SNI** (Server Name Indication) : « **le nom que je demande** ». Envoyé **en clair** dans le
  ClientHello, avant tout chiffrement — c'est obligé : le serveur doit savoir **quel certificat** présenter
  avant d'avoir une clé. C'est ce qui permet d'héberger 500 sites HTTPS sur une seule IP. Corollaire : le
  SNI est le dernier endroit où un observateur voit encore quel site tu visites (d'où ECH, *Encrypted
  Client Hello*, qui le chiffre).
- **ALPN** (Application-Layer Protocol Negotiation) : « **quel protocole on parle après** ». Le client
  propose `["h2", "http/1.1"]`, le serveur choisit. **Sans surcoût en RTT**, puisque c'est dans le
  handshake. C'est ALPN, et rien d'autre, qui fait que HTTP/2 démarre sans requête d'`Upgrade`.

> ❓ **RETIENS ÇA** — Différence entre SNI et ALPN ?
> <details><summary>→ réponse</summary><br><b>SNI</b> = quel <b>nom d'hôte</b> je demande (choix du certificat, virtual hosting HTTPS) — en clair dans le ClientHello. <b>ALPN</b> = quel <b>protocole applicatif</b> on parlera dans le tunnel (<code>h2</code>, <code>http/1.1</code>, <code>h3</code>). Moyen mnémotechnique : SNI = <b>N</b>om, ALPN = <b>P</b>rotocole.</details>

---

## 16. Certificats : la chaîne de confiance

### 16.1 Le problème

Le serveur t'envoie une clé publique. Comment sais-tu qu'elle est bien la sienne, et pas celle d'un
attaquant en coupure ? Réponse : **quelqu'un que tu connais déjà l'a signée**.

```
   ┌───────────────────────────────┐
   │  Certificat RACINE (ISRG X1)  │  auto-signé, dans le magasin de confiance
   │  CA:TRUE  ~20 ans             │  de ton OS/navigateur. ~150 racines.
   └───────────────┬───────────────┘
                   │ signe
   ┌───────────────▼───────────────┐
   │  INTERMÉDIAIRE (R11)          │  CA:TRUE, hors ligne côté racine
   │  ~5 ans                       │  ← le serveur DOIT l'envoyer
   └───────────────┬───────────────┘
                   │ signe
   ┌───────────────▼───────────────┐
   │  FEUILLE : CN/SAN=api.exemple.fr │  CA:FALSE, ≤ 398 jours (90 j Let's Encrypt)
   └───────────────────────────────┘
```

Le serveur envoie **feuille + intermédiaires**, jamais la racine (le client l'a déjà, et l'envoyer ne
prouverait rien). La racine est **auto-signée** : sa confiance ne vient pas d'une signature, mais du fait
qu'elle a été **installée** dans ton magasin.

### 16.2 Ce que le client vérifie, dans l'ordre

1. La **chaîne remonte** jusqu'à une racine du magasin de confiance.
2. Chaque **signature** est valide, et chaque CA intermédiaire a bien `basicConstraints: CA:TRUE`.
3. Les **dates** `notBefore` / `notAfter` encadrent l'heure **de la machine cliente**.
4. Le **nom demandé correspond au SAN** (`subjectAltName`). ⚠️ le `CN` n'est plus regardé depuis
   Chrome 58 (2017) : **un certificat sans SAN est invalide**, même si le CN est correct.
5. Le **`extendedKeyUsage`** contient `serverAuth` (`clientAuth` pour un certificat client).
6. La **révocation** : CRL, OCSP, ou **agrafage OCSP** (le serveur joint lui-même une réponse OCSP
   signée et fraîche → pas de requête supplémentaire ni de fuite de vie privée).

### 16.3 Les erreurs classiques et leur diagnostic

| Message | Cause réelle | Vérification |
|---|---|---|
| `unable to get local issuer certificate` | **intermédiaire manquant** dans ce que le serveur envoie, ou CA privée inconnue | `openssl s_client -showcerts` : compte les certificats renvoyés |
| `self signed certificate in certificate chain` | CA interne pas dans le magasin | ajouter le bundle, `-CAfile` |
| `certificate has expired` | expiration… ou **horloge du client décalée** | `openssl x509 -noout -dates` **et** `date -u` sur le client |
| `Hostname mismatch` / `doesn't match` | le nom demandé n'est pas dans le SAN | `openssl x509 -noout -ext subjectAltName` |
| `tlsv1 alert unknown ca` (48) | **le serveur** ne fait pas confiance à **ton** certificat client (mTLS) | vérifier le `-CAfile` côté serveur |
| `alert certificate required` (116) | mTLS exigé, aucun certificat client envoyé | ajouter `-cert` / `-key` |
| `alert handshake failure` (40) | aucune suite / version / groupe en commun | `-tls1_2`, `-tls1_3`, `-cipher` |
| `alert unrecognized name` (112) | SNI absent ou inconnu du serveur | ajouter `-servername` |

> ⚠️ **PIÈGE** — Le grand classique : **« ça marche dans le navigateur, ça casse en `curl`/Java/Python »**.
> Cause : l'**intermédiaire manquant**. Les navigateurs vont le chercher tout seuls via l'extension AIA
> (*Authority Information Access*) ; `curl`, OpenSSL et la JVM **ne le font pas**. Le serveur est mal
> configuré, mais seuls les clients stricts le disent.

> ❓ **RETIENS ÇA** — Ton navigateur accepte un site, `curl` répond `unable to get local issuer certificate`. Cause la plus probable ?
> <details><summary>→ réponse</summary><br>Le serveur n'envoie <b>pas le certificat intermédiaire</b>. Le navigateur le récupère automatiquement via l'extension AIA ; curl/OpenSSL ne le font pas et la chaîne ne remonte pas jusqu'à la racine. Correction : concaténer feuille + intermédiaire(s) dans le fichier de certificat servi (le <code>fullchain.pem</code> de Let's Encrypt, pas le <code>cert.pem</code>).</details>

### 16.4 Les trois commandes de diagnostic

```bash
# 1. Que présente le serveur, exactement ? (SNI explicite, indispensable)
openssl s_client -connect api.exemple.fr:443 -servername api.exemple.fr \
        -showcerts -alpn h2,http/1.1 </dev/null

#    Lignes à lire : "Verify return code: 0 (ok)" | "Certificate chain" (0,1,2…)
#                    "Protocol : TLSv1.3" | "ALPN protocol: h2"

# 2. Que dit le certificat lui-même ?
openssl s_client -connect api.exemple.fr:443 -servername api.exemple.fr </dev/null 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates -ext subjectAltName

# 3. La chaîne remonte-t-elle vraiment ?
openssl verify -CAfile racine.pem -untrusted intermediaire.pem feuille.pem
```

> 🧠 **MÉMO** — Devant une erreur TLS, pose-toi les **4 questions dans l'ordre** : **CHAÎNE** (remonte-t-elle ?)
> · **NOM** (le SAN colle-t-il ?) · **DATE** (valide, et l'horloge du client est-elle juste ?) · **VERSION**
> (TLS/suites/groupes en commun ?). **C-N-D-V**. Quatre-vingt-quinze pour cent des incidents tombent dans
> l'une de ces cases.

---

## 17. mTLS et la maille de services

### 17.1 De l'authentification unilatérale à la mutuelle

En TLS classique, **seul le serveur** prouve son identité ; le client s'authentifie ensuite dans HTTP
(cookie, jeton Bearer). En **mTLS**, le serveur envoie `CertificateRequest`, et le client répond avec son
propre `Certificate` **et** un `CertificateVerify` — la signature qui prouve qu'il détient la clé privée.

```
   TLS classique                    mTLS
   ─────────────                    ────
   Serveur : "voici mon certif"     Serveur : "voici mon certif, ET LE TIEN ?"
   Client  : "OK, je te crois"      Client  : "voici le mien + ma signature"
   Client  : "voici mon jeton"      Les deux sont authentifiés AVANT le 1er octet HTTP.
             ↑ dans HTTP, APRÈS
```

Avantage décisif : **il n'y a plus de secret partagé à voler**. Un jeton Bearer volé fonctionne partout ;
une clé privée mTLS ne quitte jamais la machine, et les certificats sont **à durée très courte**
(24 h chez Istio, renouvelés automatiquement à la moitié de leur vie).

### 17.2 Pourquoi la maille de services

Faire du mTLS à la main entre 200 microservices, c'est 200 paires de clés à générer, distribuer, faire
tourner, révoquer. Une **maille de services** (Istio, Linkerd, Consul) automatise tout :

```
   ┌── Pod A ──────────────┐              ┌── Pod B ──────────────┐
   │ appli ──► sidecar     │              │  sidecar ──► appli    │
   │  (HTTP  │  Envoy      │═══ mTLS ════►│  Envoy      │  (HTTP  │
   │  clair) │             │  chiffré,    │             │  clair) │
   └─────────┴─────────────┘  authentifié └─────────────┴─────────┘
        127.0.0.1                                   127.0.0.1
              ▲                                            ▲
              └── l'application ne sait même pas ──────────┘
                  qu'elle fait du TLS
```

L'identité n'est pas une IP (qui change à chaque redémarrage de pod) mais une **identité SPIFFE**, portée
dans le SAN du certificat sous forme d'URI :

```
spiffe://cluster.local/ns/data-prod/sa/spark-driver
         └─ domaine ─┘ └ namespace ┘ └ service account ┘
```

Tu peux alors écrire une politique du type « seul le `sa/spark-driver` du namespace `data-prod` peut
appeler `feature-store:8080` » — une règle qui survit au replanning des pods, contrairement à une règle
par IP.

> ❓ **RETIENS ÇA** — Qu'ajoute mTLS par rapport à TLS ?
> <details><summary>→ réponse</summary><br>L'authentification du <b>client</b> par certificat, dans le handshake : le serveur envoie <code>CertificateRequest</code>, le client répond <code>Certificate</code> + <code>CertificateVerify</code> (signature du transcript). L'identité est établie <b>avant</b> le premier octet applicatif, et il n'y a aucun secret partagé transmissible — contrairement à un jeton Bearer.</details>

> ⚠️ **PIÈGE** — mTLS authentifie **la machine ou la charge de travail**, pas **l'utilisateur final**. Dans
> un pipeline, tu as besoin des deux : mTLS pour dire « ce pod a le droit d'appeler ce service », et un
> jeton (JWT/OIDC) propagé dans `Authorization` pour dire « au nom de quel humain ». Les confondre est
> une erreur d'architecture classique.

---

## 18. gRPC

### 18.1 Le problème

Deux services internes s'échangent 50 000 messages/s. En REST+JSON, tu paies : le **parsing texte**, la
**redondance** (les noms de champs répétés dans chaque objet), l'**absence de contrat** (rien n'empêche
d'envoyer un champ en `string` là où l'autre attend un `int`), et une gestion manuelle du streaming.

gRPC = **HTTP/2** (transport) + **Protocol Buffers** (sérialisation et contrat) + génération de code.

### 18.2 Protobuf, la partie qui compte

```protobuf
syntax = "proto3";
package featurestore.v1;

message FeatureRequest {
  int64  entity_id = 1;    // ← 1, 2, 3 : NUMÉROS DE CHAMP, gravés à vie
  int64  as_of_ts  = 2;
  bool   include_raw = 3;
}

service FeatureStore {
  rpc GetFeatures (FeatureRequest) returns (FeatureVector);
  rpc StreamFeatures (FeatureRequest) returns (stream FeatureVector);
}
```

Sur le fil, **les noms de champs n'existent pas**. Chaque champ est précédé d'un octet de balise :

```
   balise = (numéro_de_champ << 3) | type_de_fil
   ┌──────────────┬───────────────────────────────────────┐
   │ type de fil  │ ce qu'il encode                       │
   ├──────────────┼───────────────────────────────────────┤
   │ 0  VARINT    │ int32/64, uint, bool, enum            │
   │ 1  I64       │ fixed64, double                       │
   │ 2  LEN       │ string, bytes, message imbriqué       │
   │ 5  I32       │ fixed32, float                        │
   └──────────────┴───────────────────────────────────────┘
   Champs 1→15  : balise sur 1 octet  ← réserve-les aux champs les plus fréquents
   Champs 16→2047 : balise sur 2 octets
```

**Exercice corrigé — encodage réel.** Encode `{entity_id: 1234567, as_of_ts: 1727654400, include_raw: true}`.

```
Champ 1, varint : balise = (1<<3)|0 = 0x08
                  1234567 : 2¹⁴=16384 < 1234567 < 2²¹=2097152 → 3 octets de varint
                  → 1 + 3 = 4 octets
Champ 2, varint : balise = (2<<3)|0 = 0x10
                  1727654400 : 2²⁸=268435456 < v < 2³⁵ → 5 octets de varint
                  → 1 + 5 = 6 octets
Champ 3, varint : balise = (3<<3)|0 = 0x18, valeur 0x01
                  → 2 octets
TOTAL PROTOBUF  = 4 + 6 + 2 = 12 octets

JSON équivalent : {"entity_id":1234567,"as_of_ts":1727654400,"include_raw":true}
                  = 62 octets  (1 + 11 + 1 + 7 + 1 + 10 + 1 + 10 + 1 + 13 + 1 + 4 + 1)
RATIO ≈ 5,2×.  Sur 50 000 msg/s : 3,1 Mo/s en JSON contre 0,6 Mo/s en protobuf.
Et le gain CPU est du même ordre : pas de parsing texte, pas d'allocation de chaînes.
```

**Les règles de compatibilité** (c'est la vraie valeur de protobuf pour un data engineer) :
- ✅ **ajouter** un champ avec un **nouveau numéro** : les anciens lecteurs l'ignorent.
- ✅ **renommer** un champ : le nom n'est pas sur le fil.
- ❌ **changer le numéro** d'un champ, ou **réutiliser** un numéro supprimé (→ `reserved 4, 7;`).
- ❌ **changer le type** d'un champ de manière incompatible.
- En proto3, tous les champs sont optionnels et ont une valeur par défaut : **un champ absent et un champ
  à zéro sont indiscernables** sans `optional` explicite. C'est un piège classique en pipeline.

> ❓ **RETIENS ÇA** — Que se passe-t-il si tu réutilises le numéro d'un champ supprimé en protobuf ?
> <details><summary>→ réponse</summary><br>Les anciens clients décodent les nouvelles données avec l'<b>ancienne interprétation</b> du champ : corruption silencieuse, sans erreur. C'est pour ça qu'on écrit <code>reserved 4, 7;</code> et <code>reserved "vieux_nom";</code> à la suppression. Les <b>noms</b> sont libres, les <b>numéros</b> sont gravés à vie.</details>

### 18.3 Les 4 types d'appel

```
   1. UNARY                    2. SERVER STREAMING
      req ──►                     req ──►
      ◄── rép                     ◄── rép, rép, rép, … (n)
      « donne-moi ce vecteur »    « abonne-moi aux mises à jour »

   3. CLIENT STREAMING         4. BIDIRECTIONAL STREAMING
      req, req, req … ──►         req ──►  ◄── rép
      ◄── rép (1)                 req ──►  ◄── rép   (indépendants,
      « ingère ce lot »           ◄── rép            full duplex)
                                  « inférence en continu, chat »
```

Le streaming n'est pas un bonus : c'est ce qui permet d'envoyer 10 millions de lignes **sans les tenir en
mémoire** ni découper à la main en pages. C'est le mécanisme derrière **Arrow Flight** (transport de
données colonnaires par gRPC) et **Spark Connect**.

### 18.4 Sur le fil

```
POST /featurestore.v1.FeatureStore/GetFeatures HTTP/2   ← le chemin EST la méthode
content-type: application/grpc+proto
te: trailers
grpc-timeout: 2500m                    ← DEADLINE : 2 500 millisecondes

[1 o : compressé 0/1][4 o : longueur big-endian][message protobuf]

← :status: 200                         ← TOUJOURS 200, même en cas d'erreur !
← (trailers) grpc-status: 5            ← le VRAI code d'erreur (5 = NOT_FOUND)
             grpc-message: dataset not found
```

**Codes gRPC à connaître** : `0 OK` · `3 INVALID_ARGUMENT` · `4 DEADLINE_EXCEEDED` · `5 NOT_FOUND` ·
`7 PERMISSION_DENIED` · `8 RESOURCE_EXHAUSTED` (quota, ou **message > 4 Mio**, la limite par défaut) ·
`12 UNIMPLEMENTED` (mauvais chemin, ou proxy qui mange les trailers) · `13 INTERNAL` ·
`14 UNAVAILABLE` (le seul qu'on rejoue d'office) · `16 UNAUTHENTICATED`.

Le **deadline** est la meilleure idée de gRPC : ce n'est pas un timeout local mais un **instant absolu
propagé de service en service**. A appelle B avec 2 s de deadline ; B, qui a déjà consommé 800 ms, appelle
C avec 1,2 s. Quand le deadline expire, **toute la chaîne** est annulée — plus de travail fantôme sur des
requêtes dont plus personne n'attend le résultat.

> ❓ **RETIENS ÇA** — Quel code HTTP renvoie un appel gRPC en erreur ?
> <details><summary>→ réponse</summary><br><b>200 OK</b>, presque toujours. L'erreur réelle est dans les <b>trailers HTTP/2</b> : <code>grpc-status</code> et <code>grpc-message</code>. Conséquence pratique : un load balancer qui compte les 5xx croit que tout va bien, et un proxy qui ne sait pas relayer les trailers casse gRPC de façon très déroutante.</details>

> ⚠️ **PIÈGE** — **gRPC + load balancer L4 = déséquilibre garanti.** gRPC ouvre **une** connexion TCP
> persistante et y multiplexe tout. Un LB L4 place cette connexion sur un backend **une fois pour toutes** :
> 10 clients, 10 connexions, et si tu as 50 pods, 40 ne reçoivent rien. Les remèdes : équilibrage **côté
> client** (`round_robin` sur un service headless, xDS), **proxy L7** conscient d'HTTP/2 (Envoy), ou
> `MAX_CONNECTION_AGE` côté serveur pour forcer une redistribution périodique. C'est le prolongement direct
> du L4/L7 de R07.

> ⚠️ **PIÈGE** — **Un navigateur ne peut pas parler gRPC nativement** : `fetch()` ne donne aucun contrôle
> sur les trames HTTP/2 et ne lit pas les trailers. Il faut **gRPC-Web** et un proxy de traduction (filtre
> `grpc_web` d'Envoy), au prix de la perte du streaming client et bidirectionnel.

---

## 19. WebSocket : garder la ligne ouverte

### 19.1 Le problème

HTTP est **client → serveur**. Comment le serveur pousse-t-il une donnée qu'on ne lui a pas demandée
(alerte, avancement d'un job, tick de marché) ? Historiquement : le *polling* (« du neuf ? » toutes les
5 s → latence et gaspillage) puis le *long polling* (requête qui reste ouverte). WebSocket ouvre un vrai
canal **bidirectionnel et persistant**.

### 19.2 L'upgrade

```
→ GET /stream HTTP/1.1
  Host: api.exemple.fr
  Upgrade: websocket
  Connection: Upgrade
  Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==      ← 16 octets aléatoires en base64
  Sec-WebSocket-Version: 13
  Sec-WebSocket-Protocol: json.v1                   ← sous-protocole, optionnel

← HTTP/1.1 101 Switching Protocols
  Upgrade: websocket
  Connection: Upgrade
  Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=

  Accept = base64( SHA1( Key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11" ) )
  → ce n'est PAS de la sécurité : ça prouve juste que le serveur a compris
    qu'il s'agit d'un WebSocket et non d'un cache qui rejoue une vieille réponse.

  Après le 101 : ce n'est PLUS de l'HTTP. C'est du cadrage WebSocket brut.
```

Trame WebSocket :

```
   ┌─┬─┬─┬─┬────────┬─┬─────────────┬───────────────┬──────────┐
   │F│R│R│R│ opcode │M│  longueur   │ clé de masque │ données  │
   │I│S│S│S│  (4 b) │A│   (7 bits,  │  (4 o, client │          │
   │N│V│V│V│        │S│  +16 ou +64)│  → serveur)   │          │
   └─┴─┴─┴─┴────────┴─┴─────────────┴───────────────┴──────────┘
   En-tête : 2 à 14 octets (contre ~500-800 o d'en-têtes HTTP par message !)

   Opcodes : 0x0 continuation · 0x1 texte · 0x2 binaire
             0x8 close · 0x9 ping · 0xA pong
   Codes de fermeture : 1000 normal · 1001 départ · 1006 ANORMAL (pas de
                        trame close reçue — le symptôme d'une coupure par un LB)
```

Le **masquage obligatoire** des trames client→serveur (XOR avec 4 octets aléatoires) n'est pas du
chiffrement : il empêche un attaquant de fabriquer, via un navigateur piégé, des octets ressemblant à une
requête HTTP valide pour empoisonner un proxy en amont.

> ❓ **RETIENS ÇA** — Quel code de statut confirme l'établissement d'un WebSocket ?
> <details><summary>→ réponse</summary><br><b>101 Switching Protocols</b>, avec <code>Upgrade: websocket</code>, <code>Connection: Upgrade</code> et <code>Sec-WebSocket-Accept</code>. Après cette réponse, la connexion TCP ne transporte plus du HTTP mais des trames WebSocket.</details>

> ⚠️ **PIÈGE** — Un WebSocket **inactif meurt silencieusement** : ALB coupe à **60 s** d'inactivité par
> défaut, nginx à `proxy_read_timeout 60s`. Le client voit un code de fermeture **1006** sans explication.
> Remède : envoyer un **ping** applicatif toutes les 20-30 s **et** relever les timeouts du proxy. C'est
> exactement le même piège que R07 sur les requêtes analytiques longues.

### 19.3 Quand ne PAS prendre WebSocket

| Besoin | Meilleur choix |
|---|---|
| Serveur → client seulement, texte, reconnexion auto | **SSE** (`text/event-stream`) : reste de l'HTTP, traverse tout, 20 lignes de code |
| Requête/réponse classique | HTTP tout court |
| Flux structuré entre services internes | **gRPC streaming** (typé, deadlines, backpressure) |
| Vrai duplex navigateur (chat, édition collaborative, terminal web) | **WebSocket** |

WebSocket est **avec état** : chaque connexion est épinglée à un processus. Ça complique la montée en
charge, les déploiements (chaque redémarrage casse toutes les connexions) et l'équilibrage.

---

## 20. REST vs gRPC vs GraphQL : choisir

| Critère | REST/JSON | gRPC | GraphQL |
|---|---|---|---|
| Contrat | OpenAPI (optionnel) | **`.proto`, obligatoire, compilé** | schéma SDL, obligatoire |
| Format | texte JSON | **binaire protobuf** | JSON |
| Transport | HTTP/1.1 ou 2 | **HTTP/2 obligatoire** | HTTP, un seul endpoint |
| Navigateur | natif | non (gRPC-Web + proxy) | natif |
| Streaming | SSE / chunked | **natif, 4 modes** | *subscriptions* (souvent WebSocket) |
| Cache HTTP | **excellent** (GET + ETag) | nul (tout est POST) | nul (tout est POST) |
| Débogage | `curl`, lisible | `grpcurl` + réflexion | outils dédiés |
| Sur-/sous-récupération | fréquente | non (contrat précis) | **résolue par construction** |
| Risque propre | versionnage anarchique | outillage, proxies capricieux | **N+1 sur les resolvers, requêtes-bombes** |

**La règle de décision en une phrase** : **frontière publique / navigateur → REST** ; **service à service à
fort volume → gRPC** ; **plusieurs clients aux besoins de données très différents → GraphQL** ; **transfert
de gros volumes de données → ni l'un ni l'autre : objet + URL présignée, ou Arrow Flight.**

> 🧠 **MÉMO** — **REST = documents. gRPC = fonctions. GraphQL = requêtes.** Trois métaphores, trois usages.
> Si tu manipules des ressources → REST. Si tu appelles des procédures → gRPC. Si le client veut composer
> lui-même sa réponse → GraphQL.

> ⚠️ **PIÈGE** — Ne jamais faire transiter un gros jeu de données **dans** la réponse d'une API. 4 Gio de
> Parquet en JSON base64, c'est un timeout et une facture. Le motif correct : l'API renvoie **202** + une
> **URL présignée** vers l'objet, et le client télécharge en parallèle par `Range` (206). L'API porte le
> **contrôle**, le stockage porte les **octets**.

---

## 21. Ce que ça donne dans un vrai pipeline

**1. Le pool de connexions est ton premier facteur de performance.** `boto3` limite par défaut à
**10 connexions** par client (`botocore.config.Config(max_pool_connections=10)`), `requests` à
`pool_maxsize=10` par hôte. Un job à 64 threads qui tape S3 avec les valeurs par défaut passe son temps à
**refaire des handshakes TLS** — 2 RTT chacun — et à écraser des connexions du pool. Régler
`max_pool_connections` au nombre de threads est souvent un gain de 2 à 5× sans changer une ligne de logique.

**2. Chaque handshake coûte un aller-retour de latence, multiplié par la distance.** Paris↔Francfort ≈
10 ms de RTT, Paris↔Virginie ≈ 85 ms, Paris↔Singapour ≈ 170 ms. À 85 ms, un handshake TCP+TLS 1.3 coûte
**170 ms avant le premier octet**. Sur 10 000 petits fichiers en série : 28 minutes de pure latence.
Réponses : **réutiliser** les connexions, **paralléliser**, et surtout **grouper** les petits fichiers.

**3. La fenêtre HTTP/2 par défaut brime les transferts longue distance** (calcul en 24.2). C'est le même
phénomène que le BDP de TCP vu en R06, remonté d'une couche.

**4. Les retards de MTU se déguisent en problèmes TLS.** Un CNI VXLAN (MTU 1450) plus un chemin qui bloque
l'ICMP donne une PMTUD aveugle : le petit `ClientHello` passe, la grosse trame `Certificate` (2-5 Ko) ne
passe pas. Symptôme : **le handshake gèle toujours au même endroit**. Ce n'est pas TLS, c'est le MTU (R03/R06).

**5. Les 4xx et 5xx ne se traitent pas pareil.** `429` et `503` → backoff exponentiel **avec jitter**, en
respectant `Retry-After`. `500` → rejouer avec prudence, seulement si l'opération est idempotente ou porte
une clé d'idempotence. `4xx` → n'insiste pas, corrige la requête. Un client qui rejoue agressivement des
`503` **cause** la panne qu'il essaie de survivre.

**6. Le nombre de certificats explose avant tout le reste.** Un cluster avec maille de services renouvelle
des certificats **toutes les 12 à 24 h** pour chaque charge de travail. Le jour où l'autorité intermédiaire
expire, ce n'est pas un service qui tombe — c'est **tout le cluster**, d'un coup. Surveille les dates
d'expiration comme une métrique de production, pas comme une tâche d'administration.

---

## 22. Diagnostic : les commandes qui répondent vraiment

```bash
# Où passe le temps ? (la commande la plus utile du module)
curl -o /dev/null -sS -w \
 'dns:%{time_namelookup}s tcp:%{time_connect}s tls:%{time_appconnect}s ttfb:%{time_starttransfer}s tot:%{time_total}s ver:%{http_version}\n' \
 https://api.exemple.fr/health
# tls - tcp = coût du handshake TLS · ttfb - tls = temps de calcul serveur

# Quelle version HTTP négocie-t-on vraiment ?
curl -sI --http2 https://api.exemple.fr | head -1     # "HTTP/2 200"
curl -sI --http3 https://api.exemple.fr | head -1     # "HTTP/3 200" (curl compilé h3)

# Les en-têtes seuls, sans le corps
curl -sSI https://api.exemple.fr/objet

# Ce que le cache va faire
curl -sSI https://cdn.exemple.fr/a.js | grep -Ei 'cache-control|etag|age|vary'

# TLS : version, chaîne, ALPN, en une commande
openssl s_client -connect api.exemple.fr:443 -servername api.exemple.fr -alpn h2 </dev/null 2>&1 \
  | grep -E 'Protocol|Cipher|Verify return|ALPN|subject=|issuer='

# mTLS côté client
openssl s_client -connect mesh.interne:443 -cert client.crt -key client.key -CAfile ca.pem

# gRPC sans écrire une ligne de code (si la réflexion est activée)
grpcurl -plaintext localhost:50051 list
grpcurl -d '{"entity_id": 42}' -H 'authorization: Bearer x' \
        api.exemple.fr:443 featurestore.v1.FeatureStore/GetFeatures

# WebSocket
websocat -v wss://api.exemple.fr/stream

# Déchiffrer TLS dans Wireshark, proprement (sans MITM)
export SSLKEYLOGFILE=/tmp/keys.log   # puis Wireshark → (Pre)-Master-Secret log filename
```

---

## 23. Exercices intégralement corrigés

### 23.1 Budget de latence d'un premier appel

**Énoncé.** Ton job tourne à Paris, l'API est à Virginie. RTT = **85 ms**, DNS non caché (1 RTT vers un
résolveur local à 2 ms, puis résolution à 40 ms), temps de calcul serveur = 30 ms. Calcule le temps
jusqu'au dernier octet pour : (a) HTTP/1.1 + TLS 1.2, (b) HTTP/2 + TLS 1.3, (c) HTTP/3, (d) HTTP/3 en
0-RTT. Puis pour 100 requêtes séquentielles sur la même connexion en (b).

**Correction.**

```
DNS (commun aux quatre)      = 42 ms

(a) HTTP/1.1 + TLS 1.2
    TCP  : 1 RTT            =  85 ms
    TLS  : 2 RTT            = 170 ms
    HTTP : 1 RTT            =  85 ms
    calcul serveur          =  30 ms
    ─────────────────────────────────
    TOTAL                   = 42 + 85 + 170 + 85 + 30 = 412 ms

(b) HTTP/2 + TLS 1.3
    TCP 85 + TLS 85 + HTTP 85 + 30           = 42 + 285 = 327 ms

(c) HTTP/3 (QUIC 1-RTT)
    QUIC 85 (TCP et TLS fusionnés) + HTTP 85 + 30 = 42 + 200 = 242 ms

(d) HTTP/3 en 0-RTT (session reprise)
    la requête part DANS le premier paquet : 1 RTT total + calcul
                                             = 42 + 85 + 30 = 157 ms
    (DNS presque toujours caché en reprise → ~115 ms en pratique)

100 requêtes séquentielles en (b), connexion réutilisée :
    handshakes payés UNE fois : 42 + 85 + 85 = 212 ms
    puis 100 × (85 + 30)                     = 11 500 ms
    TOTAL                                    = 11,7 s
    → soit 1,8 % de handshake et 98 % d'allers-retours applicatifs.
LEÇON : à longue distance, le vrai levier n'est pas le handshake mais la SÉQUENTIALITÉ.
        Multiplexe (HTTP/2), parallélise, ou groupe les requêtes en lots.
```

### 23.2 La fenêtre HTTP/2 qui brime ton transfert

**Énoncé.** Tu télécharges un fichier de 2 Gio depuis une région à **100 ms** de RTT, sur un lien à
1 Gb/s, en HTTP/2 avec les réglages par défaut. Débit maximal atteignable ? Que faire ?

**Correction.**

```
Fenêtre de contrôle de flux HTTP/2 par défaut : SETTINGS_INITIAL_WINDOW_SIZE = 65 535 o.
Un flux ne peut pas avoir plus de 65 535 octets non acquittés EN VOL (au sens HTTP/2).

Débit max = fenêtre / RTT
          = 65 535 o / 0,100 s
          = 655 350 o/s ≈ 640 Kio/s ≈ 5,24 Mb/s

Le lien fait 1 Gb/s. Tu en utilises 0,5 %.
Temps de transfert de 2 Gio = 2 147 483 648 / 655 350 ≈ 3 277 s ≈ 55 minutes.

Fenêtre NÉCESSAIRE pour saturer 1 Gb/s à 100 ms (le BDP, exactement comme en R06) :
    1 Gb/s × 0,1 s = 100 Mb = 12,5 Mo   → il faut une fenêtre de ~12,5 Mo (≈ 11,9 Mio).

CORRECTIONS, dans l'ordre :
  1. relever SETTINGS_INITIAL_WINDOW_SIZE (par flux) ET la fenêtre de CONNEXION
     (envoyer un WINDOW_UPDATE sur le flux 0) — les deux, sinon la connexion plafonne ;
  2. vérifier aussi la fenêtre TCP en dessous (wscale, tcp_rmem) : DEUX fenêtres en série,
     c'est la plus petite qui gagne ;
  3. ou : télécharger en N requêtes `Range:` parallèles, sur N CONNEXIONS distinctes —
     N × 640 Kio/s. Avec N = 20 : 20 × 640 Kio/s = 12 800 Kio/s = ~12,5 Mio/s. C'est exactement
     ce que fait le téléchargement multipart d'un SDK objet, qui puise dans un pool de connexions.
     ⚠️ N flux parallèles sur UNE SEULE connexion HTTP/2 ne multiplient RIEN : la fenêtre de
     CONNEXION vaut elle aussi 65 535 o par défaut, et elle n'est pas réglable par SETTINGS
     (seulement par WINDOW_UPDATE sur le flux 0). Les 20 flux se partageraient les mêmes 640 Kio/s.

ATTENTION AU PIÈGE CLASSIQUE : deux fenêtres imbriquées, la HTTP/2 (par flux ET par
connexion) et la TCP. Relever l'une sans l'autre ne change rien.
```

### 23.3 Diagnostic de certificat

**Énoncé.** `python -c "import requests; requests.get('https://interne.exemple.fr')"` échoue avec
`unable to get local issuer certificate`. Le navigateur affiche le site sans erreur. Que fais-tu, dans
quel ordre ?

**Correction.**

```
1. Voir CE QUE LE SERVEUR ENVOIE VRAIMENT :
   openssl s_client -connect interne.exemple.fr:443 -servername interne.exemple.fr \
           -showcerts </dev/null 2>/dev/null | grep -c 'BEGIN CERTIFICATE'

   → "1"  : le serveur n'envoie QUE la feuille. Diagnostic posé : intermédiaire manquant.
            Le navigateur le récupère via AIA, Python/OpenSSL non. → 90 % des cas.
   → "2" ou "3" : la chaîne est complète, passe à l'étape 2.

2. Voir OÙ ELLE S'ARRÊTE :
   ... | grep -E 'depth=|verify error'
   "verify error:num=20:unable to get local issuer certificate" au depth le plus haut
   → la racine n'est pas dans le magasin de confiance → c'est une CA d'entreprise.

3. Confirmer d'où vient la racine :
   openssl x509 -noout -issuer -subject -in <le certificat le plus haut>
   Si issuer == subject → auto-signé → racine privée.

CORRECTIONS :
  Cas 1 (le bon) : reconfigurer le serveur pour servir fullchain.pem (feuille +
                   intermédiaires), PAS cert.pem seul. C'est un bug serveur.
  Cas 2 : distribuer la racine d'entreprise aux clients —
          REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-entreprise.pem, ou
          update-ca-certificates dans l'image de base, ou verify='/chemin/ca.pem'.

CE QU'ON NE FAIT JAMAIS : verify=False. Ça supprime l'authentification, donc TOUTE la
sécurité de TLS, tout en gardant le chiffrement — c'est-à-dire une protection contre
personne. Et en entretien, c'est une réponse éliminatoire.
```

---

## 24. Questions d'entretien

**1. Raconte-moi ce qui se passe entre le moment où je tape une URL HTTPS et l'affichage de la page.**
Résolution DNS d'abord (le module R07 : `getaddrinfo`, `/etc/hosts`, résolveur, caches, TTL), puis
handshake TCP en trois temps vers le port 443. Ensuite le handshake TLS : `ClientHello` avec SNI, ALPN et
`key_share` en 1.3, réponse du serveur avec son certificat, que je valide — chaîne jusqu'à une racine de
confiance, dates, SAN, révocation. Une fois les clés dérivées, j'envoie la requête HTTP, en HTTP/2 si ALPN
a négocié `h2`. Le serveur répond, le navigateur consulte son cache pour chaque sous-ressource, et
réutilise la même connexion multiplexée. À froid, c'est 2 RTT avant le premier octet en TLS 1.3, 3 en 1.2.

**2. Qu'est-ce que l'idempotence, et pourquoi un ingénieur réseau s'en soucie-t-il ?**
Une méthode est idempotente si l'exécuter N fois laisse le serveur dans le même état qu'une fois. C'est ce
qui autorise le rejeu automatique. Un client HTTP ne sait jamais si un timeout signifie « perdu à l'aller »
ou « traité mais réponse perdue » ; rejouer un `GET` ou un `PUT` est sans danger, rejouer un `POST` crée un
doublon. C'est aussi la condition d'usage du 0-RTT de TLS 1.3 et QUIC, qui est rejouable par construction.
Quand le métier impose un `POST`, on restaure la propriété avec une clé d'idempotence côté serveur.

**3. HTTP/2 résout-il le head-of-line blocking ?**
Il résout celui de la couche application : plusieurs flux sont multiplexés sur une connexion, les réponses
n'ont plus à revenir dans l'ordre des requêtes, ce qui tuait le pipelining d'HTTP/1.1. Mais tout passe dans
un seul flux TCP, qui livre strictement dans l'ordre : un segment perdu bloque la remise de tous les flux,
même intacts. Sur un réseau à pertes, HTTP/2 peut donc être **pire** qu'HTTP/1.1 avec ses six connexions
parallèles. C'est exactement le problème que QUIC règle, en descendant la notion de flux dans le transport.

**4. Explique-moi TLS 1.3 et ce qu'il change par rapport à 1.2.**
Un aller-retour au lieu de deux : le client envoie sa part de clé éphémère dès le `ClientHello`, le serveur
répond avec la sienne, et le reste du handshake — certificat inclus — est déjà chiffré. TLS 1.3 supprime
tout ce qui était devenu dangereux : l'échange RSA statique, donc la PFS devient obligatoire ; les modes
CBC ; la compression ; la renégociation ; MD5 et SHA-1. Il ne reste que cinq suites, qui ne décrivent plus
que le chiffrement et le hash, puisque l'échange de clés est toujours éphémère. Il ajoute aussi le 0-RTT,
qu'on réserve aux requêtes idempotentes parce qu'il est rejouable.

**5. Qu'est-ce que la Perfect Forward Secrecy et comment l'obtient-on ?**
C'est la garantie qu'un attaquant qui enregistre du trafic aujourd'hui et vole la clé privée du serveur
demain ne peut pas déchiffrer ce trafic. On l'obtient par un échange de clés **éphémère**, ECDHE en
pratique : les deux parties génèrent une paire jetable par connexion, le secret partagé n'est jamais
transmis et disparaît en fin de session. La clé privée du certificat ne sert alors qu'à **signer** le
handshake, pas à protéger les données. TLS 1.3 la rend obligatoire ; en 1.2, il fallait exclure
explicitement les suites `TLS_RSA_WITH_*`.

**6. Différence entre SNI et ALPN ?**
Les deux sont des extensions du `ClientHello`. SNI transmet le **nom d'hôte** demandé, pour que le serveur
sache quel certificat présenter — c'est ce qui rend possible l'hébergement de plusieurs sites HTTPS sur une
IP. Il est en clair, forcément, puisqu'il précède toute clé, et c'est pour ça qu'ECH existe. ALPN transmet
la liste des **protocoles applicatifs** que le client sait parler, `h2`, `http/1.1`, `h3` ; le serveur en
choisit un. Sans ALPN, il faudrait un aller-retour supplémentaire d'`Upgrade` pour passer en HTTP/2.

**7. Comment débogues-tu une erreur de certificat ?**
Je suis quatre questions dans l'ordre : la chaîne remonte-t-elle jusqu'à une racine de confiance, le nom
demandé est-il dans le SAN, les dates sont-elles valides — y compris l'horloge du client —, et y a-t-il une
version TLS et des suites en commun. Concrètement : `openssl s_client -servername ... -showcerts` pour voir
ce que le serveur envoie réellement et le code de vérification, puis `openssl x509 -noout -dates -ext
subjectAltName`. Le cas le plus fréquent est un intermédiaire manquant : le navigateur le récupère via AIA
et masque le problème, curl et la JVM échouent. La correction est côté serveur, jamais `verify=False`.

**8. Pourquoi utiliser gRPC plutôt que REST entre deux services de données ?**
Pour quatre raisons concrètes. Le contrat `.proto` est compilé et versionné, donc les incompatibilités
apparaissent à la construction, pas en production. La sérialisation binaire divise la taille par cinq à dix
et le coût CPU d'autant. Le streaming est natif dans les quatre modes, ce qui permet de pousser des
millions de lignes sans tout charger en mémoire — c'est le socle d'Arrow Flight et de Spark Connect.
Enfin, les deadlines se propagent d'appel en appel et annulent toute la chaîne. Je ne l'utilise pas côté
navigateur ni sur une API publique, où REST reste supérieur pour le cache et l'outillage.

**9. Un service gRPC derrière un load balancer envoie 90 % du trafic à un seul pod. Pourquoi ?**
Parce que le load balancer travaille en L4. gRPC ouvre une connexion TCP persistante et y multiplexe tous
les appels ; le L4 la place sur un backend une fois pour toutes et n'a plus jamais l'occasion de rééquilibrer.
Avec dix clients et cinquante pods, quarante pods restent inactifs. Trois remèdes : un proxy L7 conscient
d'HTTP/2 qui répartit appel par appel, un équilibrage côté client (résolveur DNS headless plus politique
`round_robin`, ou xDS), ou `MAX_CONNECTION_AGE` côté serveur pour forcer les clients à se reconnecter
périodiquement. Une maille de services fait le premier point pour toi.

**10. Quand choisis-tu WebSocket, et quand SSE ?**
SSE dès que le flux est unidirectionnel du serveur vers le client et textuel : c'est du HTTP ordinaire, ça
traverse tous les proxys et CDN, la reconnexion et la reprise par `Last-Event-ID` sont dans le protocole, et
ça coûte vingt lignes. WebSocket quand j'ai vraiment besoin du duplex — chat, édition collaborative,
terminal web, trading — ou de binaire compact. Le prix de WebSocket est l'état : chaque connexion est
épinglée à un processus, chaque déploiement les casse toutes, et un timeout d'inactivité de load balancer
la tue silencieusement avec un code 1006 s'il n'y a pas de ping applicatif.

**11. Différence entre `no-cache` et `no-store` ?**
`no-cache` autorise le stockage mais impose une revalidation avant chaque réutilisation : le client renvoie
son `ETag` dans `If-None-Match` et reçoit un 304 sans corps si rien n'a changé. On économise le transfert,
pas l'aller-retour. `no-store` interdit tout stockage, en mémoire comme sur disque, et c'est ce qu'il faut
pour des données sensibles. Le nom `no-cache` est trompeur et c'est la confusion la plus courante d'HTTP.
J'ajoute que sur du contenu personnalisé, il faut aussi `private` et un `Vary` correct, sinon un cache
partagé peut servir la réponse d'un utilisateur à un autre.

---

## 25. Les 3 choses à retenir si tu ne retiens que ça

**1. Toute l'histoire d'HTTP est celle d'une file d'attente qu'on découpe, étage par étage.**
HTTP/1.1 : une requête à la fois par connexion, et le pipelining meurt du blocage de tête de file. HTTP/2 :
des flux multiplexés qui suppriment ce blocage **dans l'application** — mais TCP, en dessous, livre toujours
dans l'ordre, donc une perte gèle tout. HTTP/3 : on descend les flux **dans le transport** avec QUIC, et
une perte n'affecte plus que son flux. Retiens la question, pas la réponse : **« à quel étage l'ordre
est-il encore imposé, et quelle ressource est encore partagée ? »** Elle marche aussi pour Kafka, pour un
étage Spark et pour n'importe quelle file.

**2. TLS ne se résume pas au chiffrement : sa partie difficile, et celle qui casse, c'est
l'authentification.** Le chiffrement symétrique est rapide, éprouvé, et ne pose jamais de problème. Ce qui
tombe en production, c'est la **chaîne de certificats** : un intermédiaire manquant que le navigateur
compense et que curl refuse, un SAN qui ne correspond pas, une racine d'entreprise absente d'une image
Docker, une horloge décalée, un certificat expiré un dimanche. Ta boucle de diagnostic tient en quatre
mots — **chaîne, nom, date, version** — et la mauvaise réponse est toujours la même : désactiver la
vérification, ce qui supprime la seule garantie qui comptait.

**3. Le format et le transport que tu choisis décident de tes performances bien avant ton code.**
Un handshake, c'est un ou deux RTT ; à 85 ms de distance, c'est 170 ms avant le premier octet, et 10 000
petits fichiers en série font une demi-heure de pure latence. Un pool `boto3` à 10 connexions étrangle un
job à 64 threads. Une fenêtre HTTP/2 laissée à 65 535 octets plafonne un transfert à 5 Mb/s sur un lien à
1 Gb/s. Du JSON là où protobuf suffirait, c'est six fois plus d'octets et de CPU. **Aucun de ces chiffres
n'apparaît dans ton code ni dans tes tests** — et c'est exactement pour ça que les connaître par cœur fait
la différence entre optimiser au hasard et corriger en dix minutes.
