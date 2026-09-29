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

Dimensions trail (EXPLORATOIRES — seuils non validés)
-----------------------------------------------------
Le papier ne mesure que la distance. Pour un traileur, trois dimensions
complémentaires sont calculées avec la même logique (séance / maximum de la même
dimension sur les 30 jours précédents) et les mêmes seuils, **extrapolés** :

    km-effort   distance équivalente plat : chaque split est décomposé en une
                partie montante et une partie descendante (magnitude de pente
                commune (D+ + D-) / distance), pondérées par le coût énergétique
                de la course selon la pente (Minetti et al., J Appl Physiol
                2002;93:1039) — la descente comptant au moins comme du plat —,
                × coefficient de terrain (`terrain`).
    descente    D- pondéré ×1.5 sur les pentes descendantes > 10 % : charge
                excentrique, que le coût énergétique ignore (la descente est
                « bon marché » métaboliquement mais la plus traumatisante).
    sRPE        effort perçu × durée en minutes (Foster) : charge interne, intègre
                allure, technicité, chaleur et fatigue.

La part de marche (`walk_duration_s`) est affichée en contexte seulement : en
pente raide, marcher et courir ont un coût énergétique proche, aucune
pondération validée n'existe.

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
    --distance-km   Distance prévue/réelle de la séance évaluée, en km (requis sauf --from-file).
    --from-file     Fichier MD d'une séance réalisée : date, distance, D+/D-, splits,
                    durée, RPE et terrain lus dans son bloc ```arc.
    --elevation-gain-m / --elevation-loss-m
                    D+ / D- prévus (séance planifiée ; D- = D+ par défaut, boucle).
    --duration-min  Durée prévue, en minutes (pour la sRPE).
    --rpe           Effort perçu prévu ou déclaré, 0-10 (pour la sRPE).
    --terrain       route | chemin | single | technique | hors_sentier.
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

# Coefficient de technicité appliqué au km-effort. Ordre de grandeur : terrain
# irrégulier ≈ +5 % de coût énergétique (Voloshina & Ferris, J Exp Biol
# 2015;218:711) ; au-delà, extrapolé des facteurs de terrain de la marche
# (Soule & Goldman 1972 / Pandolf 1977 : 1.0 bitume → 1.2 broussaille).
TERRAIN_FACTORS = {
    "route": 1.00,
    "chemin": 1.05,
    "single": 1.10,
    "technique": 1.20,
    "hors_sentier": 1.30,
}
# Terrain supposé quand `terrain` est absent du bloc arc.
DEFAULT_TERRAIN = {"running": "route", "trail": "chemin"}

STEEP_DOWNHILL_GRADE = 0.10
STEEP_DOWNHILL_WEIGHT = 1.5

DIMENSIONS = {
    # clé : (libellé, unité, format)
    "effort_km": ("km-effort", "km-effort", "{:.1f}"),
    "eccentric_m": ("descente", "m D- pondéré", "{:.0f}"),
    "srpe": ("sRPE", "UA", "{:.0f}"),
}


def minetti_cost(grade: float) -> float:
    """Coût énergétique de la course (J·kg⁻¹·m⁻¹) selon la pente — Minetti et al. 2002.

    Polynôme ajusté sur −45 %…+45 % ; la pente est bornée à cet intervalle.
    """
    i = max(-0.45, min(0.45, grade))
    return 155.4 * i**5 - 30.4 * i**4 - 43.3 * i**3 + 46.3 * i**2 + 19.5 * i + 3.6


def _decompose(distance_m: float, gain_m: float, loss_m: float):
    """Répartit un tronçon en (distance montante, distance descendante, magnitude de pente).

    Hypothèse : montée et descente se font à la même magnitude de pente
    (D+ + D-) / distance, ce qui conserve tout le dénivelé du tronçon.
    """
    vertical = gain_m + loss_m
    if distance_m <= 0 or vertical <= 0:
        return 0.0, 0.0, 0.0
    grade = vertical / distance_m
    return distance_m * gain_m / vertical, distance_m * loss_m / vertical, grade


def _segments(activity: Dict[str, Any]) -> List[tuple]:
    """(distance_m, D+, D-) par split si dispo, sinon un seul tronçon pour la séance entière."""
    splits = activity.get("splits") or []
    cols = activity.get("splits_cols") or []
    if splits and "elev_gain_m" in cols and "elev_loss_m" in cols:
        ig, il = cols.index("elev_gain_m"), cols.index("elev_loss_m")
        idist = cols.index("distance_m") if "distance_m" in cols else None
        segs = []
        try:
            for row in splits:
                dist = float(row[idist]) if idist is not None and row[idist] is not None else 1000.0
                segs.append((dist, float(row[ig] or 0), float(row[il] or 0)))
        except (IndexError, TypeError, ValueError):
            segs = []
        if segs:
            return segs
    if activity.get("elevation_gain_m") is None and activity.get("elevation_loss_m") is None:
        return []
    return [(activity["distance_km"] * 1000.0,
             float(activity.get("elevation_gain_m") or 0),
             float(activity.get("elevation_loss_m") or 0))]


def terrain_of(activity: Dict[str, Any]) -> str:
    terrain = activity.get("terrain")
    if terrain in TERRAIN_FACTORS:
        return terrain
    return DEFAULT_TERRAIN.get(activity.get("type"), "route")


def effort_km(activity: Dict[str, Any]) -> Optional[float]:
    """Distance équivalente plat (Minetti) × coefficient de terrain, ou None sans dénivelé connu.

    La descente compte au moins comme du plat : sa « remise » métabolique
    annulerait sinon presque tout le coût de la montée sur une boucle, alors
    qu'elle est mécaniquement la plus chargeante (suivie à part par
    `eccentric_load`).
    """
    segs = _segments(activity)
    if not segs:
        return None
    flat = minetti_cost(0.0)
    total_m = 0.0
    for dist, gain, loss in segs:
        up, down, grade = _decompose(dist, gain, loss)
        level = dist - up - down
        total_m += level + up * minetti_cost(grade) / flat + down * max(minetti_cost(-grade), flat) / flat
    return total_m / 1000.0 * TERRAIN_FACTORS[terrain_of(activity)]


def eccentric_load(activity: Dict[str, Any]) -> Optional[float]:
    """D- en mètres, pondéré ×1.5 sur les tronçons dont la pente descendante dépasse 10 %."""
    segs = _segments(activity)
    if not segs:
        return None
    load = 0.0
    for dist, gain, loss in segs:
        _, _, grade = _decompose(dist, gain, loss)
        load += loss * (STEEP_DOWNHILL_WEIGHT if grade > STEEP_DOWNHILL_GRADE else 1.0)
    return load


def srpe(activity: Dict[str, Any]) -> Optional[float]:
    """Charge interne de Foster : RPE × durée (min), ou None si l'un manque."""
    rpe, duration_s = activity.get("rpe"), activity.get("duration_s")
    if rpe is None or not duration_s:
        return None
    return float(rpe) * float(duration_s) / 60.0


def compute_dimensions(activity: Dict[str, Any]) -> Dict[str, Optional[float]]:
    return {
        "effort_km": effort_km(activity),
        "eccentric_m": eccentric_load(activity),
        "srpe": srpe(activity),
    }


def _read_arc(content: str) -> Optional[Dict[str, Any]]:
    arc_match = ARC_BLOCK_RE.search(content)
    if not arc_match:
        return None
    try:
        arc = json.loads(arc_match.group(1))
    except json.JSONDecodeError:
        return None
    return arc if arc.get("kind") == "activity" else None


def parse_activity_file(path: str) -> Optional[Dict[str, Any]]:
    """Extrait {date, type, distance_km, …} d'un fichier MD d'activité, ou None si illisible.

    Ordre de préférence : bloc ```arc (contrat de données, `distance_m`/`sport`)
    → bloc YAML legacy (`distance_meters`/`type`) → ligne de tableau résumé.
    Le bloc arc fournit en plus, s'ils existent, D+/D-, splits, durée, RPE,
    terrain et temps de marche (dimensions trail exploratoires).
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
    extra: Dict[str, Any] = {}

    arc = _read_arc(content)
    if arc:
        if arc.get("sport"):
            activity_type = arc["sport"]
        if arc.get("distance_m") is not None:
            distance_km = float(arc["distance_m"]) / 1000.0
        for key in ("elevation_gain_m", "elevation_loss_m", "duration_s", "rpe",
                    "splits", "splits_cols", "terrain", "walk_duration_s",
                    "exclude_from_load"):
            if arc.get(key) is not None:
                extra[key] = arc[key]

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

    activity = {
        "date": file_date,
        "type": activity_type,
        "distance_km": distance_km,
        "file": basename,
        **extra,
    }
    activity.update(compute_dimensions(activity))
    return activity


