# Crave — Project Spec (Hackathon Edition)

## 1. Project Overview

Crave is an AI-native **web application** that transforms social media cooking content into interactive, personalized culinary experiences. Users import YouTube cooking videos, which are parsed by Google Gemini into structured, step-by-step recipes. The app then guides them through the cooking process with a live AI sous-chef and tracks their progress in a personal "Cookbook" — a ranked history of every dish they've cooked.

### Core Value Proposition

- **Social-to-Step:** Instant conversion of YouTube URLs into structured, step-by-step recipe data via Gemini.
- **Personalized AI:** User dietary restrictions and allergies are injected into the Gemini prompt, automatically flagging ingredient conflicts and suggesting substitutions before cooking begins.
- **Live Sous-Chef:** A real-time, WebSocket-driven AI cooking assistant that guides users step by step through the recipe.
- **Cookbook Tracking:** Users rate completed recipes (1–5 stars) and tag them, building a persistent ranked history of their culinary journey.
- **Save for Later:** Users can bookmark any extracted recipe before cooking and revisit it in a dedicated Saved tab in the Cookbook.

---

## 2. Tech Stack

| Component          | Technology                                      |
|--------------------|-------------------------------------------------|
| Platform           | Web (HTML + Vanilla CSS + JavaScript)           |
| Styling            | Tailwind CSS (CDN)                              |
| Backend            | Python (FastAPI + WebSockets + Uvicorn)         |
| AI Parsing Engine  | Google Gemini 1.5 Flash (JSON Mode)             |
| AI Cooking Mode    | Google Gemini Live API (WebSocket streaming)    |
| Database           | SQLite via SQLAlchemy ORM (local `crave.db`)    |
| Auth               | Email/password with UUID session tokens (Bearer)|

> **Future Migration Path:** The SQLAlchemy ORM is designed to be pointed at a Supabase (PostgreSQL) connection string with minimal code changes for production deployment.

---

## 3. Pages & Navigation

The app uses a persistent 4-tab bottom navigation bar across all screens.

| Tab       | Page           | Description |
|-----------|----------------|-------------|
| Discover  | `home.html`    | Social feed of trending recipes, quick filters, pantry suggestions. (Static MVP UI) |
| Import    | `import.html`  | Paste a YouTube URL to trigger AI recipe extraction. |
| Cookbook  | `tracker.html` | Personal Cookbook with two tabs — **Cooked** (ranked history) and **Saved** (bookmarked recipes). |
| Profile   | `profile.html` | Dietary preferences, allergy toggles, and account info. |

### Additional Pages

| Page                       | Description |
|----------------------------|-------------|
| `index.html`               | Sign in page (email/password). |
| `signup.html`              | Registration page. |
| `extracted-recipe.html`    | Recipe prep screen — shows parsed ingredients, dietary flags, and AI-suggested swaps before cooking starts. Back button returns to `import.html` by default, or `tracker.html` if the `from=tracker` query param is present. |
| `cooking-mode.html`        | The live cooking experience — step-by-step with real-time Gemini WebSocket assistant. |
| `cooking-mode-finish.html` | Post-cook celebration screen with star rating, quick tags, and "Log to Tracker" CTA. |

---

## 4. User Flow

1. **Sign Up / Sign In** (`index.html` → `signup.html`)
   - Email + password auth. Token stored in `localStorage` as `crave_token`.

2. **Set Profile** (`profile.html`)
   - Toggle dietary restrictions (Vegan, Gluten-Free, Nut-Free, Dairy-Free).
   - Add/remove specific allergies (e.g. "Shellfish").
   - Changes auto-save on toggle.

3. **Import a Recipe** (`import.html`)
   - Paste a YouTube URL, hit "Start Prep."
   - Frontend sends `POST /api/parse-youtube` with `Authorization: Bearer <token>`.
   - Backend fetches the user's profile, injects dietary restrictions into Gemini prompt.
   - Gemini parses the video and returns structured JSON.

4. **Recipe Prep** (`extracted-recipe.html`)
   - Displays recipe name, ingredient list, and cook time.
   - Ingredients with dietary conflicts are flagged with `dietary_conflict: true`.
   - AI Swap UI shows suggested substitutes inline.
   - **Save button** (top-right): calls `POST /api/saved` → briefly shows "Saved!" with a filled bookmark icon → automatically redirects to the Cookbook Saved tab after 600ms.
   - **Back button**: returns to `import.html` (clean load, bypasses bfcache). If the user arrived from the Cookbook (`?from=tracker`), returns to `tracker.html` instead.
   - User can also skip saving and tap **Start Cooking** to proceed directly to Cooking Mode.
   - Reachable from the Cookbook (Cooked or Saved tab) via stored `session_id` — no re-parsing required.

5. **Cooking Mode** (`cooking-mode.html`)
   - Step-by-step walkthrough of the recipe.
   - Real-time WebSocket connection to Gemini acting as a live sous-chef.
   - User can ask questions, request repeats, or skip steps.

6. **Finish & Log** (`cooking-mode-finish.html`)
   - Confetti celebration, plating suggestion from the AI.
   - User picks a 1–5 star rating and optional quick tags (Needs Salt, Perfect, Easy Prep).
   - Clicks "Log to Tracker" → `POST /api/history` → redirected to Cookbook.

