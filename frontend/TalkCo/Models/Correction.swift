import Foundation

struct Correction: Identifiable, Codable {
    let id: Int
    let userMessage: String
    let correction: String
    let explanation: String
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case userMessage = "user_message"
        case correction
        case explanation
        case createdAt = "created_at"
    }
}
