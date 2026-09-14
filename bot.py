import os
import re
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

# ── Environment variables ─────────────────────────────────────────────────────
EBAY_CLIENT_ID     = os.environ["EBAY_CLIENT_ID"]
EBAY_CLIENT_SECRET = os.environ["EBAY_CLIENT_SECRET"]
RESEND_API_KEY     = os.environ["SENDGRID_API_KEY"]   # variable name kept for compatibility
ALERT_FROM_EMAIL   = os.environ["ALERT_FROM_EMAIL"]
ALERT_TO_EMAIL     = os.environ["ALERT_TO_EMAIL"]

# RUN_MODE: "specific" (Layer 1) or "broad" (Layer 2)
RUN_MODE = os.environ.get("RUN_MODE", "specific")

# ── Global settings ───────────────────────────────────────────────────────────
MAX_PRICE            = 1000
DISCOUNT_THRESHOLD   = 0.30    # alert when 25%+ below market
MIN_SOLD_SAMPLES     = 5       # minimum sold comps to trust the average
TRIM_PCT             = 0.10    # trim top and bottom 10% for avg calculation
COOLDOWN_HOURS       = 1500

SEEN_FILE_SPECIFIC   = "seen_listings.json"
SEEN_FILE_BROAD      = "seen_broad.json"

# ── Shared exclude keywords ───────────────────────────────────────────────────
POKEMON_EXCLUDES = [
    "replica", "fake", "reproduction", "topps", "Beckett", "burger king",
    "2000", "Portuguese", "Spanish", "French", "German", "Italian",
    "Japanese", "Korean", "Chinese", "Foreign", "Reprint", "Boxing",
    "lot", "bundle", "collection", "x2", "x3", "set of", "Base 2", "AGS", "Erika's"
]

W551_EXCLUDES = ["Boxing", "Movie", "Reprint", "lot", "bundle"]

SPORTS_EXCLUDES = [
    "replica", "fake", "reproduction", "lot", "bundle", "collection",
    "x2", "x3", "set of", "reprint", "damaged", "restored", "trimmed"
]

