import Foundation

public enum CodexTitleState: String, Sendable {
    case new
    case running
    case doneCommitted
    case doneNoCommit
}

public enum CodexLogReducer {
    private static let bootstrapPrefixes = [
        "# AGENTS.md instructions",
        "<environment_context>",
    ]

    private static let commandSeparators: Set<String> = [";", "&&", "||", "|", "&"]

    public static func isBootstrapUserMessage(_ message: String) -> Bool {
        let trimmed = message.trimmingCharacters(in: .whitespacesAndNewlines)
        return bootstrapPrefixes.contains { trimmed.hasPrefix($0) }
    }

    public struct TurnState: Sendable, Equatable {
        public var title: CodexTitleState
        var pendingToolCalls: Set<String>
        var pendingCommitCalls: Set<String>
        var turnCommitSeen: Bool

        public init(title: CodexTitleState = .new) {
            self.title = title
            self.pendingToolCalls = []
            self.pendingCommitCalls = []
            self.turnCommitSeen = false
        }
    }

    public static func nextState(from state: CodexTitleState, jsonLine: String) -> CodexTitleState {
        guard let data = jsonLine.data(using: .utf8) else {
            return state
        }
        guard let object = try? JSONSerialization.jsonObject(with: data, options: []) else {
            return state
        }
        guard let event = object as? [String: Any] else {
            return state
        }
        var turn = TurnState(title: state)
        reduce(&turn, event: event)
        return turn.title
    }

    public static func nextState(from state: CodexTitleState, event: [String: Any]) -> CodexTitleState {
        var turn = TurnState(title: state)
        reduce(&turn, event: event)
        return turn.title
    }

    public static func reduce(_ state: inout TurnState, jsonLine: String) {
        guard let data = jsonLine.data(using: .utf8) else {
            return
        }
        guard let object = try? JSONSerialization.jsonObject(with: data, options: []) else {
            return
        }
        guard let event = object as? [String: Any] else {
            return
        }
        reduce(&state, event: event)
    }

    public static func reduce(_ state: inout TurnState, event: [String: Any]) {
        guard let type = event["type"] as? String else {
            return
        }
        let payload = (event["payload"] as? [String: Any]) ?? [:]

        if let userText = extractUserText(eventType: type, payload: payload) {
            if isBootstrapUserMessage(userText) {
                return
            }
            state.title = .running
            state.turnCommitSeen = false
            state.pendingToolCalls.removeAll(keepingCapacity: true)
            state.pendingCommitCalls.removeAll(keepingCapacity: true)
            return
        }

        if type == "response_item" {
            guard let itemType = payload["type"] as? String else {
                return
            }
            noteToolCall(itemType: itemType, payload: payload, pendingCalls: &state.pendingToolCalls)
            if itemType == "function_call" {
                if let (callId, command) = extractCommand(payload: payload) {
                    if commandHasGitCommit(command) {
                        state.pendingCommitCalls.insert(callId)
                    }
                }
                return
            }
            if itemType == "function_call_output" {
                if let callId = payload["call_id"] as? String, state.pendingCommitCalls.contains(callId) {
                    if let output = payload["output"] as? String, parseExitCode(output) == 0 {
                        state.turnCommitSeen = true
                    }
                }
                return
            }
            if itemType == "message", let role = payload["role"] as? String, role == "assistant" {
                state.title = state.turnCommitSeen ? .doneCommitted : .doneNoCommit
                return
            }
        }

        if type == "event_msg" {
            guard let messageType = payload["type"] as? String else {
                return
            }
            if messageType == "agent_message" || messageType == "assistant_message" || messageType == "turn_aborted" {
                state.title = state.turnCommitSeen ? .doneCommitted : .doneNoCommit
                return
            }
        }
    }

    private static func extractUserText(eventType: String, payload: [String: Any]) -> String? {
        if eventType == "event_msg" {
            if payload["type"] as? String == "user_message", let message = payload["message"] as? String {
                return message
            }
        }
        if eventType == "response_item" {
            guard let itemType = payload["type"] as? String, itemType == "message" else {
                return nil
            }
            guard let role = payload["role"] as? String, role == "user" else {
                return nil
            }
            guard let content = payload["content"] as? [[String: Any]], let first = content.first else {
                return nil
            }
            if let text = first["text"] as? String {
                return text
            }
            if let input = first["input_text"] as? String {
                return input
            }
        }
        return nil
    }

