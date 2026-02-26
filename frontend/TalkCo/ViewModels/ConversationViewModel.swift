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

    private let topic: Topic
    private var sessionId: String?
    private let recorder = AudioRecorder()
    private let player = AudioPlayer()

    init(topic: Topic) {
        self.topic = topic
    }

    // MARK: - Session lifecycle

    func startSession() async {
        isConnecting = true
        do {
            let body = CreateSessionBody(userId: Config.userID, topicId: topic.id)
            let resp: CreateSessionResponse = try await APIClient.post("/sessions", body: body)
            sessionId = resp.sessionId
            log.info("Session created: \(resp.sessionId)")

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
            for try await event in APIClient.streamSSE("/sessions/\(sessionId)/start") {
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
        guard !isProcessing, !isEnded else { return }
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
        isProcessing = true

        Task {
            await sendAudio(wavData)
            isProcessing = false
        }
    }

    private func sendAudio(_ wavData: Data) async {
        guard let sessionId else { return }
        var userText = ""
        var aiText = ""

        do {
            for try await event in APIClient.streamMultipart(
                "/sessions/\(sessionId)/chat",
                fileData: wavData,
                fileName: "audio.wav",
                fieldName: "audio",
                mimeType: "audio/wav"
            ) {
                switch event.event {
                case "transcript":
                    if let data = parseJSON(event.data), let t = data["text"] as? String {
                        userText = t
                        await MainActor.run {
                            messages.append(ChatMessage(role: .user, text: t))
                        }
                    }
                case "response":
                    if let data = parseJSON(event.data), let t = data["text"] as? String {
                        aiText = t
                        await MainActor.run {
                            messages.append(ChatMessage(role: .ai, text: t))
                        }
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
            log.error("Chat stream error: \(error)")
        }
    }

    // MARK: - End conversation

    func endConversation() async -> String? {
        guard let sessionId else { return nil }
        player.stop()
        isEnded = true

        do {
            let _: DeleteSessionResponse = try await APIClient.delete("/sessions/\(sessionId)")
            return sessionId
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

private struct CreateSessionBody: Encodable {
    let userId: String
    let topicId: String

    enum CodingKeys: String, CodingKey {
        case userId = "user_id"
        case topicId = "topic_id"
    }
}
