import Foundation
import Testing
import Darwin
@testable import LibprocPoc

private func openTempFile(named name: String) throws -> (URL, FileHandle) {
    let dir = FileManager.default.temporaryDirectory
    let url = dir.appendingPathComponent(name)
    FileManager.default.createFile(atPath: url.path, contents: Data(), attributes: nil)
    let handle = try FileHandle(forUpdating: url)
    return (url, handle)
}

private func normalizedPath(_ path: String) -> String {
    URL(fileURLWithPath: path).resolvingSymlinksInPath().path
}

private func normalizedURLPath(_ url: URL?) -> String? {
    url.map { normalizedPath($0.path) }
}

private enum LibprocPocTestError: Error {
    case tailMissing
    case invalidTimestamp
}

private func tailExecutableURL() -> URL? {
    let candidates = ["/usr/bin/tail", "/bin/tail"]
    for path in candidates {
        if FileManager.default.isExecutableFile(atPath: path) {
            return URL(fileURLWithPath: path)
        }
    }
    return nil
}

private func spawnTailProcess(url: URL) throws -> Process {
    guard let tailURL = tailExecutableURL() else {
        throw LibprocPocTestError.tailMissing
    }
    let process = Process()
    process.executableURL = tailURL
    process.arguments = ["-n", "0", "-f", url.path]
    process.standardOutput = FileHandle.nullDevice
    process.standardError = FileHandle.nullDevice
    try process.run()
    return process
}

private func waitForOpenPath(pid: pid_t, path: String, timeout: TimeInterval) throws -> Bool {
    let target = normalizedPath(path)
    let deadline = Date().addingTimeInterval(timeout)
    while Date() < deadline {
        let paths = try Libproc.openFilePaths(pid: pid).map(normalizedPath)
        if paths.contains(target) {
            return true
        }
        Thread.sleep(forTimeInterval: 0.05)
    }
    return false
}

private func writeSessionLog(path: URL, sessionId: String, cwd: URL, timestamp: String?) throws {
    var payload: [String: Any] = [
        "id": sessionId,
        "cwd": cwd.path,
    ]
    var event: [String: Any] = [
        "type": "session_meta",
        "payload": payload,
    ]
    if let timestamp {
        payload["timestamp"] = timestamp
        event["payload"] = payload
        event["timestamp"] = timestamp
    }
    var data = try JSONSerialization.data(withJSONObject: event, options: [])
    data.append(0x0a)
    try data.write(to: path)
}

private func setMtime(path: URL, epochSeconds: TimeInterval) throws {
    let date = Date(timeIntervalSince1970: epochSeconds)
    try FileManager.default.setAttributes([.modificationDate: date], ofItemAtPath: path.path)
}

private func writeHistoryLog(path: URL, sessionId: String) throws {
    let event: [String: Any] = ["session_id": sessionId]
    var data = try JSONSerialization.data(withJSONObject: event, options: [])
    data.append(0x0a)
    try data.write(to: path)
}

private func writeTuiLog(path: URL, logPath: URL) throws {
    let line = "2026-01-04T00:00:00Z  INFO Resumed rollout successfully from \"\(logPath.path)\"\n"
    try line.write(to: path, atomically: true, encoding: .utf8)
}

private func createCodexHome() throws -> URL {
    let root = FileManager.default.temporaryDirectory.appendingPathComponent(
        "codex-home-\(UUID().uuidString)"
    )
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    try FileManager.default.createDirectory(
        at: root.appendingPathComponent("log"),
        withIntermediateDirectories: true
    )
    try FileManager.default.createDirectory(
        at: root.appendingPathComponent("sessions"),
        withIntermediateDirectories: true
    )
    return root
}

@Test func openFilePathsIncludesTempFile() throws {
    let (url, handle) = try openTempFile(named: "libproc-poc-\(UUID().uuidString).txt")
    defer {
        try? handle.close()
        try? FileManager.default.removeItem(at: url)
    }

    let paths = try Libproc.openFilePaths(pid: getpid()).map(normalizedPath)
    #expect(paths.contains(normalizedPath(url.path)))
}

@Test func openRolloutLogsFiltersByName() throws {
    let (logURL, logHandle) = try openTempFile(named: "rollout-\(UUID().uuidString).jsonl")
    let (otherURL, otherHandle) = try openTempFile(named: "not-rollout-\(UUID().uuidString).txt")
    defer {
        try? logHandle.close()
        try? otherHandle.close()
        try? FileManager.default.removeItem(at: logURL)
        try? FileManager.default.removeItem(at: otherURL)
    }

    let paths = try Libproc.openRolloutLogs(pid: getpid()).map(normalizedPath)
    #expect(paths.contains(normalizedPath(logURL.path)))
    #expect(!paths.contains(normalizedPath(otherURL.path)))
}

