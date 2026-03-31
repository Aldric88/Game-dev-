# ML Implementation Reference

## Algorithms Used

---

### 1. TF-IDF (Term Frequency – Inverse Document Frequency)

**What it is:** Converts text into numerical vectors based on word importance.

**Where implemented:** `backend/app/ml/classifier.py`

**Used in:**
- Search — transforms user query into a vector for genre classification
- K-Means — vectorizes project descriptions for clustering

**Configuration:**
- Word-level n-grams (1–2 words)
- Character-level n-grams (2–4 chars) — handles partial words and typos
- Both combined via `FeatureUnion`

---

### 2. Logistic Regression

**What it is:** Multiclass classifier — predicts which of 17 game genres a query belongs to.

**Where implemented:** `backend/app/ml/classifier.py`

**Used in:**
- Search Stage 3 — predicts genre from query, brings matching projects
- Recommendations — search history events (genre + confidence) feed preference vector

**Details:**
- 17 genres: platformer, rpg, survival, shooter, space_shooter, racing, puzzle, fighting, arcade, topdown, tower_defense, snake, flappy, and more
- Confidence threshold: 0.50 — below this, ML results are skipped
- Model file: `backend/app/ml/models/game_type_classifier.pkl`
- Training data: `backend/app/ml/training_data/game_prompts.json`
- Auto-retrains at 50 new user-confirmed examples

---

### 3. Levenshtein Distance

**What it is:** Edit distance algorithm — counts character changes between two strings. Normalized to 0.0–1.0 similarity score.

**Where implemented:** `backend/app/services/search_service.py`

**Used in:**
- Search Stage 2 — fuzzy name matching, catches typos
- Example: `"nigtth surval"` → matches `"Night Survival"` (similarity ≥ 0.75)

**Details:**
- Threshold: similarity ≥ 0.75 to count as a match
- Compares each query token against every word in every project name
- No training needed — pure algorithm

---

### 4. K-Means Clustering

**What it is:** Unsupervised algorithm — groups projects into content clusters based on TF-IDF vectors.

**Where implemented:** `backend/app/ml/cluster_service.py`

**Used in:**
- Similar Games — returns projects from the same content cluster as the viewed game
- For You recommendations — projects in the same cluster as liked/created/played games get +1.0 score bonus

**Details:**
- Max 15 clusters, auto-reduced for smaller datasets (`min(15, projects // 2)`)
- Minimum 5 projects required
- Input per project: name (×2 weight) + game_type + mechanics + description
- No labels needed — fully unsupervised
- Refits automatically when new projects are added

---

## Search Pipeline

```
User types query
       │
       ▼
Stage 1 — Keyword scoring
          Per-token OR-logic across name, description, game_type, mechanics, framework
          Exact name match +3.0 | word-boundary +1.0 | substring +0.5
       │
       ▼
Stage 2 — Levenshtein fuzzy
          Each token vs every project name word
          Similarity >= 0.75 → fuzzy match
          Catches typos and near-misses
       │
       ▼
Stage 3 — TF-IDF + Logistic Regression
          Predicts genre from query (confidence >= 0.50)
          Adds all public projects of predicted genre not found in Stage 1/2
       │
       ▼
Merged results — Keyword > Fuzzy > ML priority
```

---

## Recommendation Pipeline

```
User signals
       │
       ├── Created games    × 3.0
       ├── Liked games      × 2.0
       ├── Played games     × 1.5
       └── Searched genres  × 1.0 × confidence
       │
       ▼
Preference vector  { platformer: 7.5, survival: 3.0, ... }
       │
       ▼
K-Means cluster bonus
       Find clusters of liked/created/played games
       Projects in same cluster → +1.0 bonus
       │
       ▼
Final score = genre_score + cluster_bonus
Ranked by (score DESC, likes DESC)
Top 10 returned as For You
```

---

## File Reference

| File | Algorithm | Role |
|---|---|---|
| `backend/app/ml/classifier.py` | TF-IDF + Logistic Regression | Genre prediction |
| `backend/app/ml/cluster_service.py` | TF-IDF + K-Means | Content clustering |
| `backend/app/ml/trainer.py` | Logistic Regression | Model retraining |
| `backend/app/services/search_service.py` | Levenshtein | Fuzzy search |
| `backend/app/services/recommendation_service.py` | K-Means (cluster bonus) | For You scoring |
| `backend/app/ml/models/game_type_classifier.pkl` | — | Saved LR model |
| `backend/app/ml/models/vectorizer.pkl` | — | Saved TF-IDF vectorizer |
| `backend/app/ml/training_data/game_prompts.json` | — | LR training data |
