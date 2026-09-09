# D01 — PALAIS MENTAL : les 10 étapes de la vie et de la mort d'un processus

> **Pourquoi un palais ici** : ce module contient une **séquence ordonnée de 10 étapes** qu'on te demandera
> en entretien sous deux formes différentes — « explique ce qui se passe quand tu tapes une commande » et
> « raconte-moi un arrêt propre de conteneur ». C'est la **colonne vertébrale de tout D01** : chaque étape
> porte une notion du cours (descripteurs, permissions, états, cgroup, signaux, zombie). Une liste
> chronologique de cette longueur ne se retient pas par relecture ; elle se retient **par déplacement**.
>
> **Le fil rouge** : tu suis **un seul processus**, de sa naissance à la disparition de sa fiche. Les
> emplacements 1 à 4 sont sa **naissance**, 5 et 6 sa **vie**, 7 à 10 sa **mort**. Retiens cette coupure
> en trois blocs : elle t'évite de te perdre au milieu du parcours.
>
> **Parcours utilisé** : les 10 emplacements standard de `palais/00-mes-lieux.md` —
> 1. porte d'entrée · 2. couloir · 3. cuisine · 4. table · 5. canapé · 6. fenêtre · 7. bureau ·
> 8. bibliothèque · 9. salle de bain · 10. chambre.
>
> **Mode d'emploi** : lis chaque image **les yeux fermés**, en te plaçant physiquement à l'emplacement.
> Fais bouger la scène, mets-y de la couleur et du bruit, et **implique ton corps**. Puis refais le trajet
> sans le texte, et une fois **à l'envers** (10 → 1) : si l'envers passe, c'est ancré.

---

## La liste à ancrer

```
   NAISSANCE                    VIE                          MORT
   ─────────                    ───                          ────
   1. fork()      photocopie    5. états R / S / D           7.  SIGTERM (15)  demande
   2. dup2()      FD 0,1,2      6. RSS / cgroup / OOM        8.  délai de grâce 10/30/90 s
   3. execve()    même PID                                   9.  SIGKILL (9)   code 137
   4. identité    UID + droits                               10. zombie → wait() → fiche classée

        │                            │                             │
        └──── le PID est créé ───────┴──── le PID travaille ────────┴──── le PID est libéré
```

---

## 1. Porte d'entrée — `fork()` : la photocopie

**L'image** : ta porte d'entrée est devenue une **photocopieuse industrielle vert fluo** qui vibre et
crache un **double parfait de toi-même**, encore chaud, avec l'odeur de toner. Le double te regarde et
hurle **« ZÉRO ! »** ; toi tu hurles en retour un **numéro à quatre chiffres**. Vous êtes identiques,
mais aucun de vos deux corps n'est réellement dupliqué : vous partagez la **même peau**, et elle ne se
dédouble qu'à l'endroit précis où l'un de vous se gratte.

**Le lien** : `fork()` crée une copie du processus. L'enfant reçoit **0**, le parent reçoit **le PID de
l'enfant**. La mémoire n'est pas vraiment copiée : c'est du **copy-on-write**, dupliqué page par page
seulement à la première écriture.

## 2. Couloir — `dup2()` : le recâblage des descripteurs

**L'image** : le couloir est un **standard téléphonique des années 1950**, avec **trois fiches jack
numérotées 0, 1 et 2**, grosses comme le poing. Une opératrice en tablier orange les **arrache et les
replante** à toute vitesse en criant les numéros. Elle plante le **1 dans un bocal de verre étiqueté
`app.log`**, le **2 dans le même bocal**, et laisse le **0 pendre dans le vide**. Le bruit sec du jack :
*clac, clac*.

**Le lien** : entre le `fork` et le `exec`, le shell **recâble la table des descripteurs** avec `dup2()` :
**0 = stdin, 1 = stdout, 2 = stderr**. C'est là que sont appliquées les redirections — et c'est pour ça
que `> f 2>&1` marche mais que `2>&1 > f` ne marche pas : l'opératrice suit l'ordre des ordres.

## 3. Cuisine — `execve()` : la greffe de cerveau

**L'image** : dans ta cuisine, ton double est allongé sur le plan de travail. Un **chirurgien avec un
tablier de boucher** lui **ouvre le crâne, jette le cerveau dans l'évier** (*ploc*) et y visse à sa place
un **cerveau de python vert vif**, qui siffle. Le double se relève : il ne te ressemble plus du tout —
mais il porte toujours **son bracelet d'hôpital avec le même numéro à quatre chiffres**, et les trois
jacks du couloir sont toujours branchés dessus.

