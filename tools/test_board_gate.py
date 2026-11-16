"""Budget/ownership regressions; never call GitHub or an LLM."""
import unittest
from unittest.mock import patch
import tempfile
from pathlib import Path
import board_gate as gate


class GateTests(unittest.TestCase):
    def test_cooldown_is_rolling_not_just_clock_hour(self):
        with self.assertRaises(gate.GateError):
            gate.check_cooldown(7201, {"started": 7199})
        gate.check_cooldown(10800, {"started": 7200})

    def test_other_owner_or_token_cannot_release(self):
        for record in (None, {"owner": "claude", "token": "x"}, {"owner": "codex", "token": "y"}):
            with self.assertRaises(gate.GateError):
                gate.validate_lease(record, {"token": "x"}, "codex")

    @patch.object(gate, "api")
    @patch.object(gate, "ref_record", return_value={"owner": "claude"})
    def test_existing_task_refuses_all_mutations(self, read, api):
        with self.assertRaises(gate.GateError):
            gate.claim("codex", "case inventory", Path("unused"), 7200)
        api.assert_not_called()

    @patch.object(gate, "api")
    @patch.object(gate, "ref_record", return_value=None)
    def test_failed_atomic_acquire_never_authorizes_work(self, read, api):
        api.side_effect = [{"object": {"sha": "commit"}}, {"sha": "tag"}, gate.GateError("race lost")]
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            with self.assertRaises(gate.GateError):
                gate.claim("codex", "case inventory", state, 7200)
            self.assertFalse((state / "lease.json").exists())

    @patch.object(gate, "api")
    @patch.object(gate, "ref_record", side_effect=[None, None, None, {"started": 7199}])
    def test_race_after_mutex_rechecks_budget_and_cleans_up(self, read, api):
        api.side_effect = [{"object": {"sha": "commit"}}, {"sha": "tag"}, {}, None]
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(gate.GateError):
                gate.claim("codex", "case inventory", Path(directory), 7201)
        self.assertEqual(api.call_args.args, (f"{gate.BASE}/refs/{gate.ACTIVE}", "DELETE"))


if __name__ == "__main__":
    unittest.main()
