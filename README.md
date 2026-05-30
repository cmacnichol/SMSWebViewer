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
    environment:
      # You can optionally configure these variables here instead of an .env file
      - DATABASE_URL=sqlite+aiosqlite:////data/smsviewer.db
      - APP_HOST=0.0.0.0
      - APP_PORT=8000
      - OAUTH_REDIRECT_URI=http://localhost:8000/api/auth/callback
      - DEFAULT_COUNTRY_CODE=US
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
- **Multi-User Management** - Support for multiple users with configurable permission levels, role-based access control, and password authentication (can be disabled via `AUTH_MODE=NONE`).
- **AI-Ready (MCP Enabled)** - Built with an integrated Model Context Protocol (FastMCP) server to expose your database to external AI agents securely. Generate personal API tokens directly from the UI.
- **Full Privacy** - No telemetry. Operates entirely on your local machine using your own Google API credentials.

## Tech Stack

- **Backend**: Python 3.11 with FastAPI and SQLAlchemy
- **Frontend**: Vanilla Javascript, HTML5, and Bootstrap 5.3
- **Database**: SQLite or PostgreSQL (stores messages, calls, configuration, and sync states)

## Data Persistence

The standalone Docker Compose setup uses a bind mount to persist your local SQLite database.
- Host path: `./data`
- Container path: `/data`

Inside this folder, the application will create `smsviewer.db` (your messages and calls). If using Docker Swarm and PostgreSQL, state is fully externalized and this folder is not required.

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

You can configure the application by passing environment variables either via an `.env` file or by specifying them directly in your `docker-compose.yml` under the `environment:` section.

### Google Drive Sync (Required for Syncing)
- `GCP_CLIENT_ID` - Your Google Cloud Client ID (e.g. `*.apps.googleusercontent.com`).
- `GCP_CLIENT_SECRET` - Your Google Cloud Client Secret.

### Optional Overrides
- `DATABASE_URL` - Connection string for the database (default: `sqlite+aiosqlite:////data/smsviewer.db`). Useful if you wish to connect to an external PostgreSQL database instead of the embedded SQLite.
- `APP_HOST` - The host IP the web server binds to (default: `0.0.0.0`).
- `APP_PORT` - The internal port the web server listens on (default: `8000`).
- `OAUTH_REDIRECT_URI` - The callback URI for Google OAuth. Must exactly match your GCP setting (default: `http://localhost:8000/api/auth/callback`).
- `DEFAULT_COUNTRY_CODE` - The two-letter ISO country code used for normalizing phone numbers (default: `US`).
- `AUTH_MODE` - Set to `BASIC` to enable password-based user authentication, or `NONE` to disable auth (default: `NONE`).
- `SECRET_KEY` - Used for signing JWTs when authentication is enabled. Make sure to change this in production!

## Installation (Docker Compose)

The easiest way to run SMS Web Viewer locally is using Docker Compose.

```bash
docker-compose up -d --build
```
The application will be available at `http://localhost:8000`. By default, it uses a local SQLite database stored in `./data/smsviewer.db`.

## Installation (Docker Swarm / Production)

For production deployments, high availability, and horizontal scaling, SMS Web Viewer fully supports Docker Swarm backed by an external PostgreSQL database. 

A `docker-stack.yml` is provided in the repository.

1. **Initialize Swarm** (if not already running):
   ```bash
   docker swarm init
   ```

2. **Create Docker Secrets**:
   To secure your credentials, define the following Docker secrets:
   ```bash
   echo "your_super_secret_key" | docker secret create secret_key -
   echo "postgresql+asyncpg://postgres:your_db_password@db:5432/smsviewer" | docker secret create database_url -
   
   # Optional: Google OAuth or OIDC secrets
   echo "your_gcp_client_id" | docker secret create gcp_client_id -
   echo "your_gcp_client_secret" | docker secret create gcp_client_secret -
   echo "your_oidc_client_id" | docker secret create oidc_client_id -
   echo "your_oidc_client_secret" | docker secret create oidc_client_secret -
   ```

3. **Deploy the Stack**:
   ```bash
   docker stack deploy -c docker-stack.yml smsviewer
   ```

> **Note on External Databases**: The `docker-stack.yml` includes an optional PostgreSQL `db` service. If you are using a managed database (like AWS RDS), simply comment out the `db` service in `docker-stack.yml` and point your `database_url` secret to the external instance.

## Usage Instructions

1. Access the web interface at `http://localhost:8000`.
2. Click the **Settings** gear icon in the top right.
3. Click **Connect Google Drive** and authorize the app. (If you see an "unverified app" warning, click Advanced -> Go to SMS Web Viewer).
4. Once connected, reopen Settings and select your Sync Folder from the dropdown.
5. Choose your Background Sync Schedule (e.g., Every hour, Daily at 2AM).
6. Click **Save Settings** and then click **Sync Now** to run your first ingestion!

## Testing the MCP Server

This application includes a built-in Model Context Protocol (MCP) server.

### 1. Local Connection (Same Machine)
If your AI assistant is running on the same machine as your Docker container, you can instruct it to execute the MCP server directly via `docker exec`.

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

### 2. Remote Network Connection (via SSH)
If you are hosting SMS Web Viewer on a separate local network server (e.g., a NAS or a Raspberry Pi) and want to connect your local AI assistant to it, you can bridge the `stdio` connection over SSH. Note: You must have passwordless SSH keys configured between your local machine and the server.

```json
{
  "mcpServers": {
    "sms-viewer-remote": {
      "command": "ssh",
      "args": [
        "user@192.168.1.100",
        "docker",
        "exec",
        "-i",
        "smsviewer",
        "python",
        "-c",
        "\"from app.core.mcp_server import mcp; mcp.run()\""
      ]
    }
  }
}
```

### 3. Remote Network Connection (via SSE)
If your AI Client supports **SSE (Server-Sent Events)** natively (such as the official `@modelcontextprotocol/inspector` or Roo Code), you do not need SSH. You can connect directly over HTTP using the global API Token generated by the Default Admin.

- **Transport Type:** `SSE`
- **URL:** `http://192.168.1.100:8000/mcp/sse`
- **Headers:** `Authorization: Bearer mcp_xxxxxx`

### 4. LM Studio Example (SSE)
To connect LM Studio to your SMS Web Viewer's MCP server over the local network using an API Token:

```json
{
  "sms-viewer-sse": {
    "url": "http://127.0.0.1:8000/mcp/sse",
    "headers": {
      "Authorization": "Bearer mcp_YOUR_TOKEN_HERE"
    }
  }
}
```

> **Note for Windows Users**: If you are running Docker Desktop on Windows, use `127.0.0.1` instead of `localhost` in your MCP client's configuration URL. Node.js applications (like LM Studio) often prioritize IPv6 for `localhost`, which will cause connection failures (`fetch failed`) when trying to communicate with Docker's IPv4 port mapping.

---

Available Tools:
- `query_contacts`: Look up contacts by name or phone number.
- `search_messages`: Perform a full-text search across all messages.
- `get_conversation_context`: Retrieve recent messages with a specific number.
- `get_conversation_text`: Retrieve raw chat logs specifically formatted for LLM summarization.
- `get_communication_frequency`: Get monthly message volume statistics.
- `get_call_stats`: Summarize call history (duration, missed vs. answered).
