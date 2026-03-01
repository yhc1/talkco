import Foundation
import os
import SwiftUI

private let log = Logger(subsystem: "com.talkco", category: "Conversation")

@Observable
final class ConversationViewModel {
    var messages: [ChatMessage] = []
    var isConnecting = true
    var isRecording = false
    var isProcessing = false
    var isEnded = false

    private let topic: Topic?
    private let mode: SessionMode
    private(set) var sessionId: String?
    private let api: any APIClientProtocol
    private let recorder: AudioRecording
    private let player: AudioPlaying

    init(topic: Topic? = nil, mode: SessionMode = .conversation, api: any APIClientProtocol = LiveAPIClient(), recorder: AudioRecording = AudioRecorder(), player: AudioPlaying = AudioPlayer()) {
        self.topic = topic
        self.mode = mode
        self.api = api
        self.recorder = recorder
        self.player = player
    }

    // MARK: - Session lifecycle

    func startSession() async {
        isConnecting = true

        // Request microphone permission upfront so recording can be synchronous
        let granted = await recorder.requestPermission()
        if !granted {
            log.warning("Microphone permission denied")
        }

        do {
            let body = CreateSessionBody(userId: Config.userID, topicId: topic?.id, mode: mode)
            let resp: CreateSessionResponse = try await api.post("/sessions", body: body)
            sessionId = resp.sessionId
            log.info("Session created: \(resp.sessionId) mode=\(self.mode.rawValue)")

            // Stream AI greeting (backend waits internally for WebSocket ready)
            await streamGreeting()
            isConnecting = false
        } catch {
            log.error("Failed to start session: \(error)")
            isConnecting = false
        }
    }

    private func streamGreeting() async {
        guard let sessionId else { return }

        var text = ""
        do {
            for try await event in api.streamSSE("/sessions/\(sessionId)/start") {
                switch event.event {
                case "response":
                    if let data = parseJSON(event.data), let t = data["text"] as? String {
                        text = t
                    }
                case "audio":
                    if let data = parseJSON(event.data), let b64 = data["audio"] as? String,
                       let audioData = Data(base64Encoded: b64) {
                        player.scheduleChunk(audioData)
                    }
                default:
                    break
                }
            }
        } catch {
            log.error("Greeting stream error: \(error)")
            return
        }

        if !text.isEmpty {
            messages.append(ChatMessage(role: .ai, text: text))
        }
        log.info("Greeting received: \(text.prefix(80))")
    }

    // MARK: - Recording (push-to-talk)

    func startRecording() {
        guard !isProcessing, !isEnded, !isRecording else { return }
        do {
            try recorder.startRecording()
            isRecording = true
        } catch {
            log.error("Failed to start recording: \(error)")
        }
    }

    func stopRecording() {
        guard isRecording else { return }
        let wavData = recorder.stopRecording()
        isRecording = false

        // Check if audio has meaningful speech (not just silence/noise)
        if !Self.hasSpeech(wavData) {
            log.info("Audio too quiet, discarding")
            return
        }

        isProcessing = true
        Task {
            await sendAudio(wavData)
            isProcessing = false
        }
    }

    /// Check PCM16 WAV audio RMS energy. Returns false if below speech threshold.
    private static func hasSpeech(_ wavData: Data) -> Bool {
        // WAV header is 44 bytes, PCM16 samples follow
        guard wavData.count > 44 else { return false }
        let pcm = wavData.dropFirst(44)
        let sampleCount = pcm.count / 2
        guard sampleCount > 0 else { return false }

        var sumSquares: Double = 0
        pcm.withUnsafeBytes { raw in
            let samples = raw.bindMemory(to: Int16.self)
            for i in 0..<sampleCount {
                let s = Double(samples[i])
                sumSquares += s * s
            }
        }
        let rms = sqrt(sumSquares / Double(sampleCount))
        // Int16 range is -32768...32767. Threshold ~300 filters out typical background noise.
        return rms > 300
    }

