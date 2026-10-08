#!/usr/bin/env bash
# =============================================================================
# ai-running-coach — synchronisation Garmin automatique (headless)
#
# Lance le skill /garmin-daily-sync avec l'exécuteur configuré (Claude Code ou
# Codex CLI, abonnement — pas de clé API), journalise, extrait le bloc ```resume```
# et l'envoie en notification push via scripts/notify.sh.
#
# Usage :
#   scripts/daily-sync.sh              # exécution (appelée par cron/launchd)
#   scripts/daily-sync.sh --dry-run    # affiche la commande sans l'exécuter
#   scripts/daily-sync.sh --runner codex
#
# Configuration : section [sync] de config/workspace.toml (runner, lookback_days)
# et [notifications] (voir scripts/setup-telegram.sh). S'exécute dans le workspace
# (ARC_WORKSPACE / ~/.config/ai-running-coach/workspace, sinon ce dépôt).
# Journaux : <workspace>/logs/sync-YYYY-MM-DD.log (gitignoré). Verrou : logs/.sync.lock.
# =============================================================================
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/config.sh"

DRY_RUN=0
RUNNER=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=1; shift ;;
        --runner) RUNNER="$2"; shift 2 ;;
        --help|-h) sed -n '3,18p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) die "Option inconnue : $1 (voir --help)" ;;
    esac
done

# cron/launchd démarrent avec un PATH minimal : ajoute les emplacements usuels
# de claude, codex, uv et garmin-mcp.
export PATH="$HOME/.local/bin:$HOME/.claude/bin:$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

RUNNER="${RUNNER:-$(toml_get sync runner claude)}"
LOOKBACK="$(toml_get sync lookback_days 2)"
GIT_AUTOCOMMIT="$(toml_get sync git_autocommit false)"
SKILL_FILE="$ARC_ENGINE_ROOT/skills/garmin-daily-sync/SKILL.md"
LOG_DIR="$ARC_WORKSPACE/logs"
LOG_FILE="$LOG_DIR/sync-$(date +%F).log"
LOCK_FILE="$LOG_DIR/.sync.lock"
NOTIFY="$ARC_ENGINE_ROOT/scripts/notify.sh"

