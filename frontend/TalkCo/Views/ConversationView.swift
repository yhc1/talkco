import SwiftUI

struct ConversationView: View {
    let topic: Topic
    let popToRoot: () -> Void
    @State private var vm: ConversationViewModel
    @State private var navigateToReview: String?

    init(topic: Topic, popToRoot: @escaping () -> Void) {
        self.topic = topic
        self.popToRoot = popToRoot
        _vm = State(initialValue: ConversationViewModel(topic: topic))
    }

    var body: some View {
        VStack(spacing: 0) {
            // Message list
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 12) {
                        ForEach(vm.messages) { msg in
                            MessageBubble(message: msg)
                                .id(msg.id)
                        }
                    }
                    .padding()
                }
                .onChange(of: vm.messages.count) { _, _ in
                    if let last = vm.messages.last {
                        withAnimation {
                            proxy.scrollTo(last.id, anchor: .bottom)
                        }
                    }
                }
            }

            Divider()

            // Bottom bar
            bottomBar
        }
        .navigationTitle(topic.labelZh)
        .navigationBarTitleDisplayMode(.inline)
        .navigationBarBackButtonHidden(true)
        .toolbar {
            ToolbarItem(placement: .topBarLeading) {
                Button("結束對話") {
                    Task {
                        if let sid = await vm.endConversation() {
                            navigateToReview = sid
                        } else {
                            popToRoot()
                        }
                    }
                }
                .disabled(vm.isConnecting || vm.isEnded)
            }
        }
        .navigationDestination(item: $navigateToReview) { sessionId in
            ReviewView(sessionId: sessionId, onComplete: popToRoot)
        }
        .task {
            await vm.startSession()
        }
    }

    @ViewBuilder
    private var bottomBar: some View {
        HStack(spacing: 16) {
            if vm.isConnecting {
                HStack(spacing: 8) {
                    ProgressView()
                    Text("連線中...")
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity)
            } else if vm.isProcessing {
                HStack(spacing: 8) {
                    ProgressView()
                    Text("處理中...")
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity)
            } else if vm.isEnded {
                Text("對話已結束")
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity)
            } else {
                // Push-to-talk button
                PushToTalkButton(
                    isRecording: vm.isRecording,
                    onPress: { vm.startRecording() },
                    onRelease: { vm.stopRecording() }
                )
                .frame(maxWidth: .infinity)
            }
        }
        .padding()
        .background(.ultraThinMaterial)
    }
}

// MARK: - Subviews

private struct MessageBubble: View {
    let message: ChatMessage

    var body: some View {
        HStack {
            if message.role == .user { Spacer(minLength: 60) }

            Text(message.text)
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background(
                    message.role == .user ? Color.accentColor : Color(.systemGray5),
                    in: RoundedRectangle(cornerRadius: 16)
                )
                .foregroundStyle(message.role == .user ? .white : .primary)

            if message.role == .ai { Spacer(minLength: 60) }
        }
    }
}

private struct PushToTalkButton: View {
    let isRecording: Bool
    let onPress: () -> Void
    let onRelease: () -> Void

    var body: some View {
        Image(systemName: isRecording ? "mic.fill" : "mic")
            .font(.system(size: 28))
            .foregroundStyle(isRecording ? .red : .accentColor)
            .frame(width: 72, height: 72)
            .background(
                Circle()
                    .fill(isRecording ? Color.red.opacity(0.15) : Color.accentColor.opacity(0.1))
            )
            .scaleEffect(isRecording ? 1.15 : 1.0)
            .animation(.easeInOut(duration: 0.15), value: isRecording)
            .gesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { _ in
                        if !isRecording { onPress() }
                    }
                    .onEnded { _ in
                        onRelease()
                    }
            )
    }
}
