import os
import json
import logging
import requests
from datetime import datetime, timedelta, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger(__name__)

# ── Environment variables (set in GitHub Secrets) ─────────────────────────────
EBAY_CLIENT_ID     = os.environ["EBAY_CLIENT_ID"]
EBAY_CLIENT_SECRET = os.environ["EBAY_CLIENT_SECRET"]
SENDGRID_API_KEY   = os.environ["SENDGRID_API_KEY"]
ALERT_FROM_EMAIL   = os.environ["ALERT_FROM_EMAIL"]
ALERT_TO_EMAIL     = os.environ["ALERT_TO_EMAIL"]

# ── Seen listings file (committed back to repo after each run) ────────────────
SEEN_FILE = "seen_listings.json"

# ── Inline config ─────────────────────────────────────────────────────────────
CONFIG = {
    "global_defaults": {
        "min_seller_feedback": 95,
        "min_seller_transactions": 15,
        "cooldown_hours": 72,
    },
    "alerts": [
        {
            "keywords": "1999 Charizard 4 PSA 9",
            "condition": "any",
            "exclude_keywords": ["replica", "fake", "reproduction", "topps", "Beckett", "burger king", "2000", "Boxing", "Reprint", "Portuguese", "Spanish", "French", "German", "Japanese", "Korean", "Chinese", "Foreign"],
            "tiers": [
                {"label": "Steal",         "min_price": 1500, "max_price": 2500, "buying_options": ["BUY_IT_NOW"]},
                {"label": "Worth an offer","min_price": 1500, "max_price": 2750, "buying_options": ["BUY_IT_NOW", "BEST_OFFER"]},
            ],
        },
        {
            "keywords": "1999 Charizard 4 PSA 8",
            "condition": "any",
            "exclude_keywords": ["replica", "fake", "reproduction", "topps", "Beckett", "burger king", "2000", "Boxing", "Reprint", "Portuguese", "Spanish", "French", "German", "Japanese", "Korean", "Chinese", "Foreign"],
            "tiers": [
                {"label": "Steal",         "min_price": 600,  "max_price": 1100, "buying_options": ["BUY_IT_NOW"]},
                {"label": "Worth an offer","min_price": 600,  "max_price": 1250, "buying_options": ["BUY_IT_NOW", "BEST_OFFER"]},
            ],
        },
        {
            "keywords": "1999 Charizard 4 PSA 7.5",
            "condition": "any",
            "exclude_keywords": ["replica", "fake", "reproduction", "topps", "Beckett", "burger king", "2000", "Boxing", "Reprint", "Portuguese", "Spanish", "French", "German", "Japanese", "Korean", "Chinese", "Foreign"],
            "tiers": [
                {"label": "Steal",         "min_price": 500,  "max_price": 800,  "buying_options": ["BUY_IT_NOW"]},
                {"label": "Worth an offer","min_price": 500,  "max_price": 1000, "buying_options": ["BUY_IT_NOW", "BEST_OFFER"]},
            ],
        },
        {
            "keywords": "1999 Charizard 4 PSA 7",
            "condition": "any",
            "exclude_keywords": ["replica", "fake", "reproduction", "topps", "Beckett", "burger king", "2000", "Boxing", "Reprint", "Portuguese", "Spanish", "French", "German", "Japanese", "Korean", "Chinese", "Foreign"],
            "tiers": [
                {"label": "Steal",         "min_price": 500,  "max_price": 600,  "buying_options": ["BUY_IT_NOW"]},
                {"label": "Worth an offer","min_price": 500,  "max_price": 698,  "buying_options": ["BUY_IT_NOW", "BEST_OFFER"]},
            ],
        },
        {
            "keywords": "1986 Michael Jordan Fleer 57 PSA 3",
            "condition": "any",
            "exclude_keywords": ["replica", "fake", "reproduction", "sticker"],
            "tiers": [
                {"label": "Steal",         "min_price": 3000, "max_price": 4000, "buying_options": ["BUY_IT_NOW"]},
                {"label": "Worth an offer","min_price": 3000, "max_price": 4400, "buying_options": ["BUY_IT_NOW", "BEST_OFFER"]},
            ],
        },
        {
            "keywords": "1921 w551 PSA 8",
            "condition": "any",
            "exclude_keywords": [],
            "tiers": [
                {"label": "w551 Match", "min_price": 0, "max_price": 999999, "buying_options": ["BUY_IT_NOW", "BEST_OFFER"]},
            ],
        },
        {
            "keywords": "1921 w551 PSA 9",
            "condition": "any",
            "exclude_keywords": [],
            "tiers": [
                {"label": "w551 Match", "min_price": 0, "max_price": 999999, "buying_options": ["BUY_IT_NOW", "BEST_OFFER"]},
            ],
        },
        {
            "keywords": "1921 w551 uncut",
            "condition": "any",
            "exclude_keywords": [],
            "tiers": [
                {"label": "w551 Match", "min_price": 0, "max_price": 999999, "buying_options": ["BUY_IT_NOW", "BEST_OFFER"]},
            ],
        },
    ],
}

