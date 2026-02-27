import XCTest
@testable import TalkCo

@MainActor
final class ConversationViewModelTests: XCTestCase {

    private var mockAPI: MockAPIClient!
    private var mockRecorder: MockAudioRecorder!
    private var mockPlayer: MockAudioPlayer!
    private var topic: Topic!

    override func setUp() {
        super.setUp()
        mockAPI = MockAPIClient()
        mockRecorder = MockAudioRecorder()
        mockPlayer = MockAudioPlayer()
        topic = Topic.all[0]
    }

    private func makeSUT() -> ConversationViewModel {
        ConversationViewModel(topic: topic, api: mockAPI, recorder: mockRecorder, player: mockPlayer)
    }

    // MARK: - startSession

    func testStartSessionSuccess() async {
        let vm = makeSUT()

        mockAPI.postHandler = { path, _ in
            TestFixtures.createSessionResponse(sessionId: "s-1")
        }
        mockAPI.streamSSEHandler = { _ in
            AsyncThrowingStream { continuation in
                continuation.yield(SSEvent(event: "response", data: "{\"text\":\"Hello!\"}"))
                continuation.finish()
            }
        }

        XCTAssertTrue(vm.isConnecting)
        await vm.startSession()

        XCTAssertFalse(vm.isConnecting)
        XCTAssertEqual(vm.sessionId, "s-1")
        XCTAssertEqual(vm.messages.count, 1)
        XCTAssertEqual(vm.messages.first?.text, "Hello!")
        XCTAssertEqual(vm.messages.first?.role, .ai)
    }

    func testStartSessionFailure() async {
        let vm = makeSUT()

        mockAPI.postHandler = { _, _ in
            throw APIError.httpError(statusCode: 500)
        }

        await vm.startSession()

        XCTAssertFalse(vm.isConnecting)
        XCTAssertNil(vm.sessionId)
        XCTAssertTrue(vm.messages.isEmpty)
    }

    func testStartSessionWithAudioChunks() async {
        let vm = makeSUT()

        // Base64 of 2 bytes
        let audioB64 = Data([0x01, 0x02]).base64EncodedString()

        mockAPI.postHandler = { _, _ in
            TestFixtures.createSessionResponse()
        }
        mockAPI.streamSSEHandler = { _ in
            AsyncThrowingStream { continuation in
                continuation.yield(SSEvent(event: "audio", data: "{\"audio\":\"\(audioB64)\"}"))
                continuation.yield(SSEvent(event: "response", data: "{\"text\":\"Hi\"}"))
                continuation.finish()
            }
        }

        await vm.startSession()

        XCTAssertEqual(mockPlayer.scheduledChunks.count, 1)
        XCTAssertEqual(mockPlayer.scheduledChunks[0], Data([0x01, 0x02]))
    }

    // MARK: - Recording

    func testStartRecordingSetsState() async {
        let vm = makeSUT()
        await setupSession(vm)

        vm.startRecording()

        XCTAssertTrue(vm.isRecording)
        XCTAssertTrue(mockRecorder.isRecording)
    }

    func testStartRecordingFailure() async {
        let vm = makeSUT()
        await setupSession(vm)
        mockRecorder.startRecordingError = NSError(domain: "test", code: 1)

        vm.startRecording()

        XCTAssertFalse(vm.isRecording)
    }

    func testStartRecordingWhileProcessingIsIgnored() async {
        let vm = makeSUT()
        await setupSession(vm)

        // Stub streamSSE(body:) to hang so isProcessing stays true
        mockAPI.streamSSEBodyHandler = { _, _ in
            AsyncThrowingStream { continuation in
                // Never finish — keeps isProcessing = true
            }
        }

        vm.sendText("hello") // This sets isProcessing
        // Give the Task a moment to start
        try? await Task.sleep(for: .milliseconds(50))
        vm.startRecording()

        XCTAssertFalse(mockRecorder.isRecording)
    }

    func testStartRecordingWhileEndedIsIgnored() async {
        let vm = makeSUT()
        await setupSession(vm)

        mockAPI.deleteHandler = { _ in TestFixtures.deleteSessionResponse() }
        _ = await vm.endConversation()

        vm.startRecording()
        XCTAssertFalse(mockRecorder.isRecording)
    }

