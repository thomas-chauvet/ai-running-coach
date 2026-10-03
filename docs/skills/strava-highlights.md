# 🏆 Skill : Points forts Strava

> **Description** : Repère et célèbre les PR de segments Strava (🥇/🥈/🥉) d'une séance Garmin nouvellement synchronisée, et les replie dans la ligne « Séances » de la notification quotidienne. Un signal motivant, pas un contrôle qualité. Strava reste **tertiaire** : jamais une source de données primaire, jamais bloquant.

## Pourquoi ce skill

Garmin ne met pas en valeur les PR de segments. Si la même sortie est synchronisée sur
Strava, `get_activity_performance` expose ses `pr_achievements` (PR or/argent/bronze sur des
segments nommés) : de quoi rendre le résumé quotidien plus motivant, sans en faire une
dépendance.

## Quand l'utiliser

- **Automatiquement après `/garmin-daily-sync`**, pour chaque séance nouvellement persistée
  dans `activities/`.
- Désactivable via `config/workspace.toml` → `[integrations].strava_highlights = false`.

## Fonctionnement

1. **Éligibilité** : `eligibility` est vérifiée **une fois par run**, jamais par activité.
   Connecteur absent, non autorisé ou injoignable (mode headless) → skill ignoré en silence.
2. **Appariement** : `list_activities` sur la journée, candidate la plus proche de
   `start_time` (bloc arc) à ±15 min, sport compatible. Aucune candidate ou égalité
   → ignoré en silence.
3. **Extraction** : si `pr_count > 0`, `get_activity_performance` ; le nombre annoncé est
   **toujours** `len(pr_achievements)` (le `pr_count` du résumé peut différer), compté par
   tier, avec le nom du segment du meilleur tier.
4. **Format** : replié dans la ligne `Séances :` du bloc ```resume — jamais une 6e ligne :

```
Séances : 1 nouvelle — trail 12,3 km / 480 m D+ / FC moy 148 / HRR 28 bpm (2026-09-20) — 🏆 10 PR Strava (1🥇 6🥈 1🥉), record sur « Le Lavancher bas/Le Lavancher haut »
```

À la demande (hors sync), le détail complet est donné : chaque segment, temps, D+, FC moyenne.

## Comportement

- **Silence total** si Strava est indisponible ou s'il n'y a rien à célébrer : jamais de
  ligne `ERREUR`, jamais de sync bloquée.
- **N'écrit jamais** dans `activities/` ni `medical/` : Garmin reste la source de vérité.
- Ne compare pas les mesures Garmin et Strava.
- Progression sur un segment et récap hebdomadaire : voir [Strava — vues à la demande](strava-insights.md).

## Fichier source

`skills/strava-highlights/SKILL.md`
