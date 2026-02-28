import Foundation

struct UserProfile: Codable {
    let userId: String
    let level: String
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
    let learnedExpressions: [String]
    let weakPoints: WeakPoints
    let progressNotes: String
    let commonErrors: [String]

    enum CodingKeys: String, CodingKey {
        case learnedExpressions = "learned_expressions"
        case weakPoints = "weak_points"
        case progressNotes = "progress_notes"
        case commonErrors = "common_errors"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        learnedExpressions = (try? container.decode([String].self, forKey: .learnedExpressions)) ?? []
        progressNotes = (try? container.decode(String.self, forKey: .progressNotes)) ?? ""
        commonErrors = (try? container.decode([String].self, forKey: .commonErrors)) ?? []

        // weak_points can be old format (array or dict of strings) or new format (dict of pattern objects)
        if let wp = try? container.decode(WeakPoints.self, forKey: .weakPoints) {
            weakPoints = wp
        } else {
            weakPoints = WeakPoints(grammar: [], naturalness: [], vocabulary: [], sentenceStructure: [])
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
    let vocabulary: [WeakPointPattern]
    let sentenceStructure: [WeakPointPattern]

    enum CodingKeys: String, CodingKey {
        case grammar
        case naturalness
        case vocabulary
        case sentenceStructure = "sentence_structure"
    }

    init(grammar: [WeakPointPattern] = [], naturalness: [WeakPointPattern] = [],
         vocabulary: [WeakPointPattern] = [], sentenceStructure: [WeakPointPattern] = []) {
        self.grammar = grammar
        self.naturalness = naturalness
        self.vocabulary = vocabulary
        self.sentenceStructure = sentenceStructure
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        grammar = Self.decodePatterns(from: container, forKey: .grammar)
        naturalness = Self.decodePatterns(from: container, forKey: .naturalness)
        vocabulary = Self.decodePatterns(from: container, forKey: .vocabulary)
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
