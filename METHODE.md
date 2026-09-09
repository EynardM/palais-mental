# MÉTHODE — le mode de fonctionnement

> Ce fichier est le contrat. Tout le reste (cours, fiches, cartes) n'est que du matériel.
> Si tu ne dois lire qu'un fichier avant de commencer : celui-ci.

---

## 1. Le principe fondateur : on compte des MODULES, pas des heures

Tu as annoncé une disponibilité très variable : **1h à 3h en semaine, 4h à 10h le week-end**.
Un planning en heures serait donc faux dès le 2e jour. Un planning en objectifs, non.

**L'unité de travail est le MODULE.** Un module = un sujet fermé, avec un critère de
validation binaire (tu sais / tu ne sais pas). Un module coûte **~1h à 1h30** en cycle
complet.

Conséquence pratique :

| Temps dispo réel | Ce que tu fais |
|---|---|
| 1h | 1 module en cycle court (S-P-R, pas d'ancrage) + rappels du jour |
| 2h | 1 module en cycle complet + rappels + 1 fiche relue |
| 3h | 2 modules en cycle complet + rappels |
| 4h (WE) | 3 modules + séance d'ancrage longue |
| 6-8h (WE) | 4-5 modules + 1 atelier pratique |
| 10h (WE) | 5-6 modules + atelier + simulation d'entretien technique |

Tu ne "prends pas de retard" quand tu n'as qu'1h. Tu avances d'un module de moins.
La roadmap est dimensionnée sur l'hypothèse basse (39h) pour le **noyau 🔴**, et le
surplus va dans les modules 🟠 et 🟢.

---

## 2. La boucle SPRE — comment on traite UN module

Quatre temps. Toujours les mêmes. C'est ce qui rend l'effort automatique.

### S — Survol (5 min)
Tu ouvres **la fiche de révision AVANT le cours**. Oui, avant.
Tu la lis en te demandant : « ça veut dire quoi ? je devinerais quoi ? »

> **Pourquoi ça marche** : c'est le *pretesting*. Échouer à une question avant
> d'apprendre la réponse augmente la rétention de ~30 % par rapport à la lecture seule.
> Ton cerveau crée les "trous" que le cours vient combler. Sans trous, rien ne s'accroche.

### P — Plongée (40 à 90 min)
Tu lis le cours. **Jamais passivement.** Règles :
- À chaque titre de section, tu t'arrêtes 5 secondes : « qu'est-ce qui va être dit ? »
- Chaque encadré `❓ RETIENS ÇA` : tu caches la réponse avec la main, tu réponds, tu vérifies.
- Chaque schéma : tu le **redessines** sur papier sans regarder. Le geste ancre.
- Tu ne surligne pas. Surligner est l'illusion la plus coûteuse du travail intellectuel :
  ça crée un sentiment de familiarité sans aucune trace mémorielle.

### R — Restitution (15 min) ← **l'étape que tout le monde saute, et la plus rentable**
Tu **fermes tout**. Feuille blanche. Tu réécris la fiche de mémoire :
les idées clés, les schémas, les chiffres.
Puis tu ouvres la vraie fiche et tu compares **en rouge**.

Le rouge est ta liste de travail. Ce qui est en rouge part en flashcards prioritaires.

> **Pourquoi ça marche** : c'est l'*active recall*. L'acte d'aller chercher en mémoire
> renforce la trace bien plus que l'acte d'y remettre l'information. Relire = ranger un
> livre. Se rappeler = construire la route qui y mène.

### E — Encrage (10 min)
- Tu passes les **flashcards** du module (dans Anki, ou avec le CSV brut).
- Tu accroches les listes dures dans ton **palais mental** (voir §4).
- Tu fais le **Feynman** : à voix haute, 3 minutes, tu expliques le module comme à
  quelqu'un qui n'y connaît rien. Si tu bafouilles quelque part, c'est là que tu n'as
  pas compris. Retour au cours sur ce point précis uniquement.

---

## 3. La répétition espacée — comment on ne perd pas ce qui est acquis

Apprendre 40 modules en 21 jours sans révision = en avoir 8 à l'arrivée.
La courbe de l'oubli est brutale : ~70 % perdu en 48h sans rappel.

**Chaque module vu au jour J est rappelé à J+1, J+3, J+7, J+14.**

Un rappel n'est pas une relecture. C'est **2 à 5 minutes** :
1. Tu lis le titre du module.
2. Tu récites la fiche de mémoire, à voix haute ou sur papier.
3. Tu ouvres la fiche, tu vérifies.
4. Tu notes dans `PROGRESSION.md` : ✅ (ça vient tout seul) ou ⚠️ (ça a coincé).

Un ⚠️ remet le compteur à zéro : le module repasse en J+1.

`PROGRESSION.md` contient la table de rappel : chaque jour tu regardes la ligne du jour,
elle te dit exactement quoi rappeler. Tu n'as jamais à réfléchir à ce qu'il faut réviser.

Cette table est **calculée sur tes dates réelles**, pas sur les dates prévues. Quand tu termines
la Plongée d'un module, tu renseignes sa colonne « Vu le » puis tu lances `./outils/rappels.py` :
le calendrier se réaligne. Un jour de décalage ne désynchronise donc jamais tes rappels — ce qui
compte, puisque tu vas décaler.

**Ordre de la séance, toujours :** rappels d'abord (à froid, c'est le but), nouveau module ensuite.