    private func sendAudio(_ wavData: Data) async {
        guard let sessionId else { return }
        var userTranscript = ""
        var aiText = ""

        do {
            for try await event in api.streamMultipart(
                "/sessions/\(sessionId)/chat",
                fileData: wavData,
                fileName: "audio.wav",
                fieldName: "audio",
                mimeType: "audio/wav"
            ) {
                switch event.event {
                case "transcript":
                    if let data = parseJSON(event.data), let t = data["text"] as? String {
                        userTranscript = t
                    }
                case "response":
                    if let data = parseJSON(event.data), let t = data["text"] as? String {
                        aiText = t
                    }
                case "audio":
                    // Only play audio if we got a real transcript
                    if let data = parseJSON(event.data), let b64 = data["audio"] as? String,
                       let audioData = Data(base64Encoded: b64) {
                        player.scheduleChunk(audioData)
                    }
                default:
                    break
                }
            }
        } catch {
            log.error("Chat stream error: \(error)")
        }

        // Discard turn if transcript is empty or just noise (too short to be meaningful)
        let trimmed = userTranscript.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty {
            log.info("Empty transcript, discarding turn")
            player.stop()
            return
        }

        messages.append(ChatMessage(role: .user, text: trimmed))
        if !aiText.isEmpty {
            messages.append(ChatMessage(role: .ai, text: aiText))
        }
    }

    // MARK: - Text input

    func sendText(_ text: String) {
        guard !isProcessing, !isEnded, !text.trimmingCharacters(in: .whitespaces).isEmpty else { return }
        let trimmed = text.trimmingCharacters(in: .whitespaces)
        isProcessing = true

        Task {
            await sendTextMessage(trimmed)
            isProcessing = false
        }
    }

    private func sendTextMessage(_ text: String) async {
        guard let sessionId else { return }
        var aiText = ""

        do {
            let body = TextChatBody(text: text)
            for try await event in api.streamSSE("/sessions/\(sessionId)/chat/text", body: body) {
                switch event.event {
                case "transcript":
                    if let data = parseJSON(event.data), let t = data["text"] as? String {
                        messages.append(ChatMessage(role: .user, text: t))
                    }
                case "response":
                    if let data = parseJSON(event.data), let t = data["text"] as? String {
                        aiText = t
                    }
                case "audio":
                    if let data = parseJSON(event.data), let b64 = data["audio"] as? String,
                       let audioData = Data(base64Encoded: b64) {
                        player.scheduleChunk(audioData)
                    }
                default:
                    break
                }
            }
        } catch {
            log.error("Text chat stream error: \(error)")
        }

        if !aiText.isEmpty {
            messages.append(ChatMessage(role: .ai, text: aiText))
        }
    }

    // MARK: - End conversation

    /// Returns session ID for review navigation (conversation mode only), or nil.
    func endConversation() async -> String? {
        guard let sessionId else { return nil }
        let hasUserMessages = messages.contains { $0.role == .user }
        player.stop()
        isEnded = true

        do {
            let resp: DeleteSessionResponse = try await api.delete("/sessions/\(sessionId)")
            // Review mode: no review flow needed
            if resp.mode == SessionMode.review.rawValue {
                return nil
            }
            return hasUserMessages ? sessionId : nil
        } catch {
            log.error("Failed to end conversation: \(error)")
            return nil
        }
    }

    // MARK: - Helpers

    private func parseJSON(_ string: String) -> [String: Any]? {
        guard let data = string.data(using: .utf8) else { return nil }
        return try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    }
}

private struct CreateSessionBody: Encodable, Sendable {
    let userId: String
    let topicId: String?
    let mode: SessionMode

    enum CodingKeys: String, CodingKey {
        case userId = "user_id"
        case topicId = "topic_id"
        case mode
    }
}

private struct TextChatBody: Encodable, Sendable {
    let text: String
}
