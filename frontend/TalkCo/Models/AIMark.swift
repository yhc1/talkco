import Foundation

struct AIMark: Identifiable, Codable {
    let id: Int
    let issueTypes: [String]
    let original: String
    let suggestion: String
    let explanation: String

    enum CodingKeys: String, CodingKey {
        case id
        case issueTypes = "issue_types"
        case original
        case suggestion
        case explanation
    }
}
