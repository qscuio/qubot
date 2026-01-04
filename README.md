# Personal Telegram Userbot Monitor

A Telegram Userbot built with Node.js and GramJS that monitors specified channels for keywords, filters the messages, and forwards a summary to your personal channel.

## Features
- **Real-time Monitoring**: Listens to new messages in source channels.
- **Keyword Filtering**: Only forwards messages containing specific keywords.
- **Message Rewriting**: Formats the forwarded message with a custom header and source attribution.
- **Dockerized**: Easy deployment using Docker and Docker Compose.
- **GitHub Actions**: Automated deployment to VPS.

## Setup & Configuration

### 1. Prerequisites
- **Telegram API Credentials**: Get your `API_ID` and `API_HASH` from [my.telegram.org](https://my.telegram.org).
- **Telegram Session String**: You need to generate this once locally.
- **VPS**: A server with Docker and SSH access.

### 2. Generating the Session String
Run the helper script locally on your machine to generate the session string:

```bash
npm install
npm run generate-session
```
Follow the prompts (enter credential and OTP). Save the generated string.

### 3. GitHub Secrets (for Automatic Deployment)

Go to your GitHub Repository -> Settings -> Secrets and variables -> Actions, and add the following **Repository secrets**:

| Secret Name | Description | Example |
| :--- | :--- | :--- |
| `API_ID` | Your Telegram API ID | `123456` |
| `API_HASH` | Your Telegram API Hash | `abcdef123456...` |
| `TG_SESSION` | The session string generated in step 2 | `1ApWap...` |
| `SOURCE_CHANNELS` | Comma-separated list of channels to monitor | `news_channel,tech_updates` |
| `TARGET_CHANNEL` | The channel/username where updates are sent | `my_news_feed` |
| `KEYWORDS` | Comma-separated keywords to filter for | `release,launch,urgent` |
| `VPS_HOST` | IP address or domain of your VPS | `192.168.1.100` |
| `VPS_USER` | SSH Username for your VPS | `root` or `ubuntu` |
| `VPS_SSH_KEY` | Private SSH Key for accessing your VPS | `-----BEGIN OPENSSH PRIVATE KEY...` |

### 4. Deployment
Just push to the `main` branch. The GitHub Action will:
1. Create the `.env` file from your secrets.
2. Copy the project files to your VPS folder `/home/<user>/telegram-userbot-monitor`.
3. Run `docker-compose up -d --build`.

## Manual Deployment (Local/Testing)
1. Rename `.env.example` to `.env` and fill in the values.
2. Run `docker-compose up -d --build`.
