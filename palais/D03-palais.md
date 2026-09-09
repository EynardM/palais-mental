# PALAIS D03 — Les 9 étapes d'expansion du shell, dans l'ordre

> Parcours standard, 10 emplacements (cf. `palais/00-mes-lieux.md`) :
> 1. porte d'entrée · 2. couloir · 3. cuisine · 4. table · 5. canapé · 6. fenêtre · 7. bureau · 8. bibliothèque · 9. salle de bain · 10. chambre.
>
> **Emplacements 1 à 9 = les 9 étapes d'expansion, dans l'ordre exact.** Le numéro de l'emplacement EST
> le numéro de l'étape : la cuisine est l'étape 3 (paramètres), le bureau est l'étape 7 (découpage).
> **Emplacement 10 = l'exécution** : ce qui reste après les 9 transformations part dans `execve()`.
>
> Pourquoi cette liste mérite un palais : l'ordre **n'est pas devinable**, et c'est lui — et lui seul —
> qui explique pourquoi `rm $f` détruit et `rm "$f"` non. Une inversion mentale entre l'étape 3 et
> l'étape 7 et tout ton raisonnement sur les bugs bash s'effondre.
>
> Avant de partir, dis-toi la phrase d'amorçage : **« je marche pour les expansions du shell »**.

---

## 1. Porte d'entrée → ÉTAPE 1 : EXPANSION DES ACCOLADES `{a,b}`

**L'image.** Ta porte d'entrée est devenue une **paire d'accolades géantes en néon rose**, deux crochets
mous qui **claquent comme des mâchoires**. Chaque fois que tu franchis le seuil, elles te **clonent** :
tu entres seul, et **trois toi** ressortent dans le couloir, en file, hurlant `a !` `b !` `c !`. Ça sent
le plastique chaud, et ça fait un bruit de **machine à barbe à papa**.

**Lien → notion.** Les accolades **multiplient** : `{a,b,c}` devient trois mots. C'est la **toute
première** chose que fait le shell, avant même de savoir de quoi il parle — purement textuel.

---

## 2. Couloir → ÉTAPE 2 : EXPANSION DU TILDE `~`

**L'image.** Le couloir est tapissé de **tildes en velours turquoise** qui ondulent comme des vagues.
Au bout, un **majordome moustachu** te barre la route, te pointe du doigt et beugle ton adresse
complète : « **SLASH HOME SLASH TON NOM !** », en te tendant un panneau de bois gravé. Tu ne peux pas
avancer tant qu'il n'a pas fini de crier ton chemin absolu.

**Lien → notion.** Le tilde `~` est **remplacé par le chemin absolu du home**. `~user` → le home de
`user`. Le majordome ne connaît que des **chemins**, jamais des variables.

---

## 3. Cuisine → ÉTAPE 3 : PARAMÈTRES ET VARIABLES `$v`

