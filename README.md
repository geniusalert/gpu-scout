# GPU Scout

Python Telegram bot with Keiki requirement extraction, Vast.ai listings, optional Supermemory storage, and a Maritime-ready Dockerfile.

## Start

Create a bot using Telegram @BotFather. In this folder run:

```
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit .env locally with TELEGRAM_BOT_TOKEN, then run `.\.venv\Scripts\python bot.py`.
Demo: `/find H100_SXM 8 2.50 US`. Simulated listings are explicitly labeled.

For live mode set DEMO_MODE=false, VAST_API_KEY, KEIKI_API_KEY and KEIKI_AGENT. Create a Keiki agent, enable its API gateway and configure it for JSON extraction without external action tools. Optional SUPERMEMORY_API_KEY saves requirements in user-scoped containers. Memory recall is not yet implemented. SQLite is authoritative. ALLOWED_USER_IDS optionally restricts access (comma-separated IDs). Only private chats are supported.

Commands: /start /help /find /watch /status /stop <task id> /quote <task id> /sources. Watches run every 15 minutes and persist across restarts. RFQs can be sent through AgentMail after explicit approval. Reply tracking, /compare, browser inquiry forms and broader supplier discovery are not implemented. No provisioning or payments occur. Vast.ai and Lambda are searched when their API keys are configured. Counts must match one listing exactly; topology, duration commitments, tax and additional fees need supplier confirmation.

## Maritime

Deploy the Dockerfile through Maritime custom-container hosting; supply secrets through its settings, mount persistent storage at /data and keep one continuously running replica. Long polling needs no inbound port. Confirm current container settings in Maritime documentation/dashboard. Deployment has not been performed. PumpGTM is a growth service, not a runtime dependency.

## Check

`python -m unittest discover -s tests -v`

Live Telegram/provider connections require credentials and have not been verified. Keiki receives search text; optional Supermemory receives criteria. Keep .env private.

Official API references:
https://onkeiki.com/docs/agent-api
https://vast.ai/developers/api
https://supermemory.ai/docs/api-reference/ingest/add-document
https://maritime.sh/docs/api


## Cross-provider search and approved outreach

Set LAMBDA_API_KEY to include Lambda live instance types and regional capacity alongside Vast.ai. Results rank the cheapest listed GPU-hour price within budget, among supported sources that successfully respond. This is not a guaranteed best total contract price. Exact GPU variants, count and country prefix are matched; unknown or unsupported regions are excluded conservatively. Provider failures appear in coverage. Lambda API: https://docs.lambda.ai/api/cloud

Set AGENTMAIL_API_KEY and AGENTMAIL_INBOX_ID to an inbox you control. The key supplied in chat has not been embedded in source or examples. Enter it locally in .env. Never commit .env. Configure a Telegram allowlist before enabling outreach on a publicly discoverable bot.

1. /find with your requirements.
2. /quote <task id> <supplier email> creates an immutable draft and displays the recipient, subject and body.
3. /approve <draft token> sends exactly that draft through AgentMail. Tokens belong to the requesting Telegram user, expire in 30 minutes and cannot be reused.
4. /cancel <draft token> cancels a pending draft.

Demo mode never sends. No automatic send retries occur: an ambiguous failure is marked unknown for manual inspection in AgentMail. After a crash, a sending state also needs manual inspection. Use a fresh draft for edits. Sending emails is implemented; supplier reply ingestion and automatic quote comparison are future work. Supplier addresses must currently be provided by the user; the bot does not invent or autonomously discover contact details. No emails have been sent during implementation.

AgentMail documentation: https://docs.agentmail.to/llms.txt and https://docs.agentmail.to/messages
Browser Use was evaluated but is not installed or integrated; this release uses structured provider APIs and approved email inquiries.

## Detailed Google supplier research

Configure SERPAPI_API_KEY locally (https://serpapi.com/search-api). Google results are retrieved through SerpApi; search queries are sent to that service. Each research run uses three targeted queries, deduplicates domains, investigates up to ten domains, and reads at most three pages per domain. This can use three paid search requests. No API key is included in the project.

Workflow:
1. /find <requirements> creates a task.
2. /research <task id> investigates Google results, supplier pages and linked pricing/contact pages.
3. /report <task id> retrieves the saved report with source URLs, timestamps in stored data, price excerpts and explicit business contacts.
4. /contact <task id> <supplier number> prepares an inquiry using a published sales/contact address from the supplier domain.
5. Review the complete recipient, subject and message, then /approve <token> to send through AgentMail. /cancel <token> discards it.

No email is sent during research. Website text is parsed as evidence and never executed or passed to an action-capable model. Contacts are not guessed. Pages unavailable to the HTML reader (including JavaScript-only sites) are disclosed; browser automation and form submissions remain unimplemented. Web excerpts may describe unrelated prices or outdated configurations and are deliberately excluded from verified offer ranking. Reports prioritize GPU mentions and contact availability, not a claim of the globally best deal. Research is bounded and does not cover every Google result. Reply tracking remains unimplemented.

Live Google, Telegram and email flows still require credentials and end-to-end verification. No supplier emails were sent during development.


## Imported supplier audit

The supplied `GPU_Supplier_Email_Audit_2026-10-21 (1).xlsx` has been imported into the local SQLite database: 243 nonempty rows across 8 worksheets. Run `/suppliers <company name or GPU model>` in Telegram to search company records. Records are historical evidence from 21 October 2026 and must be rechecked before procurement. The NDA-redacted company is hidden from bot search. The import retains source workbook hash and row numbers for traceability. The spreadsheet and database are local and are not sent to Google, Keiki, AgentMail, or Supermemory through this command. No supplier email is sent automatically from imported records.

To repeat the import after updating the workbook: `.\.venv\Scripts\python import_suppliers.py "..\GPU_Supplier_Email_Audit_2026-10-21 (1).xlsx"`. The import is idempotent for the same file hash. Keep the workbook and database private; they contain correspondence and commercial details. For Maritime deployment, transfer the database through its supported persistent volume or reimport the workbook there. A local import does not automatically appear in a cloud container.

Submission status: Telegram and AgentMail credentials validate; `DEMO_MODE=false`; Google supplier research is configured through SerpApi. Vast.ai, Lambda and Keiki keys are currently absent, so live provider offers and free-form language parsing are not available. The bot is usable for structured task creation, supplier audit lookup, Google research, drafts and approved AgentMail sending. Those external flows have not been verified end to end with a real supplier.


## Telegram availability

Telegram hosts the chat interface; the polling Python process must stay running to answer. On this workstation the bot can be started with `.\.venv\Scripts\python bot.py`. Closing that process or turning off the computer takes the bot offline. The source repository alone does not deploy the process. A continuously available public submission requires a container host such as Maritime with persistent `/data` storage and the environment variables from `.env.example`. Keep exactly one polling replica per bot token.

## Maritime webhook deployment

The Dockerfile now runs `webhook_server.py`, which binds Maritime's injected `PORT`, serves `/health` and `/chat`, and accepts authenticated Telegram updates at `/telegram`. Use Maritime's public web agent deployment for the repository. In the dashboard or CLI, connect the GitHub repo, choose the `main` branch, and enable a public HTTPS URL so Telegram can reach the webhook. Set `TELEGRAM_BOT_TOKEN`, a random `TELEGRAM_WEBHOOK_SECRET`, `DATABASE_PATH=/data/scout.db`, `DEMO_MODE=false`, and any provider credentials as encrypted environment variables. Do not copy `.env` to GitHub. Import the supplier workbook into the hosted `/data/scout.db` if those records are needed there.

After Maritime reports healthy, stop the local polling bot. Set the same token and webhook secret locally, then run `python configure_webhook.py https://<your-agent-id>.mtm.sh` once. Check Telegram's `getWebhookInfo` for delivery errors and send `/start` to the bot. Do not start `bot.py` while the webhook is active. Maritime's automatic sleep means in-process 15-minute watches do not run while sleeping; configure a platform schedule before claiming continuous alerting. The hosted deployment has not been performed or verified on a Maritime account.

Deployment references: https://maritime.sh/docs/web-apps ; https://maritime.sh/docs/frameworks/custom ; https://maritime.sh/docs/configuration
