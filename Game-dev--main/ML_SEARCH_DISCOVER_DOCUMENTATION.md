# ML Model Documentation for Search and Discover

## 1. Scope

This document explains the machine-learning-related behavior implemented in the `Game-dev--main` project for:

- search over user projects
- search over public projects in Discover
- personalized "For You" recommendations in Discover

It is based on the current code in:

- `backend/app/ml/train_classifier.py`
- `backend/app/ml/classifier.py`
- `backend/app/ml/trainer.py`
- `backend/app/services/search_service.py`
- `backend/app/services/recommendation_service.py`
- `backend/app/services/ml_feedback.py`
- `backend/app/api/v1/routes/projects.py`
- `backend/app/api/v1/routes/ai.py`
- `frontend/src/pages/Discover.jsx`

## 2. Executive Summary

The project uses one real trained ML model and two ML-assisted product features built around it.

### 2.1 The actual trained model

The trained model is a **supervised multiclass text classifier** that predicts a `game_type` from a short natural-language prompt.

Pipeline:

1. Convert text into TF-IDF features at the word level and character level.
2. Concatenate those features with `FeatureUnion`.
3. Train a `LogisticRegression` classifier on top of those features.

So this is **not** a neural network, LLM fine-tune, embedding model, vector database, or deep recommender system.

It is a classical ML pipeline:

- `TF-IDF (word n-grams + character n-grams)`
- `Logistic Regression`

### 2.2 How Search uses ML

Search is a **hybrid system**:

- Stage 1: deterministic keyword scoring
- Stage 2: classifier-based semantic-ish expansion by predicting the query's `game_type`

The classifier is only used when confidence is high enough.

### 2.3 How Discover uses ML

Discover has two separate behaviors:

- Public search in Discover uses the same hybrid search service as project search.
- The "For You" section uses a **rule-based recommendation engine**, not a second trained model.

The recommendation engine uses:

- game types the user created
- game types the user liked
- game types inferred from the user's past searches

So Discover is "ML-powered" because it consumes classifier outputs, but the recommender itself is a weighted scoring heuristic, not a learned recommender model.

## 3. What ML Model Is Used

## 3.1 Model family

The main ML model is defined in [`backend/app/ml/train_classifier.py`](/d:/Game-dev-/Game-dev--main/backend/app/ml/train_classifier.py) and loaded in [`backend/app/ml/classifier.py`](/d:/Game-dev-/Game-dev--main/backend/app/ml/classifier.py).

Model type:

- supervised learning
- multiclass text classification
- linear classifier
- bag-of-ngrams representation

Concrete implementation:

- `TfidfVectorizer` for word n-grams
- `TfidfVectorizer` for character n-grams
- `FeatureUnion` to combine both
- `LogisticRegression` as classifier

Relevant implementation points:

- training entry: [`backend/app/ml/train_classifier.py:100`](/d:/Game-dev-/Game-dev--main/backend/app/ml/train_classifier.py:100)
- word TF-IDF: [`backend/app/ml/train_classifier.py:122`](/d:/Game-dev-/Game-dev--main/backend/app/ml/train_classifier.py:122)
- char TF-IDF: [`backend/app/ml/train_classifier.py:132`](/d:/Game-dev-/Game-dev--main/backend/app/ml/train_classifier.py:132)
- classifier: [`backend/app/ml/train_classifier.py:146`](/d:/Game-dev-/Game-dev--main/backend/app/ml/train_classifier.py:146)

## 3.2 Why two TF-IDF vectorizers are used

The pipeline intentionally combines two views of the same text.

### Word-level TF-IDF

Configuration:

- analyzer: `word`
- `ngram_range=(1, 2)`

Purpose:

- captures normal words and short phrases
- helps understand phrases like:
  - `tower defense`
  - `space invaders`
  - `match 3`
  - `top down`

### Character-level TF-IDF

Configuration:

- analyzer: `char_wb`
- `ngram_range=(2, 4)`

Purpose:

- handles spelling variation and typos
- helps with inputs like:
  - `platfomer`
  - `flapy bird`
  - `towr defens`

This is one of the strongest design choices in the project. It gives typo robustness without needing embeddings or a spell-correction pipeline.

## 3.3 Class labels

