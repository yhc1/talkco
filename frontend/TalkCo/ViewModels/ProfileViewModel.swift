import Foundation
import os

private let log = Logger(subsystem: "com.talkco", category: "Profile")

@Observable
final class ProfileViewModel {
    var isLoading = false
    var profile: UserProfile?

    private let api: any APIClientProtocol

    init(api: any APIClientProtocol = LiveAPIClient()) {
        self.api = api
    }

    func loadProfile() async {
        isLoading = true
        do {
            profile = try await api.get("/users/\(Config.userID)/profile")
            log.info("Profile loaded: level=\(self.profile?.level ?? "?")")
        } catch {
            log.error("Failed to load profile: \(error)")
        }
        isLoading = false
    }
}
