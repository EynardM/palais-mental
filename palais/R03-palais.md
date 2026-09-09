# Palais mental R03 — L'en-tête IPv4, champ par champ dans l'ordre

> **La liste à ancrer** : les 14 champs de l'en-tête IPv4, **dans l'ordre de lecture du paquet**.
> C'est une liste ordonnée, longue, sans logique interne évidente — exactement le cas où le palais
> est rentable (cf. `palais/00-mes-lieux.md` §7).
>
> Les champs sont regroupés en 10 scènes : les deux premiers partagent le même octet, et les deux
> adresses + Options partagent la fin du paquet. Une scène = un emplacement = un bloc de l'en-tête.
>
> **Avant de partir, dis-toi la phrase d'amorce** : « je marche pour l'en-tête IPv4 ».
> Elle active le bon jeu d'images et évite les collisions avec les autres listes du même lieu.

---

## 1. La porte d'entrée — Version (4 b) + IHL (4 b)

Un **énorme 4 en néon fluo orange** est vissé sur la porte et **grésille**. Juste dessous, **cinq
paillassons** empilés, et à chaque fois que tu poses le pied dessus ils **claquent comme des dominos** :
*clac-clac-clac-clac-clac*. Tu comptes malgré toi : cinq.

→ **Version = 4** · **IHL = 5**, et 5 mots de 4 octets = **20 octets d'en-tête**. Le premier octet du
paquet est `0x45` : le 4 en néon, les 5 paillassons.

## 2. Le couloir — DSCP (6 b) + ECN (2 b)

Le couloir est devenu un **tapis rouge de festival**. Un videur en costume violet **hurle « EF !
QUARANTE-SIX ! »** et pousse les invités dans **six files** différentes. Au bout du couloir, **deux petites
ampoules vertes** clignotent ; quand la foule s'entasse, elles virent au **rouge vif** et une sonnerie
retentit.

→ **DSCP sur 6 bits**, valeur **46 = EF** (la file prioritaire, la voix). **ECN sur 2 bits** : les deux
ampoules, rouges quand c'est congestionné (**CE = `11`**).

## 3. La cuisine — Total Length (16 b)

Sur le plan de travail, une **balance de boucher géante en inox** avec un afficheur **rouge à sept
segments : 65535**. Tu y poses un colis ; la balance **beugle** parce qu'elle pèse **le colis ENTIER,
carton d'emballage compris**, et pas seulement ce qu'il y a dedans.

→ **Total Length = en-tête + données**, en octets, **maximum 65 535**. (Contrairement à IPv6, où le
Payload Length ne pèse que le contenu.)

## 4. La table — Identification (16 b)

Une **machine à étiqueter** posée sur la table crache en rafale des **étiquettes de bagage jaunes**, toutes
**tamponnées du même numéro**. Tu déchires une valise en quatre morceaux et tu colles la **même étiquette**
sur chaque morceau. *Clac, clac, clac, clac.*

→ **Identification** : le même numéro sur **tous les fragments d'un même paquet**, pour les recoller à
l'arrivée.

## 5. Le canapé — Flags (3 b) : DF et MF

Dans le canapé, deux **coussins-panneaux lumineux**. Le premier, **jaune fluo** : « **DÉFENSE DE
FRAGMENTER** ». Le second, **bleu clignotant** : « **Y EN A ENCORE !** » — et il s'allume à chaque coussin
que tu balances à travers la pièce, **sauf pour le tout dernier**, où il s'éteint dans un silence brutal.

→ **DF = Don't Fragment** (« Défense de Fragmenter »). **MF = More Fragments**, à 1 partout **sauf sur le
dernier fragment**. Le troisième bit est réservé — c'est le coussin gris que personne ne touche jamais.

## 6. La fenêtre — Fragment Offset (13 b)

La fenêtre est **quadrillée de petits carreaux**, et sur chaque carreau un peintre en salopette verte a
peint un numéro qui **saute de 8 en 8** : 0, 8, 16, 24… Il recule, admire, et **hurle
« CENT-QUATRE-VINGT-CINQ ! »** en tapant sur la vitre.

→ **Fragment Offset en unités de 8 octets**. Un offset de **185** = octet **1480** du paquet d'origine —
le début du deuxième fragment quand on découpe pour un MTU de 1500.

