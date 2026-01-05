import Foundation

public enum CodexTitleState: String, Sendable {
    case new
    case running
    case done
}

public enum CodexLogReducer {
    private static let bootstrapPrefixes = [
        "# AGENTS.md instructions",
        "<environment_context>",
    ]

    public static func isBootstrapUserMessage(_ message: String) -> Bool {
        let trimmed = message.trimmingCharacters(in: .whitespacesAndNewlines)
        return bootstrapPrefixes.contains { trimmed.hasPrefix($0) }
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
        return nextState(from: state, event: event)
    }

    public static func nextState(from state: CodexTitleState, event: [String: Any]) -> CodexTitleState {
        guard let type = event["type"] as? String else {
            return state
        }
        let payload = (event["payload"] as? [String: Any]) ?? [:]

        if type == "event_msg" {
            guard let messageType = payload["type"] as? String else {
                return state
            }
            if messageType == "user_message" {
                guard let message = payload["message"] as? String else {
                    return state
                }
                return isBootstrapUserMessage(message) ? state : .running
            }
            if messageType == "agent_message" || messageType == "assistant_message" || messageType == "turn_aborted" {
                return .done
            }
        }

        if type == "response_item" {
            guard let itemType = payload["type"] as? String else {
                return state
            }
            if itemType == "message", let role = payload["role"] as? String, role == "assistant" {
                return .done
            }
        }

        return state
    }
}

