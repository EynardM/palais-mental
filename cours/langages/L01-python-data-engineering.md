# L01 — Python pour data engineering

> **Ce que tu sauras faire à la fin**
> - Expliquer ce qu'est réellement une variable en Python (une **étiquette sur un objet**), prédire sans exécuter le résultat d'un programme qui mute des structures partagées, et désamorcer le piège de l'argument par défaut mutable.
> - Choisir la bonne structure de données en justifiant par sa **complexité réelle** — et savoir dire pourquoi un `in` sur une liste de 100 000 éléments fait exploser un job qui tournait en 3 secondes.
> - Écrire un pipeline de **générateurs** qui traite un fichier de 50 Go dans 200 Mo de RAM, et expliquer pourquoi la paresse (*lazy evaluation*) est le paradigme par défaut du data engineering.
> - Écrire un décorateur `retry` avec backoff exponentiel, un `timing`, un cache — et savoir pourquoi `functools.wraps` n'est pas décoratif.
> - Typer une codebase (annotations, `mypy --strict`), modéliser une donnée avec `dataclass` (interne) ou **Pydantic** (frontière d'entrée), et savoir précisément lequel valide à l'exécution.
> - Structurer un projet publiable : `src/` layout, `pyproject.toml`, environnement virtuel, `uv`/`poetry`, tests `pytest` avec fixtures, paramétrage et mocks, **logging** structuré (jamais de `print`), lecture/écriture CSV/JSON/Parquet.
> - Expliquer le **GIL** en trois phrases, dire pour chaque charge (I/O, CPU, NumPy) s'il faut des threads, des processus ou de l'asyncio — et calculer le gain attendu.
>
> **Pourquoi ça compte dans ton poste**
> Python est la langue franche du data engineering : les DAG Airflow, les jobs PySpark, les collecteurs
> de télémétrie réseau (SNMP, gNMI, NetFlow), les clients d'API d'équipements et les pipelines
> d'inférence sont écrits dedans. Mais un pipeline n'est pas un notebook : il tourne **sans personne
> devant**, à 3 h du matin, sur des volumes qui ne tiennent pas en mémoire, et un échec silencieux
> pollue les données en aval pendant des semaines. Ce qu'on attend de toi n'est pas « savoir Python » —
> c'est écrire du code **typé, testé, journalisé, paresseux et packagé**, dont on peut relire le
> comportement six mois plus tard. C'est aussi la compétence la plus visible en entretien : c'est le
> seul module de ce programme où on te fera écrire du code au tableau.
>
> **Prérequis** : `D01` (processus, descripteurs, codes de sortie, signaux) et `D03` (shell, redirections,
> codes de retour) — on s'y appuie pour le GIL, les sous-processus et le packaging. `R08` aide pour les
> exemples HTTP.
> **Durée de lecture** : 80-95 min. Garde un REPL ouvert : la moitié des affirmations de ce cours se
> vérifie en trois lignes, et ce qu'on vérifie soi-même s'oublie beaucoup moins vite.

---

## 1. Le modèle objet : une variable n'est pas une boîte

**La question** : quand tu écris `b = a`, est-ce que tu copies la donnée ?

En C, `int b = a;` copie 4 octets. En Python, **non**, et cette différence explique 80 % des bugs
étranges d'un débutant qui a des bases en langage compilé.

En Python, une variable est une **étiquette collée sur un objet**. L'objet vit dans le tas, il porte son
type et son compteur de références. `b = a` colle une deuxième étiquette sur **le même objet**.

```
        a = [1, 2, 3]
        b = a
        b.append(4)

     ┌───┐                ┌──────────────────────────────┐
     │ a │───────────────▶│ objet list  #0x7f3a...       │
     └───┘        ┌──────▶│ refcount = 2                 │
     ┌───┐        │       │ [1, 2, 3, 4]   ◀── muté !    │
     │ b │────────┘       └──────────────────────────────┘
     └───┘

     Deux étiquettes, UN SEUL objet. print(a) -> [1, 2, 3, 4]
```

L'analogie : une variable est un **post-it avec un nom**, pas un tiroir. Coller un deuxième post-it
« b » sur le carton « a » ne duplique pas le carton. Si tu mets un objet de plus dans le carton, les
deux post-it désignent toujours le carton — désormais plus rempli.

Trois opérateurs à ne jamais confondre :

| Opérateur | Question posée | Coût |
|---|---|---|
| `is` | **même objet** ? (compare les identités, `id()`) | O(1), comparaison de pointeurs |
| `==` | **même valeur** ? (appelle `__eq__`) | dépend du type, potentiellement O(n) |
| `id(x)` | l'adresse-identité de l'objet | O(1) |

> ⚠️ **PIÈGE** — `a is b` peut être **vrai par accident**. CPython met en cache les petits entiers de
> **-5 à 256** et interne les chaînes qui ressemblent à des identifiants. D'où :
> `a = 256; b = 256; a is b` → `True`, mais `a = 257; b = 257; a is b` → `False` (en script ;
> dans une même ligne du REPL, l'optimiseur de constantes peut te rendre `True`).
> **Conclusion opérationnelle : `is` uniquement pour `None`, `True`, `False`.** Jamais pour comparer
> des valeurs. `if x is None:` — jamais `if x == None:`.

> ❓ **RETIENS ÇA** — Quelle est la seule utilisation légitime de `is` dans du code de production ?
> <details><summary>→ réponse</summary><br>La comparaison aux <b>singletons</b> : <code>is None</code>, <code>is True</code>, <code>is False</code>, et les sentinelles que tu crées toi-même (<code>_MANQUANT = object()</code>). Tout le reste utilise <code>==</code>.</details>

### Comptage de références et ramasse-miettes

CPython libère un objet dès que son compteur de références tombe à 0 — c'est **déterministe**, à la
différence de Java. Un ramasse-miettes générationnel (3 générations, seuils par défaut **700, 10, 10**)
passe en plus pour casser les **cycles** (`a.b = b; b.a = a`), que le comptage seul ne peut pas libérer.

Conséquence pratique : un fichier ouvert sans `with` est **souvent** fermé à temps par le refcount…
et pas du tout sous PyPy ou avec un cycle. D'où la règle : **toujours `with`** (section 9).

---

## 2. Mutable / immuable, copies, et le piège n°1 des entretiens

**La question** : pourquoi certains objets se laissent-ils modifier en place et pas d'autres ?

| Immuables | Mutables |
|---|---|
| `int`, `float`, `bool`, `str`, `bytes`, `tuple`, `frozenset`, `None` | `list`, `dict`, `set`, `bytearray`, la plupart des objets utilisateurs |
| **hachables** → utilisables comme clé de `dict` ou élément de `set` | **non hachables** → `TypeError: unhashable type: 'list'` |

La règle qui relie les deux colonnes : **hachable ≈ immuable**. Un `dict` retrouve une clé par son hash ;
si la clé changeait après insertion, l'objet serait perdu dans une case où plus personne ne le cherche.
Python interdit donc les clés mutables.

```
    d = {}
    d[[1,2]] = "x"     ->  TypeError: unhashable type: 'list'
    d[(1,2)] = "x"     ->  OK, un tuple est gelé donc hachable
    d[(1,[2])] = "x"   ->  TypeError ! un tuple n'est hachable que si TOUT son contenu l'est
```

> 🧠 **MÉMO** — « **Ce qui bouge ne peut pas servir d'adresse.** » Tu ne peux pas domicilier quelqu'un
> à une adresse qui se déplace : la lettre n'arriverait jamais. Même logique pour la clé d'un `dict`.

### Copie superficielle vs copie profonde

```
   original = [[1, 2], [3, 4]]

   surface = original.copy()   (ou list(original), ou original[:], ou copy.copy)

   ┌──────────┐        ┌──────────────┐
   │ original │───────▶│ liste ext. A │──┬──▶ [1, 2]  ◀────┐
   └──────────┘        └──────────────┘  └──▶ [3, 4]  ◀──┐ │
   ┌──────────┐        ┌──────────────┐                  │ │
   │ surface  │───────▶│ liste ext. B │──────────────────┴─┘
   └──────────┘        └──────────────┘   MÊMES listes internes !

   surface.append([9])     -> n'affecte QUE surface   (niveau 1 dupliqué)
   surface[0].append(99)   -> affecte AUSSI original  (niveau 2 partagé)

   profonde = copy.deepcopy(original)   -> tout est recréé, aucun partage
```

`copy.deepcopy` suit le graphe d'objets, gère les cycles (il mémorise ce qu'il a déjà copié dans un
dict `memo`) — et il est **lent** : compte un ordre de grandeur de 10 à 100× le coût d'une copie
superficielle. En pipeline, on ne `deepcopy` pas dans une boucle sur 10 millions de lignes ; on
construit un nouvel objet.

> ❓ **RETIENS ÇA** — `list(x)`, `x[:]`, `x.copy()` : quelle profondeur de copie ?
> <details><summary>→ réponse</summary><br>Les trois font exactement la même chose : une <b>copie superficielle</b> (shallow). Le conteneur externe est neuf, les objets contenus sont <b>partagés</b>. Seul <code>copy.deepcopy()</code> descend récursivement.</details>

### Le piège de l'argument par défaut mutable

C'est **la** question posée en entretien Python, tous niveaux confondus.

```python
def ajouter(item, panier=[]):        # ← BUG
    panier.append(item)
    return panier

ajouter("a")   # ['a']
ajouter("b")   # ['a', 'b']   ← surprise : le panier n'est pas vide !
```

**Pourquoi** : la valeur par défaut est évaluée **une seule fois**, à la **définition** de la fonction,
et stockée dans `fonction.__defaults__`. Ce n'est pas « une liste vide à chaque appel », c'est
« **cette** liste-là, pour toujours ».

```
   au moment du def :        __defaults__ = ( [] , )
                                             │
   appel 1 --------------------------------->│ append("a")  -> ['a']
   appel 2 --------------------------------->│ append("b")  -> ['a','b']
                                             ▼
                              UN SEUL objet, partagé par tous les appels,
                              qui survit entre les appels et entre les threads.
```

Le correctif canonique :

```python
def ajouter(item, panier: list | None = None) -> list:
    if panier is None:
        panier = []
    panier.append(item)
    return panier
```

> ⚠️ **PIÈGE** — Le même bug frappe `def f(cache={})`, `def f(t=datetime.now())` (le timestamp est
> figé au chargement du module !) et `@dataclass class C: tags: list = []` — ce dernier lève
> carrément une `ValueError` à la définition, et t'oblige à écrire `field(default_factory=list)`.

> 🧠 **MÉMO** — « **Le `def` s'exécute une fois, le corps s'exécute mille fois.** » Tout ce qui est
> écrit **sur la ligne du `def`** (valeurs par défaut, annotations évaluées) est calculé au chargement
> du module.

---

## 3. Les structures de données et leur coût réel

**La question** : ton job tournait en 3 s sur l'échantillon, il tourne en 4 h sur la prod. Pourquoi ?

Réponse quasi certaine : une **complexité linéaire dans une boucle**, donc un O(n²) déguisé.

### Le tableau à connaître par cœur

| Opération | `list` | `deque` | `dict` | `set` | `tuple` |
|---|---|---|---|---|---|
| accès par index `x[i]` | **O(1)** | O(n) au milieu | — | — | **O(1)** |
| accès par clé `d[k]` | — | — | **O(1)** moy. | — | — |
| `x in conteneur` | **O(n)** | O(n) | **O(1)** moy. | **O(1)** moy. | O(n) |
| `append` / ajout en fin | O(1) amorti | **O(1)** | O(1) moy. | O(1) moy. | immuable |
| insertion / retrait en **tête** | **O(n)** | **O(1)** | — | — | — |
| suppression par valeur | O(n) | O(n) | O(1) moy. | O(1) moy. | — |
| tri (`sorted`, `list.sort`) | O(n log n) | — | — | — | O(n log n) |
| mémoire (vide, CPython 64 bits) | 56 o | ~624 o | 64 o | 216 o | 40 o |

Précisions qui font la différence en entretien :

- **O(1) « moyen »** pour `dict`/`set` : le pire cas théorique est O(n) en cas de collisions massives.
  En pratique, avec le hachage randomisé de CPython, tu ne le rencontreras jamais par accident.
- **`append` amorti O(1)** : quand la liste est pleine, CPython réalloue en **sur-allouant d'environ
  12 %** ; le coût de la recopie, réparti sur les insertions, donne une moyenne constante.
- Un `dict` **redimensionne quand il est rempli aux 2/3** et croît d'un facteur 3 en nombre d'entrées
  utilisées.
- Depuis **Python 3.7**, l'ordre d'insertion d'un `dict` est **garanti par le langage** (c'était un
  détail d'implémentation en 3.6). Un `set`, lui, **n'a aucun ordre** — ne t'appuie jamais dessus.
- `list.sort()` / `sorted()` utilisent **Timsort** : O(n log n) au pire, **O(n)** sur des données déjà
  triées ou presque, et surtout **stable** (deux éléments égaux gardent leur ordre relatif) — propriété
  indispensable pour trier par clés successives.

> ❓ **RETIENS ÇA** — Complexité de `x in ma_liste` versus `x in mon_set` ?
> <details><summary>→ réponse</summary><br><b>O(n)</b> pour la liste (parcours élément par élément avec <code>==</code>) contre <b>O(1) en moyenne</b> pour le set (un calcul de hash puis un accès direct). C'est la transformation la plus rentable du data engineering débutant.</details>

### Exercice corrigé — la jointure qui met 4 heures

**Énoncé.** Tu croises une liste de 200 000 flux NetFlow avec une liste de 50 000 adresses IP
blacklistées. Version naïve :

```python
suspects = [f for f in flux if f.ip_dst in blacklist]   # blacklist est une list
```

Combien d'opérations élémentaires ? Et avec un `set` ?

**Correction pas à pas.**

1. La compréhension itère sur `flux` : **200 000** tours de boucle.
2. À chaque tour, `in blacklist` sur une **liste** parcourt la blacklist jusqu'à trouver, sinon jusqu'au
   bout. En moyenne sur des données où la plupart des IP ne matchent pas : **50 000** comparaisons.
3. Total ≈ 200 000 × 50 000 = **10 000 000 000** comparaisons, soit **10 milliards**.
4. À un ordre de grandeur de 10 millions de comparaisons Python par seconde (compte 30 à 100 ns par
   comparaison d'objets simples), ça fait ≈ **1000 s ≈ 17 minutes**, et bien plus si `==` porte sur des
   objets complexes.
5. Avec `blacklist = set(blacklist)` : la construction du set coûte **50 000** hachages, puis chaque test
   coûte **1** hachage. Total ≈ 50 000 + 200 000 = **250 000** opérations.

**Gain : 10 000 000 000 / 250 000 = 40 000×.** Une ligne changée, `set(...)` autour de la blacklist.

> 🧠 **MÉMO** — « **`in` sur une liste, c'est chercher un nom dans un annuaire non trié ; `in` sur un
> set, c'est ouvrir directement à la bonne page.** » Dès qu'un `in` est dans une boucle : set ou dict.

### Quand prendre quoi

| Besoin | Structure | Pourquoi |
|---|---|---|
| Séquence ordonnée, accès par position | `list` | index O(1) |
| File / fenêtre glissante, ajout aux deux bouts | `collections.deque` | `appendleft`/`popleft` en O(1) ; `deque(maxlen=N)` éjecte tout seul |
| Test d'appartenance, déduplication | `set` | O(1), et `&` `|` `-` `^` pour intersection/union/différence |
| Association clé → valeur | `dict` | O(1), ordre d'insertion garanti |
| Enregistrement figé, clé composite | `tuple` | hachable, 30 % plus compact qu'une liste |
| Comptage d'occurrences | `collections.Counter` | `.most_common(10)` |
| Regroupement | `collections.defaultdict(list)` | évite le `if k not in d` |
| Enregistrement nommé et léger | `NamedTuple` / `dataclass(slots=True)` | lisible, typé |
| Recherche dans une liste **triée** | module `bisect` | O(log n) sans construire de dict |
| Tableau numérique volumineux | `numpy.ndarray` | voir ci-dessous |

### Le coût mémoire d'un objet Python

```
   LISTE Python de 10 000 000 d'entiers        TABLEAU NumPy int64 équivalent

   ┌──────────────────────────┐                ┌───────────────────────────────┐
   │ liste : 10 M pointeurs   │  80 Mo         │ en-tête ~100 o                │
   │      × 8 octets          │                │ + 10 M × 8 octets = 80 Mo     │
   └───────────┬──────────────┘                └───────────────────────────────┘
               │ chaque pointeur vise…          UN SEUL bloc contigu.
               ▼                                Total ≈ 80 Mo
   ┌──────────────────────────┐
   │ objet int : ~28 octets   │  280 Mo
   │ × 10 M (hors cache -5..256)│
   └──────────────────────────┘
   TOTAL ≈ 360 Mo, éparpillés  ->  cache CPU inefficace
```

**Facteur ≈ 4,5× en mémoire, et bien plus en vitesse** parce que NumPy travaille sur un bloc contigu
(favorable au cache L1/L2) et en C, sans passer par l'interpréteur. Retiens l'ordre de grandeur :
**un `int` Python ≈ 28 octets, un `int64` ≈ 8 octets**.

> ⚠️ **PIÈGE** — Règle empirique à connaître : **1 Go de CSV chargé en objets Python occupe 5 à 10 Go
> de RAM.** C'est la raison pour laquelle on ne fait pas `rows = list(csv.DictReader(f))` sur un fichier
> de production. La suite du cours (§5) montre l'alternative.

### Compréhensions

Une compréhension n'est pas du sucre syntaxique cosmétique : elle est **exécutée dans une fonction
implicite compilée**, donc plus rapide qu'une boucle `for` + `append` (de l'ordre de 20 à 40 %),
et elle exprime l'intention en une ligne.

```python
carres   = [x*x for x in nums if x % 2 == 0]        # list
uniques  = {u.ip for u in flux}                     # set
index    = {u.id: u for u in users}                 # dict
paresseux= (ligne.strip() for ligne in fichier)     # GÉNÉRATEUR (parenthèses)
```

Les quatre s'écrivent pareil, **les parenthèses changent tout** : les trois premières construisent
l'intégralité du résultat en mémoire, la quatrième ne construit rien du tout tant qu'on ne l'itère pas.

L'ordre de lecture d'une compréhension imbriquée est celui des `for` **écrits de gauche à droite**,
comme des boucles imbriquées :

```python
plat = [c for ligne in matrice for c in ligne]      # == for ligne: for c in ligne: append(c)
```

> ⚠️ **PIÈGE** — Une compréhension de plus de deux `for` ou avec un `if` complexe devient illisible.
> Règle d'équipe : **une compréhension doit tenir sur une ligne mentale**. Au-delà, une boucle nommée
> ou une fonction générateur.

---

## 4. Itérateurs et générateurs : le cœur du traitement de gros volumes

**La question** : comment lire un fichier de 50 Go sur une machine qui a 8 Go de RAM ?

Réponse : ne jamais le charger. Le traiter **élément par élément**, à la demande. C'est le protocole
d'itération, et c'est le paradigme structurant de tout ton métier.

### Le protocole, en deux méthodes

```
   for x in objet:            se traduit EXACTEMENT en :

   it = iter(objet)           # appelle objet.__iter__()  -> renvoie un ITÉRATEUR
   while True:
       try:
           x = next(it)       # appelle it.__next__()
       except StopIteration:  # l'itérateur est épuisé -> fin normale de boucle
           break
       ...corps de la boucle...
```

Deux rôles distincts, souvent confondus :

| | **Itérable** | **Itérateur** |
|---|---|---|
| Méthode requise | `__iter__` | `__iter__` **et** `__next__` |
| Peut être parcouru plusieurs fois | oui (`list`, `dict`, `str`, fichier ? non) | **non**, à usage unique |
| Exemple | `[1,2,3]`, `{'a':1}`, un `range` | `iter([1,2,3])`, un générateur, un objet fichier |

```
   ITÉRABLE  ──iter()──▶  ITÉRATEUR  ──next()──▶ valeur
   (réutilisable)         (jetable)   ──next()──▶ valeur
                                      ──next()──▶ StopIteration  (définitif)
```

> ⚠️ **PIÈGE** — Un objet fichier **est son propre itérateur**. Après une première boucle `for ligne in
> f:`, une deuxième boucle sur le même `f` ne rend **rien** : le curseur est en fin de fichier et
> l'itérateur est épuisé. Même chose pour un générateur : le consommer deux fois donne un résultat
> vide la seconde fois, **sans aucune erreur**. C'est un bug silencieux, donc pire qu'un crash.

> ❓ **RETIENS ÇA** — Quelle exception marque la fin normale d'une itération ?
> <details><summary>→ réponse</summary><br><code>StopIteration</code>. Elle est levée par <code>__next__()</code> et <b>attrapée par la boucle <code>for</code></b>, qui la transforme en sortie de boucle. C'est le seul cas où une exception fait partie du fonctionnement normal.</details>

### `yield` : une fonction qui se met en pause

Une fonction qui contient `yield` **n'est plus une fonction** : l'appeler ne s'exécute pas, ça
fabrique un objet générateur. Le corps ne tourne qu'au premier `next()`.

```python
def lire_lignes(chemin: str):
    with open(chemin, encoding="utf-8") as f:
        for ligne in f:
            yield ligne.rstrip("\n")     # rend la main ICI, garde tout l'état local
```

```
   MACHINE À ÉTATS D'UN GÉNÉRATEUR

     gen = lire_lignes(p)
          │
          ▼
     ┌──────────┐  next() ┌──────────┐ yield ┌─────────────┐
     │  CRÉÉ    │────────▶│ EN COURS │──────▶│  SUSPENDU   │
     │ (0 code  │         │ (exécute)│◀──────│ (état local │
     │  exécuté)│         └────┬─────┘ next()│  conservé,  │
     └──────────┘              │             │  pile figée)│
                        return │             └─────────────┘
                        ou fin │
                               ▼
                        ┌──────────────┐
                        │    FERMÉ     │  tout next() ultérieur -> StopIteration
                        └──────────────┘
```

L'analogie : une fonction normale est un **sprinteur** — il part, il finit, il te donne le résultat.
Un générateur est un **serveur au bar** : il te sert un verre, il s'arrête, il attend. Tu ne le paies
que pour les verres que tu demandes, et il se souvient exactement où il en était.

**Ce que ça change concrètement :**

```python
# ✗ 2 Go de CSV -> ~10 Go de RAM -> OOM killer (code de sortie 137, cf. D01)
lignes = f.readlines()
propres = [nettoyer(l) for l in lignes]
valides = [l for l in propres if valide(l)]

# ✓ mémoire constante, ~quelques Mo, quel que soit le volume
lignes  = (l for l in f)
propres = (nettoyer(l) for l in lignes)
valides = (l for l in propres if valide(l))
for l in valides:            # RIEN ne s'exécute avant cette ligne
    ecrire(l)
```

```
   PIPELINE PARESSEUX — le tirage vient de la DROITE

   fichier ──▶ [gen lire] ──▶ [gen nettoyer] ──▶ [gen filtrer] ──▶ for
   50 Go        1 ligne         1 ligne            1 ligne         écrit

   Chaque next() du for remonte la chaîne, fait circuler UNE seule ligne,
   et redescend. Aucune liste intermédiaire n'existe jamais.
   Mémoire = O(1) au lieu de O(n).
```

> 🧠 **MÉMO** — « **Crochets = tout en mémoire. Parenthèses = un à la fois.** »
> `[x for x in y]` construit. `(x for x in y)` promet.

> ❓ **RETIENS ÇA** — Que renvoie l'appel d'une fonction contenant `yield` ?
> <details><summary>→ réponse</summary><br>Un <b>objet générateur</b>, et <b>aucune ligne du corps n'a été exécutée</b>. Le code démarre au premier <code>next()</code> (donc au premier tour de la boucle <code>for</code> qui le consomme).</details>

> ⚠️ **PIÈGE** — Un générateur n'a **pas de `len()`**, ne se **slice** pas (`gen[10:20]` → `TypeError`),
> et ne se parcourt qu'une fois. Pour un slice paresseux : `itertools.islice(gen, 10, 20)`. Pour compter
> sans stocker : `sum(1 for _ in gen)`.

### `yield from`, et la boîte à outils `itertools`

`yield from sous_generateur` délègue : il relaie toutes les valeurs du sous-générateur (et remonte sa
valeur de retour). Il remplace `for x in sub: yield x`.

| Outil | Ce qu'il fait | Usage data |
|---|---|---|
| `itertools.islice(it, n)` | les n premiers, paresseusement | échantillonner un flux |
| `itertools.chain(a, b)` | concatène des itérables | fusionner des shards |
| `itertools.chain.from_iterable(x)` | aplatit un itérable d'itérables | dé-imbriquer sans mémoire |
| `itertools.groupby(it, key)` | regroupe les **consécutifs** | agréger un flux **déjà trié** |
| `itertools.tee(it, 2)` | duplique un itérateur | ⚠️ met en tampon ce qui n'est pas encore lu |
| `itertools.batched(it, n)` (3.12+) | paquets de n | écrire par lots en base |
| `enumerate(it, start=1)` | index + valeur | numéros de ligne |
| `zip(a, b, strict=True)` (3.10+) | apparie ; `strict` lève si tailles ≠ | éviter la troncature silencieuse |

> ⚠️ **PIÈGE** — `groupby` ne groupe que les éléments **consécutifs**. Sur des données non triées, il
> te rendra dix groupes pour la même clé. Trie d'abord sur la même clé, ou utilise un `defaultdict`.
> Et `zip` **tronque silencieusement** à la plus courte des séquences : d'où `strict=True`.

---

## 5. Les fonctions : `*args`, `**kwargs`, closures, décorateurs

### Signatures

```python
def f(a, b=2, *args, c, d=4, **kwargs): ...
#     └┬─┘  └┬─┘  └─┬─┘  └┬────┬┘  └──┬──┘
#      │     │      │     │    │      └── dict des kwargs restants
#      │     │      │     └────┴───────── APRÈS *args = keyword-only OBLIGATOIRE
#      │     │      └────────────────────  tuple des positionnels restants
#      │     └───────────────────────────  positionnel ou nommé, avec défaut
#      └─────────────────────────────────  positionnel ou nommé
```

Deux marqueurs à connaître : `def f(a, b, /, c, *, d)` — tout ce qui est **avant `/`** est
**positionnel uniquement**, tout ce qui est **après `*`** est **nommé uniquement**. En code de prod,
`*` est très utile : `def charger(chemin, *, ecraser=False)` interdit `charger(p, True)` — un booléen
positionnel est illisible six mois plus tard.

À l'appel, `*` et `**` **déballent** : `f(*ma_liste, **mon_dict)`.

### Closures

```python
def multiplicateur(n):
    def interne(x):
        return x * n          # n vient de la portée englobante : c'est une CLOSURE
    return interne

double = multiplicateur(2)
double(21)      # 42 ; l'objet fonction a capturé n dans double.__closure__
```

Règle de résolution des noms — **LEGB** : **L**ocal → **E**nglobant (closure) → **G**lobal (module) →
**B**uiltins. Pour écrire dans une portée supérieure : `nonlocal` (englobante) ou `global` (module).
En pratique, un `global` en code de production est presque toujours une faute de conception.

> ⚠️ **PIÈGE** — La closure capture la **variable**, pas sa valeur. D'où le classique :
> ```python
> fs = [lambda: i for i in range(3)]
> [f() for f in fs]      # [2, 2, 2] et non [0, 1, 2]
> ```
> Correctif : `lambda i=i: i` (la valeur par défaut, elle, est évaluée tout de suite — cf. §2).

### Décorateurs

**La question** : comment ajouter un comportement (mesurer, réessayer, mettre en cache, journaliser) à
20 fonctions **sans toucher leur code** ?

Un décorateur est une fonction qui prend une fonction et en rend une autre. `@deco` au-dessus de
`def f` est **exactement** `f = deco(f)`.

```
        appel utilisateur
              │
              ▼
     ┌──────────────────┐   avant : log, chrono, verrou, validation
     │    wrapper       │
     │   ┌──────────┐   │
     │   │ f() réel │   │
     │   └──────────┘   │
     │                  │   après : mesure, cache, gestion d'exception, retry
     └──────────────────┘
              │
              ▼
          résultat
```

Le squelette à savoir écrire au tableau, **sans hésiter** :

```python
import functools, logging, time

logger = logging.getLogger(__name__)

def chrono(func):
    @functools.wraps(func)                 # ← INDISPENSABLE
    def wrapper(*args, **kwargs):
        t0 = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            logger.info("%s a duré %.3f s", func.__qualname__, time.perf_counter() - t0)
    return wrapper
```

`functools.wraps` recopie `__name__`, `__doc__`, `__module__`, `__qualname__`, `__dict__` et pose
`__wrapped__`. Sans lui, toutes tes fonctions décorées s'appellent `wrapper`, tes traces sont
illisibles, Sphinx documente `wrapper`, et `inspect.signature` ment.

Décorateur **paramétré** : c'est un niveau d'imbrication de plus — `@retry(3)` s'évalue d'abord en
appelant `retry(3)`, qui doit **rendre un décorateur**.

```python
def retry(tentatives: int = 3, delai: float = 1.0, facteur: float = 2.0,
          exceptions: tuple[type[BaseException], ...] = (ConnectionError, TimeoutError)):
    def decorateur(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            attente = delai
            for essai in range(1, tentatives + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    if essai == tentatives:
                        logger.error("%s : échec définitif après %d essais", func.__name__, essai)
                        raise
                    logger.warning("%s : essai %d/%d échoué (%s), retry dans %.1fs",
                                   func.__name__, essai, tentatives, exc, attente)
                    time.sleep(attente)
                    attente *= facteur          # backoff exponentiel : 1s, 2s, 4s, 8s…
        return wrapper
    return decorateur
```

Deux points qu'un intervieweur cherchera :
1. **On ne retente que les erreurs transitoires.** Retenter un `ValueError` de parsing, c'est refaire
   trois fois la même erreur. Retenter un HTTP 500/503 ou un timeout, oui ; un 400 ou un 401, non.
2. **Backoff exponentiel + jitter.** Sans aléa, 500 workers qui échouent en même temps retentent en
   même temps : c'est le *thundering herd*. En prod : `attente = min(plafond, delai * facteur**n) *
   random.uniform(0.5, 1.5)`.

Le cache, en une ligne :

```python
from functools import lru_cache, cache

@lru_cache(maxsize=128)          # 128 est le DÉFAUT ; maxsize=None = illimité
def resoudre_asn(ip: str) -> int: ...

resoudre_asn.cache_info()        # CacheInfo(hits=…, misses=…, maxsize=128, currsize=…)
resoudre_asn.cache_clear()
```

`functools.cache` (3.9+) est l'alias de `lru_cache(maxsize=None)`.

> ⚠️ **PIÈGE** — `lru_cache` exige des **arguments hachables** (pas de `list`, pas de `dict`), garde
> une **référence forte** sur les arguments et les résultats (fuite mémoire si `maxsize=None` sur un
> flux d'IP unique), et est **par processus** — inutile pour partager entre workers. Sur une méthode,
> il retient `self` et empêche la libération de l'instance : préfère `functools.cached_property`.

> ❓ **RETIENS ÇA** — Que fait exactement `@functools.wraps(func)` et pourquoi est-ce obligatoire ?
> <details><summary>→ réponse</summary><br>Il recopie les métadonnées de la fonction d'origine (<code>__name__</code>, <code>__doc__</code>, <code>__qualname__</code>, <code>__module__</code>, <code>__dict__</code>) sur le wrapper et pose <code>__wrapped__</code>. Sans lui, la fonction décorée <b>perd son identité</b> : logs, tracebacks, doc et introspection affichent « wrapper ».</details>

---

## 6. Le typage : annotations, `mypy`, `dataclass`, Pydantic

**La question** : dans une codebase de 40 000 lignes, comment sais-tu ce que contient le dict que la
fonction d'à côté te renvoie ?

Sans annotations : tu le devines, tu te trompes, tu plantes en prod. C'est pour ça que le typage n'est
plus optionnel dans une équipe data professionnelle.

### Les annotations ne font rien à l'exécution

```python
def moyenne(valeurs: list[float]) -> float:
    return sum(valeurs) / len(valeurs)

moyenne("bonjour")     # aucune erreur de typage ! Python ne vérifie RIEN
```

Les annotations sont stockées dans `__annotations__` et **ignorées par l'interpréteur**. Elles servent
à trois consommateurs : **toi** (documentation exécutable), **mypy/pyright** (vérification statique en
CI), et les bibliothèques qui les lisent à l'exécution (**Pydantic**, FastAPI, `dataclasses`).

Syntaxe moderne à utiliser :

| Ancien (à ne plus écrire) | Moderne | Depuis |
|---|---|---|
| `List[int]`, `Dict[str, int]` | `list[int]`, `dict[str, int]` | 3.9 (PEP 585) |
| `Optional[int]`, `Union[int, str]` | `int \| None`, `int \| str` | 3.10 (PEP 604) |
| — | `type Alias = ...` | 3.12 |

Autres types utiles : `Iterable`/`Iterator`/`Sequence`/`Mapping` (depuis `collections.abc`) en
**entrée** — accepte plus large ; `list`/`dict` concrets en **sortie**. `Any` désactive la
vérification (à limiter). `Final`, `Literal["csv","parquet"]`, `TypedDict`, `Protocol` (typage
structurel, « duck typing vérifié »), `TypeVar`/génériques.

```bash
mypy --strict src/          # la cible ; commence par mypy src/ et durcis progressivement
```

`--strict` implique notamment `disallow_untyped_defs` (toute fonction doit être annotée),
`warn_return_any`, `no_implicit_optional`. En CI, `mypy` doit **casser le build**.

> ❓ **RETIENS ÇA** — Une annotation de type est-elle vérifiée à l'exécution par CPython ?
> <details><summary>→ réponse</summary><br><b>Non, jamais.</b> Elle est stockée dans <code>__annotations__</code> et ignorée. La vérification est faite <b>hors exécution</b> par un outil externe (mypy, pyright) — sauf si une bibliothèque comme Pydantic la lit délibérément pour valider à l'exécution.</details>

### `dataclass` : la structure de données interne

```python
from dataclasses import dataclass, field

@dataclass(frozen=True, slots=True)
class FluxReseau:
    ip_src: str
    ip_dst: str
    port_dst: int
    octets: int = 0
    tags: list[str] = field(default_factory=list)   # JAMAIS = []

    def __post_init__(self) -> None:
        if not 0 < self.port_dst < 65536:
            raise ValueError(f"port invalide : {self.port_dst}")
```

Le décorateur **génère** `__init__`, `__repr__`, `__eq__` (et `__hash__` si `frozen=True`).
Paramètres utiles :

| Paramètre | Défaut | Effet |
|---|---|---|
| `frozen` | `False` | immuable → **hachable**, utilisable en clé de dict/set |
| `slots` (3.10+) | `False` | supprime le `__dict__` par instance : **~30-40 % de RAM en moins** et accès attribut plus rapide |
| `order` | `False` | génère `<`, `<=`, `>`, `>=` |
| `kw_only` (3.10+) | `False` | force les arguments nommés |

> ⚠️ **PIÈGE** — `frozen=True` n'est **pas** une immuabilité profonde : `flux.tags.append("x")` marche
> toujours, parce que la liste, elle, est mutable. Seule la **réaffectation** de l'attribut est bloquée.

### Pydantic : la frontière d'entrée

`dataclass` **ne valide rien**. Si ta donnée vient de l'extérieur (API, Kafka, YAML de config,
fichier client), tu veux une validation **à l'exécution**. C'est le rôle de Pydantic (v2, dont le cœur
`pydantic-core` est écrit en Rust — d'où un gain de vitesse d'un ordre de grandeur sur la v1).

```python
from pydantic import BaseModel, Field, field_validator

class ConfigCollecteur(BaseModel):
    hote: str
    port: int = Field(default=161, ge=1, le=65535)     # SNMP
    communaute: str = "public"
    timeout_s: float = Field(default=5.0, gt=0)
    interfaces: list[str] = Field(default_factory=list)

    @field_validator("hote")
    @classmethod
    def hote_non_vide(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("hôte vide")
        return v

cfg = ConfigCollecteur.model_validate(yaml.safe_load(texte))   # lève ValidationError si non conforme
cfg.model_dump()          # -> dict           cfg.model_dump_json()  -> str JSON
```

| | `dataclass` | `pydantic.BaseModel` |
|---|---|---|
| Dans la bibliothèque standard | ✅ | ❌ (dépendance) |
| Valide les types à l'exécution | ❌ | ✅ |
| Convertit `"161"` → `161` | ❌ | ✅ (mode par défaut, « lax ») |
| Coût à la création | ~nul | non nul (mais rapide en v2) |
| **Usage** | objets **internes**, chauds, nombreux | **frontières** : config, API, messages, I/O |

> 🧠 **MÉMO** — « **Pydantic à la douane, dataclass à l'intérieur du pays.** » On contrôle les papiers
> une fois, à l'entrée ; ensuite on circule librement.

---

## 7. Exceptions et gestion d'erreur robuste

**La question** : que doit faire ton job quand la troisième ligne du fichier est corrompue —
s'arrêter, ou continuer ?

Les deux réponses sont défendables ; ce qui est indéfendable, c'est de **ne pas décider**.

```
     BaseException
       ├── SystemExit            ← sys.exit()          } NE JAMAIS
       ├── KeyboardInterrupt     ← Ctrl-C              } LES ATTRAPER
       ├── GeneratorExit                               } par accident
       └── Exception             ← TOUT le reste, c'est ici qu'on attrape
             ├── ArithmeticError ── ZeroDivisionError
             ├── LookupError ──┬── KeyError
             │                 └── IndexError
             ├── OSError ──────┬── FileNotFoundError, PermissionError
             │                 ├── TimeoutError
             │                 └── ConnectionError ─┬─ ConnectionResetError
             │                                      └─ ConnectionRefusedError
             ├── ValueError ────── UnicodeDecodeError
             ├── TypeError
             └── (tes exceptions métier)
