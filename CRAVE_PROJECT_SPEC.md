# Crave — Project Spec (Hackathon Edition)

## 1. Project Overview

Crave is an AI-native iOS application that transforms social media cooking content into interactive, hands-free culinary experiences. For the MVP/Hackathon, the focus is on high-speed ingestion and a seamless, low-latency voice dialogue using the Gemini Live API.

### Core Value Proposition

- **Social-to-Step:** Instant conversion of YouTube URLs into structured data.
- **Live Sous-Chef:** A real-time, interruptible voice assistant that knows your specific recipe.
- **Safety & Subs:** Automated detection of dietary conflicts with voice-guided alternatives.

---

## 2. Target Tech Stack

| Component        | Technology                          |
|------------------|-------------------------------------|
| Platform         | iOS (SwiftUI)                       |
| Backend/Bridge   | Python (FastAPI + WebSockets)       |
| Parsing Engine   | Gemini 1.5 Flash (JSON Mode)        |
| Voice Interface  | Gemini Live API (Multimodal Live)   |
| Persistence      | SwiftData (Local)                   |

---

## 3. User Flow (Hackathon Focus)

1. **Ingestion:** User pastes a YouTube URL.
2. **Analysis** *(Gemini 1.5 Flash)*:
   - Fast-parsing of video/audio into a specialized JSON.
   - Each step must include `visual_details` to help the Voice Assistant describe what is happening in the video.
3. **The Briefing:** Gemini Live initiates an audio session, summarizing the ingredients and asking if the user is ready to begin.
4. **Interactive Cooking:**
   - User uses voice commands (`"Next"`, `"Repeat that"`, `"What's a 'chiffonade'?"`) to navigate.
   - **Function Calling:** Gemini Live calls local functions to fetch recipe data or set timers.
5. **Dietary Guardrails:** Real-time substitution suggestions if a user mentions a missing ingredient or dietary conflict.

---

## 4. Gemini Live Implementation (Phase 1 & 2)

### A. System Instruction (The Persona)

```
You are the Crave Sous-Chef. You are helping a user cook a specific recipe parsed
from a video. You have access to `get_recipe_data`. Be concise, encouraging, and
wait for user confirmation before moving to the next step. If a user asks a question
about a technique, explain it simply. If they sound rushed, slow down your pace.
```

### B. Tool Definitions (Function Calling)

| Function | Description |
|---|---|
| `get_step_details(step_number)` | Returns the instruction and visual cues for a specific step. |
| `get_ingredient_info(item_name)` | Returns measurements or substitution logic. |
| `set_kitchen_timer(duration_seconds)` | Triggers a UI timer in the iOS app. |

---

## 5. Data Architecture: Enhanced JSON Schema

The schema includes `visual_context` and `timestamp_sec` to bridge the gap between the video and the voice assistant.

```json
{
  "recipe_name": "String",
  "source_url": "String",
  "ingredients": [
    {
      "item": "String",
      "amount": "String",
      "dietary_conflict": false,
      "suggested_substitute": "String"
    }
  ],
  "steps": [
    {
      "step_number": 1,
      "timestamp_sec": 45,
      "instruction": "Mince the garlic and ginger.",
      "visual_context": "The chef is using a rocking motion with a chef's knife; the garlic is very fine.",
      "technical_terms": ["Mince"]
    }
  ],
  "dietary_summary": "String (Quick overview of any flags for the user)"
}
```

---

## 6. UI/UX & Engagement

### Visual Theme
- **Palette:** Dark green / Cream (nature-inspired, "Fresh" aesthetic)

### Navigation
- Bottom Tab Bar: `Explore` · `Curate` · `Favorites` · `Profile`

### Smart Notifications
- **Retention:** *"That Garden Pesto looked amazing — ready to cook it tonight?"* (triggered if a recipe is saved but not cooked within 48 hours)
- **Location-Based:** Notify the user of remaining grocery list items when near a store.

---

## 7. Development Constraints (MVP)

- **No External Integrations:** All lists and data stay within the app ecosystem.
- **No Caching:** Veo generation is always fresh to ensure maximum context accuracy.
- **Local Persistence:** SwiftData for recipe and list management.

---

## 8. Future Roadmap (Post-Hackathon)

| Phase | Feature |
|---|---|
| Phase 3 — Vision | Real-time camera feed analysis via Gemini Live to verify cooking progress. |
| Phase 4 — Veo | On-demand instructional video generation for complex techniques. |
| Phase 5 — Social | Community "Remix" feed for user-submitted recipe tweaks. |


## Coding/documenting guidelines

* Create a file per feature or related features, split as much as possible in different files;
* add docstrings to all functions to explain what they do;
* start each file with a long comment explaining in detail what the feature is about and the different use cases;
* maintain a `Design.md` document at the root of the app that documents all the features of the app;
* log as info all function calls (with their parameters) and log all genai calls with all their parameters (model used, prompt, config) and their outputs, just strip inline data;
* group all configurable items (like model names) in a centralized file;
* always create a way to test the scripts without altering the data;
