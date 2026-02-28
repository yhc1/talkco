import XCTest
@testable import TalkCo

final class SessionSummaryTests: XCTestCase {

    func testDecodeFull() throws {
        let json = TestFixtures.sessionSummaryJSON.data(using: .utf8)!
        let summary = try JSONDecoder().decode(SessionSummary.self, from: json)

        XCTAssertEqual(summary.strengths, ["Good vocabulary"])
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
        XCTAssertEqual(decoded.overall, original.overall)
    }

    func testDecodeMultipleWeaknesses() throws {
        let json = """
        {
            "strengths": ["Fluent"],
            "weaknesses": {
                "grammar": "Tense errors",
                "naturalness": null,
                "sentence_structure": "Too simple"
            },
            "overall": "Intermediate"
        }
        """.data(using: .utf8)!
        let summary = try JSONDecoder().decode(SessionSummary.self, from: json)
        XCTAssertEqual(summary.weaknesses.count, 3)
        XCTAssertEqual(summary.weaknesses["grammar"] as? String, "Tense errors")
        XCTAssertEqual(summary.weaknesses["sentence_structure"] as? String, "Too simple")
    }
}