```

> ⚠️ **PIÈGE** — `except:` nu (ou `except BaseException`) attrape **aussi** `KeyboardInterrupt` et
> `SystemExit` : ton job devient **impossible à interrompre** au Ctrl-C et ignore les demandes d'arrêt.
> Écris toujours `except Exception:` au minimum, et de préférence l'exception précise.

Les cinq règles :

1. **Attraper le plus précis possible.** `except KeyError` et non `except Exception`.
2. **Ne jamais avaler une exception.** `except Exception: pass` est la pire ligne de Python. Au
   minimum `logger.exception(...)`.
3. **Enrichir sans perdre la cause** : `raise ErreurIngestion(f"ligne {n}") from exc`. Le `from`
   remplit `__cause__` et la trace affiche « The above exception was the direct cause of… ».
4. **`try` le plus court possible** : une seule ligne risquée dans le `try`, le reste dans le `else`.
5. **Définir ses exceptions métier**, dérivées d'une base unique par projet :
   `class ErreurPipeline(Exception): ...` → l'appelant peut tout attraper d'un coup.

```python
try:
    donnees = charger(chemin)          # la seule ligne risquée
except FileNotFoundError:
    logger.warning("source absente : %s — on saute", chemin)
    return None
except PermissionError as exc:
    raise ErreurPipeline(f"droits insuffisants sur {chemin}") from exc
