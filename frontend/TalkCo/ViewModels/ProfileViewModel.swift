import Foundation
import os

private let log = Logger(subsystem: "com.talkco", category: "Profile")

@Observable
final class ProfileViewModel {
    var isLoading = false
    var isEvaluating = false
    var isSavingLearningGoal = false
    var learningGoalInput = ""
    var profile: UserProfile?

    private let api: any APIClientProtocol

    init(api: any APIClientProtocol = LiveAPIClient()) {
        self.api = api
    }

    func loadProfile() async {
        isLoading = true
        do {
            profile = try await api.get("/users/\(Config.userID)/profile")
            learningGoalInput = profile?.learningGoal ?? ""
            log.info("Profile loaded: level=\(self.profile?.level ?? "?")")
        } catch {
            log.error("Failed to load profile: \(error)")
        }
        isLoading = false
    }

    func evaluateLevel() async {
        isEvaluating = true
        do {
            let empty: [String: String] = [:]
            profile = try await api.post("/users/\(Config.userID)/evaluate", body: empty)
            learningGoalInput = profile?.learningGoal ?? ""
            log.info("Level evaluated: \(self.profile?.level ?? "?")")
        } catch {
            log.error("Failed to evaluate level: \(error)")
        }
        isEvaluating = false
    }

    func saveLearningGoal() async {
        isSavingLearningGoal = true
        defer { isSavingLearningGoal = false }

        do {
            let body = UpdateLearningGoalRequest(learningGoal: learningGoalInput)
            profile = try await api.post("/users/\(Config.userID)/learning-goal", body: body)
            learningGoalInput = profile?.learningGoal ?? ""
            log.info("Learning goal updated")
        } catch {
            log.error("Failed to update learning goal: \(error)")
        }
    }
}

private struct UpdateLearningGoalRequest: Encodable, Sendable {
    let learningGoal: String?

    enum CodingKeys: String, CodingKey {
        case learningGoal = "learning_goal"
    }

    init(learningGoal: String) {
        let trimmed = learningGoal.trimmingCharacters(in: .whitespacesAndNewlines)
        self.learningGoal = trimmed.isEmpty ? nil : trimmed
    }
}
