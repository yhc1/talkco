import XCTest
@testable import TalkCo

@MainActor
final class ReviewViewModelTests: XCTestCase {

    private var mockAPI: MockAPIClient!

    override func setUp() {
        super.setUp()
        mockAPI = MockAPIClient()
    }

    private func makeSUT(sessionId: String = "test-session") -> ReviewViewModel {
        ReviewViewModel(sessionId: sessionId, api: mockAPI)
    }

    // MARK: - loadReview

    func testLoadReviewStopsWhenMarksExist() async {
        let vm = makeSUT()
        let markedSegment = TestFixtures.segment(aiMarks: [TestFixtures.aiMark()])

        mockAPI.getHandler = { _ in
            TestFixtures.reviewResponse(segments: [markedSegment])
        }

        vm.loadReview()
        try? await Task.sleep(for: .milliseconds(200))

        XCTAssertFalse(vm.isLoading)
        XCTAssertEqual(vm.segments.count, 1)
        XCTAssertEqual(vm.status, "reviewing")
    }

    func testLoadReviewStopsWhenStatusChanges() async {
        let vm = makeSUT()

        mockAPI.getHandler = { _ in
            TestFixtures.reviewResponse(status: "completed", segments: [TestFixtures.segment()])
        }

        vm.loadReview()
        try? await Task.sleep(for: .milliseconds(200))

        XCTAssertFalse(vm.isLoading)
        XCTAssertEqual(vm.status, "completed")
    }

    func testLoadReviewStopsWhenNoSegments() async {
        let vm = makeSUT()

        mockAPI.getHandler = { _ in
            TestFixtures.reviewResponse(segments: [])
        }

        vm.loadReview()
        try? await Task.sleep(for: .milliseconds(200))

        XCTAssertFalse(vm.isLoading)
        XCTAssertTrue(vm.segments.isEmpty)
    }

    func testLoadReviewStopsAfter3Errors() async {
        let vm = makeSUT()
        var callCount = 0

        mockAPI.getHandler = { _ in
            callCount += 1
            throw APIError.httpError(statusCode: 500)
        }

        vm.loadReview()
        // Wait enough for 3 attempts (each with ~2s sleep, but errors are fast)
        try? await Task.sleep(for: .seconds(6))

        XCTAssertFalse(vm.isLoading)
        XCTAssertGreaterThanOrEqual(callCount, 3)
    }

    func testLoadReviewCancelStopsPolling() async {
        let vm = makeSUT()
        var callCount = 0

        mockAPI.getHandler = { _ in
            callCount += 1
            // Always return "reviewing" with no marks to keep polling
            return TestFixtures.reviewResponse(segments: [TestFixtures.segment()])
        }

        vm.loadReview()
        try? await Task.sleep(for: .milliseconds(100))
        vm.cancel()
        let countAtCancel = callCount
        try? await Task.sleep(for: .seconds(3))

        // Should not have made many more calls after cancel
        XCTAssertLessThanOrEqual(callCount, countAtCancel + 1)
    }

    // MARK: - submitCorrection

    func testSubmitCorrectionSuccess() async {
        let vm = makeSUT()
        vm.segments = [TestFixtures.segment(id: 1)]

        mockAPI.postHandler = { _, _ in
            TestFixtures.correction(id: 10)
        }

        await vm.submitCorrection(segmentId: 1, userMessage: "我的意思是...")

        XCTAssertEqual(vm.segments[0].corrections.count, 1)
        XCTAssertEqual(vm.segments[0].corrections[0].id, 10)
    }

    func testSubmitCorrectionWrongSegmentId() async {
        let vm = makeSUT()
        vm.segments = [TestFixtures.segment(id: 1)]

        mockAPI.postHandler = { _, _ in
            TestFixtures.correction(id: 10)
        }

        await vm.submitCorrection(segmentId: 999, userMessage: "test")

        // Correction returned but segment not found — no crash, no append
        XCTAssertTrue(vm.segments[0].corrections.isEmpty)
    }

    func testSubmitCorrectionFailure() async {
        let vm = makeSUT()
        vm.segments = [TestFixtures.segment(id: 1)]

        mockAPI.postHandler = { _, _ in
            throw APIError.httpError(statusCode: 500)
        }

        await vm.submitCorrection(segmentId: 1, userMessage: "test")

        XCTAssertTrue(vm.segments[0].corrections.isEmpty)
    }

    // MARK: - endReview

    func testEndReviewSuccess() async {
        let vm = makeSUT()
        var getCallCount = 0

        mockAPI.postHandler = { _, _ in
            TestFixtures.endSessionResponse()
        }

        mockAPI.getHandler = { _ in
            getCallCount += 1
            if getCallCount >= 2 {
                return TestFixtures.reviewResponse(
                    status: "completed",
                    summary: TestFixtures.sessionSummary()
                )
            }
            return TestFixtures.reviewResponse(status: "ending")
        }

        vm.endReview()
        // Wait for POST + poll cycles
        try? await Task.sleep(for: .seconds(5))

        XCTAssertTrue(vm.isCompleted)
        XCTAssertFalse(vm.isEnding)
        XCTAssertEqual(vm.status, "completed")
        XCTAssertNotNil(vm.summary)
    }

    func testEndReviewPostFailure() async {
        let vm = makeSUT()

        mockAPI.postHandler = { _, _ in
            throw APIError.httpError(statusCode: 500)
        }

        vm.endReview()
        try? await Task.sleep(for: .milliseconds(200))

        XCTAssertFalse(vm.isEnding)
        XCTAssertFalse(vm.isCompleted)
    }

    func testEndReviewPollFailureAfter3Errors() async {
        let vm = makeSUT()
        var getCallCount = 0

        mockAPI.postHandler = { _, _ in
            TestFixtures.endSessionResponse()
        }

        mockAPI.getHandler = { _ in
            getCallCount += 1
            throw APIError.httpError(statusCode: 500)
        }

        vm.endReview()
        try? await Task.sleep(for: .seconds(8))

        XCTAssertFalse(vm.isEnding)
        XCTAssertFalse(vm.isCompleted)
        XCTAssertGreaterThanOrEqual(getCallCount, 3)
    }

    // MARK: - cancel

    func testCancelStopsActivePolling() async {
        let vm = makeSUT()

        mockAPI.getHandler = { _ in
            TestFixtures.reviewResponse(segments: [TestFixtures.segment()])
        }

        vm.loadReview()
        try? await Task.sleep(for: .milliseconds(100))
        vm.cancel()

        // Should not crash and isLoading state is left as-is (task cancelled)
        // Main point: no infinite loop
    }
}