else:
    return transformer(donnees)        # exécuté SI aucune exception
finally:
    metriques.incr("tentatives_chargement")   # exécuté DANS TOUS LES CAS
```

> ❓ **RETIENS ÇA** — Différence entre le bloc `else` et le bloc `finally` d'un `try` ?
> <details><summary>→ réponse</summary><br><code>else</code> ne s'exécute que si <b>aucune exception n'a été levée</b> dans le <code>try</code>. <code>finally</code> s'exécute <b>toujours</b> : succès, exception, et même <code>return</code>/<code>break</code> — c'est le bloc de nettoyage.</details>

> ⚠️ **PIÈGE** — Un `return` dans le `finally` **écrase** la valeur de retour du `try` **et avale
> l'exception en cours**. Ne mets jamais de `return` dans un `finally`.

À connaître aussi : `contextlib.suppress(FileNotFoundError)` (un `try/except/pass` explicite et lisible),
et depuis **3.11** les `ExceptionGroup` avec `except*`, utilisés notamment par `asyncio.TaskGroup`
quand plusieurs tâches parallèles échouent ensemble.

Enfin, l'idée à défendre en entretien : la stratégie d'erreur d'un pipeline se **choisit** :

| Stratégie | Quand | Comment |
|---|---|---|
| *Fail fast* | l'erreur signale une donnée corrompue en amont | on s'arrête, on alerte |
| *Skip + dead letter* | quelques lignes malformées sur des millions | on écrit la ligne dans un fichier/topic « rebut » et on compte |
| *Retry* | erreur **transitoire** (réseau, 503, timeout) | décorateur `retry` + backoff |
| *Circuit breaker* | la dépendance est durablement tombée | on arrête d'appeler pendant N s |

Et **toujours** un compteur : `lignes_lues`, `lignes_rejetées`, `taux_rejet`. Un pipeline qui rejette
silencieusement 40 % des lignes est plus dangereux qu'un pipeline qui plante.

---

## 8. Les context managers

**La question** : comment garantir qu'une ressource est libérée, même si le code plante au milieu ?

```
   with EXPR as v:            ┌──────────────────────────────────┐
       CORPS                  │ mgr = EXPR                       │
                              │ v = mgr.__enter__()              │
   se traduit en  ───────────▶│ try:      CORPS                  │
                              │ finally:  mgr.__exit__(t, v, tb) │
                              └──────────────────────────────────┘
