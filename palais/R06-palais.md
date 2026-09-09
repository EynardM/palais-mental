# R06 — PALAIS MENTAL : les 11 états de la vie d'une connexion TCP (10 emplacements + 1 annexe)

> **Pourquoi un palais ici** : la machine à états TCP est une **liste ordonnée de 11 états** dont on te demandera
> la séquence en entretien, et que tu liras tous les jours dans `ss`. Elle ne se retient pas par relecture — elle
> se retient par **déplacement**. Les 10 emplacements du parcours portent les 10 états du cycle normal ; le 11ᵉ,
> `CLOSING` (fermeture simultanée), est un cas rare qu'on accroche en annexe à la fin.
>
> **Attention à un point** : les emplacements 6, 7 et 10 sont vécus par **celui qui ferme en premier** (fermeture
> active), les emplacements 8 et 9 par **celui qui subit** (fermeture passive). Le parcours suit la connexion, pas
> une seule machine. C'est justement ce que la plupart des candidats mélangent.
>
> **Parcours utilisé** : les 10 emplacements standard de `palais/00-mes-lieux.md` —
> 1. porte d'entrée · 2. couloir · 3. cuisine · 4. table · 5. canapé · 6. fenêtre · 7. bureau ·
> 8. bibliothèque · 9. salle de bain · 10. chambre.
>
> **Mode d'emploi** : lis chaque image **les yeux fermés**, en te plaçant physiquement à l'emplacement. Fais bouger
> l'image, mets-y de la couleur et du bruit. Puis refais le trajet sans le texte, et une fois **à l'envers**
> (10 → 1) : si l'envers passe, c'est ancré.

---

## La liste à ancrer

```
  OUVERTURE          ┌── CLOSED ──► LISTEN ──► SYN_SENT ──► SYN_RCVD ──┐
                     │     (1)        (2)         (3)          (4)     │
                     │                                                 ▼
  VIE                │                                          ESTABLISHED (5)
                     │                                                 │
  FERMETURE ACTIVE   │   FIN_WAIT_1 (6) ──► FIN_WAIT_2 (7) ────────────┤
  (celui qui ferme)  │                                                 │
  FERMETURE PASSIVE  │   CLOSE_WAIT (8) ──► LAST_ACK (9) ──────────────┤
  (celui qui subit)  │                                                 │
                     └── TIME_WAIT (10), 2×MSL = 60 s Linux ───────────┘

                  + CLOSING : le 11ᵉ, fermeture simultanée (annexe)
```

---

## 1. Porte d'entrée — CLOSED

**L'image** : ta porte d'entrée n'a **plus de serrure, plus de numéro, plus de boîte aux lettres** — juste un
rectangle de bois gris peint à la va-vite. Tu tapes dessus : **aucun son**, le bois avale le bruit. Une pancarte
en carton pend de travers, sur laquelle quelqu'un a écrit au feutre rouge « **PERSONNE N'HABITE ICI** », et le
carton se décolle et tombe par terre en tournoyant.

**Le lien** : **CLOSED** — aucune socket, aucun état en mémoire, rien à qui parler. C'est l'état de départ **et**
l'état d'arrivée. Un paquet qui arrive ici reçoit un **RST**.

## 2. Couloir — LISTEN

**L'image** : dans le couloir, une **standardiste en tailleur jaune fluo** est assise devant **quatre mille casiers
vides** empilés jusqu'au plafond. Elle ne bouge pas, ne parle pas, mais ses yeux balaient la porte sans arrêt,
*clic-clic-clic*, comme une caméra de surveillance. Sur son bureau, un panneau : « **4096** ».

**Le lien** : **LISTEN** — le serveur attend des SYN. Les casiers sont l'**accept queue**, dont la taille vaut
`min(backlog de listen(), net.core.somaxconn)` — et **somaxconn vaut 4096** depuis Linux 5.4. Dans `ss -lnt`,
`Recv-Q`/`Send-Q` sur un LISTEN = **casiers occupés / casiers totaux**.

## 3. Cuisine — SYN_SENT

**L'image** : dans la cuisine, tu hurles ton prénom dans le **conduit de la hotte aspirante**, à pleins poumons,
six fois de suite — et l'écho revient **toujours vide**. À chaque cri, un minuteur de cuisine rouge posé sur le
plan de travail **double** son temps : 1 s, 2, 4, 8, 16, 32, 64. Au dernier *dring*, il explose en morceaux de
plastique.

