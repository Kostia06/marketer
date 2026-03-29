# Marketer — n8n Developer Content Automation

Auto-generate and publish developer-focused content on LinkedIn and X with a Discord-based approval flow.

## How It Works

Three n8n workflows:

1. **Content Generator** — Runs daily at 6 AM. Uses Gemini to draft platform-specific posts. Sends drafts to Discord for review.
2. **Review Handler** — Webhook that processes approve/reject clicks from Discord. Updates draft status.
3. **Publisher** — Runs daily at 8 AM + random 0-3hr delay. Posts approved drafts to LinkedIn and X. Confirms in Discord.

## Quick Start

```bash
git clone <your-repo-url>
cd marketer
cp .env.example .env
# Edit .env with your API keys
./setup.sh
```

## Prerequisites

- Docker & Docker Compose
- Gemini API key ([Get one here](https://aistudio.google.com/apikey))
- LinkedIn app with OAuth2 ([Developer portal](https://www.linkedin.com/developers/))
- X/Twitter developer account with OAuth 1.0a ([Developer portal](https://developer.twitter.com/))
- Discord server with a webhook ([Guide](https://support.discord.com/hc/en-us/articles/228383668))

## Setup

### 1. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
GEMINI_API_KEY=your_gemini_api_key
MARKETER_DISCORD_WEBHOOK=https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN
MARKETER_REVIEW_WEBHOOK=http://localhost:5678/webhook/marketer-review
LINKEDIN_ACCESS_TOKEN=your_linkedin_access_token
TWITTER_CONSUMER_KEY=your_consumer_key
TWITTER_CONSUMER_SECRET=your_consumer_secret
TWITTER_ACCESS_TOKEN=your_access_token
TWITTER_ACCESS_TOKEN_SECRET=your_access_token_secret
```

### 2. Start n8n

```bash
./setup.sh
```

Or manually:

```bash
docker compose up -d
```

n8n will be available at http://localhost:5678

### 3. Set Up API Credentials in n8n

#### LinkedIn

1. In n8n, go to **Credentials** > **New** > **HTTP Header Auth**
2. Name: `LinkedIn Auth`
3. Header Name: `Authorization`
4. Header Value: `Bearer YOUR_ACCESS_TOKEN`

#### X/Twitter

1. In n8n, go to **Credentials** > **New** > **OAuth1 API**
2. Name: `Twitter OAuth`
3. Consumer Key / Secret: from your X developer app
4. Access Token / Secret: from your X developer app
5. Request Token URL: `https://api.twitter.com/oauth/request_token`
6. Authorization URL: `https://api.twitter.com/oauth/authorize`
7. Access Token URL: `https://api.twitter.com/oauth/access_token`
8. Signature Method: `HMAC-SHA1`

### 4. Import Workflows

1. Open n8n at http://localhost:5678
2. Go to **Workflows** > **Import from File**
3. Import all three from `workflows/`:
   - `content-generator.json`
   - `review-handler.json`
   - `publisher.json`
4. In each workflow, update credential references to match your created credentials

### 5. Activate Workflows

1. **Review Handler** first (needs to listen for webhooks)
2. **Content Generator**
3. **Publisher**

### 6. Test

1. Open the Content Generator workflow
2. Click **Execute Workflow**
3. Check your Discord channel for the draft
4. Click the Approve/Reject links
5. Verify it works

## Server Deployment

After testing locally, deploy to your server:

```bash
# On your server
git clone <your-repo-url>
cd marketer
cp .env.example .env
```

Update `.env` for production:

```env
N8N_HOST=your-domain.com
N8N_PROTOCOL=https
WEBHOOK_URL=https://your-domain.com
MARKETER_REVIEW_WEBHOOK=https://your-domain.com/webhook/marketer-review
```

Then run:

```bash
./setup.sh
```

## Customization

### Edit Your Profile

Update `config/config.json` — changes are picked up automatically (mounted as a volume).

### Modify Prompts

Edit `config/prompts.json` to change content generation style, examples, or platform rules.

### Change Schedule

Edit the Schedule Trigger nodes in each workflow within the n8n UI.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Code node: "Cannot find module 'fs'" | Set `NODE_FUNCTION_ALLOW_BUILTIN=fs,path` in .env |
| Gemini 429 error | Rate limited -- reduce frequency or upgrade API tier |
| LinkedIn 401 | Access token expired -- regenerate (expires every 60 days) |
| X 403 | Check app permissions -- needs read/write access |
| Discord links don't work | Verify `MARKETER_REVIEW_WEBHOOK` matches your n8n URL |
| No post published | Check `data/drafts.json` -- is there an approved draft? |
