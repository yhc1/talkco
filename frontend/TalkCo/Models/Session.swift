import Foundation

struct CreateSessionResponse: Codable {
    let sessionId: String
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
        case createdAt = "created_at"
    }
}

struct DeleteSessionResponse: Codable {
    let sessionId: String
    let status: String
    let mode: String?

    enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
        case status
        case mode
    }
}

struct ReviewResponse: Codable {
    let sessionId: String
    let status: String
    let segments: [Segment]
    let summary: SessionSummary?

    enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
        case status
        case segments
        case summary
    }
}

struct CorrectionRequest: Encodable {
    let segmentId: Int
    let userMessage: String

    enum CodingKeys: String, CodingKey {
        case segmentId = "segment_id"
        case userMessage = "user_message"
    }
}

struct EndSessionResponse: Codable {
    let sessionId: String
    let status: String

    enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
        case status
    }
}
