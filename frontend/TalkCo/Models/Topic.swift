import Foundation

struct Topic: Identifiable, Sendable {
    let id: String
    let labelEn: String
    let labelZh: String
    let promptHint: String
    let icon: String  // SF Symbol name

    static let all: [Topic] = [
        Topic(id: "daily_life", labelEn: "Daily Life", labelZh: "日常生活",
              promptHint: "Everyday routines, hobbies, weekend plans, food, weather",
              icon: "sun.max"),
        Topic(id: "travel", labelEn: "Travel", labelZh: "旅遊",
              promptHint: "Travel experiences, planning trips, airports, hotels, sightseeing",
              icon: "airplane"),
        Topic(id: "workplace", labelEn: "Workplace", labelZh: "職場",
              promptHint: "Office conversations, meetings, emails, colleagues, career",
              icon: "briefcase"),
        Topic(id: "food_dining", labelEn: "Food & Dining", labelZh: "美食",
              promptHint: "Ordering at restaurants, cooking, recipes, food culture",
              icon: "fork.knife"),
        Topic(id: "entertainment", labelEn: "Entertainment", labelZh: "娛樂",
              promptHint: "Movies, music, TV shows, games, social media",
              icon: "film"),
        Topic(id: "current_events", labelEn: "Current Events", labelZh: "時事",
              promptHint: "News, trends, technology, social topics",
              icon: "newspaper"),
    ]
}
