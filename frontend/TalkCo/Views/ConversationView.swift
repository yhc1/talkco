import SwiftUI

struct ConversationView: View {
    let topic: Topic
    let popToRoot: () -> Void
    @State private var vm: ConversationViewModel
    @State private var navigateToReview: String?
    @State private var textInput = ""
    @FocusState private var isTextFieldFocused: Bool

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
        VStack(spacing: 0) {
            if vm.isConnecting {
                HStack(spacing: 8) {
                    ProgressView()
                    Text("連線中...")
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity)
                .padding()
            } else if vm.isProcessing {
                HStack(spacing: 8) {
                    ProgressView()
                    Text("處理中...")
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity)
                .padding()
            } else if vm.isEnded {
                Text("對話已結束")
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity)
                    .padding()
            } else {
                HStack(spacing: 12) {
                    // Text input
                    TextField("輸入英文...", text: $textInput)
                        .textFieldStyle(.roundedBorder)
                        .focused($isTextFieldFocused)
                        .submitLabel(.send)
                        .onSubmit { submitText() }

                    if textInput.trimmingCharacters(in: .whitespaces).isEmpty {
                        // Mic button (tap to toggle recording)
                        ToggleRecordButton(
                            isRecording: vm.isRecording,
                            onTap: {
                                if vm.isRecording {
                                    vm.stopRecording()
                                } else {
                                    vm.startRecording()
                                }
                            }
                        )
                    } else {
                        // Send button (when has text)
                        Button {
                            submitText()
                        } label: {
                            Image(systemName: "arrow.up.circle.fill")
                                .font(.system(size: 32))
                                .foregroundStyle(.tint)
                        }
                    }
                }
                .padding()
            }
        }
        .background(.ultraThinMaterial)
    }

    private func submitText() {
        let text = textInput
        textInput = ""
        isTextFieldFocused = false
        vm.sendText(text)
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

private struct ToggleRecordButton: View {
    let isRecording: Bool
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            Image(systemName: isRecording ? "stop.circle.fill" : "mic")
                .font(.system(size: 22))
                .foregroundStyle(isRecording ? .red : .accentColor)
                .frame(width: 44, height: 44)
                .background(
                    Circle()
                        .fill(isRecording ? Color.red.opacity(0.15) : Color.accentColor.opacity(0.1))
                )
                .scaleEffect(isRecording ? 1.15 : 1.0)
                .animation(.easeInOut(duration: 0.15), value: isRecording)
        }
        .buttonStyle(.plain)
    }
}
