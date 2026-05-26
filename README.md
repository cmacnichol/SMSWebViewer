# SMS Web Viewer

A modern, self-hosted web application that acts as a robust backend data pipeline and frontend interface for your [SMS Backup & Restore](https://play.google.com/store/apps/details?id=com.riteshsahu.SMSBackupRestore) XML files. It synchronizes with your Google Drive (or accepts manual uploads), parses your backups, and presents them in a beautiful, searchable, chat-like UI.

![SMS Web Viewer](https://img.shields.io/badge/Status-Active-success) ![Docker](https://img.shields.io/badge/Docker-Enabled-blue) ![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688)

## Quick Start

### Docker

Run the latest version directly from Docker Hub:
```bash
docker run -d \
  -p 8000:8000 \
  -v $(pwd)/data:/data \
  --name smsviewer \
  elevarion/smsviewer:latest
```

### Docker Compose

Create a `docker-compose.yml` file:
```yaml
services:
  smsviewer:
    image: elevarion/smsviewer:latest
    ports:
      - "8000:8000"
    volumes:
      - ./data:/data
    restart: unless-stopped
```
Then run `docker-compose up -d`.

## Features

- **Automated Sync Pipeline** - In-process scheduler automatically pulls the latest XML backups directly from your Google Drive. Schedule it daily, hourly, or run it manually.
- **Dynamic OAuth Integration** - Securely connect your Google account via a standard OAuth2 flow right from the UI.
- **Fast, Deduplicated Ingestion** - Uses a normalized SQLite database to deduplicate messages and calls based on content hashes. Works seamlessly with multi-GB backups.
- **Global Full-Text Search** - Instantly search for keywords across all your contacts and conversations simultaneously.
- **Manual XML Imports** - Easily upload XML files directly from the web interface if you don't want to use Google Drive sync.
- **Export Capabilities** - Export conversations to CSV, JSON, or beautifully formatted PDFs.
- **AI-Ready (MCP Enabled)** - Built with an integrated Model Context Protocol (FastMCP) server to expose your database to external AI agents securely.
- **Full Privacy** - No telemetry. Operates entirely on your local machine using your own Google API credentials.

## Tech Stack

- **Backend**: Python 3.11 with FastAPI and SQLAlchemy
- **Frontend**: Vanilla Javascript, HTML5, and Bootstrap 5.3
- **Database**: SQLite (stores messages, calls, configuration, and sync states)

## Data Persistence

The Docker setup uses a bind mount to persist your database.
- Host path: `./data`
- Container path: `/data`

Inside this folder, the application will create `smsviewer.db` (your messages and calls) and `sync_state.json` (Google Drive sync pointers).

## Google Cloud Platform (GCP) Setup

Because this is a self-hosted application, you need to create your own Google OAuth credentials. This ensures your data remains completely private and you get your own dedicated API quotas.

1. **Create a Project:**
   - Go to the [Google Cloud Console](https://console.cloud.google.com/).
   - Click the project dropdown at the top and select **New Project**. Name it `SMS Web Viewer`.

2. **Enable the Google Drive API:**
   - Navigate to **APIs & Services > Library**.
   - Search for **Google Drive API** and click **Enable**.

3. **Configure the OAuth Consent Screen:**
   - Navigate to **APIs & Services > OAuth consent screen**.
   - Choose **External** or **Internal** and click **Create**.
   - Fill in the required fields. On the **Scopes** page, manually add `https://www.googleapis.com/auth/drive.readonly`.
   - Add your Google email address as a **Test User**.

4. **Create OAuth Credentials:**
   - Navigate to **APIs & Services > Credentials**.
   - Click **Create Credentials** -> **OAuth client ID**.
   - Set the Application type to **Web application**.
   - Under **Authorized redirect URIs**, add: `http://localhost:8000/api/auth/callback`
   - Copy your **Client ID** and **Client Secret**.

## Environment Variables

To use the Google Drive sync feature, you must provide your Google Cloud credentials to the container. You can pass these via an `.env` file or directly in your `docker-compose.yml`:

- `GCP_CLIENT_ID` - Your Google Cloud Client ID (e.g. `*.apps.googleusercontent.com`)
- `GCP_CLIENT_SECRET` - Your Google Cloud Client Secret
- `OAUTH_REDIRECT_URI` - Must exactly match your GCP setting (default: `http://localhost:8000/api/auth/callback`)
- `DEFAULT_COUNTRY_CODE` - (Optional) Used for normalizing phone numbers (default: `US`)

## Usage Instructions

1. Access the web interface at `http://localhost:8000`.
2. Click the **Settings** gear icon in the top right.
3. Click **Connect Google Drive** and authorize the app. (If you see an "unverified app" warning, click Advanced -> Go to SMS Web Viewer).
4. Once connected, reopen Settings and select your Sync Folder from the dropdown.
5. Choose your Background Sync Schedule (e.g., Every hour, Daily at 2AM).
6. Click **Save Settings** and then click **Sync Now** to run your first ingestion!

## Testing the MCP Server

This application includes a built-in Model Context Protocol (MCP) server.

### Using with AI Assistants (LM Studio, Claude Desktop, VSCode)

Since SMS Web Viewer runs securely inside a Docker container, you can instruct your AI assistant to execute the MCP server directly via `docker exec`.

Add the following to your MCP settings file (e.g., `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "sms-viewer": {
      "command": "docker",
      "args": [
        "exec",
        "-i",
        "smsviewer",
        "python",
        "-c",
        "from app.core.mcp_server import mcp; mcp.run()"
      ]
    }
  }
}
```

Available Tools:
- `query_contacts`: Look up contacts by name or phone number.
- `search_messages`: Perform a full-text search across all messages.
- `get_conversation_context`: Retrieve recent messages with a specific number.
- `get_conversation_text`: Retrieve raw chat logs specifically formatted for LLM summarization.
- `get_communication_frequency`: Get monthly message volume statistics.
- `get_call_stats`: Summarize call history (duration, missed vs. answered).