## 7. Le bureau — TTL (8 b)

La lampe de bureau porte un **compteur mécanique** qui décrémente à voix haute : **64… 63… 62…** À chaque
fois que tu passes la main devant, il **perd un cran**. Quand il arrive à **zéro**, la lampe **explose en
confettis orange** en criant « **ONZE !** ».

→ **TTL**, initialisé à **64** sous Linux, **−1 par routeur**. À zéro : le paquet meurt et un **ICMP
type 11** (Time Exceeded) part vers la source. C'est le moteur de `traceroute`.

## 8. La bibliothèque — Protocol (8 b)

L'étagère est vide sauf **trois gros livres** posés côte à côte, numérotés à la peinture blanche sur la
tranche : **1**, **6**, **17**. Ils **se disputent bruyamment** : le 1 couine, le 6 parle posément et
lentement, le 17 crie tout ce qui lui passe par la tête sans écouter personne.

→ **Protocol : 1 = ICMP** (il couine, il signale les erreurs), **6 = TCP** (posé, fiable, ordonné),
**17 = UDP** (il envoie sans vérifier). Les trois numéros à ne jamais rater.

## 9. La salle de bain — Header Checksum (16 b)

Le **miroir refait entièrement ta tête** chaque fois que tu franchis la porte — **ta tête seulement**, ton
corps reste flou et intact. À chaque passage : un **« BIP » de caisse de supermarché**, strident.

→ **Checksum de l'en-tête uniquement**, jamais des données, et **recalculé à chaque saut** puisque le TTL
vient de changer. IPv6 a fait sauter ce miroir : il n'a plus de checksum d'en-tête.

## 10. La chambre — Adresses source et destination (32 b × 2) + Options

Deux **adresses postales géantes** sont peintes au mur, l'une au-dessus de l'autre. Elles sont
**indécollables** : tu grattes, tu tires, rien ne bouge — sauf si un plombier arrive avec un **décapeur
thermique marqué « NAT »**, qui les efface et en repeint d'autres. Sous le lit, une **valise vide et
poussiéreuse** étiquetée « **OPTIONS — jamais servi** ».

→ **Adresse source puis adresse destination**, 32 bits chacune, **inchangées de bout en bout sauf NAT**.
Puis les **Options** (0 à 40 octets), qui n'existent quasiment jamais — mais qui justifient à elles seules
le champ IHL du paillasson n°1.

---

## Parcours de récitation (une seule phrase enchaînée)

> Le **4 en néon** grésille au-dessus des **cinq paillassons** de la porte, je longe le **tapis rouge** où
> le videur hurle « EF quarante-six » entre **deux ampoules** qui rougissent, j'entre en cuisine où la
> **balance** affiche **65535** en pesant le carton entier, je pose sur la table les **étiquettes jaunes**
> toutes identiques, je m'écroule sur les coussins « **Défense de fragmenter** » et « **Y en a encore** »,
> je regarde par la fenêtre les **carreaux numérotés de 8 en 8** jusqu'à cent-quatre-vingt-cinq, je passe au
> bureau où la lampe **décompte 64, 63, 62** avant d'exploser en criant **onze**, j'attrape à la
> bibliothèque les **livres 1, 6 et 17** qui s'engueulent, je croise dans la salle de bain le **miroir qui
> ne refait que ma tête en bipant**, et je finis dans la chambre devant les **deux adresses indécollables**
> et la **valise vide des Options**.

**Test de solidité** : refais le parcours **du 10 vers le 1**. Si la marche arrière passe sans hésitation,
c'est ancré. Puis vérifie que tu sais dire, sans le parcours, **le nombre de bits de chaque champ** — c'est
la couche d'information que le palais te rend le plus lentement.

---

> **Ce qui ne mérite PAS un palais dans ce module** : les 8 valeurs légales d'un octet de masque
> (128, 192, 224, 240, 248, 252, 254, 255). Elles se déduisent par arithmétique — chacune est la précédente
> **plus la puissance de 2 suivante en descendant** (+64, +32, +16, +8, +4, +2, +1). Une règle de calcul
> bat toujours une liste mémorisée : garde-la en flashcard, pas en palais.