# ── Layer 1 — Specific searches ───────────────────────────────────────────────
SPECIFIC_ALERTS = [
    {
        "keywords": "1999 Charizard 4 PSA 9",
        "condition": "any",
        "exclude_keywords": POKEMON_EXCLUDES,
        "tiers": [
            {"label": "Steal",         "min_price": 1500, "max_price": 2500, "buying_options": ["BUY_IT_NOW"]},
            {"label": "Worth an offer","min_price": 1500, "max_price": 2990, "buying_options": ["BUY_IT_NOW", "BEST_OFFER"]},
        ],
    },
    {
        "keywords": "1999 Charizard 4 PSA 8",
        "condition": "any",
        "exclude_keywords": POKEMON_EXCLUDES,
        "tiers": [
            {"label": "Steal",         "min_price": 600,  "max_price": 1100, "buying_options": ["BUY_IT_NOW"]},
            {"label": "Worth an offer","min_price": 600,  "max_price": 1250, "buying_options": ["BUY_IT_NOW", "BEST_OFFER"]},
        ],
    },
    {
        "keywords": "1999 Charizard 4 PSA 7.5",
        "condition": "any",
        "exclude_keywords": POKEMON_EXCLUDES,
        "tiers": [
            {"label": "Steal",         "min_price": 500,  "max_price": 800,  "buying_options": ["BUY_IT_NOW"]},
            {"label": "Worth an offer","min_price": 500,  "max_price": 1000, "buying_options": ["BUY_IT_NOW", "BEST_OFFER"]},
        ],
    },
    {
        "keywords": "1999 Charizard 4 PSA 7",
        "condition": "any",
        "exclude_keywords": POKEMON_EXCLUDES,
        "tiers": [
            {"label": "Steal",         "min_price": 500,  "max_price": 600,  "buying_options": ["BUY_IT_NOW"]},
            {"label": "Worth an offer","min_price": 500,  "max_price": 698,  "buying_options": ["BUY_IT_NOW", "BEST_OFFER"]},
        ],
    },
    {
        "keywords": "1999 Blastoise 2 PSA 7",
        "condition": "any",
        "exclude_keywords": POKEMON_EXCLUDES,
        "tiers": [
            {"label": "Steal",         "min_price": 100,  "max_price": 165,  "buying_options": ["BUY_IT_NOW"]},
            {"label": "Worth an offer","min_price": 100,  "max_price": 210,  "buying_options": ["BUY_IT_NOW", "BEST_OFFER"]},
        ],
    },
    {
        "keywords": "1999 Blastoise 2 PSA 8",
        "condition": "any",
        "exclude_keywords": POKEMON_EXCLUDES,
        "tiers": [
            {"label": "Steal",         "min_price": 100,  "max_price": 300,  "buying_options": ["BUY_IT_NOW"]},
            {"label": "Worth an offer","min_price": 100,  "max_price": 400,  "buying_options": ["BUY_IT_NOW", "BEST_OFFER"]},
        ],
    },
    {
        "keywords": "1999 Blastoise 2 PSA 9",
        "condition": "any",
        "exclude_keywords": POKEMON_EXCLUDES,
        "tiers": [
            {"label": "Steal",         "min_price": 300,  "max_price": 850,  "buying_options": ["BUY_IT_NOW"]},
            {"label": "Worth an offer","min_price": 300,  "max_price": 990,  "buying_options": ["BUY_IT_NOW", "BEST_OFFER"]},
        ],
    },
    {
        "keywords": "1999 Venusaur 2 PSA 7",
        "condition": "any",
        "exclude_keywords": POKEMON_EXCLUDES,
        "tiers": [
            {"label": "Steal",         "min_price": 75,   "max_price": 150,  "buying_options": ["BUY_IT_NOW"]},
            {"label": "Worth an offer","min_price": 75,   "max_price": 200,  "buying_options": ["BUY_IT_NOW", "BEST_OFFER"]},
        ],
    },
    {
        "keywords": "1999 Venusaur 2 PSA 8",
        "condition": "any",
        "exclude_keywords": POKEMON_EXCLUDES,
        "tiers": [
            {"label": "Steal",         "min_price": 100,  "max_price": 248,  "buying_options": ["BUY_IT_NOW"]},
            {"label": "Worth an offer","min_price": 100,  "max_price": 300,  "buying_options": ["BUY_IT_NOW", "BEST_OFFER"]},
        ],
    },
    {
        "keywords": "1999 Venusaur 2 PSA 9",
        "condition": "any",
        "exclude_keywords": POKEMON_EXCLUDES,
        "tiers": [
            {"label": "Steal",         "min_price": 350,  "max_price": 500,  "buying_options": ["BUY_IT_NOW"]},
            {"label": "Worth an offer","min_price": 350,  "max_price": 600,  "buying_options": ["BUY_IT_NOW", "BEST_OFFER"]},
        ],
    },
    {
        "keywords": "1986 Michael Jordan Fleer 57 PSA 3",
        "condition": "any",
        "exclude_keywords": SPORTS_EXCLUDES,
        "tiers": [
            {"label": "Steal",         "min_price": 3000, "max_price": 4000, "buying_options": ["BUY_IT_NOW"]},
            {"label": "Worth an offer","min_price": 3000, "max_price": 4400, "buying_options": ["BUY_IT_NOW", "BEST_OFFER"]},
        ],
    },
    {
        "keywords": "1921 w551 PSA 8",
        "condition": "any",
        "exclude_keywords": W551_EXCLUDES,
        "tiers": [
            {"label": "w551 Match", "min_price": 0, "max_price": 999999, "buying_options": ["BUY_IT_NOW", "BEST_OFFER"]},
        ],
    },
    {
        "keywords": "1921 w551 PSA 9",
        "condition": "any",
        "exclude_keywords": W551_EXCLUDES,
        "tiers": [
            {"label": "w551 Match", "min_price": 0, "max_price": 999999, "buying_options": ["BUY_IT_NOW", "BEST_OFFER"]},
        ],
    },
    {
        "keywords": "1921 w551 uncut",
        "condition": "any",
        "exclude_keywords": W551_EXCLUDES,
        "tiers": [
            {"label": "w551 Match", "min_price": 0, "max_price": 89999, "buying_options": ["BUY_IT_NOW", "BEST_OFFER"]},
        ],
    },
]

