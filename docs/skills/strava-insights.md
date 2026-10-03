# 📊 Skill : Strava — vues à la demande

> **Description** : Vues Strava que Garmin ne propose pas, sur demande de l'athlète : progression sur un segment nommé, section « Points forts Strava » du rapport hebdomadaire, kilométrage du matériel, zones, objectif déclaré. **Tertiaire et en lecture seule.**

## Quand l'utiliser

Uniquement quand l'athlète le demande (« comment je progresse sur tel segment ? »), ou lors
du rapport hebdomadaire du coach. Complément ponctuel de
[Points forts Strava](strava-highlights.md), qui tourne automatiquement après chaque sync.

## Vues disponibles

| Vue | Outils Strava | Résultat |
|---|---|---|
| **Progression sur un segment** | `list_activities` puis `get_activity_performance` par activité, filtré sur le nom du segment | tableau chronologique (date, temps, FC moyenne, tier de PR) et tendance |
| **Points forts Strava** (rapport hebdo) | `get_activity_performance` sur les activités de la semaine | total de PR par tier, segments marquants, meilleur temps **de la semaine** par distance standard |
| Matériel | `get_gear` | kilométrage des chaussures |
| Zones | `get_athlete_zones` | comparaison aux zones du coach |
| Objectif déclaré | `get_training_plan`, `get_athlete_profile` | focus ou plan déclaré côté Strava |

Les trois dernières vues ne sont utilisées que si l'athlète les mentionne.

## Comportement

- **Seule persistance** : la section « Points forts Strava » du rapport hebdomadaire
  (`rapports/`), synthèse du coach. Jamais d'écriture dans `activities/` ni `medical/`.
- Formuler « meilleur de la semaine », **jamais** « record absolu » : aucun scan de
  l'historique complet n'est fait.
- Le MCP Strava n'a **aucun outil de segments, de leaderboard ou de classement** : tout vient
  de `get_activity_performance`, activité par activité. Le dire plutôt que d'inventer une
  donnée.
- `eligibility` est vérifiée avant tout usage dans une nouvelle session ; extraction minimale,
  jamais de JSON brut dans la conversation.
- En cas de contradiction avec un fichier Garmin persisté, **le fichier Garmin fait foi**.

## Fichier source

`skills/strava-insights/SKILL.md`
