import XCTest
@testable import TalkCo

final class ConfigTests: XCTestCase {

    func testBaseURLIsValid() {
        let url = Config.baseURL
        XCTAssertNotNil(url.scheme)
        XCTAssertNotNil(url.host)
        XCTAssertTrue(url.scheme == "http" || url.scheme == "https")
    }

    func testUserIDIsNotEmpty() {
        let id = Config.userID
        XCTAssertFalse(id.isEmpty)
    }

    func testUserIDIsPersistent() {
        let id1 = Config.userID
        let id2 = Config.userID
        XCTAssertEqual(id1, id2)
    }

    func testUserIDIsValidUUID() {
        let id = Config.userID
        XCTAssertNotNil(UUID(uuidString: id), "userID should be a valid UUID string")
    }
}