**Le lien** : **SYN_SENT** — le SYN est parti, on attend le SYN-ACK. `tcp_syn_retries = 6` retransmissions avec
**backoff exponentiel**, soit **≈ 127 secondes** avant que `connect()` abandonne. *Rester bloqué ici = pare-feu qui
jette les paquets, ou route de retour manquante.*

## 4. Table — SYN_RCVD

**L'image** : sur la table, **deux mains sortent du bois** et se serrent — mais une seule des deux a des doigts.
Un **biscuit en forme de cookie**, énorme et couvert de glaçage bleu, tourne sur lui-même au milieu de la table en
sifflant. Personne ne s'assoit encore : la chaise est tirée, mais vide.

**Le lien** : **SYN_RCVD** — le SYN est reçu, le SYN-ACK est parti, on attend le troisième segment. La connexion
est **semi-ouverte** et vit dans la **SYN queue** (`tcp_max_syn_backlog`). Le cookie = les **SYN cookies**
(`tcp_syncookies=1`), qui permettent de survivre à un SYN flood sans mémoriser d'état. *Beaucoup de SYN_RECV =
attaque, ou perte du 3ᵉ segment.*

## 5. Canapé — ESTABLISHED

**L'image** : sur le canapé, **deux personnes se lancent un ballon d'eau** sans arrêt, de plus en plus vite, en
comptant à voix haute **des grains de riz** — pas les ballons, les **grains** : « quatre mille, cinq mille quatre
cent soixante… ». Entre eux, deux **règles graduées transparentes** glissent l'une sur l'autre, et c'est **la plus
courte des deux** qui décide de la taille du prochain lancer.

