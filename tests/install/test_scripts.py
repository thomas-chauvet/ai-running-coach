"""Palier A — scripts compagnons (setup-telegram, notify, coach-telegram, coach-remote)."""

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


class TestSetupTelegram(InstallAsserts):
    def test_chat_id_comes_from_the_paired_account(self):
        with Sandbox() as sb:
            _telegram_state(sb)
            proc = sb.script("setup-telegram.sh", "--no-test", **NO_ENV_TOKEN)
            self.assertSucceeded(proc)
            cfg = sb.repo / "config/workspace.user.toml"
            self.assertFileContains(cfg, 'provider = "telegram"')
            self.assertFileContains(cfg, 'telegram_chat_id = "4242"')

    def test_missing_token_fails_with_instructions(self):
        with Sandbox() as sb:
            _telegram_state(sb, token=False)
            proc = sb.script("setup-telegram.sh", "--no-test", **NO_ENV_TOKEN)
            self.assertFailed(proc, "sans token")
            self.assertOutputContains(proc, "/telegram:configure")

    def test_non_interactive_without_pairing_requires_chat_id(self):
        with Sandbox() as sb:
            _telegram_state(sb, allow_from=None)
            proc = sb.script("setup-telegram.sh", "--no-test", **NO_ENV_TOKEN)
            self.assertFailed(proc, "ni appairage ni --chat-id")
            self.assertOutputContains(proc, "--chat-id")

    def test_interactive_prompts_for_chat_id(self):
        with Sandbox() as sb:
            _telegram_state(sb, allow_from=None)
            proc = sb.run_pty(
                [str(sb.repo / "scripts/setup-telegram.sh"), "--no-test"],
                answers=["987654"],
                **NO_ENV_TOKEN,
            )
            self.assertSucceeded(proc, "setup-telegram.sh interactif")
            self.assertFileContains(sb.repo / "config/workspace.user.toml", 'telegram_chat_id = "987654"')

    def test_rejects_non_numeric_chat_id(self):
        with Sandbox() as sb:
            _telegram_state(sb)
            proc = sb.script("setup-telegram.sh", "--chat-id", "@moi", "--no-test", **NO_ENV_TOKEN)
            self.assertFailed(proc, "chat_id non numérique")

    def test_migrates_from_ntfy_without_losing_the_rest(self):
        """Les clés ntfy disparaissent, le reste de la config personnelle reste."""
        with Sandbox() as sb:
            _telegram_state(sb)
            cfg = sb.repo / "config/workspace.user.toml"
            cfg.parent.mkdir(exist_ok=True)
            cfg.write_text(
                '[language]\ndocuments = "en"\n\n'
                '[notifications]\n# Généré par scripts/setup-ntfy.sh\nprovider = "ntfy"\n'
                'ntfy_url = "https://ntfy.sh"\nntfy_topic = "running-coach-x"\nntfy_token_file = ""\n'
            )
            for _ in range(2):   # relancer ne duplique rien
                self.assertSucceeded(sb.script("setup-telegram.sh", "--no-test", **NO_ENV_TOKEN))
            text = cfg.read_text()
            self.assertIn('documents = "en"', text)
            self.assertIn('provider = "telegram"', text)
            self.assertNotIn("ntfy_", text)
            self.assertEqual(text.count("[notifications]"), 1, text)
            self.assertEqual(text.count("telegram_chat_id"), 1, text)

    def test_disable(self):
        with Sandbox() as sb:
            self.assertSucceeded(sb.script("setup-telegram.sh", "--disable", **NO_ENV_TOKEN))
            self.assertFileContains(sb.repo / "config/workspace.user.toml", 'provider = "none"')


class TestNotifyTelegram(InstallAsserts):
    def _configure(self, sb: Sandbox, extra: str = "") -> None:
        cfg = sb.repo / "config/workspace.user.toml"
        cfg.parent.mkdir(exist_ok=True)
        cfg.write_text(f'[notifications]\nprovider = "telegram"\n{extra}')

    def _curl_args(self, sb: Sandbox) -> str:
        # Journal brut : le texte (titre + message) contient un saut de ligne,
        # que stub_calls() prendrait pour un second appel.
        log = sb.stub_log.read_text()
        self.assertEqual(log.count("curl\t"), 1, f"un seul appel curl attendu :\n{log}")
        return log

    def test_sends_to_the_paired_chat_with_escaped_html(self):
        with Sandbox() as sb:
            _telegram_state(sb)
            self._configure(sb)
            proc = sb.script("notify.sh", "--title", "Sync <ok>", "a & b > c", **NO_ENV_TOKEN)
            self.assertSucceeded(proc)
            args = self._curl_args(sb)
            self.assertIn("https://api.telegram.org/bot123:secret/sendMessage", args)
            self.assertIn("chat_id=4242", args)
            self.assertIn("<b>Sync &lt;ok&gt;</b>", args)
            self.assertIn("a &amp; b &gt; c", args)
            self.assertIn("disable_notification=false", args)
            self.assertNotIn("123:secret", proc.stdout + proc.stderr, "token affiché")

    def test_low_priority_is_silent_and_explicit_chat_id_wins(self):
        with Sandbox() as sb:
            _telegram_state(sb)
            self._configure(sb, 'telegram_chat_id = "77"\n')
            self.assertSucceeded(sb.script("notify.sh", "--priority", "2", "--tags", "x", "msg", **NO_ENV_TOKEN))
            args = self._curl_args(sb)
            self.assertIn("chat_id=77", args)
            self.assertIn("disable_notification=true", args)

    def test_network_failure_exits_2(self):
        with Sandbox() as sb:
            _telegram_state(sb)
            self._configure(sb)
            proc = sb.script("notify.sh", "msg", ARC_STUB_FAIL="curl", **NO_ENV_TOKEN)
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertNotIn("123:secret", proc.stdout + proc.stderr, "token affiché")

    def test_legacy_ntfy_config_fails_loudly(self):
        with Sandbox() as sb:
            cfg = sb.repo / "config/workspace.user.toml"
            cfg.parent.mkdir(exist_ok=True)
            cfg.write_text('[notifications]\nprovider = "ntfy"\nntfy_topic = "t"\n')
            proc = sb.script("notify.sh", "msg", **NO_ENV_TOKEN)
            self.assertFailed(proc, "ancienne config ntfy")
            self.assertOutputContains(proc, "setup-telegram.sh")
            self.assertEqual(sb.stub_calls("curl"), [])