```

`__exit__` reçoit le triplet (type, valeur, traceback) de l'exception en cours — ou `(None, None, None)`.
**S'il renvoie une valeur vraie, l'exception est supprimée.** C'est un pouvoir qu'on n'utilise
presque jamais : par défaut, ne renvoie rien.

Écrire le sien, forme courte :

```python
from contextlib import contextmanager

@contextmanager
def chrono(nom: str):
    t0 = time.perf_counter()
    try:
        yield                                    # tout ce qui est avant = __enter__
    finally:                                     # tout ce qui est après  = __exit__
        logger.info("%s : %.3f s", nom, time.perf_counter() - t0)

with chrono("ingestion"):
    ingerer()
```

Cas concrets en data engineering : `open()`, une transaction de base (`with conn.begin():`), un verrou,
un répertoire temporaire (`tempfile.TemporaryDirectory()`), une session HTTP, un `Timer`, la bascule
`os.chdir`, et surtout **l'écriture atomique** — écrire dans `fichier.tmp` puis `os.replace()`, pour ne
jamais laisser un fichier à moitié écrit dans le lac de données (`os.replace` est atomique sur le même
système de fichiers).

`contextlib.ExitStack` permet d'empiler un **nombre variable** de context managers (ouvrir N shards
et les fermer tous proprement) ; `contextlib.closing(obj)` fabrique un CM pour un objet qui n'a qu'un
`.close()`.

> ❓ **RETIENS ÇA** — Dans une fonction décorée par `@contextmanager`, que représente le `yield` ?
> <details><summary>→ réponse</summary><br>Le point exact où le <b>corps du <code>with</code></b> s'exécute. Ce qui est <b>avant</b> le <code>yield</code> est le <code>__enter__</code>, ce qui est <b>après</b> (donc dans le <code>finally</code>) est le <code>__exit__</code>. La valeur donnée par <code>yield</code> est ce que reçoit le <code>as</code>.</details>

---

## 9. Modules, packages, imports, structure de projet

**La question** : pourquoi `import mon_module` marche depuis le dossier du script mais pas depuis
ailleurs ?

Parce que l'import est une **recherche dans une liste de chemins**, et que cette liste dépend d'où tu
lances Python.

```
   import pandas
        │
        1. sys.modules  ── déjà importé ? ──▶ oui : on rend l'objet en cache, FIN
        │                                    (un module n'est exécuté QU'UNE FOIS)
        2. modules intégrés (sys, time…)
        3. parcours de sys.path, dans l'ORDRE :
             [0] répertoire du script lancé   (ou '' = cwd en mode -c / REPL)
             [1..] PYTHONPATH
             [..]  site-packages de l'environnement virtuel actif
        │
        4. trouvé -> compilation en .pyc (__pycache__) -> EXÉCUTION du module de haut en bas
        5. rien trouvé -> ModuleNotFoundError