@Test func openFilePathsIncludesChildProcessFile() throws {
    let (url, handle) = try openTempFile(named: "rollout-\(UUID().uuidString).jsonl")
    let process = try spawnTailProcess(url: url)
    defer {
        if process.isRunning {
            process.terminate()
        }
        process.waitUntilExit()
        try? handle.close()
        try? FileManager.default.removeItem(at: url)
    }

    let pid = process.processIdentifier
    let found = try waitForOpenPath(pid: pid, path: url.path, timeout: 1.0)
    #expect(found)
}

@Test func bestLogCandidatePrefersClosestTimestamp() throws {
    let tmpdir = FileManager.default.temporaryDirectory.appendingPathComponent(
        "log-selection-\(UUID().uuidString)"
    )
    try FileManager.default.createDirectory(at: tmpdir, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: tmpdir) }
    let startIso = "2026-01-04T00:00:00Z"
    guard let startTime = LogSelection.parseIsoTimestamp(startIso) else {
        throw LibprocPocTestError.invalidTimestamp
    }
    let cwd = tmpdir.appendingPathComponent("cwd")
    try FileManager.default.createDirectory(at: cwd, withIntermediateDirectories: true)

    let first = tmpdir.appendingPathComponent("rollout-first-\(UUID().uuidString).jsonl")
    let second = tmpdir.appendingPathComponent("rollout-second-\(UUID().uuidString).jsonl")
    try writeSessionLog(path: first, sessionId: "first", cwd: cwd, timestamp: "2026-01-04T00:00:01Z")
    try writeSessionLog(path: second, sessionId: "second", cwd: cwd, timestamp: "2026-01-04T00:00:05Z")
    try setMtime(path: first, epochSeconds: 1_000_000)
    try setMtime(path: second, epochSeconds: 1_000_100)

    let metaFirst = LogSelection.sessionMetaTimestamp(path: first)
    let metaSecond = LogSelection.sessionMetaTimestamp(path: second)
    #expect(metaFirst != nil)
    #expect(metaSecond != nil)

    let chosen = LogSelection.bestLogCandidate(
        [(mtime: 1_000_000, path: first), (mtime: 1_000_100, path: second)],
        startTime: startTime,
        cwd: cwd
    )
    #expect(chosen == first)
}

@Test func bestLogCandidatePrefersCwdMatch() throws {
    let tmpdir = FileManager.default.temporaryDirectory.appendingPathComponent(
        "log-selection-\(UUID().uuidString)"
    )
    try FileManager.default.createDirectory(at: tmpdir, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: tmpdir) }
    let startIso = "2026-01-04T00:00:00Z"
    guard let startTime = LogSelection.parseIsoTimestamp(startIso) else {
        throw LibprocPocTestError.invalidTimestamp
    }
    let cwd = tmpdir.appendingPathComponent("cwd")
    let otherCwd = tmpdir.appendingPathComponent("other")
    try FileManager.default.createDirectory(at: cwd, withIntermediateDirectories: true)
    try FileManager.default.createDirectory(at: otherCwd, withIntermediateDirectories: true)

    let first = tmpdir.appendingPathComponent("rollout-first-\(UUID().uuidString).jsonl")
    let second = tmpdir.appendingPathComponent("rollout-second-\(UUID().uuidString).jsonl")
    try writeSessionLog(path: first, sessionId: "first", cwd: otherCwd, timestamp: "2026-01-04T00:00:01Z")
    try writeSessionLog(path: second, sessionId: "second", cwd: cwd, timestamp: "2026-01-04T00:00:10Z")
    try setMtime(path: first, epochSeconds: 1_000_000)
    try setMtime(path: second, epochSeconds: 1_000_100)

    let chosen = LogSelection.bestLogCandidate(
        [(mtime: 1_000_000, path: first), (mtime: 1_000_100, path: second)],
        startTime: startTime,
        cwd: cwd
    )
    #expect(chosen == second)
}

@Test func bestLogCandidateIgnoresSkewedMetaTimestamp() throws {
    let tmpdir = FileManager.default.temporaryDirectory.appendingPathComponent(
        "log-selection-\(UUID().uuidString)"
    )
    try FileManager.default.createDirectory(at: tmpdir, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: tmpdir) }
    let startIso = "2026-01-04T00:00:00Z"
    guard let startTime = LogSelection.parseIsoTimestamp(startIso) else {
        throw LibprocPocTestError.invalidTimestamp
    }
    let cwd = tmpdir.appendingPathComponent("cwd")
    try FileManager.default.createDirectory(at: cwd, withIntermediateDirectories: true)

    let first = tmpdir.appendingPathComponent("rollout-first-\(UUID().uuidString).jsonl")
    let second = tmpdir.appendingPathComponent("rollout-second-\(UUID().uuidString).jsonl")
    try writeSessionLog(path: first, sessionId: "first", cwd: cwd, timestamp: "2026-01-04T00:10:00Z")
    try writeSessionLog(path: second, sessionId: "second", cwd: cwd, timestamp: "2026-01-04T00:20:00Z")
    try setMtime(path: first, epochSeconds: startTime + 1)
    try setMtime(path: second, epochSeconds: startTime + 2)

    let chosen = LogSelection.bestLogCandidate(
        [(mtime: startTime + 1, path: first), (mtime: startTime + 2, path: second)],
        startTime: startTime,
        cwd: cwd,
        clockSkewSeconds: 60
    )
    #expect(chosen == first)
}

