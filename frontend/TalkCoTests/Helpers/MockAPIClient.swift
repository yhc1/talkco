import Foundation
@testable import TalkCo

final class MockAPIClient: APIClientProtocol, @unchecked Sendable {
    // Closure-based stubs — set these in tests to control behavior.

    var getHandler: ((String) async throws -> Any)?
    var postHandler: ((String, Any) async throws -> Any)?
    var deleteHandler: ((String) async throws -> Any)?
    var streamSSEHandler: ((String) -> AsyncThrowingStream<SSEvent, Error>)?
    var streamSSEBodyHandler: ((String, Any) -> AsyncThrowingStream<SSEvent, Error>)?
    var streamMultipartHandler: ((String, Data, String, String, String) -> AsyncThrowingStream<SSEvent, Error>)?

    func get<T: Decodable>(_ path: String) async throws -> T {
        guard let handler = getHandler else { fatalError("MockAPIClient.get not stubbed for \(path)") }
        return try await handler(path) as! T
    }

    func post<T: Decodable>(_ path: String, body: some Encodable & Sendable) async throws -> T {
        guard let handler = postHandler else { fatalError("MockAPIClient.post not stubbed for \(path)") }
        return try await handler(path, body) as! T
    }

    func delete<T: Decodable>(_ path: String) async throws -> T {
        guard let handler = deleteHandler else { fatalError("MockAPIClient.delete not stubbed for \(path)") }
        return try await handler(path) as! T
    }

    func streamSSE(_ path: String) -> AsyncThrowingStream<SSEvent, Error> {
        guard let handler = streamSSEHandler else { fatalError("MockAPIClient.streamSSE not stubbed for \(path)") }
        return handler(path)
    }

    func streamSSE(_ path: String, body: some Encodable & Sendable) -> AsyncThrowingStream<SSEvent, Error> {
        guard let handler = streamSSEBodyHandler else { fatalError("MockAPIClient.streamSSE(body:) not stubbed for \(path)") }
        return handler(path, body)
    }

    func streamMultipart(
        _ path: String,
        fileData: Data,
        fileName: String,
        fieldName: String,
        mimeType: String
    ) -> AsyncThrowingStream<SSEvent, Error> {
        guard let handler = streamMultipartHandler else { fatalError("MockAPIClient.streamMultipart not stubbed for \(path)") }
        return handler(path, fileData, fileName, fieldName, mimeType)
    }
}
