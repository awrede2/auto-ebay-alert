import os
import time
import json
import logging
import requests
from datetime import datetime, timedelta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger(__name__)

# ── Environment variables (set in Railway) ────────────────────────────────────
EBAY_CLIENT_ID     = os.environ["EBAY_CLIENT_ID"]
EBAY_CLIENT_SECRET = os.environ["EBAY_CLIENT_SECRET"]
SENDGRID_API_KEY   = os.environ["SENDGRID_API_KEY"]     # SendGrid API key
ALERT_FROM_EMAIL   = os.environ["ALERT_FROM_EMAIL"]     # verified sender email
ALERT_TO_EMAIL     = os.environ["ALERT_TO_EMAIL"]       # email to receive alerts
SCAN_INTERVAL_SEC  = int(os.environ.get("SCAN_INTERVAL_SECONDS", 300))  # 5 min default

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
SEEN_FILE    = os.path.join(BASE_DIR, "seen_listings.json")
SELLERS_FILE = os.path.join(BASE_DIR, "seller_cache.json")

# ── Inline config (edit searches here, then commit to GitHub) ─────────────────
CONFIG = {
    "global_defaults": {
        "min_seller_feedback": 95,
        "min_seller_transactions": 15,
        "cooldown_hours": 2400,
    },
    "alerts": [
                {
            "keywords": "1999 Charizard 4 PSA 9",
            "condition": "any",
            "exclude_keywords": ["replica", "fake", "reproduction", "topps", "Beckett", "burger king"],
            "tiers": [
                {"label": "Steal",        "min_price": 1500, "max_price": 2500, "buying_options": ["BUY_IT_NOW"]},
                {"label": "Worth an offer","min_price": 1500, "max_price": 2750, "buying_options": ["BUY_IT_NOW", "BEST_OFFER"]},
            ],
        },
        {
            "keywords": "1999 Charizard 4 PSA 8",
            "condition": "any",
            "exclude_keywords": ["replica", "fake", "reproduction", "topps", "Beckett", "burger king", "2000"],
            "tiers": [
                {"label": "Steal",        "min_price": 600, "max_price": 1100, "buying_options": ["BUY_IT_NOW"]},
                {"label": "Worth an offer","min_price": 600, "max_price": 1250, "buying_options": ["BUY_IT_NOW", "BEST_OFFER"]},
            ],
        },
                {
            "keywords": "1999 Charizard 4 PSA 7.5",
            "condition": "any",
            "exclude_keywords": ["replica", "fake", "reproduction", "topps", "Beckett", "burger king", "2000"],
            "tiers": [
                {"label": "Steal",        "min_price": 500, "max_price": 800, "buying_options": ["BUY_IT_NOW"]},
                {"label": "Worth an offer","min_price": 500, "max_price": 1000, "buying_options": ["BUY_IT_NOW", "BEST_OFFER"]},
            ],
        },
        {
            "keywords": "1999 Charizard 4 PSA 7",
            "condition": "any",
            "exclude_keywords": ["replica", "fake", "reproduction", "topps", "Beckett", "burger king", "2000"],
            "tiers": [
                {"label": "Steal",        "min_price": 500, "max_price": 600, "buying_options": ["BUY_IT_NOW"]},
                {"label": "Worth an offer","min_price": 500, "max_price": 698, "buying_options": ["BUY_IT_NOW", "BEST_OFFER"]},
            ],
        },
                        {
            "keywords": "1986 Michael Jordan Fleer 57 PSA 3",
            "condition": "any",
            "exclude_keywords": ["replica", "fake", "reproduction", "sticker"],
            "tiers": [
                {"label": "Steal",        "min_price": 3000, "max_price": 4000, "buying_options": ["BUY_IT_NOW"]},
                {"label": "Worth an offer","min_price": 3000, "max_price": 4400, "buying_options": ["BUY_IT_NOW", "BEST_OFFER"]},
            ],
        },
        {
            "keywords": "1921 w551 PSA 8",
            "condition": "any",
            "exclude_keywords": ["Boxing", "Movie"],
            "tiers": [
                {"label": "w551 Match", "min_price": 0, "max_price": 999999, "buying_options": ["BUY_IT_NOW", "BEST_OFFER"]},
            ],
        },
                {
            "keywords": "1921 w551 PSA 9",
            "condition": "any",
            "exclude_keywords": ["Boxing", "Movie"],
            "tiers": [
                {"label": "w551 Match", "min_price": 0, "max_price": 999999, "buying_options": ["BUY_IT_NOW", "BEST_OFFER"]},
            ],
        },
                        {
            "keywords": "1921 w551 uncut",
            "condition": "any",
            "exclude_keywords": ["Boxing", "Movie"],
            "tiers": [
                {"label": "w551 Match", "min_price": 0, "max_price": 999999, "buying_options": ["BUY_IT_NOW", "BEST_OFFER"]},
            ],
        },
    ],
}

