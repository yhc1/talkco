import Foundation

struct SessionSummary: Codable {
    let strengths: [String]
    let weaknesses: [String: String?]
    let overall: String
}
