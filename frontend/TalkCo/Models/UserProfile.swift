import Foundation

struct UserProfile: Codable {
    let userId: String
    let level: String
    let profileData: ProfileData
    let updatedAt: String

    enum CodingKeys: String, CodingKey {
        case userId = "user_id"
        case level
        case profileData = "profile_data"
        case updatedAt = "updated_at"
    }
}

struct ProfileData: Codable {
    let learnedExpressions: [String]
    let weakPoints: WeakPoints
    let progressNotes: String
    let sessionCount: Int
    let commonErrors: [String]

    enum CodingKeys: String, CodingKey {
        case learnedExpressions = "learned_expressions"
        case weakPoints = "weak_points"
        case progressNotes = "progress_notes"
        case sessionCount = "session_count"
        case commonErrors = "common_errors"
    }
}

struct WeakPoints: Codable {
    let grammar: [String]
    let naturalness: [String]
    let vocabulary: [String]
    let sentenceStructure: [String]

    enum CodingKeys: String, CodingKey {
        case grammar
        case naturalness
        case vocabulary
        case sentenceStructure = "sentence_structure"
    }
}