```

Points qui règlent 90 % des problèmes d'import :

- **Le code au niveau module s'exécute à l'import.** Un `print`, une connexion réseau ou une lecture de
  fichier au top-level d'un module se déclenche pour tout le monde. Mets-les dans une fonction.
- `if __name__ == "__main__":` — `__name__` vaut `"__main__"` quand le fichier est **lancé**, et le nom
  du module quand il est **importé**. Sans cette garde, importer ton script exécute son main.
- **Imports absolus** (`from mon_pkg.io import lire`) partout. Les relatifs (`from .io import lire`)
  uniquement à l'intérieur d'un package, et jamais dans un fichier exécuté directement.
- **Import circulaire** : A importe B qui importe A. Symptôme : `ImportError: cannot import name X
  (most likely due to a circular import)`. Vrai correctif : extraire le code commun dans un module C.
  Palliatifs : importer dans la fonction, ou `if TYPE_CHECKING:` pour les imports servant uniquement
  aux annotations.
- `python -m mon_pkg.cli` est préférable à `python src/mon_pkg/cli.py` : le mode `-m` met le
  **répertoire courant** en tête de `sys.path` et respecte la structure du package.

### La structure de référence (layout `src/`)

```
mon-pipeline/
├── pyproject.toml            # identité, dépendances, config des outils. LA source de vérité
├── README.md
├── .gitignore                # .venv/, __pycache__/, *.pyc, .pytest_cache/, .ruff_cache/
├── .pre-commit-config.yaml
├── src/
│   └── mon_pipeline/         # nom d'IMPORT : underscores, pas de tirets
│       ├── __init__.py       # fait du répertoire un package ; garde-le quasi vide
│       ├── __main__.py       # permet `python -m mon_pipeline`
│       ├── config.py         # modèles Pydantic
│       ├── io/
│       │   ├── __init__.py
│       │   ├── lecture.py
│       │   └── ecriture.py
│       ├── transform.py
│       └── cli.py
├── tests/
│   ├── conftest.py           # fixtures partagées, découvert automatiquement par pytest
│   ├── test_transform.py
│   └── data/                 # petits fichiers d'exemple
└── scripts/                  # scripts d'exploitation (bash, cf. D03)
```

**Pourquoi `src/`** : sans lui, le répertoire courant est dans `sys.path`, donc tes tests importent le
code **source local** — même si le package est mal installé, même si un module manque du paquet
distribué. Avec `src/`, tes tests importent forcément la version **installée** : tu testes ce que tu
livres. C'est la disposition attendue dans une équipe pro.

> ❓ **RETIENS ÇA** — À quoi sert `if __name__ == "__main__":` ?
> <details><summary>→ réponse</summary><br>À exécuter un bloc <b>uniquement quand le fichier est lancé directement</b>, pas quand il est importé. <code>__name__</code> vaut <code>"__main__"</code> à l'exécution directe, et le nom du module à l'import.</details>

### `pyproject.toml`, environnements virtuels, `uv` / `poetry`

Un environnement virtuel est un **répertoire `.venv/` contenant son propre interpréteur et son propre
`site-packages`**. Il n'y a aucune magie : l'activer met `.venv/bin` en tête du `PATH`. Le but : deux
projets qui exigent deux versions incompatibles de `pyarrow` cohabitent sans se marcher dessus.

```bash
python -m venv .venv && source .venv/bin/activate    # standard, toujours disponible
uv venv                                              # équivalent, ~10× plus rapide
```

`pyproject.toml` (PEP 518/621) remplace `setup.py`, `setup.cfg` et `requirements.txt` :

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "mon-pipeline"                 # nom de DISTRIBUTION (tirets autorisés)
version = "0.3.1"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.6,<3",
    "pyarrow>=15",
    "httpx>=0.27",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-cov", "mypy", "ruff"]

[project.scripts]
mon-pipeline = "mon_pipeline.cli:main"    # crée l'exécutable dans .venv/bin/

[tool.ruff]
line-length = 100
[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]
[tool.mypy]
strict = true
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q --strict-markers"
```

| Outil | Rôle | Commandes clés |
|---|---|---|
| `pip` + `venv` | socle, toujours présent | `pip install -e ".[dev]"` (installation **éditable**) |
| **`uv`** (Astral, en Rust) | gestion env + dépendances + résolution, très rapide | `uv init`, `uv add pandas`, `uv sync`, `uv run pytest`, `uv lock` |
| `poetry` | équivalent, plus ancien, très répandu | `poetry add`, `poetry install`, `poetry lock`, `poetry build` |

> ⚠️ **PIÈGE** — **Un fichier de verrouillage (`uv.lock`, `poetry.lock`) se commite.** Il fige les
> versions **transitives** exactes : c'est lui, et pas `pyproject.toml`, qui rend un build
> reproductible. Sans lock, une mise à jour d'une dépendance de dépendance casse ta prod un mardi
> matin sans qu'aucun de tes commits n'ait changé.

