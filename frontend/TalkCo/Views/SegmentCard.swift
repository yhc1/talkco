import SwiftUI

struct SegmentCard: View {
    let segment: Segment
    let isSelected: Bool
    let onTap: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // User text with issue badges
            HStack(alignment: .top) {
                Text(segment.userText)
                    .font(.body)
                Spacer()
            }

            if !segment.aiMarks.isEmpty {
                issueBadges
            }

            // Expanded detail
            if isSelected {
                expandedContent
            }

            // Corrections
            if !segment.corrections.isEmpty {
                correctionsSection
            }
        }
        .padding()
        .background(Color(.systemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .shadow(color: .black.opacity(0.05), radius: 4, y: 1)
        .onTapGesture { onTap() }
    }

    @ViewBuilder
    private var issueBadges: some View {
        let allTypes = segment.aiMarks.flatMap(\.issueTypes)
        let unique = Array(Set(allTypes)).sorted()
        FlowLayout(spacing: 6) {
            ForEach(unique, id: \.self) { type in
                Text(displayName(for: type))
                    .font(.caption2)
                    .fontWeight(.medium)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 3)
                    .background(color(for: type).opacity(0.15))
                    .foregroundStyle(color(for: type))
                    .clipShape(Capsule())
            }
        }
    }

    @ViewBuilder
    private var expandedContent: some View {
        VStack(alignment: .leading, spacing: 10) {
            Divider()

            // AI response
            Label {
                Text(segment.aiText)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            } icon: {
                Image(systemName: "bubble.left")
                    .foregroundStyle(.secondary)
            }

            // AI marks detail
            ForEach(segment.aiMarks) { mark in
                VStack(alignment: .leading, spacing: 4) {
                    Text("✦ \(mark.original)")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .strikethrough()

                    Text(mark.suggestion)
                        .font(.subheadline)
                        .fontWeight(.medium)
                        .foregroundStyle(.primary)

                    Text(mark.explanation)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color(.systemGray6))
                .clipShape(RoundedRectangle(cornerRadius: 8))
            }
        }
    }

    @ViewBuilder
    private var correctionsSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            Divider()
            ForEach(segment.corrections) { correction in
                VStack(alignment: .leading, spacing: 4) {
                    Text(correction.userMessage)
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    Text(correction.correction)
                        .font(.subheadline)
                        .fontWeight(.medium)

                    Text(correction.explanation)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .padding(8)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.accentColor.opacity(0.08))
                .clipShape(RoundedRectangle(cornerRadius: 8))
            }
        }
    }

    private func color(for issueType: String) -> Color {
        guard let dim = IssueDimension(rawValue: issueType) else { return .gray }
        return dim.color
    }

    private func displayName(for issueType: String) -> String {
        guard let dim = IssueDimension(rawValue: issueType) else { return issueType }
        return dim.displayName
    }
}

// MARK: - FlowLayout for badges

struct FlowLayout: Layout {
    var spacing: CGFloat = 6

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let result = arrange(proposal: proposal, subviews: subviews)
        return result.size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let result = arrange(proposal: proposal, subviews: subviews)
        for (index, position) in result.positions.enumerated() {
            subviews[index].place(at: CGPoint(x: bounds.minX + position.x, y: bounds.minY + position.y),
                                  proposal: .unspecified)
        }
    }

    private func arrange(proposal: ProposedViewSize, subviews: Subviews) -> (size: CGSize, positions: [CGPoint]) {
        let maxWidth = proposal.width ?? .infinity
        var positions: [CGPoint] = []
        var x: CGFloat = 0
        var y: CGFloat = 0
        var rowHeight: CGFloat = 0
        var maxX: CGFloat = 0

        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x + size.width > maxWidth, x > 0 {
                x = 0
                y += rowHeight + spacing
                rowHeight = 0
            }
            positions.append(CGPoint(x: x, y: y))
            rowHeight = max(rowHeight, size.height)
            x += size.width + spacing
            maxX = max(maxX, x)
        }

        return (CGSize(width: maxX, height: y + rowHeight), positions)
    }
}