**Le lien** : `execve()` **remplace intégralement le programme en mémoire** — mais garde le **même PID**,
le même parent, et **les mêmes descripteurs**. Photocopie puis greffe : deux appels distincts, et c'est
exactement pour pouvoir agir entre les deux.

## 4. Table — l'identité et les droits

**L'image** : sur ta table, un **douanier en uniforme bleu électrique** tamponne violemment un passeport
(*BAM*) où est écrit en énorme **UID 1000**. À côté de lui, un **pochoir en métal** posé sur chaque
feuille qui passe **découpe des trous en forme de `rwx`** : ce qui sort est plus petit que ce qui entre.
Le douanier grogne trois fois : **« quatre… deux… un… »**.

**Le lien** : le noyau attache au processus une **identité** (UID, GID, groupes) et tranche à chaque
appel système. Le pochoir qui retire des droits, c'est le **`umask`** — et les trois grognements,
**`r=4, w=2, x=1`**.

## 5. Canapé — les états `R`, `S`, `D`

**L'image** : sur ton canapé, **trois clones du processus** se disputent la place. Le premier **court sur
place** en sueur, rouge, essoufflé. Le deuxième **dort en ronflant doucement**, et se réveille en
sursaut dès qu'on claque des doigts. Le troisième dort aussi — mais il est **congelé dans un bloc de
glace bleue**. Tu lui hurles dessus, tu le frappes avec une batte : **rien, il ne bouge pas d'un
millimètre**, et le canapé s'enfonce sous son poids énorme.

**Le lien** : **`R`** = il court (running/runnable). **`S`** = sommeil **interruptible**, l'état normal
de 95 % des processus. **`D`** = sommeil **non interruptible** : bloqué sur une E/S, **immunisé même à
`kill -9`** — et son poids qui enfonce le canapé, c'est le fait qu'il **compte dans le load average**.

## 6. Fenêtre — RSS, cgroup et OOM killer

**L'image** : ta fenêtre est barrée d'un **cadre de béton jaune trop étroit**. Le processus, devenu une
**montgolfière rouge**, essaie de sortir. Sa **nacelle** ne fait qu'un mètre — c'est ce qu'elle pèse
vraiment — mais son **ballon** en occupe trente : de l'air, rien que de l'air. Quand le ballon touche le
béton, un **videur en costume noir** surgit, **crève la montgolfière avec un couteau** (*PSSSCHHH*) et
gueule un seul nombre : **« CENT-TRENTE-SEPT ! »**

**Le lien** : la **nacelle = RSS** (ce qui est vraiment en RAM), le **ballon = VSZ** (l'espace virtuel,
qui ne coûte rien). Le cadre en béton est la **limite du cgroup** (`memory.max`), et le videur est
l'**OOM killer** : `SIGKILL`, donc **code 137**. Le cadre est plus petit que la fenêtre : c'est **ta
limite de conteneur, pas la RAM de la machine**.

## 7. Bureau — `SIGTERM` (15) : la demande polie

**L'image** : sur ton bureau, un **huissier en costume gris** dépose délicatement une **enveloppe blanche
frappée d'un gros 15 doré**, tousse poliment et dit : *« quand vous voudrez, monsieur »*. Il **s'assoit
sur ton fauteuil**, croise les jambes, sort un **gros chronomètre en laiton** qu'il déclenche avec un
**clic** sonore, et attend.

**Le lien** : **`SIGTERM = 15`**, le signal **par défaut** de `kill`, de `docker stop` et de Kubernetes.
Il est **rattrapable** : c'est une demande, pas un ordre. Le chronomètre qui démarre, c'est le délai
de grâce qui commence — étape suivante.

## 8. Bibliothèque — le délai de grâce

**L'image** : dans ta bibliothèque, le processus court en **panique multicolore** : il **claque les
livres ouverts** (*paf, paf, paf*), **jette les feuilles volantes dans un classeur**, **coupe les fils
du téléphone** un par un, et remet chaque volume à sa place. Sur les trois horloges murales, des
aiguilles géantes tournent à toute vitesse et affichent **10**, **30** et **90**. Une voix off compte
à rebours.

