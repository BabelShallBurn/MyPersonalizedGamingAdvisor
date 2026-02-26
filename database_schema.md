# Datenbankschema

```mermaid
erDiagram
    USER {
        int id PK
        string name
        string email UK
        string language
        int age
        string platform
        datetime created_at
        datetime updated_at
    }

    GAMES {
        int id PK
        int steam_appid
        string game_name
        string release_date
        int recommendations
        string description
        string genres
        int usk
        decimal price
        string platforms
        datetime created_at
        datetime updated_at
    }

    USER_GAMES {
        int user_id PK, FK
        int game_id PK, FK
        string status
        int rating
        decimal playtime_hours
        datetime created_at
    }

    GAME_SYSTEM_REQUIREMENT {
        int id PK
        int game_id FK
        string platform
        string minimum
        string recommended
        datetime created_at
        datetime updated_at
    }

    USER ||--o{ USER_GAMES : has
    GAMES ||--o{ USER_GAMES : in_library
    GAMES ||--o{ GAME_SYSTEM_REQUIREMENT : has_requirements
```

## Zusätzliche Constraints

- `user.age >= 0`
- `games.usk IN (0, 6, 12, 16, 18)`
- `games.price >= 0`
- `games.recommendations >= 0`
- `user_games.status IN ('owned', 'wishlist', 'playing', 'completed')`
- `user_games.rating IS NULL OR (rating >= 0 AND rating <= 10)`
- `user_games.playtime_hours >= 0`
- `game_system_requirement.platform IN ('pc', 'mac', 'linux')`
- `UNIQUE(game_system_requirement.game_id, game_system_requirement.platform)`

## Hinweise zu Indizes

- `user.email` ist `UNIQUE` + indexiert.
- `games.game_name` ist indexiert.
- `games.steam_appid` ist indexiert.
- `game_system_requirement.game_id` ist indexiert.
