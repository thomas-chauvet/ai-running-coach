# 📈 Skill : Spike de charge d'une séance

> **Description** : Calcule le « session-specific spike » — ratio entre la distance d'une séance running/trail et la plus longue sortie running/trail des 30 jours précédents — et reporte la catégorie de risque de blessure de surcharge associée. Source : Nielsen R. et al., « How much running is too much? Identifying high-risk running sessions in a 5205-runner cohort study », *British Journal of Sports Medicine* 2025;59(17):1203.

## Pourquoi cette métrique (et pas l'ACWR hebdomadaire)

L'étude (5 205 coureurs) montre que c'est la **distance d'UNE séance**, rapportée à
la plus longue sortie course/trail des 30 jours précédents, qui prédit le risque de
blessure de surcharge — pas le volume hebdomadaire total ni l'acute:chronic workload
ratio (ACWR) classique, pour lesquels l'étude ne trouve **aucune relation dose-réponse**.

## Formule

```
ratio = distance de la séance évaluée / plus longue distance parmi les
        séances running+trail des 30 jours PRÉCÉDENTS (jour courant exclu)
```

| Catégorie | Ratio | Hazard ratio blessure de surcharge |
|---|---|---|
| 🟢 Référence | ≤ 1.10 | 1 (référence) |
| 🟡 Spike faible | 1.10 – 1.30 | 1.64 (IC95% 1.31–2.05) |
| 🟠 Spike modéré | 1.30 – 2.00 | 1.52 (IC95% 1.16–2.00) |
| 🔴 Spike important | > 2.00 | 2.28 (IC95% 1.50–3.48) |

## Dimensions trail (exploratoires)

La distance seule ne distingue pas 20 km plats de 20 km / 650 m D+. Le script ajoute
trois spikes **exploratoires** (même logique : séance / max des 30 jours précédents ;
mêmes seuils, **extrapolés — aucune étude ne les a validés**) :

| Dimension | Calcul | Ce qu'elle capte |
|---|---|---|
| **km-effort** | distance pondérée par le coût de la course selon la pente de chaque split (Minetti et al. 2002, descente comptée au moins comme du plat) × coefficient de terrain | dénivelé + technicité |
| **descente** | D-, ×1.5 au-delà de 10 % de pente | charge excentrique |
| **sRPE** | RPE × minutes (Foster) | charge interne : allure, terrain, chaleur, fatigue |

Terrain (clé arc `terrain`) : `route` 1.00 · `chemin` 1.05 · `single` 1.10 · `technique`
1.20 · `hors_sentier` 1.30. La part de marche (`walk_duration_s`) est affichée en contexte,
sans pondération. Le spike distance reste le verdict (seul avec hazard ratio) ; une
dimension trail n'apparaît dans la notification que si elle est 🟠/🔴, plus défavorable
que la distance, et calculée sur une baseline complète.

## Quand l'utiliser

- **Avant de pousser une séance running/trail planifiée** au calendrier Garmin, notamment
  les longues sorties et les séances de fin de bloc (utilisé par l'agent `coach`).
- **Lors de la validation hebdomadaire** d'un plan, pour chaque sortie longue running/trail.
- **Après coup, pour toute séance running/trail nouvellement synchronisée** via
  `/garmin-daily-sync` — un résultat 🟠/🔴 est repris dans la notification push, même pour
  une séance jamais planifiée via le coach (sortie spontanée, changement sur la montre).

Ne s'applique pas aux séances non running/trail, ni comme substitut à un calcul ACWR
hebdomadaire (le papier ne trouve pas de valeur prédictive pour ce dernier).

## Usage

```bash
python3 skills/session-load-spike/scripts/compute_spike.py \
  --date 2026-09-28 --distance-km 24 --dir activities/
```

Séance trail planifiée, et séance réalisée lue depuis son fichier :

```bash
python3 skills/session-load-spike/scripts/compute_spike.py \
  --date 2026-10-04 --distance-km 22 --elevation-gain-m 1100 \
  --duration-min 180 --rpe 6 --terrain technique --dir activities/
python3 skills/session-load-spike/scripts/compute_spike.py \
  --from-file activities/2026-09-26_trail.md --dir activities/
```

Sortie une ligne (utilisée pour la notification) :

```bash
python3 skills/session-load-spike/scripts/compute_spike.py \
  --date 2026-09-20 --distance-km 12.3 --dir activities/ --quiet
# 🟠 Spike modéré (1.54×) — 12.3 km vs 8.0 km le 2026-08-25
```

| Flag | Défaut | Description |
|---|---|---|
| `--date` | aujourd'hui | Date de la séance évaluée (YYYY-MM-DD) |
| `--distance-km` | requis sauf `--from-file` | Distance de la séance, en km |
| `--from-file` | — | MD d'une séance réalisée (bloc arc) |
| `--elevation-gain-m` / `--elevation-loss-m` | — | D+ / D- prévus (D- = D+ par défaut) |
| `--duration-min`, `--rpe` | — | Pour la sRPE |
| `--terrain` | selon le sport | `route` `chemin` `single` `technique` `hors_sentier` |
| `--dir` | `activities/` | Dossier des activités |
| `--types` | `running,trail` | Types de séance comptant pour la baseline |
| `--window-days` | 30 | Fenêtre de lookback en jours (per papier) |
| `--json` | — | Fichier JSON de sortie |
| `--quiet` | false | Sortie une ligne |

## Comportement

- **Toujours advisory** : ne bloque jamais un push de séance ni une décision de plan. Pour
  🟠/🔴, le hazard ratio est explicitement mentionné et croisé avec le contexte de récupération
  (HRV, FC repos, historique blessures — agent `medical`) ; la décision finale reste à l'utilisateur.
- **Baseline insuffisante** (aucune séance running/trail dans les 30 jours précédents, ex.
  reprise après coupure) : signalé explicitement (« vérification impossible »), jamais
  interprété comme un feu vert.
- **Stdlib uniquement**, aucune dépendance externe.

## Fichier source

`skills/session-load-spike/SKILL.md`
