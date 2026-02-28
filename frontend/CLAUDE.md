# Frontend CLAUDE.md

> iOS app implementation reference.
For product concepts and terminology, refer to the root ../CLAUDE.md.
For backend API details, refer to @../backend/CLAUDE.md.

---

## Tech Stack

- **SwiftUI** (iOS 17+)
- **@Observable** (Observation framework) for state management
- **NavigationStack** with path-based navigation for pop-to-root
- **URLSession** for networking (JSON, SSE streaming, multipart upload)
- **AVAudioEngine** for recording (PCM16, 24kHz, mono)
- **AVAudioPlayerNode** for streaming audio playback
- **User ID**: auto-generated UUID stored in UserDefaults (no auth in v1)

---

## Navigation Flow

```
MainTabView (TabView)
  ├── Tab 1: "練習" → TopicSelectionView
  └── Tab 2: "我的" → ProfileView

TopicSelectionView (NavigationStack with NavigationPath)
  │  ReviewModeCard → NavigationLink(value: "__review__")
  │  TopicCard → NavigationLink(value: topicId)
  │  Needs-review banner (orange, shown when needs_review=true)
  ↓
ConversationView (topic?, mode, popToRoot closure)
  │  mode="conversation": "結束對話" → DELETE /sessions/{id} → navigateToReview
  │  mode="review": "結束複習" → DELETE /sessions/{id} → popToRoot() (skip review)
  │  navigationBarBackButtonHidden(true)
  ↓  navigationDestination(item: $navigateToReview) [conversation mode only]
ReviewView (sessionId, onComplete = popToRoot)
  │  "結束學習" → POST /sessions/{id}/end → poll until completed
  │  navigationBarBackButtonHidden(true)
  ↓  navigationDestination(isPresented: $showSummary)
SessionSummaryView (summary, onDismiss = popToRoot)
  │  "完成" → onDismiss() → navigationPath = NavigationPath()
  ↓
TopicSelectionView (back to root)
```

Pop-to-root: `TopicSelectionView` owns a `@State NavigationPath`, passes `popToRoot` closure (`{ navigationPath = NavigationPath() }`) down through `ConversationView` → `ReviewView` → `SessionSummaryView`.

---

## Key Implementation Details

**Audio format**: PCM16, 24kHz, mono. Recording wraps raw PCM in WAV headers. Playback converts Int16 → Float32.

**Audio silence detection**: Before sending recorded audio, `ConversationViewModel.hasSpeech()` computes PCM16 RMS energy. Audio below threshold (~300 RMS) is discarded without sending to backend. Additionally, if OpenAI returns an empty transcript, the entire turn is discarded and audio playback is stopped.

**SSE parsing**: `APIClient.parseSSEStream` reads `event:` / `data:` lines, yields `SSEvent(event, data)`.

**Audio-text sync**: AI response text is deferred until after the SSE stream ends (all audio chunks scheduled), so text and audio appear simultaneously. User transcript is shown immediately. This pattern is used in `streamGreeting()`, `sendAudio()`, and `sendTextMessage()`.

**Polling**: `ReviewViewModel` polls every 2 seconds. `loadReview()` stops when AI marks appear or status != "reviewing". `endReview()` stops when status == "completed" and summary != nil.

**Issue type colors** (used in `SegmentCard` and `SessionSummaryView`):
| issue_type | Color | Chinese |
|---|---|---|
| grammar | Red | 文法 |
| naturalness | Orange | 自然度 |
| sentence_structure | Purple | 句構 |

**State pattern**: ViewModels are `@Observable` classes, initialized via `_vm = State(initialValue: ViewModel())` in view init.

---

## Session Modes

**Conversation mode** (`mode="conversation"`):
- User picks a topic → ConversationView → end → ReviewView → SessionSummaryView → home
- `CreateSessionBody` sends `topicId` + `mode="conversation"`
- Backend injects same-topic chat history into AI context
- `endConversation()` returns sessionId for review navigation

**Review mode** (`mode="review"`):
- User taps "弱點複習" card → ConversationView → end → home (no review flow)
- `CreateSessionBody` sends `topicId=nil` + `mode="review"`
- AI acts as teacher, drilling weak points with exercises
- `endConversation()` returns nil (skip review), `popToRoot()` is called

---

## Profile Page

- **CEFR level** display with re-evaluation button
- **學習總覽** — `progressNotes` from profile (learning progress summary)
- **需要加強** — 3-dimension weak points with `DisclosureGroup`:
  - Each `WeakPointPattern` has a `pattern` (繁中 description) and `examples` (wrong/correct pairs)
  - Expand to see strikethrough wrong + green correct examples
  - Old-format weak points (plain strings) are silently ignored
- **Needs-review banner** on TopicSelectionView when `needs_review=true` (3+ examples on any pattern)
