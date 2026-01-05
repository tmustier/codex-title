import Foundation
import Darwin
import LibprocPoc

enum ExitCode {
    static let usage: Int32 = 64
    static let failure: Int32 = 1
}

let defaultNewTitle = "codex:new"
let defaultRunningTitle = "codex:running..."
let defaultDoneTitle = "codex:✅"
let defaultNoCommitTitle = "codex:🚧"
let defaultTimeoutTitle = "codex:🛑"
let defaultInactiveTimeoutSeconds: TimeInterval = 3.0

final class StopFlag: @unchecked Sendable {
    private let lock = NSLock()
    private var stopped = false

    func stop() {
        lock.lock()
        stopped = true
        lock.unlock()
    }

    func isStopped() -> Bool {
        lock.lock()
        defer { lock.unlock() }
        return stopped
    }
}

final class TitleWriter: @unchecked Sendable {
    private let lock = NSLock()
    private let handle: FileHandle?
    private var lastTitle: String?

    init() {
        let fd = open("/dev/tty", O_WRONLY)
        if fd == -1 {
            handle = nil
            return
        }
        handle = FileHandle(fileDescriptor: fd, closeOnDealloc: true)
    }

    func set(_ title: String) {
        lock.lock()
        defer { lock.unlock() }
        guard let handle else {
            return
        }
        if lastTitle == title {
            return
        }
        lastTitle = title
        let seq = "\u{001B}]0;\(title)\u{0007}"
        guard let data = seq.data(using: .utf8) else {
            return
        }
        handle.write(data)
    }
}

func title(
    for state: CodexTitleState,
    newTitle: String,
    runningTitle: String,
    doneTitle: String,
    noCommitTitle: String
) -> String {
    switch state {
    case .new:
        return newTitle
    case .running:
        return runningTitle
    case .doneCommitted:
        return doneTitle
    case .doneNoCommit:
        return noCommitTitle
    }
}

func initialTurnStateFromLog(path: URL) -> CodexLogReducer.TurnState {
    guard let handle = try? FileHandle(forReadingFrom: path) else {
        return CodexLogReducer.TurnState(title: .new)
    }
    defer { handle.closeFile() }

    let endOffset = handle.seekToEndOfFile()
    let maxBytes: UInt64 = 64 * 1024
    let startOffset = endOffset > maxBytes ? (endOffset - maxBytes) : 0
    handle.seek(toFileOffset: startOffset)
    let chunk = handle.readDataToEndOfFile()
    guard let text = String(data: chunk, encoding: .utf8) else {
        return CodexLogReducer.TurnState(title: .new)
    }
    var state = CodexLogReducer.TurnState(title: .new)
    for line in text.split(separator: "\n").suffix(200) {
        CodexLogReducer.reduce(&state, jsonLine: String(line))
    }
    return state
}

func printUsage() {
    let text = """
    Usage:
      codex-title-poc [options] -- [codex args]

    Options:
      --cwd <path>        Working directory to match logs (default: current)
      --start <iso|epoch> Start time for log selection (default: now)
      --timeout <secs>    Seconds to wait for pid log before fallback (default: 8)
      --poll <secs>       Poll interval while waiting (default: 0.2)
      --new-title <text>  Title to set on session start (default: \(defaultNewTitle))
      --running-title <text> Title to set while running (default: \(defaultRunningTitle))
      --done-title <text> Title to set on completion with commit (default: \(defaultDoneTitle))
      --no-commit-title <text> Title to set on completion without commit (default: \(defaultNoCommitTitle))
      --inactive-timeout <secs> Seconds with no log output to show timeout (default: \(defaultInactiveTimeoutSeconds))
      --timeout-title <text> Title to show when inactive timeout triggers (default: \(defaultTimeoutTitle))
      --codex-home <path> Override ~/.codex for fallback lookup
      --print-log-path    Print log_path/source once discovered
      --quiet             Suppress log_path/source output (overrides --print-log-path)
      --debug             Print codex launch diagnostics
      -h, --help          Show this help
    """
    fputs(text + "\n", stderr)
}

