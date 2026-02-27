import Foundation
@testable import TalkCo

final class MockAudioPlayer: AudioPlaying {
    var scheduledChunks: [Data] = []
    var stopCalled = false

    func scheduleChunk(_ pcmData: Data) {
        scheduledChunks.append(pcmData)
    }

    func stop() {
        stopCalled = true
    }
}
