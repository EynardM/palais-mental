# R02 — PALAIS MENTAL : la trame Ethernet sur le fil, dans l'ordre

> **Pourquoi un palais ici** : la trame Ethernet est une **liste ordonnée de 10 éléments** dont l'ordre exact
> est ce qu'on te demandera de redessiner en entretien, et dont chaque taille se perd à la relecture.
> Un décodage hexadécimal ne marche que si l'ordre est automatique.
>
> **Parcours utilisé** : les 10 emplacements standard de `palais/00-mes-lieux.md` —
> 1. porte d'entrée · 2. couloir · 3. cuisine · 4. table · 5. canapé · 6. fenêtre · 7. bureau ·
> 8. bibliothèque · 9. salle de bain · 10. chambre.
>
> **Mode d'emploi** : lis chaque image **les yeux fermés**, en te plaçant physiquement à l'emplacement.
> Fais bouger l'image, mets-y du bruit et de la couleur. Puis refais le trajet dans l'ordre, sans le texte.

---

## La liste à ancrer

```
[Préambule 7] [SFD 1] [MAC dest 6] [MAC src 6] ([Tag 4]) [Type 2] [Payload 46-1500] [Bourrage] [FCS 4] (IFG 12)
```

---

## 1. Porte d'entrée — le PRÉAMBULE (7 octets, `10101010`)

**L'image** : sept sonnettes fluo, alternées noir et blanc, clignotent en rythme sur ta porte. Un métronome
de deux mètres de haut bat au-dessus : *TAC — tac — TAC — tac*, sept fois. Tu es obligé de caler ton pas sur
le rythme avant de pouvoir entrer, sinon la porte te repousse en couinant.

**Le lien** : 7 octets de `10101010` alternés dont le seul rôle est de **synchroniser l'horloge** du
récepteur avant la vraie trame.

## 2. Couloir — le SFD (1 octet, `10101011`)

**L'image** : au bout du couloir, une **huitième** sonnette, rouge celle-là, qui au lieu d'alterner sonne
**deux fois d'affilée** : *DING-DING !* Un rideau de velours se déchire alors dans un grand **CRAAAC**.

**Le lien** : le SFD fait **1 seul octet**, il finit par **`11`** au lieu de `10`, et il annonce que la trame
**commence maintenant**. Préambule + SFD = 8 octets, et ils ne comptent pas dans la taille de la trame.

## 3. Cuisine — la MAC DESTINATION (6 octets)

**L'image** : six assiettes empilées sur le plan de travail, chacune avec une étiquette au nom d'un
destinataire. Tu cries un nom : l'assiette correspondante s'allume en **vert vif** et vibre, les cinq autres
se retournent d'un coup sec, face contre table, dans un silence total.

**Le lien** : **6 octets**, c'est le **premier champ de la trame** — le destinataire d'abord. Et l'image du
filtrage : seule la carte concernée réagit, les autres ignorent la trame en matériel.

## 4. Table — la MAC SOURCE (6 octets)

**L'image** : sur la table, six couverts gravés à ton nom. Un gros **tampon encreur bleu** se soulève tout
seul et frappe la nappe : **POC !** Il enregistre qui a mangé ici, avec la date et la place.

**Le lien** : **6 octets** juste après la destination. Le tampon, c'est le switch qui **apprend sur la MAC
source** — la règle la plus importante du module.

## 5. Canapé — le TAG 802.1Q (4 octets, optionnel)

**L'image** : quatre coussins criards, qu'on ne sort **que quand des invités viennent**. Sur le premier,
brodé au fil d'or : **`81 00`**. Sur les trois autres, un ruban de priorité gradué de **0 à 7** qui monte et
descend, et un numéro de chambre à quatre chiffres qui clignote en rouge : **4094**.

**Le lien** : tag de **4 octets** inséré **après la MAC source**, présent seulement sur un trunk :
**TPID `0x8100`** + **PCP de 0 à 7** + DEI + **VID sur 12 bits → 4094 VLAN utilisables**.

## 6. Fenêtre — l'ETHERTYPE (2 octets)

**L'image** : la fenêtre a **deux vitres** montées sur pivot. Sur la première, un autocollant géant
**`08 00`** ; sur la seconde, **`08 06`**. Elles claquent en pivotant selon ce que tu veux voir dehors, et
tu ne vois le paysage qu'à travers celle qui est en place.

**Le lien** : **2 octets** qui annoncent **le protocole du dessus** : `0800` = IPv4, `0806` = ARP,
`86DD` = IPv6. Sans lui, le récepteur ne saurait pas à qui donner le contenu.

## 7. Bureau — le PAYLOAD (46 à 1500 octets)

