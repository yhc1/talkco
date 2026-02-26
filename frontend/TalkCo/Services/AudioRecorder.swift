import AVFoundation
import Foundation

/// Records PCM16, 24kHz, mono audio via AVAudioEngine.
/// Call `startRecording()` and `stopRecording()` to capture audio.
@Observable
final class AudioRecorder {
    private let engine = AVAudioEngine()
    private var audioData = Data()
    private(set) var isRecording = false

    private static let sampleRate: Double = 24000
    private static let channels: AVAudioChannelCount = 1

    /// Start capturing microphone audio.
    func startRecording() throws {
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.playAndRecord, mode: .default, options: [.defaultToSpeaker])
        try session.setActive(true)

        audioData = Data()
        let inputNode = engine.inputNode

        // Target format: PCM16, 24kHz, mono
        let targetFormat = AVAudioFormat(
            commonFormat: .pcmFormatInt16,
            sampleRate: Self.sampleRate,
            channels: Self.channels,
            interleaved: true
        )!

        let inputFormat = inputNode.outputFormat(forBus: 0)

        // Install tap with the hardware format, then convert
        inputNode.installTap(onBus: 0, bufferSize: 4096, format: inputFormat) { [weak self] buffer, _ in
            guard let self else { return }
            if let converted = Self.convert(buffer: buffer, from: inputFormat, to: targetFormat) {
                let byteCount = Int(converted.frameLength) * Int(converted.format.streamDescription.pointee.mBytesPerFrame)
                if let ptr = converted.int16ChannelData?[0] {
                    let data = Data(bytes: ptr, count: byteCount)
                    self.audioData.append(data)
                }
            }
        }

        engine.prepare()
        try engine.start()
        isRecording = true
    }

    /// Stop recording and return WAV-wrapped audio data.
    func stopRecording() -> Data {
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        isRecording = false

        let pcm = audioData
        audioData = Data()
        return Self.wrapAsWAV(pcm: pcm, sampleRate: UInt32(Self.sampleRate))
    }

    // MARK: - Helpers

    private static func convert(
        buffer: AVAudioPCMBuffer,
        from inputFormat: AVAudioFormat,
        to outputFormat: AVAudioFormat
    ) -> AVAudioPCMBuffer? {
        guard let converter = AVAudioConverter(from: inputFormat, to: outputFormat) else { return nil }
        let ratio = outputFormat.sampleRate / inputFormat.sampleRate
        let outputFrameCount = AVAudioFrameCount(Double(buffer.frameLength) * ratio)
        guard let outputBuffer = AVAudioPCMBuffer(pcmFormat: outputFormat, frameCapacity: outputFrameCount) else { return nil }

        var error: NSError?
        var consumed = false
        converter.convert(to: outputBuffer, error: &error) { _, outStatus in
            if consumed {
                outStatus.pointee = .noDataNow
                return nil
            }
            consumed = true
            outStatus.pointee = .haveData
            return buffer
        }
        return error == nil ? outputBuffer : nil
    }

    private static func wrapAsWAV(pcm: Data, sampleRate: UInt32) -> Data {
        var wav = Data()
        let dataSize = UInt32(pcm.count)
        let bitsPerSample: UInt16 = 16
        let numChannels: UInt16 = UInt16(channels)
        let byteRate = sampleRate * UInt32(numChannels) * UInt32(bitsPerSample / 8)
        let blockAlign = numChannels * (bitsPerSample / 8)

        // RIFF header
        wav.append("RIFF".data(using: .ascii)!)
        wav.append(withUnsafeBytes(of: (36 + dataSize).littleEndian) { Data($0) })
        wav.append("WAVE".data(using: .ascii)!)
        // fmt chunk
        wav.append("fmt ".data(using: .ascii)!)
        wav.append(withUnsafeBytes(of: UInt32(16).littleEndian) { Data($0) })
        wav.append(withUnsafeBytes(of: UInt16(1).littleEndian) { Data($0) })      // PCM
        wav.append(withUnsafeBytes(of: numChannels.littleEndian) { Data($0) })
        wav.append(withUnsafeBytes(of: sampleRate.littleEndian) { Data($0) })
        wav.append(withUnsafeBytes(of: byteRate.littleEndian) { Data($0) })
        wav.append(withUnsafeBytes(of: blockAlign.littleEndian) { Data($0) })
        wav.append(withUnsafeBytes(of: bitsPerSample.littleEndian) { Data($0) })
        // data chunk
        wav.append("data".data(using: .ascii)!)
        wav.append(withUnsafeBytes(of: dataSize.littleEndian) { Data($0) })
        wav.append(pcm)
        return wav
    }
}
