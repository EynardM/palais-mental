# PALAIS L01 — La chaîne de traitement d'un log, dans l'ordre

> Parcours standard, 10 emplacements (cf. `palais/00-mes-lieux.md`) :
> 1. porte d'entrée · 2. couloir · 3. cuisine · 4. table · 5. canapé · 6. fenêtre · 7. bureau ·
> 8. bibliothèque · 9. salle de bain · 10. chambre.
>
> **Les 10 emplacements = les 10 étapes que traverse un message entre `logger.info(...)` et son
> écriture.** Le numéro de l'emplacement EST le numéro de l'étape : la cuisine est l'étape 3 (les
> filtres du logger), la bibliothèque est l'étape 8 (le formatter).
>
> Pourquoi cette liste mérite un palais : c'est la seule qui explique **« pourquoi mon log
> n'apparaît pas »**, la question posée dans tous les entretiens data. Elle contient **deux
> filtrages par niveau** (étapes 2 et 6) que tout le monde confond en un seul, et **un point
> d'interpolation** (étape 8) qui justifie le `%s` différé. Inverser 4 et 8 dans ta tête, et tu ne
> comprends plus pourquoi une f-string coûte cher.
>
> Avant de partir, dis-toi la phrase d'amorçage : **« je marche pour la chaîne du logging »**.

---

## 1. Porte d'entrée → ÉTAPE 1 : L'APPEL `logger.info("etape=%s", v)`

**L'image.** Ta porte d'entrée est devenue une **boîte aux lettres géante en laiton doré**, et un
**facteur en scaphandre** y enfonce une enveloppe **à moitié vide** : le texte est écrit, mais il y a
un **trou rectangulaire découpé au milieu**, là où devrait figurer la valeur. Le facteur hurle
« **PAS ENCORE ! PAS ENCORE !** » en tapant sur la boîte, et il glisse la valeur `v` dans une
**pochette séparée**, agrafée à l'enveloppe.

**Lien → notion.** L'appel part avec le message brut **et ses arguments à côté**, non fusionnés.
C'est le principe du **formatage différé** : `logger.info("x=%s", v)` et jamais de f-string.

---

## 2. Couloir → ÉTAPE 2 : LE NIVEAU EFFECTIF DU LOGGER (1er filtre)

**L'image.** Le couloir est barré par un **portique de vigile clignotant rouge**, gradué **10-20-30-40-50**
comme un thermomètre de fête foraine. Un **videur en costume violet** regarde l'enveloppe, gueule
« **T'ES À COMBIEN ?** », et si le chiffre est **plus bas** que la barre lumineuse, il **jette
l'enveloppe dans une trappe** qui fait un bruit de chasse d'eau. Fin du voyage, immédiatement.

**Lien → notion.** `isEnabledFor(niveau)` : premier filtrage, par le **niveau effectif** du logger
(hérité du premier ancêtre qui en a un). Trop bas → **abandon immédiat**, rien n'est construit.
`DEBUG 10 · INFO 20 · WARNING 30 · ERROR 40 · CRITICAL 50`.

---

## 3. Cuisine → ÉTAPE 3 : LES FILTRES DU LOGGER

**L'image.** Dans la cuisine, une **passoire à spaghettis fluo verte** est suspendue au plafond et
**tourne en grinçant**. Chaque enveloppe doit y passer ; certaines restent coincées dans les trous et
**pendent lamentablement**, dégoulinant de sauce tomate. Une **main en caoutchouc** les décroche et les
balance à la poubelle.

