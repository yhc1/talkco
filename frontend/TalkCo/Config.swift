import Foundation

enum Config {
    #if targetEnvironment(simulator)
    static let baseURL = URL(string: "http://localhost:8000")!
    #else
    // When running on a real device, use your Mac's local IP
    static let baseURL = URL(string: "http://192.168.1.100:8000")!
    #endif

    static var userID: String {
        let key = "talkco_user_id"
        if let existing = UserDefaults.standard.string(forKey: key) {
            return existing
        }
        let id = UUID().uuidString
        UserDefaults.standard.set(id, forKey: key)
        return id
    }
}
