# PALAIS R01 — Les 7 couches OSI (+ les chiffres clés)

> Parcours standard, 10 emplacements (cf. `palais/00-mes-lieux.md`) :
> 1. porte d'entrée · 2. couloir · 3. cuisine · 4. table · 5. canapé · 6. fenêtre · 7. bureau · 8. bibliothèque · 9. salle de bain · 10. chambre.
>
> **Emplacements 1 à 7 = les 7 couches OSI, dans l'ordre.** Le numéro de l'emplacement EST le numéro de la couche : la porte d'entrée est la couche 1, le bureau est la couche 7. Ne casse jamais cette correspondance, c'est elle qui te fait répondre instantanément à « la couche 4, c'est laquelle ? ».
> **Emplacements 8 à 10** = les trois blocs de chiffres et d'exceptions qui ne se retiennent pas seuls.

---

## 1. Porte d'entrée → COUCHE 1 : PHYSIQUE

**L'image.** Ta porte d'entrée n'est plus une porte : c'est un **câble RJ45 orange fluo de deux mètres de haut**, planté verticalement dans le chambranle, qui **vibre et grésille**. La poignée est en cuivre nu ; dès que tu la touches, des **étincelles bleu électrique** te remontent le bras en crépitant, et un **bourdonnement de 50 Hz** fait trembler le mur. Ça sent le métal chaud. Il n'y a **aucun nom, aucune adresse** écrite nulle part — juste des éclairs.

**Lien → notion.** Le geste devient courant électrique : la couche 1 transforme les **bits en signal**, et ne connaît **aucune adresse**.

---

## 2. Couloir → COUCHE 2 : LIAISON DE DONNÉES

**L'image.** Le couloir est bordé de **facteurs jumeaux en gilet jaune**, épaule contre épaule. Chacun a un **code-barres hexadécimal tatoué sur le front** : `aa:bb:cc:00:00:01`. Ils se passent un colis **de main en main, un seul pas chacun**, en hurlant « **SUIVANT !** » à chaque transfert. Au bout du couloir, un **chien-robot chromé** renifle chaque colis : soit il aboie « **CRC OK !** », soit il le **déchiquette en confettis sans rien dire à personne**.

**Lien → notion.** Tatouages hexadécimaux = **adresses MAC (48 bits)**. Un pas chacun = **un seul saut**. Le chien qui déchiquette en silence = le **FCS** : trame corrompue → jetée, aucune retransmission à ce niveau.

---

## 3. Cuisine → COUCHE 3 : RÉSEAU

**L'image.** Sur le plan de travail, une **cocotte-minute géante siffle** et projette au plafond un **hologramme tournant de la carte du monde**. Un **chef à quatre bras** tamponne chaque plat d'une étiquette rouge « **10.0.2.20** », consulte l'hologramme une demi-seconde, et **balance le plat dans l'un des trois monte-plats** du fond. Au-dessus de sa tête, un **compteur mécanique rouge claque** : **64… 63… 62…** et quand il atteint 0, le plat **explose** en fumée et une carte postale ICMP s'envole.

**Lien → notion.** Étiquette = **adresse IP globale**. Choisir le monte-plat = **routage**. Compteur qui claque = **TTL décrémenté par chaque routeur** (64 par défaut sous Linux), et à 0 → paquet jeté + **ICMP Time Exceeded**.

---

## 4. Table → COUCHE 4 : TRANSPORT

**L'image.** La table de la salle à manger est percée de **65 535 minuscules tiroirs numérotés**, en laiton. Deux serveurs se disputent le service. Le premier, en **costume noir marqué TCP**, compte chaque assiette à voix haute — « **segment 1… accusé de réception !… segment 2…** » —, rattrape au vol celles qui tombent et **refuse d'en apporter plus tant que le convive n'a pas fait signe**. Le second, en **short fluo marqué UDP**, **balance les assiettes par-dessus son épaule sans regarder**, en sifflotant, et ne se retourne jamais.

**Lien → notion.** Tiroirs numérotés = les **ports sur 16 bits (0 à 65 535)**. Le serveur qui compte et rattrape = **TCP** (séquence, ACK, retransmission, contrôle de flux). Le siffleur = **UDP** : rien de tout ça, 8 octets d'en-tête et basta.

---

## 5. Canapé → COUCHE 5 : SESSION

**L'image.** Sur ton canapé, deux **vieux téléphones à cadran en bakélite** sont scotchés l'un contre l'autre par un **fil rouge tendu à claquer**. Un **majordome en livrée** allume une **bougie parfumée** au début de la conversation, tamponne un ticket « **REPRISE ICI** » toutes les dix secondes dans un grand **CLAC** de tampon encreur, et **souffle la bougie** pile quand le dialogue se termine — jamais avant.

**Lien → notion.** Bougie allumée/soufflée = **ouverture et fermeture ordonnée** du dialogue. Tampon « REPRISE ICI » = **points de synchronisation et de reprise**. C'est tout ce que fait la couche session.

---

## 6. Fenêtre → COUCHE 6 : PRÉSENTATION

**L'image.** La vitre de ta fenêtre est un **traducteur simultané dément**. Tout ce qui passe devant ressort **d'abord en emoji, puis en morse qui bipe, puis en soupe de caractères verts qui dégoulinent verticalement** comme dans Matrix. Vissé au centre du carreau, un **gros cadenas doré grince** à chaque passage et **compresse** ce qui traverse en un petit cube qui fait « **pop** ».

**Lien → notion.** Traduction en cascade = **encodage et sérialisation** (UTF-8, ASN.1, JPEG). Cadenas doré = **chiffrement, donc TLS**, rangé ici par convention. Le cube qui fait pop = **compression**.