@Test func statusLogPathPrefersTui() throws {
    let codexHome = try createCodexHome()
    defer { try? FileManager.default.removeItem(at: codexHome) }
    let sessionsRoot = codexHome.appendingPathComponent("sessions")
    let cwd = codexHome.appendingPathComponent("workdir")
    try FileManager.default.createDirectory(at: cwd, withIntermediateDirectories: true)

    let sessionId = "session-tui"
    let logPath = sessionsRoot.appendingPathComponent("rollout-\(sessionId).jsonl")
    try writeSessionLog(path: logPath, sessionId: sessionId, cwd: cwd, timestamp: nil)
    let tuiLog = codexHome.appendingPathComponent("log").appendingPathComponent("codex-tui.log")
    try writeTuiLog(path: tuiLog, logPath: logPath)

    let result = LogDiscovery.statusLogPath(cwd: cwd, sessionDir: sessionsRoot, codexHome: codexHome)
    #expect(normalizedURLPath(result.path) == normalizedPath(logPath.path))
    #expect(result.source == .tui)
}

@Test func statusLogPathUsesHistory() throws {
    let codexHome = try createCodexHome()
    defer { try? FileManager.default.removeItem(at: codexHome) }
    let sessionsRoot = codexHome.appendingPathComponent("sessions")
    let cwd = codexHome.appendingPathComponent("workdir")
    try FileManager.default.createDirectory(at: cwd, withIntermediateDirectories: true)

    let sessionId = "session-history"
    let logPath = sessionsRoot.appendingPathComponent("rollout-\(sessionId).jsonl")
    try writeSessionLog(path: logPath, sessionId: sessionId, cwd: cwd, timestamp: nil)
    let historyLog = codexHome.appendingPathComponent("history.jsonl")
    try writeHistoryLog(path: historyLog, sessionId: sessionId)

    let result = LogDiscovery.statusLogPath(cwd: cwd, sessionDir: sessionsRoot, codexHome: codexHome)
    #expect(normalizedURLPath(result.path) == normalizedPath(logPath.path))
    #expect(result.source == .history)
}

@Test func statusLogPathUsesSessionDir() throws {
    let codexHome = try createCodexHome()
    defer { try? FileManager.default.removeItem(at: codexHome) }
    let sessionsRoot = codexHome.appendingPathComponent("sessions")
    let sessionDir = sessionsRoot.appendingPathComponent("2026/01/04")
    try FileManager.default.createDirectory(at: sessionDir, withIntermediateDirectories: true)
    let cwd = codexHome.appendingPathComponent("workdir")
    try FileManager.default.createDirectory(at: cwd, withIntermediateDirectories: true)

    let older = sessionDir.appendingPathComponent("rollout-older.jsonl")
    let newer = sessionDir.appendingPathComponent("rollout-newer.jsonl")
    try writeSessionLog(path: older, sessionId: "older", cwd: cwd, timestamp: nil)
    try writeSessionLog(path: newer, sessionId: "newer", cwd: cwd, timestamp: nil)
    try setMtime(path: older, epochSeconds: 1_000_000)
    try setMtime(path: newer, epochSeconds: 1_000_100)

    let result = LogDiscovery.statusLogPath(cwd: cwd, sessionDir: sessionDir, codexHome: codexHome)
    #expect(normalizedURLPath(result.path) == normalizedPath(newer.path))
    #expect(result.source == .sessionDir)
}

@Test func codexLogReducerIgnoresBootstrapMessage() {
    let event: [String: Any] = [
        "type": "event_msg",
        "payload": [
            "type": "user_message",
            "message": "# AGENTS.md instructions for /path/to/repo",
        ],
    ]
    let next = CodexLogReducer.nextState(from: .new, event: event)
    #expect(next == .new)
}

@Test func codexLogReducerMarksRunningAndDone() {
    let userEvent: [String: Any] = [
        "type": "event_msg",
        "payload": [
            "type": "user_message",
            "message": "Hello",
        ],
    ]
    let doneEvent: [String: Any] = [
        "type": "event_msg",
        "payload": [
            "type": "agent_message",
        ],
    ]
    let running = CodexLogReducer.nextState(from: .new, event: userEvent)
    #expect(running == .running)
    let done = CodexLogReducer.nextState(from: running, event: doneEvent)
    #expect(done == .done)
}
