"""Palier A — chat Telegram (Claude Code Channels), scripts/coach-telegram-chat.sh."""

from __future__ import annotations

import json
from pathlib import Path

from tests.lib.asserts import InstallAsserts
from tests.lib.sandbox import Sandbox


def _telegram_state(sb: Sandbox, allow_from=("4242",), policy="allowlist", token=True) -> Path:
    """État du plugin Telegram tel que l'écrivent /telegram:configure et /telegram:access."""
    state = sb.home / ".claude/channels/telegram"
    state.mkdir(parents=True, exist_ok=True)
    if token:
        (state / ".env").write_text("TELEGRAM_BOT_TOKEN=123:secret\n")
    if allow_from is not None:
        (state / "access.json").write_text(
            json.dumps({"dmPolicy": policy, "allowFrom": list(allow_from)})
        )
    return state




# Un token présent dans l'environnement du contributeur fausserait les cas « sans token ».
NO_ENV_TOKEN = {"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_STATE_DIR": "", "ANTHROPIC_API_KEY": ""}


class TestCoachTelegramChat(InstallAsserts):
    def test_refuses_to_start_unless_allowlisted(self):
        with Sandbox() as sb:
            _telegram_state(sb, policy="pairing")
            proc = sb.script("coach-telegram-chat.sh", "run", "--dry-run", **NO_ENV_TOKEN)
            self.assertFailed(proc, "politique pairing")
            self.assertOutputContains(proc, "allowlist")

    def test_pairing_mode_starts_the_channel(self):
        with Sandbox() as sb:
            _telegram_state(sb, allow_from=None)
            proc = sb.script("coach-telegram-chat.sh", "run", "--pairing", "--dry-run", **NO_ENV_TOKEN)
            self.assertSucceeded(proc)
            self.assertOutputContains(proc, "--channels plugin:telegram@claude-plugins-official")

    def test_refuses_leanproxy_mode(self):
        """mcp__leanproxy__* porterait aussi les suppressions interdites depuis Telegram."""
        with Sandbox() as sb:
            _telegram_state(sb)
            (sb.repo / ".mcp.json").write_text(json.dumps({"mcpServers": {"leanproxy": {"command": "x"}}}))
            proc = sb.script("coach-telegram-chat.sh", "run", "--dry-run", **NO_ENV_TOKEN)
            self.assertFailed(proc, "mode leanproxy")
            self.assertOutputContains(proc, "leanproxy")

    def test_install_merges_permissions_without_losing_existing_rules(self):
        with Sandbox() as sb:
            _telegram_state(sb)
            settings = sb.repo / ".claude/settings.local.json"
            settings.parent.mkdir(parents=True, exist_ok=True)
            settings.write_text(json.dumps({"permissions": {"allow": ["Bash(ls:*)"]}}))
            sb.script("coach-telegram-chat.sh", "install", **NO_ENV_TOKEN, ARC_FAKE_UNAME="Linux")
            data = json.loads(settings.read_text())
            allow, deny = data["permissions"]["allow"], data["permissions"]["deny"]
            self.assertIn("Bash(ls:*)", allow)
            self.assertIn("mcp__garmin__schedule_workouts", allow)
            self.assertIn("mcp__garmin__delete_workout", deny)
            self.assertFalse(set(allow) & set(deny), "règle à la fois autorisée et interdite")