# ── eBay OAuth ────────────────────────────────────────────────────────────────
_ebay_token     = None
_ebay_token_exp = datetime.utcnow()

def get_ebay_token():
    global _ebay_token, _ebay_token_exp
    if _ebay_token and datetime.utcnow() < _ebay_token_exp:
        return _ebay_token
    log.info("Refreshing eBay OAuth token...")
    resp = requests.post(
        "https://api.ebay.com/identity/v1/oauth2/token",
        auth=(EBAY_CLIENT_ID, EBAY_CLIENT_SECRET),
        data={"grant_type": "client_credentials",
              "scope": "https://api.ebay.com/oauth/api_scope"},
    )
    resp.raise_for_status()
    data = resp.json()
    _ebay_token     = data["access_token"]
    _ebay_token_exp = datetime.utcnow() + timedelta(seconds=data["expires_in"] - 60)
    log.info("eBay token refreshed, expires in ~%d minutes.", data["expires_in"] // 60)
    return _ebay_token

# ── Persistent state helpers ──────────────────────────────────────────────────
def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

# ── Cooldown tracker ──────────────────────────────────────────────────────────
def is_on_cooldown(seen: dict, item_id: str, cooldown_hours: int) -> bool:
    if item_id not in seen:
        return False
    alerted_at = datetime.fromisoformat(seen[item_id])
    return datetime.utcnow() < alerted_at + timedelta(hours=cooldown_hours)

def mark_seen(seen: dict, item_id: str):
    seen[item_id] = datetime.utcnow().isoformat()

# ── eBay search ───────────────────────────────────────────────────────────────
CONDITION_MAP = {
    "new":      "NEW",
    "like_new": "LIKE_NEW",
    "used":     "USED_EXCELLENT,USED_GOOD,USED_ACCEPTABLE",
    "any":      None,
}

def search_ebay(keywords: str, max_price: float, condition: str) -> list:
    token  = get_ebay_token()
    cond   = CONDITION_MAP.get(condition)
    filters = [
        "buyingOptions:{FIXED_PRICE|BEST_OFFER}",
        f"price:[..{max_price}]",
        "priceCurrency:USD",
    ]
    if cond:
        filters.append(f"conditions:{{{cond}}}")

    params = {
        "q":      keywords,
        "filter": ",".join(filters),
        "sort":   "newlyListed",
        "limit":  "50",
    }
    headers = {
        "Authorization":            f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID":  "EBAY_US",
        "Content-Type":             "application/json",
    }
    resp = requests.get(
        "https://api.ebay.com/buy/browse/v1/item_summary/search",
        params=params,
        headers=headers,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("itemSummaries", [])

# ── Seller filter ─────────────────────────────────────────────────────────────
def seller_passes(item: dict, min_feedback: float, min_transactions: int) -> bool:
    seller = item.get("seller", {})
    score  = seller.get("feedbackPercentage")
    count  = seller.get("feedbackScore", 0)
    if score is None:
        return False
    try:
        if float(score) < min_feedback:
            log.debug("Seller %s rejected: feedback %.1f%% < %.1f%%",
                      seller.get("username"), float(score), min_feedback)
            return False
    except ValueError:
        return False
    if int(count) < min_transactions:
        log.debug("Seller %s rejected: %d transactions < %d",
                  seller.get("username"), int(count), min_transactions)
        return False
    return True

# ── Title keyword checks ──────────────────────────────────────────────────────
def title_passes(title: str, required_grade: str | None, exclude_keywords: list) -> bool:
    title_lower = title.lower()
    if required_grade and required_grade.lower() not in title_lower:
        return False
    for kw in (exclude_keywords or []):
        if kw.lower() in title_lower:
            log.debug("Title excluded by keyword '%s': %s", kw, title)
            return False
    return True

# ── Tier matching ─────────────────────────────────────────────────────────────
def match_tier(item: dict, tiers: list) -> dict | None:
    price          = float(item.get("price", {}).get("value", 9999999))
    buying_options = set(item.get("buyingOptions", []))
    for tier in tiers:
        min_price = float(tier.get("min_price", 0))
        max_price = float(tier["max_price"])
        if price < min_price:
            log.debug("Price $%.2f below min_price $%.2f, skipping.", price, min_price)
            continue
        if price > max_price:
            continue
        required_options = set(tier.get("buying_options", ["BUY_IT_NOW"]))
        if required_options & buying_options:
            return tier
    return None

# ── Email alert ───────────────────────────────────────────────────────────────
def send_alert(subject: str, body: str):
    try:
        resp = requests.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={
                "Authorization": f"Bearer {SENDGRID_API_KEY}",
                "Content-Type": "application/json",
            },
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
    except Exception as e:
        log.error("Email failed: %s", e)

def build_alert(item: dict, tier: dict, alert_cfg: dict) -> tuple:
    title  = item.get("title", "Unknown item")
    price  = item.get("price", {}).get("value", "?")
    url    = item.get("itemWebUrl", "")
    opts   = ", ".join(item.get("buyingOptions", []))
    label  = tier.get("label", "Match")
    seller = item.get("seller", {})
    feedback = seller.get("feedbackPercentage", "?")
    transactions = seller.get("feedbackScore", "?")
    subject = f"eBay Alert [{label}] ${price} — {title[:50]}"
    body = (
        f"Alert: {label}\n"
        f"Search: {alert_cfg['keywords']}\n\n"
        f"Title: {title}\n"
        f"Price: ${price}\n"
        f"Buying options: {opts}\n"
        f"Seller feedback: {feedback}% ({transactions} transactions)\n\n"
        f"View listing:\n{url}"
    )
    return subject, body

# ── Main scan loop ────────────────────────────────────────────────────────────
def run_scan(config: dict, seen: dict):
    defaults = config.get("global_defaults", {})
    min_feedback     = float(defaults.get("min_seller_feedback", 95))
    min_transactions = int(defaults.get("min_seller_transactions", 25))
    cooldown_hours   = int(defaults.get("cooldown_hours", 24))

    for alert_cfg in config.get("alerts", []):
        keywords       = alert_cfg["keywords"]
        condition      = alert_cfg.get("condition", "any")
        required_grade = alert_cfg.get("required_grade")
        exclude_kws    = alert_cfg.get("exclude_keywords", [])
        tiers          = alert_cfg.get("tiers", [])

        if not tiers:
            log.warning("Alert '%s' has no tiers defined, skipping.", keywords)
            continue

        max_price = max(t["max_price"] for t in tiers)
        log.info("Scanning: '%s' (max $%.2f)", keywords, max_price)

        try:
            items = search_ebay(keywords, max_price, condition)
        except Exception as e:
            log.error("eBay search failed for '%s': %s", keywords, e)
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
            subject, body = build_alert(item, tier, alert_cfg)
            log.info("  MATCH [%s] $%s — %s",
                     tier["label"],
                     item.get("price", {}).get("value", "?"),
                     title[:50])
            send_alert(subject, body)

        log.info("  → %d new matches alerted", matched)

def main():
    log.info("eBay Alert Bot starting. Scan interval: %ds", SCAN_INTERVAL_SEC)
    seen = load_json(SEEN_FILE)

    while True:
        try:
            run_scan(CONFIG, seen)
            save_json(SEEN_FILE, seen)
        except Exception as e:
            log.error("Unexpected error during scan: %s", e)

        log.info("Sleeping %d seconds until next scan...", SCAN_INTERVAL_SEC)
        time.sleep(SCAN_INTERVAL_SEC)

if __name__ == "__main__":
    main()
