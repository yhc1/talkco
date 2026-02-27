import Foundation
@testable import TalkCo

final class MockAudioRecorder: AudioRecording {
    private(set) var isRecording = false
    var startRecordingError: Error?
    var stopRecordingData = Data()
    var permissionResult = true

    func requestPermission() async -> Bool {
        return permissionResult
    }

    func startRecording() throws {
        if let error = startRecordingError { throw error }
        isRecording = true
    }

    func stopRecording() -> Data {
        isRecording = false
        return stopRecordingData
    }
}
