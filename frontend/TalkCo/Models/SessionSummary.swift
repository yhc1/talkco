import Foundation

struct SessionSummary: Codable {
    let strengths: [String]
    let weaknesses: [String: String?]
    let levelAssessment: String
    let overall: String

    enum CodingKeys: String, CodingKey {
        case strengths
        case weaknesses
        case levelAssessment = "level_assessment"
        case overall
    }
}
