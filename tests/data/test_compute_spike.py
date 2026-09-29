"""Palier D — spike de charge : dimension distance (Nielsen 2025) et dimensions trail exploratoires."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "skills" / "session-load-spike" / "scripts" / "compute_spike.py"
sys.path.insert(0, str(SCRIPT.parent))
import compute_spike as S  # noqa: E402


def write_activity(folder: Path, day: str, sport: str, **arc) -> Path:
    block = {"arc": 1, "kind": "activity", "date": day, "sport": sport, **arc}
    path = folder / f"{day}_{sport}.md"
    path.write_text(f"# {sport}\n\n```arc\n{json.dumps(block)}\n```\n", encoding="utf-8")
    return path


def run(*args: str) -> str:
    return subprocess.run([sys.executable, str(SCRIPT), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


class TestMinetti(unittest.TestCase):
    def test_flat_is_reference(self):
        self.assertAlmostEqual(S.minetti_cost(0.0), 3.6)

    def test_uphill_costlier_moderate_downhill_cheaper(self):
        self.assertGreater(S.minetti_cost(0.10), S.minetti_cost(0.0))
        self.assertLess(S.minetti_cost(-0.10), S.minetti_cost(0.0))

    def test_grade_is_clamped(self):
        self.assertEqual(S.minetti_cost(0.8), S.minetti_cost(0.45))


class TestDimensions(unittest.TestCase):
    def test_flat_road_effort_equals_distance(self):
        act = {"type": "running", "distance_km": 10.0, "elevation_gain_m": 0, "elevation_loss_m": 0}
        self.assertAlmostEqual(S.effort_km(act), 10.0)

    def test_climbing_raises_effort(self):
        flat = {"type": "trail", "distance_km": 20.0, "elevation_gain_m": 0, "elevation_loss_m": 0}
        hilly = {**flat, "elevation_gain_m": 800, "elevation_loss_m": 800}
        self.assertGreater(S.effort_km(hilly), S.effort_km(flat))

    def test_loop_descent_not_discounted_below_flat(self):
        """Boucle 20 km / 640 m : la descente ne rembourse pas la montée (≈ km + D+/100, ITRA)."""
        loop = {"type": "running", "distance_km": 20.26, "elevation_gain_m": 637, "elevation_loss_m": 639}
        self.assertGreater(S.effort_km(loop), 23.5)
        self.assertLess(S.effort_km(loop), 26.6)

    def test_terrain_multiplies_effort(self):
        base = {"type": "running", "distance_km": 10.0, "elevation_gain_m": 0, "elevation_loss_m": 0}
        self.assertAlmostEqual(S.effort_km({**base, "terrain": "technique"}), 12.0)

    def test_steep_descent_weighted(self):
        split = {"type": "trail", "distance_km": 1.0, "splits_cols": ["km", "elev_gain_m", "elev_loss_m"]}
        gentle = S.eccentric_load({**split, "splits": [[1, 0, 50]]})
        steep = S.eccentric_load({**split, "splits": [[1, 0, 150]]})
        self.assertEqual(gentle, 50)
        self.assertEqual(steep, 225)

    def test_missing_data_gives_none(self):
        act = {"type": "running", "distance_km": 10.0}
        self.assertIsNone(S.effort_km(act))
        self.assertIsNone(S.srpe(act))


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        write_activity(self.dir, "2026-09-10", "running", distance_m=15000, duration_s=4800,
                       elevation_gain_m=50, elevation_loss_m=50, rpe=4)

    def tearDown(self):
        self.tmp.cleanup()

    def test_distance_only_output_unchanged(self):
        out = run("--date", "2026-09-20", "--distance-km", "15", "--dir", str(self.dir), "--quiet")
        self.assertEqual(out, "🟢 Référence (1.00×) — 15.0 km vs 15.0 km le 2026-09-10")

    def test_trail_dimension_surfaces_when_worse(self):
        out = run("--date", "2026-09-20", "--distance-km", "15", "--elevation-gain-m", "1000",
                  "--dir", str(self.dir), "--quiet")
        self.assertTrue(out.startswith("🟢 Référence (1.00×)"))
        self.assertIn("exploratoire", out)

    def test_partial_baseline_stays_silent(self):
        (self.dir / "2026-09-12_running.md").write_text(
            "| Distance | 8,00 km |\n", encoding="utf-8")
        out = run("--date", "2026-09-20", "--distance-km", "15", "--elevation-gain-m", "1000",
                  "--dir", str(self.dir), "--quiet")
        self.assertNotIn("exploratoire", out)

    def test_excluded_session_ignored_in_baseline(self):
        write_activity(self.dir, "2026-09-12", "trail", distance_m=40000, duration_s=20000,
                       exclude_from_load=True)
        out = run("--date", "2026-09-20", "--distance-km", "15", "--dir", str(self.dir), "--quiet")
        self.assertIn("vs 15.0 km le 2026-09-10", out)

    def test_from_file(self):
        path = write_activity(self.dir, "2026-09-20", "trail", distance_m=15000, duration_s=7200,
                              elevation_gain_m=900, elevation_loss_m=900, rpe=6, terrain="single")
        out = run("--from-file", str(path), "--dir", str(self.dir))
        self.assertIn("km-effort", out)
        self.assertIn("sRPE", out)


if __name__ == "__main__":
    unittest.main()
