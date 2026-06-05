# Brewery Telegram Bot

A Telegram bot for managing your home brewery — stock visibility, ordering, and admin controls, backed by Google Sheets.

## Features

- **View stock** — Members see current available beers with prices (`/stock`)
- **Place orders** — Interactive order flow with confirmation (`/order`)
- **Order history** — Members can check their past orders (`/myorders`)
- **Admin stock management** — Add/remove items via bot commands or directly in Google Sheets
- **Join approval** — Bot notifies admins when someone requests to join; approve/decline with buttons

## Setup

### 1. Create the Telegram Bot

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow the prompts
3. Save the **bot token**

### 2. Create a Private Group

1. Create a new Telegram group
2. Set it to **Private**
3. In group settings → Invite Links, create an invite link with **"Request admin approval"** enabled
4. Add your bot to the group and make it an **admin**

### 3. Set Up Google Sheets

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or use existing)
3. Enable **Google Sheets API** and **Google Drive API**
4. Create a **Service Account** (APIs & Services → Credentials → Create Credentials → Service Account)
5. Download the JSON key file → save as `credentials.json` in the project folder
6. Create a new Google Spreadsheet
7. Share the spreadsheet with the service account email (from the JSON file, `client_email` field)
8. Copy the spreadsheet ID from the URL:
   ```
   https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit
   ```

### 4. Configure Environment

```bash
cp .env.example .env
```

Edit `.env`:
- `TELEGRAM_BOT_TOKEN` — from BotFather
- `ADMIN_IDS` — your Telegram user ID (message [@userinfobot](https://t.me/userinfobot) to find it)
- `GOOGLE_SHEET_ID` — spreadsheet ID from step 3
- `GOOGLE_CREDENTIALS_FILE` — path to your credentials JSON (default: `credentials.json`)

### 5. Install & Run

```bash
pip install -r requirements.txt
python bot.py
```

## Commands

### For everyone:
| Command | Description |
|---------|-------------|
| `/start` | Welcome message |
| `/stock` | View available beers and prices |
| `/order` | Place an order (interactive) |
| `/myorders` | View your order history |
| `/help` | Show commands |

### Admin only:
| Command | Description |
|---------|-------------|
| `/addstock` | Add a new beer (guided flow) |
| `/remove <name>` | Remove a beer from stock |
| `/allstock` | View all stock including unavailable items |

## Google Sheet Structure

The bot auto-creates two sheets:

**Stock** sheet:
| Name | Style | Volume (L) | Price | Available |
|------|-------|------------|-------|-----------|
| Summer Pale Ale | Pale Ale | 20 | 500₽/L | Yes |
| Dark Stout | Stout | 10 | 600₽/L | Yes |

**Orders** sheet:
| Order ID | Date | User | Username | Item | Qty | Status |
|----------|------|------|----------|------|-----|--------|
| A1B2C3D4 | 2026-06-04 | John | johndoe | Summer Pale Ale | 2 | New |

You can edit both sheets directly in Google Sheets — the bot reads them in real time.

## Managing Stock

You have two options (or both):

1. **Google Sheets** — Just open the spreadsheet and edit rows directly. Add new rows, change prices, toggle "Available" column.
2. **Bot commands** — Use `/addstock` and `/remove` in Telegram.

## Deployment

For always-on operation, run on any server or free-tier platform:

```bash
# Simple: run with nohup
nohup python bot.py &

# Or use systemd, Docker, etc.
```

### Free hosting options:
- [Railway](https://railway.app) — free tier
- [Render](https://render.com) — free tier (spins down after inactivity)
- Any VPS with Python 3.10+
