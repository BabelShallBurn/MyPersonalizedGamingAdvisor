# YourPersonalizedGamingAdvisor

## Beschreibung

YourPersonalizedGamingAdvisor ist eine FastAPI-basierte Webanwendung, die es Benutzern ermöglicht, ihre persönliche Videospielebibliothek in einer PostgreSQL-Datenbank zu verwalten. Benutzer können Spiele mit Details wie Name, Genre, Altersfreigabe und Systemanforderungen speichern. Basierend auf der vorhandenen Bibliothek generiert die Anwendung personalisierte Empfehlungen für neue Spiele, die den Vorlieben des Benutzers entsprechen.

Das Projekt integriert Daten aus Steam über die Steam-API, um zusätzliche Informationen zu Spielen zu sammeln und Empfehlungen zu verbessern.

## Features

- **Spielebibliothek verwalten**: Fügen Sie Spiele hinzu, bearbeiten und entfernen Sie Einträge in Ihrer persönlichen Bibliothek.
- **Detaillierte Spielinformationen**: Speichern Sie Metadaten wie Genre, Altersfreigabe, Systemanforderungen und mehr.
- **Personalisierte Empfehlungen**: Erhalten Sie Vorschläge für neue Spiele basierend auf Ihren gespeicherten Titeln.
- **Steam-Integration**: Automatische Abfrage von Spielinformationen über die Steam-API.
- **RESTful API**: Vollständige API für die Interaktion mit der Anwendung.
- **PostgreSQL-Datenbank**: Robuste Datenspeicherung für Benutzerdaten und Spieleinformationen.

## Technologien

- **Backend**: FastAPI (Python)
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
   Führen Sie das Datenbank-Initialisierungsskript aus:
   ```bash
   python database/init.py
   ```

## Verwendung

1. **Anwendung starten**:
   ```bash
   uvicorn main:app --reload
   ```
   Die API ist dann unter `http://localhost:8000` verfügbar.

2. **API-Dokumentation**:
   Besuchen Sie `http://localhost:8000/docs` für die interaktive Swagger-Dokumentation.

3. **Spiele hinzufügen**:
   Verwenden Sie die API-Endpunkte, um Spiele zu Ihrer Bibliothek hinzuzufügen. Zum Beispiel:
   ```bash
   curl -X POST "http://localhost:8000/games/" -H "Content-Type: application/json" -d '{"name": "The Witcher 3", "genre": "RPG", "age_rating": "18+", "requirements": "High-end PC"}'
   ```

4. **Empfehlungen erhalten**:
   Rufen Sie den Empfehlungs-Endpunkt auf, um personalisierte Vorschläge zu bekommen:
   ```bash
   curl "http://localhost:8000/recommendations/"
   ```

## API-Endpunkte (Übersicht)

- `GET /games/`: Alle Spiele in der Bibliothek abrufen
- `POST /games/`: Neues Spiel hinzufügen
- `GET /games/{id}`: Einzelnes Spiel abrufen
- `PUT /games/{id}`: Spiel aktualisieren
- `DELETE /games/{id}`: Spiel löschen
- `GET /recommendations/`: Empfehlungen basierend auf der Bibliothek erhalten

Für detaillierte Informationen siehe die API-Dokumentation unter `/docs`.

## Beitrag

Beiträge sind willkommen! Bitte öffnen Sie ein Issue oder einen Pull Request auf GitHub.

## Lizenz

Dieses Projekt ist unter der MIT-Lizenz lizenziert. Siehe [LICENSE](LICENSE) für Details.
