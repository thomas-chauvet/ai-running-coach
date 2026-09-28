---
name: strava-highlights
description: Use after garmin-daily-sync persists a new activity to spot and celebrate Strava segment PRs/achievements for that outing — a positive, motivational notification, not a data-quality check. TERTIARY and advisory only (see AGENTS.md → Backends MCP → Strava): never a primary data source, never blocks the sync, never writes to activities//medical/. Degrades silently (no ERREUR line, no 6th resume line) whenever the Strava connector is unavailable, unauthorized, or no matching/PR activity is found. Verify eligibility once per run, not per activity.
---

# Skill: strava-highlights

Repère et célèbre les PR de segments/records Strava d'une séance Garmin
fraîchement persistée. Ce n'est **pas** un contrôle qualité (pas de comparaison
capteur/GPS) : une bonne nouvelle à signaler, rien de plus.

## Pourquoi ce skill

Garmin ne présente pas les PR de segments de façon ludique. Strava, si la même
sortie y est synchronisée, expose `pr_achievements` (PR or/argent/bronze sur des
segments nommés) via `get_activity_performance` — un contenu motivant que Garmin
n'a pas. Le but est de le faire remonter dans le résumé quotidien, sans jamais en
faire une dépendance : si Strava est absent, rien ne change pour l'utilisateur.

## Prérequis — Strava est optionnel et jamais bloquant

- Le connecteur `mcp__claude_ai_Strava__*` est un connecteur de **compte claude.ai**,
  pas un serveur MCP du projet (`.mcp.json`) — il peut être absent, non autorisé, ou
  injoignable en mode headless (cron). **Vérifier `eligibility` une fois par run**
  (jamais par activité) ; si `eligible` est faux ou l'appel échoue, **ignorer
  silencieusement ce skill pour tout le run** — ce n'est jamais une erreur de
  synchronisation.
- Aucune activité Strava correspondante trouvée, ou `pr_count`/`achievement_count`
  à 0 sur la candidate retenue → ignorer silencieusement aussi. Rien à célébrer
  n'est pas un échec.

## Appariement

1. Récupérer les activités Strava du jour de la séance Garmin via `list_activities`
   (filtrer sur la journée via `range_start`/`range_end`).
2. Choisir la candidate dont `start_local` est le plus proche de `start_time` (bloc
   ```arc de l'activité Garmin), tolérance ±15 minutes, sport compatible
   (running/trail Garmin ↔ Run/TrailRun Strava, etc.).
3. Plusieurs candidates aussi proches l'une que l'autre, ou aucune dans la
   tolérance → ignorer silencieusement (pas d'appariement fiable).

## Extraction et format

1. Si la candidate a `pr_count > 0` (résumé `list_activities`), appeler
   `get_activity_performance(activity_id)`. **`pr_count` n'est qu'un pré-filtre bon
   marché pour décider si l'appel vaut la peine — il peut ne pas correspondre
   exactement à la longueur du tableau `pr_achievements` retourné (vérifié en
   pratique : `pr_count: 10` côté résumé pour une activité dont
   `pr_achievements` ne contenait que 8 entrées). Le nombre annoncé à
   l'utilisateur est TOUJOURS `len(pr_achievements)`, jamais `pr_count`.**
2. Compter les `pr_achievements` par tier : `SegmentPersonalRecordGold` → 🥇,
   `SegmentPersonalRecordSilver` → 🥈, `SegmentPersonalRecordBronze` → 🥉. Le total
   célébré est la somme de ces comptes (= `len(pr_achievements)`).
3. Retenir le nom du segment du meilleur tier obtenu, en reliant l'`entity_id` du
   meilleur `pr_achievements` au `segment_efforts[].id` correspondant pour lire
   `segment_name`.
4. **Contexte automatique (`garmin-daily-sync`)** : plier le résultat dans la ligne
   `Séances :` déjà existante du bloc ```resume — **ne jamais ajouter de 6e ligne**,
   le plafond de 5 lignes du contrat `garmin-daily-sync` ne change pas. Exemple :

   ```
   Séances : 1 nouvelle — trail 12,3 km / 480 m D+ / FC moy 148 / HRR 28 bpm (2026-09-20) — 🏆 10 PR Strava (1🥇 6🥈 1🥉), record sur « Le Lavancher bas/Le Lavancher haut »
   ```

5. **À la demande** (l'utilisateur pose la question directement, hors sync
   automatique) : reporter le détail complet — chaque segment, temps, D+, FC
   moyenne — plutôt que la ligne condensée.

## Ce que ce skill NE fait PAS

- Ne compare jamais les mesures Garmin/Strava (pas de contrôle de divergence
  capteur/GPS — hors scope de cette itération).
- Ne réécrit jamais le fichier MD de l'activité (Garmin reste la source de vérité —
  voir « Persistance » dans `AGENTS.md`) ; le résultat reste conversationnel/
  notification uniquement.
- Ne bloque jamais la synchronisation ni une décision de séance.
- Pour le suivi de progression sur un segment donné dans le temps, ou le récap
  hebdomadaire dans `rapports/`, voir le skill `strava-insights`.

## Configuration

`config/workspace.toml` → `[integrations].strava_highlights` (défaut `true`)
permet de désactiver complètement ce skill sans toucher au code.

## Files

| Path | Rôle |
|:-----|:-----|
| `SKILL.md` | Ce fichier |

Base directory: skills/strava-highlights