# Complète les liens vers le moteur dans le workspace (scripts/, et les
# catalogues skills/agents sous .claude, .opencode, .github s'ils existent),
# sans rien retirer ni toucher cron/systemd/notifications — un simple `./install.sh`
# complet est hors périmètre d'un run cron non surveillé. Nécessaire parce
# qu'un skill ajouté au moteur (ex. workspace-data-contract le 23/09) reste
# invisible du workspace tant que personne ne relance `./install.sh` à la
# main ; jusque-là, la sync se dégrade en silence pendant des jours au lieu
# d'échouer une fois, bruyamment.
ensure_engine_links() {
    [[ -d "$ARC_ENGINE_ROOT" ]] || die "Moteur introuvable : $ARC_ENGINE_ROOT (ARC_ENGINE_ROOT/lien scripts cassé) — relancez ./install.sh."
    if [[ ! -e "$ARC_WORKSPACE/scripts" ]]; then
        ln -sfn "$ARC_ENGINE_ROOT/scripts" "$ARC_WORKSPACE/scripts"
        warn "Lien recréé : $ARC_WORKSPACE/scripts -> $ARC_ENGINE_ROOT/scripts"
    fi
    [[ -f "$ARC_WORKSPACE/scripts/arc_index.py" ]] \
        || die "scripts/arc_index.py introuvable après relink — moteur incomplet dans $ARC_ENGINE_ROOT."

    local cat catalog_dir engine_item name
    for cat in skills agents; do
        for catalog_dir in "$ARC_WORKSPACE/$cat" "$ARC_WORKSPACE"/.claude/"$cat" "$ARC_WORKSPACE"/.opencode/"$cat" "$ARC_WORKSPACE"/.github/"$cat"; do
            [[ -d "$catalog_dir" ]] || continue   # catalogue non déployé ici : rien à compléter
            for engine_item in "$ARC_ENGINE_ROOT/$cat"/*; do
                [[ -e "$engine_item" ]] || continue
                name="$(basename "$engine_item")"
                [[ -e "$catalog_dir/$name" ]] && continue
                ln -sfn "$engine_item" "$catalog_dir/$name"
                warn "Lien ajouté (catalogue en retard sur le moteur) : $catalog_dir/$name"
            done
        done
    done
}

[[ -f "$SKILL_FILE" ]] || die "Skill introuvable : $SKILL_FILE"
mkdir -p "$LOG_DIR"
ensure_engine_links

# Outils autorisés en mode non interactif : serveur MCP garmin (tous ses outils),
# délégation au coach (Agent/Task), skills, lecture/écriture des MD, scripts
# Python du projet. Rien d'autre.
# mcp__claude_ai_Strava est un connecteur de COMPTE claude.ai (pas un serveur
# déclaré dans .mcp.json, contrairement à garmin) — l'ajouter ici est nécessaire
# pour le skill strava-highlights mais NON garanti suffisant : son accessibilité
# en mode `claude -p` headless (ce runner) est non vérifiée. Si l'auth ne passe
# pas, le skill se dégrade silencieusement (voir garmin-daily-sync/SKILL.md) —
# aucun impact sur le sync Garmin lui-même.
CLAUDE_TOOLS="mcp__garmin,mcp__leanproxy,mcp__claude_ai_Strava,Agent,Task,Skill,Read,Write,Edit,Glob,Grep,Bash(python3:*)"
# En mode -p, un serveur MCP déclaré dans .mcp.json (portée projet) n'est chargé
# que s'il a été approuvé interactivement ; on le passe explicitement.
MCP_CONFIG="$ARC_WORKSPACE/.mcp.json"

build_command() {
    case "$RUNNER" in
        claude)
            have claude || [[ "$DRY_RUN" -eq 1 ]] || die "claude introuvable — installez Claude Code : curl -fsSL https://claude.ai/install.sh | bash"
            CMD=(claude -p "/garmin-daily-sync (lookback_days=$LOOKBACK)"
                 --permission-mode acceptEdits
                 --allowedTools "$CLAUDE_TOOLS"
                 --output-format text)
            if [[ -f "$MCP_CONFIG" ]]; then
                CMD+=(--mcp-config "$MCP_CONFIG" --strict-mcp-config)
            else
                warn "$MCP_CONFIG absent — lancez './install.sh --ide claude' (serveur MCP garmin)."
            fi ;;
        codex)
            have codex || [[ "$DRY_RUN" -eq 1 ]] || die "codex introuvable — installez Codex CLI : npm i -g @openai/codex"
            # Codex n'a pas de slash-command projet : on passe le corps du skill en prompt.
            local prompt
            prompt="$(awk 'NR==1 && /^---$/ {fm=1; next} fm && /^---$/ {fm=0; next} !fm' "$SKILL_FILE")"
            prompt="lookback_days=$LOOKBACK. Follow these instructions exactly:
$prompt"
            CMD=(codex exec --full-auto --cd "$ARC_WORKSPACE" "$prompt") ;;
        *) die "Exécuteur inconnu : $RUNNER (claude|codex)" ;;
    esac
}

# Extrait le contenu du dernier bloc ```resume … ``` de la sortie.
extract_resume() {
    awk '
        /^```resume[[:space:]]*$/ { capture = 1; buf = ""; next }
        capture && /^```[[:space:]]*$/ { capture = 0; last = buf; next }
        capture { buf = buf $0 "\n" }
        END { printf "%s", last }'
}

# Identité des commits et des rebase faits par la machine coach : cron n'a souvent
# aucune configuration git globale, et un rebase sans identité échoue.
GIT_ID=(-c user.name="${GIT_AUTHOR_NAME:-ai-running-coach}" -c user.email="${GIT_AUTHOR_EMAIL:-coach@localhost}")

# Avant le run : récupère ce qu'une autre machine a poussé (fichiers mis au contrat
# depuis le portable, plan écrit en session mobile…), pour que l'agent parte de
# l'état le plus récent. Un échec (conflit, réseau) n'empêche pas la
# synchronisation : elle se fait sur l'état local et le push final le signalera.
git_pull_before_run() {
    [[ "$GIT_AUTOCOMMIT" == "true" ]] || return 0
    git -C "$ARC_WORKSPACE" rev-parse --is-inside-work-tree >/dev/null 2>&1 || return 0
    git -C "$ARC_WORKSPACE" remote get-url origin >/dev/null 2>&1 || return 0
    if git -C "$ARC_WORKSPACE" "${GIT_ID[@]}" pull -q --rebase --autostash 2>>"$LOG_FILE"; then
        ok "git : workspace à jour"
    else
        git -C "$ARC_WORKSPACE" rebase --abort >/dev/null 2>&1 || true
        warn "git pull échoué (voir $LOG_FILE) — synchronisation sur l'état local."
    fi
}

# Versionne le workspace après chaque run (données de la sync ET fichiers créés
# entre-temps par les sessions Remote Control). Push seulement si un remote existe.
# Retourne 0 si rien à faire ou si le commit/push a réussi ; sinon 1 (signalé
# dans la notification, sans faire échouer la synchronisation).
git_autocommit() {
    [[ "$GIT_AUTOCOMMIT" == "true" ]] || return 0
    git -C "$ARC_WORKSPACE" rev-parse --is-inside-work-tree >/dev/null 2>&1 || { warn "git_autocommit : $ARC_WORKSPACE n'est pas un dépôt git."; return 1; }
    cd "$ARC_WORKSPACE"
    if [[ -z "$(git status --porcelain)" ]]; then
        ok "git : rien à versionner"
        return 0
    fi
    git add -A
    git "${GIT_ID[@]}" commit -q -m "sync: $(date '+%F %H:%M') ($RUNNER)" || { warn "git commit échoué"; return 1; }
    ok "git : commit $(git rev-parse --short HEAD)"
    if git remote get-url origin >/dev/null 2>&1; then
        # Sans ce rebase, un seul push venu d'ailleurs pendant le run rendait tous les
        # push suivants de la machine coach impossibles (historiques divergents).
        if ! git "${GIT_ID[@]}" pull -q --rebase 2>>"$LOG_FILE"; then
            git rebase --abort >/dev/null 2>&1 || true
            warn "git pull --rebase échoué avant le push (voir $LOG_FILE)"
            return 1
        fi
        git push -q 2>>"$LOG_FILE" && ok "git : push origin" || { warn "git push échoué (voir $LOG_FILE)"; return 1; }
    fi
}

notify() {
    local title="$1" priority="$2" tags="$3"
    shift 3
    if [[ "$DRY_RUN" -eq 1 ]]; then
        printf '%s\n' "${C_YELLOW}[dry-run]${C_RESET} notify.sh --title \"$title\" — $*"
        return 0
    fi
    "$NOTIFY" --title "$title" --priority "$priority" --tags "$tags" "$*" || warn "Notification non envoyée."
}

main() {
    build_command
    log "Synchronisation Garmin — exécuteur : $RUNNER, fenêtre : $LOOKBACK jour(s)"
    log "Workspace : $ARC_WORKSPACE (moteur : $ARC_ENGINE_ROOT)"

    if [[ "$DRY_RUN" -eq 1 ]]; then
        printf '%s\n' "${C_YELLOW}[dry-run]${C_RESET} cd $ARC_WORKSPACE && ${CMD[*]}" | head -c 600; echo
        printf '%s\n' "${C_YELLOW}[dry-run]${C_RESET} journal : $LOG_FILE"
        return 0
    fi

    # Verrou : pas de synchronisations concurrentes (cron du matin trop long, relance manuelle…).
    if [[ -e "$LOCK_FILE" ]] && kill -0 "$(cat "$LOCK_FILE" 2>/dev/null)" 2>/dev/null; then
        warn "Une synchronisation est déjà en cours (pid $(cat "$LOCK_FILE")) — abandon."
        exit 0
    fi
    echo $$ > "$LOCK_FILE"
    trap 'rm -f "$LOCK_FILE"' EXIT
    git_pull_before_run

    local output rc=0
    {
        echo "===== $(date '+%F %T') — runner=$RUNNER lookback=$LOOKBACK ====="
    } >> "$LOG_FILE"
    cd "$ARC_WORKSPACE"
    output="$("${CMD[@]}" 2>>"$LOG_FILE")" || rc=$?
    printf '%s\n' "$output" >> "$LOG_FILE"

    if [[ "$rc" -ne 0 ]]; then
        err "La synchronisation a échoué (code $rc) — voir $LOG_FILE"
        notify "❌ Sync Garmin échouée" 4 "warning" "Exécuteur $RUNNER, code $rc. Voir logs/sync-$(date +%F).log sur la machine coach."
        exit "$rc"
    fi

    local resume
    resume="$(printf '%s\n' "$output" | extract_resume)"
    if [[ -z "$resume" ]]; then
        warn "Aucun bloc \`\`\`resume trouvé — envoi des 5 dernières lignes de la sortie."
        resume="$(printf '%s\n' "$output" | tail -n 5)"
    fi
    ok "Résumé :"
    printf '%s\n' "$resume"

    local title="🏃 Sync Garmin" priority=3 tags="running"
    if printf '%s' "$resume" | grep -qi '^ERREUR'; then
        title="⚠️ Sync Garmin"; priority=4; tags="warning"
    elif printf '%s' "$resume" | grep -qi '^À jour'; then
        title="Sync Garmin — à jour"; priority=2; tags="running"
    fi
    # Index du tableau de bord : dérivé, jetable, et ignoré par git (.arc/ s'ignore
    # lui-même). Un tableau de bord ouvert voit ainsi la synchronisation sans attendre.
    python3 "$ARC_ENGINE_ROOT/scripts/arc_index.py" --workspace "$ARC_WORKSPACE" >>"$LOG_FILE" 2>&1 \
        || warn "Index du tableau de bord non mis à jour (voir $LOG_FILE)"
    if ! git_autocommit; then
        resume="$resume
⚠ git : commit/push du workspace échoué — voir logs/"
        priority=4
    fi
    notify "$title" "$priority" "$tags" "$resume"
}

main "$@"
