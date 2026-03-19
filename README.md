# YourPersonalizedGamingAdvisor

## Beschreibung

YourPersonalizedGamingAdvisor ist eine Python-Anwendung, die es Benutzern ermöglicht, ihre persönliche Videospielebibliothek in einer PostgreSQL-Datenbank zu verwalten und personalisierte Empfehlungen zu erhalten. Benutzer können Spiele mit Details wie Name, Genre, Altersfreigabe und Systemanforderungen speichern. Basierend auf der vorhandenen Bibliothek generiert die Anwendung passende Vorschläge.

Das Projekt integriert Daten aus Steam über die Steam-API, um zusätzliche Informationen zu Spielen zu sammeln und Empfehlungen zu verbessern. Zusätzlich gibt es eine CLI für die interaktive Beratung.

## Features

- **Spielebibliothek verwalten**: Fügen Sie Spiele hinzu, bearbeiten und entfernen Sie Einträge in Ihrer persönlichen Bibliothek.
- **Detaillierte Spielinformationen**: Speichern Sie Metadaten wie Genre, Altersfreigabe, Systemanforderungen und mehr.
- **Personalisierte Empfehlungen**: Erhalten Sie Vorschläge für neue Spiele basierend auf Ihren gespeicherten Titeln.
- **Steam-Integration**: Automatische Abfrage von Spielinformationen über die Steam-API.
- **CLI-Chat**: Interaktiver Chat für Empfehlungen und Bibliotheksverwaltung.
- **PostgreSQL-Datenbank**: Robuste Datenspeicherung für Benutzerdaten und Spieleinformationen.

## Technologien

- **Backend**: Python
- **Datenbank**: PostgreSQL
- **ORM**: SQLModel, SQLAlchemy
- **API-Integration**: Steam Web API
- **Entwicklungsumgebung**: Python 3.8+, Jupyter Notebook für Prototyping

## Voraussetzungen

- Python 3.8 oder höher
- PostgreSQL-Datenbank
- Steam API Key (für Steam-Integration)

## Installation

1. **Repository klonen**:
   ```bash
   git clone https://github.com/yourusername/YourPersonalizedGamingAdvisor.git
   cd YourPersonalizedGamingAdvisor
   ```

2. **Virtuelle Umgebung erstellen und aktivieren**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Auf Windows: venv\Scripts\activate
   ```

3. **Abhängigkeiten installieren**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Umgebungsvariablen konfigurieren**:
   Erstellen Sie eine `.env`-Datei im Projektverzeichnis mit folgenden Variablen:
   ```
   DATABASE_URL=postgresql://username:password@localhost:5432/gaming_advisor
   STEAM_API_KEY=your_steam_api_key_here
   ```

## Datenbank-Setup

1. **PostgreSQL installieren und starten** (falls nicht bereits geschehen).

2. **Datenbank erstellen**:
   ```sql
   CREATE DATABASE gaming_advisor;
   ```

3. **Tabellen initialisieren**:
   Führen Sie die Tabellenerstellung aus:
   ```bash
   python create_tables.py
   ```

4. **Embedding-Tabelle erstellen** (optional, falls empfohlen/benötigt):
   ```bash
   python create_game_embedding_table.py
   ```

## Verwendung

1. **CLI-Chat starten**:
   ```bash
   python -m cli.chat_cli
   ```
2. **Embeddings vorab berechnen** (optional, kann Initiallauf beschleunigen):
   ```bash
   python scripts/precompute_game_embeddings.py --batch-size 500
   ```

## Projektstruktur (Auszug)

```
gaming_advisor/
  config.py
  db/
    engine.py
    data_handling.py
    models.py
  llm/
    routing.py
  recommender/
    scorer.py
  schemas/
services/
  chat_service.py
cli/
  chat_cli.py
scripts/
  precompute_game_embeddings.py
```

## Beitrag

Beiträge sind willkommen! Bitte öffnen Sie ein Issue oder einen Pull Request auf GitHub.

## Lizenz

Dieses Projekt ist unter der MIT-Lizenz lizenziert. Siehe [LICENSE](LICENSE) für Details.
