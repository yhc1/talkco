import SwiftUI

struct ReviewView: View {
    let sessionId: String
    let onComplete: () -> Void

    @State private var vm: ReviewViewModel
    @State private var selectedSegmentId: Int?
    @State private var correctionSegmentId: Int?
    @State private var correctionText = ""
    @State private var isSending = false
    @State private var showSummary = false

    init(sessionId: String, onComplete: @escaping () -> Void) {
        self.sessionId = sessionId
        self.onComplete = onComplete
        _vm = State(initialValue: ReviewViewModel(sessionId: sessionId))
    }

    var body: some View {
        VStack(spacing: 0) {
            if vm.isLoading {
                loadingView
            } else if vm.segments.isEmpty {
                emptyView
            } else {
                segmentList
            }

            Divider()
            bottomBar
        }
        .navigationTitle("學習回顧")
        .navigationBarTitleDisplayMode(.inline)
        .navigationBarBackButtonHidden(true)
        .navigationDestination(isPresented: $showSummary) {
            if let summary = vm.summary {
                SessionSummaryView(summary: summary, onDismiss: onComplete)
            }
        }
        .onChange(of: vm.isCompleted) { _, completed in
            if completed {
                showSummary = true
            }
        }
        .task {
            vm.loadReview()
        }
        .onDisappear {
            vm.cancel()
        }
    }

    @ViewBuilder
    private var loadingView: some View {
        VStack(spacing: 16) {
            Spacer()
            ProgressView()
                .scaleEffect(1.2)
            Text("AI 正在分析你的對話...")
                .foregroundStyle(.secondary)
            Spacer()
        }
        .frame(maxWidth: .infinity)
    }

    @ViewBuilder
    private var emptyView: some View {
        VStack(spacing: 16) {
            Spacer()
            Image(systemName: "text.bubble")
                .font(.system(size: 48))
                .foregroundStyle(.secondary)
            Text("這次對話沒有需要回顧的內容")
                .foregroundStyle(.secondary)
            Text("試著多聊幾句再結束對話吧！")
                .font(.caption)
                .foregroundStyle(.tertiary)
            Spacer()
        }
        .frame(maxWidth: .infinity)
    }

    @ViewBuilder
    private var segmentList: some View {
        ScrollView {
            LazyVStack(spacing: 12) {
                ForEach(vm.segments) { segment in
                    SegmentCard(
                        segment: segment,
                        isSelected: selectedSegmentId == segment.id,
                        onTap: {
                            withAnimation(.easeInOut(duration: 0.2)) {
                                if selectedSegmentId == segment.id {
                                    selectedSegmentId = nil
                                } else {
                                    selectedSegmentId = segment.id
                                    correctionSegmentId = segment.id
                                }
                            }
                        }
                    )
                }
            }
            .padding()
        }
    }

    @ViewBuilder
    private var bottomBar: some View {
        VStack(spacing: 8) {
            // Correction input
            if let segId = correctionSegmentId,
               let segment = vm.segments.first(where: { $0.id == segId }) {
                HStack(spacing: 0) {
                    Text("對第 \(segment.turnIndex + 1) 句提問")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Spacer()
                    Button {
                        correctionSegmentId = nil
                        correctionText = ""
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundStyle(.secondary)
                    }
                }

                HStack(spacing: 8) {
                    TextField("用中文或英文描述你想表達的...", text: $correctionText)
                        .textFieldStyle(.roundedBorder)

                    Button {
                        sendCorrection(segmentId: segId)
                    } label: {
                        if isSending {
                            ProgressView()
                                .frame(width: 28, height: 28)
                        } else {
                            Image(systemName: "arrow.up.circle.fill")
                                .font(.title2)
                        }
                    }
                    .disabled(correctionText.trimmingCharacters(in: .whitespaces).isEmpty || isSending)
                }
            }

            // End review button
            if !vm.isLoading && vm.segments.isEmpty {
                Button {
                    onComplete()
                } label: {
                    Text("回首頁")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
            } else {
                Button {
                    vm.endReview()
                } label: {
                    if vm.isEnding {
                        HStack(spacing: 8) {
                            ProgressView()
                                .tint(.white)
                            Text("總結中...")
                        }
                        .frame(maxWidth: .infinity)
                    } else {
                        Text("結束學習")
                            .frame(maxWidth: .infinity)
                    }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .disabled(vm.isLoading || vm.isEnding)
            }
        }
        .padding()
        .background(.ultraThinMaterial)
    }

    private func sendCorrection(segmentId: Int) {
        let message = correctionText.trimmingCharacters(in: .whitespaces)
        guard !message.isEmpty else { return }
        isSending = true
        correctionText = ""

        Task {
            await vm.submitCorrection(segmentId: segmentId, userMessage: message)
            isSending = false
        }
    }
}