> 🧠 **MÉMO** — « **`pyproject.toml` = ce que je veux. Lock = ce que j'ai eu.** »

---

## 10. Les tests : pytest

**La question** : comment savoir que ta transformation est encore juste après le refactoring de demain ?

`pytest` a gagné parce qu'il utilise le `assert` natif : il **réécrit le bytecode** des assertions pour
afficher les valeurs intermédiaires en cas d'échec, sans que tu apprennes `assertEqual`.

```python
# tests/test_transform.py
import pytest
from mon_pipeline.transform import normaliser_ip

def test_normalise_ipv4_avec_zeros():
    assert normaliser_ip("010.001.001.001") == "10.1.1.1"

@pytest.mark.parametrize(
    ("entree", "attendu"),
    [
        ("10.0.0.1",       "10.0.0.1"),
        ("  10.0.0.1  ",   "10.0.0.1"),
        ("::1",            "::1"),
        pytest.param("999.0.0.1", None, marks=pytest.mark.xfail(raises=ValueError)),
    ],
)
def test_normalise(entree, attendu):
    assert normaliser_ip(entree) == attendu

def test_ip_invalide_leve():
    with pytest.raises(ValueError, match="octet hors plage"):
        normaliser_ip("300.1.1.1")
```

`parametrize` crée **un test distinct par jeu de données** : un échec te dit exactement quel cas casse,
et tu ajoutes un cas de non-régression en une ligne.

### Fixtures

Une fixture est une **dépendance injectée par son nom d'argument**, avec un cycle de vie contrôlé.

```python
# tests/conftest.py — découvert automatiquement, pas besoin de l'importer
import pytest

@pytest.fixture(scope="session")          # créée UNE fois pour toute la session
def config():
    return ConfigCollecteur(hote="10.0.0.1")

@pytest.fixture                            # scope par défaut = "function"
def base_temporaire(tmp_path):             # tmp_path : fixture intégrée, répertoire unique
    chemin = tmp_path / "test.db"
    conn = connecter(chemin)
    yield conn                             # ← le test s'exécute ici
    conn.close()                           # ← teardown, exécuté même si le test échoue
```

| Scope | Créée une fois par… |
|---|---|
| `function` (défaut) | test |
| `class` | classe de tests |
| `module` | fichier |
| `package` | package de tests |
| `session` | exécution complète |

Fixtures intégrées à connaître : `tmp_path` (répertoire temporaire `pathlib`), `monkeypatch`
(patcher attributs/variables d'env avec restauration automatique), `capsys` (capture stdout/stderr),
`caplog` (capture les logs — c'est **comme ça** qu'on teste sa journalisation), `request`.

### Mocking

```python
from unittest.mock import patch, MagicMock

@patch("mon_pipeline.io.lecture.httpx.get")     # ← où c'est UTILISÉ, pas où c'est défini
def test_collecte_gere_le_503(mock_get):
    mock_get.return_value = MagicMock(status_code=503)
    with pytest.raises(ErreurTransitoire):
        collecter("10.0.0.1")
    assert mock_get.call_count == 3             # le retry a bien retenté 3 fois
```

> ⚠️ **PIÈGE** — **On patche là où le nom est cherché, pas là où il est défini.** Si
> `lecture.py` fait `from httpx import get`, il faut patcher `mon_pipeline.io.lecture.get` — patcher
> `httpx.get` n'aura aucun effet, parce que le module a déjà **sa propre référence** vers l'ancienne
> fonction. C'est la question de mocking posée en entretien.

> ❓ **RETIENS ÇA** — Que teste-t-on, et que mocke-t-on ?
> <details><summary>→ réponse</summary><br>On teste <b>sa propre logique</b> ; on mocke ce qui est <b>lent, non déterministe ou extérieur</b> : réseau, base, horloge, système de fichiers, aléatoire. Mocker sa propre logique métier ne teste plus rien — le test devient une répétition du code.</details>

Options de ligne de commande utiles : `-x` (stop au premier échec), `-k "ip and not lent"` (filtre par
nom), `-m lent` (filtre par marqueur), `--lf` (rejouer les derniers échecs), `-q`, `-s` (ne pas capturer
la sortie), `--durations=10` (les 10 tests les plus lents), `--cov=mon_pipeline` (couverture),
`-n auto` (parallélisation via pytest-xdist).

Pour un pipeline, l'ordre de rentabilité des tests est : **1)** les fonctions pures de transformation
(rapide, gros retour), **2)** les schémas Pydantic sur des échantillons réels tordus, **3)** un test
d'intégration bout-en-bout sur un petit fichier, **4)** des tests de qualité de données (assertions sur
le résultat : pas de doublon de clé, taux de nuls sous un seuil).

---

## 11. Le logging : pourquoi `print` est une faute professionnelle

**La question** : ton job a planté cette nuit à 3 h 12 sur un worker parmi 40. Qu'est-ce que tu lis ?

`print` écrit sur stdout, sans horodatage, sans niveau, sans nom de module, sans possibilité de filtrer,
sans destination configurable, et **sans être désactivable**. Le module `logging` fait tout cela.

| Niveau | Valeur | Quand |
|---|---|---|
| `NOTSET` | 0 | hérite du parent |
| `DEBUG` | **10** | détail de mise au point (désactivé en prod) |
| `INFO` | **20** | déroulé nominal : début/fin d'étape, volumes |
| `WARNING` | **30** | anormal mais géré (retry, ligne rejetée). **Défaut de la racine** |
| `ERROR` | **40** | une opération a échoué |
| `CRITICAL` | **50** | le processus ne peut pas continuer |

```python
import logging
logger = logging.getLogger(__name__)          # ← TOUJOURS __name__, jamais getLogger()

logger.info("ingestion démarrée source=%s lignes_attendues=%d", source, n)   # % différé !
try:
    ...
except ValueError:
    logger.exception("ligne %d illisible", num)      # = ERROR + traceback complet
```

Deux règles non négociables :

1. **`logger = logging.getLogger(__name__)` en haut de chaque module.** Ça crée une hiérarchie
   (`mon_pipeline.io.lecture` est enfant de `mon_pipeline.io`, enfant de `mon_pipeline`) : tu peux
   monter en DEBUG **une seule** partie du code en prod.
2. **Formatage différé avec `%s`, jamais de f-string.** `logger.debug("x=%s", gros_objet)` n'appelle
   `str()` **que si** DEBUG est actif ; `logger.debug(f"x={gros_objet}")` construit la chaîne **à tous
   les coups**, même si le message est jeté. Sur une boucle chaude, c'est mesurable.

### La chaîne de traitement d'un log (à connaître dans l'ordre)

```
   1  logger.info("msg %s", v)
   2  niveau EFFECTIF du logger  ── trop bas ? ──▶ ABANDON immédiat
   3  filtres du logger          ── refusé ?   ──▶ ABANDON
   4  création du LogRecord      (le %s n'est PAS encore interpolé)
   5  callHandlers : handlers du logger, puis ceux des ANCÊTRES tant que propagate=True
   6  niveau de CHAQUE handler   ── second filtrage, indépendant
   7  filtres du handler
   8  formatter du handler       (c'est ICI que le %s est interpolé)
   9  handler.emit()             -> stdout / fichier / socket / Loki
  10  remontée au parent ; si aucun handler nulle part -> lastResort (WARNING sur stderr)
```

> ⚠️ **PIÈGE** — **Deux niveaux filtrent, pas un.** Un `logger.setLevel(DEBUG)` sans baisser le niveau
> du **handler** ne fait rien apparaître. Symétriquement, en remontant aux ancêtres, seuls les
> **niveaux des handlers** sont réévalués, pas les niveaux des loggers intermédiaires. C'est la cause
> n°1 des « mes logs n'apparaissent pas ».

> ⚠️ **PIÈGE** — `logging.basicConfig()` **ne fait rien** si la racine a déjà un handler (appel double,
> ou bibliothèque tierce qui a configuré avant toi) — sauf avec `force=True` (3.8+). Et une
> **bibliothèque** ne configure jamais le logging : elle se contente de `getLogger(__name__)` et laisse
> l'application décider. Seul le point d'entrée configure.

Configuration d'application, en `dictConfig` (déclaratif, testable, versionnable) :

```python
logging.config.dictConfig({
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"std": {"format": "%(asctime)s %(levelname)-8s %(name)s %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "std", "level": "INFO"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {"mon_pipeline.io": {"level": "DEBUG"}},
})
```

En production conteneurisée : **logs structurés en JSON sur stdout**, une ligne par événement, avec un
`run_id`/`trace_id` pour recoller les événements d'un même job. C'est le collecteur (Fluent Bit,
Vector, Promtail) qui route — pas ton application.

> ❓ **RETIENS ÇA** — Pourquoi `logger.info("v=%s", v)` et non `logger.info(f"v={v}")` ?
> <details><summary>→ réponse</summary><br>Parce que l'interpolation est <b>différée jusqu'au formatter</b> : si le niveau filtre le message, la chaîne n'est jamais construite. La f-string, elle, est évaluée avant l'appel, donc <b>toujours</b>. Bonus : le message brut reste stable, ce qui permet de regrouper les occurrences côté agrégateur.</details>

---

## 12. Fichiers et formats : CSV, JSON, Parquet

### Les bases qui piègent

```python
from pathlib import Path
p = Path("/data/brut") / "flux.csv"          # jamais de concaténation de chaînes
p.parent.mkdir(parents=True, exist_ok=True)
p.stat().st_size, p.exists(), p.suffix, p.stem
```

| Point | Valeur / règle |
|---|---|
| Mode par défaut de `open()` | `"r"` = **texte**, lecture |
| Tampon par défaut | **8192 octets** (`io.DEFAULT_BUFFER_SIZE`) |
| Encodage par défaut | **celui de la locale** → UTF-8 sur Linux, souvent **cp1252 sur Windows** |
| Règle | **toujours `encoding="utf-8"` explicite**, en lecture comme en écriture |
| `newline=""` | **obligatoire** avec le module `csv` (sinon lignes vides sous Windows) |
| Écriture sûre | écrire dans `.tmp` puis `os.replace()` (atomique sur le même FS) |

