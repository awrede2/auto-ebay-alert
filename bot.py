import os
import time
import json
import logging
import requests
import yaml
from datetime import datetime, timedelta
from twilio.rest import Client as TwilioClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger(__name__)

# ── Environment variables (set in Railway) ────────────────────────────────────
EBAY_CLIENT_ID     = os.environ["EBAY_CLIENT_ID"]
EBAY_CLIENT_SECRET = os.environ["EBAY_CLIENT_SECRET"]
TWILIO_SID         = os.environ["TWILIO_ACCOUNT_SID"]
TWILIO_TOKEN       = os.environ["TWILIO_AUTH_TOKEN"]
TWILIO_FROM        = os.environ["TWILIO_FROM_NUMBER"]   # e.g. +18336144069
ALERT_TO_NUMBER    = os.environ["ALERT_TO_NUMBER"]      # your personal number
SCAN_INTERVAL_SEC  = int(os.environ.get("SCAN_INTERVAL_SECONDS", 300))  # default 5 min

# ── Paths (always relative to this script location) ───────────────────────────
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH  = os.environ.get("CONFIG_PATH", os.path.join(BASE_DIR, "alerts.yaml"))
SEEN_FILE    = os.path.join(BASE_DIR, "seen_listings.json")
SELLERS_FILE = os.path.join(BASE_DIR, "seller_cache.json")

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

# ── SMS alert ─────────────────────────────────────────────────────────────────
twilio_client = TwilioClient(TWILIO_SID, TWILIO_TOKEN)

def send_sms(message: str):
    try:
        msg = twilio_client.messages.create(
            body=message,
            from_=TWILIO_FROM,
            to=ALERT_TO_NUMBER,
        )
        log.info("SMS sent: %s", msg.sid)
    except Exception as e:
        log.error("SMS failed: %s", e)

def build_sms(item: dict, tier: dict, alert_cfg: dict) -> str:
    title  = item.get("title", "Unknown item")[:60]
    price  = item.get("price", {}).get("value", "?")
    url    = item.get("itemWebUrl", "")
    opts   = ", ".join(item.get("buyingOptions", []))
    label  = tier.get("label", "Match")
    return (
        f"eBay Alert [{label}]\n"
        f"{title}\n"
        f"${price} — {opts}\n"
        f"Search: {alert_cfg['keywords']}\n"
        f"{url}"
    )

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
            msg = build_sms(item, tier, alert_cfg)
            log.info("  MATCH [%s] $%s — %s",
                     tier["label"],
                     item.get("price", {}).get("value", "?"),
                     title[:50])
            send_sms(msg)

        log.info("  → %d new matches alerted", matched)

def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)

def main():
    log.info("eBay Alert Bot starting. Scan interval: %ds", SCAN_INTERVAL_SEC)
    log.info("Config path: %s", CONFIG_PATH)
    log.info("Config exists: %s", os.path.exists(CONFIG_PATH))
    seen = load_json(SEEN_FILE)

    while True:
        try:
            config = load_config(CONFIG_PATH)
            run_scan(config, seen)
            save_json(SEEN_FILE, seen)
        except Exception as e:
            log.error("Unexpected error during scan: %s", e)

        log.info("Sleeping %d seconds until next scan...", SCAN_INTERVAL_SEC)
        time.sleep(SCAN_INTERVAL_SEC)

if __name__ == "__main__":
    main()
