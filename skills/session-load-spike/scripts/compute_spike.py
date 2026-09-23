#!/usr/bin/env python3
"""
compute_spike.py — Spike de charge d'une séance vs plus longue sortie des 30 jours.

Objectif
--------
Implémente la métrique "session-specific spike" publiée dans :

    Nielsen R. et al., "How much running is too much? Identifying high-risk
    running sessions in a 5205-runner cohort study", British Journal of
    Sports Medicine 2025;59(17):1203.
    https://bjsm.bmj.com/content/59/17/1203

Méthodologie du papier
-----------------------
    ratio = distance de la séance du jour / plus longue distance parmi les
            séances des 30 jours PRÉCÉDENTS (jour courant exclu)

Catégories et hazard ratio de blessure de surcharge (overuse injury) associés :

    Référence        ratio <= 1.10   (régression ou hausse <= 10%)   HRR = 1 (référence)
    Spike faible      1.10 < ratio <= 1.30                            HRR = 1.64
    Spike modéré      1.30 < ratio <= 2.00                            HRR = 1.52
    Spike important    ratio > 2.00                                   HRR = 2.28

Le papier ne trouve PAS de relation dose-réponse pour le ratio de charge
hebdomadaire acute:chronic (ACWR) classique ni pour le ratio semaine-à-semaine :
c'est la distance de la séance UNIQUE, comparée à la plus longue sortie récente,
qui est le meilleur prédicteur — pas le volume hebdomadaire total.

Le script travaille sur les fichiers Markdown déjà persistés dans `activities/`
(convention `YYYY-MM-DD_type.md`, bloc `## Données brutes Garmin (référence)`
contenant `distance_meters` et `type`). Conçu pour être piloté par l'agent coach
AVANT de pousser une séance running/trail planifiée au calendrier Garmin
(voir le skill `session-load-spike`).

Usage
-----
    python3 skills/session-load-spike/scripts/compute_spike.py \
        --date 2026-09-28 \
        --distance-km 24 \
        --dir activities/

Paramètres
----------
    --date          Date de la séance évaluée (YYYY-MM-DD). Défaut : aujourd'hui.
    --distance-km   Distance prévue/réelle de la séance évaluée, en km (requis).
    --dir           Dossier des activités (défaut activities/)
    --types         Types de séance comptant pour la baseline (défaut : running,trail)
    --window-days   Taille de la fenêtre de lookback en jours (défaut 30, per papier)
    --json          Fichier JSON de sortie (dump structuré, réutilisable)
    --quiet         Sortie minimale (une ligne)

Prérequis
---------
- Python 3.8+ (stdlib uniquement, aucune dépendance externe)
- Distance lue par ordre de préférence : bloc ```arc (contrat de données,
  `distance_m`/`sport` — voir le skill `workspace-data-contract`), puis bloc
  YAML legacy `## Données brutes Garmin (référence)` (`distance_meters`/
  `type`), puis ligne `| Distance | X,XX km |` du tableau résumé. Un fichier
  sans aucune de ces sources est ignoré silencieusement.
"""

import argparse
import glob
import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional


FILENAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_([a-z_]+)\.md$")
ARC_BLOCK_RE = re.compile(r"```arc\s*\n(\{.*?\})\s*\n```", re.DOTALL)
YAML_DISTANCE_RE = re.compile(r"distance_meters:\s*([\d.]+)")
YAML_TYPE_RE = re.compile(r"^type:\s*(\w+)", re.MULTILINE)
TABLE_DISTANCE_RE = re.compile(r"\|\s*Distance\s*\|\s*([\d,.]+)\s*km\s*\|")


def parse_activity_file(path: str) -> Optional[Dict[str, Any]]:
    """Extrait {date, type, distance_km} d'un fichier MD d'activité, ou None si illisible.

    Ordre de préférence : bloc ```arc (contrat de données, `distance_m`/`sport`)
    → bloc YAML legacy (`distance_meters`/`type`) → ligne de tableau résumé.
    """
    basename = os.path.basename(path)
    m = FILENAME_RE.match(basename)
    if not m:
        return None
    file_date_str, file_type = m.group(1), m.group(2)
    try:
        file_date = datetime.strptime(file_date_str, "%Y-%m-%d").date()
    except ValueError:
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return None

    activity_type = file_type
    distance_km = None

    arc_match = ARC_BLOCK_RE.search(content)
    if arc_match:
        try:
            arc = json.loads(arc_match.group(1))
        except json.JSONDecodeError:
            arc = None
        if arc and arc.get("kind") == "activity":
            if arc.get("sport"):
                activity_type = arc["sport"]
            if arc.get("distance_m") is not None:
                distance_km = float(arc["distance_m"]) / 1000.0

    if distance_km is None:
        type_match = YAML_TYPE_RE.search(content)
        if type_match:
            activity_type = type_match.group(1)
        dist_match = YAML_DISTANCE_RE.search(content)
        if dist_match:
            distance_km = float(dist_match.group(1)) / 1000.0
        else:
            table_match = TABLE_DISTANCE_RE.search(content)
            if table_match:
                distance_km = float(table_match.group(1).replace(",", "."))

    if distance_km is None:
        return None

    return {
        "date": file_date,
        "type": activity_type,
        "distance_km": distance_km,
        "file": basename,
    }