> ⚠️ **PIÈGE** — L'oubli d'`encoding="utf-8"` est le bug data le plus répandu : il ne se manifeste pas
> chez toi (Linux, UTF-8) mais chez le collègue sous Windows, ou en CI, sous forme de
> `UnicodeDecodeError` sur la 4 millionième ligne — après 40 minutes de traitement. Pour les données
> sales, `errors="replace"` (remplace par `�`) ou `errors="ignore"`, en le journalisant.

### CSV

```python
import csv
with open(p, newline="", encoding="utf-8") as f:
    for ligne in csv.DictReader(f):          # itérateur PARESSEUX -> mémoire constante
        traiter(ligne["ip_src"])
```

Le CSV est un format **sans schéma, sans types, sans compression, non splittable proprement** (un
retour à la ligne peut vivre à l'intérieur d'un champ quoté). Tout y est une chaîne. Il reste le
format d'échange universel, mais ce n'est **pas** un format de stockage analytique.

À connaître : `csv.field_size_limit()` vaut **131072** octets par défaut — un champ plus gros lève
`_csv.Error: field larger than field limit`.

### JSON

```python
import json
json.loads(texte)                                   # str -> objet
json.dumps(obj, ensure_ascii=False, separators=(",", ":"))   # objet -> str compact et lisible
```

- `ensure_ascii=True` **par défaut** : les accents sortent en `é`. Mets `False` pour de l'UTF-8 lisible.
- `json.load(f)` charge **tout** en mémoire → interdit sur un gros fichier.
- Pour du volume : **JSON Lines / NDJSON** — un objet JSON par ligne, donc lisible en streaming,
  concaténable et splittable. C'est le format d'échange de flux le plus courant.
- `orjson` est ~2 à 5× plus rapide que le module standard et gère `datetime`/`UUID` nativement.

### Parquet — le format de stockage analytique

**Le problème** : ta requête ne lit que 3 colonnes sur 80, et ne veut que le jour J. En CSV, tu lis
100 % des octets. En Parquet, tu lis les 3 colonnes concernées, et seulement dans les blocs qui
contiennent J.

```
   FICHIER PARQUET
   ┌───────────────────────────────────────────────────────────┐
   │ PAR1                                    (nombre magique)  │
   ├───────────────────────────────────────────────────────────┤
   │ ROW GROUP 0   (~128 Mo, ou ~1 M lignes)                    │
   │   ├─ Column chunk : ip_src   ─▶ pages (dict, RLE, snappy)  │
   │   ├─ Column chunk : port     ─▶ pages                      │
   │   └─ Column chunk : octets   ─▶ pages                      │
   ├───────────────────────────────────────────────────────────┤
   │ ROW GROUP 1   …                                            │
   ├───────────────────────────────────────────────────────────┤
   │ FOOTER : schéma + pour CHAQUE colonne de CHAQUE row group  │
   │          min / max / nb de nuls / offsets                  │
   │ longueur du footer (4 o) + PAR1                            │
   └───────────────────────────────────────────────────────────┘
        ▲ le lecteur lit la FIN du fichier d'abord.
```

Quatre propriétés à savoir énoncer :

1. **Orienté colonnes** → *column pruning* : on ne lit que les colonnes demandées.
2. **Statistiques min/max dans le footer** → *predicate pushdown* : un row group dont le max est
   `2026-09-01` est **entièrement sauté** pour un filtre `date > 2026-09-05`.
3. **Compression et encodage par colonne** (dictionnaire, RLE, bit-packing puis snappy/zstd) : des
   valeurs de même type se compressent bien mieux qu'une ligne hétérogène. Compte **5 à 10× plus petit
   qu'un CSV équivalent**.
4. **Schéma typé embarqué** : plus de « le port est une chaîne ».

```python
import pyarrow.parquet as pq
table = pq.read_table(p, columns=["ip_src", "octets"],
                      filters=[("date", "=", "2026-09-09")])   # pruning + pushdown
pq.write_table(table, "out.parquet", compression="zstd")
```

> ⚠️ **PIÈGE** — Le **problème des petits fichiers**. Écrire un Parquet par minute donne 1440 fichiers
> par jour, chacun avec son footer : le coût de métadonnées et de listage écrase le gain. Vise des
> fichiers de **128 Mo à 1 Go**, et compacte périodiquement.

> 🧠 **MÉMO** — « **CSV = photocopie. Parquet = base de données figée.** » Le CSV se lit avec les yeux,
> le Parquet se lit avec un moteur.

> ❓ **RETIENS ÇA** — Grâce à quoi un moteur peut-il sauter un bloc entier d'un fichier Parquet ?
> <details><summary>→ réponse</summary><br>Grâce aux <b>statistiques min/max stockées dans le footer</b> pour chaque colonne de chaque <i>row group</i>. Si l'intervalle [min, max] ne peut pas satisfaire le filtre, le row group n'est même pas lu : c'est le <i>predicate pushdown</i>.</details>

---

## 13. Le GIL et le parallélisme

**La question** : tu lances 8 threads sur une machine à 8 cœurs pour parser du JSON, et c'est **plus
lent** qu'en séquentiel. Pourquoi ?

**Le GIL (Global Interpreter Lock)** est un verrou unique par processus : **un seul thread exécute du
bytecode Python à la fois**. Il existe parce que le comptage de références de CPython n'est pas atomique
— sans verrou global, il faudrait un verrou par objet, ce qui ralentirait le code mono-thread.

Trois faits, et tout en découle :

1. Un thread relâche le GIL toutes les **5 ms** par défaut (`sys.getswitchinterval()` → `0.005`).
2. Un thread relâche le GIL **pendant toute attente d'I/O** : lecture disque, `recv()` réseau, `sleep`.
3. Une extension C peut relâcher le GIL explicitement pendant un calcul : **NumPy, pandas, pyarrow,
   `hashlib`, la compression, le chiffrement** le font.

```
   CHARGE CPU PURE, 4 threads             CHARGE I/O, 4 threads
   (parsing, boucles Python)              (appels HTTP, requêtes SQL)

   T1 ████░░░░░░░░████░░░░               T1 ██░░░░attente░░░░██
   T2 ░░░░████░░░░░░░░████               T2 ░░██░░░░attente░░░░██
   T3 ░░░░░░░░████░░░░░░░░               T3 ░░░░██░░░░attente░░░░
   T4 ░░░░░░░░░░░░████░░░░               T4 ░░░░░░██░░░░attente░░
      └─ jamais 2 blocs en même temps       └─ les attentes se RECOUVRENT
      GAIN ≈ 0 (voire négatif)              GAIN ≈ nombre de connexions
```

### La table de décision

| Type de charge | Outil | Gain attendu |
|---|---|---|
| **I/O réseau/disque**, peu de connexions | `ThreadPoolExecutor` | ×N (N = parallélisme utile) |
| **I/O réseau**, des milliers de connexions | `asyncio` + `httpx`/`aiohttp` | ×1000 possible, 1 seul thread |
| **CPU pur en Python** (parsing, boucles) | `ProcessPoolExecutor` / `multiprocessing` | ×cœurs, moins le coût de sérialisation |
| **CPU dans NumPy/pandas/pyarrow** | vectorisation, puis threads | déjà parallèle, le GIL est relâché |
| **Volume > une machine** | Spark / Dask / Ray | horizontal |

```python
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor

with ThreadPoolExecutor(max_workers=16) as ex:       # défaut : min(32, os.cpu_count() + 4)
    for res in ex.map(interroger_equipement, hotes):
        ...

with ProcessPoolExecutor() as ex:                    # défaut : os.cpu_count()
    resultats = list(ex.map(parser_bloc, blocs))
```

> ⚠️ **PIÈGE** — Avec `ProcessPoolExecutor`, arguments et résultats transitent par **pickle**. Trois
> conséquences : les `lambda` et les fonctions locales ne passent pas (`PicklingError`) ; envoyer un
> DataFrame de 2 Go à 8 workers coûte plus cher que le calcul lui-même ; chaque worker démarre un
> **interpréteur complet** (dizaines à centaines de ms). On parallélise en processus des **tâches
> grosses et peu nombreuses**, en passant des **chemins de fichiers**, pas des données.

> ⚠️ **PIÈGE** — Le GIL protège l'interpréteur, **pas ta logique**. `compteur += 1` depuis plusieurs
> threads reste une course (lecture, addition, écriture = plusieurs bytecodes, interruptibles entre
> deux). Il te faut quand même un `threading.Lock`.

### Exercice corrigé — threads ou processus ?

**Énoncé.** Tu dois interroger 400 routeurs en gNMI. Chaque appel prend **200 ms d'attente réseau** et
**5 ms de parsing Python**. Machine à 8 cœurs. Séquentiel, threads (32), processus (8) ?

**Correction.**

- **Séquentiel** : 400 × (200 + 5) ms = 400 × 0,205 s = **82 s**.
- **Threads (32)** : les 200 ms d'attente se recouvrent (GIL relâché). Le parsing, lui, est
  sérialisé par le GIL : 400 × 5 ms = **2 s incompressibles**. L'attente devient
  400/32 × 200 ms = 2,5 s. Total ≈ **max/somme des deux ≈ 4,5 s**, soit **≈ ×18**.
- **Processus (8)** : 400/8 = 50 appels par worker, soit 50 × 205 ms = **10,25 s**, plus le coût de
  démarrage (8 × ~50 ms) et la sérialisation. Total ≈ **10,5 s** — **2× plus lent que les threads**,
  pour un code plus compliqué.

**Verdict : threads.** La charge est à **97,5 % de l'attente réseau**. Règle générale : *si le temps
est passé à attendre, ce sont des threads (ou asyncio) ; s'il est passé à calculer en Python pur,
ce sont des processus.*

