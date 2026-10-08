---
name: garmin-daily-sync
description: Use for the unattended (headless/cron) Garmin synchronisation — invoked as /garmin-daily-sync by scripts/daily-sync.sh, from the phone (Remote Control or the Telegram chat) or from the IDE. Orchestrates the coach agent + garmin-sync-efficiency to persist the last days of activities/sleep/HRV/readiness as Markdown, checks each newly persisted running/trail session for a session-load spike (session-load-spike skill, Nielsen et al. BJSM 2025;59(17):1203) and for Strava segment PRs (strava-highlights skill, TERTIARY, silent no-op if unavailable), then emits a short ```resume``` block for the notification (including any 🟠/🔴 spike alert and any Strava PR celebration). Never asks questions.
---

# Garmin Daily Sync — Skill (orchestration headless)

Ce skill **n'ajoute aucune logique de synchronisation** : c'est le prompt versionné que le
cron (`scripts/daily-sync.sh`), le téléphone (`/garmin-daily-sync` dans une session
Remote Control) et l'IDE partagent. Il délègue tout à l'agent `coach` et au skill
`garmin-sync-efficiency`.

## Contexte d'exécution

- **Mode sans surveillance** : personne ne lit la conversation en direct. Ne JAMAIS poser de
  question (`question`, `AskUserQuestion`) ni attendre une validation. En cas de doute,
  choisir l'option conservatrice (ne rien écrire) et le signaler dans le résumé.
- **Configuration** : lire `config/workspace.toml` puis `config/workspace.user.toml`
  (ses valeurs priment) — `[language].documents` (langue des MD), `[sync].lookback_days`
  (défaut : 2), `[health].morning_check` (voir ci-dessous).
- **Pas de contrôle de premier démarrage** : le coach propose `/coach-setup` quand aucune
  configuration n'existe. **Ici, ne jamais le proposer** : personne ne peut répondre, et la
  proposition finirait dans la notification push. Travailler avec les défauts et le signaler
  en une ligne du résumé si la configuration manque.
- **Bilan matinal** : respecter `[health].morning_check`. À `off`, ne récupérer ni HRV, ni FC
  de repos, ni readiness — les fichiers correspondants ne sont alors pas attendus dans
  `medical/` et leur absence n'est pas un manque.
- **Idempotence** : ne récupérer que les dates dont le fichier MD manque dans `activities/`
  ou `medical/` (règle 1 de `garmin-sync-efficiency`). Une date déjà persistée n'est jamais
  re-synchronisée.

## Déroulé