---

## 7. Bureau → COUCHE 7 : APPLICATION

**L'image.** Sur ton bureau, un **perroquet en costume trois-pièces** se tient debout sur le clavier et **hurle** dans l'écran : « **GET SLASH INDEX POINT HTML, HTTP UN POINT UN !** ». L'écran lui répond en **crachant des confettis dorés** sur lesquels est imprimé « **200 OK** ». À côté, un **annuaire téléphonique géant se feuillette tout seul** en claquant les pages et gueule « **example point com, c'est 93.184.216.34 !** ».

**Lien → notion.** Le perroquet qui parle un protocole = **la couche 7, c'est le protocole (HTTP), pas le programme**. L'annuaire qui se feuillette = **DNS**.

---

## 8. Bibliothèque → LES TAILLES D'EN-TÊTES : 14 / 20 / 20 / 8

**L'image.** Quatre rayonnages, quatre couleurs. Le premier : **14 encyclopédies orange** marquées **ETHERNET**. Le deuxième : **20 volumes bleus IP**. Le troisième : **20 volumes verts TCP**. Le dernier : seulement **8 fascicules jaunes UDP**, si fins qu'ils tiennent debout tout seuls. Un **bibliothécaire hystérique** t'empile les trois premières piles sur la tête en scandant « **QUA-TORZE ! VINGT ! VINGT !** », et au moment où tu plies sous le poids, un **néon rouge s'allume au plafond : 54**.

**Lien → notion.** **Ethernet 14 o, IP 20 o, TCP 20 o, UDP 8 o.** Le néon : **14 + 20 + 20 = 54 octets** d'en-têtes pour transporter le moindre octet en TCP/IPv4 sur Ethernet.

---

## 9. Salle de bain → MTU 1500, MSS 1460, FRAGMENTATION

**L'image.** La baignoire est remplie **exactement à 1500 litres**, trait rouge au feutre sur l'émail. Dedans flotte un **canard en plastique jaune de 40 litres** qui **couine sans arrêt « JE SUIS LES EN-TÊTES ! »** — du coup il ne reste que **1460 litres d'eau utile**. Si tu ajoutes **une seule goutte**, une **sirène de sous-marin** se déclenche, la bonde s'ouvre et **recrache un panneau plastifié : « ICMP 3 / 4 »**, pendant que la baignoire se **coupe en trois morceaux de 8 litres pile** qui partent chacun de leur côté.

**Lien → notion.** Baignoire = **MTU 1500**. Canard de 40 = **IP 20 + TCP 20**. Eau utile = **MSS 1460**. La goutte de trop = **fragmentation**, découpée en **multiples de 8 octets**, ou bien **ICMP type 3 code 4** si DF=1.

---

## 10. Chambre → LES 3 FUITES DU MODÈLE : TLS, VXLAN, QUIC

**L'image.** Trois intrus sont dans ton lit, sous la couette. À gauche, un **espion en smoking** chiffre tout ce qu'il touche et **répète en boucle « je n'ai pas de chambre attitrée, je dors entre deux étages »**. Au milieu, une **poupée russe géante** ouvre la bouche et **recrache un camion Ethernet entier, phares allumés**, qu'elle fourre dans une **enveloppe kraft marquée UDP 4789**. À droite, un **athlète en survêtement** défonce la fenêtre en criant « **JE FAIS LE TRANSPORT MOI-MÊME, EN ESPACE UTILISATEUR, SUR UDP 443 !** ».

**Lien → notion.** L'espion sans chambre = **TLS**, coincé entre la couche 4 et la couche 7. La poupée qui recrache un camion dans une enveloppe = **VXLAN**, une trame L2 encapsulée dans de l'UDP (port **4789**, **50 octets** d'overhead). L'athlète qui saute par la fenêtre = **QUIC**, le transport remonté en espace utilisateur sur **UDP 443**.

---

## Parcours de récitation

**En une phrase enchaînée, à réciter à voix haute :**

> Je pousse la **porte-câble qui grésille** *(1 physique)*, je longe le **couloir des facteurs tatoués en hexadécimal** *(2 liaison)*, j'entre dans la **cuisine où le chef à quatre bras étiquette les plats et décompte 64** *(3 réseau)*, je m'assieds à la **table aux 65 535 tiroirs entre le serveur qui compte et celui qui siffle** *(4 transport)*, je m'affale sur le **canapé où le majordome allume et souffle la bougie** *(5 session)*, je regarde par la **fenêtre qui traduit tout en Matrix derrière un cadenas doré** *(6 présentation)*, je m'installe au **bureau où le perroquet en costume hurle GET slash index** *(7 application)*, je passe à la **bibliothèque et le bibliothécaire m'empile quatorze-vingt-vingt sur la tête** *(en-têtes, total 54)*, je file à la **salle de bain où le canard de 40 litres flotte dans les 1500 litres** *(MTU/MSS 1460)*, et je finis dans la **chambre avec l'espion sans chambre, la poupée qui recrache un camion et l'athlète qui saute par la fenêtre** *(TLS, VXLAN, QUIC)*.

**Variante haut → bas.** Fais le parcours **à l'envers**, de la chambre vers la porte : tu obtiens l'ordre de l'**encapsulation**, celui dans lequel les en-têtes s'empilent quand tu descends la pile (7 → 1). Entraîne-toi dans les deux sens : en entretien on te demande un numéro de couche, pas une liste.

**Contrôle en 20 secondes.** Cite l'emplacement 4 → table → **transport**. Emplacement 6 → fenêtre → **présentation**. Emplacement 2 → couloir → **liaison**. Si les trois sortent sans hésitation, le palais est posé.
