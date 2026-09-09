# Palais mental D02 — Les 10 étapes de la traversée Netfilter

> **La liste à ancrer** : les **10 étapes que traverse un paquet forwardé** sous Linux, dans l'ordre exact,
> de la carte réseau à la carte réseau. C'est la question d'entretien du module (« décris l'ordre de traversée
> de Netfilter »), c'est la carte qui explique **Docker, kube-proxy, les VPN et tous les CNI**, et c'est ta
> procédure de débogage : tu ne cherches pas « où le paquet meurt », tu **marches** dans les dix étapes.
>
> Dix étapes, dix emplacements. Ça tombe juste.
>
> **Phrase d'amorce, à te dire avant de partir** : « **je marche pour la traversée Netfilter** ». Elle active
> le bon jeu d'images et évite les collisions avec les autres listes logées dans le même appartement (la
> résolution DNS de R07, les états TCP de R06, le best path BGP de R05).
>
> **Le fil rouge à ne jamais lâcher** : emplacements **1 à 5**, on est **avant le routage** — le paquet est
> inspecté, suivi, marqué, et sa **destination** peut changer. Emplacement **6**, l'aiguillage : la décision de
> routage. Emplacement **7**, le tribunal : on passe ou on meurt. Emplacements **8 à 10**, la sortie — la
> **source** change au tout dernier moment. **Cinq avant, un aiguillage, un tribunal, trois pour sortir.**

---

## 1. La porte d'entrée — l'arrivée sur la NIC et la sonde tcpdump RX

Ta porte d'entrée a été remplacée par un **tourniquet de métro rouge fluo** qui claque, et **juste devant**,
un **paparazzi en gilet jaune** mitraille au flash **tout le monde qui entre**, même les gens qu'on va jeter
dehors trois mètres plus loin. Il hurle « TCPDUMP ! TCPDUMP ! » à chaque cliché.

→ **Étape 1 : le paquet arrive par le driver de la carte, et la sonde `tcpdump` (AF_PACKET) le photographie
AVANT tout le reste.** D'où la règle : **en réception, tu vois le paquet même s'il va être droppé**, et avec
ses adresses **d'avant le DNAT**. Le paparazzi photographie avant le vestiaire.

## 2. Le couloir — la table `raw`, priorité −300

Le couloir est occupé par un **moine chauve en bure grise**, assis en tailleur, qui ne fait **rien**. Quand un
paquet passe, il lève une main molle et murmure « **toi, je ne t'ai jamais vu** », puis lui colle un **tampon
NOTRACK invisible** sur le front. Le tampon fait un bruit de ventouse.

→ **Étape 2 : la table `raw`, priorité −300, la première de toutes.** Sa seule raison d'être : intervenir
**avant conntrack**, essentiellement pour marquer `NOTRACK` un flux qu'on ne veut pas suivre (trafic massif de
réplication, backup). Le moine qui « ne t'a jamais vu » = l'exemption de suivi.

## 3. La cuisine — conntrack, priorité −200

La cuisine est envahie par une **secrétaire à lunettes en écaille** entourée de **milliers de fiches
cartonnées roses qui volent**. À chaque paquet, elle attrape une fiche, la tamponne avec un gros tampon en
bois — **NEW**, **ESTABLISHED**, **RELATED** ou **INVALID** — et la range dans un **frigo géant qui garde
tout pendant CINQ JOURS** en bourdonnant. Le frigo est déjà plein à craquer, des fiches débordent par la
porte.

