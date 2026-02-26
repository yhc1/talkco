import Foundation

/// Represents a single Server-Sent Event.
struct SSEvent {
    let event: String
    let data: String
}

/// Networking layer for the TalkCo backend.
/// Supports JSON requests, SSE streaming, and multipart file upload.
enum APIClient {

    // MARK: - JSON requests

    static func get<T: Decodable>(_ path: String) async throws -> T {
        let url = Config.baseURL.appendingPathComponent(path)
        let (data, response) = try await URLSession.shared.data(from: url)
        try validateResponse(response)
        return try JSONDecoder().decode(T.self, from: data)
    }

    static func post<T: Decodable>(_ path: String, body: some Encodable) async throws -> T {
        let url = Config.baseURL.appendingPathComponent(path)
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(body)
        let (data, response) = try await URLSession.shared.data(for: request)
        try validateResponse(response)
        return try JSONDecoder().decode(T.self, from: data)
    }

    static func delete<T: Decodable>(_ path: String) async throws -> T {
        let url = Config.baseURL.appendingPathComponent(path)
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        let (data, response) = try await URLSession.shared.data(for: request)
        try validateResponse(response)
        return try JSONDecoder().decode(T.self, from: data)
    }

    // MARK: - SSE streaming

    /// Streams Server-Sent Events from a POST endpoint (no body).
    static func streamSSE(_ path: String) -> AsyncThrowingStream<SSEvent, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    let url = Config.baseURL.appendingPathComponent(path)
                    var request = URLRequest(url: url)
                    request.httpMethod = "POST"
                    request.timeoutInterval = 60
                    let (bytes, response) = try await URLSession.shared.bytes(for: request)
                    try validateResponse(response)
                    try await parseSSEStream(bytes, continuation: continuation)
                } catch {
                    if !Task.isCancelled {
                        continuation.finish(throwing: error)
                    }
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    /// Streams Server-Sent Events from a multipart POST (file upload).
    static func streamMultipart(
        _ path: String,
        fileData: Data,
        fileName: String,
        fieldName: String,
        mimeType: String
    ) -> AsyncThrowingStream<SSEvent, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    let url = Config.baseURL.appendingPathComponent(path)
                    let boundary = UUID().uuidString
                    var request = URLRequest(url: url)
                    request.httpMethod = "POST"
                    request.setValue("multipart/form-data; boundary=\(boundary)",
                                    forHTTPHeaderField: "Content-Type")
                    request.timeoutInterval = 60
                    request.httpBody = buildMultipartBody(
                        boundary: boundary,
                        fieldName: fieldName,
                        fileName: fileName,
                        mimeType: mimeType,
                        fileData: fileData
                    )
                    let (bytes, response) = try await URLSession.shared.bytes(for: request)
                    try validateResponse(response)
                    try await parseSSEStream(bytes, continuation: continuation)
                } catch {
                    if !Task.isCancelled {
                        continuation.finish(throwing: error)
                    }
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    // MARK: - Helpers

    private static func validateResponse(_ response: URLResponse) throws {
        guard let http = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }
        guard (200..<300).contains(http.statusCode) else {
            throw APIError.httpError(statusCode: http.statusCode)
        }
    }

    private static func parseSSEStream(
        _ bytes: URLSession.AsyncBytes,
        continuation: AsyncThrowingStream<SSEvent, Error>.Continuation
    ) async throws {
        var currentEvent: String?

        for try await line in bytes.lines {
            if Task.isCancelled { break }

            if line.hasPrefix("event: ") {
                currentEvent = String(line.dropFirst(7))
            } else if line.hasPrefix("data: "), let event = currentEvent {
                let data = String(line.dropFirst(6))
                continuation.yield(SSEvent(event: event, data: data))
                currentEvent = nil
            }
        }
        continuation.finish()
    }

    private static func buildMultipartBody(
        boundary: String,
        fieldName: String,
        fileName: String,
        mimeType: String,
        fileData: Data
    ) -> Data {
        var body = Data()
        let crlf = "\r\n"
        body.append("--\(boundary)\(crlf)".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"\(fieldName)\"; filename=\"\(fileName)\"\(crlf)".data(using: .utf8)!)
        body.append("Content-Type: \(mimeType)\(crlf)\(crlf)".data(using: .utf8)!)
        body.append(fileData)
        body.append("\(crlf)--\(boundary)--\(crlf)".data(using: .utf8)!)
        return body
    }
}

enum APIError: LocalizedError {
    case invalidResponse
    case httpError(statusCode: Int)

    var errorDescription: String? {
        switch self {
        case .invalidResponse: return "Invalid server response"
        case .httpError(let code): return "HTTP error \(code)"
        }
    }
}