**Le lien** : c'est **l'arrêt propre** — vider les tampons, commiter les offsets Kafka, fermer les
connexions à la base, finir les requêtes en cours. Trois délais de grâce à retenir :
**10 s (`docker stop`) · 30 s (Kubernetes) · 90 s (systemd)**.

## 9. Salle de bain — `SIGKILL` (9) : le couperet

**L'image** : dans ta salle de bain, une **guillotine de cuivre poli** est montée au-dessus de la
baignoire. Un **9 rouge sang** est peint sur la lame. Aucun avertissement, aucun bruit avant : la lame
tombe (*CLAC*), l'eau devient rouge, et **la radio qui jouait s'arrête en plein milieu d'un mot**. Rien
n'a été rangé : le savon flotte, la brosse à dents tombe dans le lavabo.

**Le lien** : **`SIGKILL = 9`**, appliqué **par le noyau**, **ni rattrapable, ni blocable, ni ignorable**.
**Aucune ligne de code applicatif n'est exécutée** — d'où le fichier Parquet tronqué, l'offset non
commité, le verrou orphelin. Le mot coupé en plein milieu, c'est **l'absence totale de log**.
Code de sortie : **137**.

## 10. Chambre — zombie, puis `wait()`

**L'image** : dans ta chambre, un **cadavre en costume de bureau est assis bien droit sur ton lit**, gris,
immobile, **une étiquette cartonnée pendue à l'orteil**. Tu lui tires dessus au fusil : **les balles le
traversent, il ne tombe pas** — il est déjà mort. Puis **sa mère entre en trombe**, hurlante, **arrache
l'étiquette**, la **signe** en gros (*scriiitch*) — et le corps **se désintègre en poussière dorée**.

**Le lien** : le **zombie** est un enfant terminé dont le parent n'a pas encore appelé `wait()`. Il ne
consomme **qu'un PID et une entrée de table** ; **`kill -9` n'a aucun effet sur lui**. Seul **le parent**
peut le faire disparaître en lisant son code de sortie — et si le parent meurt, l'enfant est **ré-adopté
par PID 1**, qui moissonne en boucle. La fiche est classée : le PID est libéré.

---

## Le parcours de récitation

> À la **porte d'entrée**, une photocopieuse me duplique et mon double crie « **zéro** » ; dans le
> **couloir**, une opératrice replante les jacks **0, 1 et 2** dans un bocal ; dans la **cuisine**, un
> chirurgien lui greffe un cerveau de python **sans changer son bracelet numéroté** ; sur la **table**,
> un douanier tamponne **UID 1000** et un pochoir découpe **4-2-1** ; sur le **canapé**, trois clones —
> un qui court, un qui dort, un **congelé qu'aucune balle ne réveille** ; à la **fenêtre**, la
> montgolfière à petite nacelle et gros ballon est crevée par un videur qui gueule « **137** » ; sur le
> **bureau**, l'huissier pose l'enveloppe **15** et déclenche son chronomètre ; dans la **bibliothèque**,
> tout est rangé en panique sous les horloges **10, 30, 90** ; dans la **salle de bain**, la guillotine
> **9** tombe et coupe la radio en plein mot ; et dans la **chambre**, le cadavre criblé de balles ne
> tombe que lorsque **sa mère signe l'étiquette**.

**Test à l'envers (10 → 1)** : la mère qui signe · la guillotine 9 · les horloges 10/30/90 ·
l'enveloppe 15 · la montgolfière crevée · le clone congelé · le pochoir 4-2-1 · le cerveau de python ·
les trois jacks · la photocopieuse. Si tu récites l'envers sans hésiter, c'est ancré.

---

## Annexe — les deux questions d'entretien que ce parcours répond directement

| Question posée | Emplacements à parcourir |
|---|---|
| « Que se passe-t-il quand tu tapes une commande ? » | **1 → 4** (fork, dup2, exec, droits), puis 5 |
| « Raconte-moi un arrêt propre de conteneur » | **7 → 10** (TERM, grâce, KILL, moisson par PID 1) |
| « Pourquoi un pod met-il 30 s à s'arrêter ? » | 7 puis 8 : le chronomètre part, **personne n'ouvre l'enveloppe** |
| « Code 137, aucun log : que s'est-il passé ? » | 6 puis 9 : le videur du cgroup, puis la guillotine |
