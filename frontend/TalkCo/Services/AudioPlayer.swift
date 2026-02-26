import AVFoundation
import Foundation

/// Plays streaming PCM16, 24kHz, mono audio chunks via AVAudioEngine.
/// Engine setup is deferred until the first chunk arrives.
final class AudioPlayer {
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
        pcmData.withUnsafeBytes { raw in
            let src = raw.bindMemory(to: Int16.self)
            for i in 0..<Int(frameCount) {
                dst[i] = Float(src[i]) / 32768.0
            }
        }

        playerNode.scheduleBuffer(buffer)
    }

    /// Stop playback and tear down engine.
    func stop() {
        playerNode?.stop()
        engine?.stop()
        engine = nil
        playerNode = nil
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
