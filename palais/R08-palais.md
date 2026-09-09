# Palais mental R08 — Les 10 messages du handshake TLS 1.2, dans l'ordre

> **La liste à ancrer** : les **10 messages d'un handshake TLS 1.2 complet avec authentification mutuelle**,
> dans l'ordre exact. C'est la question d'entretien la plus prévisible du module (« déroule-moi un handshake
> TLS »), et c'est aussi ta grille de lecture quand tu regardes une capture Wireshark ou la sortie de
> `openssl s_client -trace` : tu ne cherches pas « où ça casse », tu **marches** dans les dix messages et tu
> t'arrêtes à celui qui n'arrive jamais.
>
> Dix messages, dix emplacements. Ça tombe juste — encore.
>
> **Phrase d'amorce, à te dire avant de partir** : « **je marche pour le handshake TLS** ». Elle active le
> bon jeu d'images et évite les collisions avec les autres listes logées dans le même appartement (les
> étapes DNS de R07, l'en-tête IPv4 de R03, le best path BGP de R05).
>
> **Le fil rouge à ne jamais lâcher — qui parle, et quand :**
>
> ```
>   1        │ 2   3   4   5   6      │ 7   8   9      │ 10
>   CLIENT   │      S E R V E U R     │   C L I E N T  │ SERVEUR
>   ─────────┴────────────────────────┴────────────────┴─────────
>   « salut »│ « voici qui je suis,   │ « voici qui je │ « OK, on
>            │   ma part de clé, et   │  suis, ma part │  y va »
>            │   à toi de jouer »     │  de clé, on    │
>            │                        │  chiffre »     │
>   └──── RTT 1 ────────────────────┘ └──── RTT 2 ────────────────┘
> ```
>
> **UN client, CINQ serveur, TROIS client, UN serveur. 1-5-3-1.** Si tu ne retiens que ce rythme, tu
> reconstruis la liste.

---

## 1. La porte d'entrée — `ClientHello`

Un **gamin en ciré jaune poussin** martèle ta sonnette et hurle : « **BONJOUR ! JE PARLE TRENTE-DEUX
LANGUES !** » En même temps il balance par terre **32 dés en métal** qui rebondissent partout dans un
vacarme de casserole. Sur sa poitrine, deux badges cousus de travers : « **LE NOM QUE JE VEUX** » et
« **h2, sinon http/1.1** ».

