# L01 — FICHE : Python pour data engineering

> Lire **avant** le cours (pretesting), puis réciter de mémoire aux rappels. Cible : **3 minutes**.
> Une variable est une **étiquette**, pas une boîte. Par défaut on est **paresseux**. Le code de prod,
> c'est ce qu'il y a **autour** du code.

## Modèle objet
`b = a` → deux étiquettes, **un objet**. `is` = même objet · `==` = même valeur.
`is` **uniquement** pour `None`/`True`/`False` (petits ints **-5 à 256** mis en cache → faux positifs).
Libération par **comptage de références** + GC générationnel (seuils **700, 10, 10**) pour les cycles.

**Immuables** `int float bool str bytes tuple frozenset None` → **hachables** → clés de dict/set.
**Mutables** `list dict set bytearray` → `TypeError: unhashable`.

**Copies** : `list(x)` = `x[:]` = `x.copy()` = `copy.copy` → **superficielle** (contenu partagé).
Seul `copy.deepcopy` descend (10-100× plus cher).

**Piège n°1** : `def f(x=[])` → défaut évalué **une fois au `def`**, partagé par tous les appels.
→ `def f(x=None): if x is None: x=[]` · en dataclass : `field(default_factory=list)`.

## Complexités
| Op | list | deque | dict | set | tuple |
|---|---|---|---|---|---|
| `x[i]` | **O(1)** | O(n) | — | — | **O(1)** |
| `in` | **O(n)** | O(n) | **O(1)** | **O(1)** | O(n) |
| ajout fin | O(1) amorti | O(1) | O(1) | O(1) | — |
| ajout/retrait **tête** | **O(n)** | **O(1)** | — | — | — |

Vides (64 bits) : `()` 40 · `[]` 56 · `{}` 64 · `set()` 216 o. `int` ≈ **28 o** vs `int64` **8 o**.
Liste : sur-alloue ~**12 %** · dict : redimensionne aux **2/3** · ordre d'insertion garanti **3.7+**.
`sorted`/`.sort` = **Timsort**, O(n log n), **stable**, O(n) si déjà trié.
**1 Go de CSV ≈ 5-10 Go d'objets Python.**

## Itération / générateurs
`for` = `it = iter(obj)` puis `next(it)` jusqu'à **`StopIteration`**.
Itérable = `__iter__` · Itérateur = `__iter__` + `__next__`, **à usage unique**.
Fichier et générateur = **leur propre itérateur** → 2e parcours = vide, **sans erreur**.
`[...]` construit · **`(...)` promet** · appeler une fonction à `yield` n'exécute **rien**.
`islice · chain.from_iterable · groupby (CONSÉCUTIFS → trier d'abord) · batched (3.12) · zip(strict=True)`

## Fonctions
`def f(a, b, /, c, *args, d, **kw)` — avant `/` positionnel seul, après `*` **nommé obligatoire**.
Closure capture la **variable** pas la valeur (`[lambda: i for i in range(3)]` → `[2,2,2]`).
LEGB : Local → Englobant → Global → Builtins.
`@deco` ≡ `f = deco(f)` · **toujours `@functools.wraps(func)`** (sinon `__name__` = `wrapper`).
`lru_cache(maxsize=128)` (défaut) · `functools.cache` = `maxsize=None` · args **hachables** seulement.
**retry** = essais bornés + backoff exponentiel + **jitter**, sur exceptions **transitoires** uniquement.

## Typage
Annotations **jamais vérifiées à l'exécution** (`__annotations__`) → mypy/pyright en CI.
`list[int]` (3.9) · `int | None` (3.10). `mypy --strict src/` doit casser le build.
`@dataclass(frozen=True, slots=True)` → hachable + ~30-40 % de RAM en moins. `frozen` **≠** profond.
**Pydantic v2 = validation à l'exécution** (`model_validate`, `ValidationError`, `model_dump`).
→ **Pydantic à la douane, dataclass à l'intérieur.**

## Exceptions
`BaseException` > `SystemExit`, `KeyboardInterrupt`, `GeneratorExit` **et** `Exception`.
→ `except Exception:` jamais `except:` nu. Jamais `except: pass`. `raise Neuve(...) **from** exc`.
`else` = si **aucune** exception · `finally` = **toujours** (jamais de `return` dedans).
Stratégies : fail fast · skip + **dead letter** · retry · circuit breaker. **Toujours compter les rejets.**

