import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codex_title import cli


_BASE_TIME = datetime.now(timezone.utc) - timedelta(seconds=10)


def _ts(offset_seconds: float) -> str:
    return (_BASE_TIME + timedelta(seconds=offset_seconds)).isoformat()


def _event(ts: str, etype: str, payload: dict | None = None) -> dict:
    data = {"timestamp": ts, "type": etype}
    if payload is not None:
        data["payload"] = payload
    return data


_TMP_DIRS: list[tempfile.TemporaryDirectory] = []


def _write_log(events: list[dict]) -> Path:
    tmpdir = tempfile.TemporaryDirectory()
    _TMP_DIRS.append(tmpdir)
    path = Path(tmpdir.name) / "rollout-test.jsonl"
    path.write_text(
        "\n".join(json.dumps(event) for event in events) + "\n",
        encoding="utf-8",
    )
    return path


class CollectLogStateTests(unittest.TestCase):
    def test_bootstrap_message_is_ignored(self) -> None:
        events = [
            _event(
                _ts(0),
                "event_msg",
                {"type": "user_message", "message": "# AGENTS.md instructions foo"},
            ),
        ]
        path = _write_log(events)
        pending_user, seen_assistant, _, _, _ = cli._collect_log_state(path, history_seen=False)
        self.assertFalse(pending_user)
        self.assertFalse(seen_assistant)

    def test_user_to_agent_message_marks_done(self) -> None:
        events = [
            _event(
                _ts(0),
                "event_msg",
                {"type": "user_message", "message": "Hello"},
            ),
            _event(_ts(1), "event_msg", {"type": "agent_message"}),
        ]
        path = _write_log(events)
        pending_user, seen_assistant, _, last_assistant_ts, _ = cli._collect_log_state(
            path, history_seen=True
        )
        self.assertFalse(pending_user)
        self.assertTrue(seen_assistant)
        self.assertIsNotNone(last_assistant_ts)

    def test_tool_only_turn_fallback_marks_done(self) -> None:
        events = [
            _event(
                _ts(0),
                "event_msg",
                {"type": "user_message", "message": "Run tool"},
            ),
            _event(_ts(1), "response_item", {"type": "reasoning"}),
            _event(
                _ts(2),
                "response_item",
                {"type": "function_call", "call_id": "call_1", "name": "exec_command"},
            ),
            _event(
                _ts(3),
                "response_item",
                {"type": "function_call_output", "call_id": "call_1", "output": "Exit code: 0"},
            ),
            _event(_ts(4), "event_msg", {"type": "token_count"}),
        ]
        path = _write_log(events)
        pending_user, seen_assistant, _, last_assistant_ts, _ = cli._collect_log_state(
            path, history_seen=True
        )
        self.assertFalse(pending_user)
        self.assertTrue(seen_assistant)
        self.assertIsNotNone(last_assistant_ts)

    def test_tool_only_turn_skew_does_not_mark_done(self) -> None:
        events = [
            _event(
                _ts(0),
                "event_msg",
                {"type": "user_message", "message": "Run tool"},
            ),
            _event(_ts(1), "response_item", {"type": "reasoning"}),
            _event(
                _ts(2),
                "response_item",
                {"type": "function_call", "call_id": "call_1", "name": "exec_command"},
            ),
            _event(
                _ts(3),
                "response_item",
                {"type": "function_call_output", "call_id": "call_1", "output": "Exit code: 0"},
            ),
            _event(_ts(4), "event_msg", {"type": "token_count"}),
        ]
        path = _write_log(events)
        skew_now = (_BASE_TIME + timedelta(hours=1)).timestamp()
        with mock.patch.object(cli, "_CLOCK_SKEW_SECS", 60.0), mock.patch.object(
            cli.time, "time", return_value=skew_now
        ):
            pending_user, seen_assistant, _, _, _ = cli._collect_log_state(path, history_seen=True)
        self.assertTrue(pending_user)
        self.assertFalse(seen_assistant)

    def test_pending_tool_call_keeps_running(self) -> None:
        events = [
            _event(
                _ts(0),
                "event_msg",
                {"type": "user_message", "message": "Run tool"},
            ),
            _event(
                _ts(1),
                "response_item",
                {"type": "function_call", "call_id": "call_1", "name": "exec_command"},
            ),
        ]
        path = _write_log(events)
        pending_user, seen_assistant, _, _, _ = cli._collect_log_state(path, history_seen=True)
        self.assertTrue(pending_user)
        self.assertFalse(seen_assistant)

    def test_git_commit_detected_from_tool_output(self) -> None:
        events = [
            _event(
                _ts(0),
                "event_msg",
                {"type": "user_message", "message": "Commit"},
            ),
            _event(
                _ts(1),
                "response_item",
                {
                    "type": "function_call",
                    "call_id": "call_1",
                    "name": "exec_command",
                    "arguments": json.dumps({"cmd": "git commit -m \"msg\""}),
                },
            ),
            _event(
                _ts(2),
                "response_item",
                {
                    "type": "function_call_output",
                    "call_id": "call_1",
                    "output": "Exit code: 0",
                },
            ),
            _event(_ts(3), "event_msg", {"type": "agent_message"}),
        ]
        path = _write_log(events)
        _, _, _, _, last_turn_commit = cli._collect_log_state(path, history_seen=True)
        self.assertTrue(last_turn_commit)


class IdleDoneTests(unittest.TestCase):
    def test_idle_done_requires_activity(self) -> None:
        now = 10.0
        self.assertFalse(cli._should_idle_done(True, True, set(), None, now, 1.0))

    def test_idle_done_requires_no_pending_calls(self) -> None:
        now = 10.0
        last = 8.0
        self.assertFalse(cli._should_idle_done(True, True, {"call_1"}, last, now, 1.0))

    def test_idle_done_triggers_after_timeout(self) -> None:
        now = 10.0
        last = 8.5
        self.assertTrue(cli._should_idle_done(True, True, set(), last, now, 1.0))