---

## 4. Les techniques de mémorisation — la boîte à outils

Tu as dit avoir besoin de beaucoup mémoriser. Voilà l'arsenal, avec le cas d'usage de chacune.
**On n'applique pas les 9 à chaque module** — chaque cours te dira laquelle utiliser.

| # | Technique | Pour quoi | Coût |
|---|---|---|---|
| 1 | **Active recall** | Tout, toujours. La base non négociable. | Gratuit |
| 2 | **Répétition espacée** | Tout, toujours. | 10 min/j |
| 3 | **Palais mental (loci)** | Listes **ordonnées** : 7 couches OSI, étapes du handshake TCP, ordre d'exécution SQL, phases d'un job Spark | Élevé, réservé aux listes qui résistent |
| 4 | **Chunking / acronymes** | Listes courtes non ordonnées : les 4 V du big data, ACID, CAP | Faible |
| 5 | **Analogie & récit** | Concepts abstraits : le shuffle Spark, le backpressure Kafka, l'attention d'un Transformer | Faible, très rentable |
| 6 | **Feynman** | Vérifier qu'on a *compris* et pas juste retenu. Prépare littéralement l'entretien. | 3 min |
| 7 | **Dessin de mémoire** | Toute architecture, tout protocole, tout flux de données | 5 min |
| 8 | **Interleaving** | Mélanger réseau/data/devops dans une même séance plutôt que blocs purs | Gratuit |
| 9 | **Élaboration** | Demander « pourquoi ? » et « et si on faisait autrement ? » à chaque affirmation | Gratuit |

### Le palais mental — mode d'emploi (c'est le nom du repo, autant s'en servir)

1. **Choisis un lieu que tu connais par cœur** : ton appartement, le trajet domicile-boulot,
   ta salle de sport. Il doit avoir un **parcours naturel et toujours identique**.
2. **Fixe 10 emplacements** dans l'ordre du parcours (porte d'entrée → couloir → cuisine → ...).
   Écris-les une fois pour toutes dans `palais/00-mes-lieux.md`. **Ne change plus jamais l'ordre.**
3. Pour chaque liste à retenir, place un **objet mental absurde, en mouvement, coloré,
   sonore** à chaque emplacement. Plus c'est ridicule, mieux ça tient : le cerveau retient
   l'anormal et jette le raisonnable.
4. Pour réciter : tu **marches mentalement** dans le lieu. La liste sort dans l'ordre.

Chaque cours qui contient une liste ordonnée te fournit un palais **déjà écrit** dans
`palais/`. Tu peux l'utiliser tel quel, mais il tiendra deux fois mieux si tu remplaces
mes images par les tiennes — l'image que *tu* fabriques bat toujours l'image qu'on te donne.

Un seul lieu suffit pour tout : on réutilise les mêmes 10 emplacements pour plusieurs
listes. Les interférences sont bien plus faibles qu'on ne le craint, à condition que les
images soient franchement distinctes.

---

## 5. Les 5 niveaux de maîtrise

Pour chaque module, tu notes ton niveau dans `PROGRESSION.md` :

| Niveau | Sens | Comment tu le sais |
|---|---|---|
| **N0** | Pas vu | — |
| **N1** | Lu | J'ai fait la plongée |
| **N2** | Restitué | J'ai réécrit la fiche de mémoire sans trou majeur |
| **N3** | Expliqué | Feynman 3 min sans notes, à voix haute, sans bafouiller |
| **N4** | Appliqué | J'ai fait l'atelier / répondu à la question d'entretien type |

