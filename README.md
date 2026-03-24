# YourPersonalizedGamingAdvisor

YourPersonalizedGamingAdvisor is a Python application for managing a personal game library in PostgreSQL and getting tailored recommendations through a CLI chat. It combines library signals (genres, descriptions, playtime, ratings) with catalog popularity and optional embedding-based similarity for richer suggestions.

## Features

- Manage a personal library with status, rating, and playtime
- CLI chat to add games, update profile data, and request recommendations
- Recommendation scoring based on genres, TF-IDF description similarity, and Steam recommendation volume
- Optional OpenAI embeddings for query-to-description similarity
- Steam API integration module for enriching the game catalog
- PostgreSQL storage with pgvector for embeddings

## Requirements

- Python 3.10+
- PostgreSQL (with the `pgvector` extension)
- OpenAI API key for chat and embeddings
- Steam API key if you want to fetch data from Steam

## Quick Start

1. Clone the repository and create a virtual environment:
   ```bash
   git clone https://github.com/yourusername/YourPersonalizedGamingAdvisor.git
   cd YourPersonalizedGamingAdvisor
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file in the project root:
   ```env
   DATABASE_URL=postgresql://username:password@localhost:5432/gaming_advisor
   OPENAI_API_KEY=your_openai_api_key
   STEAM_API_KEY=your_steam_api_key  # optional
   TEST_USER_EMAIL=you@example.com   # optional default for the CLI prompt
   ```

4. Prepare the database (run once):
   ```sql
   CREATE DATABASE gaming_advisor;
   CREATE EXTENSION IF NOT EXISTS vector;
   ```

5. Create tables:
   ```bash
   python create_tables.py
   ```

6. Load game data into the `games` table (see "Loading Game Data" below).

7. (Optional) Precompute embeddings for faster query matching:
   ```bash
   python scripts/precompute_game_embeddings.py --batch-size 500
   ```

8. Start the CLI chat:
   ```bash
   python -m cli.chat_cli
   ```

## Configuration

Environment variables loaded via `python-dotenv`:

- `DATABASE_URL` (required): PostgreSQL connection string. Importing DB modules without this will raise an error.
- `OPENAI_API_KEY` (required for chat and embeddings)
- `STEAM_API_KEY` (required only for Steam API calls)
- `TEST_USER_EMAIL` (optional, used as the default CLI email)
- `EMBEDDING_MODEL` (optional, default `text-embedding-3-small`)
- `EMBEDDING_BATCH_SIZE` (optional, default `128`)
- `EMBEDDING_MAX_TOKENS` (optional, default `8000`)
- `RERANK_TOP_N` (optional, default `200`)

## Loading Game Data

The recommender expects the `games` table to be populated. There is no built-in import CLI yet, but you can use the Steam integration module and the DB helpers in a small script:

```python
from gaming_advisor.steam import retrieve_app_details
from gaming_advisor.db.data_handling import save_game_details

app = retrieve_app_details(620)  # Portal 2
if app:
    save_game_details(app)
```

You can also build your own import pipeline and store records via `save_game_details()`.

## Usage Tips

- Type `library` in the CLI to list your saved games.
- Use natural language like "I own Hades and Hollow Knight" or "Recommend a cozy RPG".
- Ask for details: "How many hours do I have in Elden Ring?" or "What's my rating for Hades?"

## Tests

Run tests with:

```bash
pytest
```

## Architecture

### System Overview

```mermaid
flowchart TD
    CLI["CLI\nchat_cli.py"]
    CS["ChatService\nchat_service.py"]
    LLM["LLM Routing\nrouting.py"]
    REC["Recommender\nscorer.py"]
    DB["DB Operations\ndata_handling.py"]
    PG[("PostgreSQL\n+ pgvector")]
    STEAM["Steam API\nsteam.py"]
    OAI["OpenAI API"]

    CLI -->|user message| CS
    CS -->|classify intent| LLM
    LLM -->|structured parse| CS
    CS -->|recommendation request| REC
    CS -->|CRUD| DB
    REC -->|query embeddings| OAI
    REC -->|score games| DB
    DB -->|read/write| PG
    STEAM -->|enrich catalog| DB
    LLM -->|chat + parsing| OAI
```

### Database Schema

```mermaid
erDiagram
    User {
        int id PK
        string name
        string email
        string language
        int age
        string platform
    }
    Games {
        int id PK
        int steam_appid
        string title
        string genres
        string description
        float price
        int recommendations
    }
    UserGames {
        int id PK
        int user_id FK
        int game_id FK
        string status
        float rating
        float playtime_hours
    }
    GameEmbedding {
        int id PK
        int game_id FK
        vector embedding
    }
    GameSystemRequirement {
        int id PK
        int game_id FK
        string platform
        string minimum
        string recommended
    }

    User ||--o{ UserGames : owns
    Games ||--o{ UserGames : "owned by"
    Games ||--o| GameEmbedding : "embedded as"
    Games ||--o{ GameSystemRequirement : "requires"
```

### Request Flow: Recommendation

```mermaid
sequenceDiagram
    actor User
    participant CLI
    participant ChatService
    participant LLM
    participant Recommender
    participant DB

    User->>CLI: "Recommend a cozy RPG"
    CLI->>ChatService: handle_user_message()
    ChatService->>LLM: route_user_text()
    LLM-->>ChatService: intent = recommendation
    ChatService->>Recommender: recommend_for_user_request()
    Recommender->>DB: load user library + game catalog
    DB-->>Recommender: genres, descriptions, ratings
    Recommender->>Recommender: score (genre + TF-IDF + embeddings + popularity)
    Recommender-->>ChatService: ranked game list
    ChatService-->>CLI: ChatResult
    CLI-->>User: top recommendations
```

## Project Structure

```
cli/
  chat_cli.py
create_tables.py
create_game_embedding_table.py
gaming_advisor/
  config.py
  db/
    data_handling.py
    engine.py
    models.py
  llm/
    routing.py
  recommender/
    scorer.py
  schemas/
  services/
    chat_service.py
  steam.py
scripts/
  precompute_game_embeddings.py
```

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

## License

This project is licensed under the MIT License. See `LICENSE` for details.
