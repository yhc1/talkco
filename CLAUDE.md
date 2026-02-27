# Language Learning App — App-Level Context

> This file defines the product's core concepts, user flow, and terminology.
> It is the shared reference for all sub-projects (frontend, backend).
> Implementation details belong in frontend @fontend/CLAUDE.md and backend @backend/CLAUDE.md.

---

## What This App Does

An AI-powered English conversation practice app for Mandarin Chinese native speakers. The core loop is: have a conversation, review it with AI assistance, and let the system adapt to your level over time.

---

## Core User Flow

```
[ Pick a Topic ]
  - Frontend shows predefined topic cards
  - User selects one
       ↓
[ Conversation ]
  - AI greets the user and introduces the chosen topic
  - User chats with AI in English
       ↓
[ Review Interface ]
  - AI proactively marks Segments it identified as unnatural or incorrect
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