The current training dataset declares **17 game types** in [`backend/app/ml/training_data/game_prompts.json:2`](/d:/Game-dev-/Game-dev--main/backend/app/ml/training_data/game_prompts.json:2):

- `platformer`
- `shooter`
- `racing`
- `puzzle`
- `rpg`
- `tower_defense`
- `flappy`
- `snake`
- `space_shooter`
- `fighting`
- `survival`
- `topdown`
- `arcade`
- `clicker`
- `rhythm`
- `sports`
- `simulation`

Important note:

Some older comments/tests still talk about 13 game types, but the dataset and saved model artifact now clearly include newer classes such as `clicker`, `rhythm`, `sports`, and `simulation`. The current implementation should be understood as a **17-class classifier**.

## 4. Training Data

## 4.1 Source dataset

Base training data lives in [`backend/app/ml/training_data/game_prompts.json`](/d:/Game-dev-/Game-dev--main/backend/app/ml/training_data/game_prompts.json).

The file describes itself as:

- version `5.0`
- "1000+ examples"
- examples covering slang, typos, metaphors, feature descriptions, and colloquial prompts

From the file contents, the current raw dataset contains **951 labeled examples**.

## 4.2 Class distribution

Raw label counts in the JSON file:

- `platformer`: 85
- `arcade`: 82
- `puzzle`: 68
- `rpg`: 66
- `flappy`: 57
- `shooter`: 55
- `survival`: 55
- `tower_defense`: 55
- `racing`: 53
- `space_shooter`: 52
- `topdown`: 52
- `fighting`: 50
- `snake`: 48
- `simulation`: 45
- `clicker`: 43
- `sports`: 43
- `rhythm`: 42

Observations:

- the dataset is fairly balanced for a hand-built intent classifier
- `platformer` and `arcade` are the largest classes
- `rhythm`, `sports`, and `clicker` are the smallest classes
- no class is extremely underrepresented

## 4.3 Example data

Examples from the dataset:

### Platformer

- `make a mario style game`
- `something like sonic but simpler`
- `side scroller where you avoid obstacles and collect stars`
- `platfomer`

### Flappy

- `game where a bird flies through pipes`
- `tap to fly through obstacles`
- `flapy bird`

### Tower defense

- `build a tower defense game with archers`
- `hold the line against enemy waves`

### Puzzle

- `match 3 puzzle game`
- `match tiles to clear the board`

### RPG

- `rpg with dungeons and loot`
- `a knight explores dungeons and levels up`

This is important because the classifier is trained on **query-like natural language**, not full game design documents. It is optimized for prompt interpretation.

## 5. How the Model Is Trained

## 5.1 Training workflow

The main training script is [`backend/app/ml/train_classifier.py`](/d:/Game-dev-/Game-dev--main/backend/app/ml/train_classifier.py).

Training steps:

1. Load raw prompt-label pairs from JSON.
2. Apply lightweight data augmentation.
3. Split into train/test sets.
4. Train the TF-IDF + Logistic Regression pipeline.
5. Evaluate on held-out test data.
6. Run 5-fold cross-validation.
7. Save the fitted pipeline to disk.

## 5.2 Train/test split

The code uses:

- `test_size=0.15`
- `random_state=42`
- `stratify=labels`

Meaning:

- 85% training
- 15% test
- class balance preserved in the split

Reference: [`backend/app/ml/train_classifier.py:107`](/d:/Game-dev-/Game-dev--main/backend/app/ml/train_classifier.py:107)

## 5.3 Data augmentation

The project uses simple local augmentation in [`backend/app/ml/train_classifier.py:58`](/d:/Game-dev-/Game-dev--main/backend/app/ml/train_classifier.py:58):

- capitalize the first letter of each prompt
- replace the first matching token with a synonym from a tiny dictionary

Synonym dictionary:

- `make` -> `create`, `build`, `generate`, `design`
- `game` -> `clone`, `project`, `prototype`
- `simple` -> `basic`, `easy`, `minimal`
- `a` -> `an`, `the`

Purpose:

- increase wording variation
- reduce brittleness to phrasing changes
- expand data without external APIs

This is basic augmentation, but it matches the problem well because user prompts are short and phrasing-sensitive.

## 5.4 Training algorithm details

Word TF-IDF settings:

