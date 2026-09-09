# D03 — CHEATSHEET : Bash & scripting robuste

Référence opérationnelle. À garder ouverte pendant qu'on travaille.

---

## 1. Les nombres et valeurs à ne jamais chercher

| Grandeur | Valeur |
|---|---|
| `IFS` par défaut | **espace, tabulation, saut de ligne** (`$' \t\n'`) |
| `ARG_MAX` (Linux) | **≈ 2 097 152 octets** (`getconf ARG_MAX`) |
| Tampon d'un tube | **64 Kio** |
| Écriture atomique concurrente en ajout | jusqu'à **`PIPE_BUF` = 4096 octets** |
| Plage d'un code de sortie | **0-255** (tronqué modulo 256) |
| `$RANDOM` | **0 à 32767** |
| Arithmétique `$(( ))` | **entiers signés 64 bits**, pas de flottants |
| Bash associatifs `declare -A` | bash **≥ 4.0** |
| `wait -n`, `local -n` | bash **≥ 4.3** |
| `inherit_errexit`, `mapfile -d` | bash **≥ 4.4** |
| macOS livré avec | bash **3.2** (d'où `#!/usr/bin/env bash`) |
| `sh` sur Debian/Ubuntu | **dash** (pas de `[[ ]]`, pas de `<( )`, pas de tableaux) |

## 2. Codes de sortie

| Code | Sens | Code | Sens |
|---|---|---|---|
| **0** | succès | **128+N** | tué par le signal N |
| 1 | erreur générique | **130** | 128+2 SIGINT (Ctrl-C) |
| 2 | erreur d'usage (convention) | **137** | 128+9 SIGKILL → **OOM killer** |
| **124** | `timeout` a expiré | **141** | 128+13 SIGPIPE |
| **126** | trouvé mais non exécutable | **143** | 128+15 SIGTERM (arrêt demandé) |
| **127** | **commande introuvable** (PATH) | 75 | `EX_TEMPFAIL` : réessayer plus tard |

Codes d'outils : `grep` 0 trouvé / **1 rien trouvé** / 2 erreur · `diff` 0 identique / 1 différent /
2 erreur · `jq -e` 1 si sortie `null`/`false` · `xargs` 123 si un appel a échoué, 124 si un appel a
rendu 255, 125 tué par un signal.

## 3. Ordre d'expansion

| # | Étape | Exemple |
|---|---|---|
| 1 | accolades | `{a,b}` `{1..10}` `{0..100..10}` |
| 2 | tilde | `~` `~user` |
| 3 | paramètres | `$v` `${v:-d}` |
| 4 | arithmétique | `$(( 2+2 ))` |
| 5 | substitution de commande | `$(cmd)` |
| 6 | substitution de processus | `<(cmd)` → `/dev/fd/63` |
| **7** | **découpage en mots** | selon `IFS`, **sur les résultats non quotés** |
| **8** | **globbing** | `*` `?` `[a-z]` `**` (avec `globstar`) |
| 9 | suppression des quotes | `"` `'` `\` disparaissent |

## 4. Options `set` et `shopt`

| Option | Effet |
|---|---|
| `set -e` / `-o errexit` | sortie à la première commande en échec |
| `set -u` / `-o nounset` | variable non définie = erreur |
| `set -o pipefail` | code du pipeline = dernier maillon en échec |
| `set -E` / `-o errtrace` | trap `ERR` hérité par fonctions et sous-shells |
| `set -T` / `-o functrace` | idem pour `DEBUG` et `RETURN` |
| `set -x` | trace ; personnaliser avec `PS4='+ ${BASH_SOURCE}:${LINENO}: '` |
| `set -n` | analyse la syntaxe **sans exécuter** |
| `set +e` | **désactive** l'option |
| `shopt -s nullglob` | motif sans match → liste **vide** |
| `shopt -s failglob` | motif sans match → **erreur** |
| `shopt -s globstar` | `**/` récursif |
| `shopt -s dotglob` | `*` inclut les fichiers cachés |
| `shopt -s extglob` | `?()` `*()` `+()` `@()` `!()` |
| `shopt -s inherit_errexit` | `set -e` s'applique dans `$( )` |
| `shopt -s lastpipe` | dernier maillon du pipe dans le shell courant |

## 5. Expansions de paramètres

| Écriture | Effet | `f=/data/raw/ventes.csv.gz` |
|---|---|---|
| `${#v}` | longueur | `23` |
| `${v:-def}` | défaut si vide/absent | |
| `${v:=def}` | défaut **et affecte** | |
| `${v:?msg}` | **erreur + sortie** si vide/absent | validation |
| `${v:+alt}` | `alt` si **non vide** | flag conditionnel |
| `${v#*/}` | coupe plus court préfixe | `data/raw/ventes.csv.gz` |
| `${v##*/}` | plus long préfixe = **basename** | `ventes.csv.gz` |
| `${v%.gz}` | plus court suffixe | `/data/raw/ventes.csv` |
| `${v%%.*}` | plus long suffixe | `/data/raw/ventes` |
| `${v%/*}` | = **dirname** | `/data/raw` |
| `${v/a/b}` `${v//a/b}` | remplace 1re / toutes | |
| `${v:2:5}` | sous-chaîne (offset, longueur) | |
| `${v^^}` `${v,,}` | MAJ / min | |
| `${!pref@}` | noms de variables commençant par `pref` | |

## 6. Variables spéciales

| | | | |
|---|---|---|---|
| `$0` script | `$1…$9` args | `"$@"` N mots | `"$*"` 1 mot |
| `$#` nb d'args | `$?` code précédent | `$$` PID | `$!` PID du dernier `&` |
| `$_` dernier arg | `${PIPESTATUS[@]}` codes du pipe | `$LINENO` ligne | `$BASH_COMMAND` commande en cours |
| `$SECONDS` s écoulées | `${BASH_SOURCE[0]}` fichier | `$OPTARG`/`$OPTIND` (getopts) | `$IFS` séparateurs |

## 7. Tests

| `[[ ]]` | Vrai si |
|---|---|
| `-e f` `-f f` `-d f` `-L f` | existe · fichier régulier · répertoire · lien |
| **`-s f`** | existe **et taille > 0** |
| `-r f` `-w f` `-x f` | lisible · inscriptible · exécutable |
| `f1 -nt f2` / `-ot` | plus récent / plus ancien (mtime) |
| `-z s` / `-n s` | chaîne vide / non vide |
| `"$a" == "$b"` | égalité (droite **non quotée** = motif glob) |
| `"$s" =~ ^re$` | regex ERE (droite **non quotée**) ; groupes dans `${BASH_REMATCH[@]}` |
| `-eq -ne -lt -le -gt -ge` | comparaison **d'entiers** (sinon `(( ))`) |
| `-v nom` | la variable `nom` est définie |

## 8. Redirections

| Écriture | Effet |
|---|---|
| `> f` / `>> f` | stdout : écrase / ajoute |
| `2> f` | stderr seul |
| `> f 2>&1` | **tout** dans f (ordre obligatoire) |
| `2>&1 > f` | **piège** : stderr reste au terminal |
| `&> f` / `&>> f` | raccourci bash |
| `1>&2` | stdout vers stderr (les logs) |
| `< f` | stdin depuis f |
| `<<EOF` / `<<'EOF'` | here-doc : interprété / **littéral** |
| `<<-EOF` | retire les **tabulations** de début (pas les espaces) |
| `<<< "$s"` | here-string |
| `<(cmd)` / `>(cmd)` | substitution de processus → `/dev/fd/N` |
| `exec 3>&1` | duplique stdout dans le fd 3 |
| `exec > >(tee -a log) 2>&1` | journalise tout le script |
| `exec 9>f; flock -n 9` | verrou |
| `>/dev/null 2>&1` | silence total |

## 9. Boîte à outils texte

| Besoin | Commande |
|---|---|
| Compter les lignes | `wc -l < f` (le `<` évite le nom de fichier en sortie) |
| Top N valeurs d'une colonne | `awk '{print $1}' f \| sort \| uniq -c \| sort -rn \| head -10` |
| Somme d'une colonne CSV | `awk -F, 'NR>1{s+=$3} END{printf "%.2f\n", s}' f` |
| Agréger par clé | `awk -F, '{s[$2]+=$3} END{for(k in s) print k, s[k]}' f` |
| Jointure de 2 fichiers | `awk -F, 'NR==FNR{r[$1]=$2;next} $1 in r{print $0","r[$1]}' ref f` |
| Lignes mal formées | `awk -F, 'NF!=7{print FILENAME":"FNR": "NF}' *.csv` |
| Trier par colonne 3, décroissant | `sort -t, -k3,3nr f` |
| Dédoublonner | `sort -u f` · doublons seuls : `sort f \| uniq -d` |
| Différence de 2 listes | `comm -13 <(sort a) <(sort b)` |
| Supprimer l'en-tête | `tail -n +2 f` ou `sed '1d' f` |
| CSV Windows → Unix | `tr -d '\r' < f > f.unix` |
| Colonne → liste CSV | `tr '\n' ',' < ids.txt` |
| JSON → TSV | `jq -r '.[] \| [.a,.b] \| @tsv' f.json` |
| Inventaire réseau | `ip -j addr show \| jq -r '.[].ifname'` |
| Fichiers récents | `find /d -type f -mmin -60` |
| Purge > 7 jours | `find /d -type f -mtime +7 -delete` |
| Compresser en parallèle | `find /d -type f -print0 \| xargs -0 -P "$(nproc)" -n 20 gzip` |
| Les 10 plus gros | `find /d -type f -printf '%s\t%p\n' \| sort -rn \| head` |

## 10. `sort` — options qui comptent

| Option | Effet |
|---|---|
| `-t C` | séparateur de champs |
| `-k3,3` | **champ 3 seul** (`-k3` = du 3 à la fin de ligne) |
| `-n` / `-g` / `-h` | numérique / scientifique / **humain (2K < 3M)** |
| `-r` / `-u` / `-s` | inverse / dédoublonne / **stable** |
| `-S 4G` `-T /data/tmp` `--parallel=8` | gros volumes (tri externe sur disque) |
| `LC_ALL=C sort` | comparaison octet à octet : **plus rapide et déterministe** |

## 11. Squelette de script

```bash
#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
shopt -s nullglob inherit_errexit

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
log()  { printf '%s [%-5s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "${*:2}" >&2; }
die()  { log ERROR "${*:2}"; exit "$1"; }

cleanup() { local rc=$?; trap - EXIT INT TERM; [[ -n "${TMP:-}" ]] && rm -rf "${TMP:?}"; exit "$rc"; }
trap cleanup EXIT INT TERM
trap 'log ERROR "ligne $LINENO : $BASH_COMMAND"' ERR

exec 9>"/var/lock/$(basename "$0").lock"
flock -n 9 || die 75 "déjà en cours"

: "${SRC:?SRC requis}"; [[ -d "$SRC" ]] || die 66 "source absente : $SRC"
command -v duckdb >/dev/null || die 69 "duckdb introuvable"

TMP="$(mktemp -d -p "$DST" .staging-XXXXXX)"     # MÊME FS que la cible
# … produire dans "$TMP" …
mv -- "$TMP"/*.parquet "$DST/" && touch "$DST/_SUCCESS"
```

## 12. Motifs à recopier

```bash
# Lire un fichier ligne à ligne (la seule forme correcte)
while IFS= read -r l || [[ -n "$l" ]]; do …; done < "$f"

# Boucle sans perdre les variables (le sous-shell est du côté de la substitution)
while IFS= read -r f; do n=$((n+1)); done < <(find /data -name '*.parquet')

# Fichier -> tableau
mapfile -t lignes < "$f"

# Construire une ligne de commande
args=(--master yarn); [[ -n "${Q:-}" ]] && args+=(--queue "$Q"); spark-submit "${args[@]}" j.py

# Retry avec backoff exponentiel
retry(){ local m=$1 d=$2; shift 2; local n=1
  until "$@"; do (( n>=m )) && return 1; sleep "$d"; d=$((d*2)); n=$((n+1)); done; }
retry 5 2 curl -fsS --max-time 30 -o out.json https://api/dump

# Timeout avec grâce puis KILL (rend 124 si expiré)
timeout --signal=TERM --kill-after=60 4h spark-submit …

# Parallélisme avec collecte des codes
for h in "${HOSTS[@]}"; do collecter "$h" & pids+=("$!"); done
rc=0; for p in "${pids[@]}"; do wait "$p" || rc=1; done; exit "$rc"

# Options courtes
while getopts ":d:nh" o; do case "$o" in d) jour=$OPTARG;; n) dry=1;; \?) usage;; esac; done
shift $((OPTIND-1))
```

## 13. `shellcheck`

`shellcheck -x -S warning -f gcc script.sh` — `-x` suit les `source`, `-f gcc` pour la CI.
Désactivation ciblée, juste au-dessus de la ligne : `# shellcheck disable=SC2086  # raison`.

| Code | Problème | Correctif |
|---|---|---|
| **SC2086** | variable non quotée | `"$var"` |
| SC2046 | `$(…)` non quotée | `"$(cmd)"` |
| SC2155 | `local x=$(cmd)` masque le code | déclarer puis affecter |
| SC2164 | `cd` sans garde | `cd "$d" \|\| exit 1` |
| SC2115 | `rm -rf "$d/"` | `"${d:?}"` |
| SC2181 | `if [ $? -eq 0 ]` | tester la commande |
| SC2045 | itérer sur `ls` | utiliser un glob |
| SC2059 | variable dans le format `printf` | `printf '%s' "$v"` |
| SC2006 | backticks | `$( )` |
| SC1091 | `source` non analysé | `shellcheck -x` |

## 14. Signaux utiles (rappel D01)

| Nom | N° | Trappable | Usage |
|---|---|---|---|
| SIGHUP | 1 | oui | rechargement de config |
| SIGINT | 2 | oui | Ctrl-C → code 130 |
| SIGKILL | **9** | **NON** | OOM killer → code 137 |
| SIGPIPE | 13 | oui | lecteur du tube parti → code 141 |
| SIGTERM | **15** | oui | arrêt propre → code 143 |
| SIGSTOP | 19 | **NON** | suspension |
