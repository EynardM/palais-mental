# R04 — PALAIS MENTAL : les 8 états d'adjacence OSPF, dans l'ordre

> **Pourquoi un palais ici** : la montée en adjacence OSPF est une **liste ordonnée de 8 états** dont on te
> demandera la séquence exacte en entretien, et dont deux étapes (ExStart et Exchange) sont précisément
> celles où l'on se bloque en production. Une liste d'états ne se retient pas par relecture : elle se retient
> par **déplacement**. Les deux emplacements finaux ajoutent ce qui vient *après* Full — le calcul et
> l'installation de la route — pour que le parcours raconte l'histoire complète.
>
> **Parcours utilisé** : les 10 emplacements standard de `palais/00-mes-lieux.md` —
> 1. porte d'entrée · 2. couloir · 3. cuisine · 4. table · 5. canapé · 6. fenêtre · 7. bureau ·
> 8. bibliothèque · 9. salle de bain · 10. chambre.
>
> **Mode d'emploi** : lis chaque image **les yeux fermés**, en te plaçant physiquement à l'emplacement.
> Fais bouger l'image, mets-y de la couleur et du bruit. Puis refais le trajet sans le texte, et une fois
> **à l'envers** (10 → 1) : si l'envers passe, c'est ancré.

---

## La liste à ancrer

```
 DOWN → ATTEMPT → INIT → 2-WAY → EXSTART → EXCHANGE → LOADING → FULL
                                                                  │
                                            (9) DIJKSTRA / SPF ───┘
                                            (10) ROUTE INSTALLÉE (RIB → FIB)
```

---

## 1. Porte d'entrée — DOWN

**L'image** : ta porte d'entrée est **soudée**, peinte en gris terne, sans poignée ni sonnette. Tu tapes
dessus à coups de poing : **aucun son ne sort**, comme si le bois avalait le bruit. Un routeur en plastique
noir gît par terre devant, débranché, sa LED éteinte. Tu le pousses du pied : il fait *tchk*, rien de plus.

**Le lien** : **DOWN** — aucun Hello reçu, aucun voisin, silence total. L'état de départ.

## 2. Couloir — ATTEMPT

**L'image** : dans le couloir, un **standardiste en blouse orange fluo** compose frénétiquement un numéro
sur un vieux téléphone à cadran, en criant **un nom précis** : « MONSIEUR DUPONT ! MONSIEUR DUPONT ! ». Il
n'appelle personne d'autre — il a le numéro écrit sur sa main, et il ne fait **que** ce numéro. Ça sonne
dans le vide, *driiing… driiing…*, et il recommence.

**Le lien** : **ATTEMPT** — on envoie des Hello **unicast à un voisin configuré à la main** (le numéro sur la
main). N'existe **que sur les réseaux NBMA**, où le multicast est impossible. C'est le seul état optionnel
de la liste : sur de l'Ethernet, on passe directement de Down à Init.

## 3. Cuisine — INIT

**L'image** : dans la cuisine, un facteur passe la tête par la fenêtre et te tend une **carte postale
jaune vif**. Tu la retournes : il y a une **liste de noms** au dos… et **le tien n'y est pas**. Tu la
secoues, tu la mets à la lumière, tu cherches : rien. Le facteur, lui, hausse les épaules et repart en
sifflant. Tu restes là, la carte à la main, vexé.

**Le lien** : **INIT** — j'ai bien **reçu un Hello**, mais **je ne me vois pas** dans sa liste de voisins.
La communication ne va que dans un sens. *Rester bloqué ici = trafic unidirectionnel : ACL, mauvais VLAN,
authentification asymétrique.*

## 4. Table — 2-WAY

**L'image** : sur la table de la cuisine, **deux miroirs** se font face et se **serrent la main** — deux
mains qui sortent des miroirs et se secouent vigoureusement, *clac clac clac*. Au même instant, une
**couronne dorée** tombe du plafond en tournoyant et se pose sur le miroir de gauche ; une **couronne
argentée** suit et se pose sur celui de droite. Les autres objets de la table (salière, verres) restent
sagement à leur place et **ne se serrent la main avec personne**.

**Le lien** : **2-WAY** — je me vois dans son Hello, la bidirectionnalité est confirmée. Et c'est **ici, et
nulle part ailleurs, que se fait l'élection du DR (couronne dorée) et du BDR (couronne argentée)**. Les
objets qui ne bougent pas = les DROTHER, qui **restent en 2-Way**, et c'est parfaitement normal.

## 5. Canapé — EXSTART

**L'image** : sur le canapé, deux enfants se disputent la télécommande en hurlant **« C'EST MOI LE CHEF ! »**.
Le plus grand gagne. Puis, avant de commencer quoi que ce soit, ils sortent un **mètre ruban jaune** et
mesurent **la largeur du canapé** chacun de son côté. Le premier annonce « 1500 ! », le second « 9000 ! ».
Ils se figent, se regardent — et **tout s'arrête**. Le silence dure. Ils ne bougeront plus jamais.

