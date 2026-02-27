import XCTest
@testable import TalkCo

final class TopicTests: XCTestCase {

    func testSixTopicsExist() {
        XCTAssertEqual(Topic.all.count, 6)
    }

    func testUniqueIDs() {
        let ids = Topic.all.map(\.id)
        XCTAssertEqual(Set(ids).count, ids.count, "Topic IDs must be unique")
    }

    func testExpectedIDs() {
        let ids = Set(Topic.all.map(\.id))
        let expected: Set<String> = ["daily_life", "travel", "workplace", "food_dining", "entertainment", "current_events"]
        XCTAssertEqual(ids, expected)
    }

    func testNonEmptyFields() {
        for topic in Topic.all {
            XCTAssertFalse(topic.id.isEmpty, "id should not be empty")
            XCTAssertFalse(topic.labelEn.isEmpty, "labelEn should not be empty for \(topic.id)")
            XCTAssertFalse(topic.labelZh.isEmpty, "labelZh should not be empty for \(topic.id)")
            XCTAssertFalse(topic.promptHint.isEmpty, "promptHint should not be empty for \(topic.id)")
            XCTAssertFalse(topic.icon.isEmpty, "icon should not be empty for \(topic.id)")
        }
    }

    func testIdentifiableConformance() {
        let topic = Topic.all[0]
        XCTAssertEqual(topic.id, "daily_life")
    }
}