def collect_window(activities_dir: str, target_date: date, window_days: int, types: List[str]) -> List[Dict[str, Any]]:
    """Séances des `window_days` jours précédant `target_date` (jour courant exclu), filtrées par type."""
    window_start = target_date - timedelta(days=window_days)
    results = []
    for path in glob.glob(os.path.join(activities_dir, "*.md")):
        parsed = parse_activity_file(path)
        if not parsed:
            continue
        if parsed["type"] not in types:
            continue
        if not (window_start <= parsed["date"] < target_date):
            continue
        results.append(parsed)
    return sorted(results, key=lambda a: a["date"])


def categorize(ratio: float) -> Dict[str, Any]:
    """Catégorise le ratio de spike selon les seuils du papier BJSM 2025;59(17):1203."""
    if ratio <= 1.10:
        return {"label": "Référence", "emoji": "🟢", "hrr": "1 (référence)", "min": None, "max": 1.10}
    if ratio <= 1.30:
        return {"label": "Spike faible", "emoji": "🟡", "hrr": "1.64 (IC95% 1.31–2.05)", "min": 1.10, "max": 1.30}
    if ratio <= 2.00:
        return {"label": "Spike modéré", "emoji": "🟠", "hrr": "1.52 (IC95% 1.16–2.00)", "min": 1.30, "max": 2.00}
    return {"label": "Spike important", "emoji": "🔴", "hrr": "2.28 (IC95% 1.50–3.48)", "min": 2.00, "max": None}


def format_report(target_date: date, distance_km: float, window_days: int,
                   window_activities: List[Dict[str, Any]], quiet: bool) -> str:
    if not window_activities:
        return (
            f"🟢 Spike de charge — {target_date.isoformat()} : baseline insuffisante "
            f"(aucune séance course/trail dans les {window_days} jours précédents). "
            "Vérification impossible, pas de signal à reporter."
        )

    longest = max(window_activities, key=lambda a: a["distance_km"])
    ratio = distance_km / longest["distance_km"] if longest["distance_km"] > 0 else float("inf")
    cat = categorize(ratio)

    if quiet:
        return (
            f"{cat['emoji']} {cat['label']} ({ratio:.2f}×) — "
            f"{distance_km:.1f} km vs {longest['distance_km']:.1f} km le {longest['date'].isoformat()}"
        )

    lines = [
        f"## Spike de charge — séance du {target_date.isoformat()}",
        "",
        f"**Distance évaluée** : {distance_km:.2f} km",
        f"**Plus longue sortie des {window_days} derniers jours** : {longest['distance_km']:.2f} km "
        f"({longest['date'].isoformat()}, `{longest['file']}`)",
        f"**Ratio** : {ratio:.2f}×",
        f"**Catégorie** : {cat['emoji']} **{cat['label']}** "
        f"(hazard ratio blessure de surcharge ≈ {cat['hrr']} — Nielsen et al., BJSM 2025;59(17):1203)",
        "",
    ]
    if cat["label"] != "Référence":
        lines.append(
            "> ⚠️ Ce spike augmente le risque de blessure de surcharge selon l'étude "
            "de référence. Signal ADVISORY (non bloquant) — ne pas annuler la séance "
            "automatiquement, mais le mentionner explicitement dans la validation et "
            "envisager une progression plus douce si le contexte de récupération "
            "(HRV, FC repos, historique blessures) est déjà chargé."
        )
    else:
        lines.append("Progression dans la zone de référence — aucun signal à reporter.")

    lines.append("")
    lines.append(f"_{len(window_activities)} séance(s) course/trail considérée(s) dans la fenêtre de {window_days} jours._")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--date", default=None, help="Date de la séance évaluée (YYYY-MM-DD). Défaut : aujourd'hui.")
    parser.add_argument("--distance-km", type=float, required=True, help="Distance prévue/réelle de la séance, en km.")
    parser.add_argument("--dir", default="activities", help="Dossier des activités (défaut activities/).")
    parser.add_argument("--types", default="running,trail", help="Types de séance comptant pour la baseline (défaut running,trail).")
    parser.add_argument("--window-days", type=int, default=30, help="Fenêtre de lookback en jours (défaut 30).")
    parser.add_argument("--json", default=None, help="Fichier JSON de sortie (dump structuré).")
    parser.add_argument("--quiet", action="store_true", help="Sortie minimale (une ligne).")
    args = parser.parse_args()

    target_date = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else date.today()
    types = [t.strip() for t in args.types.split(",") if t.strip()]

    window_activities = collect_window(args.dir, target_date, args.window_days, types)
    report = format_report(target_date, args.distance_km, args.window_days, window_activities, args.quiet)
    print(report)

    if args.json:
        longest = max(window_activities, key=lambda a: a["distance_km"]) if window_activities else None
        ratio = (args.distance_km / longest["distance_km"]) if longest and longest["distance_km"] > 0 else None
        payload = {
            "target_date": target_date.isoformat(),
            "distance_km": args.distance_km,
            "window_days": args.window_days,
            "longest_in_window_km": longest["distance_km"] if longest else None,
            "longest_in_window_date": longest["date"].isoformat() if longest else None,
            "ratio": ratio,
            "category": categorize(ratio)["label"] if ratio is not None else None,
            "window_activities": [
                {"date": a["date"].isoformat(), "type": a["type"], "distance_km": a["distance_km"], "file": a["file"]}
                for a in window_activities
            ],
        }
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    return 0


if __name__ == "__main__":
    sys.exit(main())
