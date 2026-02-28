import Foundation

struct Topic: Identifiable, Sendable, Codable {
    let id: String
    let labelEn: String
    let labelZh: String
    let promptHint: String
    let icon: String  // SF Symbol name

    enum CodingKeys: String, CodingKey {
        case id
        case labelEn = "label_en"
        case labelZh = "label_zh"
        case promptHint = "prompt_hint"
        case icon
    }

    static let all: [Topic] = {
        guard let url = Bundle.main.url(forResource: "topics", withExtension: "json") else {
            print("[Topic] topics.json not found in bundle")
            return []
        }
        do {
            let data = try Data(contentsOf: url)
            return try JSONDecoder().decode([Topic].self, from: data)
        } catch {
            print("[Topic] Failed to decode topics.json: \(error)")
            return []
        }
    }()
}
