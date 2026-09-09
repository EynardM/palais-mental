# D03 — Bash & scripting robuste

> **Ce que tu sauras faire à la fin**
> - Dérouler dans l'ordre les **9 étapes d'expansion** que bash applique à une ligne avant de l'exécuter, et expliquer pourquoi `rm $f` détruit une machine quand `rm "$f"` ne fait rien de mal.
> - Écrire l'en-tête `set -euo pipefail` + `IFS` en sachant **exactement** ce que chaque option attrape, et surtout les six cas où `set -e` te laisse tomber en silence.
> - Écrire une fonction, propager un code de retour, poser un `trap` de nettoyage et un verrou `flock` qui survit à un `kill -9` du script précédent.
> - Bâtir un pipeline texte `grep | sed | awk | sort | uniq | jq` sur de vraies données (logs HTTP, CSV, JSON, sortie de `ip -j`) et calculer une agrégation sans ouvrir Python.
> - Paralléliser proprement avec `xargs -P` et `wait`, et savoir pourquoi `find … | xargs` sans `-print0` casse au premier fichier avec une espace.
> - Écrire un script **idempotent** : validation des entrées, journalisation horodatée, écriture atomique, retry avec backoff, code de sortie parlant — et le passer au `shellcheck` sans avertissement.
> - Reconnaître le moment précis où il faut arrêter le bash et réécrire en Python.
>
> **Pourquoi ça compte dans ton poste**
> En data engineering, le bash n'est pas le langage de la logique métier : c'est le langage de la **colle**
> et de la **glu d'exécution**. Entre un `cron`/Airflow et un job Spark, il y a toujours un script shell qui
> valide des chemins, teste la fraîcheur d'une source, pose un verrou, appelle `spark-submit`, capture le
> code de retour et remonte une alerte. C'est aussi le seul langage disponible dans un conteneur minimal à
> 3 h du matin, quand tu dois savoir pourquoi une NIC drop des paquets ou pourquoi un fichier de 400 Go
> est arrivé tronqué. Un script bash mal écrit ne plante pas : il **réussit à moitié**, écrit un fichier
> partiel dans le lac de données, et pollue trois semaines de calculs en aval. Le shell robuste est donc
> une compétence de **fiabilité de données**, pas de confort.
>
> **Prérequis** : `D01` (processus, descripteurs 0/1/2, signaux, codes de sortie, tubes) — obligatoire, on
> s'appuie dessus en permanence. `R08`/`R07` aident pour les exemples réseau (`curl`, `ss`, DNS).
> **Durée de lecture** : 75-90 min. Garde un terminal ouvert : ce module se **tape**, il ne se lit pas.

---

## 1. Le shell est un langage, et il fait 9 choses avant d'exécuter quoi que ce soit

Pose la vraie question : **quand tu tapes une ligne, qu'est-ce qui est exécuté au juste ?**

Réponse : jamais ce que tu as tapé. Bash lit ta ligne, la **découpe en mots**, applique une série de
transformations dans un **ordre fixe**, obtient une liste de chaînes finales, et seulement là appelle
`fork()` + `execve()` avec cette liste comme `argv`.

Tout — absolument tout — ce que tu vas rater en bash vient de ne pas connaître cet ordre.

```
   TA LIGNE :   echo ~/data/{a,b}-$(date +%F)*.csv
                     |
   1. accolades      {a,b}          -> ~/data/a-$(...)*.csv  ~/data/b-$(...)*.csv
   2. tilde          ~              -> /home/toi/data/...
   3. paramètres     $VAR ${V:-x}   |
   4. arithmétique   $(( 2+2 ))     |  ces trois-là, de gauche à droite
   5. subst. de cmd  $(date +%F)    |  dans la même passe
   6. subst. de proc <(cmd)         -> /dev/fd/63
                     |
   7. DÉCOUPAGE EN MOTS  (word splitting)  <- seulement sur résultats NON quotés, selon IFS
                     |
   8. GLOBBING       *.csv -> liste de fichiers réels (ou motif littéral si aucun match)
                     |
   9. suppression des quotes   "  '  \   disparaissent
                     |
              argv[] final  ->  execve()
```

Trois faits contre-intuitifs à graver :

1. Le **découpage en mots (7) arrive APRÈS la substitution de variable (3)**. Donc le contenu d'une
   variable est redécoupé. C'est la cause n°1 des bugs.
2. Le **globbing (8) arrive APRÈS lui aussi**. Donc un `*` qui sort d'une variable est développé comme
   fichier. Cause n°2.
3. Les **quotes ne disparaissent qu'à l'étape 9**, ce qui veut dire qu'elles sont visibles par les
   étapes 7 et 8 — et c'est précisément comme ça qu'elles les désactivent.

> 🧠 **MÉMO** — « **A-T-P-A-C-P — Découpe, Glob, Démasque** » : Accolades, Tilde, Paramètres,
> Arithmétique, Commandes, Processus, puis Découpage, Globbing, Démasquage des quotes.
> Retiens surtout la fin : **Découpe → Glob → Démasque**. Les trois dernières étapes sont celles qui
> te tuent.

Démonstration au terminal, avec la sortie commentée :

```bash
$ f='mon rapport.csv'
$ ls -l $f
ls: cannot access 'mon': No such file or directory        # étape 7 a coupé sur l'espace…
ls: cannot access 'rapport.csv': No such file or directory # …et a fabriqué DEUX arguments
$ ls -l "$f"
-rw-r--r-- 1 you you 1240 Sep  9 10:12 'mon rapport.csv'   # un seul argument, correct
```

```bash
$ v='*'
$ echo $v
D01.tsv D03.tsv README.md      # étape 8 : le contenu de $v a été globbé sur le répertoire
$ echo "$v"
*                              # quoté : ni découpage ni globbing
```

> ❓ **RETIENS ÇA** — Le découpage en mots et le globbing s'appliquent-ils avant ou après le remplacement d'une variable ?
> <details><summary>→ réponse</summary><br><b>Après</b>. Bash remplace d'abord <code>$var</code> par son contenu, <b>puis</b> découpe ce contenu sur les caractères d'<code>IFS</code>, <b>puis</b> tente le globbing dessus. C'est pour ça qu'une variable non quotée contenant une espace ou une étoile change le nombre d'arguments réellement passés au programme.</details>

> ⚠️ **PIÈGE** — Le globbing est fait par **le shell**, pas par la commande. `ls *.csv` ne reçoit jamais
> `*.csv` : il reçoit déjà la liste des fichiers. Corollaire : si **aucun** fichier ne correspond, bash
> passe le motif **littéral** — d'où la boucle qui s'exécute une fois avec `f='*.csv'` sur un répertoire
> vide. Antidote : `shopt -s nullglob` (le motif sans match devient une liste vide).

---

## 2. Le quoting : la source n°1 de bugs, et elle tient en 4 règles

**Le problème** : tu veux transmettre une chaîne telle quelle, mais le shell veut la transformer.
Le quoting est le mécanisme qui dit « n'y touche pas ».

| Forme | Ce qui est encore interprété | Usage |
|---|---|---|
| `'simple'` | **rien du tout** | chaîne littérale. Impossible d'y mettre une `'` |
| `"double"` | `$var`, `` `…` ``, `$(…)`, `$(( ))`, `\` (partiellement), `!` en interactif | **99 % des cas** |
| `\c` | échappe le caractère suivant | un caractère isolé |
| `$'…'` | interprète `\n`, `\t`, `\x41`, `é` | seule façon propre d'écrire une tabulation |

Les 4 règles, dans l'ordre d'importance :

1. **Quote toute expansion de variable.** `"$var"`, `"$@"`, `"$(cmd)"`, `"${arr[@]}"`. Pas d'exception
   utile pour un débutant. Si tu veux du découpage, tu l'écris exprès avec un commentaire.
2. **`"$@"` et jamais `$*`.** `"$@"` se développe en **un mot par argument**, en préservant les espaces.
   `"$*"` colle tous les arguments en **une seule chaîne**, séparés par le **premier caractère d'IFS**.
3. **Les guillemets doubles s'arrêtent aux frontières**, pas aux commandes : `"$(dirname "$0")"` est
   correct et non ambigu — bash ré-ouvre un contexte de quoting à l'intérieur de `$( )`.
4. **Pas de quoting = tu demandes explicitement le découpage et le globbing.**

```bash
$ set -- "un deux" trois          # deux arguments positionnels
$ printf '[%s]\n' "$@"
[un deux]                          # arg 1 intact
[trois]
$ printf '[%s]\n' "$*"
[un deux trois]                    # un SEUL argument, joint par l'espace (1er char d'IFS)
$ printf '[%s]\n' $@              # non quoté : recoupé
[un]
[deux]
[trois]
```

> ❓ **RETIENS ÇA** — Quelle différence exacte entre `"$@"` et `"$*"` ?
> <details><summary>→ réponse</summary><br><code>"$@"</code> produit <b>N mots</b>, un par argument, chacun préservé tel quel. <code>"$*"</code> produit <b>1 seul mot</b> : tous les arguments concaténés, séparés par le <b>premier caractère d'IFS</b> (une espace par défaut). Dans un script qui relaie ses arguments à une autre commande, c'est toujours <code>"$@"</code>.</details>

> ⚠️ **PIÈGE** — `echo "Total : $(( 3 * n ))"` fonctionne, mais `echo "Fichiers : *"` n'affiche pas la
> liste : le globbing n'a pas lieu dans des guillemets. À l'inverse `grep -r $motif .` où
> `motif='foo bar'` cherche `foo` dans le fichier `bar`. Le quoting n'est pas cosmétique, il change
> **le nombre d'arguments**.

> 🧠 **MÉMO** — **« Si ça sort d'un `$`, ça rentre dans des `"` »**. Neuf bugs bash sur dix meurent
> avec cette seule phrase.

---

## 3. Variables, expansions de paramètres, tableaux

### 3.1 Variables : pas de type, pas d'espace autour du `=`

```bash
nom=valeur          # correct
nom = valeur        # ERREUR : bash cherche à exécuter le programme "nom"
export NOM=valeur   # passé aux processus enfants (dans leur environnement)
readonly PI=3       # constante
local x             # uniquement dans une fonction
```

Une variable shell non exportée n'existe **pas** pour les processus fils. C'est la distinction
variable de shell / variable d'environnement de `D01` : `env` ne montre que les secondes.

### 3.2 Les expansions de paramètres : le couteau suisse

Elles évitent d'appeler `basename`, `dirname`, `sed`, `cut` — donc évitent un `fork()` à chaque tour de
boucle (comptable : ~1 ms par fork, ×100 000 fichiers = 100 s de perdues).

