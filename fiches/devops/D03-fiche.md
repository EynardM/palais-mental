# D03 — FICHE : Bash & scripting robuste

> Lire **avant** le cours (pretesting), puis réciter de mémoire aux rappels. Cible : **3 minutes**.
> Le shell **transforme** ta ligne avant de l'exécuter. Tout bug bash vient de l'ordre de ces transformations.

## Ordre d'expansion (9 étapes, à réciter)
```
1 accolades {a,b}  2 tilde ~  3 paramètres $v  4 arithmétique $(( ))  5 subst. commande $( )
6 subst. processus <( )   ->   7 DÉCOUPAGE (IFS)   8 GLOBBING *   9 suppression des quotes
```
**Découpage (7) et globbing (8) arrivent APRÈS le remplacement des variables (3).**
→ Règle unique : **ce qui sort d'un `$` va entre `"`**.

## Quoting
| Forme | Interprète encore |
|---|---|
| `'…'` | **rien** |
| `"…"` | `$var`, `$( )`, `$(( ))`, `\` — **99 % des cas** |
| `$'…'` | `\n` `\t` `\x41` — seule façon d'écrire une tabulation |

`"$@"` = **N mots**, un par argument · `"$*"` = **1 mot**, joint par le **1er char d'IFS**.

## En-tête obligatoire
```bash
#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
```
`-e` sortie à la 1re erreur · `-u` variable non définie = erreur · `-o pipefail` pipeline = 1er échec ·
`-E` trap ERR hérité par les fonctions. **IFS défaut = espace, tabulation, saut de ligne.**

**Les 6 angles morts de `set -e`** : condition de `if`/`while` · opérande de `&&`/`||` · après `!` ·
maillon non final d'un pipe · dans `$( )` (sauf `inherit_errexit`) · `local x=$(cmd)` (code de `local` = 0).
Bonus mortel : **`((i++))` rend 1 quand `i` vaut 0** → utiliser `i=$((i+1))`.

## Expansions de paramètres
| | | | |
|---|---|---|---|
| `${#v}` longueur | `${v:-d}` défaut | `${v:=d}` défaut + affecte | `${v:?msg}` **erreur si vide** |
| `${v#p}` coupe court gauche | `${v##p}` **= basename** | `${v%p}` coupe court droite | `${v%%p}` long droite |
| `${v/a/b}` 1re occ. | `${v//a/b}` toutes | `${v^^}` MAJ | `${v,,}` min |
`#` coupe à **gauche**, `%` à **droite** ; **doubler = manger plus**.

## Tests
`[ ]` = commande (découpage, globbing) · **`[[ ]]` = mot-clé bash → à utiliser partout**.
`-f` fichier · **`-s` existe ET non vide** · `-d` répertoire · `-z`/`-n` chaîne vide/non vide ·
`-nt` plus récent · entiers `-eq -ne -lt -le -gt -ge` ou `(( ))`.
**`[[ 9 > 10 ]]` est VRAI** (chaînes) ; `(( 9 > 10 ))` est faux.

## Codes de sortie
| 0 | 1 | 2 | 124 | 126 | 127 | 130 | 137 | 141 | 143 |
|---|---|---|---|---|---|---|---|---|---|
| OK | erreur | usage | **timeout** | non exécutable | **introuvable** | Ctrl-C | **SIGKILL/OOM** | SIGPIPE | SIGTERM |

**128 + N = tué par le signal N.** `grep` : 0 trouvé · **1 rien trouvé** · 2 erreur.

## trap & verrou
```bash
trap cleanup EXIT INT TERM        # cleanup(){ local rc=$?; trap - EXIT INT TERM; …; exit "$rc"; }
trap 'log ERROR "ligne $LINENO : $BASH_COMMAND"' ERR      # exige set -E
exec 9>/var/lock/x.lock; flock -n 9 || exit 75            # verrou porté par le FD
```
**SIGKILL (9) et SIGSTOP (19) ne se trappent pas.** `flock` : libéré par le noyau à la mort du process
→ **zéro verrou fantôme** (contrairement au fichier PID).

## Redirections
`> f 2>&1` ✅ · **`2>&1 > f` ❌** (photo de la destination, prise avant le déplacement) · `&> f` ·
`1>&2` logs sur stderr · `<<EOF` interprète · **`<<'EOF'` littéral** · `<<-` retire les **tabulations** ·
`<<<` here-string · `<(cmd)` → `/dev/fd/63` (bash only, pas dash).

## Pipeline texte
| Outil | Rôle | À retenir |
|---|---|---|
| `grep` | filtrer des **lignes** | `-o -q -v -c -F -E -r --include` |
| `sed` | éditer un **flux** | `s///g`, `-n '2,5p'`, `1d`, `-i.bak`, `5q` |
| `awk` | calculer par **champs** | `$1..$NF`, `NF`, `NR`, `FNR`, `BEGIN`/`END`, tableaux |
| `sort` | ranger | `-t, -k3,3nr` · **`-k3` seul = jusqu'à la fin de ligne** · `LC_ALL=C` |
| `uniq` | dédoublonner | **exige un tri préalable** · `-c -d -u` |
| `cut` `tr` | colonnes / caractères | `cut` ne réordonne pas · `tr -d '\r'` (CSV Windows) |
| `jq` | JSON | **`-r`** raw · `select()` · `@tsv` · `-c` NDJSON · `//` défaut |
| `find` | trouver | `-mmin -60`, `-mtime +7`, `-size +1G`, `-print0`, `-exec … +` |
| `xargs` | liste → arguments | **`-0 -r`** · `-P N` parallèle · `-n K` |

`awk 'NR==FNR{ref[$1]=$2; next} $1 in ref {…}' a b` = **jointure** (1er fichier en mémoire).
`ARG_MAX ≈ 2 Mio` (`getconf ARG_MAX`) → « Argument list too long » → `find -print0 | xargs -0`.

## Idempotence (le cœur du métier)
1. **Écriture atomique** : staging **sur le même FS** puis `mv` (`rename()` atomique).
2. **Marqueur `_SUCCESS`** testé en tête → relance = sortie 0 immédiate.
3. `mkdir -p`, `rsync`, `ON CONFLICT DO NOTHING`.
4. Validation `${VAR:?}` / `[[ -s ]]`, journal **UTC ISO 8601 sur stderr**, retry avec **backoff ×2**.
> Le risque du bash n'est pas le plantage, c'est la **réussite partielle**.

## Pièges qui reviennent
`for f in $(ls)` ❌ → `for f in *.csv` · glob sans match = **motif littéral** → `shopt -s nullglob` ·
`cmd | while read` perd les variables (**sous-shell**) → `done < <(cmd)` · `cat f | while` idem ·
`cut`/`awk -F,` **ne parsent pas le CSV quoté** · `pipefail` + `head` → **141** (SIGPIPE).

## shellcheck
**SC2086** variable non quotée (le n°1) · SC2046 `$( )` non quotée · SC2155 `local x=$(…)` ·
SC2164 `cd` sans `|| exit` · SC2115 `rm -rf "$d/"` → `"${d:?}"` · SC2045 itérer sur `ls`.

## Bash → Python quand…
CSV quoté / JSON profond · flottants · dates & fuseaux · API paginée · **> 150 lignes** · besoin de tests.
> **Bash colle les processus, Python transforme les données.**

---

## Test express (réponses dans le cours)
1. Cite les 9 étapes d'expansion dans l'ordre.
2. Pourquoi `local v=$(cmd)` masque-t-il l'échec de `cmd` ?
3. Que vaut le code de `cmd_qui_echoue | tee log` sans `pipefail` ?
4. Quelle est la valeur par défaut d'`IFS` ?
5. Quels signaux `trap` ne peut-il pas attraper, et quelle conséquence pratique ?
6. Un conteneur sort en 137 : diagnostic ? Et en 124 ? En 127 ?
7. Pourquoi `mv` depuis un staging plutôt qu'écrire directement le fichier cible ?
8. Que fait `NR==FNR` dans un `awk` à deux fichiers ?