# ── Layer 2 — Broad player searches ──────────────────────────────────────────
PLAYER_SEARCHES = [
    # Basketball
    {"player": "Michael Jordan",           "sport": "Basketball", "max_price": 1000, "min_grade": 7},
    {"player": "Kobe Bryant",              "sport": "Basketball", "max_price": 1000, "min_grade": 7},
    {"player": "LeBron James",             "sport": "Basketball", "max_price": 1000, "min_grade": 8},
    {"player": "Magic Johnson",            "sport": "Basketball", "max_price": 1000, "min_grade": 7},
    {"player": "Larry Bird",               "sport": "Basketball", "max_price": 1000, "min_grade": 7},
    {"player": "Shaquille O'Neal",         "sport": "Basketball", "max_price": 1000, "min_grade": 8},
    {"player": "Charles Barkley",          "sport": "Basketball", "max_price": 1000, "min_grade": 8},
    {"player": "Hakeem Olajuwon",          "sport": "Basketball", "max_price": 1000, "min_grade": 8},
    #{"player": "Dirk Nowitzki",            "sport": "Basketball", "max_price": 1000, "min_grade": 8},
    {"player": "Kevin Durant",             "sport": "Basketball", "max_price": 1000, "min_grade": 8},
    {"player": "Stephen Curry",            "sport": "Basketball", "max_price": 1000, "min_grade": 8},
    {"player": "Giannis Antetokounmpo",    "sport": "Basketball", "max_price": 1000, "min_grade": 8},
    {"player": "Luka Doncic",              "sport": "Basketball", "max_price": 1000, "min_grade": 8},
   # {"player": "Zion Williamson",          "sport": "Basketball", "max_price": 1000, "min_grade": 9},
    {"player": "Shai Gilgeous-Alexander",  "sport": "Basketball", "max_price": 1000, "min_grade": 9},
    {"player": "Nikola Jokic",             "sport": "Basketball", "max_price": 1000, "min_grade": 9},
    {"player": "Victor Wembanyama",        "sport": "Basketball", "max_price": 1000, "min_grade": 9},
    # Baseball
    {"player": "Mickey Mantle",            "sport": "Baseball",   "max_price": 1000, "min_grade": 1},
    {"player": "Babe Ruth",                "sport": "Baseball",   "max_price": 1000, "min_grade": 1},
    {"player": "Hank Aaron",               "sport": "Baseball",   "max_price": 1000, "min_grade": 1},
    {"player": "Willie Mays",              "sport": "Baseball",   "max_price": 1000, "min_grade": 1},
    {"player": "Roberto Clemente",         "sport": "Baseball",   "max_price": 1000, "min_grade": 1},
    {"player": "Cal Ripken Jr",            "sport": "Baseball",   "max_price": 1000, "min_grade": 8},
    {"player": "Ken Griffey Jr",           "sport": "Baseball",   "max_price": 1000, "min_grade": 8},
    {"player": "Derek Jeter",              "sport": "Baseball",   "max_price": 1000, "min_grade": 8},
    {"player": "Mike Trout",               "sport": "Baseball",   "max_price": 1000, "min_grade": 9},
    {"player": "Ronald Acuna",             "sport": "Baseball",   "max_price": 1000, "min_grade": 9},
    {"player": "Carlos LaGrange",          "sport": "Baseball",   "max_price": 1000, "min_grade": 9},
    {"player": "Shohei Ohtani",            "sport": "Baseball",   "max_price": 1000, "min_grade": 9},
    {"player": "Juan Soto",                "sport": "Baseball",   "max_price": 1000, "min_grade": 9},
    # Football
    {"player": "Patrick Mahomes",          "sport": "Football",   "max_price": 1000, "min_grade": 9},
    {"player": "Joe Burrow",               "sport": "Football",   "max_price": 1000, "min_grade": 9},
    {"player": "Justin Herbert",           "sport": "Football",   "max_price": 1000, "min_grade": 9},
    {"player": "Lamar Jackson",            "sport": "Football",   "max_price": 1000, "min_grade": 9},
    {"player": "Josh Allen",               "sport": "Football",   "max_price": 1000, "min_grade": 9},
    {"player": "Justin Jefferson",         "sport": "Football",   "max_price": 1000, "min_grade": 9},
    {"player": "Jayden Daniels",           "sport": "Football",   "max_price": 1000, "min_grade": 9},
    {"player": "Drake Maye",               "sport": "Football",   "max_price": 1000, "min_grade": 9},
    {"player": "Tom Brady",                "sport": "Football",   "max_price": 1000, "min_grade": 8},
    {"player": "Justin Herbert",           "sport": "Football",   "max_price": 1000, "min_grade": 9},
    {"player": "Bo Nix",                   "sport": "Football",   "max_price": 1000, "min_grade": 9},
    {"player": "Caleb Williams",           "sport": "Football",   "max_price": 1000, "min_grade": 9},
    # Pokemon
    {"player": "Charizard",                "sport": "Pokemon",    "max_price": 500,  "min_grade": 7},
    {"player": "Blastoise",                "sport": "Pokemon",    "max_price": 500,  "min_grade": 7},
    {"player": "Venusaur",                 "sport": "Pokemon",    "max_price": 500,  "min_grade": 7},
    {"player": "Pikachu",                  "sport": "Pokemon",    "max_price": 300,  "min_grade": 8},
    {"player": "Mewtwo",                   "sport": "Pokemon",    "max_price": 500,  "min_grade": 7},
    {"player": "Gengar",                   "sport": "Pokemon",    "max_price": 300,  "min_grade": 8},
    {"player": "Lugia",                    "sport": "Pokemon",    "max_price": 500,  "min_grade": 8},
    {"player": "Ho-Oh",                    "sport": "Pokemon",    "max_price": 500,  "min_grade": 8},
    {"player": "Rayquaza",                 "sport": "Pokemon",    "max_price": 300,  "min_grade": 8},
    {"player": "Umbreon",                  "sport": "Pokemon",    "max_price": 300,  "min_grade": 8},
    {"player": "Espeon",                   "sport": "Pokemon",    "max_price": 300,  "min_grade": 8},
]

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

