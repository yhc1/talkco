# Frontend CLAUDE.md

> iOS app implementation reference.
> For product concepts and terminology, refer to the root /CLAUDE.md.
> For backend API details, refer to /backend/CLAUDE.md.
> **Always read /CORRECTNESS.md before starting work** to avoid repeating past mistakes.

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

## Current File Structure

```
frontend/TalkCo/
  TalkCoApp.swift                    -- @main, WindowGroup → TopicSelectionView
  Config.swift                       -- baseURL (localhost vs device), userID (UUID in UserDefaults)
  Models/
    Topic.swift                      -- Topic struct + static all (6 hardcoded topics)
    Session.swift                    -- CreateSessionResponse, DeleteSessionResponse,
                                        ReviewResponse, CorrectionRequest, EndSessionResponse
    ChatMessage.swift                -- ChatMessage(id: UUID, role: .user/.ai, text: String)
    Segment.swift                    -- Segment(id, turnIndex, userText, aiText, aiMarks, corrections)
    AIMark.swift                     -- AIMark(id, issueTypes, original, suggestion, explanation)
    Correction.swift                 -- Correction(id, userMessage, correction, explanation, createdAt)
    SessionSummary.swift             -- SessionSummary(strengths, weaknesses, levelAssessment, overall)
  Services/
    APIClient.swift                  -- get/post/delete JSON, streamSSE, streamMultipart
    AudioRecorder.swift              -- AVAudioEngine → PCM16 24kHz mono → WAV Data
    AudioPlayer.swift                -- PCM16 base64 → Float32 → AVAudioPlayerNode.scheduleBuffer
  ViewModels/
    ConversationViewModel.swift      -- startSession, startRecording, stopRecording, endConversation
    ReviewViewModel.swift            -- loadReview (poll), submitCorrection, endReview (poll)
  Views/
    TopicSelectionView.swift         -- NavigationStack + NavigationPath, 2-col grid of TopicCard
    ConversationView.swift           -- Message list + push-to-talk + "結束對話" toolbar button
    ReviewView.swift                 -- Segment list + correction input bar + "結束學習" button
    SegmentCard.swift                -- Expandable card with issue badges + FlowLayout
    SessionSummaryView.swift         -- Strengths/weaknesses/level display + "完成" button
    CorrectionSheet.swift            -- Placeholder (correction input integrated in ReviewView)
```

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

## Backend Endpoints Used

| Method | Endpoint | Request | Response | Used In |
|--------|----------|---------|----------|---------|
| POST | /sessions | `{ user_id, topic_id }` | `CreateSessionResponse` | ConversationViewModel.startSession |
| POST | /sessions/{id}/start | (none, SSE) | events: response, audio | ConversationViewModel.streamGreeting |
| POST | /sessions/{id}/chat | multipart WAV | events: transcript, response, audio | ConversationViewModel.sendAudio |
| DELETE | /sessions/{id} | (none) | `DeleteSessionResponse` | ConversationViewModel.endConversation |
| GET | /sessions/{id}/review | (none) | `ReviewResponse` | ReviewViewModel.loadReview (polled) |
| POST | /sessions/{id}/corrections | `CorrectionRequest` | `Correction` | ReviewViewModel.submitCorrection |
| POST | /sessions/{id}/end | `{}` (empty) | `EndSessionResponse` | ReviewViewModel.endReview |

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

---

## Not in v1

- User login / registration
- Offline mode
- Session history list
- Push notifications
- Custom animations / transitions

---

## End-to-End Verification

```
1. Start backend: cd backend && source .venv/bin/activate && python main.py
2. Run app in Xcode (simulator or device)
3. ✅ Select a topic → hear AI greeting
4. ✅ Push-to-talk a few turns → see transcripts + hear AI responses
5. ✅ Tap "結束對話"
6. ✅ Review: see AI marks with color badges → tap a segment → ask a correction question
7. ✅ Tap "結束學習" → see session summary
8. ⬜ Switch to Profile tab → verify updated level and weaknesses  ← Phase 4
```
