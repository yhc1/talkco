import XCTest
@testable import TalkCo

final class SegmentCodableTests: XCTestCase {

    // MARK: - Segment

    func testSegmentDecodeFromJSON() throws {
        let json = TestFixtures.segmentJSON.data(using: .utf8)!
        let segment = try JSONDecoder().decode(Segment.self, from: json)

        XCTAssertEqual(segment.id, 1)
        XCTAssertEqual(segment.turnIndex, 0)
        XCTAssertEqual(segment.userText, "I go to store yesterday")
        XCTAssertEqual(segment.aiText, "That sounds nice!")
        XCTAssertEqual(segment.aiMarks.count, 1)
        XCTAssertEqual(segment.corrections.count, 1)
    }

    func testSegmentRoundTrip() throws {
        let original = TestFixtures.segment(
            aiMarks: [TestFixtures.aiMark()],
            corrections: [TestFixtures.correction()]
        )
        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(Segment.self, from: data)

        XCTAssertEqual(decoded.id, original.id)
        XCTAssertEqual(decoded.turnIndex, original.turnIndex)
        XCTAssertEqual(decoded.userText, original.userText)
        XCTAssertEqual(decoded.aiText, original.aiText)
    }

    func testSegmentWithEmptyMarksAndCorrections() throws {
        let json = """
        {
            "id": 5,
            "turn_index": 2,
            "user_text": "Hello",
            "ai_text": "Hi there!",
            "ai_marks": [],
            "corrections": []
        }
        """.data(using: .utf8)!

        let segment = try JSONDecoder().decode(Segment.self, from: json)
        XCTAssertEqual(segment.id, 5)
        XCTAssertTrue(segment.aiMarks.isEmpty)
        XCTAssertTrue(segment.corrections.isEmpty)
    }

    // MARK: - AIMark

    func testAIMarkDecode() throws {
        let json = """
        {
            "id": 2,
            "issue_types": ["grammar", "naturalness"],
            "original": "He go home",
            "suggestion": "He went home",
            "explanation": "Past tense"
        }
        """.data(using: .utf8)!

        let mark = try JSONDecoder().decode(AIMark.self, from: json)
        XCTAssertEqual(mark.id, 2)
        XCTAssertEqual(mark.issueTypes, ["grammar", "naturalness"])
        XCTAssertEqual(mark.original, "He go home")
        XCTAssertEqual(mark.suggestion, "He went home")
    }

    func testAIMarkRoundTrip() throws {
        let original = TestFixtures.aiMark(issueTypes: ["naturalness", "sentence_structure"])
        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(AIMark.self, from: data)

        XCTAssertEqual(decoded.id, original.id)
        XCTAssertEqual(decoded.issueTypes, original.issueTypes)
    }

    // MARK: - Correction

    func testCorrectionDecode() throws {
        let json = """
        {
            "id": 3,
            "user_message": "我想說的是...",
            "correction": "What I meant was...",
            "explanation": "Use 'what I meant' for clarification",
            "created_at": "2025-06-15T10:30:00Z"
        }
        """.data(using: .utf8)!

        let correction = try JSONDecoder().decode(Correction.self, from: json)
        XCTAssertEqual(correction.id, 3)
        XCTAssertEqual(correction.userMessage, "我想說的是...")
        XCTAssertEqual(correction.createdAt, "2025-06-15T10:30:00Z")
    }

    func testCorrectionRoundTrip() throws {
        let original = TestFixtures.correction()
        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(Correction.self, from: data)

        XCTAssertEqual(decoded.id, original.id)
        XCTAssertEqual(decoded.userMessage, original.userMessage)
        XCTAssertEqual(decoded.correction, original.correction)
    }
}