**L'image.** Dans la cuisine, un **distributeur de bonbons jaune fluo** couvert de gros `$` tourne sur
lui-même en **cliquetant**. Tu glisses une étiquette `DOSSIER` dans la fente : la machine **vomit** le
contenu — `/data in` — sur le carrelage, **en vrac, sans emballage, avec un trou au milieu** (l'espace).
Personne ne le ramasse, personne ne le range. Ça colle aux semelles.

**Lien → notion.** Le contenu de la variable est **déposé tel quel**, avec ses espaces et ses étoiles,
et **sans protection**. C'est là que naît le bug : il ne se déclenchera que trois pièces plus loin, au
bureau.

---

## 4. Table → ÉTAPE 4 : EXPANSION ARITHMÉTIQUE `$(( ))`

**L'image.** Sur la table, un **boulier en cuivre à double parenthèses** fait des additions tout seul
en **claquant ses boules** comme des castagnettes. Un petit comptable en gilet rayé recrache un ticket
de caisse : `3`. Quand tu lui demandes `1/3`, il te **tire la langue** et écrit **`0`** — il ne connaît
que les **entiers**.

**Lien → notion.** `$(( ))` calcule en **entiers signés 64 bits**, sans virgule. Pour du flottant :
`awk`, `bc -l` ou Python.

---

## 5. Canapé → ÉTAPE 5 : SUBSTITUTION DE COMMANDE `$( )`

**L'image.** Le canapé est **avalé par une bouche** en forme de `$( )` qui **mâche un cuisinier entier**
et recrache, à sa place, une **assiette fumante** posée sur les coussins. Le cuisinier a disparu :
il ne reste que le plat. Et les **trois serviettes en papier** qui traînaient sur l'assiette
(les sauts de ligne finaux) sont **aspirées** par un mini-aspirateur rouge.

**Lien → notion.** `$(cmd)` exécute la commande **dans un sous-shell** et **la remplace par sa sortie**.
Le processus disparaît (ses variables aussi), et **tous les sauts de ligne finaux sont supprimés**.

---

## 6. Fenêtre → ÉTAPE 6 : SUBSTITUTION DE PROCESSUS `<( )`

**L'image.** À la fenêtre, un **tuyau d'arrosage translucide** entre par la vitre et se termine par une
**plaque d'immatriculation métallique** qui clignote : **`/dev/fd/63`**. De l'eau verte fluo circule
dedans en gargouillant. Tu tentes de saisir le tuyau : ta main **passe à travers** — il n'y a pas de
fichier, juste un numéro de plaque.

**Lien → notion.** `<(cmd)` branche la sortie d'une commande sur un tube et la fait passer pour un
**chemin de descripteur** (`/dev/fd/63`). Aucun fichier temporaire n'existe vraiment. Bash seulement,
**jamais sous `sh`/dash**.

---

## 7. Bureau → ÉTAPE 7 : DÉCOUPAGE EN MOTS (IFS)

**L'image.** Sur ton bureau, une **guillotine de bureau orange vif** tranche **toutes les deux
secondes**, avec un **CLAC** métallique. Tu poses la nappe sale rapportée de la cuisine (`/data in`) :
elle ressort en **deux morceaux** qui tombent chacun dans une corbeille différente. Sur le flanc de la
machine, une étiquette gravée : **« coupe sur : espace, tabulation, saut de ligne »**. Un seul objet
est épargné : celui **enveloppé dans du film plastique transparent** — la guillotine glisse dessus.

**Lien → notion.** Le découpage en mots casse les résultats **non quotés** sur les caractères d'`IFS`
(**espace, tabulation, saut de ligne** par défaut). Le film plastique, ce sont les **guillemets
doubles** : ce qui est quoté n'est pas coupé.

---

## 8. Bibliothèque → ÉTAPE 8 : GLOBBING `*`

**L'image.** Dans la bibliothèque, une **étoile dorée à cinq branches, énorme, tourne au plafond** en
projetant des faisceaux. Chaque fois qu'un faisceau frappe une étagère, **les livres correspondants
sautent au sol en piles ordonnées**. Mais si le faisceau ne touche **aucun** livre, l'étoile **tombe
lourdement sur le parquet et reste là**, inerte, ridicule, à sa place de simple étoile en carton.

**Lien → notion.** Le globbing remplace `*.csv` par la **liste réelle des fichiers**. S'il n'y a
**aucune correspondance**, bash laisse le **motif littéral** — d'où la boucle qui tourne une fois avec
`f='*.csv'`. Antidote : `shopt -s nullglob`.

---

## 9. Salle de bain → ÉTAPE 9 : SUPPRESSION DES QUOTES

**L'image.** Dans la douche, une **pluie de guillemets en savon** dégringole du pommeau. Ils touchent
le sol et **fondent instantanément en mousse blanche** qui part dans la bonde en **glougloutant**. Ce
qu'ils protégeaient — la nappe intacte — reste posé sur le tapis de bain, **sec et entier**. Les
guillemets, eux, ont **totalement disparu** : il n'en reste rien.

**Lien → notion.** Les `"`, `'` et `\` ont fait leur travail (protéger des étapes 7 et 8) puis sont
**retirés en dernier**. La commande ne voit **jamais** les guillemets — seulement leur effet.

---

## 10. Chambre → L'EXÉCUTION : `argv` PART DANS `execve()`

**L'image.** Dans la chambre, un **lit-catapulte rouge** est armé. Les mots survivants sont sanglés
dessus, **numérotés au marqueur noir** : `argv[0]`, `argv[1]`, `argv[2]`… Un **compte à rebours de
fusée** résonne, la catapulte part dans un **claquement de drap**, et les mots traversent le mur.
Au-dessus du lit, un panneau clignote : **« ce qui est parti ne revient pas ».**

**Lien → notion.** Après les 9 transformations, il reste une **liste de chaînes** — `argv` — passée à
`execve()`. Le programme ne voit **que ça** : ni ta ligne d'origine, ni tes quotes, ni tes variables.
C'est pourquoi un bug de quoting est **invisible côté programme** : il a reçu de mauvais arguments et
les a exécutés fidèlement.

---

## Parcours de récitation (une phrase enchaînée)

> Les **accolades-mâchoires de la porte** me clonent en trois, le **majordome du couloir** hurle mon
> chemin absolu, le **distributeur de la cuisine** vomit ma variable en vrac, le **boulier de la table**
> compte en entiers seulement, la **bouche du canapé** mâche le cuisinier et n'en garde que le plat, le
> **tuyau de la fenêtre** exhibe sa plaque `/dev/fd/63`, la **guillotine du bureau** tranche tout ce qui
> n'est pas sous film plastique, l'**étoile de la bibliothèque** fait sauter les livres ou s'écrase
> seule au sol, les **guillemets de la salle de bain** fondent en mousse, et le **lit-catapulte de la
> chambre** expédie `argv` à travers le mur.

**Test à l'envers** (le vrai test d'ancrage) : de la chambre à la porte — `argv`, quotes, glob,
découpage, `<( )`, `$( )`, `$(( ))`, `$v`, `~`, `{a,b}`.

**Les deux questions qui tombent** :
- *« Le découpage arrive avant ou après le remplacement de la variable ? »* → **Après** : la cuisine (3)
  est avant le bureau (7), et il y a **quatre pièces** entre les deux. C'est tout le drame.
- *« Pourquoi les guillemets suffisent-ils ? »* → Ils sont encore là au bureau (7) et à la bibliothèque
  (8), et ne fondent qu'à la salle de bain (9).