func parseDouble(_ value: String) -> Double? {
    Double(value.trimmingCharacters(in: .whitespaces))
}

func parseStartTime(_ value: String) -> TimeInterval? {
    if let ts = LogSelection.parseIsoTimestamp(value) {
        return ts
    }
    return parseDouble(value)
}

func normalizeCodexArgs(_ args: [String]) -> [String] {
    guard let first = args.first else {
        return args
    }
    if first == "--resume" {
        var updated = args
        updated[0] = "resume"
        return updated
    }
    if first == "--last" {
        return ["resume"] + args
    }
    return args
}

func bestLogForPid(pid: pid_t, startTime: TimeInterval, cwd: URL) -> URL? {
    let paths: [String]
    do {
        paths = try Libproc.openRolloutLogs(pid: pid)
    } catch {
        return nil
    }
    if paths.isEmpty {
        return nil
    }
    var candidates: [(mtime: TimeInterval, path: URL)] = []
    candidates.reserveCapacity(paths.count)
    for path in paths {
        let url = URL(fileURLWithPath: path)
        let values = try? url.resourceValues(forKeys: [.contentModificationDateKey])
        let mtime = values?.contentModificationDate?.timeIntervalSince1970 ?? 0
        candidates.append((mtime: mtime, path: url))
    }
    return LogSelection.bestLogCandidate(candidates, startTime: startTime, cwd: cwd)
}

func waitForLog(
    pid: pid_t,
    startTime: TimeInterval,
    cwd: URL,
    timeout: TimeInterval,
    pollInterval: TimeInterval,
    codexHome: URL?
) -> (path: URL?, source: String?) {
    let deadline = Date().addingTimeInterval(max(0, timeout))
    if timeout > 0 {
        while Date() < deadline {
            if let path = bestLogForPid(pid: pid, startTime: startTime, cwd: cwd) {
                return (path, "pid")
            }
            Thread.sleep(forTimeInterval: max(0.05, pollInterval))
        }
    }
    let sessionDir = LogDiscovery.sessionDirForTime(startTime, codexHome: codexHome)
    let result = LogDiscovery.statusLogPath(cwd: cwd, sessionDir: sessionDir, codexHome: codexHome)
    return (result.path, result.source?.rawValue)
}

func resolveExecutable(_ name: String) -> URL? {
    if name.contains("/") {
        let url = URL(fileURLWithPath: name)
        return FileManager.default.isExecutableFile(atPath: url.path) ? url : nil
    }
    let env = ProcessInfo.processInfo.environment
    let pathValue = env["PATH"] ?? ""
    for entry in pathValue.split(separator: ":") {
        let url = URL(fileURLWithPath: String(entry)).appendingPathComponent(name)
        if FileManager.default.isExecutableFile(atPath: url.path) {
            return url
        }
    }
    return nil
}

func makeCStringArray(_ args: [String]) -> [UnsafeMutablePointer<CChar>?] {
    var result: [UnsafeMutablePointer<CChar>?] = args.map { strdup($0) }
    result.append(nil)
    return result
}

func freeCStringArray(_ args: inout [UnsafeMutablePointer<CChar>?]) {
    for ptr in args {
        if let ptr {
            free(ptr)
        }
    }
    args.removeAll(keepingCapacity: false)
}

func spawnCodex(executable: URL, arguments: [String], cwd: URL) -> pid_t? {
    let argv = [executable.path] + arguments
    var cArgs = makeCStringArray(argv)
    defer { freeCStringArray(&cArgs) }

    var pid: pid_t = 0
    var actions: posix_spawn_file_actions_t? = nil
    let initActionsResult = posix_spawn_file_actions_init(&actions)
    if initActionsResult != 0 {
        fputs("posix_spawn_file_actions_init failed: \(initActionsResult)\n", stderr)
        return nil
    }
    defer { posix_spawn_file_actions_destroy(&actions) }

    let addChdirResult = cwd.path.withCString { posix_spawn_file_actions_addchdir_np(&actions, $0) }
    if addChdirResult != 0 {
        fputs("posix_spawn_file_actions_addchdir_np failed: \(addChdirResult)\n", stderr)
        return nil
    }

    let spawnResult = executable.path.withCString { pathPtr in
        cArgs.withUnsafeMutableBufferPointer { buffer in
            posix_spawn(&pid, pathPtr, &actions, nil, buffer.baseAddress, environ)
        }
    }
    if spawnResult != 0 {
        fputs("posix_spawn failed: \(spawnResult)\n", stderr)
        return nil
    }

    return pid
}

