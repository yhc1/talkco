# Language Learning App — App-Level Context

> This file defines the product's core concepts, user flow, and terminology.
> It is the shared reference for all sub-projects (frontend, backend).
> Implementation details belong in /frontend/CLAUDE.md and /backend/CLAUDE.md.

---

## What This App Does

An AI-powered English conversation practice app for Mandarin Chinese native speakers. The core loop is: have a conversation, review it with AI assistance, and let the system adapt to your level over time.

The two problems it solves:
1. Conversation practice feels unnatural with existing apps
2. Users practice but don't systematically improve

---

## Core User Flow

```
[ Start Chatting ]
       ↓
[ Conversation ]
  - User chats with AI in English
  - Topic can be system-suggested or user-directed
       ↓
[ Review Interface ]
  - AI proactively marks Segments it identified as unnatural or incorrect
  - User can additionally Flag any Segment: "I didn't express what I meant"
  - User can re-describe their intent in Mandarin Chinese for any flagged Segment
  - AI provides natural, level-appropriate English alternatives with context
  - Shows overall summary: what the user did well, what needs improvement
  - User presses [ End ] to finalize
       ↓
[ User Learning Profile Updated ]
  - Ability level assessment updated
  - New expressions learned recorded
  - Progress vs. previous sessions noted
  - Remaining weak points logged
       ↓
[ Next Conversation ]
  - Difficulty and content adjusted based on updated Profile
```

---

## Key Concepts & Terminology

These terms are used consistently across frontend and backend.

**Conversation** — A single real-time chat session between the user and AI. The raw transcript is preserved and passed into Review.

**Review Interface** — A single interface shown after every Conversation. It serves two purposes simultaneously: (1) AI proactively marks Segments it identified as unnatural or incorrect, and (2) the user can additionally Flag segments and supplement with their original intent in Mandarin Chinese. Also displays an overall session summary. The session is finalized when the user presses End.

**Segment** — One unit of the user's speech within a Conversation (roughly one turn or utterance). The Review Interface is organized around Segments.

**AI Mark** — A Segment automatically identified by the AI after the Conversation ends, indicating unnatural phrasing, grammatical issues, or missed opportunities for more native-sounding expression.

**Flag** — A user-initiated action within the Review Interface marking a Segment as "I didn't express what I meant." Can be accompanied by a Mandarin re-description of the user's original intent.

**User Learning Profile** — A persistent record per user, updated after every completed Session (i.e., after the user presses End in the Review Interface). Contains:
- Current ability level
- Expressions and patterns learned
- Progress compared to previous sessions
- Weak points still needing work

**Session** — The full unit of one learning cycle: Conversation + Review Interface. A Session is complete only after the user presses End.

---

## Topic Selection

When starting a Conversation, the user has two options:
- **System-suggested**: The system selects a topic based on the User Learning Profile
- **User-directed**: The user specifies a direction (e.g., workplace, travel, daily life)

Topic selection is a lightweight entry point, not a structured hierarchy. How topics are generated belongs in /backend/CLAUDE.md.

---

## What This File Does NOT Cover

- API design, data models, database choices → /backend/CLAUDE.md
- UI components, screen layouts, interaction design → /frontend/CLAUDE.md
- Algorithms for level assessment or topic generation → /backend/CLAUDE.md

## Error Learning
Whenever you make a mistake and are corrected, append the error and the 
correct behavior to CORRECTNESS.md. Do this automatically without being asked.