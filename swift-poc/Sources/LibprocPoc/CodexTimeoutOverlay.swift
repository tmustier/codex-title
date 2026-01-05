import Foundation

public struct CodexTimeoutOverlay: Sendable, Equatable {
    public private(set) var timeoutActive: Bool
    public private(set) var lastActivity: TimeInterval

    public init(now: TimeInterval = Date().timeIntervalSince1970) {
        self.timeoutActive = false
        self.lastActivity = now
    }

    public mutating func noteActivity(now: TimeInterval) {
        lastActivity = now
        timeoutActive = false
    }

    public mutating func tick(
        now: TimeInterval,
        underlying: CodexTitleState,
        timeoutSeconds: TimeInterval
    ) -> Bool {
        let timeoutSeconds = max(0, timeoutSeconds)
        if timeoutSeconds <= 0 {
            if timeoutActive {
                timeoutActive = false
                return true
            }
            return false
        }

        if underlying != .running {
            if timeoutActive {
                timeoutActive = false
                return true
            }
            return false
        }

        if !timeoutActive && now - lastActivity >= timeoutSeconds {
            timeoutActive = true
            return true
        }

        return false
    }
}