func waitStatusIsExited(_ status: Int32) -> Bool {
    (status & 0x7F) == 0
}

func waitStatusExitCode(_ status: Int32) -> Int32 {
    (status >> 8) & 0xFF
}

func waitStatusIsSignaled(_ status: Int32) -> Bool {
    let code = status & 0x7F
    return code != 0 && code != 0x7F
}

func waitStatusSignal(_ status: Int32) -> Int32 {
    status & 0x7F
}

func runTitleWatcher(
    pid: pid_t,
    startTime: TimeInterval,
    cwd: URL,
    timeout: TimeInterval,
    pollInterval: TimeInterval,
    codexHome: URL?,
    newTitle: String,
    runningTitle: String,
    doneTitle: String,
    noCommitTitle: String,
    timeoutTitle: String,
    inactiveTimeoutSeconds: TimeInterval,
    stopFlag: StopFlag,
    titleWriter: TitleWriter
) {
    let discoveryStart = Date()
    var usedFallback = false
    var currentLog: URL?
    var handle: FileHandle?
    var buffer = Data()
    var state = CodexLogReducer.TurnState(title: .new)
    var overlay = CodexTimeoutOverlay(now: Date().timeIntervalSince1970)
    var lastSwitchCheck = Date.distantPast
    let switchInterval: TimeInterval = 1.0

    func applyTitle(_ next: CodexTitleState) {
        if overlay.timeoutActive, next == .running {
            titleWriter.set(timeoutTitle)
            return
        }
        titleWriter.set(
            title(
                for: next,
                newTitle: newTitle,
                runningTitle: runningTitle,
                doneTitle: doneTitle,
                noCommitTitle: noCommitTitle
            )
        )
    }

    func openLog(_ url: URL) {
        currentLog = url
        handle?.closeFile()
        handle = try? FileHandle(forReadingFrom: url)
        buffer.removeAll(keepingCapacity: true)
        state = initialTurnStateFromLog(path: url)
        overlay.noteActivity(now: Date().timeIntervalSince1970)
        applyTitle(state.title)
        _ = handle?.seekToEndOfFile()
    }

    while !stopFlag.isStopped() {
        if currentLog == nil {
            if let url = bestLogForPid(pid: pid, startTime: startTime, cwd: cwd) {
                openLog(url)
                continue
            }
            if !usedFallback && Date().timeIntervalSince(discoveryStart) >= max(0, timeout) {
                usedFallback = true
                let sessionDir = LogDiscovery.sessionDirForTime(startTime, codexHome: codexHome)
                let result = LogDiscovery.statusLogPath(cwd: cwd, sessionDir: sessionDir, codexHome: codexHome)
                if let url = result.path {
                    openLog(url)
                    continue
                }
            }
            Thread.sleep(forTimeInterval: max(0.05, pollInterval))
            continue
        }

        let now = Date()
        if now.timeIntervalSince(lastSwitchCheck) >= switchInterval {
            lastSwitchCheck = now
            if let url = bestLogForPid(pid: pid, startTime: startTime, cwd: cwd), url != currentLog {
                openLog(url)
                continue
            }
        }

        guard let handle else {
            currentLog = nil
            continue
        }

        let chunk = handle.readData(ofLength: 4096)
        if chunk.isEmpty {
            if overlay.tick(
                now: now.timeIntervalSince1970,
                underlying: state.title,
                timeoutSeconds: inactiveTimeoutSeconds
            ) {
                applyTitle(state.title)
            }
            Thread.sleep(forTimeInterval: 0.1)
            continue
        }

        let overlayWasActive = overlay.timeoutActive
        overlay.noteActivity(now: now.timeIntervalSince1970)
        if overlayWasActive {
            applyTitle(state.title)
        }

        buffer.append(chunk)
        while let newlineIndex = buffer.firstIndex(of: 0x0a) {
            let lineData = buffer.subdata(in: 0..<newlineIndex)
            buffer.removeSubrange(0...newlineIndex)
            guard let line = String(data: lineData, encoding: .utf8) else {
                continue
            }
            let before = state.title
            CodexLogReducer.reduce(&state, jsonLine: line)
            if state.title != before {
                applyTitle(state.title)
            }
        }
    }

    handle?.closeFile()
}

