# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.4] - 2026-06-08

### Added
- **OAuth Re-Authentication**: Added a manual "Disconnect" button to the UI to sever Google Drive links.
- **Expiration Handling**: Background sync now gracefully handles expired or revoked Google OAuth tokens. It automatically clears the tokens from the database, halts the sync without crashing, and sends an Apprise notification alert to re-authenticate.
- **Custom OAuth Logo**: Generated and included a custom 120x120 app logo for the Google Cloud Consent screen.
- **GitHub Link**: Added a subtle link to the GitHub repository in the application footer.

### Changed
- **Responsive Toolbars**: Re-engineered the application header, sync status bar, and chat toolbars to wrap gracefully on smaller mobile screens.

### Fixed
- **Documentation**: Expanded the `README.md` to explicitly detail how to bypass the "Verification Required" warning when publishing the OAuth Consent Screen to permanently prevent 7-day token expirations.

## [1.3.3] - 2026-06-06

### Added
- **Configurable Log Levels:** Added backend support for the `LOG_LEVEL` environment variable. You can now set `LOG_LEVEL=DEBUG` in your Docker configuration for verbose backend logging.

### Fixed
- **Global Search Deep-Linking Bug:** Fixed a Javascript variable scoping bug that prevented the chat window from rendering enough historical messages to reach deep search results, causing the scroll-to-message feature to fail silently on older messages.
- **Frontend Debugging:** Added frontend `console.debug` statements to track search-jump failures.

## [1.3.2] - 2026-06-06

### Fixed
- **Global Search Jump Bug (PostgreSQL):** Fixed an issue where clicking a global search result on PostgreSQL databases would fail to jump to the message or jump to the wrong message. This was caused by overlapping auto-incrementing IDs between the SMS and MMS tables. The UI now uses a composite ID (`source-id`) to uniquely identify and target messages.

## [1.3.1] - 2026-06-06

### Changed
- **Global Search UI & Context Navigation:** The global search results now display the phone number next to contact names for better clarity with unsaved numbers. Clicking on a search result now intelligently jumps the chat window directly to that specific message in the conversation thread and highlights it, providing instant context.

## [1.3.0] - 2026-06-03

### Added
- **Multi-Provider Notifications:** Integrated the Apprise framework to deliver robust background notifications whenever a Google Drive sync succeeds or fails. Supports Discord, Telegram, Pushover, Slack, and almost 100 other services.
- **Notification Settings UI:** Added a new Notifications configuration pane in the Settings modal, allowing users to define their webhook URLs, toggle success/failure alerts, and send live test notifications directly from the browser.

## [1.2.2] - 2026-06-01

### Added
- **Version Badge:** Added a visible version number badge to the top right of the navigation header that adapts seamlessly to both light and dark modes.

### Fixed
- **PostgreSQL Strict Enforcement Fixes:** Added aggressive data sanitization to the XML parser to prevent PostgreSQL DBAPI crashes caused by corrupted or unbounded Android backup data:
  - Strips NULL bytes (`\x00`) from all parsed strings to prevent `DataError: invalid byte sequence`.
  - Clamps all `SmallInteger` fields (`type`, `msg_box`, `read`, `status`, `presentation`) to safe Postgres bounds (-32768 to 32767).
  - Clamps all standard `Integer` fields (`duration`, `sub_id`) to safe Postgres bounds (-2147483648 to 2147483647).

## [1.2.1] - 2026-06-01

### Added
- **Audit Logging:** Added comprehensive server-side audit logs to track successful/failed authentication attempts, manual XML uploads, data exports (CSV/JSON/ZIP), API token creation/revocation, user deletion, and MCP client SSE connections.

### Fixed
- **PostgreSQL Sync Crash:** Fixed a `StringDataRightTruncationError` that occurred exclusively on PostgreSQL databases when a user's phone locale generated a `readable_date` string longer than the schema's 64-character limit. The string is now safely truncated during ingestion, allowing the sync pipeline to complete successfully.

## [1.2.0] - 2026-06-01

### Added
- **API Token Expiration:** Tokens now support explicit expiration dates (e.g., 30 days) for improved security.
- **Bulk Token Revocation:** Added UI and API support (`DELETE /api/user/tokens/all`) to immediately revoke all active tokens.
- **Client-Side Upload Validation:** The UI now warns you if an uploaded XML file exceeds the 4 GB limit before making a wasteful network request.

### Changed
- **XML Streaming Security:** Upgraded the XML ingestion pipeline to use the highly secure `DefusedXMLParser` directly integrated with Python's native `iterparse()`, protecting against advanced XXE and Billion Laughs bypasses without sacrificing streaming speed.
- **Media Exports (ZIP):** Completely rewrote the `export_media` endpoint to stream attachments from PostgreSQL directly to disk in batches, preventing Out-Of-Memory (OOM) crashes on large multi-gigabyte media exports.
- **Search Boundaries:** Enforced `min_length=1` and `max_length=500` limits for the `q` query parameter across global search and MCP search tools to prevent payload abuse.
- **Export Consistency:** CSV and JSON exports now successfully combine and sort both SMS and MMS messages together in a unified conversation log.

### Fixed
- Fixed an SQLite-specific `strftime` incompatibility in `get_communication_frequency` that caused the MCP tool to fail when using a PostgreSQL backend.
- Fixed a silent failure where the background scheduler cron expressions were not properly validated before saving to the database.
- Fixed an issue where the file upload endpoint didn't properly enforce the chunk size limit, resulting in 413 Payload Too Large HTTP exceptions explicitly.
- Fixed timezone comparison `TypeError` crashes during token authentication by ensuring all datetimes are UTC-aware.