Un **Survol seul** — la fiche lue sans le cours — ne fait pas passer à `N1`. Il se note dans
la colonne « Notes ». C'est une distinction qui a l'air tatillonne et qui ne l'est pas : un
tracker qui compte les survols comme des lectures te dira que tu es prêt alors que tu ne l'es pas.

**🎯 Objectif au 29/09 : tous les modules 🔴 en N3 minimum, les 🟠 en N2 minimum.**

N3 est le vrai seuil : c'est le niveau où tu tiens une conversation technique.
N1 ne sert à rien en entretien comme en réunion. Ne te laisse pas rassurer par du N1 en masse.

---

## 6. Le rituel quotidien

### Matin (ou avant de commencer) — 2 min
1. Ouvrir `PROGRESSION.md`, regarder la ligne du jour.
2. Décider **honnêtement** ton budget temps du jour.
3. Me demander la séance (voir §7).

### Séance
1. **Rappels espacés** d'abord (5-15 min selon la charge du jour).
2. **Module(s) du jour** en boucle SPRE.
3. **Atelier** si week-end.

### Fin de séance — 5 min
1. Mettre à jour `PROGRESSION.md` (niveaux atteints, ⚠️ éventuels).
2. Écrire 3 lignes dans `journal/AAAA-MM-JJ.md` :
   - ce qui est entré tout seul
   - ce qui résiste
   - une question que je me pose encore

Le journal n'est pas de la coquetterie : relire « ce qui résiste » au bout d'une semaine
te montre tes vrais points faibles, ceux que ton ressenti à chaud te cache.

---

## 7. Comment on travaille ensemble (le protocole de génération)

Tu génères le matériel **au fil de l'eau**, pas tout d'avance. Deux raisons : le contenu
s'adapte à ce qui résiste, et un stock de 40 modules non lus est démoralisant.

**Chaque jour, tu m'écris une ligne de ce type :**

```
go J-18 — 5h dispo
```

ou plus librement :

```
go, j'ai 2h ce soir, et le BGP d'hier n'est pas passé
```

**Je réponds avec :**
1. La **séance du jour** : rappels à faire + modules à traiter, calibrés sur ton temps réel.
2. Les **fichiers générés** (cours + fiche + cheatsheet + flashcards + palais si besoin),
   commités et poussés.
3. La **mise à jour de `PROGRESSION.md`**.

**Signaux utiles à me donner** (ils changent ce que je génère) :
- `⚠️ [module] n'est pas passé` → je regénère une explication sous un autre angle,
  avec plus d'analogies et un exercice ciblé.
- `j'ai que 45 min` → je te donne un module en format court, pas un module tronqué.
- `on m'a parlé de X en entretien / à l'onboarding` → j'insère un module hors roadmap.
- `je veux pratiquer, pas lire` → je bascule sur un atelier avec correction.

---

## 8. Les 6 règles qui font la différence

1. **Rappels avant nouveauté.** Toujours. Un module de plus vaut moins qu'un module gardé.
2. **Jamais de lecture sans restitution.** Un cours lu et non restitué compte comme non lu — et il coûte une illusion de progrès en plus.
3. **Ne pas surligner. Ne pas recopier.** Fermer le fichier et écrire de mémoire.
4. **À voix haute.** Le Feynman marmonné ne marche pas. Articuler force à structurer.
5. **Papier pour les schémas.** Le geste manuscrit ancre mieux que la frappe, particulièrement pour le spatial (topologies, architectures, flux).
6. **Un jour raté ne se rattrape pas, il se réabsorbe.** Tu ne doubles pas la dose le lendemain (ça casse le rythme et la qualité). Tu décales, et le surplus du week-end absorbe.

---

## 9. Ce qu'on vise vraiment

Le 30 septembre, tu n'as pas besoin d'être un expert. Tu as besoin de :

- **Comprendre ce qui se dit** dans une réunion technique sans décrocher.
- **Poser les bonnes questions** — c'est le vrai marqueur de niveau à l'arrivée.
- **Savoir où chercher** : reconnaître le sujet, savoir dans quel cours revenir.
- **Ne pas être bloqué** sur les gestes du quotidien : Linux, git, Docker, SQL, un DAG Airflow.

Le reste s'apprendra en poste, et bien plus vite parce que la carte sera déjà là.
Ces 21 jours servent à construire la **carte**, pas à visiter chaque rue.
