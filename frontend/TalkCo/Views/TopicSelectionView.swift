import SwiftUI

struct TopicSelectionView: View {
    @State private var navigationPath = NavigationPath()
    @State private var needsReview = false
    private let api: any APIClientProtocol

    init(api: any APIClientProtocol = LiveAPIClient()) {
        self.api = api
    }

    private let columns = [
        GridItem(.flexible(), spacing: 16),
        GridItem(.flexible(), spacing: 16),
    ]

    var body: some View {
        NavigationStack(path: $navigationPath) {
            ScrollView {
                VStack(spacing: 16) {
                    // Needs-review banner
                    if needsReview {
                        Button {
                            navigationPath.append("__review__")
                        } label: {
                            HStack(spacing: 8) {
                                Image(systemName: "exclamationmark.triangle.fill")
                                Text("有重複出現的錯誤，建議進行弱點複習")
                                    .font(.subheadline)
                                Spacer()
                                Image(systemName: "chevron.right")
                                    .font(.caption)
                            }
                            .foregroundStyle(.white)
                            .padding()
                            .background(.orange, in: RoundedRectangle(cornerRadius: 12))
                        }
                        .buttonStyle(.plain)
                        .padding(.horizontal)
                    }

                    // Review mode entry card
                    NavigationLink(value: "__review__") {
                        ReviewModeCard()
                    }
                    .buttonStyle(.plain)
                    .padding(.horizontal)

                    // Topic cards grid
                    LazyVGrid(columns: columns, spacing: 16) {
                        ForEach(Topic.all) { topic in
                            NavigationLink(value: topic.id) {
                                TopicCard(topic: topic)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(.horizontal)
                }
                .padding(.vertical)
            }
            .navigationTitle("練習主題")
            .navigationDestination(for: String.self) { value in
                if value == "__review__" {
                    ConversationView(mode: .review, popToRoot: { navigationPath = NavigationPath() })
                } else if let topic = Topic.all.first(where: { $0.id == value }) {
                    ConversationView(topic: topic, popToRoot: { navigationPath = NavigationPath() })
                }
            }
            .task {
                await loadNeedsReview()
            }
        }
    }

    private func loadNeedsReview() async {
        do {
            let profile: UserProfile = try await api.get("/users/\(Config.userID)/profile")
            needsReview = profile.needsReview ?? false
        } catch {
            // Silently ignore — banner just won't show
        }
    }
}

private struct ReviewModeCard: View {
    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "target")
                .font(.system(size: 28))
                .foregroundStyle(.orange)

            VStack(alignment: .leading, spacing: 2) {
                Text("弱點複習")
                    .font(.headline)
                Text("針對你的弱點進行刻意練習")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }

            Spacer()

            Image(systemName: "chevron.right")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.background, in: RoundedRectangle(cornerRadius: 16))
        .shadow(color: .black.opacity(0.06), radius: 8, y: 2)
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
