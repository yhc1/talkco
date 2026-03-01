import Foundation
import SwiftUI

// MARK: - JSON Loading

private struct ConstantsJSON: Codable {
    let sessionModes: [String]
    let sessionStatuses: [String]
    let issueDimensions: [String: DimensionInfo]

    enum CodingKeys: String, CodingKey {
        case sessionModes = "session_modes"
        case sessionStatuses = "session_statuses"
        case issueDimensions = "issue_dimensions"
    }

    struct DimensionInfo: Codable {
        let en: String
        let zh: String
        let color: String
    }
}

private let _constants: ConstantsJSON = {
    guard let url = Bundle.main.url(forResource: "constants", withExtension: "json") else {
        fatalError("[Constants] constants.json not found in bundle")
    }
    do {
        let data = try Data(contentsOf: url)
        return try JSONDecoder().decode(ConstantsJSON.self, from: data)
    } catch {
        fatalError("[Constants] Failed to decode constants.json: \(error)")
    }
}()

// MARK: - Session Mode

enum SessionMode: String, Codable, CaseIterable {
    case conversation
    case review
}

// MARK: - Session Status

enum SessionStatus: String, Codable, CaseIterable {
    case active
    case reviewing
    case completing
    case completed
    case ended
}

// MARK: - Issue Dimension

enum IssueDimension: String, Codable, CaseIterable {
    case grammar
    case naturalness
    case sentenceStructure = "sentence_structure"

    var displayName: String {
        guard let info = _constants.issueDimensions[rawValue] else { return rawValue }
        return info.zh
    }

    var color: Color {
        guard let info = _constants.issueDimensions[rawValue] else { return .gray }
        switch info.color {
        case "red": return .red
        case "orange": return .orange
        case "purple": return .purple
        default: return .gray
        }
    }
}