- `ngram_range=(1, 2)`
- `min_df=1`
- `max_df=0.95`
- `sublinear_tf=True`
- `strip_accents="unicode"`
- `token_pattern=r"\w{1,}"`

Character TF-IDF settings:

- `ngram_range=(2, 4)`
- `min_df=1`
- `max_df=0.95`
- `sublinear_tf=True`
- `strip_accents="unicode"`
- `analyzer="char_wb"`

Classifier settings:

- `C=5.0`
- `max_iter=1000`
- `solver="lbfgs"`
- `random_state=42`

Interpretation:

- `C=5.0` means somewhat lighter regularization than the default
- `max_iter=1000` helps convergence on sparse text features
- `lbfgs` is standard for logistic regression with dense optimization logic
- with many classes, this behaves as a multiclass logistic classifier

## 5.5 Model artifact

The trained pipeline is saved as:

- [`backend/app/ml/models/game_type_classifier.pkl`](/d:/Game-dev-/Game-dev--main/backend/app/ml/models/game_type_classifier.pkl)

The feature block is also saved separately as:

- [`backend/app/ml/models/vectorizer.pkl`](/d:/Game-dev-/Game-dev--main/backend/app/ml/models/vectorizer.pkl)

The saved pipeline already contains both feature extraction and classification, so inference only needs one `pickle.load(...)`.

## 6. How Inference Works

Inference is implemented in [`backend/app/ml/classifier.py`](/d:/Game-dev-/Game-dev--main/backend/app/ml/classifier.py).

Main runtime entry:

- [`backend/app/ml/classifier.py:76`](/d:/Game-dev-/Game-dev--main/backend/app/ml/classifier.py:76)

## 6.1 Runtime flow

When `predict_game_type(prompt)` is called:

1. Load the pickled pipeline once and cache it.
2. Call `pipeline.predict([prompt])` for the best class.
3. Call `pipeline.predict_proba([prompt])` for per-class probabilities.
4. Sort probabilities descending.
5. Return:
   - `game_type`
   - `confidence`
   - `needs_clarification`
   - `top3`
   - `source`

## 6.2 Output format

Typical output shape:

```json
{
  "game_type": "platformer",
  "confidence": 0.94,
  "needs_clarification": false,
  "top3": [
    {"game_type": "platformer", "confidence": 0.94},
    {"game_type": "arcade", "confidence": 0.03},
    {"game_type": "topdown", "confidence": 0.02}
  ],
  "source": "ml_model"
}
```

## 6.3 Confidence threshold

The code uses a central threshold:

- `CONFIDENCE_THRESHOLD = 0.50`

Reference: [`backend/app/ml/classifier.py:31`](/d:/Game-dev-/Game-dev--main/backend/app/ml/classifier.py:31)

This threshold controls:

- whether a prediction is considered strong enough
- whether search should use the classifier result
- whether search history is stored as a personalization signal

## 6.4 Clarification logic

The model may still produce a class for vague text, but the system can choose not to trust it fully.

`needs_clarification` becomes true when:

- classifier confidence is below `0.50`, or
- the prompt has only one real word and the predicted class is `arcade`

This prevents generic prompts like `fun`, `cool`, or `game` from acting like precise semantic intent.

## 6.5 Fallback behavior

If the trained model file is missing or prediction fails, the code falls back to a hand-written keyword classifier in:

- [`backend/app/ml/classifier.py:137`](/d:/Game-dev-/Game-dev--main/backend/app/ml/classifier.py:137)

That fallback maps words like:

- `mario`, `jump`, `platform` -> `platformer`
- `bird`, `pipes`, `flappy` -> `flappy`
- `quest`, `dungeon`, `pokemon` -> `rpg`

This means the feature degrades gracefully instead of hard-failing.

## 7. How the Model Classifies Text

## 7.1 Conceptual explanation

For a prompt like:

`make a mario style game`

the model does not understand the sentence like a large language model. Instead, it converts the text into sparse weighted features.

Examples of helpful word features:

- `mario`
- `style`
- `mario style`

Examples of helpful character features:

- `ma`
- `mar`
- `mari`
- `rio`

During training, the classifier learns weights such as:

- strong positive weight from `mario` toward `platformer`
- positive weight from `pipes` toward `flappy`
- positive weight from `match 3` toward `puzzle`
- positive weight from `quest`, `loot`, `dungeon` toward `rpg`

