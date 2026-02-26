import SwiftUI

struct TopicSelectionView: View {
    @State private var navigationPath = NavigationPath()

    private let columns = [
        GridItem(.flexible(), spacing: 16),
        GridItem(.flexible(), spacing: 16),
    ]

    var body: some View {
        NavigationStack(path: $navigationPath) {
            ScrollView {
                LazyVGrid(columns: columns, spacing: 16) {
                    ForEach(Topic.all) { topic in
                        NavigationLink(value: topic.id) {
                            TopicCard(topic: topic)
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding()
            }
            .navigationTitle("練習主題")
            .navigationDestination(for: String.self) { topicId in
                if let topic = Topic.all.first(where: { $0.id == topicId }) {
                    ConversationView(topic: topic, popToRoot: { navigationPath = NavigationPath() })
                }
            }
        }
    }
}

private struct TopicCard: View {
    let topic: Topic

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: topic.icon)
                .font(.system(size: 32))
                .foregroundStyle(.tint)

            Text(topic.labelZh)
                .font(.headline)

            Text(topic.labelEn)
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 24)
        .background(.background, in: RoundedRectangle(cornerRadius: 16))
        .shadow(color: .black.opacity(0.06), radius: 8, y: 2)
    }
}
