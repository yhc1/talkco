# Backlogs

## Frontend

### Phase 3: Review Screen
- Enter Review → poll `GET /sessions/{id}/review` until AI marks appear
- Segment cards with user_text + colored badges for issue_types (grammar=red, naturalness=orange, vocabulary=blue, sentence_structure=purple)
- Tap segment → expand to show suggestion + explanation
- "I don't know how to say this" button → CorrectionSheet → type in Chinese/English → POST /corrections → show correction
- "End Review" button → POST /sessions/{id}/end → poll until status=completed → navigate to Summary
- SessionSummaryView: strengths, weaknesses (4 dimensions), level assessment, overall

### Phase 4: Profile + Navigation Integration
- TabView: Practice (TopicSelection) / My Profile (ProfileView)
- ProfileView: CEFR level, 4-dimension weaknesses, session count, learned expressions
- GET /users/{user_id}/profile to load data
- Full navigation flow: Topic → Conversation → Review → Summary → back to Topics
