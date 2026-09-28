---
name: session-load-spike
description: Use before pushing ANY planned running/trail session to the Garmin calendar, AND after garmin-daily-sync persists a new completed running/trail session. Computes the "session-specific spike" metric from Nielsen et al., BJSM 2025;59(17):1203 (5205-runner cohort) — ratio of the session's distance to the longest running/trail session in the preceding 30 days — and reports the injury-risk category (reference/small/moderate/large spike) with its hazard ratio. Advisory only, never blocks scheduling; a 🟠/🔴 result on a newly-synced session is also surfaced in the daily-sync push notification. Do not use for weekly ACWR (the paper found no dose-response there); this is a single-session check.
---

# Skill: session-load-spike

Calcule le **spike de charge d'une séance unique**, tel que défini par l'étude
de référence :

> Nielsen R. et al., "How much running is too much? Identifying high-risk
> running sessions in a 5205-runner cohort study", *British Journal of Sports
> Medicine* 2025;59(17):1203. https://bjsm.bmj.com/content/59/17/1203

## Pourquoi cette métrique (et pas l'ACWR hebdomadaire)

L'étude (5 205 coureurs) montre que c'est la **distance d'UNE séance**,
rapportée à la plus longue sortie course/trail des 30 jours précédents, qui
prédit le risque de blessure de surcharge — pas le volume hebdomadaire total
ni l'acute:chronic workload ratio (ACWR) classique, pour lesquels l'étude ne
trouve **aucune relation dose-réponse**. Ne pas remplacer ce skill par un
calcul ACWR hebdomadaire : ce n'est pas ce que le papier valide.

## Formule

```
ratio = distance de la séance évaluée / plus longue distance parmi les
        séances running+trail des 30 jours PRÉCÉDENTS (jour courant exclu)
```

| Catégorie | Ratio | Hazard ratio blessure de surcharge |
|:---|:---|:---|
| 🟢 Référence | ≤ 1.10 | 1 (référence) |
| 🟡 Spike faible | 1.10 – 1.30 | 1.64 (IC95% 1.31–2.05) |
| 🟠 Spike modéré | 1.30 – 2.00 | 1.52 (IC95% 1.16–2.00) |
| 🔴 Spike important | > 2.00 | 2.28 (IC95% 1.50–3.48) |

## Quand l'utiliser

- **Systématiquement avant de pousser une séance running ou trail planifiée**
  au calendrier Garmin (`schedule_workouts`/`schedule_week`), notamment pour
  les longues sorties et les séances de fin de bloc.
- Lors de la validation hebdomadaire d'un plan, pour chaque sortie longue
  running/trail du bloc.
- **Après coup, pour chaque séance running/trail nouvellement persistée par
  `garmin-daily-sync`** (`--date`/`--distance-km` = ceux de la séance réellement
  effectuée) — pour signaler un spike 🟠/🔴 dans la notification push, même
  quand la séance n'a jamais été planifiée/poussée via le coach (rattrapage,
  sortie spontanée, séance modifiée sur la montre).

**Ne PAS utiliser** pour les séances non running/trail (renfo, vélo, natation),
ni comme substitut à un calcul ACWR hebdomadaire (le papier montre que ce
dernier n'a pas de valeur prédictive ici).

## Workflow

```bash
python3 skills/session-load-spike/scripts/compute_spike.py \
  --date 2026-09-28 \
  --distance-km 24 \
  --dir activities/
```

Pour la notification (`garmin-daily-sync`), utiliser `--quiet` (sortie une ligne,
directement réutilisable dans le bloc ```resume) :

```bash
python3 skills/session-load-spike/scripts/compute_spike.py \
  --date 2026-09-20 --distance-km 12.3 --dir activities/ --quiet
# 🟠 Spike modéré (1.54×) — 12.3 km vs 8.0 km le 2026-08-25
```

1. **Calculer** le spike avec le script pour chaque séance running/trail
   avant de la pousser au calendrier (`--date` = date de la séance planifiée,
   `--distance-km` = distance prévue de cette séance).
2. **Reporter le résultat dans la validation** (texte de réponse à
   l'utilisateur et/ou `planning/Semaine_*.md`) — TOUJOURS en mode advisory :
   - 🟢/🟡 : mentionner brièvement, aucune action requise.
   - 🟠/🔴 : signaler explicitement le hazard ratio, croiser avec le contexte
     de récupération (HRV, FC repos, historique blessures — agent `medical`)
     et suggérer une progression plus douce si le contexte est déjà chargé.
     **Ne jamais annuler ou refuser de pousser la séance automatiquement** —
     la décision finale reste à l'utilisateur.
3. **Baseline insuffisante** (aucune séance running/trail dans les 30 jours
   précédents, ex. reprise après coupure) : le script le signale explicitement
   ("vérification impossible") — ne pas interpréter l'absence de signal comme
   une validation.

## Configuration (CLI flags)

| Flag | Défaut | Description |
|:-----|:-------|:------------|
| `--date` | aujourd'hui | Date de la séance évaluée (YYYY-MM-DD) |
| `--distance-km` | requis | Distance prévue/réelle de la séance, en km |
| `--dir` | `activities/` | Dossier des activités |
| `--types` | `running,trail` | Types de séance comptant pour la baseline |
| `--window-days` | 30 | Fenêtre de lookback en jours (per papier) |
| `--json` | — | Fichier JSON de sortie (dump structuré) |
| `--quiet` | false | Sortie une ligne |

## Notes techniques

- **Stdlib uniquement** (re, glob, argparse, json) — aucune dépendance.
- Lit la distance par ordre de préférence pour chaque fichier
  `activities/YYYY-MM-DD_{running,trail}.md` : bloc ```arc (`distance_m`,
  `sport` — contrat de données, voir `workspace-data-contract`) → bloc YAML
  legacy `## Données brutes Garmin (référence)` (`distance_meters`, `type`)
  → ligne `| Distance | X,XX km |` du tableau résumé.
- Le jour courant (date évaluée) est **exclu** de la fenêtre de lookback,
  conformément à la méthodologie du papier.
- Un fichier d'activité illisible ou sans distance exploitable est ignoré
  silencieusement (pas d'erreur bloquante).

## Files

| Path | Role |
|:-----|:-----|
| `SKILL.md` | Ce fichier |
| `scripts/compute_spike.py` | Calcul du ratio + catégorisation (CLI) |

Base directory: skills/session-load-spike