# ── eBay OAuth ────────────────────────────────────────────────────────────────
def get_ebay_token():
    resp = requests.post(
        "https://api.ebay.com/identity/v1/oauth2/token",
        auth=(EBAY_CLIENT_ID, EBAY_CLIENT_SECRET),
        data={"grant_type": "client_credentials",
              "scope": "https://api.ebay.com/oauth/api_scope"},
    )
    resp.raise_for_status()
    return resp.json()["access_token"]

# ── Persistent state ──────────────────────────────────────────────────────────
def load_seen():
    try:
        with open(SEEN_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(seen, f, indent=2)

# ── Cooldown ──────────────────────────────────────────────────────────────────
def is_on_cooldown(seen, item_id, cooldown_hours):
    if item_id not in seen:
        return False
    alerted_at = datetime.fromisoformat(seen[item_id])
    if alerted_at.tzinfo is None:
        alerted_at = alerted_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) < alerted_at + timedelta(hours=cooldown_hours)

def mark_seen(seen, item_id):
    seen[item_id] = datetime.now(timezone.utc).isoformat()

# ── eBay search ───────────────────────────────────────────────────────────────
CONDITION_MAP = {
    "new":      "NEW",
    "like_new": "LIKE_NEW",
    "used":     "USED_EXCELLENT,USED_GOOD,USED_ACCEPTABLE",
    "any":      None,
}

