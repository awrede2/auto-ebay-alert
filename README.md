# eBay Alert Bot

Scans eBay every 5 minutes for Buy It Now listings matching your criteria and sends SMS alerts via Twilio when a match is found.

## Features
- Multi-tier price alerts (e.g. "Steal" vs "Good deal")
- Buy It Now and/or Best Offer filtering
- Seller quality filters (min feedback %, min transactions)
- Grade filtering (e.g. PSA 8) via title matching
- Exclude keywords (e.g. "broken", "parts only")
- 24-hour cooldown per listing to avoid repeat alerts
- Auto-refreshing eBay OAuth token

---

## Setup

### 1. Environment variables
Set these in Railway under your project → Variables:

| Variable | Description |
|---|---|
| `EBAY_CLIENT_ID` | Your eBay App ID (Client ID) |
| `EBAY_CLIENT_SECRET` | Your eBay Cert ID (Client Secret) |
| `TWILIO_ACCOUNT_SID` | From Twilio dashboard |
| `TWILIO_AUTH_TOKEN` | From Twilio dashboard |
| `TWILIO_FROM_NUMBER` | Your assigned Twilio number e.g. +18336144069 |
| `ALERT_TO_NUMBER` | Your personal number e.g. +12125551234 |
| `SCAN_INTERVAL_SECONDS` | How often to scan in seconds (default: 300 = 5 min) |

### 2. Configure your alerts
Edit `alerts.yaml` to add your searches. Each alert supports:

```yaml
- keywords: "search terms here"
  condition: used          # new | like_new | used | any
  required_grade: "PSA 8"  # optional — must appear in title
  exclude_keywords: [broken, fake]  # optional
  tiers:
    - label: "Steal"
      max_price: 150
      buying_options: [BUY_IT_NOW]
    - label: "Good deal"
      max_price: 200
      buying_options: [BUY_IT_NOW, BEST_OFFER]
```

### 3. Deploy
Push this repo to GitHub, connect to Railway, add your environment variables, and deploy. The bot starts automatically.

---

## Adjusting searches
Just edit `alerts.yaml`, commit, and push to GitHub. Railway will automatically redeploy with your new settings within seconds.