**Lien → notion.** Les objets `Filter` attachés au **logger** (`logger.addFilter`). Deuxième barrage,
sur le contenu cette fois (ex. : ne garder que les logs d'un `run_id`). Refusé → abandon.

---

## 4. Table → ÉTAPE 4 : CRÉATION DU `LogRecord`

**L'image.** Sur la table de la salle à manger, une **imprimante 3D orange** vomit en trois secondes
un **plateau-repas compartimenté**, chaque case étiquetée à la craie : *heure*, *niveau*, *nom du
module*, *fichier*, *ligne*, *processus*. Mais la case centrale, celle du message, contient encore
l'enveloppe **avec son trou** et la pochette d'arguments **agrafée à côté, non ouverte**.

**Lien → notion.** Le `LogRecord` est fabriqué : tous les métadonnées (`asctime`, `levelname`, `name`,
`lineno`, `process`…) sont remplies. Le message, lui, **n'est toujours pas interpolé**.

---

## 5. Canapé → ÉTAPE 5 : `callHandlers` — LOGGER PUIS ANCÊTRES

**L'image.** Le canapé est une **famille de matriochkas empilées** qui se **passent le plateau de main
en main en chantant**, de la plus petite à la plus grande : `mon_pipeline.io.lecture` → `mon_pipeline.io`
→ `mon_pipeline` → `root`. Chaque matriochka a un **drapeau vert « PROPAGATE »** planté sur le crâne ;
si tu arraches le drapeau de l'une d'elles, la chaîne s'**arrête net** et le plateau tombe par terre.

**Lien → notion.** `callHandlers` remonte la **hiérarchie de loggers** (le point `.` du nom crée la
filiation) et exécute les handlers de **chaque ancêtre**, tant que `propagate` vaut `True`.
⚠️ En remontant, ce sont les **handlers** qu'on réévalue, **pas** les niveaux des loggers intermédiaires.

---

## 6. Fenêtre → ÉTAPE 6 : LE NIVEAU DE CHAQUE HANDLER (2e filtre)

**L'image.** À la fenêtre, un **second videur, jumeau du premier mais en costume jaune canari**, est
assis sur le rebord, jambes dans le vide. Il tient **sa propre barre lumineuse**, réglée **beaucoup
plus haut** que celle du couloir. Il rigole : « **le gars d'en bas t'a laissé passer, mais MOI je m'en
fous !** » et il balance l'enveloppe par la fenêtre, qui tombe en tournoyant dans la rue.

**Lien → notion.** **Chaque handler a son propre niveau**, totalement indépendant de celui du logger.
C'est le **deuxième filtrage**, et la cause n°1 des « j'ai mis DEBUG et je ne vois rien » : il faut
baisser **les deux**.

---

## 7. Bureau → ÉTAPE 7 : LES FILTRES DU HANDLER

**L'image.** Sur ton bureau, un **tamis d'orpailleur bleu électrique** vibre en cliquetant, secoué par
un **petit chercheur d'or barbu** qui recrache du gravier partout sur ton clavier. Il ne garde que les
paillettes et **souffle le reste** au sol en faisant « pfff ».

**Lien → notion.** Les `Filter` attachés au **handler** cette fois — mêmes objets qu'à la cuisine, mais
posés un cran plus loin, juste avant l'écriture.

---

## 8. Bibliothèque → ÉTAPE 8 : LE FORMATTER (c'est ICI que le `%s` est rempli)

**L'image.** Devant la bibliothèque, un **typographe du XIXᵉ siècle en blouse tachée d'encre** attrape
l'enveloppe trouée, **décachette enfin la pochette agrafée**, et **enfonce la valeur `v` dans le trou**
avec un gros **CLAC** de presse à imprimer. L'encre gicle, ça sent le solvant. Il colle par-dessus une
bande de papier : `2026-09-09 03:12:44 INFO mon_pipeline.io …`.

**Lien → notion.** Le **formatter** du handler construit la chaîne finale : c'est **le seul endroit du
parcours** où `"x=%s" % v` est réellement évalué. D'où : si le message a été jeté aux étapes 2 ou 6,
**l'interpolation n'a jamais lieu** — et c'est tout l'intérêt du `%s` sur la f-string.

---

## 9. Salle de bain → ÉTAPE 9 : `emit()` — L'ÉCRITURE

**L'image.** Dans la salle de bain, la **douche crache des lignes de texte au lieu de l'eau**, en
cascade lumineuse verte façon terminal. Un tuyau part vers **l'évier** (`stdout`), un autre vers la
**baignoire qui déborde** (le fichier qui tourne), un troisième traverse le mur en sifflant vers
**l'extérieur** (le socket vers l'agrégateur). Tu glisses sur le carrelage.

**Lien → notion.** `handler.emit()` écrit vraiment : `StreamHandler` (stdout),
`RotatingFileHandler(maxBytes, backupCount)`, `SysLogHandler`, `QueueHandler`. En conteneur : **JSON
structuré sur stdout**, et c'est le collecteur qui route.

---

## 10. Chambre → ÉTAPE 10 : REMONTÉE AU PARENT, SINON `lastResort`

**L'image.** Dans la chambre, ton lit est un **ascenseur qui monte tout seul en grinçant** vers un
grenier plein de matriochkas. Et si, tout en haut, **personne n'attend** — aucun handler nulle part —
une **vieille dame en peignoir gris**, l'air agacé, se lève, écrit ton message **au crayon sur un
bout de papier journal** et le glisse sous la porte d'à côté (`stderr`), en marmonnant :
« **je ne prends que les avertissements et au-dessus, hein.** »

**Lien → notion.** La propagation remonte jusqu'à la racine. Si **aucun** handler n'a été trouvé sur
tout le chemin, `logging.lastResort` écrit un message minimal sur **`stderr`**, au niveau
**`WARNING`** — d'où l'impression que « les logs INFO ne marchent pas » quand rien n'est configuré.

---

## Parcours de récitation (une phrase enchaînée)

> **Le facteur en scaphandre** poste une enveloppe **trouée** avec sa pochette d'arguments, le
> **videur violet** du couloir la mesure au thermomètre, la **passoire verte** de la cuisine l'égoutte,
> l'**imprimante orange** de la table lui fabrique un plateau-repas étiqueté, les **matriochkas** du
> canapé se le passent tant que le drapeau vert tient, le **videur jaune** de la fenêtre le rejette
> quand même, le **chercheur d'or** du bureau le tamise, le **typographe** de la bibliothèque enfonce
> enfin la valeur dans le trou d'un grand CLAC, la **douche** de la salle de bain le crache vers
> stdout, le fichier et le réseau — et si le lit-ascenseur de la chambre ne trouve personne là-haut,
> la **vieille dame en peignoir** le griffonne sur stderr en ronchonnant qu'elle ne prend que les
> WARNING.

**Test d'ancrage** : refais le parcours **à l'envers**, du 10 au 1. Puis réponds sans marcher :
« c'est quoi l'étape 6 ? » → le **niveau du handler**, le second filtrage. « Et l'étape 8 ? » →
le **formatter**, seul endroit où le `%s` est interpolé.