**Le lien** : **EXSTART** — élection **maître/esclave** (le plus **grand Router ID** est maître), échange du
numéro de séquence initial, et **contrôle du MTU**. Le blocage définitif sur des mesures différentes
(1500 vs 9000) est **la** panne n°1 d'OSPF : **MTU mismatch**.

## 6. Fenêtre — EXCHANGE

**L'image** : par la fenêtre grande ouverte, deux voisins se jettent des **catalogues de vente par
correspondance** — épais, brillants, qui claquent en atterrissant. Mais ce ne sont **que les sommaires** :
tu ouvres, il n'y a que la **table des matières**, des titres et des numéros de page, **aucun article**.
Le vent en emporte les pages, qui volettent dans le salon.

**Le lien** : **EXCHANGE** — échange des **DBD**, qui ne contiennent que les **en-têtes des LSA**. Le
catalogue, pas les livres : on compare qui a quoi avant de demander quoi que ce soit.

## 7. Bureau — LOADING

**L'image** : à ton bureau, tu **entoures au marqueur rouge** trois lignes du sommaire en criant
**« CELUI-LÀ ! CELUI-LÀ ! ET CELUI-LÀ ! »**. Aussitôt, trois cartons lourds arrivent par le monte-charge et
s'écrasent sur le bureau — *BOUM*. Tu signes un **reçu** à chaque carton, avec un gros tampon vert :
*TAC. TAC. TAC.*

**Le lien** : **LOADING** — j'entoure ce qui me manque (**LSR**), on m'envoie le contenu réel (**LSU**), et
j'accuse réception de chacun (**LSAck**). Trois paquets, trois gestes, dans cet ordre.

## 8. Bibliothèque — FULL

**L'image** : ta bibliothèque et **celle du voisin** apparaissent côte à côte, **rigoureusement
identiques** : même nombre de livres, mêmes couleurs de dos, même poussière, même livre de travers au même
endroit. Tu déplaces un livre chez toi : **le même livre bouge tout seul chez lui**, dans un léger
scintillement bleu et un son de cloche cristallin.

**Le lien** : **FULL** — les **LSDB sont synchronisées et identiques**. L'adjacence est complète. C'est
l'invariant fondamental d'OSPF : dans une aire, tout le monde a exactement la même base.

## 9. Salle de bain — DIJKSTRA (le calcul SPF)

**L'image** : dans la baignoire, **une pieuvre violette** trempe et étale devant elle une **carte routière
géante** qui déborde sur le carrelage. Elle plante des **épingles fluo** une par une — toujours **la plus
proche d'abord** — en couinant à chaque fois **« CELLE-LÀ EST DÉFINITIVE ! »**. Une épingle plantée ne se
retire jamais. La carte est mouillée, l'encre coule, mais elle continue.

**Le lien** : **Dijkstra / SPF** — chacun calcule sur **sa** copie de la LSDB, avec **lui-même comme
racine** (la pieuvre est au centre de sa carte). On fige **toujours le candidat le plus proche**, et une
distance figée est **définitive**.

## 10. Chambre — LA ROUTE INSTALLÉE (RIB → FIB)

**L'image** : au-dessus de ton lit, un **panneau d'autoroute** vert descend du plafond dans un grondement
et se **visse tout seul** au mur : *VZZZT-CLAC*. Il n'affiche qu'**une seule flèche** et un seul nom — pas
l'itinéraire complet, juste **la direction du prochain village**. Un petit robot vient tamponner en dessous
**[110 / 12]** avec un tampon encreur bleu.

**Le lien** : la route entre dans la **RIB**, puis est programmée dans la **FIB**. Elle ne contient que le
**prochain saut**, jamais le chemin complet — et elle est étiquetée **[AD / métrique]**, soit **110** pour
OSPF et le coût cumulé.

---

## Parcours de récitation

> Je pousse la **porte soudée et muette** (*Down*), je croise dans le **couloir le standardiste qui appelle
> un seul numéro** (*Attempt*), à la **cuisine on me tend une carte où mon nom manque** (*Init*), sur la
> **table deux miroirs se serrent la main et reçoivent deux couronnes** (*2-Way*, élection DR/BDR), sur le
> **canapé les enfants élisent un chef puis se figent sur deux mesures différentes** (*ExStart*, maître/esclave
> et MTU), à la **fenêtre on se jette des catalogues sans articles** (*Exchange*, en-têtes de LSA), au
> **bureau j'entoure en rouge et je signe trois reçus** (*Loading*, LSR/LSU/LSAck), à la **bibliothèque ma
> bibliothèque et celle du voisin sont identiques** (*Full*, LSDB synchronisées), dans la **baignoire la
> pieuvre plante ses épingles en partant de la plus proche** (*Dijkstra*), et au-dessus du **lit un panneau
> se visse en n'indiquant que le prochain village, tamponné [110/12]** (*route installée, RIB → FIB*).

**Test** : refais le parcours **à l'envers**, de la chambre à la porte d'entrée. Puis demande-toi
« c'est quoi le 5 ? » — la réponse doit venir **immédiatement** : le canapé, donc **ExStart**, donc
**maître/esclave et contrôle du MTU**.