def collect_window(activities_dir: str, target_date: date, window_days: int, types: List[str]) -> List[Dict[str, Any]]:
    """Séances des `window_days` jours précédant `target_date` (jour courant exclu), filtrées par type.

    Les séances marquées `exclude_from_load` dans leur bloc arc sont ignorées.
    """
    window_start = target_date - timedelta(days=window_days)
    results = []
    for path in glob.glob(os.path.join(activities_dir, "*.md")):
        parsed = parse_activity_file(path)
        if not parsed:
            continue
        if parsed["type"] not in types:
            continue
        if parsed.get("exclude_from_load"):
            # Écartée sur décision de l'athlète (ex. course objectif) — clé arc `exclude_from_load`.
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


def dimension_spikes(session: Dict[str, Any], window_activities: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Spike exploratoire par dimension trail : valeur de la séance / max de la fenêtre.

    Une dimension n'est calculée que si la séance ET au moins une séance de la
    fenêtre la renseignent ; les séances sans la donnée sont ignorées pour elle,
    et `complete` est faux — le max de la fenêtre peut alors être sous-estimé
    (fichiers anciens sans bloc arc : lancer /arc-backfill).
    """
    results = {}
    for key in DIMENSIONS:
        value = session.get(key)
        if value is None:
            continue
        baseline = [a for a in window_activities if a.get(key)]
        coverage = (len(baseline), len(window_activities))
        if not baseline:
            results[key] = {"value": value, "baseline": None, "coverage": coverage, "complete": False}
            continue
        ref = max(baseline, key=lambda a: a[key])
        ratio = value / ref[key]
        results[key] = {"value": value, "baseline": ref[key], "baseline_date": ref["date"],
                        "ratio": ratio, "category": categorize(ratio),
                        "coverage": coverage, "complete": coverage[0] == coverage[1]}
    return results


def _fmt(key: str, value: float) -> str:
    return DIMENSIONS[key][2].format(value)


def format_report(target_date: date, distance_km: float, window_days: int,
                   window_activities: List[Dict[str, Any]], quiet: bool,
                   session: Optional[Dict[str, Any]] = None) -> str:
    if not window_activities:
        return (
            f"🟢 Spike de charge — {target_date.isoformat()} : baseline insuffisante "
            f"(aucune séance course/trail dans les {window_days} jours précédents). "
            "Vérification impossible, pas de signal à reporter."
        )

    longest = max(window_activities, key=lambda a: a["distance_km"])
    ratio = distance_km / longest["distance_km"] if longest["distance_km"] > 0 else float("inf")
    cat = categorize(ratio)
    dims = dimension_spikes(session, window_activities) if session else {}

    if quiet:
        line = (
            f"{cat['emoji']} {cat['label']} ({ratio:.2f}×) — "
            f"{distance_km:.1f} km vs {longest['distance_km']:.1f} km le {longest['date'].isoformat()}"
        )
        # Une dimension trail ne s'ajoute que si elle est 🟠/🔴, plus défavorable
        # que le spike distance et calculée sur une baseline complète — la ligne
        # reste unique (notification).
        worst = [(k, d) for k, d in dims.items()
                 if d["complete"] and d["ratio"] > 1.30 and d["ratio"] > ratio]
        if worst:
            key, d = max(worst, key=lambda kd: kd[1]["ratio"])
            line += (
                f" · {d['category']['emoji']} {DIMENSIONS[key][0]} {d['ratio']:.2f}× "
                f"({_fmt(key, d['value'])} vs {_fmt(key, d['baseline'])}, exploratoire)"
            )
        return line

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

    if dims:
        lines += [
            "",
            "### Dimensions trail (exploratoires — seuils extrapolés, non validés)",
            "",
            "| Dimension | Séance | Max 30 j | Ratio | Catégorie | Baseline |",
            "|:---|---:|---:|---:|:---|:---|",
        ]
        for key, d in dims.items():
            label, unit, _ = DIMENSIONS[key]
            known, total = d["coverage"]
            coverage = f"{known}/{total} séances" + ("" if d["complete"] else " ⚠️ partielle")
            if d["baseline"] is None:
                lines.append(f"| {label} | {_fmt(key, d['value'])} {unit} | — | — | baseline insuffisante | {coverage} |")
                continue
            lines.append(
                f"| {label} | {_fmt(key, d['value'])} {unit} | {_fmt(key, d['baseline'])} "
                f"({d['baseline_date'].isoformat()}) | {d['ratio']:.2f}× | "
                f"{d['category']['emoji']} {d['category']['label']} | {coverage} |"
            )
        context = [f"terrain : {terrain_of(session)}"]
        if session.get("walk_duration_s") and session.get("duration_s"):
            context.append(f"marche : {100 * session['walk_duration_s'] / session['duration_s']:.0f} % du temps")
        lines += [
            "",
            f"_{' · '.join(context)}. km-effort = coût de la course selon la pente "
            "(Minetti 2002) × terrain ; descente = D- pondéré ×1.5 au-delà de 10 % ; "
            "sRPE = RPE × minutes. Seuls les seuils de la distance sont validés._",
        ]
        if not all(d["complete"] for d in dims.values()):
            lines.append(
                "_Baseline partielle : des séances de la fenêtre n'ont pas la donnée "
                "(fichiers anciens sans bloc arc, RPE non déclaré) — le ratio est alors "
                "surestimé ; `/arc-backfill` complète les fichiers anciens._"
            )

    lines.append("")
    lines.append(f"_{len(window_activities)} séance(s) course/trail considérée(s) dans la fenêtre de {window_days} jours._")
    return "\n".join(lines)


def build_session(args: argparse.Namespace) -> Dict[str, Any]:
    """Séance évaluée : lue depuis --from-file, puis complétée/surchargée par les flags."""
    session: Dict[str, Any] = {}
    if args.from_file:
        parsed = parse_activity_file(args.from_file)
        if not parsed:
            raise SystemExit(f"Fichier d'activité illisible ou sans distance : {args.from_file}")
        session.update(parsed)
    else:
        session["type"] = "trail" if args.elevation_gain_m else "running"
    if args.date:
        session["date"] = datetime.strptime(args.date, "%Y-%m-%d").date()
    session.setdefault("date", date.today())
    overrides = {
        "distance_km": args.distance_km,
        "elevation_gain_m": args.elevation_gain_m,
        "elevation_loss_m": args.elevation_loss_m if args.elevation_loss_m is not None else (
            args.elevation_gain_m if args.elevation_gain_m is not None and not args.from_file else None),
        "duration_s": args.duration_min * 60 if args.duration_min is not None else None,
        "rpe": args.rpe,
        "terrain": args.terrain,
    }
    for key, value in overrides.items():
        if value is not None:
            session[key] = value
    if "distance_km" not in session:
        raise SystemExit("--distance-km est requis sans --from-file.")
    if not args.from_file and args.elevation_gain_m is None:
        # Séance planifiée sans dénivelé : pas de km-effort/descente à comparer.
        session.pop("elevation_loss_m", None)
    session.update(compute_dimensions(session))
    return session


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--date", default=None, help="Date de la séance évaluée (YYYY-MM-DD). Défaut : aujourd'hui.")
    parser.add_argument("--distance-km", type=float, default=None, help="Distance prévue/réelle de la séance, en km.")
    parser.add_argument("--from-file", default=None, help="Fichier MD d'une séance réalisée (bloc ```arc).")
    parser.add_argument("--elevation-gain-m", type=float, default=None, help="D+ prévu, en m.")
    parser.add_argument("--elevation-loss-m", type=float, default=None, help="D- prévu, en m (défaut : = D+).")
    parser.add_argument("--duration-min", type=float, default=None, help="Durée prévue, en minutes.")
    parser.add_argument("--rpe", type=float, default=None, help="Effort perçu 0-10.")
    parser.add_argument("--terrain", choices=sorted(TERRAIN_FACTORS), default=None, help="Technicité du terrain.")
    parser.add_argument("--dir", default="activities", help="Dossier des activités (défaut activities/).")
    parser.add_argument("--types", default="running,trail", help="Types de séance comptant pour la baseline (défaut running,trail).")
    parser.add_argument("--window-days", type=int, default=30, help="Fenêtre de lookback en jours (défaut 30).")
    parser.add_argument("--json", default=None, help="Fichier JSON de sortie (dump structuré).")
    parser.add_argument("--quiet", action="store_true", help="Sortie minimale (une ligne).")
    args = parser.parse_args()

    session = build_session(args)
    target_date = session["date"]
    distance_km = session["distance_km"]
    types = [t.strip() for t in args.types.split(",") if t.strip()]

    window_activities = collect_window(args.dir, target_date, args.window_days, types)
    report = format_report(target_date, distance_km, args.window_days, window_activities, args.quiet, session)
    print(report)

    if args.json:
        longest = max(window_activities, key=lambda a: a["distance_km"]) if window_activities else None
        ratio = (distance_km / longest["distance_km"]) if longest and longest["distance_km"] > 0 else None
        dims = dimension_spikes(session, window_activities)
        payload = {
            "target_date": target_date.isoformat(),
            "distance_km": distance_km,
            "window_days": args.window_days,
            "longest_in_window_km": longest["distance_km"] if longest else None,
            "longest_in_window_date": longest["date"].isoformat() if longest else None,
            "ratio": ratio,
            "category": categorize(ratio)["label"] if ratio is not None else None,
            "terrain": terrain_of(session),
            "exploratory": {
                key: {
                    "value": d["value"],
                    "baseline": d["baseline"],
                    "baseline_date": d["baseline_date"].isoformat() if d.get("baseline_date") else None,
                    "ratio": d.get("ratio"),
                    "category": d["category"]["label"] if d.get("category") else None,
                    "baseline_coverage": list(d["coverage"]),
                    "baseline_complete": d["complete"],
                }
                for key, d in dims.items()
            },
            "window_activities": [
                {"date": a["date"].isoformat(), "type": a["type"], "distance_km": a["distance_km"],
                 "file": a["file"], **{k: a.get(k) for k in DIMENSIONS}}
                for a in window_activities
            ],
        }
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    return 0


if __name__ == "__main__":
    sys.exit(main())