| Écriture | Effet | Exemple `f=/data/raw/ventes.csv.gz` |
|---|---|---|
| `${#v}` | longueur | `${#f}` → `24` |
| `${v:-def}` | valeur si vide/non défini (**ne modifie pas** `v`) | garde-fou de lecture |
| `${v:=def}` | idem **et affecte** `v` | valeur par défaut durable |
| `${v:?msg}` | **erreur et sortie** si vide/non défini | validation d'entrée |
| `${v:+alt}` | `alt` seulement si `v` est **non vide** | ajouter un flag conditionnel |
| `${v#motif}` | coupe le **plus court** préfixe | `${f#*/}` → `data/raw/ventes.csv.gz` |
| `${v##motif}` | coupe le **plus long** préfixe = `basename` | `${f##*/}` → `ventes.csv.gz` |
| `${v%motif}` | coupe le **plus court** suffixe | `${f%.gz}` → `/data/raw/ventes.csv` |
| `${v%%motif}` | coupe le **plus long** suffixe | `${f%%.*}` → `/data/raw/ventes` |
| `${v/a/b}` | remplace la **1re** occurrence | |
| `${v//a/b}` | remplace **toutes** les occurrences | |
| `${v:2:5}` | sous-chaîne (offset, longueur) | |
| `${v^^}` / `${v,,}` | MAJUSCULES / minuscules (bash ≥ 4.0) | |

> 🧠 **MÉMO** — **`#` est à gauche sur le clavier des dièses… et coupe à gauche ; `%` coupe à droite.**
> Autre image : `#` c'est le début d'un commentaire (**début** de ligne), `%` c'est la fin (le pourcentage
> se met **après** le nombre). Et **doubler le signe = manger plus**.