→ **Message 1 : `ClientHello`.** Le client ouvre. Il envoie son **`client_random` de 32 octets** (les 32
dés — l'aléa qui garantit que deux handshakes ne produiront jamais les mêmes clés), la **liste des suites
cryptographiques** qu'il sait parler (les trente-deux langues), et ses **extensions** : **SNI** = le nom
d'hôte demandé (badge 1), **ALPN** = les protocoles applicatifs proposés (badge 2), plus
`supported_groups` et `signature_algorithms`.

## 2. Le couloir — `ServerHello`

Un **majordome en velours violet** sort de l'ombre, jette à son tour **ses** 32 dés, puis sort une
**perforatrice géante** : **CLAC**. Il poinçonne **UNE SEULE** carte dans le paquet du gamin, la punaise au
mur, et **toutes les autres cartes prennent feu** en crépitant.

→ **Message 2 : `ServerHello`.** Le serveur répond avec son **`server_random` de 32 octets** et **choisit
une seule suite** dans la liste proposée. Le choix appartient au serveur, jamais au client. Les autres
options n'existent plus.

## 3. La cuisine — `Certificate`

La porte du **frigo** s'ouvre toute seule et **vomit une guirlande de cartes d'identité plastifiées**,
rivetées les unes aux autres, qui se déroule en cliquetant jusqu'au bout du carrelage. Tu remarques un
détail qui te glace : **la dernière carte de la guirlande n'est pas là**. La vieille dame qui l'a signée est
déjà **accrochée en portrait au mur**, depuis toujours.

→ **Message 3 : `Certificate`.** Le serveur envoie sa **chaîne** : certificat **feuille + intermédiaires**,
rivetés par les signatures. La **racine n'est jamais envoyée** — elle est déjà dans ton magasin de
confiance (le portrait au mur). Guirlande incomplète = `unable to get local issuer certificate`.

## 4. La table — `ServerKeyExchange`

Le majordome pose sur la table **la moitié gauche d'une clé verte fluo, énorme**. Puis il sort un stylo à
plume, la **signe à l'encre rouge** en appuyant si fort que la plume **transperce la table** dans un
craquement de bois. La signature **luit dans le noir**.

→ **Message 4 : `ServerKeyExchange`.** Le serveur envoie sa **part publique ECDHE** (la demi-clé verte) —
et la **signe** avec la clé privée de son certificat. **C'est ici, et nulle part ailleurs, que le serveur
prouve qu'il détient la clé privée.** Envoyer un certificat ne prouve rien : un certificat est public. La
plume qui transperce la table, c'est la preuve qui traverse tout.

## 5. Le canapé — `CertificateRequest` (facultatif)

De sous les coussins du canapé surgit un **douanier en gilet orange fluo**, sifflet à roulette strident :
« **ET VOS PAPIERS À VOUS ?!** » Détail capital : **la moitié du temps, le canapé reste muet**. Le douanier
ne sort que quand la maison est en alerte.

→ **Message 5 : `CertificateRequest`.** **Facultatif** : c'est le message qui transforme un TLS ordinaire
en **mTLS**. Le serveur exige un certificat client. Dans une maille de services, ce douanier est toujours
là ; sur un site web public, jamais.

## 6. La fenêtre — `ServerHelloDone`

Le majordome claque la **fenêtre** avec un **coup de gong** qui fait vibrer les vitres, et un **néon rouge**
se met à clignoter au-dessus : « **J'AI FINI DE PARLER** ». Plus un bruit du côté serveur.

→ **Message 6 : `ServerHelloDone`.** Message **vide**, purement structurel : il marque la fin du bloc
serveur. C'est le signal que la parole revient au client. C'est aussi **la frontière du premier
aller-retour** : tout ce qui précède tenait dans le RTT 1.

## 7. Le bureau — `Certificate` du client

Tu jettes **ton propre badge plastifié** sur le bureau, et rien d'autre. Le badge glisse sur le sous-main
et s'arrête pile au bord. **Personne ne t'a encore demandé de signer quoi que ce soit.**

→ **Message 7 : `Certificate` du client** — **seulement si le douanier est sorti**. Le client envoie sa
chaîne de certificats. Elle ne prouve **rien** à elle seule : un certificat est public. La preuve viendra
à l'emplacement 8, **après** la demi-clé.

## 8. La bibliothèque — `ClientKeyExchange`, puis `CertificateVerify`

Tu tires un livre, l'étagère **pivote en grondant**, et **ta moitié droite de clé verte** vient se plaquer
sur celle du majordome dans un **CLAC magnétique**. Un **nuage vert phosphorescent** se forme entre les
deux moitiés — puis **disparaît instantanément**. Il **n'est jamais passé par le couloir**. Aussitôt après,
un **bras mécanique** jaillit d'un tiroir de l'étagère, t'attrape le poignet et te **force à signer un
registre géant** où est recopié **tout ce qui s'est dit depuis la porte d'entrée** — le nuage vert compris.
Le registre **grince** à chaque lettre.

→ **Message 8 : `ClientKeyExchange`, puis `CertificateVerify` (mTLS).** Le client envoie **sa part publique
ECDHE**. Les deux camps calculent alors **chacun de leur côté** le secret partagé, puis en dérivent le
`master_secret` et les clés de session. **Le secret ne circule jamais sur le fil** — c'est toute la magie
de Diffie-Hellman, et c'est la raison de la **PFS** : les deux moitiés sont jetables. **Ensuite seulement**,
en mTLS, vient le `CertificateVerify` : le client **signe le transcript** de tout le handshake. ⚠️ **L'ordre
compte** : `CertificateVerify` arrive **après** `ClientKeyExchange`, jamais avant — il doit signer un
transcript qui contient déjà la demi-clé du client. Même logique qu'au message 4, dans l'autre sens : le
certificat ne prouve rien, **la signature prouve**.

## 9. La salle de bain — `ChangeCipherSpec` + `Finished` du client

Tu ouvres le robinet et il en sort une **mousse blanche opaque** qui envahit la pièce en gargouillant et
**avale tout ce qu'elle touche** — plus rien n'est visible. Depuis l'intérieur de la mousse, tu **hurles
dans le pommeau de douche**, qui te **récite en écho toute la conversation** depuis la porte d'entrée,
compressée en une seule phrase incompréhensible.

→ **Message 9 : `ChangeCipherSpec` + `Finished` (client).** Le `ChangeCipherSpec` annonce : « **tout ce que
j'envoie après cette ligne est chiffré** » (la mousse opaque). Le `Finished` est le **premier message
chiffré**, et il contient un **hash de la totalité du handshake** (l'écho du pommeau) : si un attaquant a
modifié un seul octet en route — pour forcer une suite faible, par exemple — les hash divergent et la
connexion casse. **C'est la protection anti-downgrade.**

## 10. La chambre — `ChangeCipherSpec` + `Finished` du serveur

Le majordome est **déjà couché**, bordé jusqu'au menton. Il répond par **la même mousse blanche** et **le
même écho récité**, d'une voix endormie. Puis, sans se lever, il te tend une **pizza en forme d'accolade
JSON**, brûlante.

→ **Message 10 : `ChangeCipherSpec` + `Finished` (serveur).** Symétrique du 9. Et **seulement après**, la
première `application_data` — la requête HTTP, la pizza JSON. **Deux allers-retours complets avant le
premier octet utile** : c'est exactement ce que TLS 1.3 va supprimer.

---

## Ce que TLS 1.3 fait de ce parcours

Ne fabrique pas un second palais. **Modifie celui-ci**, c'est plus rapide et ça grave la différence :

| Emplacement | En TLS 1.3 |
|---|---|
| **1. Porte** | le gamin **jette déjà sa demi-clé verte** avec les 32 dés → `key_share` dans le `ClientHello` |
| **2. Couloir** | le majordome jette la sienne **immédiatement** → les clés sont dérivées **tout de suite** |
| **3-4-5. Cuisine, table, canapé** | **noyés dans la mousse blanche** : à partir du couloir, tout est chiffré. Le certificat n'est plus visible d'un observateur |
| **4. Table** | la signature existe toujours, mais s'appelle **`CertificateVerify`** |
| **6. Fenêtre** | **le gong disparaît** : plus de `ServerHelloDone` |
| **8. Bibliothèque** | **l'étagère ne pivote plus** : la demi-clé du client était déjà partie à l'emplacement 1. Seul le **bras mécanique** subsiste, en mTLS (`CertificateVerify` du client) |
| **9-10.** | `ChangeCipherSpec` n'est plus qu'un **figurant** conservé pour ne pas effrayer les boîtiers intermédiaires |

**Résultat, et de 2 RTT à 1 RTT** : sans mTLS, le parcours passe de **8 emplacements** (1-2-3-4-6-8-9-10)
à **6** (la fenêtre et la bibliothèque disparaissent) ; avec mTLS, de **10 à 9**. L'image à garder : en 1.3,
**le gamin arrive avec sa demi-clé à la main**, et la mousse blanche envahit la maison **dès le couloir**.

---

## Parcours de récitation

Dis-le d'un trait, en marchant :

> **Le gamin en ciré jaune** hurle à la **porte** et jette ses 32 dés ; le **majordome violet** dans le
> **couloir** jette les siens et poinçonne une seule carte ; le **frigo** de la **cuisine** vomit la
> guirlande de badges dont la dernière carte est déjà au mur ; sur la **table** il pose sa demi-clé verte et
> la signe en transperçant le bois ; sous le **canapé** le douanier orange réclame *tes* papiers — parfois ;
> à la **fenêtre** le gong rouge annonce qu'il a fini de parler ; au **bureau** tu jettes ton badge sur le
> sous-main ; à la **bibliothèque** l'étagère pivote, ta demi-clé claque sur la sienne en formant un nuage
> vert qui disparaît, **puis** le bras mécanique te force à signer le registre de tout ce qui s'est dit ;
> dans la **salle de bain** la mousse opaque avale
> tout pendant que le pommeau récite la conversation ; dans la **chambre**, le majordome couché répond la
> même mousse, le même écho, et te tend la pizza JSON.

**Test de solidité (à faire avant de fermer le fichier) :**

1. Récite les 10 dans l'ordre, à voix haute, en 40 secondes.
2. **Récite-les à l'envers**, de la chambre à la porte. Si l'envers passe, c'est ancré.
3. Réponds sans réfléchir : « **c'est quoi le 4 ?** » → *table, demi-clé signée, la plume transperce* →
   `ServerKeyExchange`, **la preuve de possession de la clé privée**.
4. Réponds : « **qu'est-ce qui n'existe qu'en mTLS ?** » → **5** (le canapé : le douanier), **7** (le
   bureau : ton badge) et **le bras mécanique de la bibliothèque** (le registre = `CertificateVerify` du
   client, signé **après** la demi-clé). Aucun emplacement ne disparaît en mTLS : ils s'ajoutent.
5. Réponds : « **où tombe la frontière entre RTT 1 et RTT 2 ?** » → **après la fenêtre** (emplacement 6).
