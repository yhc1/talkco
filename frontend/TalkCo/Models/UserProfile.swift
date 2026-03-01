import Foundation

struct UserProfile: Codable {
    let userId: String
    let level: String?
    let profileData: ProfileData
    let updatedAt: String
    let needsReview: Bool?

    enum CodingKeys: String, CodingKey {
        case userId = "user_id"
        case level
        case profileData = "profile_data"
        case updatedAt = "updated_at"
        case needsReview = "needs_review"
    }
}

struct ProfileData: Codable {
    let personalFacts: [String]
    let weakPoints: WeakPoints
    let commonErrors: [String]
    let progressNotes: String

    enum CodingKeys: String, CodingKey {
        case personalFacts = "personal_facts"
        case weakPoints = "weak_points"
        case commonErrors = "common_errors"
        case progressNotes = "progress_notes"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        personalFacts = (try? container.decode([String].self, forKey: .personalFacts)) ?? []
        commonErrors = (try? container.decode([String].self, forKey: .commonErrors)) ?? []
        progressNotes = (try? container.decode(String.self, forKey: .progressNotes)) ?? ""

        // weak_points can be old format (array or dict of strings) or new format (dict of pattern objects)
        if let wp = try? container.decode(WeakPoints.self, forKey: .weakPoints) {
            weakPoints = wp
        } else {
            weakPoints = WeakPoints(grammar: [], naturalness: [], sentenceStructure: [])
        }
    }
}

struct WeakPointPattern: Codable, Identifiable {
    let pattern: String
    let examples: [WeakPointExample]
    var id: String { pattern }
}

struct WeakPointExample: Codable {
    let wrong: String
    let correct: String
}

struct WeakPoints: Codable {
    let grammar: [WeakPointPattern]
    let naturalness: [WeakPointPattern]
    let sentenceStructure: [WeakPointPattern]

    enum CodingKeys: String, CodingKey {
        case grammar
        case naturalness
        case sentenceStructure = "sentence_structure"
    }

    init(grammar: [WeakPointPattern] = [], naturalness: [WeakPointPattern] = [],
         sentenceStructure: [WeakPointPattern] = []) {
        self.grammar = grammar
        self.naturalness = naturalness
        self.sentenceStructure = sentenceStructure
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        grammar = Self.decodePatterns(from: container, forKey: .grammar)
        naturalness = Self.decodePatterns(from: container, forKey: .naturalness)
        sentenceStructure = Self.decodePatterns(from: container, forKey: .sentenceStructure)
    }

    /// Decode a dimension as [WeakPointPattern]. Ignores old format (plain strings) entirely.
    private static func decodePatterns(from container: KeyedDecodingContainer<CodingKeys>,
                                       forKey key: CodingKeys) -> [WeakPointPattern] {
        if let patterns = try? container.decode([WeakPointPattern].self, forKey: key) {
            return patterns
        }
        return []
    }
}
