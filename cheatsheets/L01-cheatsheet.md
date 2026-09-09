# L01 — CHEATSHEET : Python pour data engineering

Référence opérationnelle. À garder ouverte pendant qu'on code.

---

## 1. Les chiffres à ne jamais chercher

| Grandeur | Valeur |
|---|---|
| Cache des petits entiers (CPython) | **-5 à 256** |
| Taille d'un `int` Python | **≈ 28 octets** (vs **8** pour un `int64` NumPy) |
| `sys.getsizeof` à vide | `()` **40** · `[]` **56** · `{}` **64** · `set()` **216** · `""` **49** |
| Sur-allocation d'une `list` | **≈ 12 %** à chaque réallocation |
| Redimensionnement d'un `dict` | quand rempli aux **2/3** |
| Ordre d'insertion `dict` garanti | **Python 3.7** (implémentation dès 3.6) |
| Seuils du GC générationnel | **700, 10, 10** |
| Limite de récursion | **1000** (`sys.setrecursionlimit`) |
| Intervalle de bascule du GIL | **5 ms** (`sys.getswitchinterval()` → `0.005`) |
| `ThreadPoolExecutor` max_workers défaut | **`min(32, os.cpu_count() + 4)`** |
| `ProcessPoolExecutor` max_workers défaut | **`os.cpu_count()`** |
| `lru_cache` maxsize défaut | **128** (`functools.cache` = `None` = illimité) |
| Tampon d'`open()` | **8192 octets** (`io.DEFAULT_BUFFER_SIZE`) |
| `csv.field_size_limit()` | **131072** octets |
| Longueur de ligne `black` / `ruff format` | **88** colonnes (PEP 8 : 79) |
| Indentation PEP 8 | **4 espaces** |
| Row group Parquet visé | **128 Mo – 1 Go** (~1 M lignes par défaut avec pyarrow) |
| Ratio de taille Parquet vs CSV | **5 à 10× plus petit** |
| Coût mémoire d'un CSV chargé en objets Python | **×5 à ×10** |

## 2. Complexités

| Opération | `list` | `deque` | `dict` | `set` | `tuple` | `str` |
|---|---|---|---|---|---|---|
| indexation `x[i]` | O(1) | O(n) | — | — | O(1) | O(1) |
| accès par clé | — | — | O(1)* | — | — | — |
| `in` | **O(n)** | O(n) | **O(1)*** | **O(1)*** | O(n) | O(n·m) |
| `append` / `add` | O(1) amorti | O(1) | O(1)* | O(1)* | — | immuable |
| `insert(0)` / `pop(0)` | **O(n)** | **O(1)** | — | — | — | — |
| `del`/`remove` par valeur | O(n) | O(n) | O(1)* | O(1)* | — | — |
| `len` | O(1) | O(1) | O(1) | O(1) | O(1) | O(1) |
| tri | O(n log n) | — | — | — | O(n log n) | — |
| copie superficielle | O(n) | O(n) | O(n) | O(n) | O(1) | O(1) |

\* moyen ; pire cas théorique O(n). — `a += b` sur des `str` en boucle : **quadratique** → `"".join(liste)`.

## 3. Structures : la bonne pour le besoin

| Besoin | Choix |
|---|---|
| Appartenance, déduplication | `set` (`&` inter · `\|` union · `-` diff · `^` sym.) |
| File / fenêtre glissante | `deque(maxlen=N)` — `appendleft` `popleft` O(1) |
| Comptage | `Counter(iterable).most_common(10)` |
| Regroupement | `defaultdict(list)` |
| Recherche dans liste triée | `bisect.bisect_left / insort` — O(log n) |
| File de priorité | `heapq.heappush/heappop`, `nlargest(k)` |
| Enregistrement typé, léger | `@dataclass(slots=True)` ou `NamedTuple` |
| Tableau numérique | `numpy.ndarray` (contigu, GIL relâché) |

## 4. Itérateurs et `itertools`

