import XCTest
@testable import TalkCo

final class APIClientHelpersTests: XCTestCase {

    // MARK: - validateResponse

    func testValidateResponse200() throws {
        let url = URL(string: "https://example.com")!
        let response = HTTPURLResponse(url: url, statusCode: 200, httpVersion: nil, headerFields: nil)!
        XCTAssertNoThrow(try APIClient.validateResponse(response))
    }

    func testValidateResponse201() throws {
        let url = URL(string: "https://example.com")!
        let response = HTTPURLResponse(url: url, statusCode: 201, httpVersion: nil, headerFields: nil)!
        XCTAssertNoThrow(try APIClient.validateResponse(response))
    }

    func testValidateResponse299() throws {
        let url = URL(string: "https://example.com")!
        let response = HTTPURLResponse(url: url, statusCode: 299, httpVersion: nil, headerFields: nil)!
        XCTAssertNoThrow(try APIClient.validateResponse(response))
    }

    func testValidateResponse404ThrowsHTTPError() {
        let url = URL(string: "https://example.com")!
        let response = HTTPURLResponse(url: url, statusCode: 404, httpVersion: nil, headerFields: nil)!
        XCTAssertThrowsError(try APIClient.validateResponse(response)) { error in
            guard case APIError.httpError(let code) = error else {
                XCTFail("Expected APIError.httpError, got \(error)")
                return
            }
            XCTAssertEqual(code, 404)
        }
    }

    func testValidateResponse500ThrowsHTTPError() {
        let url = URL(string: "https://example.com")!
        let response = HTTPURLResponse(url: url, statusCode: 500, httpVersion: nil, headerFields: nil)!
        XCTAssertThrowsError(try APIClient.validateResponse(response)) { error in
            guard case APIError.httpError(let code) = error else {
                XCTFail("Expected APIError.httpError, got \(error)")
                return
            }
            XCTAssertEqual(code, 500)
        }
    }

    func testValidateResponseNonHTTPThrowsInvalidResponse() {
        let response = URLResponse(url: URL(string: "https://example.com")!, mimeType: nil, expectedContentLength: 0, textEncodingName: nil)
        XCTAssertThrowsError(try APIClient.validateResponse(response)) { error in
            guard case APIError.invalidResponse = error else {
                XCTFail("Expected APIError.invalidResponse, got \(error)")
                return
            }
        }
    }

    // MARK: - buildMultipartBody

    func testBuildMultipartBodyStructure() {
        let fileData = "test content".data(using: .utf8)!
        let boundary = "test-boundary-123"

        let body = APIClient.buildMultipartBody(
            boundary: boundary,
            fieldName: "audio",
            fileName: "audio.wav",
            mimeType: "audio/wav",
            fileData: fileData
        )

        let bodyString = String(data: body, encoding: .utf8)!

        XCTAssertTrue(bodyString.contains("--test-boundary-123\r\n"))
        XCTAssertTrue(bodyString.contains("Content-Disposition: form-data; name=\"audio\"; filename=\"audio.wav\""))
        XCTAssertTrue(bodyString.contains("Content-Type: audio/wav"))
        XCTAssertTrue(bodyString.contains("test content"))
        XCTAssertTrue(bodyString.hasSuffix("\r\n--test-boundary-123--\r\n"))
    }

    func testBuildMultipartBodyContainsFileData() {
        let fileData = Data([0x00, 0x01, 0x02, 0xFF])
        let body = APIClient.buildMultipartBody(
            boundary: "b",
            fieldName: "file",
            fileName: "data.bin",
            mimeType: "application/octet-stream",
            fileData: fileData
        )

        // The body should contain the raw file data bytes
        XCTAssertTrue(body.count > fileData.count)
        // Find the fileData within the body
        let range = body.range(of: fileData)
        XCTAssertNotNil(range, "Body should contain the file data")
    }

    // MARK: - APIError descriptions

    func testAPIErrorInvalidResponseDescription() {
        let error = APIError.invalidResponse
        XCTAssertEqual(error.errorDescription, "Invalid server response")
    }

    func testAPIErrorHTTPErrorDescription() {
        let error = APIError.httpError(statusCode: 503)
        XCTAssertEqual(error.errorDescription, "HTTP error 503")
    }
}