    func testStopRecordingWhenNotRecordingIsIgnored() {
        let vm = makeSUT()
        vm.stopRecording()
        // Should not crash
        XCTAssertFalse(vm.isRecording)
    }

    func testConsecutiveRecordingCycles() async {
        let vm = makeSUT()
        await setupSession(vm)

        mockAPI.streamMultipartHandler = { _, _, _, _, _ in
            AsyncThrowingStream { continuation in
                continuation.yield(SSEvent(event: "transcript", data: "{\"text\":\"hello\"}"))
                continuation.yield(SSEvent(event: "response", data: "{\"text\":\"hi\"}"))
                continuation.finish()
            }
        }

        // First recording cycle
        vm.startRecording()
        XCTAssertTrue(vm.isRecording)
        XCTAssertTrue(mockRecorder.isRecording)

        vm.stopRecording()
        XCTAssertFalse(vm.isRecording)
        XCTAssertTrue(vm.isProcessing)

        // Wait for audio processing to complete
        try? await Task.sleep(for: .milliseconds(100))
        XCTAssertFalse(vm.isProcessing)

        // Second recording cycle — must not crash
        vm.startRecording()
        XCTAssertTrue(vm.isRecording)
        XCTAssertTrue(mockRecorder.isRecording)

        vm.stopRecording()
        XCTAssertFalse(vm.isRecording)
        XCTAssertTrue(vm.isProcessing)
    }

    // MARK: - sendText

    func testSendTextSuccess() async {
        let vm = makeSUT()
        await setupSession(vm)

        mockAPI.streamSSEBodyHandler = { _, _ in
            AsyncThrowingStream { continuation in
                continuation.yield(SSEvent(event: "transcript", data: "{\"text\":\"How are you?\"}"))
                continuation.yield(SSEvent(event: "response", data: "{\"text\":\"I'm fine!\"}"))
                continuation.finish()
            }
        }

        vm.sendText("How are you?")
        // Wait for the async task to complete
        try? await Task.sleep(for: .milliseconds(100))

        // Initial greeting + user message + AI response
        XCTAssertEqual(vm.messages.count, 3) // greeting + transcript + response
    }

    func testSendTextEmptyIsIgnored() async {
        let vm = makeSUT()
        await setupSession(vm)

        vm.sendText("")
        XCTAssertFalse(vm.isProcessing)
    }

    func testSendTextWhitespaceOnlyIsIgnored() async {
        let vm = makeSUT()
        await setupSession(vm)

        vm.sendText("   ")
        XCTAssertFalse(vm.isProcessing)
    }

    func testSendTextWhileEndedIsIgnored() async {
        let vm = makeSUT()
        await setupSession(vm)

        mockAPI.deleteHandler = { _ in TestFixtures.deleteSessionResponse() }
        _ = await vm.endConversation()

        vm.sendText("hello")
        XCTAssertFalse(vm.isProcessing)
    }

    // MARK: - endConversation

    func testEndConversationSuccess() async {
        let vm = makeSUT()
        await setupSession(vm)

        mockAPI.deleteHandler = { _ in TestFixtures.deleteSessionResponse() }

        let sessionId = await vm.endConversation()

        XCTAssertNotNil(sessionId)
        XCTAssertTrue(vm.isEnded)
        XCTAssertTrue(mockPlayer.stopCalled)
    }

    func testEndConversationFailure() async {
        let vm = makeSUT()
        await setupSession(vm)

        mockAPI.deleteHandler = { _ in throw APIError.httpError(statusCode: 500) }

        let sessionId = await vm.endConversation()

        XCTAssertNil(sessionId)
        XCTAssertTrue(vm.isEnded) // isEnded is set before the API call
    }

    func testEndConversationNoSession() async {
        let vm = makeSUT()

        let sessionId = await vm.endConversation()

        XCTAssertNil(sessionId)
    }

    // MARK: - Helpers

    private func setupSession(_ vm: ConversationViewModel) async {
        mockAPI.postHandler = { _, _ in TestFixtures.createSessionResponse() }
        mockAPI.streamSSEHandler = { _ in
            AsyncThrowingStream { continuation in
                continuation.yield(SSEvent(event: "response", data: "{\"text\":\"Hi\"}"))
                continuation.finish()
            }
        }
        await vm.startSession()
    }
}