| Appel | Effet |
|---|---|
| `iter(x)` / `next(it, defaut)` | protocole brut ; `defaut` évite `StopIteration` |
| `enumerate(x, start=1)` | `(i, v)` |
| `zip(a, b, strict=True)` | apparie ; `strict` (3.10+) lève si longueurs ≠ |
| `itertools.islice(it, debut, fin)` | slice **paresseux** (un générateur ne se slice pas) |
| `itertools.chain(a, b)` / `.from_iterable(x)` | concatène / aplatit |
| `itertools.groupby(it, key)` | groupe les **consécutifs** → trier d'abord ! |
| `itertools.batched(it, n)` (3.12+) | paquets de n |
| `itertools.tee(it, 2)` | duplique (met en tampon l'avance) |
| `itertools.count/cycle/repeat` | infinis — toujours avec `islice` |
| `sum(1 for _ in gen)` | compter sans matérialiser |

## 5. `functools` et décorateurs

```python
@functools.wraps(func)                 # OBLIGATOIRE dans tout wrapper
@functools.lru_cache(maxsize=128)      # args hachables ; .cache_info() .cache_clear()
@functools.cache                       # = lru_cache(maxsize=None)  (3.9+)
@functools.cached_property             # cache par instance, libérable
functools.partial(f, a=1)              # fige des arguments
functools.reduce(op, it, initial)
```

## 6. Typage

| Écrire | Ne plus écrire | Depuis |
|---|---|---|
| `list[int]`, `dict[str, int]` | `List`, `Dict` | 3.9 |
| `int \| None` | `Optional[int]` | 3.10 |
| `Iterable`/`Sequence`/`Mapping` en **entrée** | types concrets | `collections.abc` |
| `Literal["csv","parquet"]`, `TypedDict`, `Protocol`, `Final` | | |

```bash
mypy --strict src/        # disallow_untyped_defs + warn_return_any + no_implicit_optional
```

```python
@dataclass(frozen=True, slots=True, order=False, kw_only=False)
champ: list[str] = field(default_factory=list)      # JAMAIS = []
def __post_init__(self) -> None: ...                # validation
```

| Pydantic v2 | Rôle |
|---|---|
| `Model.model_validate(dict)` | valide + convertit (lève `ValidationError`) |
| `Model.model_validate_json(txt)` | idem depuis du JSON |
| `m.model_dump()` / `m.model_dump_json()` | sérialise |
| `Field(default=161, ge=1, le=65535)` | contraintes |
| `@field_validator("x")` / `@model_validator(mode="after")` | validation sur mesure |

## 7. Exceptions

```
BaseException ├ SystemExit ├ KeyboardInterrupt ├ GeneratorExit └ Exception
Exception ├ LookupError(KeyError, IndexError) ├ OSError(FileNotFoundError, PermissionError,
          │   TimeoutError, ConnectionError…) ├ ValueError(UnicodeDecodeError) ├ TypeError
```

| Forme | Sens |
|---|---|
| `except Exception:` | le minimum acceptable (jamais `except:` nu) |
| `raise Neuve(msg) from exc` | chaîne la cause (`__cause__`) |
| `raise ... from None` | masque volontairement la cause |
| `else:` | si **aucune** exception |
| `finally:` | **toujours** — jamais de `return` dedans |
| `contextlib.suppress(FileNotFoundError)` | `try/except/pass` lisible |
| `except*` + `ExceptionGroup` | 3.11+, tâches concurrentes |

## 8. Projet et packaging

```
mon-pipeline/  pyproject.toml  README.md  src/mon_pipeline/{__init__,__main__,cli}.py  tests/conftest.py
```

| Commande | Effet |
|---|---|
| `python -m venv .venv && source .venv/bin/activate` | environnement virtuel standard |
| `pip install -e ".[dev]"` | installation **éditable** + extras dev |
| `pip freeze > requirements.txt` | figer (dépannage ; préférer un lock) |
| `uv init` · `uv add X` · `uv sync` · `uv run pytest` · `uv lock` · `uv venv` | gestion complète (Rust) |
| `poetry add X` · `poetry install` · `poetry lock` · `poetry build` | équivalent |
| `python -m mon_pipeline` | exécute `__main__.py` |

Sections `pyproject.toml` : `[build-system]` · `[project]` (name, version, requires-python,
dependencies) · `[project.optional-dependencies]` · `[project.scripts]` · `[tool.ruff]` ·
`[tool.mypy]` · `[tool.pytest.ini_options]`.

## 9. pytest

| Option | Effet |
|---|---|
| `-x` / `--maxfail=N` | arrêt au premier / au N-ième échec |
| `-k "ip and not lent"` | filtre par nom |
| `-m lent` | filtre par marqueur (`@pytest.mark.lent`) |
| `--lf` / `--ff` | rejouer / prioriser les derniers échecs |
| `-q` / `-v` / `-s` | silencieux / verbeux / ne pas capturer stdout |
| `--durations=10` | les 10 tests les plus lents |
| `--cov=pkg --cov-report=term-missing` | couverture |
| `-n auto` | parallèle (pytest-xdist) |

```python
@pytest.fixture(scope="session")      # function (défaut) | class | module | package | session
@pytest.mark.parametrize(("a","b"), [(1,2), (3,4)])
with pytest.raises(ValueError, match="regex"): ...
pytest.approx(0.3)                    # comparaison de flottants
```
Fixtures intégrées : `tmp_path` `tmp_path_factory` `monkeypatch` `capsys` `caplog` `request`.
Mock : `@patch("pkg.module_qui_utilise.nom")` — **là où c'est utilisé**. `mock.assert_called_once_with(...)`,
`mock.call_count`, `side_effect=[a, b, Exception()]`, `return_value=...`.

## 10. Logging

| Niveau | Valeur |
|---|---|
| `NOTSET` | 0 |
| `DEBUG` | 10 |
| `INFO` | 20 |
| `WARNING` | **30 — défaut de la racine** |
| `ERROR` | 40 |
| `CRITICAL` | 50 |

```python
logger = logging.getLogger(__name__)          # dans CHAQUE module
logger.info("etape=%s lignes=%d", nom, n)     # formatage différé (jamais de f-string)
logger.exception("échec ligne %d", i)         # = ERROR + traceback
logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
                    force=True)               # force=True : reconfigure malgré un handler existant
```
Attributs de format : `%(asctime)s %(levelname)s %(name)s %(message)s %(filename)s %(lineno)d
%(funcName)s %(process)d %(threadName)s`. Handlers : `StreamHandler`, `FileHandler`,
`RotatingFileHandler(maxBytes, backupCount)`, `TimedRotatingFileHandler`, `SysLogHandler`,
`QueueHandler`. Config déclarative : `logging.config.dictConfig({...})`.

## 11. Fichiers et formats

```python
open(p, mode="r", buffering=-1, encoding="utf-8", errors="strict", newline=None)
```
Modes : `r` `w` (**tronque**) `a` `x` (échoue si existe) `b` binaire `+` lecture/écriture.
`errors=` : `strict` (défaut) · `replace` (→ `�`) · `ignore` · `surrogateescape`.

| Tâche | Code |
|---|---|
| Chemins | `Path("/a") / "b.csv"` · `.exists() .stat().st_size .suffix .stem .parent .glob("*.parquet")` |
| CSV lecture | `csv.DictReader(open(p, newline="", encoding="utf-8"))` |
| CSV écriture | `csv.DictWriter(f, fieldnames=…)` + `.writeheader()` |
| JSON | `json.loads/dumps(obj, ensure_ascii=False, separators=(",",":"), default=str)` |
| NDJSON | une ligne = un objet JSON → streaming |
| Parquet lecture | `pq.read_table(p, columns=[...], filters=[("d","=",v)])` |
| Parquet écriture | `pq.write_table(t, p, compression="zstd", row_group_size=…)` |
| Écriture atomique | écrire `p.tmp` puis `os.replace(p.tmp, p)` |
| Compression | `gzip.open` · `zstandard` · `snappy` (défaut pyarrow) |

Parquet : `PAR1` en tête et en queue · row group → column chunk → pages · footer = schéma +
**min/max/nulls** par colonne et par row group → *predicate pushdown* + *column pruning*.

## 12. Concurrence

| Situation | Outil |
|---|---|
| I/O, dizaines de tâches | `ThreadPoolExecutor(max_workers=N)` + `ex.map` / `submit` + `as_completed` |
| I/O, milliers de connexions | `asyncio` + `httpx`/`aiohttp`, `asyncio.gather`, `TaskGroup` (3.11), `Semaphore` |
| Bloquant dans de l'async | `await asyncio.to_thread(f, *args)` (3.9+) |
| CPU en Python pur | `ProcessPoolExecutor()` — args **picklables**, pas de `lambda` |
| CPU numérique | NumPy/pyarrow (GIL relâché) puis threads |
| Hors machine | Spark / Dask / Ray |

`multiprocessing` start methods : `fork` (rapide, dangereux si multithread), `forkserver`, `spawn`.
Synchronisation : `threading.Lock`, `RLock`, `Semaphore`, `Event`, `queue.Queue`.

## 13. Outillage et CI

| Commande | Effet |
|---|---|
| `ruff check --fix .` | lint + corrections automatiques |
| `ruff format .` / `--check` | formatage / vérification sans écrire |
| `black .` / `--check --diff` | formatage historique (88 colonnes) |
| `mypy --strict src/` | typage statique |
| `pytest -q --cov=src` | tests + couverture |
| `pre-commit install` / `run --all-files` | hooks git |
| `python -X importtime -m pkg` | coût des imports |
| `python -m cProfile -s cumtime script.py` | profilage CPU |
| `tracemalloc` / `memory_profiler` | profilage mémoire |
| `timeit.timeit("expr", number=100000)` | micro-benchmark |

Ordre de CI : **`ruff format --check` → `ruff check` → `mypy` → `pytest` → build**.

Règles ruff utiles dans `select` : `E`/`W` (pycodestyle) · `F` (pyflakes) · `I` (isort) ·
`UP` (pyupgrade) · `B` (bugbear — attrape `def f(x=[])`) · `SIM` · `ANN` · `PTH` · `RUF`.