**Le lien** : **ESTABLISHED** — les données circulent. TCP numérote des **octets** (les grains), jamais des
paquets. Les deux règles qui glissent = les deux **fenêtres** : `rwnd` (annoncée par le récepteur) et `cwnd`
(devinée par l'émetteur) — **on prend le minimum des deux**.

## 6. Fenêtre — FIN_WAIT_1

**L'image** : tu ouvres la fenêtre et tu **jettes ton téléphone dehors** en criant « **J'AI FINI DE PARLER !** ».
Le téléphone tombe dans un buisson. Tu restes penché, les deux mains sur le rebord, l'oreille tendue vers la rue,
**et rien ne remonte**. Le vent fait claquer le volet, *clac, clac*.

**Le lien** : **FIN_WAIT_1** — j'ai envoyé mon **FIN**, je n'ai **pas encore reçu son ACK**. C'est celui qui ferme
**en premier** qui passe par là. *Rester ici = le pair ne répond plus du tout.*

## 7. Bureau — FIN_WAIT_2

**L'image** : au bureau, un **tampon vert fluo** s'abat tout seul sur une feuille — *TCHAK* — et laisse la marque
« REÇU ». Mais en face de toi, un **collègue en peignoir** continue tranquillement de te dicter des chiffres, sans
lever les yeux, alors que **toi tu ne peux plus rien dire** : ta bouche est recouverte de scotch orange. Un
sablier d'une minute se vide à côté du tampon.

**Le lien** : **FIN_WAIT_2** — mon FIN est acquitté, mais le pair **peut encore émettre** : c'est le
**half-close** (`shutdown(fd, SHUT_WR)`). J'attends **son** FIN, avec un plafond de `tcp_fin_timeout` = **60 s**
(le sablier). *Bloqué ici = c'est le code **du pair** qui n'appelle pas `close()`.*

## 8. Bibliothèque — CLOSE_WAIT

**L'image** : dans la bibliothèque, **des centaines de livres restent ouverts, à plat, empilés partout**, jusqu'à
te bloquer le passage. Un bibliothécaire minuscule crie « **FERME-LES ! FERME-LES !** » d'une voix stridente en
sautant sur place, mais **tes bras sont dans le plâtre** et tu ne peux rien fermer. La pile s'effondre sur ton pied.

**Le lien** : **CLOSE_WAIT** — j'ai **reçu** le FIN du pair, mon noyau l'a acquitté, et il attend que **mon
application appelle `close()`**. Les livres ouverts = les **descripteurs de fichiers**. Des CLOSE_WAIT qui
s'accumulent, **c'est TON bug** : `try` sans `finally`, session HTTP non fermée. Ça finit en `EMFILE`.

## 9. Salle de bain — LAST_ACK

**L'image** : tu tires la chasse d'eau, tu sors, tu fermes la porte — puis tu **restes planté devant, la main sur
la poignée**, à attendre le **dernier « bloup »** de la citerne. Tant que ce bloup n'a pas retenti, tu ne bouges
pas. Il arrive enfin, *bloup*, et la porte **disparaît d'un coup**, comme effacée.

**Le lien** : **LAST_ACK** — j'ai envoyé mon FIN à mon tour, j'attends **l'accusé final**. Dès qu'il arrive, je
passe directement en **CLOSED**, sans aucune attente : celui qui ferme **en second** n'a **pas** de TIME_WAIT.

## 10. Chambre — TIME_WAIT

**L'image** : dans la chambre, tu es assis sur le lit tout habillé, manteau sur le dos, à **regarder un réveil
géant** qui affiche **60** en chiffres rouges et décompte à voix haute. Par la fenêtre, tu vois un **facteur en
scooter** finir sa tournée dans le quartier ; tant qu'il roule, tu ne te couches pas. Deux **lettres fantômes**,
translucides, flottent dans la pièce et s'évaporent une par une dans un *pshhh*.

**Le lien** : **TIME_WAIT** — l'état de **celui qui a fermé en premier**, pendant **2 × MSL** = **60 s en dur sous
Linux**. Deux raisons, les deux images : le **réveil et le facteur** = pouvoir **ré-acquitter** si le dernier ACK
s'est perdu ; les **lettres fantômes** = laisser **mourir les vieux segments** avant de réutiliser le quadruplet.
Côté client, 28 232 ports / 60 s ⇒ **≈ 470 connexions/s** avant `EADDRNOTAVAIL`.

---

## Annexe — le 11ᵉ état : CLOSING

**L'image** : sous le lit, **deux aspirateurs se foncent dessus en même temps** et se percutent de plein fouet
dans un fracas de plastique. Aucun des deux n'avait cédé le passage.

**Le lien** : **CLOSING** — les deux côtés ont envoyé leur FIN **simultanément**, avant d'avoir reçu celui de
l'autre. Rare, parfaitement normal, et on en sort vers **TIME_WAIT**.

---

## Parcours de récitation

> Je pousse la **porte grise sans serrure** (*CLOSED*), je croise dans le **couloir la standardiste aux 4096
> casiers vides** (*LISTEN*), à la **cuisine je hurle six fois dans la hotte et le minuteur double** (*SYN_SENT*),
> sur la **table deux mains se serrent autour d'un cookie qui tourne** (*SYN_RCVD*, SYN cookies), sur le **canapé
> on se lance un ballon en comptant les grains de riz entre deux règles qui glissent** (*ESTABLISHED*, octets et
> min(rwnd, cwnd)), à la **fenêtre je jette mon téléphone en criant que j'ai fini** (*FIN_WAIT_1*), au **bureau le
> tampon vert tombe mais le collègue en peignoir continue de parler** (*FIN_WAIT_2*, half-close), à la
> **bibliothèque les livres ouverts s'empilent et j'ai les bras dans le plâtre** (*CLOSE_WAIT*, fuite de FD), dans
> la **salle de bain j'attends le dernier bloup de la citerne** (*LAST_ACK*), et dans la **chambre je fixe le
> réveil à 60 pendant que le facteur finit sa tournée et que les lettres fantômes s'évaporent** (*TIME_WAIT*).

**Test** : refais le parcours **à l'envers**, de la chambre à la porte d'entrée. Puis demande-toi « c'est quoi le
8 ? » — la réponse doit venir **immédiatement** : la bibliothèque, donc **CLOSE_WAIT**, donc **c'est mon
application qui n'appelle pas `close()`**.

**Deuxième test, celui qui compte en entretien** : pour chaque emplacement, dis **de quel côté** il se vit.
6, 7 et 10 → celui qui **ferme** ; 8 et 9 → celui qui **subit**. Si tu sais dire ça, tu sais lire un `ss` en
production.