> ❓ **RETIENS ÇA** — Comment obtenir le nom de fichier sans chemin, sans appeler `basename` ?
> <details><summary>→ réponse</summary><br><code>${f##*/}</code> — on coupe le <b>plus long</b> préfixe se terminant par <code>/</code>. Le dossier s'obtient symétriquement avec <code>${f%/*}</code>. Zéro <code>fork()</code>, donc utilisable dans une boucle de 100 000 tours.</details>

### 3.3 Substitution de commande

```bash
today=$(date -u +%F)             # forme moderne, imbricable
n=$(wc -l < data.csv)            # < évite un fork de cat ET la sortie "nom de fichier"
content=$(<fichier)              # LE plus rapide : builtin, aucun processus créé
```

Deux propriétés à connaître par cœur :
- La substitution s'exécute dans un **sous-shell** : toute variable modifiée dedans est **perdue**.
- Elle **supprime tous les sauts de ligne finaux**. `x=$(printf 'a\n\n\n')` donne `x='a'`.

> ⚠️ **PIÈGE** — Les backticks `` `cmd` `` sont l'ancienne syntaxe : imbrication illisible, échappement
> des `\` différent. `shellcheck` te sortira **SC2006**. Utilise `$( )`, toujours.

### 3.4 Tableaux (bash uniquement, pas POSIX `sh`)

```bash
arr=(alpha "deux mots" gamma)
arr+=(delta)                     # ajout
echo "${arr[1]}"                 # deux mots      (index à partir de 0)
echo "${#arr[@]}"                # 4              (nombre d'éléments)
echo "${!arr[@]}"                # 0 1 2 3        (les indices)
printf '%s\n' "${arr[@]}"        # itération SÛRE, un élément par ligne

declare -A conf                  # tableau associatif (bash >= 4.0)
conf[env]=prod ; conf[retries]=3
echo "${conf[retries]}"          # 3
for k in "${!conf[@]}"; do echo "$k=${conf[$k]}"; done
```

**Le cas d'usage n°1 en data eng** : construire une ligne de commande dynamiquement.

```bash
args=(--master yarn --deploy-mode cluster)
[[ -n ${QUEUE:-} ]] && args+=(--queue "$QUEUE")
spark-submit "${args[@]}" job.py          # chaque option reste un argument distinct
```

C'est la seule façon correcte : mettre les options dans une **chaîne** et ne pas la quoter fonctionne
« par hasard » jusqu'au premier chemin avec une espace.

> ❓ **RETIENS ÇA** — Comment lire un fichier ligne par ligne dans un tableau, sans boucle ?
> <details><summary>→ réponse</summary><br><code>mapfile -t lignes &lt; fichier</code> (alias <code>readarray</code>, bash ≥ 4.0). Le <code>-t</code> retire le saut de ligne final de chaque élément. Pour des noms de fichiers issus de <code>find -print0</code> : <code>mapfile -d '' -t f &lt; &lt;(find … -print0)</code> (bash ≥ 4.4).</details>

---

## 4. L'en-tête de tout script sérieux : `set -euo pipefail` et `IFS`

**Le problème** : par défaut, le shell est fait pour l'interactif. Il est **indulgent** — une commande
échoue, il continue ; une variable n'existe pas, il la remplace par du vide. Dans un script d'ingestion,
cette indulgence signifie : `cd /data/prod` échoue, puis `rm -rf ./tmp/*` s'exécute dans le mauvais
répertoire.

```bash
#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
```

Décortiquons ligne par ligne, option par option, **avec ses trous**.

### 4.1 `set -e` (errexit) — « arrête-toi à la première erreur »

Le shell quitte dès qu'une commande retourne un code ≠ 0. **Sauf** dans six situations, qu'il faut
connaître, parce que ce sont exactement celles où on croit être protégé :

```
   set -e NE DÉCLENCHE PAS quand la commande est :

   1. la condition d'un if / while / until      if grep -q x f; then       <- normal
   2. à gauche/droite d'un && ou ||             cmd_qui_echoue || true
   3. précédée d'un !                           ! grep -q x f
   4. ailleurs que la dernière d'un pipeline    faux | vrai   -> code 0    <- d'où pipefail
   5. dans une substitution de commande         x=$(faux); echo "continue" <- (sans inherit_errexit)
   6. une affectation avec local/export/declare local x=$(faux)  -> code de "local" = 0
```

Les cas 5 et 6 sont les plus vicieux. Démonstration :

```bash
$ bash -c 'set -e; f(){ local v=$(exit 7); echo "je passe, code=$?"; }; f'
je passe, code=0        # le code 7 a été AVALÉ par "local", qui retourne 0
$ bash -c 'set -e; f(){ local v; v=$(exit 7); echo "jamais"; }; f; echo ok'
                        # rien : déclaration et affectation SÉPARÉES -> set -e voit le 7
```

C'est l'avertissement **SC2155** de shellcheck : *« Declare and assign separately to avoid masking
return values. »*

Autre piège classique, celui de l'incrémentation :

```bash
$ bash -c 'set -e; i=0; ((i++)); echo "atteint $i"'
                        # RIEN. (( )) retourne 1 quand le RÉSULTAT vaut 0 : i++ rend 0 (post-incrément)
$ bash -c 'set -e; i=0; ((++i)); echo "atteint $i"'
atteint 1               # pré-incrément : le résultat vaut 1, donc code 0
$ bash -c 'set -e; i=0; i=$((i+1)); echo "atteint $i"'
atteint 1               # forme sûre, toujours
```

> ⚠️ **PIÈGE** — `((i++))` avec `set -e` tue ton script au premier tour de boucle, et seulement quand le
> compteur part de 0. Le bug ne se voit pas en test si tu commences à 1. Écris `i=$((i+1))` ou
> `((i++)) || true`.

> ❓ **RETIENS ÇA** — Pourquoi `local v=$(commande_qui_echoue)` ne déclenche-t-il pas `set -e` ?
> <details><summary>→ réponse</summary><br>Parce que le code de retour de la ligne est celui de la <b>commande <code>local</code></b> (qui réussit), pas celui de la substitution. Idem avec <code>export</code>, <code>declare</code>, <code>readonly</code>. Correctif : <code>local v; v=$(commande)</code> sur deux lignes.</details>

### 4.2 `set -u` (nounset) — « une variable non définie est une erreur »

```bash
$ bash -c 'echo "suppression de /$DOSSIER"'
suppression de /              # sans -u : le désastre est silencieux
$ bash -c 'set -u; echo "suppression de /$DOSSIER"'
bash: DOSSIER: unbound variable      # code de sortie 1
```

Conséquence pratique : toute variable **optionnelle** doit être écrite `${VAR:-}`.

```bash
if [[ -n "${DEBUG:-}" ]]; then set -x; fi     # correct sous set -u
```

> ⚠️ **PIÈGE** — Sur bash < 4.4, `"${arr[@]}"` sur un tableau **vide** déclenche `unbound variable`
> sous `set -u` (macOS livre encore bash **3.2**). Écriture défensive portable :
> `"${arr[@]+"${arr[@]}"}"`. Sur bash ≥ 4.4, le cas est corrigé.

### 4.3 `set -o pipefail` — « le code d'un pipeline n'est plus celui du dernier maillon »

Rappel de `D01` : par défaut le code d'un pipeline est celui de **la dernière** commande.

```bash
$ curl -f https://api.interne/dump | gzip > dump.gz ; echo "code=$?"
code=0            # curl a pris un 404, gzip a réussi à compresser du vide -> "succès"
$ set -o pipefail
$ curl -f https://api.interne/dump | gzip > dump.gz ; echo "code=$?"
code=22           # 22 = code de curl pour une erreur HTTP >= 400
```

Avec `pipefail`, le code du pipeline est celui de la **dernière commande ayant échoué**, ou 0 si toutes
réussissent. Le détail complet reste lisible dans `PIPESTATUS` :

```bash
$ false | true | false ; echo "${PIPESTATUS[@]}"
1 0 1             # un code par maillon, dans l'ordre (à lire IMMÉDIATEMENT après)
```

> ⚠️ **PIÈGE** — `pipefail` + `head` = faux positif. `zcat gros.gz | head -5` : `head` sort après 5
> lignes, `zcat` reçoit **SIGPIPE (13)** et rend **141**, donc le pipeline échoue et `set -e` tue le
> script. Solutions : `|| true` ciblé, ou `zcat gros.gz | { head -5; cat >/dev/null; }`.

> ❓ **RETIENS ÇA** — Sans `pipefail`, quel est le code de retour de `commande_qui_echoue | tee log` ?
> <details><summary>→ réponse</summary><br><b>0</b> — celui de <code>tee</code>. C'est le piège classique de la journalisation : on ajoute <code>| tee</code> à une commande critique et on rend tous ses échecs invisibles. Il faut <code>set -o pipefail</code> ou lire <code>${PIPESTATUS[0]}</code>.</details>

### 4.4 `set -E` (errtrace) et `set -T`

`set -E` fait **hériter le trap ERR** par les fonctions, sous-shells et substitutions de commande. Sans
lui, ton beau `trap 'erreur ligne $LINENO' ERR` ne se déclenche pas à l'intérieur des fonctions — donc
nulle part où ça compte. `set -T` fait la même chose pour les traps `DEBUG` et `RETURN`.

### 4.5 `IFS` — le séparateur de champs interne

`IFS` (Internal Field Separator) est la liste des caractères sur lesquels l'étape 7 (découpage) coupe.
**Valeur par défaut : espace, tabulation, saut de ligne** (`$' \t\n'`).

`IFS=$'\n\t'` retire **l'espace** de la liste : les expansions non quotées ne se coupent plus au milieu
d'un nom de fichier. C'est un filet de sécurité, pas une dispense de quoting.

```bash
$ ligne='alice;30;paris'
$ IFS=';' read -r nom age ville <<< "$ligne"    # IFS local à cette commande seulement
$ echo "$ville"
paris
```

> ⚠️ **PIÈGE** — Modifier `IFS` globalement casse tout code qui comptait sur le découpage à l'espace
> (`for mot in $phrase`), et change le collage de `"$*"`. Préfère la forme **préfixée** `IFS=';' read …`,
> qui ne vaut que pour la commande. Et n'oublie jamais le `-r` de `read` (sans lui, les `\` sont mangés).

Le motif canonique de lecture d'un fichier ligne à ligne, à connaître par cœur :

```bash
while IFS= read -r ligne || [[ -n "$ligne" ]]; do
    printf 'LU: %s\n' "$ligne"
done < "$fichier"
```

- `IFS=` (vide) : conserve les espaces de début et de fin.
- `-r` : conserve les antislashs.
- `|| [[ -n "$ligne" ]]` : traite la **dernière ligne sans saut de ligne final** — cas fréquent des
  exports CSV mal terminés.

> ❓ **RETIENS ÇA** — Quelle est la valeur par défaut d'`IFS` ?
> <details><summary>→ réponse</summary><br><b>Espace, tabulation, saut de ligne</b> — <code>IFS=$' \t\n'</code>. Le passer à <code>$'\n\t'</code> supprime le découpage sur l'espace, ce qui protège les chemins contenant des espaces.</details>

### 4.6 Les `shopt` utiles

| Option | Effet | Quand |
|---|---|---|
| `shopt -s nullglob` | motif sans correspondance → **liste vide** | toute boucle `for f in *.csv` |
| `shopt -s failglob` | motif sans correspondance → **erreur** | quand l'absence est anormale |
| `shopt -s globstar` | active `**/` récursif | `for f in data/**/*.parquet` |
| `shopt -s dotglob` | `*` inclut les fichiers cachés | nettoyage de répertoire |
| `shopt -s extglob` | motifs étendus `!(x)`, `@(a\|b)`, `+(…)` | filtrage fin |
| `shopt -s inherit_errexit` | `set -e` s'applique dans les `$( )` (bash ≥ 4.4) | bouche le trou n°5 |
| `shopt -s lastpipe` | le **dernier** maillon d'un pipe tourne dans le shell courant | garder une variable |

---

## 5. Tests, conditions, boucles, `case`

### 5.1 `[ ]` contre `[[ ]]` : ne jamais hésiter

`[` est une **commande** (un builtin, et aussi `/usr/bin/[`) : ses arguments subissent découpage et
globbing. `[[ ]]` est un **mot-clé** du shell : bash l'analyse sans découper.

| | `[ ]` (POSIX) | `[[ ]]` (bash) |
|---|---|---|
| Variable vide non quotée | **erreur de syntaxe** | sans danger |
| `&&` `\|\|` internes | non (`-a`/`-o`, obsolètes) | oui |
| Comparaison de motifs | non | `[[ $f == *.csv ]]` |
| Regex | non | `[[ $ip =~ ^[0-9.]+$ ]]` |
| Portabilité `sh`/dash | oui | non |

**Règle** : dans un script bash (`#!/usr/bin/env bash`), utilise `[[ ]]` partout. Réserve `[ ]` aux
scripts qui doivent tourner sous `sh`/`dash` (l'image Docker Alpine, par exemple).

```bash
[[ -f "$f" ]]          # fichier régulier existant
[[ -d "$d" ]]          # répertoire
[[ -s "$f" ]]          # existe ET taille > 0        <- LE test d'un fichier de données
[[ -r "$f" ]]          # lisible par moi
[[ -z "$s" ]] / [[ -n "$s" ]]   # chaîne vide / non vide
[[ "$a" == "$b" ]]     # égalité de chaînes
[[ "$f" == *.parquet ]]  # motif : le côté DROIT non quoté est un GLOB
[[ "$f" == "$motif" ]]   # côté droit quoté = comparaison LITTÉRALE
[[ $n -gt 100 ]]       # entiers : -eq -ne -lt -le -gt -ge
(( n > 100 ))          # équivalent arithmétique, plus lisible
[[ "$a" < "$b" ]]      # ordre lexicographique
[[ f1 -nt f2 ]]        # f1 plus récent que f2 (mtime)
```

> ⚠️ **PIÈGE** — `[[ $a > $b ]]` compare des **chaînes**, pas des nombres : `[[ 9 > 10 ]]` est **vrai**
> (« 9 » vient après « 1 » dans l'ordre des caractères). Pour des nombres : `(( 9 > 10 ))` → faux.
> Inversement, dans `[ ]`, `>` est une **redirection** : `[ 3 > 2 ]` crée un fichier nommé `2` et
> retourne vrai toujours.

> ❓ **RETIENS ÇA** — Quel test utiliser pour vérifier qu'un fichier de données existe **et n'est pas vide** ?
> <details><summary>→ réponse</summary><br><code>[[ -s "$f" ]]</code>. <code>-f</code> ne teste que l'existence : un fichier de 0 octet le passe. Dans un pipeline d'ingestion, le fichier vide est le cas d'échec le plus fréquent (transfert coupé, requête sans résultat).</details>

### 5.2 Boucles

```bash
for f in /data/in/*.csv; do …; done          # sur des fichiers : préférer TOUJOURS le glob
for i in {1..10}; do …; done                 # accolades : 1 2 3 … 10
for i in {0..100..10}; do …; done            # avec pas (bash >= 4.0) : 0 10 20 …
for ((i=0; i<n; i++)); do …; done            # style C
for arg in "$@"; do …; done                  # sur les arguments : quoter !
while read -r l; do …; done < f              # sur un fichier
until ping -c1 -W1 "$h" &>/dev/null; do sleep 2; done   # attendre un hôte
```

> ⚠️ **PIÈGE MAJEUR** — `for f in $(ls *.csv)` est doublement faux : `ls` recoupe sur les espaces, et la
> sortie subit un second globbing. **N'utilise jamais `ls` dans un script.** Le glob `for f in *.csv`
> fait le travail correctement, y compris pour un fichier nommé `mon rapport été.csv`.

> ⚠️ **PIÈGE** — `cat f | while read -r l; do n=$((n+1)); done; echo "$n"` affiche **vide/0** : chaque
> maillon d'un pipe tourne dans un **sous-shell**, la variable meurt avec lui. Correctifs :
> redirection `done < f`, ou substitution de processus `done < <(cmd)`, ou `shopt -s lastpipe`.

### 5.3 `case` — le bon outil pour dispatcher

```bash
case "$fichier" in
    *.csv)          charger_csv "$fichier" ;;
    *.parquet)      charger_parquet "$fichier" ;;
    *.json|*.ndjson) charger_json "$fichier" ;;      # alternatives avec |
    *.tmp|*.part)   continue ;;                      # fichiers en cours d'écriture : ignorer
    *)              log ERROR "extension inconnue: $fichier"; exit 2 ;;
esac
```

`;;` termine ; `;&` **enchaîne** sur le bloc suivant sans tester ; `;;&` continue à tester les motifs
suivants (bash ≥ 4.0). `case` compare avec des **globs**, pas des regex.

---

## 6. Fonctions, arguments, codes de retour

```bash
verifier_fraicheur() {              # pas de liste de paramètres dans la signature
    local chemin="$1"               # local : sinon la variable est GLOBALE
    local max_min="${2:-60}"        # valeur par défaut du 2e argument
    [[ -n "$chemin" ]] || { echo "usage: verifier_fraicheur <chemin> [minutes]" >&2; return 2; }
    [[ -e "$chemin" ]] || return 3

    local age_s=$(( $(date +%s) - $(stat -c %Y "$chemin") ))
    (( age_s <= max_min * 60 ))     # le code de retour de la fonction = celui de la dernière commande
}

if verifier_fraicheur /data/in/ventes.csv 30; then
    echo "frais"
else
    echo "périmé ou absent (code $?)"
fi
```

Points structurants :

- Dans une fonction, `$1 $2 … $@ $#` sont **ceux de la fonction**, pas ceux du script. `$0` reste le
  script.
- `return` sort de la fonction (code 0-255), `exit` tue **tout le script**. Confondre les deux est un
  classique d'entretien.
- **`local` sur toutes les variables**, sinon elles polluent l'espace global — les fonctions bash n'ont
  pas de portée par défaut.
- Une fonction retourne un **entier**, pas une valeur. Pour « retourner » une chaîne : `echo` la valeur
  et capturer avec `$( )`, ou écrire dans une variable passée par nom (`local -n ref="$1"`, bash ≥ 4.3).

### 6.1 Codes de sortie : le vocabulaire d'un script

| Code | Sens |
|---|---|
| **0** | succès — le seul qui le signifie |
| 1 | erreur générique |
| 2 | erreur d'usage (convention : mauvais arguments) |
| 64-78 | codes `sysexits.h` (`EX_USAGE`=64, `EX_DATAERR`=65, `EX_NOINPUT`=66…), rarement utilisés |
| **126** | fichier trouvé mais **non exécutable** |
| **127** | **commande introuvable** (PATH, typo, binaire absent de l'image) |
| **128+N** | tué par le signal **N** |
| **130** | 128+2 = **SIGINT** (Ctrl-C) |
| **137** | 128+9 = **SIGKILL** (OOM killer, `kill -9`) |
| **141** | 128+13 = **SIGPIPE** |
| **143** | 128+15 = **SIGTERM** (arrêt propre demandé) |
| 124 | **`timeout` a expiré** |
| 255 | code hors bornes (le shell tronque modulo 256) |

> ❓ **RETIENS ÇA** — Un conteneur d'ingestion sort avec le code 137. Que s'est-il passé ?
> <details><summary>→ réponse</summary><br>128 + 9 : le processus a reçu <b>SIGKILL</b>. En pratique quasi toujours l'<b>OOM killer</b> (dépassement de <code>memory.max</code> du cgroup) ou un <code>docker kill</code> après expiration du délai de grâce. Un 143 (SIGTERM) signifierait au contraire un arrêt <b>demandé</b> et propre.</details>

> 🧠 **MÉMO** — **« 126 je ne peux pas, 127 je ne trouve pas, 128+N on m'a tué »**. Et les trois tueurs
> à retenir : **130** = Ctrl-C, **137** = OOM, **143** = arrêt propre.

### 6.2 Analyser les options avec `getopts`

```bash
usage() { echo "usage: $0 [-v] [-d AAAA-MM-JJ] -i CHEMIN" >&2; exit 64; }
verbose=0; date_lot=$(date -u +%F); chemin=""
while getopts ":vd:i:h" opt; do
    case "$opt" in
        v) verbose=1 ;;
        d) date_lot="$OPTARG" ;;         # le ':' après la lettre = option AVEC argument
        i) chemin="$OPTARG" ;;
        h) usage ;;
        :) echo "option -$OPTARG : argument manquant" >&2; usage ;;   # actif car ':' initial
        \?) echo "option inconnue : -$OPTARG" >&2; usage ;;
    esac
done
shift $((OPTIND - 1))                    # consomme les options, laisse les arguments dans "$@"
[[ -n "$chemin" ]] || usage
```

`getopts` ne gère **que les options courtes** (`-v`, pas `--verbose`). Pour du long, on écrit une boucle
`while [[ $# -gt 0 ]]` + `case` à la main.

---

## 7. `trap`, nettoyage, et le verrou

**Le problème** : ton script crée un répertoire temporaire de 40 Go, puis Airflow lui envoie un SIGTERM.
Qui nettoie ? Personne — sauf si tu as posé un `trap`.

`trap` associe une commande à un événement : un signal (`INT`, `TERM`, `HUP`…) ou une pseudo-condition
du shell (`EXIT`, `ERR`, `DEBUG`, `RETURN`).

```bash
#!/usr/bin/env bash
set -Eeuo pipefail

tmpdir="$(mktemp -d -t ingest-XXXXXX)"     # les X sont remplacés aléatoirement

cleanup() {
    local rc=$?                            # CAPTURER le code AVANT toute autre commande
    trap - EXIT INT TERM                   # désarmer : évite un double passage
    rm -rf "${tmpdir:?}"                   # :? garantit qu'on ne fait pas "rm -rf /"
    (( rc == 0 )) && log INFO "terminé" || log ERROR "échec (code $rc)"
    exit "$rc"
}
trap cleanup EXIT INT TERM
trap 'log ERROR "erreur ligne $LINENO : \"$BASH_COMMAND\" (code $?)"' ERR
```

Détails qui font la différence :

- `local rc=$?` **en toute première ligne** du handler : la moindre commande avant écrase `$?`.
- `trap - EXIT INT TERM` désarme, sinon `exit "$rc"` peut relancer le handler.
- `rm -rf "${tmpdir:?}"` : si `tmpdir` est vide, bash **refuse** et affiche l'erreur — c'est le
  garde-fou contre le `rm -rf /` historique (avertissement shellcheck **SC2115**).
- Le trap `ERR` te donne `$LINENO` (la ligne) et `$BASH_COMMAND` (la commande fautive) : c'est ta
  stack trace. Il exige `set -E` pour fonctionner dans les fonctions.
- **Aucun trap n'attrape SIGKILL (9) ni SIGSTOP (19)** — ils ne sont pas rattrapables, par conception
  du noyau. Un script tué par l'OOM killer ne nettoiera jamais : c'est pourquoi les fichiers temporaires
  vont dans un répertoire balayé au démarrage.
- Trappe explicitement `EXIT INT TERM` : ne parie pas sur `EXIT` seul pour couvrir les signaux.

> ❓ **RETIENS ÇA** — Quels signaux ne peuvent pas être rattrapés par `trap` ?
> <details><summary>→ réponse</summary><br><b>SIGKILL (9)</b> et <b>SIGSTOP (19)</b>. Le noyau les traite sans passer par le processus. Conséquence directe : le nettoyage par <code>trap</code> ne couvre pas l'OOM killer ni un <code>kill -9</code>, il faut un filet côté système (répertoire temporaire jetable, verrou <code>flock</code> libéré à la mort du process).</details>

### 7.1 Le verrou : `flock`, et rien d'autre

**Le problème** : l'ingestion de 06 h 00 dure 70 minutes. Celle de 07 h 00 démarre par-dessus. Deux
process écrivent le même fichier de sortie.

La solution naïve — un fichier `.pid` : `[[ -f lock ]] && exit` puis `touch lock` — a deux défauts
rédhibitoires : **course** entre le test et le `touch` (deux process peuvent passer), et **verrou
fantôme** si le script meurt sur `kill -9` sans supprimer le fichier.

`flock(2)` résout les deux : le verrou est porté par un **descripteur de fichier**, et le noyau le
libère automatiquement quand le processus meurt, quelle qu'en soit la raison.

```bash
# Forme 1 — enveloppe (la plus simple)
flock -n /var/lock/ingest.lock -c '/opt/bin/ingest.sh'   # -n : échoue tout de suite si occupé

# Forme 2 — dans le script lui-même
exec 9>/var/lock/ingest.lock          # fd 9 ouvert pour toute la durée du script
if ! flock -n 9; then
    echo "une autre instance tourne déjà, abandon" >&2
    exit 75                            # EX_TEMPFAIL : réessayer plus tard
fi
# … le verrou tient jusqu'à la fermeture du fd, donc jusqu'à la fin du process
```

Options : `-n` non bloquant, `-w 30` attendre 30 s puis abandonner, `-s` verrou **partagé** (plusieurs
lecteurs), `-x` **exclusif** (défaut).

> 🧠 **MÉMO** — **« Le verrou n'est pas dans le fichier, il est dans le descripteur. »** Le fichier
> `.lock` peut rester sur disque pour l'éternité, il ne verrouille rien tout seul. Le process meurt →
> le fd se ferme → le verrou saute. Zéro verrou fantôme.

---

## 8. Redirections avancées, here-doc, substitution de processus

Rappel `D01` : `0` stdin, `1` stdout, `2` stderr ; `>` ne redirige **que le 1**.

```bash
cmd > out.log 2>&1        # tout dans out.log — L'ORDRE COMPTE
cmd 2>&1 > out.log        # FAUX : 2 part vers le terminal, seul 1 va dans le fichier
cmd &> out.log            # raccourci bash équivalent au premier
cmd >> out.log 2>&1       # ajout
cmd 2>/dev/null           # jeter uniquement les erreurs
cmd >/dev/null 2>&1       # tout jeter (silence total)
cmd 1>&2                  # envoyer stdout sur stderr (LE bon canal pour les logs)
exec 3>&1                 # dupliquer stdout dans le fd 3 (sauvegarde)
exec 1>fichier            # rediriger TOUT le reste du script
```

> ⚠️ **PIÈGE** — `2>&1` signifie « fais pointer 2 vers **là où 1 pointe en ce moment** ». C'est une
> **photo**, pas un lien. Écrit avant `> fichier`, la photo montre encore le terminal. Moyen mnémotechnique :
> **on range d'abord la destination (`>`), on duplique ensuite (`2>&1`)**.

### 8.1 Here-document et here-string

```bash
cat <<EOF > /tmp/conf.ini      # variables INTERPRÉTÉES
[spark]
master=$MASTER_URL
date=$(date -u +%F)
EOF

cat <<'EOF' > /tmp/script.py   # 'EOF' quoté : AUCUNE interprétation ($ littéral)
import os
print(f"{os.environ['HOME']}")   # les $ et backticks passent tels quels
EOF

cat <<-EOF                     # <<- retire les TABULATIONS de début de ligne (PAS les espaces)
	texte indenté dans le code, aligné à gauche en sortie
	EOF

grep -c error <<< "$contenu"   # here-string : envoie une chaîne sur stdin (1 seul argument)
```

> ❓ **RETIENS ÇA** — Quelle différence entre `<<EOF` et `<<'EOF'` ?
> <details><summary>→ réponse</summary><br>Sans quotes, le corps subit l'expansion des variables, de <code>$(…)</code> et de l'arithmétique. Avec le délimiteur <b>quoté</b> (<code>&lt;&lt;'EOF'</code>), le corps est passé <b>littéralement</b> — indispensable pour générer un script Python, un YAML ou une requête SQL contenant des <code>$</code>.</details>

### 8.2 Substitution de processus `<(…)` et `>(…)`

**Le problème** : `diff` veut deux **fichiers**, tu as deux **commandes**. Sans fichier temporaire ?

```bash
$ diff <(sort a.txt) <(sort b.txt)
$ ls -l /dev/fd/63
lr-x------ 1 you you 64 Sep  9 11:02 /dev/fd/63 -> 'pipe:[3814226]'
```

`<(cmd)` lance `cmd`, branche sa sortie sur un tube, et **remplace l'expression par un chemin**
(`/dev/fd/63`) que la commande appelante ouvre comme un fichier. Aucun fichier temporaire, aucun
nettoyage.

Trois usages que tu réutiliseras tout le temps :

```bash
# 1. Comparer deux inventaires sans écrire sur disque
comm -13 <(sort inventaire_source.txt) <(sort inventaire_cible.txt)   # présents seulement en cible

# 2. Lire une commande dans un while SANS perdre les variables (le sous-shell est côté GAUCHE ici)
n=0
while IFS= read -r f; do n=$((n+1)); done < <(find /data -name '*.parquet')
echo "$n fichiers"        # affiche le vrai compte

# 3. Journalisation : tout le script est dupliqué vers un fichier ET vers l'écran
exec > >(tee -a "/var/log/ingest-$(date -u +%F).log") 2>&1
```

> ⚠️ **PIÈGE** — La substitution de processus est du **bash**, pas du POSIX. Sous `#!/bin/sh` (dash sur
> Debian/Ubuntu), `<(…)` est une erreur de syntaxe. C'est l'erreur la plus fréquente en CI, quand un
> script testé en local en bash est lancé par `sh script.sh`.

---

## 9. La boîte à outils texte : les 10 commandes qui font 95 % du travail

Le modèle mental : chaque outil est un **transformateur de flux ligne à ligne**. On les enchaîne par
tubes ; chaque maillon est un processus séparé, donc **parallèle par construction** (le noyau ordonnance,
le tampon de tube de 64 Kio régule le débit).

```
 fichier ──> grep ──> sed ──> awk ──> sort ──> uniq ──> tête
           filtrer  éditer  calculer  ranger  compter
           les      les     par       pour    les
           lignes   champs  colonnes  grouper doublons
```

### 9.1 `grep` — filtrer des **lignes**

| Option | Effet | Option | Effet |
|---|---|---|---|
| `-i` | insensible à la casse | `-r`/`-R` | récursif (R suit les liens) |
| `-v` | lignes **non** correspondantes | `-l`/`-L` | fichiers **avec** / **sans** match |
| `-c` | compte les **lignes** | `-n` | numéro de ligne |
| `-o` | n'affiche que la **partie qui matche** | `-A/-B/-C n` | n lignes après/avant/autour |
| `-w` | mot entier | `-E` | regex étendues (`+ ? \| ( )`) |
| `-q` | silencieux, sert au code de retour | `-F` | chaîne **fixe** — le plus rapide |

**Codes de retour** : `0` au moins une correspondance, `1` **aucune**, `2` erreur (fichier illisible).

> ⚠️ **PIÈGE** — Sous `set -e`, `grep -q ERROR "$log"` qui ne trouve rien renvoie 1 et **tue le script**.
> Écris `if grep -q ERROR "$log"; then …; fi` (contexte de condition, `set -e` désactivé) ou
> `grep -q ERROR "$log" || true`.

```bash
$ grep -c ' 500 ' access.log
137                                   # 137 réponses HTTP 500 (ici -c compte les LIGNES, pas les occurrences)
$ grep -oE '^[0-9]{1,3}(\.[0-9]{1,3}){3}' access.log | sort | uniq -c | sort -rn | head -3
   4821 10.42.0.17                    # l'IP la plus bavarde, 4821 requêtes
   1903 10.42.0.31
    884 10.42.1.2
```

### 9.2 `sed` — éditer un **flux**

```bash
sed 's/ancien/nouveau/g'       # /g = toutes les occurrences (sinon la 1re de chaque ligne)
sed 's#/data/v1#/data/v2#g'    # tout caractère peut servir de séparateur : utile pour les chemins
sed -n '2,5p'                  # -n = ne rien afficher, p = afficher : lignes 2 à 5
sed '1d'                       # supprimer l'en-tête CSV
sed '/^#/d; /^$/d'             # supprimer commentaires et lignes vides
sed -E 's/([0-9]{4})-([0-9]{2})/\2\/\1/'   # -E : ERE, groupes de capture \1 \2
sed -i.bak 's/foo/bar/g' f     # -i : en place. AVEC un suffixe de sauvegarde, toujours
sed '5q'                       # afficher jusqu'à la ligne 5 puis QUITTER (rapide sur gros fichier)
```

> ⚠️ **PIÈGE** — `sed -i` **n'est pas portable** : GNU accepte `sed -i 's/…/…/'`, BSD/macOS exige un
> argument `sed -i '' 's/…/…/'`. Dans un script destiné aux deux, utilise `sed … > tmp && mv tmp f`.
> Et rappelle-toi que `sed -i` **remplace l'inode** : les processus qui avaient le fichier ouvert
> continuent d'écrire dans l'ancien.

### 9.3 `awk` — le vrai langage du lot

`awk` découpe chaque ligne en **champs** et exécute `motif { action }`. C'est un langage complet avec
variables, tableaux associatifs et arithmétique **flottante** — ce que bash n'a pas.

| Variable | Sens | Variable | Sens |
|---|---|---|---|
| `$0` | la ligne entière | `NR` | numéro de ligne **global** |
| `$1 … $NF` | champ 1 … **dernier** | `FNR` | numéro de ligne dans **ce** fichier |
| `NF` | nombre de champs de la ligne | `FS`/`OFS` | séparateur entrée / sortie |

```bash
# 1. Somme et moyenne d'une colonne (CSV, montant en colonne 3)
$ awk -F, 'NR>1 {s+=$3; n++} END {printf "total=%.2f  moyenne=%.2f  lignes=%d\n", s, s/n, n}' ventes.csv
total=184203.55  moyenne=41.28  lignes=4462
#   -F,       séparateur virgule
#   NR>1      saute la ligne d'en-tête
#   END{}     bloc exécuté une fois, après la dernière ligne

# 2. Agrégation par clé : chiffre d'affaires par région (tableau associatif)
$ awk -F, 'NR>1 {ca[$2]+=$3} END {for (r in ca) printf "%-10s %10.2f\n", r, ca[r]}' ventes.csv | sort -k2 -rn
IDF          92417.30
PACA         41880.05
BRETAGNE     29906.20
#   ca[$2]    un "dictionnaire" indexé par la colonne 2. L'ordre de "for (r in ca)" est INDÉFINI -> on trie après

# 3. Contrôle qualité : lignes dont le nombre de colonnes est anormal
$ awk -F, 'NF != 7 {print FILENAME ":" FNR ": " NF " colonnes"}' /data/in/*.csv
/data/in/j-3.csv:8814: 6 colonnes      # une virgule manquante, ou un champ contenant une virgule non quotée

# 4. Jointure de deux fichiers (idiome NR==FNR, à connaître)
$ awk -F, 'NR==FNR {ref[$1]=$2; next} $1 in ref {print $0 "," ref[$1]}' referentiel.csv faits.csv
#   NR==FNR   vrai UNIQUEMENT pendant la lecture du 1er fichier -> on charge le référentiel en mémoire
#   next      passe à la ligne suivante sans exécuter la suite
#   2e fichier : on enrichit chaque ligne trouvée dans le référentiel

# 5. Filtrer sur une valeur numérique et reformater
$ awk -F'\t' -v OFS='\t' '$4 > 1000 {print $1, $4}' latences.tsv    # -v : passer une variable à awk
```

> ❓ **RETIENS ÇA** — Que fait la condition `NR==FNR` dans un `awk` à deux fichiers ?
> <details><summary>→ réponse</summary><br>Elle n'est vraie que pendant la lecture du <b>premier</b> fichier (<code>NR</code>, compteur global, et <code>FNR</code>, compteur du fichier courant, ne coïncident que là). C'est l'idiome standard pour <b>charger un référentiel en mémoire</b> puis enrichir/filtrer le second fichier — une jointure en une ligne.</details>

> 🧠 **MÉMO** — **awk = « pour chaque ligne, si (condition) alors {action} »**, avec deux blocs
> spéciaux : `BEGIN` avant la première ligne, `END` après la dernière. Tout le reste est du décor.

### 9.4 `sort`, `uniq`, `cut`, `tr`

```bash
sort -t, -k3,3nr fichier.csv    # -t, séparateur ; -k3,3 champ 3 SEUL ; n numérique ; r décroissant
sort -u                          # dédoublonne (lignes entières)
sort -h                          # tailles humaines (2K < 3M < 1G)
sort -s -k2,2                    # tri STABLE : conserve l'ordre initial à clé égale
LC_ALL=C sort                    # comparaison octet à octet : nettement plus rapide, ordre déterministe
sort -S 2G --parallel=8 -T /data/tmp   # gros fichiers : tampon, threads, répertoire temporaire
```

> ⚠️ **PIÈGE** — `sort -k3` ne trie **pas** sur le champ 3 : il trie « du champ 3 jusqu'à la fin de
> ligne ». Il faut `-k3,3`. Deuxième piège : `sort -u -k1,1` dédoublonne **par clé**, pas par ligne
> entière — il ne garde qu'une ligne par valeur du champ 1.

`uniq` ne voit que les lignes **adjacentes** : il exige une entrée **triée**.

```bash
sort f | uniq -c        # compter les occurrences
sort f | uniq -d        # n'afficher que les lignes en double
sort f | uniq -u        # n'afficher que les lignes uniques
```

```bash
cut -d, -f1,3 f.csv      # colonnes 1 et 3. NE SAIT PAS réordonner : -f3,1 sort quand même 1 puis 3
cut -d, -f2- f.csv       # de la 2 à la fin
cut -c1-8                # par caractères (dates ISO en début de ligne)

tr 'a-z' 'A-Z' < f       # translittérer
tr -d '\r' < f > f.unix  # supprimer les CR : LE correctif des CSV venus de Windows
tr -s ' '                # "squeeze" : compresse les espaces répétées
tr '\n' ',' < ids.txt    # transformer une colonne en liste séparée par des virgules
```

> ⚠️ **PIÈGE DATA** — `cut` et `awk -F,` **ne comprennent pas le CSV quoté**. Une ligne
> `12,"Dupont, Jean",42` a **4** champs pour eux, 3 pour un vrai parseur. Dès qu'un CSV contient des
> guillemets ou des virgules dans les champs, le shell n'est plus l'outil : passe à Python (`csv`,
> `pandas`) ou à `duckdb`/`csvkit`.

### 9.5 `jq` — le `awk` du JSON

```bash
$ curl -sS https://api.interne/hosts | jq -r '.items[] | select(.state=="UP") | .ip'
10.42.0.17
10.42.0.31
#   -r        raw : sans les guillemets JSON (indispensable pour alimenter un pipe)
#   .items[]  itère sur le tableau ; select() filtre

$ jq -r '.[] | [.name, .rx_bytes, .tx_bytes] | @tsv' stats.json > stats.tsv
#   @tsv      formate en TSV en échappant proprement -> pont JSON vers les outils texte
$ jq -c '.[]' gros.json > lignes.ndjson       # -c compact : 1 objet JSON par ligne (NDJSON)

$ ip -j addr show | jq -r '.[] | "\(.ifname) \(.operstate) \(.addr_info[0].local // "-")"'
lo UNKNOWN 127.0.0.1
eth0 UP 10.42.0.17
#   ip -j     iproute2 sort du JSON : fin du parsing fragile de texte pour l'inventaire réseau
#   //        opérateur "sinon" : valeur par défaut si null

$ jq --arg d "$(date -u +%F)" '.date = $d' modele.json    # injecter une variable shell SANS injection
$ jq -e '.status == "OK"' rep.json >/dev/null && echo ok   # -e : code 1 si la sortie est null/false
```

> ❓ **RETIENS ÇA** — À quoi sert `jq -r` et pourquoi est-ce presque toujours nécessaire dans un script ?
> <details><summary>→ réponse</summary><br><code>-r</code> = <i>raw output</i> : les chaînes sortent <b>sans guillemets</b>. Sans lui, une IP sort <code>"10.42.0.17"</code>, guillemets compris, et toute commande en aval (<code>ping</code>, <code>ssh</code>, comparaison) reçoit une valeur fausse.</details>

### 9.6 `find` et `xargs`

```bash
find /data/in -type f -name '*.csv' -mmin -60          # modifiés il y a MOINS de 60 minutes
find /data -type f -mtime +7 -delete                   # plus vieux que 7 jours (périodes de 24 h)
find /data -maxdepth 2 -type d -empty                  # -maxdepth AVANT les autres tests
find /data -type f -size +1G -printf '%s\t%p\n' | sort -rn | head
find /data -name '*.tmp' -newer /tmp/marqueur          # plus récent qu'un fichier témoin
find /data -type f -exec gzip {} \;                    # UN processus gzip PAR fichier (lent)
find /data -type f -exec gzip {} +                     # groupé : peu de processus (rapide)
find /data -type f -print0 | xargs -0 -P 8 -n 20 gzip  # groupé ET parallèle sur 8 cœurs
```

| Test `find` | Unité | Attention |
|---|---|---|
| `-mtime -1` | jours de **24 h** | `-mtime 0` = 0 à 24 h ; arrondi vers le bas |
| `-mmin -60` | **minutes** | la bonne granularité pour une fraîcheur horaire |
| `-size +1G` | `c` octets, `k`, `M`, `G` | sans suffixe = **blocs de 512 octets** |
| `-name` / `-iname` | motif glob | à **quoter** : sinon le shell le développe avant `find` |

`xargs` transforme une **liste sur stdin** en **arguments** :
`-0` entrées séparées par **NUL** (avec `find -print0`) · `-n K` K arguments par invocation ·
`-P N` N processus **en parallèle** · `-I {}` placeholder (1 argument par appel) ·
`-r` ne rien lancer sur une entrée **vide** · `-t` affiche la commande avant exécution.

> ⚠️ **PIÈGE** — `find … \| xargs cmd` sans `-print0`/`-0` casse sur le premier nom contenant une espace,
> une apostrophe ou un saut de ligne. Et sans `-r`, une liste vide lance quand même la commande une fois
> (`rm` sans argument → erreur ; `gzip` sans argument → **attend sur stdin**, ton cron se fige).

**Pourquoi `xargs` plutôt qu'une boucle ?** La limite `ARG_MAX` : `getconf ARG_MAX` vaut typiquement
**2 097 152 octets** (2 Mio) sur Linux. `rm /data/*.tmp` sur 300 000 fichiers rend
`Argument list too long`. `xargs` **découpe automatiquement** en plusieurs invocations sous la limite.

> ❓ **RETIENS ÇA** — Que signifie « Argument list too long » et quel outil règle le problème ?
> <details><summary>→ réponse</summary><br>La ligne de commande dépasse <code>ARG_MAX</code> (≈ 2 Mio sur Linux, <code>getconf ARG_MAX</code>). Le glob a produit trop d'arguments. Solution : <code>find … -print0 | xargs -0 cmd</code> (ou <code>find -exec cmd {} +</code>), qui découpe l'appel en plusieurs invocations sous la limite.</details>

---

## 10. Paralléliser

Trois niveaux, du plus simple au plus contrôlé.

```bash
# 1. xargs -P : pool de N workers. LA solution par défaut.
find /data/in -name '*.csv' -print0 | xargs -0 -P "$(nproc)" -n 1 ./traiter_un.sh

# 2. arrière-plan + wait : contrôle fin sur peu de tâches
for h in "${HOSTS[@]}"; do
    collecter "$h" > "/tmp/out.$h" &      # & = arrière-plan, PID dans $!
    pids+=("$!")
done
rc=0
for p in "${pids[@]}"; do wait "$p" || rc=1; done   # wait <pid> rend le code de CE job
exit "$rc"

# 3. GNU parallel : reprise, journal, formatage
parallel -j 8 --halt now,fail=1 --joblog /var/log/jobs.tsv ./traiter_un.sh ::: /data/in/*.csv
```

Points de vigilance :

- **`wait` sans argument** attend tous les jobs et retourne **0**, même si l'un a échoué. Pour détecter
  un échec, il faut `wait "$pid"` **job par job** (ou `wait -n`, bash ≥ 4.3, qui rend la main au premier
  job terminé).
- **Les écritures concurrentes dans un même fichier** ne sont sûres que pour des lignes < `PIPE_BUF`
  (**4096 octets** sur Linux) en mode ajout. Au-delà, les sorties s'entrelacent : fais écrire chaque
  worker dans **son** fichier, et concatène après.
- Le bon degré de parallélisme dépend du facteur limitant : **CPU** → `nproc` ; **disque/réseau** →
  souvent 2 à 4 × `nproc`, mais ça se mesure ; **base de données distante** → ce que le DBA autorise.

> ⚠️ **PIÈGE** — Paralléliser un job déjà limité par les I/O disque ne l'accélère pas, ça le ralentit :
> les têtes de lecture (ou la file du contrôleur NVMe) saturent, et le débit agrégé **baisse**. Mesure
> avant de multiplier.

---

## 11. Anatomie d'un script robuste et idempotent

**Idempotent** = le relancer produit le même état final, sans dégât. En data engineering, c'est
non négociable : un scheduler **relancera** ton script (retry automatique, reprise d'incident, backfill).

Les six propriétés à cocher :

| Propriété | Comment |
|---|---|
| **Entrées validées** | `${VAR:?message}`, tests `-d`/`-s`, format de date vérifié par regex |
| **Un seul exemplaire** | `flock` sur un fd |
| **Écriture atomique** | écrire dans `f.tmp` **sur le même système de fichiers**, puis `mv` |
| **Reprise sûre** | marqueur `_SUCCESS`, ou `mkdir -p`, ou `INSERT … ON CONFLICT` côté base |
| **Journal exploitable** | horodatage **UTC ISO 8601**, niveau, sur **stderr** |
| **Code de sortie parlant** | 0 / 2 usage / 3 données absentes / 75 réessayer plus tard |

**Pourquoi `mv` et pas une écriture directe ?** `rename(2)` est **atomique au sein d'un même système de
fichiers** : à aucun instant un lecteur ne voit un fichier à moitié écrit. Écrire directement dans
`/data/out/ventes.parquet` expose un fichier tronqué à tout job aval qui lit pendant ce temps — et un
crash au milieu laisse un fichier corrompu qui **a l'air** valide.

> ❓ **RETIENS ÇA** — Pourquoi écrit-on dans un fichier temporaire suivi d'un `mv` plutôt que directement dans le fichier cible ?
> <details><summary>→ réponse</summary><br>Parce que <code>rename()</code> est <b>atomique dans un même système de fichiers</b> : le consommateur voit soit l'ancien fichier complet, soit le nouveau complet, jamais un fichier partiel. Condition : le temporaire doit être sur <b>le même FS</b> que la cible, sinon <code>mv</code> fait copie + suppression, et l'atomicité est perdue.</details>

Le squelette complet, à recopier :

```bash
#!/usr/bin/env bash
#
# ingest.sh — ingère les CSV du jour vers /data/curated
# Usage : ingest.sh -d AAAA-MM-JJ [-n]   (SRC_DIR / DST_DIR par variables d'environnement)
#
set -Eeuo pipefail
IFS=$'\n\t'
shopt -s nullglob inherit_errexit

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly LOCK_FILE="/var/lock/$(basename "$0").lock"
readonly SRC_DIR="${SRC_DIR:-/data/in}"
readonly DST_DIR="${DST_DIR:-/data/curated}"

# --- journalisation : niveau + horodatage UTC, sur STDERR (stdout reste réservé aux données) ---
log() { printf '%s [%-5s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "${*:2}" >&2; }
die() { log ERROR "${*:2}"; exit "$1"; }

# --- nettoyage ---
TMPDIR_RUN=""
cleanup() {
    local rc=$?                              # capturer le code AVANT toute autre commande
    trap - EXIT INT TERM
    [[ -n "$TMPDIR_RUN" ]] && rm -rf "${TMPDIR_RUN:?}"
    log INFO "fin, code=$rc"
    exit "$rc"
}
trap cleanup EXIT INT TERM
trap 'log ERROR "échec ligne $LINENO : $BASH_COMMAND"' ERR

# --- arguments ---
jour=""; dry_run=0
while getopts ":d:nh" o; do case "$o" in
    d) jour="$OPTARG" ;;
    n) dry_run=1 ;;
    h) sed -n '2,4p' "$0"; exit 0 ;;         # l'en-tête du fichier SERT de page d'aide
    :) die 64 "option -$OPTARG : argument manquant" ;;
    \?) die 64 "option inconnue : -$OPTARG" ;;
esac; done

# --- validation des entrées : échouer TÔT et BRUYAMMENT ---
[[ "$jour" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || die 64 "date invalide : '$jour' (attendu AAAA-MM-JJ)"
[[ -d "$SRC_DIR" ]] || die 66 "source absente : $SRC_DIR"
command -v duckdb >/dev/null || die 69 "duckdb introuvable dans le PATH"
mkdir -p "$DST_DIR"                          # idempotent : pas d'erreur si déjà là

# --- exclusion mutuelle ---
exec 9>"$LOCK_FILE"
flock -n 9 || die 75 "une autre instance tourne (verrou $LOCK_FILE)"

# --- travail ---
TMPDIR_RUN="$(mktemp -d -p "$DST_DIR" .staging-XXXXXX)"   # MÊME FS que la cible -> mv atomique
fichiers=( "$SRC_DIR/$jour"/*.csv )
(( ${#fichiers[@]} > 0 )) || die 3 "aucun fichier pour $jour"
log INFO "${#fichiers[@]} fichier(s) à traiter"

marqueur="$DST_DIR/$jour/_SUCCESS"
if [[ -f "$marqueur" ]]; then
    log INFO "$jour déjà ingéré, rien à faire"      # <- L'IDEMPOTENCE EST ICI
    exit 0
fi

for f in "${fichiers[@]}"; do
    [[ -s "$f" ]] || { log WARN "fichier vide ignoré : ${f##*/}"; continue; }
    log INFO "traitement ${f##*/}"
    (( dry_run )) && continue
    duckdb -c "COPY (SELECT * FROM read_csv_auto('$f')) TO '$TMPDIR_RUN/${f##*/}.parquet' (FORMAT PARQUET)"
done

mkdir -p "$DST_DIR/$jour"
mv -- "$TMPDIR_RUN"/*.parquet "$DST_DIR/$jour/"   # publication atomique, fichier par fichier
touch "$marqueur"
log INFO "ingestion $jour terminée"
```

### 11.1 Le retry avec backoff exponentiel

Toute commande réseau doit être réessayée : un DNS lent, un 503 passager, une renégociation TLS.

```bash
retry() {
    local max="$1" delai="$2"; shift 2
    local n=1
    until "$@"; do
        (( n >= max )) && { log ERROR "échec définitif après $n tentatives : $*"; return 1; }
        log WARN "tentative $n/$max échouée, nouvel essai dans ${delai}s"
        sleep "$delai"
        delai=$(( delai * 2 ))         # 2, 4, 8, 16… (backoff exponentiel)
        n=$(( n + 1 ))
    done
}

retry 5 2 curl -fsS --max-time 30 -o "$TMPDIR_RUN/dump.json" https://api.interne/dump
```

`curl` a son propre mécanisme (`--retry 5 --retry-delay 2 --retry-max-time 120`), mais il ne couvre que
`curl` : la fonction générique sert aussi pour `spark-submit`, `psql`, `aws s3 cp`.

> 🧠 **MÉMO** — Les drapeaux `curl` d'un script : **`-fsS`** = **f**ail (erreur sur HTTP ≥ 400),
> **s**ilent (pas de barre de progression), **S**how errors (mais montre quand même les erreurs).
> Sans `-f`, `curl` écrit la page d'erreur 500 dans ton fichier de données et retourne **0**.

---

## 12. `shellcheck` : le relecteur qui ne dort jamais

`shellcheck` est un analyseur statique de scripts shell. Il n'est pas optionnel : il attrape en une
seconde ce qui te coûterait une nuit de production.

```bash
$ shellcheck ingest.sh
In ingest.sh line 42:
    for f in $(ls "$SRC_DIR"); do
             ^-- SC2045: Iterating over ls output is fragile. Use globs.
             ^-- SC2086: Double quote to prevent globbing and word splitting.
```

Les avertissements qui reviennent le plus, et ce qu'ils veulent dire :

| Code | Sens | Correctif |
|---|---|---|
| **SC2086** | variable non quotée → découpage + globbing | `"$var"` |
| **SC2046** | `$(…)` non quotée | `"$(cmd)"` |
| **SC2164** | `cd` sans garde | `cd "$d" \|\| exit 1` |
| **SC2155** | `local x=$(cmd)` masque le code retour | déclarer puis affecter |
| **SC2181** | `if [ $? -eq 0 ]` | tester la commande directement |
| **SC2115** | `rm -rf "$d/"` avec `$d` possiblement vide | `"${d:?}"` |
| **SC2059** | variable dans le **format** de `printf` | `printf '%s' "$v"` |
| **SC2045** | itérer sur la sortie de `ls` | utiliser un glob |
| **SC2006** | backticks | `$( )` |
| **SC1091** | fichier `source` non analysé | `shellcheck -x` |

Usage : `shellcheck -x -S warning script.sh` en CI (avec `-f gcc` pour un format lisible par les
annotations de PR). Désactivation ciblée, **avec justification**, juste au-dessus de la ligne :

```bash
# shellcheck disable=SC2086  # découpage voulu : $OPTS contient plusieurs options
spark-submit $OPTS job.py
```

> ❓ **RETIENS ÇA** — Que signale SC2086, l'avertissement shellcheck le plus fréquent ?
> <details><summary>→ réponse</summary><br>Une expansion <b>non quotée</b> : <code>$var</code> au lieu de <code>"$var"</code>. Elle expose la valeur au découpage en mots et au globbing (étapes 7 et 8), donc au bug quand la valeur contient une espace, une étoile ou est vide.</details>

---

## 13. Quand arrêter le bash

Le bash est excellent pour **orchestrer des processus**. Il est mauvais pour **manipuler des données**.
La frontière est nette, et savoir la nommer est une question d'entretien à part entière.

| Reste en bash | Passe à Python |
|---|---|
| Enchaîner des binaires, gérer codes de retour et signaux | Logique métier, branches imbriquées |
| Glob, `find`, déplacements de fichiers, verrous | Parsing **CSV quoté**, JSON profond, XML |
| Filtrage/agrégation ligne à ligne simple (`awk`) | Calcul flottant, dates/fuseaux, statistiques |
| Wrapper de `spark-submit`, `psql`, `aws` | Appels d'API paginés, gestion de tokens, retries typés |
| Moins de ~150 lignes, moins de 3 niveaux d'imbrication | Besoin de **tests unitaires** et de structures de données |

Les cinq signaux d'alarme, quand tu les vois, tu réécris :

1. Tu utilises `eval` ou des variables indirectes (`${!nom}`) pour simuler des structures.
2. Tu parses du JSON/CSV avec `sed`/`cut` parce que « jq/csv n'est pas installé ».
3. Tu as besoin de **flottants** (`bc -l`, `awk` en renfort partout).
4. Ton script dépasse **150-200 lignes** ou a **plus de 10 fonctions**.
5. Tu écris des dates avec de l'arithmétique manuelle sur les fuseaux.

> 🧠 **MÉMO** — **« Bash colle les processus, Python transforme les données. »** Si ton script passe plus
> de temps à *décider* qu'à *lancer*, il a changé de nature.

---

## 14. Trois scripts d'un data engineer, commentés

### 14.1 Vérification de fraîcheur (sonde d'alerte)

```bash
#!/usr/bin/env bash
set -Eeuo pipefail
# Sortie : 0 frais, 1 périmé, 3 source absente. Conçu pour être appelé par un check Nagios/Prometheus.
seuil_min="${2:-90}"
src="${1:?usage: fraicheur.sh <chemin> [minutes]}"

recent="$(find "$src" -type f -name '*.parquet' -mmin "-$seuil_min" -print -quit)"
#   -print -quit : s'arrête au PREMIER trouvé -> O(1) au lieu de parcourir 4 millions de fichiers

if [[ -n "$recent" ]]; then
    echo "OK - fichier récent : ${recent##*/}"; exit 0
fi

dernier="$(find "$src" -type f -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1)"
#   %T@ = mtime en secondes epoch (flottant) -> triable numériquement
[[ -z "$dernier" ]] && { echo "CRITICAL - aucune donnée dans $src"; exit 3; }

age_min=$(( ( $(date +%s) - ${dernier%%.*} ) / 60 ))
#   ${dernier%%.*} : coupe au premier point -> garde la partie entière de l'epoch
echo "CRITICAL - dernier fichier vieux de ${age_min} min (seuil ${seuil_min})"
exit 1
```

### 14.2 Wrapper `spark-submit`

```bash
#!/usr/bin/env bash
set -Eeuo pipefail
: "${APP:?variable APP requise}" "${JOUR:?variable JOUR requise}"   # validation en une ligne

log() { printf '%s [%s] %s\n' "$(date -u +%FT%TZ)" "$1" "${*:2}" >&2; }

args=(
  --master yarn --deploy-mode cluster
  --name "${APP}-${JOUR}"
  --conf spark.sql.shuffle.partitions="${PARTITIONS:-200}"
  --conf spark.dynamicAllocation.enabled=true
)
[[ -n "${QUEUE:-}" ]] && args+=(--queue "$QUEUE")

log INFO "lancement ${APP} pour ${JOUR}"
start=$SECONDS                                   # SECONDS : compteur interne bash, s'incrémente seul

set +e                                           # on veut analyser le code, pas mourir dessus
timeout --signal=TERM --kill-after=60 4h \
    spark-submit "${args[@]}" "/opt/jobs/${APP}.py" --date "$JOUR" \
    > >(tee "/var/log/${APP}-${JOUR}.out") 2>&1
rc=$?
set -e

duree=$(( SECONDS - start ))
case "$rc" in
    0)   log INFO  "succès en ${duree}s" ;;
    124) log ERROR "TIMEOUT après 4h — job tué"; exit 124 ;;
    137) log ERROR "SIGKILL (128+9) : OOM probable, augmente executor.memory / memoryOverhead"; exit 137 ;;
    143) log ERROR "SIGTERM (128+15) : préemption YARN ou arrêt demandé"; exit 143 ;;
    *)   log ERROR "échec spark-submit, code=$rc"; exit "$rc" ;;
esac
```

`timeout --signal=TERM --kill-after=60 4h` : au bout de 4 h, SIGTERM (le job peut se fermer proprement) ;
60 s après, SIGKILL. `timeout` retourne **124** quand il a dû intervenir.

### 14.3 Top des erreurs d'un log réseau, en une ligne

```bash
$ awk '$9 ~ /^5/ {print $1, $7}' access.log \
  | sort | uniq -c | sort -rn | head -5 \
  | awk '{printf "%6d  %-15s %s\n", $1, $2, $3}'
   842  10.42.0.17      /api/v2/ingest
   311  10.42.0.31      /api/v2/ingest
    97  10.42.1.2       /health
#   $9 ~ /^5/   colonne 9 du format combiné = code HTTP ; ^5 = toutes les 5xx
#   uniq -c     exige un tri préalable ; compte les couples (IP, URL) identiques
#   sort -rn    tri numérique décroissant sur le compteur produit par uniq
```

---

## 15. Exercices corrigés

### Exercice 1 — Dérouler les expansions

Soit `dir='/data in'`, `n=3`, et un répertoire `/data in/` contenant `a1.csv` et `a2.csv`.
Que reçoit `cp` dans `cp $dir/a*.csv /backup$((n))` ?

**Correction, étape par étape** :

1. Accolades : rien.
2. Tilde : rien.
3. Paramètres : `$dir` → `/data in`. La ligne devient `cp /data in/a*.csv /backup$((n))`.
4. Arithmétique : `$((n))` → `3`. → `cp /data in/a*.csv /backup3`.
5-6. Substitutions : rien.
7. **Découpage** (non quoté !) : `/data` et `in/a*.csv` deviennent **deux mots distincts**.
8. **Globbing** : `/data` n'est pas un motif → littéral. `in/a*.csv` est un motif relatif au répertoire
   courant → aucune correspondance → **laissé littéral**.
9. Quotes : rien à retirer.

`cp` reçoit donc `argv = [cp, /data, in/a*.csv, /backup3]` : **deux** sources au lieu de deux fichiers
attendus, et toutes deux inexistantes. Sortie réelle (avec `/backup3` déjà créé) :

```
cp: cannot stat '/data': No such file or directory
cp: cannot stat 'in/a*.csv': No such file or directory
```

Si `/backup3` n'existe pas, l'erreur est encore plus déroutante — `cp: target '/backup3': No such file
or directory` — parce que `cp` reçoit **3 arguments** et exige alors que le dernier soit un répertoire.

**Forme correcte** : `cp "$dir"/a*.csv "/backup$n"`. Le glob doit rester **hors** des guillemets pour
être développé, la variable **dedans** pour être protégée.

### Exercice 2 — Débit moyen par interface

Fichier `debits.tsv` (tabulations), colonnes : `horodatage  interface  octets_rx  octets_tx`.

```
2026-09-09T10:00:00Z	eth0	120000000	8400000
2026-09-09T10:00:10Z	eth0	138000000	9100000
2026-09-09T10:00:00Z	eth1	4000000	3900000
2026-09-09T10:00:10Z	eth1	4200000	4050000
```

**Question** : débit moyen en **Mbit/s** par interface, sachant que chaque ligne couvre un intervalle de
**10 s** et que les valeurs sont des octets transférés pendant l'intervalle.

```bash
awk -F'\t' '{ tot[$2] += $3 + $4 ; n[$2]++ }
            END { for (i in tot) printf "%-6s %8.2f Mbit/s\n", i, (tot[i]*8)/(n[i]*10)/1e6 }' debits.tsv
```

**Raisonnement** :
1. `tot[$2] += $3+$4` : somme des octets (rx + tx) par interface.
2. `n[$2]++` : nombre d'intervalles observés par interface.
3. Durée totale = `n[i] × 10` secondes.
4. Octets → bits : `× 8`. Bits/s → Mbit/s : `/ 1e6`.

**Vérification à la main pour `eth0`** : `(120 000 000 + 8 400 000) + (138 000 000 + 9 100 000)
= 128 400 000 + 147 100 000 = 275 500 000` octets sur `2 × 10 = 20` s.
`275 500 000 × 8 = 2 204 000 000` bits / 20 s = `110 200 000` bit/s = **110,20 Mbit/s**.

Pour `eth1` : `7 900 000 + 8 250 000 = 16 150 000` octets → `× 8 = 129 200 000` bits / 20 s
= `6 460 000` bit/s = **6,46 Mbit/s**.

Sortie :
```
eth0     110.20 Mbit/s
eth1       6.46 Mbit/s
```

### Exercice 3 — Trouver le bug

```bash
#!/usr/bin/env bash
set -euo pipefail
compte=0
for f in /data/in/*.csv; do
    lignes=$(wc -l < "$f")
    grep -q ERROR "$f" && echo "erreurs dans $f"
    ((compte++))
done
echo "$compte fichiers"
```

Ce script sort **silencieusement** au premier fichier, sans message. Trois défauts :

1. **`((compte++))`** : `compte` vaut 0, le **post**-incrément renvoie l'ancienne valeur 0, `(( ))`
   retourne alors le code **1**, et `set -e` termine le script. → `compte=$((compte+1))`.
2. **`grep -q … && echo`** : la partie gauche d'un `&&` est exemptée de `set -e`, donc ce n'est pas là
   que ça casse — mais si la ligne était `grep -q ERROR "$f"` seule, un fichier sans « ERROR » (code 1)
   tuerait le script. Il faut la mettre en condition `if`.
3. **Pas de `nullglob`** : si `/data/in/` ne contient aucun `.csv`, la boucle tourne **une fois** avec
   `f='/data/in/*.csv'`, et `wc -l < "$f"` échoue sur un fichier inexistant. → `shopt -s nullglob`.

Version corrigée :

```bash
#!/usr/bin/env bash
set -Eeuo pipefail
shopt -s nullglob
compte=0
for f in /data/in/*.csv; do
    lignes=$(wc -l < "$f")
    if grep -q ERROR "$f"; then echo "erreurs dans $f ($lignes lignes)"; fi
    compte=$((compte + 1))
done
echo "$compte fichiers"
```

### Exercice 4 — Lire un code de sortie

Un job affiche `ExecutorLost` puis le wrapper shell rend **137**, un autre rend **124**, un troisième
**127**. Diagnostic ?

- **137** = 128 + 9 = **SIGKILL**. Personne ne l'a rattrapé : OOM killer du cgroup dans 90 % des cas.
  On regarde `dmesg | grep -i oom` et `memory.max`.
- **124** = code réservé de **`timeout`** : le job a dépassé le délai imposé par le wrapper. Le job n'a
  pas « échoué », il a été **coupé** ; augmenter le délai ou optimiser.
- **127** = **commande introuvable** : `spark-submit` absent du `PATH` du contexte d'exécution (cron a un
  `PATH` minimal, typiquement `/usr/bin:/bin`). Correctif : chemin absolu, ou `PATH=` explicite en tête
  de crontab.

---

## 16. Questions d'entretien

**1. Pourquoi faut-il quoter les variables en bash ?**
Parce que l'expansion d'une variable est suivie, dans l'ordre d'évaluation, du découpage en mots sur
`IFS` puis du globbing. Une variable non quotée contenant une espace devient plusieurs arguments ; une
variable contenant `*` est développée sur le répertoire courant ; une variable vide **disparaît**,
décalant les arguments suivants. `rm $f` avec `f='mon fichier.csv'` tente d'effacer deux fichiers. Les
guillemets doubles inhibent exactement ces deux étapes, tout en laissant l'expansion se faire. La règle
opérationnelle : tout ce qui sort d'un `$` va entre guillemets, sauf découpage volontaire documenté.

**2. Que fait `set -euo pipefail`, et pourquoi n'est-ce pas suffisant ?**
`-e` quitte à la première commande en échec, `-u` transforme une variable non définie en erreur,
`-o pipefail` fait qu'un pipeline échoue si **n'importe quel** maillon échoue. Ce n'est pas suffisant
parce que `-e` a des angles morts documentés : conditions de `if`/`while`, opérandes de `&&`/`||`,
commandes précédées de `!`, substitutions de commande (sans `inherit_errexit`), et affectations avec
`local`/`export` qui masquent le code de retour. On complète avec `set -E` + `trap … ERR` pour tracer,
`shopt -s inherit_errexit`, et surtout des tests explicites sur les points critiques.

**3. Différence entre `[` et `[[` ?**
`[` est une commande (builtin, doublée d'un binaire `/usr/bin/[`) : ses arguments subissent le découpage
et le globbing, d'où les erreurs de syntaxe sur variable vide et l'obligation de tout quoter. `[[` est un
mot-clé analysé par bash : pas de découpage, pas de globbing sur les variables, opérateurs `&&`/`||`,
comparaison de motifs avec `==` et regex avec `=~`. En bash on utilise `[[`. On garde `[` uniquement
pour du POSIX `sh` (dash, images Alpine).

**4. Comment garantir qu'une seule instance d'un script tourne ?**
`flock` sur un descripteur de fichier : `exec 9>/var/lock/x.lock ; flock -n 9 || exit 75`. Le verrou est
détenu par le **descripteur**, donc le noyau le libère automatiquement à la mort du processus, y compris
sur `kill -9`, panne ou OOM. Un fichier PID est une mauvaise réponse : il y a une course entre le test
d'existence et la création, et un crash laisse un verrou fantôme qui bloque définitivement les
exécutions suivantes.

**5. Comment rendre un script d'ingestion idempotent ?**
Trois leviers. D'abord des opérations naturellement idempotentes : `mkdir -p`, `rsync`, `INSERT … ON
CONFLICT DO NOTHING`, partitionnement par date avec écrasement complet de la partition. Ensuite un
**marqueur de succès** (`_SUCCESS` par partition) testé en tête de script pour sortir en 0 sans rien
refaire. Enfin l'**écriture atomique** : on produit dans un répertoire de staging **sur le même système
de fichiers**, puis on publie par `mv` — `rename()` est atomique, donc aucun consommateur ne voit un
fichier partiel, et un crash en cours de route ne laisse que du staging jetable.

**6. Que se passe-t-il exactement dans `cat f | while read l; do n=$((n+1)); done` et pourquoi `n` vaut 0 après ?**
Chaque maillon d'un pipeline s'exécute dans un **sous-shell** (un `fork()`). La boucle `while` modifie
`n` dans ce processus fils ; les variables ne remontent jamais vers le parent. À la fin du pipeline, le
fils meurt avec sa valeur. Trois correctifs : rediriger le fichier directement (`done < f`), utiliser une
substitution de processus (`done < <(cmd)`) qui laisse la boucle dans le shell courant, ou activer
`shopt -s lastpipe` qui fait tourner le dernier maillon dans le shell courant.

**7. Comment comptes-tu les 10 IP les plus fréquentes dans un log de 50 Go ?**
`awk '{print $1}' access.log | LC_ALL=C sort -S 4G -T /data/tmp | uniq -c | sort -rn | head -10`.
`awk` extrait la colonne sans charger le fichier ; `LC_ALL=C` supprime le coût de collation locale et
donne un ordre déterministe ; `-S` fixe le tampon mémoire et `-T` un répertoire temporaire assez grand,
car `sort` bascule sur disque avec des fusions externes. `uniq -c` exige l'entrée triée. Si le nombre
d'IP distinctes tient en mémoire, `awk '{c[$1]++} END{for(i in c) print c[i], i}' | sort -rn | head` est
plus rapide : un seul passage, pas de tri du volume total.

**8. `2>&1 > f` et `> f 2>&1` : quelle différence ?**
Les redirections sont appliquées **de gauche à droite**, et `2>&1` signifie « fais pointer le
descripteur 2 vers ce que 1 désigne **à cet instant** ». Dans `2>&1 > f`, stderr est dupliqué vers le
terminal (position actuelle de stdout), puis stdout part vers le fichier : les erreurs restent à
l'écran. Dans `> f 2>&1`, stdout va d'abord dans le fichier, puis stderr copie cette destination : tout
atterrit dans le fichier. C'est une copie de destination, pas un alias vivant.

**9. Quand arrêtes-tu le bash pour passer à Python ?**
Quand le script cesse d'orchestrer pour commencer à transformer. Concrètement : dès qu'il faut parser du
CSV quoté ou du JSON imbriqué, faire du calcul flottant ou des dates avec fuseaux, gérer des retries
typés sur une API paginée, ou dès que le script dépasse ~150 lignes et qu'il aurait besoin de tests
unitaires. Bash reste imbattable pour enchaîner des binaires, gérer signaux, codes de retour, globs et
verrous — c'est-à-dire pour la **couche d'exécution**, pas pour la **logique**.

**10. À quoi sert `trap`, et que ne peut-il pas attraper ?**
`trap CMD SIGNAL` installe un handler exécuté à la réception d'un signal ou sur des pseudo-événements
shell : `EXIT` (fin du script, quelle qu'en soit la cause), `ERR` (commande en échec, avec `$LINENO` et
`$BASH_COMMAND` pour la trace). C'est ainsi qu'on garantit la suppression des temporaires et la
libération des ressources. Deux signaux échappent à tout handler : **SIGKILL (9)** et **SIGSTOP (19)**,
traités directement par le noyau — donc un script tué par l'OOM killer ne nettoiera jamais, et il faut
un filet côté système (staging jetable, verrou `flock`).

---

## Les 3 choses à retenir si tu ne retiens que ça

1. **Le shell transforme ta ligne avant de l'exécuter, et le découpage en mots + le globbing arrivent
   APRÈS le remplacement des variables.** D'où l'unique règle qui élimine la majorité des bugs :
   **tout ce qui sort d'un `$` va entre guillemets doubles**.

2. **`set -Eeuo pipefail` + `IFS=$'\n\t'` en tête, `trap cleanup EXIT INT TERM` juste après, `flock` sur
   un descripteur pour l'unicité.** Et connais les angles morts de `set -e` — `local x=$(cmd)`,
   `((i++))`, les conditions — parce qu'un script qui échoue en silence est pire qu'un script qui plante.

3. **En data engineering, publie toujours par écriture atomique** : staging sur le **même système de
   fichiers**, puis `mv`, plus un marqueur `_SUCCESS` qui rend le script rejouable. Le vrai risque du
   bash n'est pas le plantage, c'est la **réussite partielle** qui empoisonne le lac de données.
