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
TopicSelectionView (NavigationStack with NavigationPath)
  │  NavigationLink(value: topicId)
  ↓
ConversationView (topic, popToRoot closure)
  │  "結束對話" → DELETE /sessions/{id} → set navigateToReview
  │  navigationBarBackButtonHidden(true)
  ↓  navigationDestination(item: $navigateToReview)
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

**SSE parsing**: `APIClient.parseSSEStream` reads `event:` / `data:` lines, yields `SSEvent(event, data)`.

**Polling**: `ReviewViewModel` polls every 2 seconds. `loadReview()` stops when AI marks appear or status != "reviewing". `endReview()` stops when status == "completed" and summary != nil.

**Issue type colors** (used in `SegmentCard` and `SessionSummaryView`):
| issue_type | Color | Chinese |
|---|---|---|
| grammar | Red | 文法 |
| naturalness | Orange | 自然度 |
| vocabulary | Blue | 詞彙 |
| sentence_structure | Purple | 句構 |

**State pattern**: ViewModels are `@Observable` classes, initialized via `_vm = State(initialValue: ViewModel())` in view init.

---

## Next Phase: Phase 4 — Profile + Tab Navigation

User profile screen and tab-based navigation.

**Files to create:**
```
  Views/
    MainTabView.swift              -- TabView: "練習" (TopicSelectionView) / "我的" (ProfileView)
    ProfileView.swift              -- CEFR level, 4-dimension weaknesses, session count, expressions
  ViewModels/
    ProfileViewModel.swift         -- Load and display user profile
```

**Files to modify:**
- `TalkCoApp.swift` — Change root from `TopicSelectionView` to `MainTabView`

**Functionality:**
1. `TabView` with two tabs: "練習" (Practice → TopicSelectionView) / "我的" (Profile → ProfileView)
2. `ProfileView`: CEFR level display, 4-dimension weaknesses, session count, learned expressions
3. `GET /users/{user_id}/profile` to load data

**Backend endpoint:** `GET /users/{user_id}/profile`

**Verification:** Complete a full session → return to home → switch to Profile tab → see updated level and weaknesses
