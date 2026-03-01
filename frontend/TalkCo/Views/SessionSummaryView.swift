import SwiftUI

struct SessionSummaryView: View {
    let summary: SessionSummary
    let onDismiss: () -> Void

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                // Overall
                VStack(alignment: .leading, spacing: 8) {
                    Label("整體評語", systemImage: "text.quote")
                        .font(.headline)
                    Text(summary.overall)
                        .font(.body)
                        .foregroundStyle(.secondary)
                }

                // Strengths
                VStack(alignment: .leading, spacing: 8) {
                    Label("表現良好", systemImage: "hand.thumbsup")
                        .font(.headline)
                    ForEach(summary.strengths, id: \.self) { strength in
                        HStack(alignment: .top, spacing: 8) {
                            Image(systemName: "checkmark.circle.fill")
                                .foregroundStyle(.green)
                                .font(.subheadline)
                            Text(strength)
                                .font(.subheadline)
                        }
                    }
                }

                // Weaknesses
                VStack(alignment: .leading, spacing: 8) {
                    Label("需要加強", systemImage: "exclamationmark.triangle")
                        .font(.headline)
                    ForEach(Array(summary.weaknesses.keys.sorted()), id: \.self) { key in
                        if let value = summary.weaknesses[key], let text = value {
                            HStack(alignment: .top, spacing: 8) {
                                Circle()
                                    .fill(weaknessColor(for: key))
                                    .frame(width: 8, height: 8)
                                    .padding(.top, 6)
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(weaknessDisplayName(for: key))
                                        .font(.subheadline)
                                        .fontWeight(.medium)
                                    Text(text)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                }
            }
            .padding()
        }
        .navigationTitle("學習總結")
        .navigationBarTitleDisplayMode(.inline)
        .navigationBarBackButtonHidden(true)
        .toolbar {
            ToolbarItem(placement: .bottomBar) {
                Button {
                    onDismiss()
                } label: {
                    Text("完成")
                        .fontWeight(.semibold)
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
            }
        }
    }

    private func weaknessColor(for key: String) -> Color {
        guard let dim = IssueDimension(rawValue: key) else { return .gray }
        return dim.color
    }

    private func weaknessDisplayName(for key: String) -> String {
        guard let dim = IssueDimension(rawValue: key) else { return key }
        return dim.displayName
    }
}