At inference time, each class receives a score based on the active features, then probabilities are produced. The highest-probability label becomes the predicted `game_type`.

## 7.2 Why typos still work

Suppose the user types:

`platfomer game`

Word-level features may be weak because `platfomer` is misspelled.

Character-level features are still useful because substrings like:

- `pl`
- `pla`
- `plat`
- `tfo`
- `for`

overlap with `platformer`.

That is why the code comments explicitly say the char-level model handles typo robustness.

## 7.3 Example classification walkthrough

Input:

`tap to fly through obstacles`

Likely activated signals:

- word features: `fly`, `obstacles`
- phrase features: `tap to`, `tap to fly`
- char features overlapping with training examples for flappy-style prompts

Expected top classes:

1. `flappy`
2. possibly `arcade`
3. possibly `platformer` or `shooter` depending on the rest of the vocabulary

Why `flappy` wins:

- the training set contains many "bird flies through pipes", "tap to fly", and obstacle-avoidance examples
- those examples create high positive weights for the `flappy` class

## 7.4 Example with ambiguous input

Input:

`something cool`

What happens:

1. the classifier still returns some class
2. confidence is likely low
3. `needs_clarification` becomes `true`
4. hybrid search suppresses ML expansion for that query

This is an important safety check. It stops the product from overcommitting on vague inputs.

## 8. How Search Uses the Model

The hybrid search implementation is in [`backend/app/services/search_service.py`](/d:/Game-dev-/Game-dev--main/backend/app/services/search_service.py).

## 8.1 Search architecture

The search service has two stages.

### Stage 1: Keyword scoring

The query is tokenized with `_tokenize(...)`:

- lowercase
- extract alphanumeric tokens
- remove stop words
- remove single-character tokens

Reference: [`backend/app/services/search_service.py:51`](/d:/Game-dev-/Game-dev--main/backend/app/services/search_service.py:51)

Each project is then scored across multiple fields:

- `name` weight `1.0`
- `description` weight `0.6`
- `game_type` weight `0.4`
- `mechanics` weight `0.3`
- `framework` weight `0.2`

Reference: [`backend/app/services/search_service.py:37`](/d:/Game-dev-/Game-dev--main/backend/app/services/search_service.py:37)

This is purely deterministic scoring, not ML.

### Stage 2: ML classifier expansion

If the query is at least 3 characters:

1. call `predict_game_type(query)`
2. read `predicted_game_type` and `classifier_confidence`
3. if confidence passes threshold and no clarification is needed:
   - fetch projects whose `design_doc.game_type` matches the predicted type

Reference:

- classifier call: [`backend/app/services/search_service.py:162`](/d:/Game-dev-/Game-dev--main/backend/app/services/search_service.py:162)
- ML score multiplier: [`backend/app/services/search_service.py:171`](/d:/Game-dev-/Game-dev--main/backend/app/services/search_service.py:171)

## 8.2 Merge behavior

Keyword results always have priority.

Merge logic:

1. start with keyword hits
2. add ML hits only if they were not already matched by keyword
3. sort descending by score

This gives the product a useful behavior:

- explicit lexical matches rank first
- semantically related same-genre projects can still appear
- duplicates are avoided

## 8.3 Why this is called "hybrid search"

It is called hybrid because it combines:

- lexical retrieval
- classifier-driven class expansion

It is **not** hybrid in the vector-search sense. There is no embedding index, cosine similarity, ANN lookup, or semantic vector database.

## 8.4 Worked search example

Imagine these stored projects:

| Project | Name | Game type | Description |
|---|---|---|---|
| P1 | Mario Adventure | platformer | Jump across platforms and collect coins |
| P2 | Pipe Bird | flappy | Tap to fly through pipes |
| P3 | Castle Quest | rpg | Explore dungeons and level up |
| P4 | Neon Jumper | platformer | Side-scrolling jump challenge |

User query:

`jumping side scroll`

### Stage 1 keyword results

Tokenization might produce:

- `jumping`
- `side`
- `scroll`

Keyword matches:

- P1 description may match `jump`
- P4 description may match `side-scrolling` and `jump`

So P1 and P4 likely become keyword hits.

### Stage 2 ML results

The classifier likely predicts:

- `platformer`

Then the service finds all projects with `design_doc.game_type == "platformer"`.