**L'image** : une pile de dossiers sur ton bureau, montée sur **piston hydraulique**. Elle respire, monte et
descend en chuintant : **jamais moins de 46 feuilles, jamais plus de 1500**. Au-delà, une alarme néon rouge
hurle **« TROP GROS ! »** et le dossier est éjecté par la fenêtre.

**Le lien** : payload de **46 à 1500 octets**. Le 1500, c'est **le MTU**. Le dossier éjecté, c'est le paquet
qui dépasse le MTU et qui est jeté quand le bit DF est posé.

## 8. Bibliothèque — le BOURRAGE (padding)

**L'image** : l'étagère est à moitié vide, ça fait désordre. De **faux livres en polystyrène blanc** se
glissent alors tout seuls dans les trous, en couinant contre le bois, jusqu'à ce que le rayon soit plein.
Ils ne contiennent rien.

**Le lien** : si le payload fait **moins de 46 octets**, on ajoute du **bourrage de zéros** pour atteindre
la **trame minimale de 64 octets**. C'est le cas de toutes les trames ARP (42 octets → 64).

## 9. Salle de bain — le FCS (CRC-32, 4 octets)

**L'image** : quatre robinets calculent à voix haute, en chœur, une somme de contrôle : *« trente-deux…
trente-deux… »*. Si le total ne tombe pas juste, la **bonde s'ouvre d'un coup** et **tout part à l'égout**
dans un glouglou — sans un mot, sans réclamation, sans que personne soit prévenu.

**Le lien** : **4 octets** de **CRC-32** en fin de trame. FCS faux → **trame jetée en silence**, aucune
retransmission en couche 2.

## 10. Chambre — l'IFG (12 octets de silence)

**L'image** : tu entres dans la chambre et c'est le **noir complet**. Silence absolu. Au mur, un panneau
lumineux affiche **96** en chiffres verts, et un compte à rebours de **12** égrène des billes qui tombent
une à une. Puis la lumière se rallume pour l'invité suivant.

**Le lien** : **inter-frame gap de 12 octets = 96 temps-bit** de silence obligatoire entre deux trames.
Avec le préambule et le SFD, il porte l'overhead total sur le fil à **38 octets**.

---

## Parcours de récitation — une seule phrase enchaînée

> **Sept sonnettes** clignotent à la **porte** au rythme du métronome, une **huitième** sonne deux fois dans
> le **couloir** et déchire le rideau ; en **cuisine** six assiettes s'allument pour un seul nom, sur la
> **table** un tampon bleu enregistre qui est passé, sur le **canapé** quatre coussins dorés ne sortent que
> pour les invités, la **fenêtre** pivote entre `0800` et `0806`, au **bureau** la pile de dossiers respire
> entre 46 et 1500, à la **bibliothèque** de faux livres blancs comblent les trous, dans la **salle de bain**
> quatre robinets font tout partir à l'égout si le compte est faux, et dans la **chambre** douze billes
> tombent dans le noir avant l'invité suivant.

**Auto-test** : redonne, dans l'ordre, les 10 champs **et leur taille**.
Réponse : 7 · 1 · 6 · 6 · (4) · 2 · 46-1500 · bourrage · 4 · 12.

---

## Deuxième tour — les 5 états de port 802.1D (emplacements 1 à 5)

Même parcours, deuxième passage. Cinq emplacements suffisent, et l'ordre est celui de la traversée.

| # | Lieu | État | L'image |
|---|---|---|---|
| 1 | **Porte d'entrée** | **Disabled** | La porte est **condamnée par des planches clouées en croix**. Personne n'entre, personne ne parle. |
| 2 | **Couloir** | **Blocking** | Un videur en costume noir, **écouteur dans l'oreille**, entend tout ce qui se dit (il reçoit les BPDU) mais **ne dit rien et ne laisse passer personne**. |
| 3 | **Cuisine** | **Listening** (15 s) | La radio hurle et le cuisinier **parle sans arrêt** (il émet des BPDU), mais **aucun plat ne sort**. Un minuteur affiche **15**. |
| 4 | **Table** | **Learning** (15 s) | On **écrit les noms des convives au feutre sur la nappe** (on apprend les MAC), toujours **rien à manger**. Deuxième minuteur : **15**. |
| 5 | **Canapé** | **Forwarding** | Tout le monde s'assoit, **les plats circulent enfin** et la musique démarre. |

**Phrase de récitation** : *porte clouée, videur muet, cuisinier bavard pendant 15, noms sur la nappe
pendant 15, puis les plats circulent.*
→ **Disabled, Blocking, Listening, Learning, Forwarding**, et **15 + 15 = 30 secondes** de convergence
802.1D. En RSTP, les trois premiers fusionnent en **Discarding**.

**Rappel d'ordre pour l'élection STP** : **Root, Route, Reste** — le **R**oot bridge (Bridge ID le plus
faible), la **R**oute (root port, coût le plus faible), le **R**este est bloqué.