## Context managers
`with E as v` ≡ `v = E.__enter__()` / `try: corps / finally: E.__exit__(t,v,tb)`.
`__exit__` renvoyant **vrai supprime l'exception**. `@contextmanager` : avant `yield` = enter, après = exit.
Écriture **atomique** : écrire `.tmp` puis `os.replace()`.

## Projet
Import : `sys.modules` → intégrés → `sys.path` (script, PYTHONPATH, site-packages) → `ModuleNotFoundError`.
Un module n'est **exécuté qu'une fois**. `__name__ == "__main__"` si **lancé**, sinon nom du module.
Layout **`src/`** → les tests importent le paquet **installé**. `pyproject.toml` = identité + deps + outils.
`.venv` = interpréteur + site-packages dédiés. `uv` / `poetry`. **Le lock se commite** (reproductibilité).

## Tests
`pytest` réécrit les `assert`. `@pytest.mark.parametrize` = **1 test par cas**. `pytest.raises(..., match=)`.
Fixtures dans `conftest.py` ; scopes **function** (défaut) · class · module · package · session.
Intégrées : `tmp_path` `monkeypatch` `capsys` `caplog`. Options `-x -k --lf -q --durations=10 --cov`.
**Mock : on patche là où le nom est UTILISÉ, pas où il est défini.**

## Logging
`NOTSET 0 · DEBUG 10 · INFO 20 · WARNING 30 (défaut racine) · ERROR 40 · CRITICAL 50`
`logger = logging.getLogger(__name__)` en haut de **chaque** module. `logger.exception` = ERROR + trace.
**`logger.info("v=%s", v)`** — formatage **différé** ; jamais de f-string.
**Deux filtrages** : niveau du **logger** puis niveau du **handler**. `basicConfig` no-op si handler existant.

## Fichiers
`open()` : mode `"r"` texte, tampon **8192 o**, encodage = **locale** → **toujours `encoding="utf-8"`**.
Module `csv` → `newline=""` obligatoire ; `field_size_limit` = **131072**.
JSON : `ensure_ascii=True` par défaut ; gros volume → **NDJSON** (1 objet/ligne).
**Parquet** : colonnes, **row groups** (~128 Mo / ~1 M lignes), footer avec **min/max** → *predicate
pushdown* + *column pruning*, magie `PAR1`, **5-10× plus petit qu'un CSV**. Éviter les petits fichiers.

## GIL
**Un seul thread exécute du bytecode Python à la fois** (refcount non atomique).
Relâché : toutes les **5 ms** (`getswitchinterval` = 0.005), pendant les **I/O**, par les **extensions C**.
I/O → threads (`ThreadPoolExecutor`, défaut `min(32, cpu+4)`) ou asyncio · CPU Python → **processus**
(`ProcessPoolExecutor`, défaut `os.cpu_count()`, args via **pickle**) · NumPy/pyarrow → déjà libéré.
GIL ≠ atomicité métier : `compteur += 1` reste une course → `Lock`. 3.13 : build *free-threaded* (PEP 703).

## Outillage
`ruff check --fix` + `ruff format` (Rust, remplace flake8+isort+black) · `black` **88 colonnes** ·
`mypy --strict` · `pytest` · `pre-commit`. CI : **format → lint → types → tests → build**.

---

## Test express (réponses dans le cours)
1. Pourquoi `def f(x=[])` accumule-t-il les valeurs d'un appel à l'autre ?
2. `list(x)`, `x[:]`, `x.copy()` : quelle profondeur de copie ?
3. Complexité de `x in liste` vs `x in set`, et pourquoi ?
4. Que renvoie l'appel d'une fonction contenant `yield`, et combien de lignes ont été exécutées ?
5. Que fait `@functools.wraps` et que se passe-t-il si tu l'oublies ?
6. Une annotation de type est-elle vérifiée à l'exécution ? Par qui alors ?
7. Différence entre le bloc `else` et le bloc `finally` d'un `try` ?
8. Pourquoi 8 threads sur 8 cœurs n'accélèrent-ils pas un parsing JSON en Python pur ?