let args = Array(CommandLine.arguments.dropFirst())
var codexArgs: [String] = []
var cwd = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
var startTime: TimeInterval?
var timeout: TimeInterval = 8.0
var pollInterval: TimeInterval = 0.2
var codexHome: URL?
var quiet = false
var printLogPath = false
var debug = false
var newTitle = defaultNewTitle
var runningTitle = defaultRunningTitle
var doneTitle = defaultDoneTitle
var noCommitTitle = defaultNoCommitTitle
var inactiveTimeoutSeconds = defaultInactiveTimeoutSeconds
var timeoutTitle = defaultTimeoutTitle

var index = 0
while index < args.count {
    let arg = args[index]
    if arg == "--" {
        codexArgs = Array(args[(index + 1)...])
        break
    }
    switch arg {
    case "--cwd":
        index += 1
        guard index < args.count else {
            fputs("Missing --cwd value\n", stderr)
            printUsage()
            exit(ExitCode.usage)
        }
        cwd = URL(fileURLWithPath: args[index])
    case "--start":
        index += 1
        guard index < args.count, let ts = parseStartTime(args[index]) else {
            fputs("Invalid --start value\n", stderr)
            printUsage()
            exit(ExitCode.usage)
        }
        startTime = ts
    case "--timeout":
        index += 1
        guard index < args.count, let value = parseDouble(args[index]) else {
            fputs("Invalid --timeout value\n", stderr)
            printUsage()
            exit(ExitCode.usage)
        }
        timeout = value
    case "--poll":
        index += 1
        guard index < args.count, let value = parseDouble(args[index]) else {
            fputs("Invalid --poll value\n", stderr)
            printUsage()
            exit(ExitCode.usage)
        }
        pollInterval = value
    case "--new-title":
        index += 1
        guard index < args.count else {
            fputs("Missing --new-title value\n", stderr)
            printUsage()
            exit(ExitCode.usage)
        }
        newTitle = args[index]
    case "--running-title":
        index += 1
        guard index < args.count else {
            fputs("Missing --running-title value\n", stderr)
            printUsage()
            exit(ExitCode.usage)
        }
        runningTitle = args[index]
    case "--done-title":
        index += 1
        guard index < args.count else {
            fputs("Missing --done-title value\n", stderr)
            printUsage()
            exit(ExitCode.usage)
        }
        doneTitle = args[index]
    case "--no-commit-title":
        index += 1
        guard index < args.count else {
            fputs("Missing --no-commit-title value\n", stderr)
            printUsage()
            exit(ExitCode.usage)
        }
        noCommitTitle = args[index]
    case "--inactive-timeout":
        index += 1
        guard index < args.count, let value = parseDouble(args[index]) else {
            fputs("Invalid --inactive-timeout value\n", stderr)
            printUsage()
            exit(ExitCode.usage)
        }
        inactiveTimeoutSeconds = value
    case "--timeout-title":
        index += 1
        guard index < args.count else {
            fputs("Missing --timeout-title value\n", stderr)
            printUsage()
            exit(ExitCode.usage)
        }
        timeoutTitle = args[index]
    case "--codex-home":
        index += 1
        guard index < args.count else {
            fputs("Missing --codex-home value\n", stderr)
            printUsage()
            exit(ExitCode.usage)
        }
        codexHome = URL(fileURLWithPath: args[index])
    case "--print-log-path":
        printLogPath = true
    case "--quiet":
        quiet = true
    case "--debug":
        debug = true
    case "--help", "-h":
        printUsage()
        exit(0)
    default:
        if arg.hasPrefix("-") {
            fputs("Unknown option: \(arg)\n", stderr)
            printUsage()
            exit(ExitCode.usage)
        }
        fputs("Unexpected argument: \(arg)\n", stderr)
        printUsage()
        exit(ExitCode.usage)
    }
    index += 1
}

