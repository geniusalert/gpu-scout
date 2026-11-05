# GPU Scout

A Telegram GPU sourcing assistant: Google discovery, supplier-audit lookup, optional live marketplace listings, and approved email inquiries.

Telegram: https://t.me/spotgpubot

## Use the bot

Send `/find 8 H100 SXM in US under $2.50 per GPU-hour`.

`/find` automatically runs three targeted Google queries, removes general GPU explainers, groups results by domain, and returns a linked shortlist. It also searches the imported supplier audit with deterministic rules. Saved historical leads remain available when Google cannot complete a search. No empty provider configuration is shown in replies.

The web shortlist identifies potential suppliers and comparison sources; its prices and capacity must be confirmed. Historical audit records do not prove current availability or a match for the requested GPU count, variant, region or budget. Only connected marketplace API listings are ranked as instant-rental offers by listed USD per GPU-hour. The bot never purchases, reserves or provisions GPUs.

Commands:

- `/find <requirements>` — Google search, optional marketplace offers and historical supplier leads.
- `/report <task id>` — source links, snippets, pricing evidence and imported records.
- `/research <task id>` — read supplier pages and linked pricing/contact pages for more detail. This can take several minutes.
- `/contact <task id> <supplier number>` — draft a tailored inquiry for a published supplier-domain business address found during research.
- `/quote <task id> <supplier email>` — draft an inquiry to an address you supply.
- `/approve <draft token>` — send the exact reviewed email through AgentMail.
- `/cancel <draft token>` — cancel a pending draft.
- `/suppliers <company or GPU>` — search the imported audit directly.
- `/status` — saved tasks; `/sources` — available search sources.

Approvals belong to the requesting user, expire after 30 minutes, and cannot be reused. Ambiguous email failures require manual inspection in AgentMail and are never retried automatically. Changing an email requires a new draft and approval. Supplier inbox reply tracking and browser form submission are not implemented.

## Run locally

Create a Telegram bot with @BotFather. Use a separate test bot if the production token already has a webhook.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python bot.py
```

Edit `.env` before starting. Set `TELEGRAM_BOT_TOKEN` and `DEMO_MODE=false`. Keep keys out of source control.

For Google, use **one of** `SERPAPI_API_KEY` (SerpApi) or `SERPER_API_KEY` (Serper). These are different services and their keys are not interchangeable. If both are set, Serper takes precedence. The currently configured production service is SerpApi, and live searches have been verified. Each `/find` or `/research` may consume three Google API requests. Query text is sent to the selected search service.

Optional `VAST_API_KEY` and `LAMBDA_API_KEY` add live marketplace capacity. `KEIKI_API_KEY` and `KEIKI_AGENT` enable language-model extraction; a local parser handles common English requests and `H100_SXM 8 2.50 US` without Keiki. Optional `SUPERMEMORY_API_KEY` stores criteria in user-scoped containers; recall is not implemented. SQLite remains authoritative. `ALLOWED_USER_IDS` optionally restricts access to comma-separated Telegram user IDs. Only private chats are processed.

`AGENTMAIL_API_KEY` and `AGENTMAIL_INBOX_ID` enable approved inquiries. Tests do not send supplier emails. Demo mode is opt-in for testing and never sends email; production uses `DEMO_MODE=false`.

## Imported supplier audit

The supplied supplier-audit workbook has 243 nonempty records across 8 sheets. It is imported locally and on the hosted database with source hashes and sheet row numbers. Company records are used as a deterministic fallback; NDA-redacted companies, undeliverable contacts, nonresponders and records explicitly reporting no requested H100 stock are excluded from automatic recommendations. Region mentions are prioritized, while uncertain quantity, region and variant are disclosed.

```powershell
.\.venv\Scripts\python import_suppliers.py "..\GPU_Supplier_Email_Audit_2026-10-21 (1).xlsx"
```

The same workbook hash can be imported repeatedly without adding duplicate rows. Records are historical evidence from October 21, 2026. The workbook and database are excluded from GitHub. Deployments must preserve or import the database separately. The audit lookup command does not send the workbook to external services.

## Maritime deployment

Production is hosted at https://8b4a398d-fc7a-444a-88de-e83028d5fc6a.mtm.sh . `GET /health` reports app health. The Dockerfile starts `webhook_server.py`, binds the injected `PORT`, and stores SQLite at `/data/scout.db`. `POST /telegram` checks Telegram's secret header, saves and deduplicates updates, and acknowledges immediately. A worker processes accepted searches from the persistent queue and resumes queued work after restarts. It clears completed payloads. Long research does not hold open Telegram's delivery request.

Deploy the GitHub `main` branch as a public Maritime web agent. Supply the environment values as encrypted secrets, including a random `TELEGRAM_WEBHOOK_SECRET`; keep `DATABASE_PATH=/data/scout.db`. After the app is healthy, stop any local poller and register the webhook using the same token and secret:

```powershell
python configure_webhook.py https://<agent-id>.mtm.sh
```

Do not run a polling process for the production token while its webhook is active. Maritime build health, Telegram webhook registration and delivery have been verified. Scheduled watch alerts are not enabled in webhook mode; `/watch` exists for local polling, where checks run every 15 minutes. Persistent platform scheduling is required for hosted watches. The `/chat` endpoint supplies the platform contract; the product conversation is through Telegram.

## Verification

```powershell
.\.venv\Scripts\python -m unittest discover -s tests -v
```

Tests cover budgets and provider ranking, Google service contracts, automatic `/find` searches, source relevance, historical fallback, redactions and stock exclusions, user ownership, approval send protection, and durable webhook acceptance/deduplication. Live Google searches have also been tested separately with production credentials. No real supplier email is sent by the test suite.

## Official references

- https://serpapi.com/search-api
- https://serper.dev
- https://vast.ai/developers/api
- https://docs.lambda.ai/api/cloud
- https://onkeiki.com/docs/agent-api
- https://supermemory.ai/docs/api-reference/ingest/add-document
- https://docs.agentmail.to/llms.txt
- https://maritime.sh/docs/web-apps
- https://maritime.sh/docs/frameworks/custom
- https://maritime.sh/docs/configuration
