import Foundation
import Darwin
import LibprocPoc

enum ExitCode {
    static let usage: Int32 = 64
    static let failure: Int32 = 1
}

func printUsage() {
    let text = """
    Usage:
      libproc-poc <pid> [--all] [--best] [--start <iso|epoch>] [--cwd <path>]
      libproc-poc --status [--cwd <path>] [--session-dir <path>] [--codex-home <path>]

    Options:
      --all         Print every open file path for the pid (default: only rollout-*.jsonl)
      --best        Choose a single rollout log using cwd + start time
      --start       ISO-8601 timestamp or epoch seconds for --best
      --cwd         Working directory to match logs (default: current)
      --session-dir Override session dir for --status
      --codex-home  Override ~/.codex for --status
      --status      Resolve the status log path using TUI/history/session dir
    """
    fputs(text + "\n", stderr)
}

let args = Array(CommandLine.arguments.dropFirst())
var showAll = false
var showBest = false
var showStatus = false
var startTime: TimeInterval?
var cwd = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
var sessionDir: URL?
var codexHome: URL?
var pidValue: pid_t?

func parseStartTime(_ value: String) -> TimeInterval? {
    if let ts = LogSelection.parseIsoTimestamp(value) {
        return ts
    }
    return Double(value)
}

var index = 0
while index < args.count {
    let arg = args[index]
    switch arg {
    case "--all":
        showAll = true
    case "--best":
        showBest = true
    case "--status":
        showStatus = true
    case "--start":
        index += 1
        guard index < args.count, let ts = parseStartTime(args[index]) else {
            fputs("Invalid --start value\n", stderr)
            printUsage()
            exit(ExitCode.usage)
        }
        startTime = ts
    case "--cwd":
        index += 1
        guard index < args.count else {
            fputs("Missing --cwd value\n", stderr)
            printUsage()
            exit(ExitCode.usage)
        }
        cwd = URL(fileURLWithPath: args[index])
    case "--session-dir":
        index += 1
        guard index < args.count else {
            fputs("Missing --session-dir value\n", stderr)
            printUsage()
            exit(ExitCode.usage)
        }
        sessionDir = URL(fileURLWithPath: args[index])
    case "--codex-home":
        index += 1
        guard index < args.count else {
            fputs("Missing --codex-home value\n", stderr)
            printUsage()
            exit(ExitCode.usage)
        }
        codexHome = URL(fileURLWithPath: args[index])
    case "--help", "-h":
        printUsage()
        exit(0)
    default:
        if arg.hasPrefix("-") {
            fputs("Unknown option: \(arg)\n", stderr)
            printUsage()
            exit(ExitCode.usage)
        }
        if pidValue == nil, let parsed = Int32(arg) {
            pidValue = pid_t(parsed)
        } else {
            fputs("Unexpected argument: \(arg)\n", stderr)
            printUsage()
            exit(ExitCode.usage)
        }
    }
    index += 1
}

if showStatus {
    let dir = sessionDir ?? LogDiscovery.sessionDirForTime(Date().timeIntervalSince1970, codexHome: codexHome)
    let result = LogDiscovery.statusLogPath(cwd: cwd, sessionDir: dir, codexHome: codexHome)
    if let path = result.path {
        print("log_path: \(path.path)")
    } else {
        print("log_path:")
    }
    if let source = result.source {
        print("source: \(source.rawValue)")
    }
    exit(0)
}

guard let pid = pidValue else {
    printUsage()
    exit(ExitCode.usage)
}

do {
    if showBest {
        let paths = try Libproc.openRolloutLogs(pid: pid)
        var candidates: [(mtime: TimeInterval, path: URL)] = []
        candidates.reserveCapacity(paths.count)
        for path in paths {
            let url = URL(fileURLWithPath: path)
            let values = try? url.resourceValues(forKeys: [.contentModificationDateKey])
            let mtime = values?.contentModificationDate?.timeIntervalSince1970 ?? 0
            candidates.append((mtime: mtime, path: url))
        }
        let start = startTime ?? Date().timeIntervalSince1970
        if let chosen = LogSelection.bestLogCandidate(candidates, startTime: start, cwd: cwd) {
            print(chosen.path)
        } else {
            exit(ExitCode.failure)
        }
        exit(0)
    }

    let paths: [String]
    if showAll {
        paths = try Libproc.openFilePaths(pid: pid)
    } else {
        paths = try Libproc.openRolloutLogs(pid: pid)
    }
    for path in paths {
        print(path)
    }
} catch {
    fputs("libproc error: \(error)\n", stderr)
    exit(ExitCode.failure)
}
