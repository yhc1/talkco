import SwiftUI

struct ProfileView: View {
    @State private var vm: ProfileViewModel

    init(api: any APIClientProtocol = LiveAPIClient()) {
        _vm = State(initialValue: ProfileViewModel(api: api))
    }

    var body: some View {
        NavigationStack {
            Group {
                if vm.isLoading && vm.profile == nil {
                    ProgressView("載入中…")
                } else if let profile = vm.profile {
                    profileContent(profile)
                } else {
                    ContentUnavailableView("無法載入", systemImage: "person.crop.circle.badge.exclamationmark")
                }
            }
            .navigationTitle("我的")
        }
        .task { await vm.loadProfile() }
    }

    @ViewBuilder
    private func profileContent(_ profile: UserProfile) -> some View {
        List {
            // CEFR Level
            Section {
                HStack {
                    Spacer()
                    VStack(spacing: 4) {
                        Text(profile.level)
                            .font(.system(size: 48, weight: .bold, design: .rounded))
                        Text("CEFR 等級")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                }
                .padding(.vertical, 8)
            }

            // Weak points
            Section {
                VStack(alignment: .leading, spacing: 16) {
                    Text("需要加強")
                        .font(.headline)
                    weakPointRow("文法", items: profile.profileData.weakPoints.grammar, color: .red)
                    weakPointRow("自然度", items: profile.profileData.weakPoints.naturalness, color: .orange)
                    weakPointRow("詞彙", items: profile.profileData.weakPoints.vocabulary, color: .blue)
                    weakPointRow("句構", items: profile.profileData.weakPoints.sentenceStructure, color: .purple)
                }
            }

            // Stats
            Section("練習統計") {
                LabeledContent("練習次數", value: "\(profile.profileData.sessionCount)")
            }

            // Learned expressions
            if !profile.profileData.learnedExpressions.isEmpty {
                Section("學過的表達") {
                    ForEach(profile.profileData.learnedExpressions, id: \.self) { expr in
                        Text(expr)
                            .font(.subheadline)
                    }
                }
            }
        }
    }

    @ViewBuilder
    private func weakPointRow(_ label: String, items: [String], color: Color) -> some View {
        if !items.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Text(label)
                    .font(.subheadline)
                    .fontWeight(.medium)
                    .foregroundStyle(color)
                ForEach(items, id: \.self) { item in
                    Text(item)
                        .font(.caption)
                        .foregroundStyle(.primary)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(color.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
                        .overlay(alignment: .leading) {
                            RoundedRectangle(cornerRadius: 8)
                                .fill(color)
                                .frame(width: 3)
                        }
                }
            }
            .padding(.vertical, 2)
        }
    }
}
