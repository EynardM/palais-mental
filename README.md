# 🧠 Palais Mental

**Programme de remise à niveau intensive — 21 jours, du 9 au 30 septembre 2026.**
Objectif : prise de poste **Data Engineer**, forte composante **réseau**, composante **IA**.

---

## Par où commencer

1. **Lis [`METHODE.md`](METHODE.md)** — 15 minutes. C'est le contrat de fonctionnement.
   Ne saute pas cette étape : le matériel ne vaut rien sans la méthode qui va avec.
2. **Parcours [`ROADMAP.md`](ROADMAP.md)** — les 47 modules, les 4 sprints, les objectifs de validation.
3. **Remplis [`palais/00-mes-lieux.md`](palais/00-mes-lieux.md)** — 10 minutes, une seule fois.
   Tes 10 emplacements mentaux, réutilisés pendant tout le programme.
4. **Ouvre [`PROGRESSION.md`](PROGRESSION.md)** — c'est ton tableau de bord quotidien.
5. **Commence par `R01`.**

---

## Comment c'est rangé

```
palais-mental/
├── METHODE.md          ← le mode de fonctionnement (à lire en premier)
├── ROADMAP.md          ← les 47 modules, 4 sprints, jour par jour
├── PROGRESSION.md      ← ton tableau de bord : niveaux + calendrier de rappel
│
├── cours/              ← les cours copieux (60-90 min de lecture chacun)
│   ├── reseau/  devops/  data/  ia/  langages/
├── fiches/             ← 1 page dense par module, récitable en 3 min
├── cheatsheets/        ← référence opérationnelle, à garder ouverte
├── flashcards/         ← cartes mémoire au format TSV (import Anki direct)
├── palais/             ← palais mentaux pour les listes ordonnées
├── quiz/               ← auto-évaluations et simulations d'entretien
├── journal/            ← 3 lignes par jour : acquis / résiste / question
└── templates/          ← gabarits des différents formats
```

---

## Les 5 formats, et à quoi sert chacun

| Format | Quand | Durée | Rôle |
|---|---|---|---|
| **Cours** | Découverte | 60-90 min | Comprendre. Dense, avec schémas, analogies, exercices corrigés, questions d'entretien. |
| **Fiche** | Avant ET après le cours | 3-5 min | Amorcer (pretesting), puis réciter de mémoire lors des rappels. |
| **Cheatsheet** | Pendant la pratique | — | Référence. Ne se mémorise pas, se consulte. |
| **Flashcards** | Tous les jours | 10 min | Ancrer les détails : chiffres, ports, valeurs par défaut. Ce qui se perd en premier. |
| **Palais** | Listes ordonnées | 10 min | Retenir une séquence dans l'ordre exact, pour toujours. |

---

## Le cycle sur un module : **SPRE**

```
   S            P                R                 E
 Survol  →   Plongée    →   Restitution   →     Encrage
  5 min      40-90 min        15 min             10 min
   │            │                │                  │
 lire la     lire le        FERMER TOUT         flashcards
  fiche       cours          réécrire de          + palais
  AVANT      activement      mémoire             + Feynman
   │            │            comparer en rouge     3 min
   ▼            ▼                ▼                  ▼
 créer les   remplir        révéler ce qui      ancrer dans
  "trous"    les trous      n'est PAS acquis     la durée
```

**L'étape R est celle que tout le monde saute. C'est la plus rentable des quatre.**
Un cours lu sans restitution compte comme non lu — et coûte en plus une illusion de progrès.

---

## Le rythme

Pas de planning en heures : la disponibilité est trop variable (1-3h en semaine, 4-10h le week-end).
**On compte des modules.** Un module ≈ 1h-1h30 en cycle complet.

Les 47 modules sont hiérarchisés :
- 🔴 **35 modules noyau** — le socle du poste, non négociable (~40-50h)
- 🟠 **11 modules importants** — passent de "je suis la conversation" à "je contribue" (~15h)
- 🟢 **1 module bonus** — confort

**Une journée à 1h n'est pas un échec.** C'est un module de moins, absorbé par le week-end suivant.

---

## Le protocole quotidien

Chaque jour, une ligne suffit :

```
go J-18 — 5h dispo
```

ou, plus utilement :

```
go, 2h ce soir, et le BGP d'hier n'est pas passé
```

En retour : la séance calibrée sur le temps réel (rappels + modules), les fichiers générés
et poussés, et `PROGRESSION.md` mis à jour.

**Signaux qui changent ce qui est généré :**

| Tu dis | Il se passe |
|---|---|
| `⚠️ [module] pas passé` | Réexplication sous un autre angle, plus d'analogies, exercice ciblé |
| `j'ai que 45 min` | Un module en **format court** — pas un module tronqué |
| `on m'a parlé de X` | Module hors roadmap inséré |
| `je veux pratiquer` | Atelier avec correction, au lieu d'un cours |

---

## Importer les flashcards dans Anki

Les cartes sont en TSV (`question<TAB>réponse`, sans en-tête).

1. Anki → *Fichier* → *Importer* → sélectionner le `.tsv`
2. Type de note : **Basique**
3. Séparateur : **Tabulation**
4. Champ 1 → *Recto*, Champ 2 → *Verso*
5. Un deck par famille : `Palais::Réseau`, `Palais::Data`, `Palais::DevOps`, `Palais::IA`, `Palais::Langages`

Sans Anki, le TSV se lit très bien dans un tableur en masquant la colonne B.

**Outil fourni** : `./outils/anki.sh valider` contrôle le format de toutes les cartes,
`./outils/anki.sh build` assemble un deck par famille dans `outils/decks/`.

---

## Tenir le tableau de bord à jour

Quand tu termines la **Plongée** d'un module, renseigne sa colonne « Vu le » dans
`PROGRESSION.md`, puis :

```
./outils/rappels.py
```

Le calendrier de rappel espacé est recalculé sur tes **dates réelles**. Un décalage d'une
journée ne désynchronise donc rien.

Un **Survol** seul (fiche lue sans le cours) ne compte pas comme `N1` : il se note dans la
colonne « Notes ».

---

## L'objectif réel du 30 septembre

Pas d'être expert. D'être :

- capable de **suivre** une réunion technique sans décrocher
- capable de **poser les bonnes questions** — c'est le vrai marqueur de niveau à l'arrivée
- capable de **savoir où chercher** : reconnaître le sujet, savoir dans quel cours revenir
- **non bloqué** sur les gestes du quotidien : Linux, git, Docker, SQL, un DAG Airflow

Ces 21 jours construisent la **carte**. Les rues se visiteront en poste — beaucoup plus vite
avec la carte en main.
