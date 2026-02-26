import Foundation

struct Segment: Identifiable, Codable {
    let id: Int
    let turnIndex: Int
    let userText: String
    let aiText: String
    var aiMarks: [AIMark]
    var corrections: [Correction]

    enum CodingKeys: String, CodingKey {
        case id
        case turnIndex = "turn_index"
        case userText = "user_text"
        case aiText = "ai_text"
        case aiMarks = "ai_marks"
        case corrections
    }
}
