import Foundation

private struct AppConfig: Decodable {
    let useCloudBackend: Bool
    let cloudBackendUrl: String
    let localBackendUrl: String
    let deviceBackendUrl: String
    let userName: String?

    enum CodingKeys: String, CodingKey {
        case useCloudBackend = "use_cloud_backend"
        case cloudBackendUrl = "cloud_backend_url"
        case localBackendUrl = "local_backend_url"
        case deviceBackendUrl = "device_backend_url"
        case userName = "user_name"
    }
}

private let appConfig: AppConfig = {
    guard let url = Bundle.main.url(forResource: "app_config", withExtension: "json"),
          let data = try? Data(contentsOf: url),
          let config = try? JSONDecoder().decode(AppConfig.self, from: data) else {
        fatalError("Missing or invalid app_config.json")
    }
    return config
}()

enum Config {
    static let baseURL: URL = {
        if appConfig.useCloudBackend {
            return URL(string: appConfig.cloudBackendUrl)!
        }
        #if targetEnvironment(simulator)
        return URL(string: appConfig.localBackendUrl)!
        #else
        return URL(string: appConfig.deviceBackendUrl)!
        #endif
    }()

    /// User name from app_config.json (e.g. "wayne"). Nil if not set.
    static var userName: String? { appConfig.userName }

    /// Numeric user ID (9 digits), generated once and persisted in UserDefaults.
    static var userID: String {
        let key = "talkco_user_id"
        if let existing = UserDefaults.standard.string(forKey: key),
           existing.allSatisfy(\.isNumber) {
            return existing
        }
        let id = String(Int.random(in: 100_000_000...999_999_999))
        UserDefaults.standard.set(id, forKey: key)
        return id
    }
}
