#!/usr/bin/env python3
"""Wrapper to run Codex with automatic terminal tab title updates."""

from __future__ import annotations

import argparse
import io
import json
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

DEFAULT_RUNNING = "codex:running..."
DEFAULT_DONE = "codex:✅"
DEFAULT_NEW = "codex:new"


class TitleWriter:
    def __init__(self) -> None:
        self._stream = None
        try:
            self._stream = open("/dev/tty", "wb", buffering=0)
        except Exception:
            self._stream = getattr(sys.stdout, "buffer", sys.stdout)

    def set(self, title: str) -> None:
        seq = f"\033]0;{title}\007"
        try:
            if isinstance(self._stream, (io.BufferedIOBase, io.RawIOBase)):
                self._stream.write(seq.encode("utf-8", errors="ignore"))
            else:
                self._stream.write(seq)
            self._stream.flush()
        except Exception:
            pass


def _parse_timestamp(event: dict) -> float | None:
    ts = event.get("timestamp")
    if not isinstance(ts, str):
        return None
    try:
        if ts.endswith("Z"):
            ts = f"{ts[:-1]}+00:00"
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


def iter_jsonl(
    path: Path,
    stop_event: threading.Event,
    start_time: float | None,
) -> Iterable[dict]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            data = _parse_json(line)
            if data is not None and _should_emit(data, start_time):
                yield data
        while not stop_event.is_set():
            line = handle.readline()
            if not line:
                time.sleep(0.1)
                continue
            data = _parse_json(line)
            if data is not None and _should_emit(data, start_time):
                yield data


def _parse_json(line: str) -> dict | None:
    try:
        return json.loads(line)
    except Exception:
        return None


def _should_emit(event: dict, start_time: float | None) -> bool:
    if start_time is None:
        return True
    ts = _parse_timestamp(event)
    if ts is None:
        return False
    return ts >= start_time


def session_dir_for_time(epoch: float) -> Path:
    tm = time.localtime(epoch)
    return (
        Path.home()
        / ".codex"
        / "sessions"
        / f"{tm.tm_year:04d}"
        / f"{tm.tm_mon:02d}"
        / f"{tm.tm_mday:02d}"
    )


def _latest_log(session_dir: Path) -> Path | None:
    if not session_dir.exists():
        return None
    latest: tuple[float, Path] | None = None
    for path in session_dir.glob("rollout-*.jsonl"):
        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError:
            continue
        if latest is None or mtime > latest[0]:
            latest = (mtime, path)
    return latest[1] if latest else None


def wait_for_log(
    session_dir: Path,
    start_time: float,
    stop_event: threading.Event,
    fallback_after: float = 2.0,
) -> Path | None:
    existing = set(session_dir.glob("rollout-*.jsonl")) if session_dir.exists() else set()
    started = time.time()
    while not stop_event.is_set():
        if session_dir.exists():
            candidates = []
            for path in session_dir.glob("rollout-*.jsonl"):
                try:
                    mtime = path.stat().st_mtime
                except FileNotFoundError:
                    continue
                if mtime >= start_time - 1 and (path not in existing or not existing):
                    candidates.append((mtime, path))
            if candidates:
                return max(candidates, key=lambda item: item[0])[1]
        if fallback_after >= 0 and time.time() - started >= fallback_after:
            return _latest_log(session_dir)
        time.sleep(0.2)
    return None


def watch_log(
    log_path: Path,
    title: TitleWriter,
    running_title: str,
    done_title: str,
    stop_event: threading.Event,
    start_time: float | None,
) -> None:
    pending_user = False
    for event in iter_jsonl(log_path, stop_event, start_time):
        if stop_event.is_set():
            break
        etype = event.get("type")
        payload = event.get("payload") or {}
        if etype == "event_msg":
            msg_type = payload.get("type")
            if msg_type == "user_message":
                pending_user = True
            elif msg_type in {"agent_message", "assistant_message", "turn_aborted"}:
                pending_user = False
                title.set(done_title)
        elif etype == "response_item" and payload.get("type") == "message":
            role = payload.get("role")
            if role == "user":
                pending_user = True
            elif role == "assistant":
                pending_user = False
                title.set(done_title)
        elif etype == "response_item" and payload.get("type") in {"reasoning", "function_call"}:
            if pending_user:
                title.set(running_title)


def start_watcher(
    log_path: Path | None,
    session_dir: Path,
    start_time: float,
    title: TitleWriter,
    running_title: str,
    done_title: str,
    stop_event: threading.Event,
) -> threading.Thread:
    def _run() -> None:
        path = log_path or wait_for_log(session_dir, start_time, stop_event)
        if not path:
            return
        watch_log(path, title, running_title, done_title, stop_event, start_time)

    thread = threading.Thread(target=_run, name="codex-title-watch", daemon=True)
    thread.start()
    return thread


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Codex with terminal tab title updates based on session logs."
    )
    parser.add_argument(
        "--watch-only",
        action="store_true",
        help="Only watch logs; do not start Codex.",
    )
    parser.add_argument(
        "--log",
        type=Path,
        help="Explicit Codex session log to watch.",
    )
    parser.add_argument(
        "--session-dir",
        type=Path,
        help="Override Codex session directory (defaults to today's).",
    )
    parser.add_argument(
        "--new-title",
        default=DEFAULT_NEW,
        help="Title to set on session start before any prompts.",
    )
    parser.add_argument(
        "--running-title",
        default=DEFAULT_RUNNING,
        help="Title to set while Codex is running.",
    )
    parser.add_argument(
        "--done-title",
        default=DEFAULT_DONE,
        help="Title to set when Codex finishes a response.",
    )
    parser.add_argument(
        "--yolo",
        action="store_true",
        help="Run Codex with --dangerously-bypass-approvals-and-sandbox.",
    )
    parser.add_argument(
        "codex_args",
        nargs=argparse.REMAINDER,
        help="Arguments to pass to codex after --",
    )
    args = parser.parse_args()
    if args.codex_args[:1] == ["--"]:
        args.codex_args = args.codex_args[1:]
    return args


def main() -> int:
    args = parse_args()
    title = TitleWriter()
    title.set(args.new_title)

    stop_event = threading.Event()

    def _signal_handler(_signum: int, _frame: object) -> None:
        stop_event.set()
        title.set(args.done_title)

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    session_dir = args.session_dir or session_dir_for_time(time.time())
    watcher = start_watcher(
        args.log,
        session_dir,
        time.time(),
        title,
        args.running_title,
        args.done_title,
        stop_event,
    )

    if args.watch_only:
        try:
            while watcher.is_alive():
                time.sleep(0.2)
        finally:
            stop_event.set()
            title.set(args.done_title)
        return 0

    codex_args = list(args.codex_args)
    if args.yolo and "--dangerously-bypass-approvals-and-sandbox" not in codex_args:
        codex_args = ["--dangerously-bypass-approvals-and-sandbox", *codex_args]
    cmd = ["codex"] + codex_args
    try:
        return subprocess.call(cmd)
    finally:
        stop_event.set()
        title.set(args.done_title)


if __name__ == "__main__":
    raise SystemExit(main())
