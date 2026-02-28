import SwiftUI

struct ConversationView: View {
    let topic: Topic?
    let mode: String
    let popToRoot: () -> Void
    @State private var vm: ConversationViewModel
    @State private var navigateToReview: String?
    @State private var textInput = ""
    @State private var showTextInput = false
    @FocusState private var isTextFieldFocused: Bool

    init(topic: Topic? = nil, mode: String = "conversation", popToRoot: @escaping () -> Void) {
        self.topic = topic
        self.mode = mode
        self.popToRoot = popToRoot
        _vm = State(initialValue: ConversationViewModel(topic: topic, mode: mode))
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
        .navigationTitle(mode == "review" ? "弱點複習" : (topic?.labelZh ?? "對話"))
        .navigationBarTitleDisplayMode(.inline)
        .navigationBarBackButtonHidden(true)
        .toolbar {
            ToolbarItem(placement: .topBarLeading) {
                Button(mode == "review" ? "結束複習" : "結束對話") {
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
                .padding(.vertical, 24)
            } else if vm.isProcessing {
                HStack(spacing: 8) {
                    ProgressView()
                    Text("處理中...")
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 24)
            } else if vm.isEnded {
                Text("對話已結束")
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 24)
            } else if showTextInput {
                // Text input mode (secondary)
                HStack(spacing: 10) {
                    Button {
                        withAnimation(.easeInOut(duration: 0.2)) {
                            showTextInput = false
                            isTextFieldFocused = false
                        }
                    } label: {
                        Image(systemName: "mic.fill")
                            .font(.system(size: 20))
                            .foregroundStyle(Color.accentColor)
                            .frame(width: 36, height: 36)
                    }

                    TextField("輸入英文...", text: $textInput)
                        .textFieldStyle(.roundedBorder)
                        .focused($isTextFieldFocused)
                        .submitLabel(.send)
                        .onSubmit { submitText() }

                    Button {
                        submitText()
                    } label: {
                        Image(systemName: "arrow.up.circle.fill")
                            .font(.system(size: 32))
                            .foregroundStyle(
                                textInput.trimmingCharacters(in: .whitespaces).isEmpty
                                    ? Color(.systemGray4) : Color.accentColor
                            )
                    }
                    .disabled(textInput.trimmingCharacters(in: .whitespaces).isEmpty)
                }
                .padding(.horizontal)
                .padding(.vertical, 10)
            } else {
                // Voice mode (primary) — large centered mic
                HStack {
                    // Keyboard toggle (small, left side)
                    Button {
                        withAnimation(.easeInOut(duration: 0.2)) {
                            showTextInput = true
                        }
                        isTextFieldFocused = true
                    } label: {
                        Image(systemName: "keyboard")
                            .font(.system(size: 18))
                            .foregroundStyle(.secondary)
                            .frame(width: 44, height: 44)
                    }

                    Spacer()

                    // Main mic button
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

                    Spacer()

                    // Invisible spacer to keep mic centered
                    Color.clear.frame(width: 44, height: 44)
                }
                .padding(.horizontal)
                .padding(.vertical, 12)
            }
        }
        .background(.ultraThinMaterial)
    }

    private func submitText() {
        let text = textInput
        textInput = ""
        isTextFieldFocused = false
        showTextInput = false
        vm.sendText(text)
    }
}

// MARK: - Subviews

private struct MessageBubble: View {
    let message: ChatMessage

    var body: some View {
        HStack(alignment: .bottom, spacing: 8) {
            if message.role == .user {
                Spacer(minLength: 40)
            } else {
                avatar(systemName: "sparkles", color: .purple)
            }

            Text(message.text)
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background(
                    message.role == .user ? Color.accentColor : Color(.systemGray5),
                    in: RoundedRectangle(cornerRadius: 16)
                )
                .foregroundStyle(message.role == .user ? .white : .primary)

            if message.role == .ai {
                Spacer(minLength: 40)
            } else {
                avatar(systemName: "person.circle.fill", color: .accentColor)
            }
        }
    }

    private func avatar(systemName: String, color: Color) -> some View {
        Image(systemName: systemName)
            .font(.system(size: 24))
            .foregroundStyle(color)
            .frame(width: 32, height: 32)
    }
}

private struct ToggleRecordButton: View {
    let isRecording: Bool
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            Image(systemName: isRecording ? "stop.fill" : "mic.fill")
                .font(.system(size: 28, weight: .medium))
                .foregroundStyle(isRecording ? .white : Color.accentColor)
                .frame(width: 64, height: 64)
                .background(
                    Circle()
                        .fill(isRecording ? Color.red : Color.accentColor.opacity(0.12))
                )
                .scaleEffect(isRecording ? 1.08 : 1.0)
                .animation(.easeInOut(duration: 0.2), value: isRecording)
        }
        .buttonStyle(.plain)
    }
}
