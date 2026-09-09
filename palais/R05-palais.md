# Palais mental R05 — L'ordre de sélection du meilleur chemin BGP

> **La liste à ancrer** : les **10 critères de sélection du meilleur chemin BGP**, dans l'ordre exact
> d'application. C'est le cas d'école du palais : liste longue, ordre strictement séquentiel, aucune
> logique interne qui permettrait de la reconstruire, et une erreur d'ordre donne une mauvaise réponse
> en entretien comme en production.
>
> Dix critères, dix emplacements. Ça tombe juste, profite-s-en.
>
> **Avant de partir, dis-toi la phrase d'amorce** : « **je marche pour le best path BGP** ».
> Elle active le bon jeu d'images et évite les collisions avec les listes des autres modules
> (l'en-tête IPv4 de R03, les états OSPF de R04) qui vivent dans le même appartement.
>
> **Le fil rouge à ne jamais lâcher** : les emplacements **2 et 3** (couloir, cuisine) veulent la valeur
> **la plus GRANDE**. Tous les autres chiffres veulent la plus **PETITE**. Deux pièces qui montent, le
> reste qui descend.

---

## 1. La porte d'entrée — le NEXT_HOP doit être joignable

Ta porte d'entrée n'a plus de serrure : à la place, un **videur en costume fluo vert** avec une
oreillette. Il ne te laisse pas entrer, il **hurle dans son micro** : « **T'AS UNE ADRESSE OÙ ALLER,
TOI ?!** » Tu montres un papier avec une adresse. Il compose le numéro, ça sonne dans le vide —
*driiing… driiing…* — il déchire le papier en confettis et te **jette dehors**, portière claquée.

→ **Critère 0 : le NEXT_HOP doit être joignable.** Si le routeur ne sait pas atteindre le prochain saut
par une autre source (IGP, statique, connecté), la route est **éliminée avant même d'être comparée**. Elle
apparaît dans `show ip bgp` **sans le `*`**. C'est la panne n°1 en iBGP, et le remède s'appelle
`next-hop-self`.

> Le videur ne compare rien. Il **filtre**. C'est pour ça qu'il est à la porte, avant tout le reste.

## 2. Le couloir — WEIGHT, le plus GRAND

Le couloir est occupé par une **balance de pesée de camions**, en tôle jaune, qui **grince** sous le
poids. Un haltérophile russe en léotard rose y monte, lève **32 768 kg** au-dessus de sa tête et **rugit**.
Un post-it collé sur la balance : « **NE SORT PAS DE CETTE MAISON** ». Quand tu essaies de photographier
la balance, l'appareil affiche « erreur : appareil Cisco requis ».

→ **Critère 1 : le WEIGHT le plus GRAND gagne.** Ce n'est **pas un attribut BGP** : c'est une valeur
propriétaire **Cisco**, **locale au routeur**, jamais transmise à personne (le post-it). Défaut : **0**
pour une route apprise, **32 768** pour une route originée localement (l'haltérophile).

## 3. La cuisine — LOCAL_PREF, la plus GRANDE

Sur le plan de travail, une **cocotte-minute géante bleu électrique** siffle à s'en décrocher la
soupape. Son manomètre est bloqué sur **100**. Ton voisin de palier essaie de la faire monter à 200 en
soufflant dedans, mais **il n'a pas le droit de la sortir de l'appartement** : dès qu'il approche de la
porte, une chaîne la retient et tout le monde crie « **ELLE RESTE DANS L'AS !** ».

→ **Critère 2 : la LOCAL_PREF la plus GRANDE gagne.** Défaut **100**. Attribut *well-known
discretionary* de **type 5**, transmis en **iBGP** et **jamais en eBGP** — la chaîne à la porte. C'est le
levier n°1 pour piloter ton trafic **sortant**, et celui qui écrase l'AS-path prepending des autres.

## 4. La table — la route ORIGINÉE LOCALEMENT

Sur la table de la cuisine, ta **grand-mère** a posé un plat fumant et **tape sur la table avec une
cuillère en bois** : « **C'EST MOI QUI L'AI FAIT !** » À côté, un plat sous vide de supermarché, tout
tiède. Elle balance le plat industriel par la fenêtre — il fait *ploc* dans la cour.

→ **Critère 3 : une route originée localement est préférée.** Une route injectée par ce routeur
lui-même — commande `network`, `aggregate-address`, ou `redistribute` — passe avant une route apprise
d'un voisin. C'est fait maison, donc c'est mieux.

## 5. Le canapé — AS_PATH, le plus COURT

Le canapé s'est transformé en **file d'attente de préfecture**, en accordéon, qui traverse tout le salon.
Chaque personne dans la file porte un **maillot de foot numéroté d'un ASN** et **crie son numéro** en
passant : « *soixante-cinq-mille-un !* », « *deux-cent !* ». Un couloir voisin ne compte que **deux**
personnes. Tu choisis évidemment celui-là. Et au bout de la file courte, un **sac fourre-tout** contient
douze personnes entassées — mais le sac ne compte que pour **une**.

→ **Critère 4 : l'AS_PATH le plus COURT gagne.** On compte les **AS**, pas les routeurs. Le sac
fourre-tout, c'est l'**AS_SET**, qui ne compte que pour **1** quel que soit son contenu. Les segments de
confédération comptent pour **0**. C'est ici, et seulement ici, que l'**AS-path prepending** agit —
en 4ᵉ position, donc trop tard pour battre un LOCAL_PREF.

## 6. La fenêtre — ORIGIN, le plus BAS

À la fenêtre, **trois pigeons** alignés sur le rebord, dans cet ordre exact de gauche à droite :

- un pigeon **blanc immaculé** avec un badge « **i** », qui roucoule proprement ;
- un pigeon **gris poussiéreux** avec un badge « **e** », qui tousse ;
- un pigeon **borgne, dépenaillé**, badge « **?** », qui **crie et boite**.

Tu ouvres la fenêtre : le blanc entre en premier, le borgne reste dehors sous la pluie.

→ **Critère 5 : l'ORIGIN le plus BAS gagne.** **IGP (0) `i`** < **EGP (1) `e`** < **INCOMPLETE (2) `?`**.
Le `i` vient d'une commande `network` (propre), le `?` d'une **redistribution** (le pigeon borgne). Le
`e` est un vestige que tu ne verras jamais.

## 7. Le bureau — MED, le plus PETIT

Sur ton bureau, une **boîte à idées en carton orange fluo** avec l'inscription « **SUGGESTIONS DU
VOISIN** ». Un facteur en uniforme y glisse des enveloppes en **chuchotant** des chiffres — « *dix…
cinq…* » — mais un panneau vissé au mur clignote en rouge : « **ON NE COMPARE QUE LES ENVELOPPES DU MÊME
FACTEUR** ». Un deuxième facteur arrive, on **refuse de comparer** ses enveloppes aux premières. Et le
patron passe, prend une enveloppe et la **jette au panier** en haussant les épaules.

→ **Critère 6 : le MED le plus PETIT gagne.** Défaut **0**. C'est une **suggestion** faite au voisin
pour influencer le trafic **entrant** — il peut l'ignorer (le patron qui jette). Restriction capitale :
par défaut on ne compare le MED **qu'entre chemins reçus du MÊME AS voisin** (le même facteur), sauf
`bgp always-compare-med`.

## 8. La bibliothèque — eBGP bat iBGP

Deux rayonnages face à face. À gauche, des livres **reliés cuir rouge, poussiéreux, marqués « MAISON »**.
À droite, des livres **couverts de tampons de douane, autocollants d'aéroport, sable qui tombe des
pages**, marqués « **ÉTRANGER** ». Un bibliothécaire en uniforme de douanier **claque un tampon** sur le
rayon étranger : « **CELUI-CI D'ABORD !** » Les livres maison boudent en silence.

→ **Critère 7 : un chemin eBGP est préféré à un chemin iBGP.** Traduction logique : si un routeur voisin
d'un autre AS me donne le préfixe directement, autant sortir tout de suite plutôt que de traverser mon
propre réseau. Repère chiffré associé : distance administrative **eBGP 20**, **iBGP 200**.

## 9. La salle de bain — la métrique IGP la plus BASSE

Dans la baignoire, une **patate brûlante géante**, rouge vif, qui **fume et siffle**. Tu ne peux pas la
tenir : tu la lances par la **fenêtre la plus proche** en criant. Sur le mur, un plan du quartier avec
deux sorties : **Paris coût 10**, **Marseille coût 80**. Tu vises Paris sans réfléchir, parce que c'est
plus près et que **ça brûle**.

→ **Critère 8 : la métrique IGP la plus BASSE vers le NEXT_HOP gagne.** C'est le **hot potato routing** :
je me débarrasse du trafic par le point de sortie le plus proche au sens de mon IGP, parce que le
transporter me coûte. C'est aussi la cause structurelle du **routage asymétrique** — ton AS et l'AS
distant appliquent chacun *leur* patate chaude.

## 10. La chambre — le plus PETIT router-ID (et les départages finaux)

Dans la chambre, une **course d'escargots fluorescents** sur ta couette, chacun portant une **plaque
d'immatriculation à 4 chiffres**. Un arbitre en pyjama souffle dans un **sifflet strident** et proclame
dans cet ordre :

1. « **LE PLUS VIEUX D'ABORD !** » — un escargot ridé, couvert de mousse, gagne pour ancienneté.
2. « **SINON, LA PLUS PETITE PLAQUE !** » — il compare les immatriculations et prend la plus basse.
3. « **SINON, LA PLUS COURTE LAISSE !** » — certains escargots traînent une laisse de perles.
4. « **SINON, LA PLUS PETITE ADRESSE !** »

→ **Critère 9 — les départages finaux, dans l'ordre** : le chemin **eBGP le plus ancien** (pour la
stabilité : on ne bascule pas sans raison), puis le **plus petit router-ID du voisin**, puis la **plus
courte CLUSTER_LIST** (la laisse de perles des route reflectors), puis la **plus petite adresse IP de
voisin**.

---

## Parcours de récitation

Lis-la une fois à voix haute, puis reconstruis-la les yeux fermés en marchant :

> **À la porte**, le videur fluo hurle « t'as une adresse ? » et jette le papier *(next-hop joignable)* ;
> **dans le couloir**, l'haltérophile rose soulève 32 768 kg sur une balance qui ne sort jamais de la
> maison *(weight, le plus grand, local et Cisco)* ; **à la cuisine**, la cocotte bleue siffle à 100 et
> une chaîne l'empêche de quitter l'AS *(local pref, la plus grande)* ; **à la table**, grand-mère tape
> avec sa cuillère « c'est moi qui l'ai fait » et jette le plat industriel par la fenêtre *(route
> originée localement)* ; **sur le canapé**, la file de maillots numérotés crie ses ASN et le sac
> fourre-tout ne compte que pour un *(AS_PATH le plus court, AS_SET = 1)* ; **à la fenêtre**, le pigeon
> blanc `i` entre avant le gris `e`, et le borgne `?` reste sous la pluie *(origin le plus bas)* ; **au
> bureau**, la boîte à suggestions orange n'accepte que les enveloppes du même facteur, et le patron en
> jette une *(MED le plus petit, même AS voisin, ignorable)* ; **à la bibliothèque**, le douanier tamponne
> les livres étrangers avant ceux de la maison *(eBGP bat iBGP)* ; **dans la baignoire**, la patate
> brûlante part par la fenêtre la plus proche, Paris coût 10 *(métrique IGP la plus basse, hot potato)* ;
> **et dans la chambre**, l'arbitre en pyjama siffle : le plus vieux, sinon la plus petite plaque, sinon
> la plus courte laisse, sinon la plus petite adresse *(ancienneté, router-ID, cluster-list, IP)*.

**Contrôle en 20 secondes** — récite juste les initiales en marchant :
**N — W — L — O — A — O — M — E — I — R**
« **N**os **W**agons **L**ivrent **O**nze **A**nanas **O**range, **M**ais **E**lle **I**gnore **R**obert. »

**Contrôle du SENS** — la seule erreur qui reste possible une fois l'ordre acquis :
**couloir et cuisine MONTENT** (weight et local pref : le plus grand gagne).
**Tout le reste DESCEND** (AS_PATH, origin, MED, métrique IGP, router-ID : le plus petit gagne).

---

## Auto-test

Fais-le sans relire le parcours ci-dessus.

1. Emplacement **7** → quel critère, dans quel sens, avec quelle restriction ?
2. Quel emplacement porte l'**AS_PATH**, et quelle est sa position numérique dans l'algorithme ?
3. Quels sont les **deux** emplacements où la **plus grande** valeur gagne ?
4. Que fait le personnage de l'emplacement **1**, et pourquoi n'est-ce pas une comparaison ?
5. Parcours **à l'envers**, du 10 vers le 1, en nommant chaque critère.
6. Emplacement **6** : quels sont les trois pigeons, dans l'ordre, et que valent-ils ?
