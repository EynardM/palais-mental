#!/usr/bin/env python3
"""Régénère le calendrier de rappel espacé de PROGRESSION.md.

Lit la colonne « Vu le » de chaque module et replace la table située entre
les marqueurs RAPPELS:DEBUT et RAPPELS:FIN. Le reste du fichier — niveaux,
notes, cases cochées — n'est pas touché.

    ./outils/rappels.py            met à jour PROGRESSION.md
    ./outils/rappels.py --dry-run  affiche sans écrire
"""
import datetime, pathlib, re, sys

ECARTS = (1, 3, 7, 14)
FIN = datetime.date(2026, 9, 29)          # dernier jour avant la prise de poste
JOURS = ("Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim")
LIGNE = re.compile(r"^\| `([A-Z]\d\d)` \|[^|]*\|[^|]*\|[^|]*\|([^|]*)\|", re.M)

racine = pathlib.Path(__file__).resolve().parent.parent
cible = racine / "PROGRESSION.md"
texte = cible.read_text()


def parse_date(brut):
    """« 10/09 » ou « 2026-09-10 » -> date. None si vide ou illisible."""
    brut = brut.strip()
    for motif in ("%d/%m", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            d = datetime.datetime.strptime(brut, motif).date()
            return d.replace(year=2026) if motif == "%d/%m" else d
        except ValueError:
            continue
    return None


vus = [(mid, d) for mid, brut in LIGNE.findall(texte) if (d := parse_date(brut))]

rappels = {}
for mid, vu in vus:
    for ecart in ECARTS:
        jour = vu + datetime.timedelta(days=ecart)
        if jour <= FIN:
            rappels.setdefault(jour, []).append(f"`{mid}(J+{ecart})`")

lignes = ["| Date | Rappels du jour | Fait |", "|---|---|---|"]
if vus:
    debut = min(datetime.date.today(), min(d for _, d in vus) + datetime.timedelta(days=1))
    jour = debut
    while jour <= FIN:
        contenu = " · ".join(rappels.get(jour, [])) or "_(rien)_"
        lignes.append(f"| **{JOURS[jour.weekday()]} {jour:%d/%m}** | {contenu} | |")
        jour += datetime.timedelta(days=1)
else:
    lignes.append('| — | _Aucun module traité : renseigne la colonne « Vu le »._ | |')

table = "\n".join(lignes)
nouveau = re.sub(r"<!-- RAPPELS:DEBUT -->.*?<!-- RAPPELS:FIN -->",
                 lambda _: f"<!-- RAPPELS:DEBUT -->\n{table}\n<!-- RAPPELS:FIN -->", texte, flags=re.S)

if "RAPPELS:DEBUT" not in texte:
    sys.exit("Marqueurs RAPPELS:DEBUT / RAPPELS:FIN introuvables dans PROGRESSION.md")

if "--dry-run" in sys.argv:
    print(table)
else:
    cible.write_text(nouveau)

total = sum(len(v) for v in rappels.values())
print(f"{len(vus)} module(s) traité(s) → {total} rappel(s) programmé(s) jusqu'au {FIN:%d/%m}")
for mid, d in vus:
    echeances = ", ".join(f"{d + datetime.timedelta(days=e):%d/%m}" for e in ECARTS
                          if d + datetime.timedelta(days=e) <= FIN)
    print(f"  {mid}  vu le {d:%d/%m}  →  {echeances}")