codexArgs = normalizeCodexArgs(codexArgs)

guard let codexURL = resolveExecutable("codex") else {
    fputs("codex not found on PATH\n", stderr)
    exit(ExitCode.failure)
}
let stdinIsTty = isatty(STDIN_FILENO) == 1
let stdoutIsTty = isatty(STDOUT_FILENO) == 1
let stderrIsTty = isatty(STDERR_FILENO) == 1
let interactive = stdinIsTty && stdoutIsTty && stderrIsTty

if interactive && !printLogPath {
    quiet = true
}

let titleWriter = TitleWriter()
if interactive {
    titleWriter.set(newTitle)
}

guard let codexPid = spawnCodex(executable: codexURL, arguments: codexArgs, cwd: cwd) else {
    exit(ExitCode.failure)
}

if debug {
    fputs("codex_path: \(codexURL.path)\n", stderr)
    fputs("codex_pid: \(codexPid)\n", stderr)
    fputs("cwd: \(cwd.path)\n", stderr)
    fputs("stdin_tty: \(stdinIsTty)\n", stderr)
    fputs("stdout_tty: \(stdoutIsTty)\n", stderr)
    fputs("stderr_tty: \(stderrIsTty)\n", stderr)
}

let stopFlag = StopFlag()
    if interactive {
        let start = startTime ?? Date().timeIntervalSince1970
        let watcherPid = codexPid
        let watcherCwd = cwd
    let watcherTimeout = timeout
    let watcherPollInterval = pollInterval
    let watcherCodexHome = codexHome
    let watcherStopFlag = stopFlag
    let watcherTitleWriter = titleWriter
    let watcherNewTitle = newTitle
    let watcherRunningTitle = runningTitle
    let watcherDoneTitle = doneTitle
    let watcherNoCommitTitle = noCommitTitle
    let watcherTimeoutTitle = timeoutTitle
    let watcherInactiveTimeoutSeconds = inactiveTimeoutSeconds
    Thread.detachNewThread {
        runTitleWatcher(
            pid: watcherPid,
            startTime: start,
            cwd: watcherCwd,
            timeout: watcherTimeout,
            pollInterval: watcherPollInterval,
            codexHome: watcherCodexHome,
            newTitle: watcherNewTitle,
            runningTitle: watcherRunningTitle,
            doneTitle: watcherDoneTitle,
            noCommitTitle: watcherNoCommitTitle,
            timeoutTitle: watcherTimeoutTitle,
            inactiveTimeoutSeconds: watcherInactiveTimeoutSeconds,
            stopFlag: watcherStopFlag,
            titleWriter: watcherTitleWriter
        )
    }
}

if !quiet && printLogPath {
    let start = startTime ?? Date().timeIntervalSince1970
    let result = waitForLog(
        pid: codexPid,
        startTime: start,
        cwd: cwd,
        timeout: timeout,
        pollInterval: pollInterval,
        codexHome: codexHome
    )
    if let path = result.path {
        fputs("log_path: \(path.path)\n", stderr)
    } else {
        fputs("log_path:\n", stderr)
    }
    if let source = result.source {
        fputs("source: \(source)\n", stderr)
    }
}

var status: Int32 = 0
while waitpid(codexPid, &status, 0) == -1 {
    if errno == EINTR {
        continue
    }
    perror("waitpid")
    exit(ExitCode.failure)
}

stopFlag.stop()

if debug {
    if waitStatusIsExited(status) {
        fputs("codex exited with status \(waitStatusExitCode(status))\n", stderr)
    } else if waitStatusIsSignaled(status) {
        fputs("codex terminated by signal \(waitStatusSignal(status))\n", stderr)
    }
}

if waitStatusIsExited(status) {
    exit(waitStatusExitCode(status))
}
if waitStatusIsSignaled(status) {
    exit(128 + waitStatusSignal(status))
}
exit(ExitCode.failure)
