import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codex_title import cli


def _write_session_log(
    path: Path, session_id: str, cwd: Path, timestamp: str | None = None
) -> None:
    event = {
        "type": "session_meta",
        "payload": {"id": session_id, "cwd": str(cwd)},
    }
    if timestamp is not None:
        event["payload"]["timestamp"] = timestamp
        event["timestamp"] = timestamp
    path.write_text(json.dumps(event) + "\n", encoding="utf-8")


def _write_tui_log(path: Path, log_path: Path) -> None:
    line = f'2026-01-04T00:00:00Z  INFO Resumed rollout successfully from "{log_path}"\n'
    path.write_text(line, encoding="utf-8")


class _FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class ResumeSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.home = Path(self.tmpdir.name)
        self.codex_home = self.home / ".codex"
        self.sessions_root = self.codex_home / "sessions"
        self.sessions_root.mkdir(parents=True, exist_ok=True)
        self.cwd = self.home / "workdir"
        self.cwd.mkdir(parents=True, exist_ok=True)
        self.tui_log = self.codex_home / "log" / "codex-tui.log"
        self.tui_log.parent.mkdir(parents=True, exist_ok=True)
        self.history_log = self.codex_home / "history.jsonl"

    def test_best_log_candidate_prefers_closest_timestamp(self) -> None:
        start_iso = "2026-01-04T00:00:00Z"
        start_time = cli._parse_iso_timestamp(start_iso)
        if start_time is None:
            self.fail("Failed to parse start timestamp")

        first = self.sessions_root / "rollout-first.jsonl"
        second = self.sessions_root / "rollout-second.jsonl"
        _write_session_log(first, "first", self.cwd, "2026-01-04T00:00:01Z")
        _write_session_log(second, "second", self.cwd, "2026-01-04T00:00:05Z")
        os.utime(first, (1_000_000, 1_000_000))
        os.utime(second, (1_000_100, 1_000_100))

        chosen = cli._best_log_candidate(
            [(first.stat().st_mtime, first), (second.stat().st_mtime, second)],
            start_time,
            self.cwd,
        )
        self.assertEqual(chosen, first)

    def test_best_log_candidate_prefers_cwd_match(self) -> None:
        start_iso = "2026-01-04T00:00:00Z"
        start_time = cli._parse_iso_timestamp(start_iso)
        if start_time is None:
            self.fail("Failed to parse start timestamp")

        other_cwd = self.home / "other"
        other_cwd.mkdir(parents=True, exist_ok=True)

        first = self.sessions_root / "rollout-first.jsonl"
        second = self.sessions_root / "rollout-second.jsonl"
        _write_session_log(first, "first", other_cwd, "2026-01-04T00:00:01Z")
        _write_session_log(second, "second", self.cwd, "2026-01-04T00:00:10Z")
        os.utime(first, (1_000_000, 1_000_000))
        os.utime(second, (1_000_100, 1_000_100))

        chosen = cli._best_log_candidate(
            [(first.stat().st_mtime, first), (second.stat().st_mtime, second)],
            start_time,
            self.cwd,
        )
        self.assertEqual(chosen, second)

    def test_best_log_candidate_ignores_skewed_meta_timestamp(self) -> None:
        start_iso = "2026-01-04T00:00:00Z"
        start_time = cli._parse_iso_timestamp(start_iso)
        if start_time is None:
            self.fail("Failed to parse start timestamp")

        first = self.sessions_root / "rollout-first.jsonl"
        second = self.sessions_root / "rollout-second.jsonl"
        _write_session_log(first, "first", self.cwd, "2026-01-04T00:10:00Z")
        _write_session_log(second, "second", self.cwd, "2026-01-04T00:20:00Z")
        os.utime(first, (start_time + 1, start_time + 1))
        os.utime(second, (start_time + 2, start_time + 2))

        with mock.patch.object(cli, "_CLOCK_SKEW_SECS", 60.0):
            chosen = cli._best_log_candidate(
                [(first.stat().st_mtime, first), (second.stat().st_mtime, second)],
                start_time,
                self.cwd,
            )
        self.assertEqual(chosen, first)

    def test_resume_log_from_tui_matches_cwd(self) -> None:
        session_id = "session-abc"
        log_path = self.sessions_root / f"rollout-{session_id}.jsonl"
        _write_session_log(log_path, session_id, self.cwd)
        _write_tui_log(self.tui_log, log_path)

        result = cli._resume_log_from_tui(self.tui_log, self.cwd)
        self.assertEqual(result, log_path)

    def test_resume_log_from_tui_fallbacks_when_cwd_mismatch(self) -> None:
        session_id = "session-def"
        other_cwd = self.home / "other"
        other_cwd.mkdir(parents=True, exist_ok=True)
        log_path = self.sessions_root / f"rollout-{session_id}.jsonl"
        _write_session_log(log_path, session_id, other_cwd)
        _write_tui_log(self.tui_log, log_path)

        result = cli._resume_log_from_tui(self.tui_log, self.cwd)
        self.assertEqual(result, log_path)

    def test_status_log_path_prefers_tui(self) -> None:
        session_id = "session-tui"
        log_path = self.sessions_root / f"rollout-{session_id}.jsonl"
        _write_session_log(log_path, session_id, self.cwd)
        _write_tui_log(self.tui_log, log_path)

        with mock.patch.object(cli, "TUI_LOG_PATH", self.tui_log):
            path, source = cli._status_log_path(self.sessions_root, self.cwd)

        self.assertEqual(path, log_path)
        self.assertEqual(source, "tui")

    def test_status_log_path_uses_history(self) -> None:
        session_id = "session-history"
        log_path = self.sessions_root / f"rollout-{session_id}.jsonl"
        _write_session_log(log_path, session_id, self.cwd)
        self.history_log.write_text(json.dumps({"session_id": session_id}) + "\n", encoding="utf-8")

        with mock.patch.object(cli, "TUI_LOG_PATH", self.tui_log), mock.patch.object(
            cli, "HISTORY_LOG_PATH", self.history_log
        ), mock.patch.object(cli.Path, "home", return_value=self.home):
            path, source = cli._status_log_path(self.sessions_root, self.cwd)

        self.assertEqual(path, log_path)
        self.assertEqual(source, "history")

    def test_status_log_path_uses_session_dir(self) -> None:
        session_dir = self.sessions_root / "2026" / "01" / "04"
        session_dir.mkdir(parents=True, exist_ok=True)
        older = session_dir / "rollout-older.jsonl"
        newer = session_dir / "rollout-newer.jsonl"
        _write_session_log(older, "older", self.cwd)
        _write_session_log(newer, "newer", self.cwd)
        os.utime(older, (1_000_000, 1_000_000))
        os.utime(newer, (1_000_100, 1_000_100))

        with mock.patch.object(cli, "TUI_LOG_PATH", self.tui_log), mock.patch.object(
            cli, "HISTORY_LOG_PATH", self.history_log
        ):
            path, source = cli._status_log_path(session_dir, self.cwd)

        self.assertEqual(path, newer)
        self.assertEqual(source, "session_dir")

    def test_wait_for_log_keeps_polling_pid_after_timeout(self) -> None:
        session_dir = self.sessions_root / "2026" / "01" / "04"
        session_dir.mkdir(parents=True, exist_ok=True)
        log_path = session_dir / "rollout-resume.jsonl"
        log_path.write_text("", encoding="utf-8")

        clock = _FakeClock()

        def fake_log_path(_pid: int) -> Path | None:
            if clock.now >= 5.0:
                return log_path
            return None

        stop_event = threading.Event()

        with mock.patch.object(cli, "_log_path_from_pid", side_effect=fake_log_path), mock.patch.object(
            cli, "_PID_LOG_TIMEOUT_SECS", 1.0
        ), mock.patch.object(cli.time, "time", clock.time), mock.patch.object(
            cli.time, "sleep", clock.sleep
        ):
            path, source = cli.wait_for_log(
                session_dir,
                start_time=clock.time(),
                stop_event=stop_event,
                allow_external_switch=False,
                codex_pid=123,
                fallback_after=-1.0,
            )

        self.assertEqual(path, log_path)
        self.assertEqual(source, "pid")
        self.assertGreaterEqual(clock.now, 5.0)

    def test_wait_for_log_prefers_pid_over_session_dir(self) -> None:
        session_dir = self.sessions_root / "2026" / "01" / "04"
        session_dir.mkdir(parents=True, exist_ok=True)
        session_log = session_dir / "rollout-session.jsonl"
        session_log.write_text("", encoding="utf-8")
        pid_log = session_dir / "rollout-pid.jsonl"
        pid_log.write_text("", encoding="utf-8")

        clock = _FakeClock()

        def fake_log_path(_pid: int) -> Path | None:
            if clock.now >= 3.0:
                return pid_log
            return None

        stop_event = threading.Event()

        with mock.patch.object(cli, "_log_path_from_pid", side_effect=fake_log_path), mock.patch.object(
            cli, "_PID_LOG_TIMEOUT_SECS", 1.0
        ), mock.patch.object(cli, "_PID_LOG_AVAILABLE", True), mock.patch.object(
            cli.time, "time", clock.time
        ), mock.patch.object(cli.time, "sleep", clock.sleep):
            path, source = cli.wait_for_log(
                session_dir,
                start_time=clock.time(),
                stop_event=stop_event,
                allow_external_switch=False,
                codex_pid=123,
                fallback_after=-1.0,
            )

        self.assertEqual(path, pid_log)
        self.assertEqual(source, "pid")

    def test_switch_state_prefers_pid(self) -> None:
        session_dir = self.sessions_root / "2026" / "01" / "04"
        session_dir.mkdir(parents=True, exist_ok=True)
        log_path = session_dir / "rollout-session.jsonl"
        pid_path = session_dir / "rollout-pid.jsonl"
        log_path.write_text("", encoding="utf-8")
        pid_path.write_text("", encoding="utf-8")

        clock = _FakeClock()
        state = cli.SwitchState(
            log_path=log_path,
            sessions_root=self.sessions_root,
            cwd=self.cwd,
            start_time=clock.time(),
            allow_external_switch=False,
            codex_pid=123,
        )

        with mock.patch.object(cli, "_log_path_from_pid", return_value=pid_path), mock.patch.object(
            cli, "_PID_LOG_AVAILABLE", True
        ), mock.patch.object(cli.time, "time", clock.time):
            clock.now = 2.0
            state.maybe_switch()

        self.assertEqual(state.next_path, pid_path)
