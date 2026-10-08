#!/usr/bin/env bash
# =============================================================================
# ai-running-coach — notifications push sur Telegram, en une fois
#
# Les notifications (résumé de chaque synchronisation Garmin) partent dans la
# même conversation que le chat avec le coach (scripts/coach-telegram.sh) :
# même bot, même token. Ce script :
#   1. vérifie que le token du bot est disponible (/telegram:configure <token>)
#   2. détermine votre chat_id (compte appairé dans access.json, ou --chat-id)
#   3. écrit la section [notifications] dans config/workspace.user.toml (gitignoré)
#      et y retire les anciennes clés ntfy
#   4. envoie un message de test
#
# Usage :
#   scripts/setup-telegram.sh                     # interactif
#   scripts/setup-telegram.sh --chat-id 123456789 [--token-file ~/.config/ai-running-coach/telegram.env]
#   scripts/setup-telegram.sh --disable           # provider = "none"
# =============================================================================
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/config.sh"

CHAT_ID=""; TOKEN_FILE=""; DISABLE=0; NO_TEST=0
TG_DIR="${TELEGRAM_STATE_DIR:-$HOME/.claude/channels/telegram}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --chat-id) CHAT_ID="$2"; shift 2 ;;
        --token-file) TOKEN_FILE="$2"; shift 2 ;;
        --disable) DISABLE=1; shift ;;
        --no-test) NO_TEST=1; shift ;;
        --help|-h) sed -n '3,18p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) die "Option inconnue : $1 (voir --help)" ;;
    esac
done

# Écriture clé par clé : le reste de workspace.user.toml n'est jamais touché.
cfg_set()   { python3 "$ARC_ENGINE_ROOT/scripts/coach_config.py" set   --workspace "$ARC_WORKSPACE" --section notifications --key "$1" --value "$2" >/dev/null; }
cfg_unset() { python3 "$ARC_ENGINE_ROOT/scripts/coach_config.py" unset --workspace "$ARC_WORKSPACE" --section notifications --key "$1" >/dev/null; }

drop_legacy_ntfy() {
    local key
    for key in ntfy_url ntfy_topic ntfy_token_file; do cfg_unset "$key"; done
}

if [[ "$DISABLE" -eq 1 ]]; then
    cfg_set provider none
    drop_legacy_ntfy
    ok "Notifications désactivées."
    exit 0
fi

log "Configuration des notifications Telegram"
echo

# --- 1. Token ------------------------------------------------------------------
if [[ -n "$TOKEN_FILE" ]]; then
    TOKEN_FILE_EXPANDED="$(expand_path "$TOKEN_FILE")"
    [[ -f "$TOKEN_FILE_EXPANDED" ]] || die "Fichier token introuvable : $TOKEN_FILE_EXPANDED"
    chmod 600 "$TOKEN_FILE_EXPANDED" 2>/dev/null || true
    TOKEN_FILE="${TOKEN_FILE_EXPANDED/#$HOME/\~}"   # forme ~ : portable entre machines
elif [[ -z "${TELEGRAM_BOT_TOKEN:-}" && ! -f "$TG_DIR/.env" ]]; then
    die "Token du bot introuvable ($TG_DIR/.env).
  1. Telegram → @BotFather → /newbot → copiez le token
  2. Dans Claude Code : /plugin install telegram@claude-plugins-official, puis /telegram:configure <token>
  Puis relancez ce script."
fi
ok "Token du bot disponible"

# --- 2. chat_id ----------------------------------------------------------------
if [[ -z "$CHAT_ID" && -f "$TG_DIR/access.json" ]]; then
    CHAT_ID="$(python3 -c '
import json, sys
ids = json.load(open(sys.argv[1])).get("allowFrom") or []
print(ids[0] if ids else "")' "$TG_DIR/access.json" 2>/dev/null || true)"
    [[ -z "$CHAT_ID" ]] || ok "Compte appairé trouvé dans access.json : $CHAT_ID"
fi
if [[ -z "$CHAT_ID" ]]; then
    [[ -t 0 ]] || die "Aucun compte appairé : passez --chat-id (votre ID numérique, via @userinfobot) ou appairez le bot (scripts/coach-telegram.sh run --pairing)."
    echo "Aucun compte appairé. Votre ID numérique Telegram s'obtient auprès de @userinfobot."
    read -r -p "chat_id : " CHAT_ID
fi
[[ "$CHAT_ID" =~ ^-?[0-9]+$ ]] || die "chat_id invalide : « $CHAT_ID » (nombre attendu)"

# --- 3. Écriture ---------------------------------------------------------------
cfg_set provider telegram
cfg_set telegram_chat_id "$CHAT_ID"
cfg_set telegram_token_file "$TOKEN_FILE"
drop_legacy_ntfy
ok "Section [notifications] écrite dans $ARC_CONFIG_USER"

# --- 4. Test -------------------------------------------------------------------
if [[ "$NO_TEST" -eq 0 && -t 0 ]]; then
    read -r -p "Envoyer un message de test maintenant ? [O/n] : " yn
    if [[ "${yn:-o}" =~ ^([oO]([uU][iI])?|[yY]([eE][sS])?)$ ]]; then
        "$ARC_ENGINE_ROOT/scripts/notify.sh" --title "AI Running Coach" \
            "Notifications configurées ✅ — vous recevrez ici le résumé de chaque synchronisation Garmin."
    fi
fi
ok "Terminé. Les synchronisations automatiques (scripts/daily-sync.sh) enverront leur résumé sur Telegram."