→ **Étape 3 : conntrack, priorité −200.** Il crée ou retrouve l'entrée du flux, avec son tuple d'origine et
son tuple de réponse attendu. Le tampon = l'état `ct state`. Le frigo bourré = `nf_conntrack_tcp_timeout_
established = 432 000 s = 5 jours`, et la table pleine qui jette des paquets au hasard.

## 4. La table — `mangle PREROUTING`, priorité −150

Sur la table, un **enfant surexcité** peint des **gros ronds de peinture fluo orange** sur le dos de chaque
paquet qui passe, en criant « **MARQUÉ ! MARQUÉ !** ». La peinture ne change ni le nom ni l'adresse du paquet :
elle sert seulement à ce qu'un vigile, plus loin dans le couloir, le reconnaisse.

→ **Étape 4 : `mangle PREROUTING`, priorité −150.** On **modifie** sans traduire : `MARK` (la marque servira
à `ip rule fwmark`), TOS/DSCP, TTL. La peinture qui ne sert qu'à être reconnu plus tard = la marque de
routage.

## 5. Le canapé — `nat PREROUTING` / **DNAT**, priorité −100

Sur le canapé, un **faussaire moustachu en costume violet** arrache l'**étiquette de DESTINATION** collée sur
chaque colis, la déchire bruyamment, et en colle une autre — « **172.17.0.2:80** » — au pistolet à colle. Il
ne le fait qu'une seule fois par client, **le premier jour seulement**, et note tout dans le carnet de la
secrétaire de la cuisine.

→ **Étape 5 : `nat PREROUTING`, DNAT, priorité −100. LA DESTINATION CHANGE ICI.** C'est exactement ce que fait
`docker run -p 8080:80` et ce que fait kube-proxy pour un ClusterIP. **« Le premier jour seulement »** = la
table `nat` ne s'applique qu'au paquet en état `NEW` ; conntrack rejoue ensuite tout seul.

## 6. La fenêtre — **LA DÉCISION DE ROUTAGE**

La fenêtre est ouverte en grand, et un **aiguilleur de gare en uniforme bleu**, debout sur le rebord, tire un
**énorme levier métallique** dans un grincement d'acier. Deux voies : « **POUR MOI** » (à gauche, vers le
salon) et « **À TRAVERS** » (à droite, vers la sortie). Il regarde **uniquement l'étiquette de destination** —
celle que le faussaire vient de changer.

→ **Étape 6 : la décision de routage.** Le noyau compare la destination à ses adresses locales : c'est pour lui
(→ `INPUT`) ou pour quelqu'un d'autre (→ `FORWARD`). **C'est pour ça que le DNAT doit être AVANT** : sinon
l'aiguilleur lirait la mauvaise étiquette et enverrait le paquet sur la mauvaise voie.

## 7. Le bureau — `filter FORWARD` (ou `INPUT`), priorité 0

Le bureau est devenu un **tribunal miniature**. Un **juge minuscule en perruque blanche**, monté sur une pile
d'annuaires, abat un **maillet géant** dans un grand BANG et hurle un seul mot : « **ACCEPT !** », « **DROP !** »
ou « **REJECT !** ». Derrière lui, un **compteur mécanique de station-service** cliquette et incrémente à chaque
verdict.

→ **Étape 7 : `filter`, priorité 0, chaîne `FORWARD` (ou `INPUT` si l'aiguilleur a dit « pour moi »).** C'est
**le** pare-feu. **DROP = silence** (le client attend 2 minutes) ; **REJECT = RST ou ICMP** (échec immédiat).
Le compteur qui cliquette = `iptables -L -n -v` : en debug, **on lit les compteurs, pas les règles**.

## 8. La bibliothèque — `mangle POSTROUTING`, priorité −150

Dans la bibliothèque, le **même enfant à la peinture fluo** est revenu, mais cette fois il est **assis à
l'envers sur l'échelle**, et il repeint les paquets **en vert pomme** en chantonnant. Dernier retouche avant
la sortie.

→ **Étape 8 : `mangle POSTROUTING`, priorité −150.** Dernière occasion de modifier des champs (marque, TOS,
MSS clamping pour les tunnels) avant l'émission. Même personnage, autre couleur, autre moment : la seule
chose qui change, c'est **où** tu es dans le parcours.

## 9. La salle de bain — `nat POSTROUTING` / **SNAT / MASQUERADE**, priorité +100

Devant le miroir de la salle de bain, une **file de paquets** enfile des **masques de carnaval dorés
identiques** en gloussant. Un **habilleur** leur arrache l'étiquette **EXPÉDITEUR**, la remplace par la sienne,
et leur souffle : « **tu sortiras sous MON nom, sinon personne ne saura te répondre.** » Le miroir est
embué et on ne reconnaît plus personne.

→ **Étape 9 : `nat POSTROUTING`, SNAT/MASQUERADE, priorité +100. LA SOURCE CHANGE ICI.** C'est ce que fait
la box, la passerelle NAT, et Docker pour `172.17.0.0/16`. **Le masque après le tribunal** : le SNAT est
forcément **après** le routage, puisque l'adresse à mettre dépend de l'interface de sortie choisie.

## 10. La chambre — qdisc, NIC, et la sonde tcpdump TX

Dans la chambre, un **videur de boîte de nuit en costume noir** pousse les paquets **un par un** dans un
**toboggan en plastique jaune** qui grince. Et là, **deuxième paparazzi**, celui-ci **à l'intérieur** du
toboggan : il ne photographie que des gens **déjà masqués**, et il n'en revient pas.

→ **Étape 10 : la qdisc (`fq_codel`) met le paquet en file, la carte l'émet, et la sonde `tcpdump` TX le
photographie — APRÈS le SNAT.** D'où la règle jumelle de l'étape 1 : **en émission, tu vois les adresses
déjà traduites**. Pour voir la vraie IP source d'un conteneur, capture sur la veth ou le bridge, pas sur `eth0`.

---

## Parcours de récitation

> Le **paparazzi** photographie tout le monde à la **porte** ; le **moine** du **couloir** dit « je ne t'ai
> jamais vu » ; la **secrétaire** de la **cuisine** tamponne une fiche et la met au frigo cinq jours ;
> l'**enfant** peint un rond orange sur la **table** ; le **faussaire** du **canapé** change l'étiquette de
> destination ; l'**aiguilleur** de la **fenêtre** tire le levier « pour moi / à travers » ; le **juge** du
> **bureau** abat son maillet ACCEPT ou DROP ; l'enfant repeint en vert à la **bibliothèque** ; l'**habilleur**
> de la **salle de bain** met le masque doré de l'expéditeur ; et le **videur** de la **chambre** pousse le
> paquet dans le toboggan, photographié une dernière fois, déjà masqué.

**Test d'ancrage** : refais le parcours **à l'envers**, de la chambre à la porte. Si tu retrouves
`tcpdump TX → SNAT → mangle POST → filter → routage → DNAT → mangle PRE → conntrack → raw → tcpdump RX`,
c'est ancré.

**Les deux mots à ne jamais confondre, et le palais te les donne par la position** :
**canapé (5) = DESTINATION**, avant l'aiguilleur. **Salle de bain (9) = SOURCE**, après le juge.
