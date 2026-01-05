import Foundation

public enum LogSource: String {
    case tui = "tui"
    case history = "history"
    case sessionDir = "session_dir"
    case recentAny = "recent_any"
}

public struct LogDiscovery {
    public static func codexHome() -> URL {
        FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".codex")
    }

    public static func sessionsRoot(codexHome: URL? = nil) -> URL {
        let base = codexHome ?? LogDiscovery.codexHome()
        return base.appendingPathComponent("sessions")
    }

    public static func tuiLogPath(codexHome: URL? = nil) -> URL {
        let base = codexHome ?? LogDiscovery.codexHome()
        return base.appendingPathComponent("log").appendingPathComponent("codex-tui.log")
    }

    public static func historyLogPath(codexHome: URL? = nil) -> URL {
        let base = codexHome ?? LogDiscovery.codexHome()
        return base.appendingPathComponent("history.jsonl")
    }

    public static func sessionDirForTime(_ epochSeconds: TimeInterval, codexHome: URL? = nil) -> URL {
        let base = codexHome ?? LogDiscovery.codexHome()
        let date = Date(timeIntervalSince1970: epochSeconds)
        let parts = Calendar.current.dateComponents([.year, .month, .day], from: date)
        let year = parts.year ?? 0
        let month = parts.month ?? 0
        let day = parts.day ?? 0
        let yearDir = String(format: "%04d", year)
        let monthDir = String(format: "%02d", month)
        let dayDir = String(format: "%02d", day)
        return base
            .appendingPathComponent("sessions")
            .appendingPathComponent(yearDir)
            .appendingPathComponent(monthDir)
            .appendingPathComponent(dayDir)
    }

    public static func statusLogPath(
        cwd: URL,
        sessionDir: URL? = nil,
        codexHome: URL? = nil
    ) -> (path: URL?, source: LogSource?) {
        let base = codexHome ?? LogDiscovery.codexHome()
        let tuiLog = tuiLogPath(codexHome: base)
        if let resumePath = resumeLogFromTui(tuiLog: tuiLog, cwd: cwd) {
            return (resumePath, .tui)
        }
        let historyLog = historyLogPath(codexHome: base)
        if FileManager.default.fileExists(atPath: historyLog.path),
           let sessionId = latestHistorySessionId(historyLog: historyLog),
           let path = findLogBySessionId(root: sessionsRoot(codexHome: base), sessionId: sessionId, cwd: cwd) {
            return (path, .history)
        }
        let dir = sessionDir ?? sessionDirForTime(Date().timeIntervalSince1970, codexHome: base)
        if let latest = latestLog(in: dir) {
            return (latest, .sessionDir)
        }
        if let recent = recentLogAny(root: sessionsRoot(codexHome: base), since: 0, cwd: cwd) {
            return (recent, .recentAny)
        }
        return (nil, nil)
    }

    static func resumeLogFromTui(tuiLog: URL, cwd: URL) -> URL? {
        let lines = tailLines(url: tuiLog, limit: 1000)
        var fallback: URL?
        for line in lines.reversed() {
            guard let path = parseResumePath(line) else {
                continue
            }
            let url = URL(fileURLWithPath: path)
            if !FileManager.default.fileExists(atPath: url.path) {
                continue
            }
            if LogSelection.logMatchesCwd(path: url, cwd: cwd) {
                return url
            }
            if fallback == nil {
                fallback = url
            }
        }
        return fallback
    }

    static func latestHistorySessionId(historyLog: URL, limit: Int = 200) -> String? {
        let lines = tailLines(url: historyLog, limit: limit)
        for line in lines.reversed() {
            guard let data = parseJsonLine(line),
                  let sessionId = data["session_id"] as? String else {
                continue
            }
            return sessionId
        }
        return nil
    }

    static func latestLog(in sessionDir: URL) -> URL? {
        guard let entries = try? FileManager.default.contentsOfDirectory(
            at: sessionDir,
            includingPropertiesForKeys: [.contentModificationDateKey],
            options: [.skipsHiddenFiles]
        ) else {
            return nil
        }
        var latest: (TimeInterval, URL)?
        for entry in entries {
            let name = entry.lastPathComponent
            if !name.hasPrefix("rollout-") || entry.pathExtension != "jsonl" {
                continue
            }
            let values = try? entry.resourceValues(forKeys: [.contentModificationDateKey])
            let mtime = values?.contentModificationDate?.timeIntervalSince1970 ?? 0
            if latest == nil || mtime > latest!.0 {
                latest = (mtime, entry)
            }
        }
        return latest?.1
    }

    static func recentLogAny(root: URL, since: TimeInterval, cwd: URL) -> URL? {
        guard let enumerator = FileManager.default.enumerator(
            at: root,
            includingPropertiesForKeys: [.contentModificationDateKey],
            options: [.skipsHiddenFiles]
        ) else {
            return nil
        }
        var bestAny: (TimeInterval, URL)?
        var bestCwd: (TimeInterval, URL)?
        for case let url as URL in enumerator {
            let name = url.lastPathComponent
            if !name.hasPrefix("rollout-") || url.pathExtension != "jsonl" {
                continue
            }
            let values = try? url.resourceValues(forKeys: [.contentModificationDateKey])
            let mtime = values?.contentModificationDate?.timeIntervalSince1970 ?? 0
            if mtime < since {
                continue
            }
            if bestAny == nil || mtime > bestAny!.0 {
                bestAny = (mtime, url)
            }
            if LogSelection.logMatchesCwd(path: url, cwd: cwd) {
                if bestCwd == nil || mtime > bestCwd!.0 {
                    bestCwd = (mtime, url)
                }
            }
        }
        return bestCwd?.1 ?? bestAny?.1
    }

    static func findLogBySessionId(root: URL, sessionId: String, cwd: URL) -> URL? {
        guard let enumerator = FileManager.default.enumerator(
            at: root,
            includingPropertiesForKeys: [.contentModificationDateKey],
            options: [.skipsHiddenFiles]
        ) else {
            return nil
        }
        var matches: [(TimeInterval, URL)] = []
        for case let url as URL in enumerator {
            let name = url.lastPathComponent
            if !name.contains(sessionId) || !name.hasSuffix(".jsonl") {
                continue
            }
            let values = try? url.resourceValues(forKeys: [.contentModificationDateKey])
            let mtime = values?.contentModificationDate?.timeIntervalSince1970 ?? 0
            matches.append((mtime, url))
        }
        if matches.isEmpty {
            return nil
        }
        if matches.count == 1 {
            return matches[0].1
        }
        var bestCwd: (TimeInterval, URL)?
        for (mtime, url) in matches {
            if LogSelection.logMatchesCwd(path: url, cwd: cwd) {
                if bestCwd == nil || mtime > bestCwd!.0 {
                    bestCwd = (mtime, url)
                }
            }
        }
        if let bestCwd {
            return bestCwd.1
        }
        return matches.max { $0.0 < $1.0 }?.1
    }

    private static func tailLines(url: URL, limit: Int) -> [String] {
        guard limit > 0, let reader = LineReader(url: url) else {
            return []
        }
        var lines: [String] = []
        lines.reserveCapacity(limit)
        while let line = reader.nextLine() {
            lines.append(line)
            if lines.count > limit {
                lines.removeFirst()
            }
        }
        return lines
    }

    private static func parseResumePath(_ line: String) -> String? {
        if !line.contains("INFO Resum") || !line.contains("rollout") {
            return nil
        }
        guard let range = line.range(of: " from \"") else {
            return nil
        }
        let remainder = line[range.upperBound...]
        guard let end = remainder.firstIndex(of: "\"") else {
            return nil
        }
        return String(remainder[..<end])
    }

    private static func parseJsonLine(_ line: String) -> [String: Any]? {
        guard let data = line.data(using: .utf8) else {
            return nil
        }
        let obj = try? JSONSerialization.jsonObject(with: data, options: [])
        return obj as? [String: Any]
    }
}
