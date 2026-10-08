# 💬 Skill : Coach sur Telegram

> **Description** : Forme des échanges et garde-fous quand l'athlète écrit au coach depuis Telegram (session Claude Code *Channels* lancée par `scripts/coach-telegram.sh`). Réponses courtes via l'outil `reply`, **aucun envoi au calendrier Garmin sans « OK » explicite dans un message suivant**, aucune suppression depuis Telegram.

## Quand l'utiliser

À chaque message reçu par le canal Telegram. La session est rappelée à l'ordre par
`--append-system-prompt` au démarrage. Mise en route : [Le coach dans la poche](../mobile.md).

## Comportement

| Sujet | Règle |
|---|---|
| Réponse | Uniquement par l'outil `reply` du canal : le texte du terminal n'arrive pas sur le téléphone |
| Forme | Courte, lisible sur mobile, sans tableau large ni JSON ; renvoi au fichier MD pour le détail |
| Tâche longue | « ⏳ … » d'abord, puis `edit_message` avec le résultat |
| Questions | Posées dans Telegram, jamais par une invite du terminal (personne ne la verrait) |
| Envoi Garmin | Présenter la séance (+ spike de charge), demander « OK ? », n'envoyer qu'après un « OK » dans un message **suivant** |
| Suppression Garmin | Interdite depuis Telegram (permissions `deny`) : Garmin Connect, Remote Control ou terminal |
| Photos | Lues depuis `~/.claude/channels/telegram/inbox/` (repas → nutritionniste) |

Toutes les règles d'`AGENTS.md` restent valables : bilan matinal selon
`[health].morning_check`, météo, fraîcheur des données, contrat `arc`, délégation limitée à
`[agents].enabled`.

## Permissions

Le plugin ne relaie pas les demandes de permission : `coach-telegram.sh install` fusionne
`templates/settings.telegram.json` dans `.claude/settings.local.json` du workspace (lecture
Garmin, envois Garmin, fichiers, agents, skills, scripts Python, météo, Strava ; suppressions
Garmin en `deny`).

## Fichier source

`skills/telegram-chat/SKILL.md`
