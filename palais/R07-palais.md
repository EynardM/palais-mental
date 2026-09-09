# Palais mental R07 — Les 10 étapes d'une résolution DNS complète

> **La liste à ancrer** : les **10 étapes d'une résolution DNS de bout en bout**, dans l'ordre exact, depuis
> l'appel de ton programme jusqu'à l'ouverture du socket. C'est la question d'entretien n°1 du module
> (« raconte-moi ce qui se passe quand je tape une URL ») et c'est aussi ta procédure de débogage : tu
> ne cherches pas « où est le problème », tu **marches** dans les dix étapes et tu t'arrêtes là où ça bloque.
>
> Dix étapes, dix emplacements. Ça tombe juste.
>
> **Phrase d'amorce, à te dire avant de partir** : « **je marche pour la résolution DNS** ». Elle active le
> bon jeu d'images et évite les collisions avec les listes des autres modules qui vivent dans le même
> appartement (l'en-tête IPv4 de R03, les états OSPF de R04, le best path BGP de R05).
>
> **Le fil rouge à ne jamais lâcher** : emplacements **1 à 5**, on est encore **chez soi** — rien n'est
> parti sur le réseau, tout se joue dans des fichiers et des caches. Emplacements **6 et 7**, on te dit
> **NON, va voir ailleurs** (délégation). Emplacement **8**, enfin **OUI** (autorité). Emplacements 9 et 10,
> on **range et on part**. Cinq à la maison, deux refus, un oui, deux pour finir.

---

## 1. La porte d'entrée — `getaddrinfo()` et l'ordre des sources

Ta sonnette ne sonne plus. Quand tu appuies, elle **récite d'une voix de GPS enrhumé** : « *files… dns…
files… dns…* ». Derrière la porte, un **huissier en robe noire** brandit un classeur à onglets numérotés et
te hurle au visage : « **DANS QUEL ORDRE ?! DANS QUEL ORDRE ?!** » Il refuse de te laisser passer tant que tu
n'as pas récité la liste dans le bon sens.

→ **Étape 1 : l'application appelle `getaddrinfo()`, qui suit `/etc/nsswitch.conf`.** Ce n'est pas encore du
DNS : c'est la couche NSS qui décide **dans quel ordre** consulter les sources. `hosts: files dns` — les
fichiers d'abord, le DNS ensuite. C'est pour ça que `ping` et `dig` ne résolvent pas pareil : `dig` saute
directement à l'étape 3, l'huissier ne le voit jamais.

## 2. Le couloir — `/etc/hosts`

Le couloir est barré par un **post-it manuscrit géant, rose fluo, de deux mètres de haut**, scotché de
travers. Il te **gifle au passage** avec un claquement sec en gueulant : « **MOI D'ABORD !** ». Ce qui est
écrit dessus est faux, périmé, écrit au marqueur qui bave — et personne ne le corrige jamais.

→ **Étape 2 : `/etc/hosts` est consulté AVANT le DNS.** Une entrée statique court-circuite toute la suite,
sans laisser aucune trace dans les logs DNS. C'est la première chose à vérifier devant un nom qui « pingue
mais ne digue pas ». Le post-it manuscrit, c'est exactement ça : une donnée écrite à la main, qui gagne.

## 3. La cuisine — `/etc/resolv.conf`

Sur la porte du frigo, un **répertoire téléphonique en néon vert clignotant** ne contient qu'**un seul
numéro** (le résolveur). À côté, une **roue de loterie** qui tourne en cliquetant, avec trois secteurs :
`ns.svc.cluster.local`, `svc.cluster.local`, `cluster.local`. Au-dessus, un compteur mécanique affiche en
rouge : « **5 POINTS** ».

→ **Étape 3 : le stub resolver lit `/etc/resolv.conf`** — quel `nameserver` interroger, quels suffixes
`search` essayer, et le fameux **`ndots:5`**. La roue qui tourne avant que tu puisses composer le vrai
numéro, c'est l'amplification des requêtes : trois essais inutiles avant le bon.

## 4. La table — la requête au résolveur, `RD=1`, UDP/53

Sur la table, un **enfant en pyjama jaune poussin** est debout, trépigne, et hurle : « **JE VEUX LA RÉPONSE
FINALE, PAS UN INDICE !** ». Il fourre une enveloppe estampillée d'un énorme **53** dans le bec d'un
**pigeon voyageur borgne**, qui décolle en renversant la carafe — et **personne ne te confirmera jamais**
qu'il est arrivé.

→ **Étape 4 : le stub envoie une requête RÉCURSIVE (`RD=1`) au résolveur, en UDP sur le port 53.** L'enfant
qui exige la réponse finale, c'est le bit RD. Le pigeon sans accusé de réception, c'est UDP : pas de
garantie, d'où le `timeout:5 attempts:2` du client.

## 5. Le canapé — le cache du résolveur

Enfoncé dans le canapé, un **hamster orange de la taille d'un labrador** aux **joues démesurément gonflées**.
Il recrache des réponses déjà mâchées, tièdes, à toute vitesse. Sur chacune de ses joues est collé un
**sablier qui fond à vue d'œil**. Quand un sablier atteint zéro, il **recrache la boulette par la fenêtre**
en couinant.

→ **Étape 5 : le résolveur récursif consulte SON cache.** S'il a la réponse, tout s'arrête ici — c'est le cas
dans la grande majorité des résolutions, en moins d'une milliseconde. Les sabliers, ce sont les **TTL** :
chaque enregistrement est gardé sa durée propre, puis jeté. **Tant que le hamster a des joues pleines, les
étapes 6, 7 et 8 n'ont jamais lieu.**

## 6. La fenêtre — les serveurs racine

Par la fenêtre, tu vois un **arbre planté à l'envers**, racines en l'air, qui grince au vent. **Treize
corbeaux** numérotés de **a à m** y sont perchés et croassent tous en même temps : « **PAS CHEZ NOUS !
DEMANDE AU POINT-EFF-ERRE !** ». L'un d'eux te lance une **carte de visite déjà pré-remplie avec une
adresse**, qui te tombe dans le col.

→ **Étape 6 : le résolveur interroge un serveur RACINE.** Il ne connaît aucun `www`, il ne sait qu'une
chose : à qui appartient chaque TLD. Il répond par une **délégation** (`NS` en section AUTHORITY), sans le
bit AA. Les **13 noms** `a` à `m.root-servers.net`, en anycast. La carte pré-remplie, ce sont les **glue
records** en section ADDITIONAL — sans eux, il faudrait résoudre le nom du serveur pour joindre le serveur.

## 7. Le bureau — les serveurs de TLD

À ton bureau siège un **fonctionnaire à moustache bleu électrique**, derrière un guichet en plexiglas
marqué « **.FR** ». Il **tamponne** bruyamment ta demande — *BANG, BANG* — puis, sans lever les yeux :
« **NS1 ET NS2. TROISIÈME ÉTAGE.** ». Et il glisse sous la vitre un **second post-it avec leur adresse**.

→ **Étape 7 : le résolveur interroge un serveur du TLD.** Deuxième renvoi, même mécanique : une délégation
vers les serveurs autoritatifs de la zone, plus la glue. Toujours **pas** de bit AA. Deux étages de « ce
n'est pas moi » — c'est ce qui fait qu'une résolution à froid coûte 40 à 150 ms.

## 8. La bibliothèque — le serveur autoritatif

Au fond de la bibliothèque, un **bibliothécaire coiffé d'une couronne dorée** abat un tampon gros comme une
enclume en beuglant : « **A-A ! C'EST MOI QUI L'ÉCRIS !** ». Le sol tremble. Il te tend enfin **la fiche avec
l'adresse dessus** — le premier de tout le parcours qui **répond** au lieu de te renvoyer.

→ **Étape 8 : le serveur AUTORITATIF répond, avec le bit `AA=1`.** Il détient la zone. C'est le seul point du
parcours qui produit une vraie donnée. Si tu veux court-circuiter tous les caches pendant un débogage, c'est
lui que tu interroges directement : `dig @ns1.exemple.fr`.

## 9. La salle de bain — la mise en cache selon le TTL

Dans la baignoire flottent des **glaçons numérotés au feutre : 300, 3600, 86400, 172800**. Ils **fondent en
sifflant** comme de l'eau sur une plaque brûlante. Le hamster du canapé déboule en glissant sur le carrelage,
les ramasse à pleines pattes et court les ranger dans ses joues.

→ **Étape 9 : le résolveur met en cache CHAQUE enregistrement obtenu, avec SON propre TTL.** Le A du service
pour 300 s, les NS de la zone pour 86 400 s, la délégation du TLD pour 172 800 s. **C'est pour ça qu'il ne
repassera plus par la racine.** Et c'est exactement là que se joue toute migration DNS : ces glaçons-là
fondront à leur rythme, quoi que tu changes chez toi.

## 10. La chambre — la réponse au stub, puis `connect()`

Sur ton lit, ton **téléphone vibre si fort qu'il tombe par terre**, et l'adresse IP s'affiche en chiffres
géants au plafond. Du balcon part un **grappin** qui siffle dans l'air et se plante dans un immeuble à
l'horizon, avec un **CLANG** métallique. Une **étiquette rouge** pend au bout du câble : le nom du site,
écrit dessus en toutes lettres.

→ **Étape 10 : le résolveur rend l'adresse au stub, l'application ouvre le socket.** Handshake TCP vers le
port 443, puis TLS avec le **SNI** — l'étiquette au bout du grappin, qui porte encore le **nom** alors qu'on
navigue déjà à l'adresse. **Une fois le câble tendu, le DNS n'a plus son mot à dire** : c'est pour ça qu'un
changement d'enregistrement ne déplace jamais une connexion déjà établie.

---

## Le parcours de récitation, en une phrase

> L'**huissier** de la porte hurle dans quel ordre chercher, le **post-it** du couloir te gifle « moi
> d'abord », le **répertoire néon** de la cuisine te donne un seul numéro et trois suffixes, l'**enfant en
> pyjama** debout sur la table exige la réponse finale et lâche son pigeon 53, le **hamster** du canapé
> recrache peut-être la réponse avant tout le monde, les **treize corbeaux** de la fenêtre croassent « va
> voir le point-fr », le **fonctionnaire moustachu** du bureau tamponne et renvoie au troisième étage, le
> **bibliothécaire couronné** de la bibliothèque abat enfin son tampon AA, les **glaçons numérotés** de la
> salle de bain fondent chacun à son rythme dans les joues du hamster, et le **grappin** de la chambre part
> se planter au loin avec le nom encore accroché au bout.

## Tests

1. **À l'endroit** : récite les 10 étapes en marchant. Objectif : sans hésitation, en moins de 60 s.
2. **À l'envers**, du 10 au 1. Impossible par mémoire de liste, facile par le parcours. Si l'envers passe,
   c'est ancré.
3. **Par sondage** : « c'est quoi le 7 ? » → *le TLD, deuxième délégation, toujours pas de AA*. La réponse
   doit être immédiate.
4. **En débogage** : pars d'un vrai symptôme (« le nom ne résout pas depuis ce pod ») et marche dans les dix
   emplacements en nommant, à chaque étape, la commande qui la teste — `getent hosts`, `cat /etc/hosts`,
   `cat /etc/resolv.conf`, `dig @<résolveur>`, `dig +trace`, `dig @<autoritatif>`. C'est l'usage le plus
   rentable de ce palais.
