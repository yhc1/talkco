import AVFoundation
import Foundation

/// Protocol for audio playback, enabling mock injection in tests.
protocol AudioPlaying: AnyObject {
    func scheduleChunk(_ pcmData: Data)
    func stop()
}

/// Plays streaming PCM16, 24kHz, mono audio chunks via AVAudioEngine.
/// Engine setup is deferred until the first chunk arrives.
final class AudioPlayer: AudioPlaying {
    private var engine: AVAudioEngine?
    private var playerNode: AVAudioPlayerNode?

    // Output format: Float32 (required by mixer), 24kHz, mono
    private let playbackFormat = AVAudioFormat(
        commonFormat: .pcmFormatFloat32,
        sampleRate: 24000,
        channels: 1,
        interleaved: false
    )!

    /// Schedule a chunk of PCM16 audio for playback.
    func scheduleChunk(_ pcmData: Data) {
        if engine == nil {
            setupEngine()
        }

        guard let playerNode else { return }

        let frameCount = AVAudioFrameCount(pcmData.count / 2) // 2 bytes per Int16 sample
        guard let buffer = AVAudioPCMBuffer(pcmFormat: playbackFormat, frameCapacity: frameCount) else { return }
        buffer.frameLength = frameCount

        // Convert PCM16 Int16 → Float32
        guard let dst = buffer.floatChannelData?[0] else { return }
        Self.convertInt16ToFloat32(pcmData, destination: dst, frameCount: Int(frameCount))

        playerNode.scheduleBuffer(buffer)
    }

    /// Stop playback and tear down engine.
    func stop() {
        playerNode?.stop()
        engine?.stop()
        engine = nil
        playerNode = nil
    }

    /// Convert PCM16 Int16 samples to Float32 in range [-1.0, 1.0).
    static func convertInt16ToFloat32(_ data: Data, destination: UnsafeMutablePointer<Float>, frameCount: Int) {
        data.withUnsafeBytes { raw in
            let src = raw.bindMemory(to: Int16.self)
            for i in 0..<frameCount {
                destination[i] = Float(src[i]) / 32768.0
            }
        }
    }

    private func setupEngine() {
        let e = AVAudioEngine()
        let p = AVAudioPlayerNode()
        e.attach(p)
        e.connect(p, to: e.mainMixerNode, format: playbackFormat)

        do {
            try e.start()
            p.play()
            engine = e
            playerNode = p
        } catch {
            print("AudioPlayer engine start failed: \(error)")
        }
    }
}
