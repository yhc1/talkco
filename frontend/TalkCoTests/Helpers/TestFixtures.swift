import Foundation
@testable import TalkCo

enum TestFixtures {

    // MARK: - Segments

    static func segment(
        id: Int = 1,
        turnIndex: Int = 0,
        userText: String = "I go to store yesterday",
        aiText: String = "That sounds nice!",
        aiMarks: [AIMark] = [],
        corrections: [Correction] = []
    ) -> Segment {
        Segment(
            id: id,
            turnIndex: turnIndex,
            userText: userText,
            aiText: aiText,
            aiMarks: aiMarks,
            corrections: corrections
        )
    }

    static func aiMark(
        id: Int = 1,
        issueTypes: [String] = ["grammar"],
        original: String = "I go to store yesterday",
        suggestion: String = "I went to the store yesterday",
        explanation: String = "Past tense required"
    ) -> AIMark {
        AIMark(
            id: id,
            issueTypes: issueTypes,
            original: original,
            suggestion: suggestion,
            explanation: explanation
        )
    }

    static func correction(
        id: Int = 1,
        userMessage: String = "我昨天去了商店",
        correction: String = "I went to the store yesterday",
        explanation: String = "Use past tense for completed actions",
        createdAt: String = "2025-01-01T00:00:00Z"
    ) -> Correction {
        Correction(
            id: id,
            userMessage: userMessage,
            correction: correction,
            explanation: explanation,
            createdAt: createdAt
        )
    }

    // MARK: - Session Responses

    static func createSessionResponse(
        sessionId: String = "test-session-123",
        createdAt: String = "2025-01-01T00:00:00Z"
    ) -> CreateSessionResponse {
        CreateSessionResponse(sessionId: sessionId, createdAt: createdAt)
    }

    static func deleteSessionResponse(
        sessionId: String = "test-session-123",
        status: String = "deleted"
    ) -> DeleteSessionResponse {
        DeleteSessionResponse(sessionId: sessionId, status: status)
    }

    static func reviewResponse(
        sessionId: String = "test-session-123",
        status: String = "reviewing",
        segments: [Segment] = [],
        summary: SessionSummary? = nil
    ) -> ReviewResponse {
        ReviewResponse(sessionId: sessionId, status: status, segments: segments, summary: summary)
    }

    static func endSessionResponse(
        sessionId: String = "test-session-123",
        status: String = "ending"
    ) -> EndSessionResponse {
        EndSessionResponse(sessionId: sessionId, status: status)
    }

    static func sessionSummary(
        strengths: [String] = ["Good vocabulary range"],
        weaknesses: [String: String?] = ["grammar": "Frequent tense errors", "naturalness": nil],
        levelAssessment: String = "B1",
        overall: String = "Good progress overall"
    ) -> SessionSummary {
        SessionSummary(
            strengths: strengths,
            weaknesses: weaknesses,
            levelAssessment: levelAssessment,
            overall: overall
        )
    }

    // MARK: - JSON Strings

    static let segmentJSON = """
    {
        "id": 1,
        "turn_index": 0,
        "user_text": "I go to store yesterday",
        "ai_text": "That sounds nice!",
        "ai_marks": [{
            "id": 1,
            "issue_types": ["grammar"],
            "original": "I go to store yesterday",
            "suggestion": "I went to the store yesterday",
            "explanation": "Past tense required"
        }],
        "corrections": [{
            "id": 1,
            "user_message": "我昨天去了商店",
            "correction": "I went to the store yesterday",
            "explanation": "Use past tense",
            "created_at": "2025-01-01T00:00:00Z"
        }]
    }
    """

    static let createSessionResponseJSON = """
    {"session_id": "test-123", "created_at": "2025-01-01T00:00:00Z"}
    """

    static let reviewResponseJSON = """
    {
        "session_id": "test-123",
        "status": "reviewing",
        "segments": [],
        "summary": null
    }
    """

    static let sessionSummaryJSON = """
    {
        "strengths": ["Good vocabulary"],
        "weaknesses": {"grammar": "Needs work", "naturalness": null},
        "level_assessment": "B1",
        "overall": "Good progress"
    }
    """
}