class TestCoachTelegram(InstallAsserts):
    def test_refuses_to_start_unless_allowlisted(self):
        with Sandbox() as sb:
            _telegram_state(sb, policy="pairing")
            proc = sb.script("coach-telegram.sh", "run", "--dry-run", **NO_ENV_TOKEN)
            self.assertFailed(proc, "politique pairing")
            self.assertOutputContains(proc, "allowlist")

    def test_pairing_mode_starts_the_channel(self):
        with Sandbox() as sb:
            _telegram_state(sb, allow_from=None)
            proc = sb.script("coach-telegram.sh", "run", "--pairing", "--dry-run", **NO_ENV_TOKEN)
            self.assertSucceeded(proc)
            self.assertOutputContains(proc, "--channels plugin:telegram@claude-plugins-official")

    def test_install_merges_permissions_without_losing_existing_rules(self):
        with Sandbox() as sb:
            _telegram_state(sb)
            settings = sb.repo / ".claude/settings.local.json"
            settings.parent.mkdir(parents=True, exist_ok=True)
            settings.write_text(json.dumps({"permissions": {"allow": ["Bash(ls:*)"]}}))
            sb.script("coach-telegram.sh", "install", **NO_ENV_TOKEN, ARC_FAKE_UNAME="Linux")
            data = json.loads(settings.read_text())
            allow, deny = data["permissions"]["allow"], data["permissions"]["deny"]
            self.assertIn("Bash(ls:*)", allow)
            self.assertIn("mcp__garmin__schedule_workouts", allow)
            self.assertIn("mcp__garmin__delete_workout", deny)
            self.assertFalse(set(allow) & set(deny), "règle à la fois autorisée et interdite")


# `coach-remote.sh:41` rajoute /opt/homebrew/bin et /usr/local/bin au PATH, hors
# de portée du bac à sable. Sur une machine qui y a screen ou tmux, « aucun
# backend » n'est pas une situation atteignable : le test le dit plutôt que de
# se croire vert. Le lint du palier B verrouille la régression partout.
HARDCODED_PATH_DIRS = ("/opt/homebrew/bin", "/usr/local/bin")


def _backend_tool_on_host() -> str | None:
    for directory in HARDCODED_PATH_DIRS:
        for tool in ("screen", "tmux"):
            if (Path(directory) / tool).exists():
                return f"{directory}/{tool}"
    return None


class TestCoachRemote(InstallAsserts):
    """0.2 — `die` dans `$(backend)` transforme une erreur fatale en succès."""

    def setUp(self):
        found = _backend_tool_on_host()
        if found:
            self.skipTest(
                f"{found} est présent et coach-remote.sh rajoute ce dossier au PATH : "
                "« aucun backend » n'est pas atteignable sur cette machine."
            )

    def test_no_backend_fails_loudly(self):
        with Sandbox() as sb:
            proc = sb.run(
                [str(sb.repo / "scripts/coach-remote.sh"), "status"],
                hide=("systemctl", "screen", "tmux"),
                ARC_FAKE_UNAME="Linux",
            )
            self.assertFailed(proc, "coach-remote.sh sans backend disponible")
            self.assertOutputContains(proc, "systemd")

    def test_no_backend_install_does_not_claim_success(self):
        with Sandbox() as sb:
            proc = sb.run(
                [str(sb.repo / "scripts/coach-remote.sh"), "install"],
                hide=("systemctl", "screen", "tmux"),
                ARC_FAKE_UNAME="Linux",
            )
            self.assertFailed(proc, "install sans backend")
            self.assertOutputLacks(proc, "Sur le téléphone")


class TestCoachRemotePrompts(InstallAsserts):
    def test_accepts_spelled_out_yes(self):
        """« oui » doit être accepté comme « o » (sinon on relance claude pour rien)."""
        with Sandbox() as sb:
            proc = sb.run_pty(
                [str(sb.repo / "scripts/coach-remote.sh"), "install"],
                answers=["oui"],
                ARC_FAKE_UNAME="Darwin",
            )
            self.assertOutputLacks(proc, "Lancement interactif")