def search_ebay(token, keywords, max_price, condition):
    cond = CONDITION_MAP.get(condition)
    filters = [
        "buyingOptions:{FIXED_PRICE|BEST_OFFER}",
        f"price:[..{max_price}]",
        "priceCurrency:USD",
    ]
    if cond:
        filters.append(f"conditions:{{{cond}}}")
    resp = requests.get(
        "https://api.ebay.com/buy/browse/v1/item_summary/search",
        params={"q": keywords, "filter": ",".join(filters), "sort": "newlyListed", "limit": "50"},
        headers={"Authorization": f"Bearer {token}", "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("itemSummaries", [])

# ── Filters ───────────────────────────────────────────────────────────────────
def seller_passes(item, min_feedback, min_transactions):
    seller = item.get("seller", {})
    score = seller.get("feedbackPercentage")
    count = seller.get("feedbackScore", 0)
    if score is None:
        return False
    try:
        if float(score) < min_feedback:
            return False
    except ValueError:
        return False
    return int(count) >= min_transactions

def title_passes(title, required_grade, exclude_keywords):
    title_lower = title.lower()
    if required_grade and required_grade.lower() not in title_lower:
        return False
    for kw in (exclude_keywords or []):
        if kw.lower() in title_lower:
            return False
    return True

def match_tier(item, tiers):
    price = float(item.get("price", {}).get("value", 9999999))
    buying_options = set(item.get("buyingOptions", []))
    for tier in tiers:
        if price < float(tier.get("min_price", 0)):
            continue
        if price > float(tier["max_price"]):
            continue
        if set(tier.get("buying_options", ["BUY_IT_NOW"])) & buying_options:
            return tier
    return None

# ── Email ─────────────────────────────────────────────────────────────────────
def send_alert(subject, body):
    resp = requests.post(
        "https://api.sendgrid.com/v3/mail/send",
        headers={"Authorization": f"Bearer {SENDGRID_API_KEY}", "Content-Type": "application/json"},
        json={
            "personalizations": [{"to": [{"email": ALERT_TO_EMAIL}]}],
            "from": {"email": ALERT_FROM_EMAIL},
            "subject": subject,
            "content": [{"type": "text/plain", "value": body}],
        },
        timeout=15,
    )
    if resp.status_code == 202:
        log.info("Email sent: %s", subject)
    else:
        log.error("Email failed: %s %s", resp.status_code, resp.text)

def build_alert(item, tier, alert_cfg):
    title = item.get("title", "Unknown item")
    price = item.get("price", {}).get("value", "?")
    url = item.get("itemWebUrl", "")
    opts = ", ".join(item.get("buyingOptions", []))
    seller = item.get("seller", {})
    subject = f"eBay Alert [{tier['label']}] ${price} — {title[:50]}"
    body = (
        f"Alert: {tier['label']}\n"
        f"Search: {alert_cfg['keywords']}\n\n"
        f"Title: {title}\n"
        f"Price: ${price}\n"
        f"Buying options: {opts}\n"
        f"Seller feedback: {seller.get('feedbackPercentage', '?')}% ({seller.get('feedbackScore', '?')} transactions)\n\n"
        f"View listing:\n{url}"
    )
    return subject, body

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    log.info("eBay Alert Bot starting (GitHub Actions mode)")
    seen = load_seen()
    token = get_ebay_token()
    log.info("eBay token acquired")

    defaults = CONFIG["global_defaults"]
    min_feedback     = float(defaults.get("min_seller_feedback", 95))
    min_transactions = int(defaults.get("min_seller_transactions", 25))
    cooldown_hours   = int(defaults.get("cooldown_hours", 72))
    total_matched    = 0

    for alert_cfg in CONFIG["alerts"]:
        keywords     = alert_cfg["keywords"]
        condition    = alert_cfg.get("condition", "any")
        required_grade = alert_cfg.get("required_grade")
        exclude_kws  = alert_cfg.get("exclude_keywords", [])
        tiers        = alert_cfg.get("tiers", [])

        if not tiers:
            continue

        max_price = max(t["max_price"] for t in tiers)
        log.info("Scanning: '%s' (max $%.2f)", keywords, max_price)

        try:
            items = search_ebay(token, keywords, max_price, condition)
        except Exception as e:
            log.error("Search failed for '%s': %s", keywords, e)
            continue

        log.info("  → %d results returned", len(items))
        matched = 0

        for item in items:
            item_id = item.get("itemId", "")
            if is_on_cooldown(seen, item_id, cooldown_hours):
                continue
            if not seller_passes(item, min_feedback, min_transactions):
                continue
            title = item.get("title", "")
            if not title_passes(title, required_grade, exclude_kws):
                continue
            tier = match_tier(item, tiers)
            if not tier:
                continue
            mark_seen(seen, item_id)
            matched += 1
            total_matched += 1
            subject, body = build_alert(item, tier, alert_cfg)
            log.info("  MATCH [%s] $%s — %s", tier["label"], item.get("price", {}).get("value", "?"), title[:50])
            send_alert(subject, body)

        log.info("  → %d new matches alerted", matched)

    save_seen(seen)
    log.info("Done. Total matches this run: %d", total_matched)

if __name__ == "__main__":
    main()