That means:

- P1 and P4 are genre matches

But because they already matched by keyword, ML does not duplicate them.

If there were another platformer project with no lexical overlap, it could still be added as an ML-only hit.

That is the practical value of the classifier inside search.

## 9. How Discover Uses the Model

Discover behavior is split between backend routes and the frontend page.

Backend:

- [`backend/app/api/v1/routes/projects.py:120`](/d:/Game-dev-/Game-dev--main/backend/app/api/v1/routes/projects.py:120)
- [`backend/app/api/v1/routes/projects.py:162`](/d:/Game-dev-/Game-dev--main/backend/app/api/v1/routes/projects.py:162)

Frontend:

- [`frontend/src/pages/Discover.jsx`](/d:/Game-dev-/Game-dev--main/frontend/src/pages/Discover.jsx)

## 9.1 Public Discover search

When the Discover page has a search query:

1. frontend calls `/api/v1/projects/discover?q=...`
2. backend loads public projects
3. backend runs the same `search_service.search(...)`
4. backend returns only the project list to the frontend

Important detail:

The backend search response contains metadata like:

- `predicted_game_type`
- `classifier_confidence`
- `ml_hits`

But the Discover route strips that and only returns projects. So the current UI does not explain why an item matched.

## 9.2 Personalized "For You" recommendations

Recommendations are generated by [`backend/app/services/recommendation_service.py`](/d:/Game-dev-/Game-dev--main/backend/app/services/recommendation_service.py).

This service does **not** train a model. It builds a preference vector with fixed weights.

Weights:

- created project game type: `3.0`
- liked project game type: `2.0`
- searched game type: `1.0 * classifier_confidence`

Reference: [`backend/app/services/recommendation_service.py:16`](/d:/Game-dev-/Game-dev--main/backend/app/services/recommendation_service.py:16)

## 9.3 Recommendation algorithm

For each user:

1. inspect the game types they created
2. inspect the game types they liked
3. inspect recent search history events
4. accumulate a score per `game_type`
5. score public candidate projects by that preference vector
6. break ties with project likes

Cold-start behavior:

- if the user has no signals, return the most-liked public projects

## 9.4 Example recommendation vector

Suppose a user has:

- created 2 platformers
- liked 1 puzzle game
- searched:
  - `mario style game` -> `platformer`, confidence `0.92`
  - `jumping side scroll` -> `platformer`, confidence `0.81`
  - `match 3 gems` -> `puzzle`, confidence `0.88`

Preference vector:

- `platformer = 2 * 3.0 + 0.92 + 0.81 = 7.73`
- `puzzle = 1 * 2.0 + 0.88 = 2.88`

A public project with `game_type = platformer` will rank above a puzzle project unless the tie-breakers or exclusions change the candidate pool.

## 9.5 Important conclusion about Discover

The "For You" feature is personalized and partly ML-driven, but the recommender itself is a **weighted rules engine over game types**, not a separately trained classifier/ranker.

## 10. How the Model Learns After Deployment

The project also includes dynamic retraining.

Key files:

- [`backend/app/services/ml_feedback.py`](/d:/Game-dev-/Game-dev--main/backend/app/services/ml_feedback.py)
- [`backend/app/ml/trainer.py`](/d:/Game-dev-/Game-dev--main/backend/app/ml/trainer.py)

## 10.1 How new training examples are collected

When an AI-generated design is produced, the backend stores the confirmed `game_type` as a training signal.

Reference:

- signal capture: [`backend/app/api/v1/routes/ai.py:142`](/d:/Game-dev-/Game-dev--main/backend/app/api/v1/routes/ai.py:142)

The function `record_game_creation(...)` saves:

- original user prompt
- confirmed `game_type`
- confidence

into storage as ML examples.

## 10.2 Acceptance threshold for training signals

Only examples with confidence `>= 0.70` are accepted into retraining.

Reference:

- [`backend/app/services/ml_feedback.py`](/d:/Game-dev-/Game-dev--main/backend/app/services/ml_feedback.py)

This helps avoid feeding noisy labels into future retrains.

## 10.3 Auto-retrain threshold

Retraining is triggered when pending examples reach:

- `RETRAIN_THRESHOLD = 50`

Reference:

