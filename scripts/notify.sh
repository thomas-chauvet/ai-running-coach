#!/usr/bin/env bash
# =============================================================================
# ai-running-coach — envoi d'une notification push (Telegram)
#
# Usage :
#   scripts/notify.sh [--title "Titre"] [--priority 1-5] [--tags "tag1,tag2"] "message"
#   echo "message" | scripts/notify.sh --title "Titre"
#
# Configuration : section [notifications] de config/workspace.toml
# (overrides dans config/workspace.user.toml — voir scripts/setup-telegram.sh) :
#   provider            = "telegram" | "none"
#   telegram_chat_id    = "123456789"   # vide : premier ID autorisé de access.json
#   telegram_token_file = ""            # vide : ~/.claude/channels/telegram/.env
#
# Le bot est celui du chat avec le coach (plugin Claude Code Channels
# telegram@claude-plugins-official, voir scripts/coach-telegram.sh) : même token,
# même conversation. L'envoi passe par l'API Bot en direct — il ne dépend pas de
# la session de chat, qui peut être arrêtée.
# Priorité ≤ 2 : message silencieux (sans son). Les tags sont ignorés.
#
# Codes de sortie : 0 envoyé (ou provider=none), 1 erreur de configuration, 2 échec réseau.
# =============================================================================
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/config.sh"

TITLE="AI Running Coach"
PRIORITY="3"
MESSAGE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --title) TITLE="$2"; shift 2 ;;
        --priority) PRIORITY="$2"; shift 2 ;;
        --tags) shift 2 ;;   # accepté pour compatibilité des appelants — sans effet sur Telegram
        --help|-h) sed -n '3,21p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) MESSAGE="$1"; shift ;;
    esac
done
if [[ -z "$MESSAGE" && ! -t 0 ]]; then
    MESSAGE="$(cat)"
fi
[[ -n "$MESSAGE" ]] || die "Aucun message à envoyer."

PROVIDER="$(toml_get notifications provider none)"
case "$PROVIDER" in
    none)
        warn "Notifications désactivées (provider = \"none\") — message non envoyé :"
        printf '%s\n' "$MESSAGE"
        exit 0 ;;
    telegram) ;;
    # Ancienne configuration : échouer bruyamment plutôt que perdre la notification en silence.
    ntfy) die "ntfy n'est plus pris en charge — lancez scripts/setup-telegram.sh (notifications Telegram)." ;;
    *) die "Provider de notification inconnu : $PROVIDER (telegram|none)" ;;
esac

TG_DIR="${TELEGRAM_STATE_DIR:-$HOME/.claude/channels/telegram}"

# Token : variable d'environnement, sinon fichier configuré, sinon le .env écrit
# par /telegram:configure. Une seule source pour le chat et les notifications.
TOKEN="${TELEGRAM_BOT_TOKEN:-}"
if [[ -z "$TOKEN" ]]; then
    TOKEN_FILE="$(expand_path "$(toml_get notifications telegram_token_file)")"
    TOKEN_FILE="${TOKEN_FILE:-$TG_DIR/.env}"
    [[ -f "$TOKEN_FILE" ]] || die "Token Telegram introuvable ($TOKEN_FILE) — dans Claude Code : /telegram:configure <token>"
    if grep -q '^[[:space:]]*TELEGRAM_BOT_TOKEN=' "$TOKEN_FILE"; then
        TOKEN="$(grep -m1 '^[[:space:]]*TELEGRAM_BOT_TOKEN=' "$TOKEN_FILE" | cut -d= -f2- | tr -d "[:space:]\"'")"
    else
        TOKEN="$(head -n1 "$TOKEN_FILE" | tr -d '[:space:]')"
    fi
fi
[[ -n "$TOKEN" ]] || die "Token Telegram vide — dans Claude Code : /telegram:configure <token>"

# Destinataire : clé explicite, sinon le premier compte appairé (allowFrom).
CHAT_ID="$(toml_get notifications telegram_chat_id)"
if [[ -z "$CHAT_ID" && -f "$TG_DIR/access.json" ]]; then
    CHAT_ID="$(python3 -c '
import json, sys
ids = json.load(open(sys.argv[1])).get("allowFrom") or []
print(ids[0] if ids else "")' "$TG_DIR/access.json" 2>/dev/null || true)"
fi
[[ -n "$CHAT_ID" ]] || die "telegram_chat_id inconnu — appairez le bot (/telegram:access pair) ou lancez scripts/setup-telegram.sh"

html_escape() {
    local s="$1" amp='&amp;' lt='&lt;' gt='&gt;'
    # Depuis bash 5.2 (patsub_replacement), un « & » non protégé du remplacement
    # désigne le texte trouvé, même venu d'une variable : d'où "$amp". Et pas de
    # guillemets autour de ${…} : bash 3.2 (macOS) garderait ceux de "$amp".
    s=${s//&/"$amp"}; s=${s//</"$lt"}; s=${s//>/"$gt"}
    printf '%s' "$s"
}

TEXT="<b>$(html_escape "$TITLE")</b>
$(html_escape "$MESSAGE")"
SILENT=false
[[ "$PRIORITY" =~ ^[0-9]+$ && "$PRIORITY" -le 2 ]] && SILENT=true

# Le token fait partie de l'URL : on ne l'affiche jamais, y compris en cas d'erreur.
if curl -fsS --max-time 15 \
        --data-urlencode "chat_id=$CHAT_ID" \
        --data-urlencode "text=$TEXT" \
        --data-urlencode "parse_mode=HTML" \
        --data-urlencode "disable_notification=$SILENT" \
        "https://api.telegram.org/bot$TOKEN/sendMessage" >/dev/null 2>&1; then
    ok "Notification Telegram envoyée (chat $CHAT_ID)"
else
    err "Échec de l'envoi Telegram vers le chat $CHAT_ID (token ? réseau ? bot bloqué ?)"
    exit 2
fi