# ── Seen listings ─────────────────────────────────────────────────────────────
def load_seen(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_seen(seen, path):
    with open(path, "w") as f:
        json.dump(seen, f, indent=2)

def is_on_cooldown(seen, item_id):
    if item_id not in seen:
        return False
    alerted_at = datetime.fromisoformat(seen[item_id])
    if alerted_at.tzinfo is None:
        alerted_at = alerted_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) < alerted_at + timedelta(hours=COOLDOWN_HOURS)

def mark_seen(seen, item_id):
    seen[item_id] = datetime.now(timezone.utc).isoformat()

# ── Grade verification ────────────────────────────────────────────────────────
PSA_GRADE_PATTERN = re.compile(
    r'\bPSA\s*(10|[1-9](?:\.5)?)\b', re.IGNORECASE
)

def extract_grade_from_keywords(keywords):
    """Extract the PSA grade we are searching for from the keyword string."""
    m = PSA_GRADE_PATTERN.search(keywords)
    return m.group(1).strip() if m else None

def grade_matches_title(title, required_grade):
    """
    Confirm:
    1. The required grade appears in the title.
    2. No conflicting PSA grade appears in the title.
    e.g. searching PSA 8 — reject titles containing PSA 7, PSA 9 etc.
    """
    if required_grade is None:
        return True  # no grade in keywords, skip check

    title_lower = title.lower()
    required_lower = required_grade.lower()

    # Must contain the required grade
    if f"psa {required_lower}" not in title_lower and f"psa{required_lower}" not in title_lower:
        return False

    # Must not contain any OTHER PSA grade
    all_grades = PSA_GRADE_PATTERN.findall(title)
    for g in all_grades:
        if g.strip().lower() != required_lower:
            log.debug("Grade conflict in title: wanted PSA %s, found PSA %s — '%s'",
                      required_grade, g, title[:60])
            return False

    return True

