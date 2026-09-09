#!/usr/bin/env bash
# Valide les flashcards et construit les decks Anki par famille.
#   ./outils/anki.sh valider   -> contrôle le format TSV de toutes les cartes
#   ./outils/anki.sh build     -> génère outils/decks/*.tsv, un par famille
set -euo pipefail
cd "$(dirname "$0")/.."

declare -A FAM=( [R]="Reseau" [D]="DevOps" [T]="Data" [A]="IA" [L]="Langages" )

valider() {
  local ko=0 total=0
  for f in flashcards/*.tsv; do
    [ -e "$f" ] || { echo "Aucune flashcard."; return 0; }
    local n bad
    n=$(wc -l < "$f")
    bad=$(awk -F'\t' 'NF!=2 || $1=="" || $2=="" {c++} END{print c+0}' "$f")
    total=$((total + n))
    if [ "$bad" -ne 0 ]; then
      printf '  ✗ %-24s %3d cartes, %d ligne(s) mal formée(s)\n' "$f" "$n" "$bad"
      awk -F'\t' 'NF!=2 || $1=="" || $2=="" {printf "      L%d: %s\n", NR, substr($0,1,70)}' "$f"
      ko=$((ko + 1))
    else
      printf '  ✓ %-24s %3d cartes\n' "$f" "$n"
    fi
  done
  echo
  echo "  $total cartes au total, $ko fichier(s) en erreur"
  [ "$ko" -eq 0 ]
}

build() {
  mkdir -p outils/decks
  for prefixe in "${!FAM[@]}"; do
    local sortie="outils/decks/Palais-${FAM[$prefixe]}.tsv"
    local sources=(flashcards/${prefixe}[0-9][0-9].tsv)
    [ -e "${sources[0]}" ] || continue
    cat "${sources[@]}" > "$sortie"
    printf '  %-32s %3d cartes  (%d modules)\n' "$sortie" "$(wc -l < "$sortie")" "${#sources[@]}"
  done
  echo
  echo "  Import Anki : Fichier > Importer, type de note « Basique », séparateur « Tabulation »."
}

case "${1:-valider}" in
  valider) echo "Validation des flashcards"; echo; valider ;;
  build)   echo "Construction des decks"; echo; valider >/dev/null && build ;;
  *)       echo "Usage: $0 {valider|build}" >&2; exit 1 ;;
esac
