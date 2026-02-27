import XCTest
@testable import TalkCo

final class ChatMessageTests: XCTestCase {

    func testUUIDUniqueness() {
        let msg1 = ChatMessage(role: .user, text: "Hello")
        let msg2 = ChatMessage(role: .user, text: "Hello")
        XCTAssertNotEqual(msg1.id, msg2.id)
    }

    func testUserRole() {
        let msg = ChatMessage(role: .user, text: "Test")
        XCTAssertEqual(msg.role, .user)
        XCTAssertEqual(msg.text, "Test")
    }

    func testAIRole() {
        let msg = ChatMessage(role: .ai, text: "Response")
        XCTAssertEqual(msg.role, .ai)
        XCTAssertEqual(msg.text, "Response")
    }

    func testTextMutation() {
        var msg = ChatMessage(role: .ai, text: "Partial")
        msg.text = "Partial response completed"
        XCTAssertEqual(msg.text, "Partial response completed")
    }

    func testEmptyText() {
        let msg = ChatMessage(role: .user, text: "")
        XCTAssertTrue(msg.text.isEmpty)
    }
}
