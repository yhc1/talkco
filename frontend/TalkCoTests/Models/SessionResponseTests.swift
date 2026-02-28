import XCTest
@testable import TalkCo

final class SessionResponseTests: XCTestCase {

    // MARK: - CreateSessionResponse

    func testCreateSessionResponseDecode() throws {
        let json = TestFixtures.createSessionResponseJSON.data(using: .utf8)!
        let resp = try JSONDecoder().decode(CreateSessionResponse.self, from: json)
        XCTAssertEqual(resp.sessionId, "test-123")
        XCTAssertEqual(resp.createdAt, "2025-01-01T00:00:00Z")
    }

    func testCreateSessionResponseRoundTrip() throws {
        let original = TestFixtures.createSessionResponse()
        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(CreateSessionResponse.self, from: data)
        XCTAssertEqual(decoded.sessionId, original.sessionId)
        XCTAssertEqual(decoded.createdAt, original.createdAt)
    }

    // MARK: - DeleteSessionResponse

    func testDeleteSessionResponseDecode() throws {
        let json = """
        {"session_id": "sess-456", "status": "deleted"}
        """.data(using: .utf8)!
        let resp = try JSONDecoder().decode(DeleteSessionResponse.self, from: json)
        XCTAssertEqual(resp.sessionId, "sess-456")
        XCTAssertEqual(resp.status, "deleted")
    }

    func testDeleteSessionResponseRoundTrip() throws {
        let original = TestFixtures.deleteSessionResponse()
        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(DeleteSessionResponse.self, from: data)
        XCTAssertEqual(decoded.sessionId, original.sessionId)
        XCTAssertEqual(decoded.status, original.status)
    }

    // MARK: - ReviewResponse

    func testReviewResponseDecodeEmpty() throws {
        let json = TestFixtures.reviewResponseJSON.data(using: .utf8)!
        let resp = try JSONDecoder().decode(ReviewResponse.self, from: json)
        XCTAssertEqual(resp.sessionId, "test-123")
        XCTAssertEqual(resp.status, "reviewing")
        XCTAssertTrue(resp.segments.isEmpty)
        XCTAssertNil(resp.summary)
    }

    func testReviewResponseDecodeWithSegmentsAndSummary() throws {
        let json = """
        {
            "session_id": "s-1",
            "status": "completed",
            "segments": [{
                "id": 1,
                "turn_index": 0,
                "user_text": "Hello",
                "ai_text": "Hi",
                "ai_marks": [],
                "corrections": []
            }],
            "summary": {
                "strengths": ["Good"],
                "weaknesses": {},
                "overall": "OK"
            }
        }
        """.data(using: .utf8)!
        let resp = try JSONDecoder().decode(ReviewResponse.self, from: json)
        XCTAssertEqual(resp.segments.count, 1)
        XCTAssertNotNil(resp.summary)
        XCTAssertEqual(resp.summary?.overall, "OK")
    }

    // MARK: - EndSessionResponse

    func testEndSessionResponseDecode() throws {
        let json = """
        {"session_id": "sess-789", "status": "ending"}
        """.data(using: .utf8)!
        let resp = try JSONDecoder().decode(EndSessionResponse.self, from: json)
        XCTAssertEqual(resp.sessionId, "sess-789")
        XCTAssertEqual(resp.status, "ending")
    }

    // MARK: - CorrectionRequest

    func testCorrectionRequestEncode() throws {
        let req = CorrectionRequest(segmentId: 5, userMessage: "我的意思是...")
        let data = try JSONEncoder().encode(req)
        let dict = try JSONSerialization.jsonObject(with: data) as! [String: Any]
        XCTAssertEqual(dict["segment_id"] as? Int, 5)
        XCTAssertEqual(dict["user_message"] as? String, "我的意思是...")
    }
}