- [`backend/app/services/ml_feedback.py:23`](/d:/Game-dev-/Game-dev--main/backend/app/services/ml_feedback.py:23)

## 10.4 Retraining pipeline

The retrainer:

1. loads base JSON examples
2. fetches user-contributed examples from storage
3. filters for confidence `>= 0.70`
4. merges them with base data
5. augments data again
6. retrains the same TF-IDF + LogisticRegression pipeline
7. saves new `.pkl` files
8. hot-reloads the runtime classifier
9. marks examples as trained

Reference:

- retrain entry: [`backend/app/ml/trainer.py:110`](/d:/Game-dev-/Game-dev--main/backend/app/ml/trainer.py:110)

This is a nice production-minded design for a small app: simple, explainable, and cheap to run.

## 11. End-to-End Data Flow

## 11.1 Search flow

1. User enters a search query.
2. Frontend calls `/api/v1/projects/search` or `/api/v1/projects/discover`.
3. Backend tokenizes and keyword-scores projects.
4. Backend predicts query `game_type` with the classifier.
5. If confidence is high, same-genre projects are added.
6. Results are merged and sorted.
7. For authenticated project search, high-confidence search events are stored for future recommendation use.

Relevant search-history persistence:

- [`backend/app/api/v1/routes/projects.py:88`](/d:/Game-dev-/Game-dev--main/backend/app/api/v1/routes/projects.py:88)

## 11.2 Recommendation flow

1. User visits Discover.
2. Frontend requests `/api/v1/projects/recommendations`.
3. Backend fetches:
   - user projects
   - public projects
   - liked project ids
   - search history
4. Recommendation service builds a preference vector over game types.
5. Public projects are ranked by matching `game_type`.
6. Top projects are returned to the UI.

## 12. What the Model Is Good At

Strengths of this implementation:

- short prompt classification
- typo robustness
- explainable behavior
- cheap training and inference
- no dependency on remote ML APIs for classification
- easy hot-retraining with user-confirmed data

Good fit for:

- intent recognition
- genre detection
- light semantic expansion in search

## 13. Limitations

Important limitations of the current design:

- it predicts only one coarse label: `game_type`
- it does not model multiple simultaneous genres well
- it does not use full semantic embeddings
- it does not rank projects by deep semantic similarity
- it does not personalize recommendations beyond fixed weighted genre preferences
- it may over-predict broad buckets like `arcade` when the query is vague
- recommendation quality depends heavily on correct `design_doc.game_type` labeling

## 14. Practical Bottom Line

If someone asks, "What ML is implemented in search and Discover?", the most accurate short answer is:

> The project uses a supervised TF-IDF + Logistic Regression multiclass text classifier to infer a game's genre from natural-language prompts. Search combines deterministic keyword matching with this classifier's predicted genre. Discover recommendations then reuse those genre signals in a weighted preference engine rather than a separate trained recommender model.

## 15. Key Code References

- Training script: [`backend/app/ml/train_classifier.py`](/d:/Game-dev-/Game-dev--main/backend/app/ml/train_classifier.py)
- Runtime classifier: [`backend/app/ml/classifier.py`](/d:/Game-dev-/Game-dev--main/backend/app/ml/classifier.py)
- Dynamic retraining: [`backend/app/ml/trainer.py`](/d:/Game-dev-/Game-dev--main/backend/app/ml/trainer.py)
- Hybrid search: [`backend/app/services/search_service.py`](/d:/Game-dev-/Game-dev--main/backend/app/services/search_service.py)
- Recommendations: [`backend/app/services/recommendation_service.py`](/d:/Game-dev-/Game-dev--main/backend/app/services/recommendation_service.py)
- ML feedback ingestion: [`backend/app/services/ml_feedback.py`](/d:/Game-dev-/Game-dev--main/backend/app/services/ml_feedback.py)
- Project/discover routes: [`backend/app/api/v1/routes/projects.py`](/d:/Game-dev-/Game-dev--main/backend/app/api/v1/routes/projects.py)
- AI route that captures new examples: [`backend/app/api/v1/routes/ai.py`](/d:/Game-dev-/Game-dev--main/backend/app/api/v1/routes/ai.py)
- Discover UI: [`frontend/src/pages/Discover.jsx`](/d:/Game-dev-/Game-dev--main/frontend/src/pages/Discover.jsx)
