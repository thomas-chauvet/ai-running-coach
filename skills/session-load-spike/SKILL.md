---
name: session-load-spike
description: Use before pushing ANY planned running/trail session to the Garmin calendar, AND after garmin-daily-sync persists a new completed running/trail session. Computes the "session-specific spike" metric from Nielsen et al., BJSM 2025;59(17):1203 (5205-runner cohort) — ratio of the session's distance to the longest running/trail session in the preceding 30 days — and reports the injury-risk category (reference/small/moderate/large spike) with its hazard ratio. Advisory only, never blocks scheduling; a 🟠/🔴 result on a newly-synced session is also surfaced in the daily-sync push notification. Also reports three EXPLORATORY trail dimensions on the same 30-day logic — km-effort (Minetti grade cost × terrain), weighted descent (eccentric load) and sRPE — labelled as non-validated thresholds. Do not use for weekly ACWR (the paper found no dose-response there); this is a single-session check.
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

## Dimensions trail (exploratoires)

Le papier ne mesure que la distance. Un traileur qui fait 20 km / 650 m D+ ne
subit pas la même contrainte que sur 20 km plats : le script calcule donc, à
côté du spike distance, trois spikes **exploratoires**, chacun sur une dimension
distincte, avec la même logique (séance / maximum de la même dimension sur les
30 jours précédents) et les mêmes seuils — **extrapolés, non validés** :

| Dimension | Calcul | Ce qu'elle capte |
|:---|:---|:---|
| **km-effort** | chaque split est décomposé en montée + descente de même pente (D+ + D-) / distance, pondérées par le coût énergétique de la course selon la pente (Minetti et al., *J Appl Physiol* 2002;93:1039, borné à ±45 %) — la descente comptant au moins comme du plat, sinon sa « remise » métabolique annule la montée sur une boucle —, × coefficient de terrain | charge métabolique externe (dénivelé + technicité) |
| **descente** | D- en m, pondéré ×1.5 sur les splits dont la pente dépasse 10 % | charge excentrique, que le coût énergétique ignore (≈ −10 % est la pente la moins coûteuse… et l'une des plus traumatisantes) |
| **sRPE** | RPE × durée en minutes (Foster) | charge interne : allure, technicité, chaleur, fatigue — validée et fiable |

Coefficient de terrain (clé arc `terrain`) : `route` 1.00 · `chemin` 1.05 ·
`single` 1.10 · `technique` 1.20 · `hors_sentier` 1.30. Absent = `route` pour
une séance `running`, `chemin` pour `trail`. Ordre de grandeur : terrain
irrégulier ≈ +5 % de coût (Voloshina & Ferris, *J Exp Biol* 2015) ; au-delà,
extrapolé des facteurs de terrain de la marche (Soule & Goldman, Pandolf).

**Marche** (`walk_duration_s`) : affichée en contexte seulement. En pente raide,
marcher et courir coûtent à peu près autant ; aucune pondération validée
n'existe, et l'allure est déjà captée par la sRPE.

**Baseline partielle** : une séance de la fenêtre sans la donnée (fichier ancien
sans bloc arc, RPE non déclaré) est ignorée pour cette dimension, ce qui
surestime le ratio. Le rapport l'indique (`k/n séances ⚠️ partielle`) ; en
`--quiet`, une dimension trail n'est jamais affichée sur baseline partielle.
`/arc-backfill` complète les fichiers anciens.

**Hiérarchie** : le spike distance reste le verdict principal (seul validé,
seul avec hazard ratio). Une dimension trail 🟠/🔴 plus défavorable que la
distance se signale comme contexte (« le D+ fait de cette sortie un saut plus
gros que sa distance ne le dit ») — jamais comme hazard ratio.

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

Séance planifiée trail : passer aussi le D+ (D- = D+ par défaut, boucle), et si
connus la durée, l'effort visé et le terrain :

```bash
python3 skills/session-load-spike/scripts/compute_spike.py \
  --date 2026-10-04 --distance-km 22 --elevation-gain-m 1100 \
  --duration-min 180 --rpe 6 --terrain technique --dir activities/
```

Séance réalisée : `--from-file activities/<date>_<type>.md` lit tout du bloc arc
(date, distance, D+/D-, splits, durée, RPE, terrain).

Pour la notification (`garmin-daily-sync`), utiliser `--quiet` (sortie une ligne,
directement réutilisable dans le bloc ```resume) :

```bash
python3 skills/session-load-spike/scripts/compute_spike.py \
  --date 2026-09-20 --distance-km 12.3 --dir activities/ --quiet
# 🟠 Spike modéré (1.54×) — 12.3 km vs 8.0 km le 2026-08-25
# Dimension trail plus défavorable (baseline complète) → ajoutée sur la même ligne :
# 🟢 Référence (1.00×) — 15.0 km vs 15.0 km le 2026-09-10 · 🟠 km-effort 1.45× (21.8 vs 15.1, exploratoire)
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
| `--distance-km` | requis sauf `--from-file` | Distance prévue/réelle de la séance, en km |
| `--from-file` | — | MD d'une séance réalisée : tout est lu dans son bloc arc |
| `--elevation-gain-m` / `--elevation-loss-m` | — | D+ / D- prévus (D- = D+ par défaut) |
| `--duration-min` | — | Durée prévue (sRPE) |
| `--rpe` | — | Effort perçu 0-10 (sRPE) |
| `--terrain` | selon le sport | `route` `chemin` `single` `technique` `hors_sentier` |
| `--dir` | `activities/` | Dossier des activités |
| `--types` | `running,trail` | Types de séance comptant pour la baseline |
| `--window-days` | 30 | Fenêtre de lookback en jours (per papier) |
| `--json` | — | Fichier JSON de sortie (dump structuré, dimensions trail sous `exploratory`) |
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
- Une séance dont le bloc arc porte `"exclude_from_load": true` (décision de
  l'athlète, ex. course objectif hors norme) est écartée de la baseline.

## Files

| Path | Role |
|:-----|:-----|
| `SKILL.md` | Ce fichier |
| `scripts/compute_spike.py` | Calcul du ratio + catégorisation (CLI) |

Base directory: skills/session-load-spike
