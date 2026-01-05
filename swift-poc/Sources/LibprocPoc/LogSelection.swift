import Foundation

public struct LogSelection {
    public static func parseIsoTimestamp(_ value: String) -> TimeInterval? {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = formatter.date(from: value) {
            return date.timeIntervalSince1970
        }
        formatter.formatOptions = [.withInternetDateTime]
        return formatter.date(from: value)?.timeIntervalSince1970
    }

    static func timestampTrustworthy(
        _ ts: TimeInterval?,
        reference: TimeInterval,
        clockSkewSeconds: TimeInterval
    ) -> Bool {
        guard let ts else {
            return false
        }
        if clockSkewSeconds <= 0 {
            return true
        }
        return abs(ts - reference) <= clockSkewSeconds
    }

    static func sessionMetaTimestamp(path: URL, maxLines: Int = 200) -> TimeInterval? {
        guard let reader = LineReader(url: path) else {
            return nil
        }
        var lines = 0
        while lines < maxLines, let line = reader.nextLine() {
            lines += 1
            guard let data = parseJsonLine(line) else {
                continue
            }
            guard let type = data["type"] as? String, type == "session_meta" else {
                continue
            }
            if let payload = data["payload"] as? [String: Any],
               let ts = payload["timestamp"] as? String,
               let parsed = parseIsoTimestamp(ts) {
                return parsed
            }
            if let ts = data["timestamp"] as? String,
               let parsed = parseIsoTimestamp(ts) {
                return parsed
            }
        }
        return nil
    }

    static func logMatchesCwd(path: URL, cwd: URL, maxLines: Int = 200) -> Bool {
        guard let reader = LineReader(url: path) else {
            return false
        }
        let target = cwd.path
        var lines = 0
        while lines < maxLines, let line = reader.nextLine() {
            lines += 1
            guard let data = parseJsonLine(line) else {
                continue
            }
            guard let type = data["type"] as? String else {
                continue
            }
            if type == "session_meta" || type == "turn_context" {
                if let payload = data["payload"] as? [String: Any],
                   let cwdValue = payload["cwd"] as? String,
                   cwdValue == target {
                    return true
                }
            }
        }
        return false
    }

    public static func bestLogCandidate(
        _ candidates: [(mtime: TimeInterval, path: URL)],
        startTime: TimeInterval,
        cwd: URL,
        clockSkewSeconds: TimeInterval = 300
    ) -> URL? {
        var bestPath: URL?
        var bestCwdRank = Int.max
        var bestDistance = Double.greatestFiniteMagnitude
        var bestMtime = -Double.greatestFiniteMagnitude

        for candidate in candidates {
            var metaTs = sessionMetaTimestamp(path: candidate.path)
            if let ts = metaTs,
               !timestampTrustworthy(ts, reference: startTime, clockSkewSeconds: clockSkewSeconds) {
                metaTs = nil
            }
            let candidateTs = metaTs ?? candidate.mtime
            let distance = abs(candidateTs - startTime)
            let cwdRank = logMatchesCwd(path: candidate.path, cwd: cwd) ? 0 : 1
            if bestPath == nil
                || cwdRank < bestCwdRank
                || (cwdRank == bestCwdRank && distance < bestDistance)
                || (cwdRank == bestCwdRank && distance == bestDistance && candidate.mtime > bestMtime) {
                bestPath = candidate.path
                bestCwdRank = cwdRank
                bestDistance = distance
                bestMtime = candidate.mtime
            }
        }
        return bestPath
    }

    private static func parseJsonLine(_ line: String) -> [String: Any]? {
        guard let data = line.data(using: .utf8) else {
            return nil
        }
        let obj = try? JSONSerialization.jsonObject(with: data, options: [])
        return obj as? [String: Any]
    }
}

final class LineReader {
    private let handle: FileHandle
    private let bufferSize: Int
    private var buffer = Data()
    private var atEOF = false
    private let newline = Data([0x0a])

    init?(url: URL, bufferSize: Int = 4096) {
        guard let handle = try? FileHandle(forReadingFrom: url) else {
            return nil
        }
        self.handle = handle
        self.bufferSize = bufferSize
    }

    deinit {
        try? handle.close()
    }

    func nextLine() -> String? {
        while true {
            if let range = buffer.range(of: newline) {
                let lineData = buffer.subdata(in: 0..<range.lowerBound)
                buffer.removeSubrange(0..<range.upperBound)
                return String(data: lineData, encoding: .utf8)
            }
            if atEOF {
                if buffer.isEmpty {
                    return nil
                }
                let line = String(data: buffer, encoding: .utf8)
                buffer.removeAll()
                return line
            }
            let chunk = handle.readData(ofLength: bufferSize)
            if chunk.isEmpty {
                atEOF = true
                continue
            }
            buffer.append(chunk)
        }
    }
}
