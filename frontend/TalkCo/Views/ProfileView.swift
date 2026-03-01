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
                        Text(profile.level ?? "--")
                            .font(.system(size: 48, weight: .bold, design: .rounded))
                        Text(profile.level != nil ? "CEFR 等級" : "尚未評估")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                }
                .padding(.vertical, 8)

                Button {
                    Task { await vm.evaluateLevel() }
                } label: {
                    HStack {
                        Spacer()
                        if vm.isEvaluating {
                            ProgressView()
                                .controlSize(.small)
                            Text("更新中...")
                        } else {
                            Text("更新學習報告")
                        }
                        Spacer()
                    }
                }
                .disabled(vm.isEvaluating)
            }

            // Progress notes
            if !profile.profileData.progressNotes.isEmpty {
                Section {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("學習總覽")
                            .font(.headline)
                        Text(profile.profileData.progressNotes)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                }
            }

            // Quick review
            if !profile.profileData.quickReview.isEmpty {
                Section {
                    VStack(alignment: .leading, spacing: 12) {
                        Text("快速複習")
                            .font(.headline)
                        ForEach(profile.profileData.quickReview) { item in
                            VStack(alignment: .leading, spacing: 2) {
                                Text(item.chinese)
                                    .font(.subheadline)
                                    .foregroundStyle(.secondary)
                                Text(item.english)
                                    .font(.subheadline)
                            }
                        }
                    }
                }
            }

        }
    }
}
