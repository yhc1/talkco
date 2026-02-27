import XCTest
@testable import TalkCo

final class SessionSummaryTests: XCTestCase {

    func testDecodeFull() throws {
        let json = TestFixtures.sessionSummaryJSON.data(using: .utf8)!
        let summary = try JSONDecoder().decode(SessionSummary.self, from: json)

        XCTAssertEqual(summary.strengths, ["Good vocabulary"])
        XCTAssertEqual(summary.levelAssessment, "B1")
        XCTAssertEqual(summary.overall, "Good progress")
        XCTAssertEqual(summary.weaknesses["grammar"] as? String, "Needs work")
        // null value should decode as nil wrapped in Optional
        XCTAssertTrue(summary.weaknesses.keys.contains("naturalness"))
    }

    func testDecodeEmptyWeaknesses() throws {
        let json = """
        {
            "strengths": [],
            "weaknesses": {},
            "level_assessment": "A1",
            "overall": "Beginner"
        }
        """.data(using: .utf8)!
        let summary = try JSONDecoder().decode(SessionSummary.self, from: json)
        XCTAssertTrue(summary.strengths.isEmpty)
        XCTAssertTrue(summary.weaknesses.isEmpty)
    }

    func testRoundTrip() throws {
        let original = TestFixtures.sessionSummary()
        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(SessionSummary.self, from: data)

        XCTAssertEqual(decoded.strengths, original.strengths)
        XCTAssertEqual(decoded.levelAssessment, original.levelAssessment)
        XCTAssertEqual(decoded.overall, original.overall)
    }

    func testDecodeMultipleWeaknesses() throws {
        let json = """
        {
            "strengths": ["Fluent"],
            "weaknesses": {
                "grammar": "Tense errors",
                "vocabulary": "Limited range",
                "naturalness": null,
                "sentence_structure": "Too simple"
            },
            "level_assessment": "B2",
            "overall": "Intermediate"
        }
        """.data(using: .utf8)!
        let summary = try JSONDecoder().decode(SessionSummary.self, from: json)
        XCTAssertEqual(summary.weaknesses.count, 4)
        XCTAssertEqual(summary.weaknesses["grammar"] as? String, "Tense errors")
        XCTAssertEqual(summary.weaknesses["vocabulary"] as? String, "Limited range")
    }
}