> ❓ **RETIENS ÇA** — Le GIL empêche-t-il d'accélérer un programme avec des threads ?
> <details><summary>→ réponse</summary><br><b>Seulement pour le calcul en Python pur.</b> Le GIL est relâché pendant les I/O et par les extensions C (NumPy, pyarrow, hashlib, compression) : les threads accélèrent donc massivement les charges I/O et les charges numériques vectorisées.</details>

**À jour** : Python **3.13** introduit un build expérimental **« free-threaded »** (PEP 703, binaire
`python3.13t`) qui supprime le GIL, au prix d'un léger surcoût mono-thread. Ce n'est pas le build par
défaut ; les extensions C doivent être adaptées. Le mentionner en entretien montre que tu suis
l'écosystème — mais raisonne, aujourd'hui, avec le GIL présent.

---

## 14. Style et outillage : ce que la CI doit refuser

| Outil | Rôle | Commande | À savoir |
|---|---|---|---|
| **ruff** | linter **et** formateur, en Rust | `ruff check --fix .` / `ruff format .` | 10-100× plus rapide que flake8 ; réimplémente flake8, isort, pyupgrade, bugbear… |
| **black** | formateur historique | `black .` | **88 colonnes** par défaut ; « magic trailing comma » |
| **mypy** | typage statique | `mypy --strict src/` | doit casser le build |
| **pytest** | tests | `pytest -q --cov` | |
| **pre-commit** | lance tout avant chaque commit | `pre-commit install` | empêche le code non formaté d'entrer dans git |

`ruff format` est compatible avec le style black (même largeur de 88 par défaut). En pratique, une
équipe moderne remplace `flake8 + isort + black` par **ruff seul**.

Le formatage n'est pas cosmétique : **un formateur automatique supprime 100 % des discussions de style
en revue de code** et rend les diffs lisibles (un diff ne contient plus que du sens).

PEP 8 en quatre chiffres : **4 espaces** d'indentation, **79 colonnes** (norme historique ; en pratique
88 ou 100), `snake_case` pour fonctions/variables, `PascalCase` pour les classes, `MAJUSCULES` pour les
constantes, `_prefixe` pour le privé par convention.

> 🧠 **MÉMO** — L'ordre d'une CI Python : **format → lint → types → tests → build**. Du moins cher au
> plus cher, pour échouer le plus tôt possible.

---

## 15. Questions d'entretien

**1. Quelle est la différence entre une liste et un tuple, au-delà de la mutabilité ?**
Le tuple est immuable, donc **hachable** (utilisable comme clé de dict ou élément de set) tant que son
contenu l'est. Il est plus compact (40 octets à vide contre 56) et légèrement plus rapide à créer et à
parcourir. Sémantiquement, on utilise un tuple pour un **enregistrement hétérogène de taille fixe**
(une coordonnée, une clé composite) et une liste pour une **collection homogène de taille variable**.
En code typé : `tuple[str, int]` versus `list[str]`.

**2. Explique le piège de l'argument par défaut mutable.**
La valeur par défaut est évaluée **une seule fois, à la définition** de la fonction, et rangée dans
`__defaults__`. Une liste ou un dict par défaut est donc **partagé par tous les appels** et accumule
les mutations d'un appel à l'autre — un état global caché, y compris entre threads. Le correctif est
`def f(x=None)` puis `if x is None: x = []`. Même problème avec un `datetime.now()` par défaut, figé au
chargement du module, et avec les dataclasses, où il faut `field(default_factory=list)`.

**3. Générateur ou liste — comment choisis-tu ?**
Générateur par défaut dès qu'il s'agit d'un flux de données : la mémoire devient O(1) au lieu de O(n),
et le premier résultat sort immédiatement au lieu d'attendre la fin du traitement. Liste quand tu dois
parcourir **plusieurs fois**, connaître la **longueur**, **indexer**, ou trier. Le piège du générateur
est son **usage unique** : le consommer deux fois donne un résultat vide la seconde fois, sans aucune
erreur. Sur un fichier de 50 Go, la version liste fait tomber le processus sur OOM (code 137) ; la
version générateur tourne dans quelques centaines de Mo.

**4. Explique le GIL.**
C'est un verrou global par processus qui garantit qu'**un seul thread exécute du bytecode Python à la
fois**, nécessaire parce que le comptage de références de CPython n'est pas atomique. Il est relâché
toutes les 5 ms, pendant toute attente d'I/O, et par les extensions C comme NumPy ou pyarrow.
Conséquence : les threads accélèrent les charges **I/O** et les charges **numériques vectorisées**,
mais pas le calcul en Python pur, pour lequel il faut des **processus**. Python 3.13 propose un build
expérimental sans GIL (PEP 703), qui n'est pas encore le défaut.

**5. `dataclass` ou Pydantic ?**
`dataclass` est dans la stdlib, ne coûte presque rien et **ne valide rien** : c'est le bon choix pour
les objets **internes**, créés en grand nombre, surtout avec `slots=True`. Pydantic **valide et
convertit à l'exécution** en lisant les annotations : c'est le bon choix aux **frontières** — parsing
d'une configuration, d'un message Kafka, d'une réponse d'API. Règle : *Pydantic à la douane, dataclass
à l'intérieur*. Valider une seule fois, à l'entrée, puis circuler avec des objets de confiance.

**6. Comment rends-tu un appel réseau robuste dans un pipeline ?**
Un décorateur `retry` avec un nombre d'essais borné, un **backoff exponentiel** et du **jitter** pour
éviter le *thundering herd*, appliqué **uniquement aux exceptions transitoires** (timeout, connexion
réinitialisée, HTTP 429/5xx) — jamais à une erreur de parsing ou à un 4xx d'authentification. J'ajoute
un timeout explicite sur chaque appel (jamais de timeout infini), un log en WARNING par tentative et un
ERROR à l'échec définitive, et une métrique de taux d'échec. Au-delà, un *circuit breaker* si la
dépendance tombe durablement.

**7. Pourquoi `print` est-il interdit en production ?**
Parce qu'il n'a ni niveau, ni horodatage, ni origine (module), ni destination configurable, ni moyen
d'être filtré ou désactivé sans modifier le code. `logging` donne une hiérarchie de loggers
(`getLogger(__name__)`), cinq niveaux, des handlers routables (stdout, fichier, syslog, agrégateur), un
formatage **différé** avec `%s` et l'inclusion automatique du traceback via `logger.exception`. En
conteneur, on émet du JSON structuré sur stdout et c'est le collecteur qui route.

**8. Comment testes-tu une fonction qui appelle une API externe ?**
Je ne l'appelle pas : je **mocke** la frontière avec `unittest.mock.patch`, en patchant **là où le nom
est utilisé** dans mon module, pas là où il est défini. Je paramètre les cas avec
`@pytest.mark.parametrize` (200, 429, 503, JSON malformé, timeout) et je vérifie le comportement
attendu — nombre de retries, exception levée, valeur de repli. Les fixtures `tmp_path` et `monkeypatch`
isolent le système de fichiers et l'environnement. En complément, un test d'intégration réel, marqué
`@pytest.mark.integration`, exclu de la CI rapide.

**9. Comment structures-tu un projet Python livrable ?**
Layout `src/` (pour que les tests importent le paquet **installé** et pas les fichiers locaux),
`pyproject.toml` unique pour l'identité, les dépendances et la configuration des outils, un
environnement virtuel par projet, un **fichier de verrouillage commité** (`uv.lock` / `poetry.lock`)
pour la reproductibilité, un dossier `tests/` avec `conftest.py`, et une CI qui enchaîne
`ruff format --check`, `ruff check`, `mypy --strict`, `pytest`. Le point d'entrée est déclaré en
`[project.scripts]` plutôt qu'en script libre.

**10. Copie superficielle ou profonde : quelle différence, et laquelle utiliser ?**
`list(x)`, `x[:]`, `x.copy()` et `copy.copy(x)` font une copie **superficielle** : le conteneur externe
est neuf, mais les objets contenus sont **partagés** — muter un sous-élément se voit des deux côtés.
`copy.deepcopy(x)` recrée récursivement tout le graphe (en gérant les cycles), pour un coût 10 à 100×
supérieur. En pipeline, on évite `deepcopy` dans une boucle : on construit un nouvel objet, ou on
travaille avec des structures **immuables** (`tuple`, `frozen=True`) qui rendent la question sans objet.

**11. Ton job consomme 12 Go de RAM et se fait tuer. Ta démarche ?**
D'abord confirmer : code de sortie **137** = SIGKILL, typiquement l'OOM killer (`dmesg`). Ensuite
chercher la **matérialisation** : un `readlines()`, un `list(...)`, un `pd.read_csv` complet, un
`.collect()`. Les remplacer par un pipeline de générateurs ou une lecture par lots
(`chunksize`, `itertools.batched`, row groups Parquet). Vérifier les caches non bornés
(`lru_cache(maxsize=None)` sur des clés uniques). Mesurer avec `tracemalloc` ou `memory_profiler`
plutôt que deviner. Et changer le format d'entrée si possible : Parquet en colonnes avec projection
des seules colonnes utiles.

---

## Les 3 choses à retenir si tu ne retiens que ça

1. **Une variable est une étiquette, pas une boîte.** Tout ce qui est mutable est partagé dès qu'il est
   affecté, passé en argument ou mis en valeur par défaut. Le piège de l'argument par défaut mutable
   (`def f(x=[])`) et la copie superficielle découlent tous les deux de ce seul fait.

2. **Par défaut, sois paresseux.** Générateurs, `yield`, `itertools`, lecture par lots, Parquet en
   colonnes : on ne matérialise jamais ce qu'on peut faire circuler. C'est la différence entre un
   script de notebook et un pipeline qui tient en production — mémoire O(1) au lieu de O(n).

3. **Le code de production, c'est ce qu'il y a autour du code.** Typage vérifié par `mypy`, validation
   des entrées par Pydantic, exceptions précises avec `raise ... from`, ressources sous `with`,
   `logging` hiérarchique au lieu de `print`, tests `pytest` paramétrés, `pyproject.toml` avec fichier
   de verrouillage. Une fonction juste sans cet entourage n'est pas livrable.