1. Déléguer à l'agent **`coach`** (outil `task`, prompt en anglais + « Respond in <langue des
   documents> ») la tâche suivante :
   > Load the `garmin-sync-efficiency` skill. For each of the last `lookback_days` days
   > (today included), check whether `activities/YYYY-MM-DD_<type>.md` and
   > `medical/YYYY-MM-DD_health.md` exist. For missing dates only, fetch from the `garmin` MCP
   > server: activities (with splits and `recovery_hr_bpm`), sleep, HRV, training readiness,
   > resting HR / body battery. Persist each file immediately using the workspace conventions
   > (`AGENTS.md`: file names; load the `workspace-data-contract` skill and open every file
   > with its ```arc JSON block — `kind: activity` with `garmin_activity_id`, `location` and
   > `splits`, `kind: health` with `morning_check` set to the configured mode; document
   > language from `config/workspace.toml` for the prose below the block). Validate each file
   > with `python3 scripts/arc_index.py --validate <file>` and fix what it reports. For each
   > newly persisted `running`/`trail` activity, load the `session-load-spike` skill and run
   > `python3 skills/session-load-spike/scripts/compute_spike.py --from-file
   > activities/<date>_<type>.md --dir activities/ --quiet` (session-specific load spike,
   > Nielsen et al., BJSM 2025;59(17):1203, plus exploratory trail dimensions); if the line
   > holds a 🟠 or 🔴 (distance or an appended trail dimension), keep it to fold into the
   > alert line below — 🟢/🟡 results are not worth a notification line.
   > Then check `mcp__claude_ai_Strava__eligibility` once for the whole run (not per
   > activity); if eligible, load the `strava-highlights` skill and, for each newly
   > persisted activity, look for a matching Strava activity of the same day and, if it
   > has segment PRs, fold the tier count + best segment name into the "Séances" summary
   > line (never a 6th line). Any Strava-related failure at any step (eligibility,
   > matching, MCP call) is caught and ignored silently — never an `ERREUR` line, never a
   > blocked sync. Never dump raw JSON into the conversation. Do not ask questions. Do not
   > push anything to the Garmin calendar. Reply with: the list of files created, and a
   > 5-line maximum summary (new activities: type/distance/D+/HR avg/HRR, plus any Strava
   > PR celebration folded into the same line; sleep score; HRV status vs baseline;
   > readiness score; any alert such as low HRV, poor sleep, HRR missing, or a 🟠/🔴
   > session-load spike with its ratio and hazard ratio).
2. Réindexer le workspace pour le tableau de bord : `python3 scripts/arc_index.py`. La base
   est dérivée ; un échec ici ne bloque rien, mais se signale en une ligne `Alerte :` du
   résumé. Un fichier resté `NON CONFORME` à la validation se signale de la même façon
   (`Alerte : 1 fichier hors contrat — medical/2026-09-20_health.md`).
3. Si l'agent `coach` échoue (MCP indisponible, tokens Garmin expirés…), ne rien inventer :
   le résumé doit contenir `ERREUR : <cause>` (ex. « tokens Garmin expirés — relancer
   `uv run garmin-mcp-auth` »).

## Sortie OBLIGATOIRE (dernier élément de la réponse)

Terminer la réponse par un bloc de code clôturé avec le langage `resume`, **5 lignes maximum**,
dans la langue des documents, sans Markdown à l'intérieur. C'est ce bloc que
`scripts/daily-sync.sh` extrait mot pour mot pour la notification push (Telegram).

````
```resume
Séances : 1 nouvelle — trail 12,3 km / 480 m D+ / FC moy 148 / HRR 28 bpm (2026-09-20)
Sommeil : 7 h 42, score 81
HRV : 62 ms — équilibré (baseline 58-66)
Readiness : 74
Alerte : aucune
```
````

Exemple avec un spike de charge 🟠/🔴 détecté sur une séance nouvellement persistée
(remplace la ligne `Alerte`, ne s'ajoute pas en 6e ligne — 5 lignes maximum toujours) :

````
```resume
Séances : 1 nouvelle — trail 12,3 km / 480 m D+ / FC moy 148 / HRR 28 bpm (2026-09-20)
Sommeil : 7 h 42, score 81
HRV : 62 ms — équilibré (baseline 58-66)
Readiness : 74
Alerte : spike de charge 🟠 modéré (1.54×, HRR≈1.52) — 12,3 km vs 8,0 km le 2026-08-25
```
````

Exemple avec des PR de segments Strava détectés sur la séance (skill `strava-highlights`,
pliés dans la ligne `Séances`, jamais une 6e ligne — bonne nouvelle, pas une `Alerte`) :

````
```resume
Séances : 1 nouvelle — trail 12,3 km / 480 m D+ / FC moy 148 / HRR 28 bpm (2026-09-20) — 🏆 10 PR Strava (1🥇 6🥈 1🥉), record sur « Le Lavancher bas/Le Lavancher haut »
Sommeil : 7 h 42, score 81
HRV : 62 ms — équilibré (baseline 58-66)
Readiness : 74
Alerte : aucune
```
````

Si aucune date ne manquait : `À jour — aucune nouvelle donnée Garmin (dernière séance : YYYY-MM-DD)`.
Si une étape a échoué : première ligne `ERREUR : <cause courte>`.
Si le spike distance est 🟢/🟡 mais qu'une dimension trail (km-effort, descente, sRPE) est
🟠/🔴, le script l'ajoute à la même ligne ; la reprendre telle quelle, marquée exploratoire,
sans hazard ratio : `Alerte : km-effort 🟠 1.45× (21,8 vs 15,1, exploratoire) — distance 🟢 1.00×`.

S'il y a plusieurs alertes simultanées (ex. HRV faible ET spike 🟠/🔴), les regrouper sur la
même ligne `Alerte :` séparées par `; ` — la contrainte de 5 lignes ne s'assouplit jamais.
