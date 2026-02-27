import XCTest
@testable import TalkCo

final class AudioRecorderWAVTests: XCTestCase {

    func testWrapAsWAVHeaderSize() {
        let pcm = Data(repeating: 0, count: 100)
        let wav = AudioRecorder.wrapAsWAV(pcm: pcm, sampleRate: 24000)

        // WAV header is 44 bytes
        XCTAssertEqual(wav.count, 44 + 100)
    }

    func testWrapAsWAVEmptyPCM() {
        let pcm = Data()
        let wav = AudioRecorder.wrapAsWAV(pcm: pcm, sampleRate: 24000)

        // Header only
        XCTAssertEqual(wav.count, 44)
    }

    func testWrapAsWAVRIFFHeader() {
        let pcm = Data(repeating: 0x42, count: 200)
        let wav = AudioRecorder.wrapAsWAV(pcm: pcm, sampleRate: 24000)

        // Check RIFF magic
        let riff = String(data: wav[0..<4], encoding: .ascii)
        XCTAssertEqual(riff, "RIFF")

        // Check WAVE magic
        let wave = String(data: wav[8..<12], encoding: .ascii)
        XCTAssertEqual(wave, "WAVE")

        // Check fmt chunk
        let fmt = String(data: wav[12..<16], encoding: .ascii)
        XCTAssertEqual(fmt, "fmt ")

        // Check data chunk
        let dataChunk = String(data: wav[36..<40], encoding: .ascii)
        XCTAssertEqual(dataChunk, "data")
    }

    func testWrapAsWAVFileSize() {
        let pcm = Data(repeating: 0, count: 480)
        let wav = AudioRecorder.wrapAsWAV(pcm: pcm, sampleRate: 24000)

        // RIFF chunk size = 36 + dataSize
        let chunkSize = wav[4..<8].withUnsafeBytes { $0.load(as: UInt32.self) }
        XCTAssertEqual(chunkSize, 36 + 480)

        // data chunk size
        let dataSize = wav[40..<44].withUnsafeBytes { $0.load(as: UInt32.self) }
        XCTAssertEqual(dataSize, 480)
    }

    func testWrapAsWAVSampleRate() {
        let pcm = Data(repeating: 0, count: 10)
        let wav = AudioRecorder.wrapAsWAV(pcm: pcm, sampleRate: 24000)

        // Sample rate at offset 24 (4 bytes, little-endian)
        let sampleRate = wav[24..<28].withUnsafeBytes { $0.load(as: UInt32.self) }
        XCTAssertEqual(sampleRate, 24000)
    }

    func testWrapAsWAVPCMFormat() {
        let pcm = Data(repeating: 0, count: 10)
        let wav = AudioRecorder.wrapAsWAV(pcm: pcm, sampleRate: 24000)

        // Audio format at offset 20 (2 bytes) should be 1 (PCM)
        let format = wav[20..<22].withUnsafeBytes { $0.load(as: UInt16.self) }
        XCTAssertEqual(format, 1)

        // Channels at offset 22 (2 bytes) should be 1 (mono)
        let channels = wav[22..<24].withUnsafeBytes { $0.load(as: UInt16.self) }
        XCTAssertEqual(channels, 1)

        // Bits per sample at offset 34 (2 bytes) should be 16
        let bitsPerSample = wav[34..<36].withUnsafeBytes { $0.load(as: UInt16.self) }
        XCTAssertEqual(bitsPerSample, 16)
    }

    func testWrapAsWAVByteRate() {
        let pcm = Data(repeating: 0, count: 10)
        let wav = AudioRecorder.wrapAsWAV(pcm: pcm, sampleRate: 24000)

        // ByteRate = sampleRate * numChannels * bitsPerSample/8 = 24000 * 1 * 2 = 48000
        let byteRate = wav[28..<32].withUnsafeBytes { $0.load(as: UInt32.self) }
        XCTAssertEqual(byteRate, 48000)

        // BlockAlign = numChannels * bitsPerSample/8 = 1 * 2 = 2
        let blockAlign = wav[32..<34].withUnsafeBytes { $0.load(as: UInt16.self) }
        XCTAssertEqual(blockAlign, 2)
    }

    func testWrapAsWAVPreservesPCMData() {
        let pcm = Data([0x01, 0x02, 0x03, 0x04, 0x05])
        let wav = AudioRecorder.wrapAsWAV(pcm: pcm, sampleRate: 24000)

        // PCM data starts at offset 44
        let extractedPCM = wav[44...]
        XCTAssertEqual(Data(extractedPCM), pcm)
    }
}
