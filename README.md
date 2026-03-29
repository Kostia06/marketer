# Marketer — n8n Developer Content Automation

Auto-generate and publish developer-focused content on LinkedIn and X with a Discord-based approval flow.

## How It Works

Three n8n workflows:

1. **Content Generator** — Runs daily at 6 AM. Uses Gemini to draft platform-specific posts. Sends drafts to Discord for review.
2. **Review Handler** — Webhook that processes approve/reject clicks from Discord. Updates draft status.
3. **Publisher** — Runs daily at 8 AM + random 0-3hr delay. Posts approved drafts to LinkedIn and X. Confirms in Discord.

## Prerequisites

- Self-hosted n8n instance (v1.0+)
- Gemini API key ([Get one here](https://aistudio.google.com/apikey))
- LinkedIn app with OAuth2 ([Developer portal](https://www.linkedin.com/developers/))
- X/Twitter developer account with OAuth 1.0a ([Developer portal](https://developer.twitter.com/))
- Discord server with a webhook ([Guide](https://support.discord.com/hc/en-us/articles/228383668))

## Setup

### 1. Configure n8n Environment

Add these environment variables to your n8n instance:

```env
# Required: Allow filesystem access in Code nodes
NODE_FUNCTION_ALLOW_BUILTIN=fs,path

# API Keys
GEMINI_API_KEY=your_gemini_api_key

# LinkedIn
LINKEDIN_PERSON_ID=your_linkedin_person_urn_id

# Discord
MARKETER_DISCORD_WEBHOOK=https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN

# Review webhook (your n8n instance URL)
MARKETER_REVIEW_WEBHOOK=https://your-n8n-domain.com/webhook/marketer-review
```

### 2. Copy Configuration Files

Copy the config files to your n8n data directory:

```bash
# Create the marketer directory in n8n's data folder
mkdir -p /home/node/.n8n/marketer

# Copy config files
cp config/config.json /home/node/.n8n/marketer/
cp config/prompts.json /home/node/.n8n/marketer/
cp data/drafts.json /home/node/.n8n/marketer/
```

Update the paths in `config.json` if your n8n data directory is different.

### 3. Set Up API Credentials in n8n

#### LinkedIn OAuth2

1. Create a LinkedIn app at [linkedin.com/developers](https://www.linkedin.com/developers/)
2. Request the `w_member_social` scope
3. In n8n, create an **HTTP Header Auth** credential:
   - Name: `LinkedIn Auth`
   - Header Name: `Authorization`
   - Header Value: `Bearer YOUR_ACCESS_TOKEN`

#### X/Twitter OAuth 1.0a

1. Create a Twitter developer app at [developer.twitter.com](https://developer.twitter.com/)
2. Enable OAuth 1.0a with read/write permissions
3. In n8n, create an **OAuth1 API** credential:
   - Name: `Twitter OAuth`
   - Consumer Key: your API key
   - Consumer Secret: your API secret
   - Access Token: your access token
   - Access Token Secret: your access token secret
   - Request Token URL: `https://api.twitter.com/oauth/request_token`
   - Authorization URL: `https://api.twitter.com/oauth/authorize`
   - Access Token URL: `https://api.twitter.com/oauth/access_token`
   - Signature Method: `HMAC-SHA1`

### 4. Import Workflows

1. Open your n8n instance
2. Go to **Workflows** → **Import from File**
3. Import each workflow:
   - `workflows/content-generator.json`
   - `workflows/review-handler.json`
   - `workflows/publisher.json`
4. Update credential references in each workflow if needed

### 5. Update Credential IDs

After importing, open each workflow and update the HTTP Request nodes to use your configured credentials:

- **Publisher** → "Post to LinkedIn" node → select your LinkedIn credential
- **Publisher** → "Post to X" node → select your Twitter credential

### 6. Activate Workflows

1. Activate **Review Handler** first (it needs to be listening for webhook calls)
2. Activate **Content Generator**
3. Activate **Publisher**

### 7. Test

Run the Content Generator manually to verify:

1. Open the Content Generator workflow
2. Click "Execute Workflow"
3. Check your Discord channel for the draft message
4. Click the Approve/Reject links
5. Verify the draft status updates

## Customization

### Edit Your Profile

Update `config/config.json` with your details, then copy to the n8n data directory.

### Modify Prompts

Edit `config/prompts.json` to change how content is generated. You can:
- Add/remove content types
- Change tone and style examples
- Adjust platform formatting rules

### Change Schedule

Edit the Schedule Trigger nodes in each workflow:
- Content Generator: change the hour in "Daily 6AM Trigger"
- Publisher: change the hour in "Daily 8AM Trigger"
- Adjust the random delay range in "Calculate Random Delay" code node

### File Paths

All workflows read/write from `/home/node/.n8n/marketer/`. Update the `DRAFTS_PATH`, `CONFIG_PATH`, and `PROMPTS_PATH` constants in the Code nodes if your paths differ.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Code node: "Cannot find module 'fs'" | Set `NODE_FUNCTION_ALLOW_BUILTIN=fs,path` in n8n env |
| Gemini 429 error | Rate limited — reduce frequency or upgrade API tier |
| LinkedIn 401 | Access token expired — refresh OAuth token |
| X 403 | Check app permissions — needs read/write access |
| Discord links don't work | Verify `MARKETER_REVIEW_WEBHOOK` matches your n8n webhook URL |
| No post published | Check drafts.json — is there an approved draft? |