# ── Title / seller filters ────────────────────────────────────────────────────
def title_passes(title, exclude_keywords):
    title_lower = title.lower()
    for kw in (exclude_keywords or []):
        if kw.lower() in title_lower:
            return False
    return True

def seller_passes(item, min_feedback=95, min_transactions=15):
    seller = item.get("seller", {})
    score  = seller.get("feedbackPercentage")
    count  = seller.get("feedbackScore", 0)
    if score is None:
        return False
    try:
        if float(score) < min_feedback:
            return False
    except ValueError:
        return False
    return int(count) >= min_transactions

# ── Tier matching ─────────────────────────────────────────────────────────────
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

# ── eBay search ───────────────────────────────────────────────────────────────
CONDITION_MAP = {
    "new":      "NEW",
    "like_new": "LIKE_NEW",
    "used":     "USED_EXCELLENT,USED_GOOD,USED_ACCEPTABLE",
    "any":      None,
}

def search_active(token, keywords, max_price, condition="any"):
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
        params={"q": keywords, "filter": ",".join(filters),
                "sort": "newlyListed", "limit": "50"},
        headers={"Authorization": f"Bearer {token}",
                 "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("itemSummaries", [])

# ── Sold listing market price ─────────────────────────────────────────────────
LOT_KEYWORDS = ["lot", "bundle", "collection", "x2", "x3", "set of",
                 "reprint", "damaged", "restored", "trimmed"]

def get_market_price(keywords, max_price):
    """
    Query eBay Finding API for recently sold listings.
    Returns trimmed mean price or None if insufficient data.
    """
    try:
        resp = requests.get(
            "https://svcs.ebay.com/services/search/FindingService/v1",
            params={
                "OPERATION-NAME":                "findCompletedItems",
                "SERVICE-VERSION":               "1.0.0",
                "SECURITY-APPNAME":              EBAY_CLIENT_ID,
                "RESPONSE-DATA-FORMAT":          "JSON",
                "keywords":                      keywords,
                "itemFilter(0).name":            "SoldItemsOnly",
                "itemFilter(0).value":           "true",
                "itemFilter(1).name":            "ListingType",
                "itemFilter(1).value":           "FixedPrice",
                "itemFilter(2).name":            "MinPrice",
                "itemFilter(2).value":           "10",
                "itemFilter(3).name":            "MaxPrice",
                "itemFilter(3).value":           str(max_price),
                "itemFilter(4).name":            "Currency",
                "itemFilter(4).value":           "USD",
                "sortOrder":                     "EndTimeSoonest",
                "paginationInput.entriesPerPage":"25",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data  = resp.json()
        items = (
            data.get("findCompletedItemsResponse", [{}])[0]
                .get("searchResult", [{}])[0]
                .get("item", [])
        )

        prices = []
        for item in items:
            try:
                title = item.get("title", [""])[0].lower() \
                    if isinstance(item.get("title"), list) \
                    else str(item.get("title", "")).lower()

                # Skip lots and outlier listings
                if any(kw in title for kw in LOT_KEYWORDS):
                    continue

                price = float(
                    item["sellingStatus"][0]["currentPrice"][0]["__value__"]
                )
                if 10 < price <= max_price:
                    prices.append(price)
            except (KeyError, ValueError, IndexError):
                continue

        if len(prices) < MIN_SOLD_SAMPLES:
            log.info("    Not enough sold comps (%d found, need %d)",
                     len(prices), MIN_SOLD_SAMPLES)
            return None

        # Trimmed mean — remove top and bottom TRIM_PCT
        prices.sort()
        trim = max(1, int(len(prices) * TRIM_PCT))
        trimmed = prices[trim:-trim] if len(prices) > trim * 2 else prices
        avg = sum(trimmed) / len(trimmed)
        log.info("    Market avg: $%.2f (%d comps, trimmed from %d)",
                 avg, len(trimmed), len(prices))
        return avg

    except Exception as e:
        log.warning("    Sold listing lookup failed: %s", e)
        return None

# ── Email ─────────────────────────────────────────────────────────────────────
def send_alert(subject, body):
    resp = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {RESEND_API_KEY}",
                 "Content-Type": "application/json"},
        json={
            "from":    ALERT_FROM_EMAIL,
            "to":      [ALERT_TO_EMAIL],
            "subject": subject,
            "text":    body,
        },
        timeout=15,
    )
    if resp.status_code == 200:
        log.info("Email sent: %s", subject)
    else:
        log.error("Email failed: %s %s", resp.status_code, resp.text)

def build_specific_alert(item, tier, alert_cfg):
    title  = item.get("title", "Unknown item")
    price  = item.get("price", {}).get("value", "?")
    url    = item.get("itemWebUrl", "")
    opts   = ", ".join(item.get("buyingOptions", []))
    seller = item.get("seller", {})
    subject = f"eBay Alert [{tier['label']}] ${price} — {title[:50]}"
    body = (
        f"Alert: {tier['label']}\n"
        f"Search: {alert_cfg['keywords']}\n\n"
        f"Title: {title}\n"
        f"Price: ${price}\n"
        f"Buying options: {opts}\n"
        f"Seller: {seller.get('feedbackPercentage','?')}% "
        f"({seller.get('feedbackScore','?')} transactions)\n\n"
        f"View listing:\n{url}"
    )
    return subject, body

def build_broad_alert(item, player, sport, price, market_price, discount_pct):
    title  = item.get("title", "Unknown item")
    url    = item.get("itemWebUrl", "")
    opts   = ", ".join(item.get("buyingOptions", []))
    seller = item.get("seller", {})
    subject = (f"🔥 {sport} Deal! {discount_pct:.0f}% Below Market — "
               f"${price:.2f} {player}")
    body = (
        f"UNDERVALUED CARD — {sport}\n"
        f"Player/Character: {player}\n\n"
        f"Title: {title}\n"
        f"Listed price:    ${price:.2f}\n"
        f"Market average:  ${market_price:.2f}\n"
        f"Discount:        {discount_pct:.1f}% below market\n"
        f"Est. profit:     ~${market_price - price:.2f}\n"
        f"Buying options:  {opts}\n"
        f"Seller: {seller.get('feedbackPercentage','?')}% "
        f"({seller.get('feedbackScore','?')} transactions)\n\n"
        f"View listing:\n{url}"
    )
    return subject, body

# ── Layer 1 — Specific searches ───────────────────────────────────────────────
def run_specific(token, seen):
    log.info("=== LAYER 1: Specific searches ===")
    total = 0

    for alert_cfg in SPECIFIC_ALERTS:
        keywords    = alert_cfg["keywords"]
        condition   = alert_cfg.get("condition", "any")
        exclude_kws = alert_cfg.get("exclude_keywords", [])
        tiers       = alert_cfg.get("tiers", [])

        if not tiers:
            continue

        # Extract expected grade from keywords for verification
        expected_grade = extract_grade_from_keywords(keywords)
        max_price = max(t["max_price"] for t in tiers)
        log.info("Scanning: '%s' (max $%.2f, grade check: PSA %s)",
                 keywords, max_price, expected_grade or "none")

        try:
            items = search_active(token, keywords, max_price, condition)
        except Exception as e:
            log.error("  Search failed: %s", e)
            continue

        log.info("  → %d results returned", len(items))
        matched = 0

        for item in items:
            item_id = item.get("itemId", "")
            if is_on_cooldown(seen, item_id):
                continue
            if not seller_passes(item):
                continue

            title = item.get("title", "")

            # Grade verification — must match, no conflicting grades
            if not grade_matches_title(title, expected_grade):
                log.debug("  Grade mismatch — skipping: %s", title[:60])
                continue

            if not title_passes(title, exclude_kws):
                continue

            tier = match_tier(item, tiers)
            if not tier:
                continue

            mark_seen(seen, item_id)
            matched += 1
            total += 1
            subject, body = build_specific_alert(item, tier, alert_cfg)
            log.info("  MATCH [%s] $%s — %s",
                     tier["label"],
                     item.get("price", {}).get("value", "?"),
                     title[:50])
            send_alert(subject, body)

        log.info("  → %d new matches alerted", matched)

    return total

# ── Layer 2 — Broad player searches ──────────────────────────────────────────
def run_broad(token, seen):
    log.info("=== LAYER 2: Broad player searches ===")
    total = 0

    for cfg in PLAYER_SEARCHES:
        player    = cfg["player"]
        sport     = cfg["sport"]
        max_price = cfg["max_price"]
        min_grade = cfg["min_grade"]

        keywords = f"{player} PSA graded rookie card"
        if sport == "Pokemon":
            keywords = f"{player} PSA holo"

        log.info("Scanning: %s (%s, max $%d, min grade PSA %d)",
                 player, sport, max_price, min_grade)

        try:
            items = search_active(token, keywords, max_price)
        except Exception as e:
            log.error("  Search failed: %s", e)
            continue

        log.info("  → %d results returned", len(items))
        matched = 0

        for item in items:
            item_id = item.get("itemId", "")
            if is_on_cooldown(seen, item_id):
                continue
            if not seller_passes(item):
                continue

            title = item.get("title", "")

            # Skip lots and junk
            if not title_passes(title, LOT_KEYWORDS):
                continue

            # Extract grade from title
            grade_matches = PSA_GRADE_PATTERN.findall(title)
            if not grade_matches:
                continue  # no PSA grade in title, skip

            # Must have exactly one grade in the title
            if len(grade_matches) > 1:
                log.debug("  Multiple grades in title, skipping: %s", title[:60])
                continue

            grade_num = float(grade_matches[0].replace(" ", ""))
            if grade_num < min_grade:
                continue  # below minimum grade threshold

            price = float(item.get("price", {}).get("value", 0))
            if price <= 0:
                continue

            # Get market price from sold listings
            sold_keywords = f"{player} PSA {int(grade_num)}"
            market_price  = get_market_price(sold_keywords, max_price)
            if market_price is None:
                continue

            # Check discount threshold
            discount_pct = ((market_price - price) / market_price) * 100
            if discount_pct < DISCOUNT_THRESHOLD * 100:
                continue

            mark_seen(seen, item_id)
            matched += 1
            total += 1
            subject, body = build_broad_alert(
                item, player, sport, price, market_price, discount_pct
            )
            log.info("  MATCH! $%.2f vs market $%.2f (%.1f%% off) — %s",
                     price, market_price, discount_pct, title[:50])
            send_alert(subject, body)

        log.info("  → %d new matches alerted", matched)

    return total

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    log.info("eBay Alert Bot starting — mode: %s", RUN_MODE)
    token = get_ebay_token()
    log.info("eBay token acquired")

    if RUN_MODE == "specific":
        seen = load_seen(SEEN_FILE_SPECIFIC)
        total = run_specific(token, seen)
        save_seen(seen, SEEN_FILE_SPECIFIC)
    elif RUN_MODE == "broad":
        seen = load_seen(SEEN_FILE_BROAD)
        total = run_broad(token, seen)
        save_seen(seen, SEEN_FILE_BROAD)
    else:
        log.error("Unknown RUN_MODE: %s", RUN_MODE)
        return

    log.info("Done. Total matches this run: %d", total)

if __name__ == "__main__":
    main()
