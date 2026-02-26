import Foundation
import os

private let log = Logger(subsystem: "com.talkco", category: "Review")

@Observable
final class ReviewViewModel {
    var segments: [Segment] = []
    var summary: SessionSummary?
    var status: String = ""
    var isLoading = true
    var isEnding = false
    var isCompleted = false

    private let sessionId: String
    private var pollTask: Task<Void, Never>?

    init(sessionId: String) {
        self.sessionId = sessionId
    }

    // MARK: - Load review (poll until AI marks appear)

    func loadReview() {
        pollTask?.cancel()
        isLoading = true
        pollTask = Task {
            var errorCount = 0

            while !Task.isCancelled {
                do {
                    let response: ReviewResponse = try await APIClient.get("/sessions/\(sessionId)/review")
                    errorCount = 0
                    segments = response.segments
                    status = response.status
                    summary = response.summary

                    // Stop polling when: marks arrived, no segments to review, or backend moved past reviewing
                    let hasMarks = response.segments.contains { !$0.aiMarks.isEmpty }
                    if hasMarks || response.segments.isEmpty || response.status != "reviewing" {
                        isLoading = false
                        return
                    }
                } catch {
                    errorCount += 1
                    log.error("Failed to load review (attempt \(errorCount)): \(error)")
                    if errorCount >= 3 {
                        log.error("Giving up polling after \(errorCount) consecutive errors")
                        isLoading = false
                        return
                    }
                }

                try? await Task.sleep(for: .seconds(2))
            }
        }
    }

    // MARK: - Submit correction

    func submitCorrection(segmentId: Int, userMessage: String) async {
        let body = CorrectionRequest(segmentId: segmentId, userMessage: userMessage)
        do {
            let correction: Correction = try await APIClient.post(
                "/sessions/\(sessionId)/corrections", body: body
            )
            if let idx = segments.firstIndex(where: { $0.id == segmentId }) {
                segments[idx].corrections.append(correction)
            }
        } catch {
            log.error("Failed to submit correction: \(error)")
        }
    }

    // MARK: - End review

    func endReview() {
        isEnding = true
        pollTask?.cancel()
        pollTask = Task {
            do {
                let _: EndSessionResponse = try await APIClient.post(
                    "/sessions/\(sessionId)/end", body: EmptyBody()
                )
            } catch {
                log.error("Failed to end session: \(error)")
                isEnding = false
                return
            }

            // Poll until completed with summary
            var errorCount = 0
            while !Task.isCancelled {
                do {
                    let response: ReviewResponse = try await APIClient.get("/sessions/\(sessionId)/review")
                    errorCount = 0
                    segments = response.segments
                    status = response.status
                    summary = response.summary

                    if response.status == "completed" {
                        isEnding = false
                        isCompleted = true
                        return
                    }
                } catch {
                    errorCount += 1
                    log.error("Failed to poll review (attempt \(errorCount)): \(error)")
                    if errorCount >= 3 {
                        isEnding = false
                        return
                    }
                }

                try? await Task.sleep(for: .seconds(2))
            }
        }
    }

    func cancel() {
        pollTask?.cancel()
    }
}

private struct EmptyBody: Encodable {}
