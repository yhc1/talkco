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
                            Text("評估中...")
                        } else {
                            Text("重新評估程度")
                        }
                        Spacer()
                    }
                }
                .disabled(vm.isEvaluating)
            }

            // Progress summary
            if !profile.profileData.progressNotes.isEmpty {
                Section("學習總覽") {
                    Text(profile.profileData.progressNotes)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
            }

            // Weak points
            let wp = profile.profileData.weakPoints
            if !wp.grammar.isEmpty || !wp.naturalness.isEmpty || !wp.sentenceStructure.isEmpty {
                Section {
                    VStack(alignment: .leading, spacing: 16) {
                        Text("需要加強")
                            .font(.headline)
                        weakPointSection("文法", patterns: wp.grammar, color: .red)
                        weakPointSection("自然度", patterns: wp.naturalness, color: .orange)
                        weakPointSection("句構", patterns: wp.sentenceStructure, color: .purple)
                    }
                }
            }

        }
    }

    @ViewBuilder
    private func weakPointSection(_ label: String, patterns: [WeakPointPattern], color: Color) -> some View {
        if !patterns.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Text(label)
                    .font(.subheadline)
                    .fontWeight(.medium)
                    .foregroundStyle(color)
                ForEach(patterns) { pattern in
                    DisclosureGroup {
                        VStack(alignment: .leading, spacing: 6) {
                            ForEach(Array(pattern.examples.enumerated()), id: \.offset) { _, example in
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(example.wrong)
                                        .font(.caption)
                                        .strikethrough()
                                        .foregroundStyle(.red.opacity(0.7))
                                    Text(example.correct)
                                        .font(.caption)
                                        .foregroundStyle(.green)
                                }
                                .padding(.vertical, 2)
                            }
                        }
                        .padding(.leading, 4)
                    } label: {
                        Text(pattern.pattern)
                            .font(.caption)
                            .foregroundStyle(.primary)
                    }
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
