# SMS Web Viewer

SMS Web Viewer is a containerized, self-hosted web application that acts as a robust backend data pipeline and frontend interface for your [SMS Backup & Restore](https://play.google.com/store/apps/details?id=com.riteshsahu.SMSBackupRestore) XML files. It automatically synchronizes with your Google Drive, parses your text message and call log backups, and presents them in a beautiful, searchable, chat-like UI.

![SMS Web Viewer](https://img.shields.io/badge/Status-Active-success) ![Docker](https://img.shields.io/badge/Docker-Enabled-blue) ![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688)

## Features

- **Automated Sync Pipeline:** In-process scheduler automatically pulls the latest XML backups directly from your Google Drive every day.
- **Dynamic OAuth Integration:** Securely connect your Google account via a standard OAuth2 flow right from the UI—no manual Service Account JSONs required.
- **Fast, Deduplicated Ingestion:** Uses a normalized SQLite database to deduplicate messages and calls based on content hashes, handling large backups efficiently.
- **Modern Chat UI:** A clean, responsive interface featuring Dark Mode, contact filtering, message search, and media attachment indicators.
- **Export Capabilities:** Export conversations to CSV, JSON, or PDF formats.
- **MCP Enabled:** Built with an integrated Model Context Protocol (FastMCP) server to expose the database to external AI agents.

---

## Prerequisites

- **Docker** and **Docker Compose** installed on your host machine.
- A **Google Cloud Platform (GCP)** account (free) to generate OAuth credentials for accessing your own Google Drive.

---

## Google Cloud Platform (GCP) Setup

Because this is a self-hosted application, you need to create your own Google OAuth credentials. This ensures your data remains completely private and you get your own dedicated API quotas.

1. **Create a Project:**
   - Go to the [Google Cloud Console](https://console.cloud.google.com/).
   - Click the project dropdown at the top and select **New Project**. Name it something like `SMS Web Viewer`.

2. **Enable the Google Drive API:**
   - In the left sidebar, navigate to **APIs & Services > Library**.
   - Search for **Google Drive API** and click **Enable**.

3. **Configure the OAuth Consent Screen:**
   - Navigate to **APIs & Services > OAuth consent screen**.
   - Choose **External** (if you're using a personal Gmail account) or **Internal** (if using Google Workspace) and click **Create**.
   - Fill in the required fields (App name, User support email, Developer contact info). You can leave the rest blank.
   - On the **Scopes** page, click **Add or Remove Scopes** and manually add `https://www.googleapis.com/auth/drive.readonly`.
   - On the **Test users** page, add your own Google email address.

4. **Create OAuth Credentials:**
   - Navigate to **APIs & Services > Credentials**.
   - Click **Create Credentials** -> **OAuth client ID**.
   - Set the Application type to **Web application**.
   - Give it a name (e.g., `SMS Viewer Local`).
   - Under **Authorized redirect URIs**, add the exact URI where your app will run locally:
     `http://localhost:8000/api/auth/callback`
   - Click **Create**.
   - Copy your **Client ID** and **Client Secret**. You will need these for the `.env` file.

---

## Initial Setup

1. **Clone the Repository:**
   ```bash
   git clone https://github.com/yourusername/smsviewer.git
   cd smsviewer
   ```

2. **Configure Environment Variables:**
   Create a `.env` file in the root directory and add your Google Cloud credentials:
   ```env
   # Google OAuth2 Credentials (from GCP Setup)
   GCP_CLIENT_ID="your-client-id.apps.googleusercontent.com"
   GCP_CLIENT_SECRET="your-client-secret"
   
   # The redirect URI must match exactly what you put in Google Cloud Console
   OAUTH_REDIRECT_URI="http://localhost:8000/api/auth/callback"
   
   # Optional: Set the default sync schedule (cron format). Default is 2 AM daily.
   SYNC_SCHEDULE="0 2 * * *"
   
   # Optional: Default country code for phone number normalization
   DEFAULT_COUNTRY_CODE="US"
   ```

3. **Start the Application:**
   Run the following command to build the image and start the container:
   ```bash
   docker-compose up -d --build
   ```

   The application will initialize its SQLite database in a persistent Docker volume (`/data/smsviewer.db`).

---

## Usage Instructions

1. **Access the Web UI:**
   Open your browser and navigate to `http://localhost:8000`.

2. **Connect Google Drive:**
   - Click the **Settings** button (gear icon) in the top right corner.
   - Click **Connect Google Drive**.
   - You will be redirected to Google to authorize the application. Since your app is unverified, you may see a "Google hasn't verified this app" warning. Click **Advanced** and then **Go to SMS Web Viewer (unsafe)** to proceed.
   - Grant the required read-only access to your Google Drive.

3. **Select Your Sync Folder:**
   - Once redirected back to the app, open the **Settings** modal again.
   - You will now see a dropdown populated with the folders in your Google Drive.
   - Select the folder where your SMS Backup & Restore XML files are saved.
   - Click **Save Settings**.

4. **Run a Sync:**
   - Click the **Sync Now** button on the main dashboard.
   - The backend will scan your selected folder, download the newest `sms-*.xml` and `calls-*.xml` files, and ingest them into the database.
   - When the sync completes, your contacts, messages, and call logs will instantly populate!

---

## Testing the MCP Server

This application includes a built-in Model Context Protocol (MCP) server that allows external AI agents to query your SMS and Call data securely. It exposes an SSE (Server-Sent Events) transport endpoint.

### Using the Official MCP Inspector

The easiest way to test the available MCP tools is using the official interactive inspector:

1. Ensure your SMS Web Viewer Docker container is running (`http://localhost:8000`).
2. Run the inspector using Node.js (`npx`):
   ```bash
   npx @modelcontextprotocol/inspector
   ```
3. The inspector will open a web interface in your browser.
4. In the connection settings:
   - Select **SSE** as the transport type.
   - Set the URL to: `http://localhost:8000/mcp/sse`
   - Click **Connect**.
5. Once connected, you can browse and test the available tools:
   - `query_contacts`: Look up contacts by name or phone number.
   - `search_messages`: Perform a full-text search across all SMS and MMS messages.
   - `get_conversation_context`: Retrieve the last N messages with a specific number.
   - `get_call_stats`: Summarize call history (duration, missed vs. answered) for a specific number.

### Using with LM Studio, VSCode, or Claude Desktop

Most AI coding assistants and desktop apps (like LM Studio, Claude Desktop, Cline, or Roo Code) communicate with MCP servers using standard input/output (`stdio`). 

Since SMS Web Viewer runs securely inside a Docker container, you can instruct your AI assistant to execute the MCP server directly from the container.

Add the following configuration to your MCP settings file (e.g., LM Studio's MCP Config, `claude_desktop_config.json`, or `cline_mcp_settings.json`):

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

**Note:** Ensure the `smsviewer` Docker container is running before attempting to use the MCP tools in your AI assistant.

---

## Data Privacy & Security

SMS Web Viewer operates entirely on your local machine. 
- It communicates directly with Google Drive using the OAuth credentials you generated. 
- No middleman servers are used.
- Your downloaded XML files and SQLite database are securely stored on your local Docker volumes.