    private static func noteToolCall(
        itemType: String,
        payload: [String: Any],
        pendingCalls: inout Set<String>
    ) {
        if itemType == "function_call" || itemType == "custom_tool_call" {
            if let callId = payload["call_id"] as? String {
                if payload["status"] as? String == "completed" {
                    pendingCalls.remove(callId)
                } else {
                    pendingCalls.insert(callId)
                }
            }
            return
        }
        if itemType == "function_call_output" || itemType == "custom_tool_call_output" {
            if let callId = payload["call_id"] as? String {
                pendingCalls.remove(callId)
            }
        }
    }

    private static func extractCommand(payload: [String: Any]) -> (callId: String, command: String)? {
        guard payload["type"] as? String == "function_call" else {
            return nil
        }
        guard let name = payload["name"] as? String, name == "shell_command" || name == "exec_command" else {
            return nil
        }
        guard let callId = payload["call_id"] as? String else {
            return nil
        }
        guard let argsAny = payload["arguments"] else {
            return nil
        }
        let args: [String: Any]
        if let dict = argsAny as? [String: Any] {
            args = dict
        } else if let raw = argsAny as? String, let data = raw.data(using: .utf8) {
            guard let object = try? JSONSerialization.jsonObject(with: data, options: []),
                  let dict = object as? [String: Any]
            else {
                return nil
            }
            args = dict
        } else {
            return nil
        }
        if let cmd = args["command"] as? String {
            return (callId, cmd)
        }
        if let cmd = args["cmd"] as? String {
            return (callId, cmd)
        }
        return nil
    }

    private static func parseExitCode(_ output: String) -> Int? {
        let patterns = [
            "Exit code:\\s*(\\d+)",
            "Process exited with code\\s+(\\d+)",
            "\"exit_code\"\\s*:\\s*(\\d+)",
        ]
        for pattern in patterns {
            if let regex = try? NSRegularExpression(pattern: pattern, options: []) {
                let range = NSRange(output.startIndex..<output.endIndex, in: output)
                if let match = regex.firstMatch(in: output, options: [], range: range),
                   let codeRange = Range(match.range(at: 1), in: output),
                   let code = Int(output[codeRange])
                {
                    return code
                }
            }
        }
        return nil
    }

    private static func isGitToken(_ token: String) -> Bool {
        if token == "git" {
            return true
        }
        return URL(fileURLWithPath: token).lastPathComponent == "git"
    }

    private static func segmentHasGitCommit(_ tokens: [String]) -> Bool {
        for (index, token) in tokens.enumerated() where isGitToken(token) {
            if tokens[(index + 1)...].contains("commit") {
                return true
            }
        }
        return false
    }

    private static func commandHasGitCommit(_ command: String) -> Bool {
        let tokens = shellSplit(command)
        var segment: [String] = []
        for token in tokens {
            if commandSeparators.contains(token) {
                if segmentHasGitCommit(segment) {
                    return true
                }
                segment.removeAll(keepingCapacity: true)
            } else {
                segment.append(token)
            }
        }
        return segmentHasGitCommit(segment)
    }

    private static func shellSplit(_ command: String) -> [String] {
        var tokens: [String] = []
        tokens.reserveCapacity(16)
        var current = ""
        current.reserveCapacity(32)
        var inSingleQuote = false
        var inDoubleQuote = false
        var index = command.startIndex

        func flushCurrent() {
            if !current.isEmpty {
                tokens.append(current)
                current.removeAll(keepingCapacity: true)
            }
        }

        while index < command.endIndex {
            let char = command[index]
            if inSingleQuote {
                if char == "'" {
                    inSingleQuote = false
                } else {
                    current.append(char)
                }
                index = command.index(after: index)
                continue
            }
            if inDoubleQuote {
                if char == "\"" {
                    inDoubleQuote = false
                } else {
                    current.append(char)
                }
                index = command.index(after: index)
                continue
            }

            if char == "'" {
                inSingleQuote = true
                index = command.index(after: index)
                continue
            }
            if char == "\"" {
                inDoubleQuote = true
                index = command.index(after: index)
                continue
            }
            if char.isWhitespace {
                flushCurrent()
                index = command.index(after: index)
                continue
            }

            if char == "&" || char == "|" {
                flushCurrent()
                let next = command.index(after: index)
                if next < command.endIndex, command[next] == char {
                    tokens.append(String([char, char]))
                    index = command.index(after: next)
                } else {
                    tokens.append(String(char))
                    index = next
                }
                continue
            }
            if char == ";" {
                flushCurrent()
                tokens.append(String(char))
                index = command.index(after: index)
                continue
            }

            current.append(char)
            index = command.index(after: index)
        }
        flushCurrent()
        return tokens
    }
}
