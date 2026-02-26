import Foundation

struct ChatMessage: Identifiable {
    let id = UUID()
    let role: Role
    var text: String

    enum Role {
        case user
        case ai
    }
}