7. **Cookbook / Tracker** (`tracker.html`)
   - Two tabs: **Cooked** and **Saved**.
   - **Cooked tab** (default): fetches `GET /api/history?sort_by=ranked` — displays ranked recipe cards with YouTube thumbnails, star ratings, and tags.
   - **Saved tab**: fetches `GET /api/saved` — displays bookmarked recipes with thumbnail.
   - Clicking a Cooked or Saved card with a `session_id` navigates to `extracted-recipe.html?session=<id>&from=tracker` (no re-parsing). Cards without a `session_id` (saved before this feature) fall back to opening the YouTube URL in a new tab.
   - `+` FAB routes back to Import.

---

## 5. Backend API Reference

All protected endpoints require `Authorization: Bearer <token>` header.

| Method | Endpoint              | Auth | Description |
|--------|-----------------------|------|-------------|
| POST   | `/api/auth/register`  | No   | Create a new account. Returns `access_token`. |
| POST   | `/api/auth/login`     | No   | Log in with email/password. Returns `access_token`. |
| GET    | `/api/profile`        | Yes  | Fetch the current user's profile. |
| PUT    | `/api/profile`        | Yes  | Update dietary preferences and allergies. |
| POST   | `/api/parse-youtube`  | Yes  | Parse a YouTube URL. Returns `session_id` + recipe JSON. |
| GET    | `/api/recipes/{id}`   | No   | Fetch a stored recipe session by ID. |
| GET    | `/api/history`        | Yes  | Fetch user's cooked history (supports `?sort_by=ranked`). |
| POST   | `/api/history`        | Yes  | Log a completed recipe with rating and tags. |
| GET    | `/api/saved`          | Yes  | Fetch user's saved/bookmarked recipes (newest first). |
| POST   | `/api/saved`          | Yes  | Save a recipe from a session. De-duplicates by URL per user (409 if already saved). |
| DELETE | `/api/saved/{id}`     | Yes  | Remove a saved recipe (unsave). |
| WS     | `/ws/cook/{id}`       | No   | WebSocket for live Gemini cooking assistant. |

---

## 6. Data Architecture

### Recipe JSON Schema (Gemini Output)

```json
{
  "recipe_name": "String",
  "source_url": "String",
  "cook_time_minutes": 30,
  "ingredients": [
    {
      "item": "String",
      "amount": "String",
      "dietary_conflict": false,
      "suggested_substitute": "String or null"
    }
  ],
  "steps": [
    {
      "step_number": 1,
      "timestamp_sec": 45,
      "instruction": "Mince the garlic and ginger.",
      "visual_context": "The chef uses a rocking motion with a chef's knife.",
      "technical_terms": ["Mince"]
    }
  ],
  "dietary_summary": "String"
}
```

### SQLite Database Schema (`crave.db`)

| Table            | Key Columns |
|------------------|-------------|
| `users`          | `id`, `email`, `pwd_hash` |
| `sessions`       | `access_token`, `user_id` |
| `profiles`       | `user_id`, `name`, `vegan`, `gluten_free`, `nut_free`, `dairy_free`, `allergies (JSON)` |
| `parsed_recipes` | `session_id`, `dry_run`, `schema_dump (JSON)` |
| `cooked_history` | `id`, `user_id`, `recipe_name`, `source_url`, `thumbnail_url`, `session_id`, `rating`, `tags (JSON)`, `cooked_at` |
| `saved_recipes`  | `id`, `user_id`, `recipe_name`, `source_url`, `thumbnail_url`, `session_id`, `saved_at` |

---

## 7. AI & Personalization

### Dietary Injection (Parsing)
When a user imports a recipe, their profile is fetched and injected into the Gemini system prompt:
```
User dietary context: Vegan. Nut-free. Allergies: Shellfish, Gluten.
Flag any conflicting ingredients with dietary_conflict=true and provide a suggested_substitute.
```

### Gemini Cooking Persona (WebSocket)
```
You are the Crave Sous-Chef. You are helping a user cook a specific recipe parsed
from a video. Be concise, encouraging, and wait for user confirmation before
moving to the next step. If a user asks about a technique, explain it simply.
```

---

## 8. Design System

- **Color Palette:** Dark Forest Green (`#0f5238`) · Cream White (`#f8faf6`) · Mint (`#b1f0ce`)
- **Typography:** Plus Jakarta Sans (headlines) · Inter (body)
- **Style:** Glassmorphism headers, botanical gradients, rounded cards, Material Symbols icons
- **Navigation:** Fixed 4-tab bottom nav with active state indicator pill

---

## 9. Authentication & Security

- Passwords hashed with SHA-256.
- Session tokens are UUIDs stored in the `sessions` table.
- Frontend stores token in `localStorage` as `crave_token`.
- All recipe import, history, and profile endpoints are protected — the app requires an account to use any core feature.

---

## 10. Future Roadmap (Post-Hackathon)

| Phase | Feature |
|---|---|
| Phase 2 — Database | Migrate from SQLite to Supabase (PostgreSQL) with minimal ORM changes. |
| Phase 3 — Discover Feed | Dynamic AI-curated recipe feed based on user history and trending social content. |
| Phase 4 — Pantry | Smart pantry tracking — suggest recipes based on what's about to expire. |
| Phase 5 — Vision | Real-time camera feed analysis via Gemini Live to verify cooking progress. |
| Phase 6 — Social | Community "Remix" feed for user-submitted recipe tweaks. |
