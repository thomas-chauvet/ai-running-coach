---
name: strava-insights
description: Use on demand when the athlete asks about Strava-native views Garmin doesn't surface — progress on a named segment over time, a weekly "Strava highlights" recap (segment PRs, best efforts) for the rapports/ report, gear mileage, athlete zones, or a declared training focus/plan on Strava. TERTIARY and read-only (see AGENTS.md → Backends MCP → Strava): never a primary data source; the only persisted output is a synthesis paragraph inside the coach-owned weekly rapports/ file, never a write to activities//medical/. Verify eligibility before use in a new session.
---

# Skill: strava-insights

Vues Strava plus riches, à la demande — complément conversationnel/ponctuel de
`strava-highlights` (qui, lui, tourne automatiquement après chaque sync).

## Progression sur un segment nommé

Quand l'utilisateur demande "comment je progresse sur <segment> ?" :

1. `list_activities` sur la période demandée (`range_start`/`range_end`).
2. Pour chaque activité candidate du bon sport, `get_activity_performance` et
   filtrer `segment_efforts` par nom (ou `segment_id` si déjà connu d'un appel
   précédent).
3. Construire un tableau chronologique : date, temps, FC moyenne, tier de PR
   obtenu ce jour-là (si le segment apparaît aussi dans `pr_achievements` de cette
   activité). Conclure sur la tendance (progression, plateau, régression).

## Récap hebdomadaire « Points forts Strava » (dans `rapports/`)

Lors de la production du rapport hebdomadaire (`rapports/YYYY-MM-DD_rapport.md`,
propriété du coach — voir `agents/coach.md` → Weekly Reports), ajouter une section
**« Points forts Strava »** agrégeant, pour les activités de la semaine :

- Le total de PR de segments obtenus, par tier (🥇/🥈/🥉).
- Le ou les segments marquants de la semaine (nommés).
- Le meilleur temps de la semaine par distance standard parmi les `best_efforts`
  retournés par `get_activity_performance` (ex. "meilleur 5K de la semaine : 31:19").

**Formuler explicitement en "meilleur de la semaine", jamais en "record all-time"**
— il n'y a pas de scan historique complet permettant d'affirmer un record absolu.

Cette section est le **seul cas où un contenu dérivé de Strava est persisté** : le
rapport est une synthèse du coach, pas un fichier `activities/`/`medical/` — cela
ne viole pas la règle TERTIAIRE, qui porte sur la source de vérité des données
brutes d'activité, pas sur les synthèses narratives du coach.

## Autres vues (seulement si l'utilisateur les mentionne)

- `get_gear` — kilométrage chaussures.
- `get_athlete_zones` — comparaison aux zones utilisées par le coach.
- `get_training_plan` / `current_focus` du profil (`get_athlete_profile`) —
  objectif ou focus déclaré côté Strava.

## Limite honnête à rappeler

Le jeu d'outils MCP Strava disponible (`list_activities`, `get_activity_performance`,
`get_activity_streams`, `get_athlete_profile`, `get_athlete_zones`, `get_gear`,
`get_strength_workout_details`, `get_training_plan`, `get_club_info`, `eligibility`)
**ne comporte aucun outil dédié segments/leaderboard/classement**. Tout ce qui
concerne les segments vient de `get_activity_performance`, activité par activité —
le dire explicitement à l'utilisateur plutôt que d'inventer un classement ou une
donnée absente.

## Discipline

- Vérifier `eligibility` avant tout usage dans une nouvelle session.
- Même discipline de fraîcheur que `garmin-sync-efficiency` : dates/périodes
  précises, extraction minimale, jamais de JSON brut dans la conversation.
- Strava reste TERTIAIRE : en cas de contradiction avec un fichier Garmin déjà
  persisté, le fichier MD Garmin fait foi pour toute décision d'entraînement —
  Strava enrichit la conversation et le rapport, il ne tranche jamais une décision.

## Files

| Path | Rôle |
|:-----|:-----|
| `SKILL.md` | Ce fichier |

Base directory: skills/strava-insights
