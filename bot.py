import os
import re
import json
import logging
import requests
import time
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
RESEND_API_KEY     = os.environ["SENDGRID_API_KEY"]
ALERT_FROM_EMAIL   = os.environ["ALERT_FROM_EMAIL"]
ALERT_TO_EMAIL     = os.environ["ALERT_TO_EMAIL"]
RUN_MODE           = os.environ.get("RUN_MODE", "specific")
 
# ── Global settings ───────────────────────────────────────────────────────────
DISCOUNT_THRESHOLD = 0.35
MIN_SOLD_SAMPLES   = 3
TRIM_PCT           = 0.10
COOLDOWN_HOURS     = 1500
SEEN_FILE_SPECIFIC = "seen_listings.json"
SEEN_FILE_BROAD    = "seen_broad.json"
 
# ── Known brands/sets by sport ────────────────────────────────────────────────
SPORT_BRANDS = {
    "Basketball": [
        "Topps Chrome", "Bowman Chrome", "Panini Prizm", "Panini Select",
        "Panini Mosaic", "Panini Hoops", "Panini Contenders", "Panini Optic",
        "Panini National Treasures", "Panini Immaculate", "Panini",
        "Fleer Ultra", "Fleer", "Topps", "Upper Deck", "Bowman",
        "SkyBox", "Stadium Club", "Hoops",
    ],
    "Baseball": [
        "Topps Chrome", "Bowman Chrome", "Topps Heritage", "Topps Finest",
        "Topps Allen Ginter", "Topps Gypsy Queen", "Topps Stadium Club",
        "Topps", "Bowman", "Fleer", "Donruss", "Upper Deck", "Score",
    ],
    "Football": [
        "Panini Prizm", "Panini Select", "Panini Mosaic", "Panini Contenders",
        "Panini Optic", "Panini National Treasures", "Panini Immaculate",
        "Panini", "Topps Chrome", "Topps", "Bowman", "Upper Deck",
        "Fleer", "Donruss", "Score",
    ],
    "Pokemon": [
        "Base Set Unlimited", "Shadowless Base Set", "Base Set 2",
        "Base Set", "Jungle", "Fossil", "Team Rocket", "Gym Heroes",
        "Gym Challenge", "Neo Genesis", "Neo Discovery", "Neo Revelation",
        "Neo Destiny", "Legendary Collection", "Expedition", "Aquapolis",
        "Skyridge", "Hidden Fates", "Shining Fates", "Champion's Path",
        "Evolving Skies", "Brilliant Stars", "Silver Tempest", "Crown Zenith",
    ],
}
 
# ── Shared exclude keywords ───────────────────────────────────────────────────
POKEMON_EXCLUDES = [
    "replica", "fake", "reproduction", "topps", "Beckett", "burger king",
    "2000", "Portuguese", "Spanish", "French", "German", "Italian",
    "Japanese", "Korean", "Chinese", "Foreign", "Reprint", "Boxing",
    "lot", "bundle", "collection", "x2", "x3", "set of", "Base 2",
    "AGS", "Erika's",
]
W551_EXCLUDES  = ["Boxing", "Movie", "Reprint", "lot", "bundle"]
SPORTS_EXCLUDES = [
    "replica", "fake", "reproduction", "lot", "bundle", "collection",
    "x2", "x3", "set of", "reprint", "damaged", "restored", "trimmed",
]
LOT_KEYWORDS = [
    "lot", "bundle", "collection", "x2", "x3", "set of",
    "reprint", "damaged", "restored", "trimmed",
]
 
# ── Layer 1 specific alerts ───────────────────────────────────────────────────
SPECIFIC_ALERTS = [
    {"keywords": "1999 Charizard 4 PSA 9",   "condition": "any", "exclude_keywords": POKEMON_EXCLUDES,
     "tiers": [{"label": "Steal",         "min_price": 1500, "max_price": 2500, "buying_options": ["BUY_IT_NOW"]},
               {"label": "Worth an offer","min_price": 1500, "max_price": 2990, "buying_options": ["BUY_IT_NOW","BEST_OFFER"]}]},
    {"keywords": "1999 Charizard 4 PSA 8",   "condition": "any", "exclude_keywords": POKEMON_EXCLUDES,
     "tiers": [{"label": "Steal",         "min_price": 600,  "max_price": 1100, "buying_options": ["BUY_IT_NOW"]},
               {"label": "Worth an offer","min_price": 600,  "max_price": 1250, "buying_options": ["BUY_IT_NOW","BEST_OFFER"]}]},
    {"keywords": "1999 Charizard 4 PSA 7.5", "condition": "any", "exclude_keywords": POKEMON_EXCLUDES,
     "tiers": [{"label": "Steal",         "min_price": 500,  "max_price": 800,  "buying_options": ["BUY_IT_NOW"]},
               {"label": "Worth an offer","min_price": 500,  "max_price": 1000, "buying_options": ["BUY_IT_NOW","BEST_OFFER"]}]},
    {"keywords": "1999 Charizard 4 PSA 7",   "condition": "any", "exclude_keywords": POKEMON_EXCLUDES,
     "tiers": [{"label": "Steal",         "min_price": 500,  "max_price": 600,  "buying_options": ["BUY_IT_NOW"]},
               {"label": "Worth an offer","min_price": 500,  "max_price": 698,  "buying_options": ["BUY_IT_NOW","BEST_OFFER"]}]},
    {"keywords": "1999 Blastoise 2 PSA 7",   "condition": "any", "exclude_keywords": POKEMON_EXCLUDES,
     "tiers": [{"label": "Steal",         "min_price": 100,  "max_price": 165,  "buying_options": ["BUY_IT_NOW"]},
               {"label": "Worth an offer","min_price": 100,  "max_price": 210,  "buying_options": ["BUY_IT_NOW","BEST_OFFER"]}]},
    {"keywords": "1999 Blastoise 2 PSA 8",   "condition": "any", "exclude_keywords": POKEMON_EXCLUDES,
     "tiers": [{"label": "Steal",         "min_price": 100,  "max_price": 300,  "buying_options": ["BUY_IT_NOW"]},
               {"label": "Worth an offer","min_price": 100,  "max_price": 400,  "buying_options": ["BUY_IT_NOW","BEST_OFFER"]}]},
    {"keywords": "1999 Blastoise 2 PSA 9",   "condition": "any", "exclude_keywords": POKEMON_EXCLUDES,
     "tiers": [{"label": "Steal",         "min_price": 300,  "max_price": 850,  "buying_options": ["BUY_IT_NOW"]},
               {"label": "Worth an offer","min_price": 300,  "max_price": 990,  "buying_options": ["BUY_IT_NOW","BEST_OFFER"]}]},
    {"keywords": "1999 Venusaur 2 PSA 7",    "condition": "any", "exclude_keywords": POKEMON_EXCLUDES,
     "tiers": [{"label": "Steal",         "min_price": 75,   "max_price": 150,  "buying_options": ["BUY_IT_NOW"]},
               {"label": "Worth an offer","min_price": 75,   "max_price": 200,  "buying_options": ["BUY_IT_NOW","BEST_OFFER"]}]},
    {"keywords": "1999 Venusaur 2 PSA 8",    "condition": "any", "exclude_keywords": POKEMON_EXCLUDES,
     "tiers": [{"label": "Steal",         "min_price": 100,  "max_price": 248,  "buying_options": ["BUY_IT_NOW"]},
               {"label": "Worth an offer","min_price": 100,  "max_price": 300,  "buying_options": ["BUY_IT_NOW","BEST_OFFER"]}]},
    {"keywords": "1999 Venusaur 2 PSA 9",    "condition": "any", "exclude_keywords": POKEMON_EXCLUDES,
     "tiers": [{"label": "Steal",         "min_price": 350,  "max_price": 500,  "buying_options": ["BUY_IT_NOW"]},
               {"label": "Worth an offer","min_price": 350,  "max_price": 600,  "buying_options": ["BUY_IT_NOW","BEST_OFFER"]}]},
    {"keywords": "1986 Michael Jordan Fleer 57 PSA 3", "condition": "any", "exclude_keywords": SPORTS_EXCLUDES,
     "tiers": [{"label": "Steal",         "min_price": 3000, "max_price": 4000, "buying_options": ["BUY_IT_NOW"]},
               {"label": "Worth an offer","min_price": 3000, "max_price": 4400, "buying_options": ["BUY_IT_NOW","BEST_OFFER"]}]},
    {"keywords": "1921 w551 PSA 8",   "condition": "any", "exclude_keywords": W551_EXCLUDES,
     "tiers": [{"label": "w551 Match", "min_price": 0, "max_price": 999999, "buying_options": ["BUY_IT_NOW","BEST_OFFER"]}]},
    {"keywords": "1921 w551 PSA 9",   "condition": "any", "exclude_keywords": W551_EXCLUDES,
     "tiers": [{"label": "w551 Match", "min_price": 0, "max_price": 999999, "buying_options": ["BUY_IT_NOW","BEST_OFFER"]}]},
    {"keywords": "1921 w551 uncut",   "condition": "any", "exclude_keywords": W551_EXCLUDES,
     "tiers": [{"label": "w551 Match", "min_price": 0, "max_price": 89999,  "buying_options": ["BUY_IT_NOW","BEST_OFFER"]}]},
]
 
# ── Layer 2 player searches ───────────────────────────────────────────────────
PLAYER_SEARCHES = [
    # Basketball
    {"player": "Michael Jordan",          "sport": "Basketball", "max_price": 1000, "min_grade": 7},
    {"player": "Kobe Bryant",             "sport": "Basketball", "max_price": 1000, "min_grade": 7},
    {"player": "LeBron James",            "sport": "Basketball", "max_price": 1000, "min_grade": 8},
    {"player": "Magic Johnson",           "sport": "Basketball", "max_price": 1000, "min_grade": 7},
    {"player": "Larry Bird",              "sport": "Basketball", "max_price": 1000, "min_grade": 7},
    {"player": "Shaquille O'Neal",        "sport": "Basketball", "max_price": 1000, "min_grade": 8},
    {"player": "Charles Barkley",         "sport": "Basketball", "max_price": 1000, "min_grade": 8},
    {"player": "Hakeem Olajuwon",         "sport": "Basketball", "max_price": 1000, "min_grade": 8},
    {"player": "Kevin Durant",            "sport": "Basketball", "max_price": 1000, "min_grade": 8},
    {"player": "Stephen Curry",           "sport": "Basketball", "max_price": 1000, "min_grade": 8},
    {"player": "Giannis Antetokounmpo",   "sport": "Basketball", "max_price": 1000, "min_grade": 8},
    {"player": "Luka Doncic",             "sport": "Basketball", "max_price": 1000, "min_grade": 8},
    {"player": "Shai Gilgeous-Alexander", "sport": "Basketball", "max_price": 1000, "min_grade": 9},
    {"player": "Nikola Jokic",            "sport": "Basketball", "max_price": 1000, "min_grade": 9},
    {"player": "Victor Wembanyama",       "sport": "Basketball", "max_price": 1000, "min_grade": 9},
    # Baseball
    {"player": "Mickey Mantle",           "sport": "Baseball",   "max_price": 1000, "min_grade": 1},
    {"player": "Babe Ruth",               "sport": "Baseball",   "max_price": 1000, "min_grade": 1},
    {"player": "Hank Aaron",              "sport": "Baseball",   "max_price": 1000, "min_grade": 1},
    {"player": "Willie Mays",             "sport": "Baseball",   "max_price": 1000, "min_grade": 1},
    {"player": "Roberto Clemente",        "sport": "Baseball",   "max_price": 1000, "min_grade": 1},
    {"player": "Cal Ripken Jr",           "sport": "Baseball",   "max_price": 1000, "min_grade": 8},
    {"player": "Ken Griffey Jr",          "sport": "Baseball",   "max_price": 1000, "min_grade": 8},
    {"player": "Derek Jeter",             "sport": "Baseball",   "max_price": 1000, "min_grade": 8},
    {"player": "Mike Trout",              "sport": "Baseball",   "max_price": 1000, "min_grade": 9},
    {"player": "Ronald Acuna",            "sport": "Baseball",   "max_price": 1000, "min_grade": 9},
    {"player": "Shohei Ohtani",           "sport": "Baseball",   "max_price": 1000, "min_grade": 9},
    {"player": "Juan Soto",               "sport": "Baseball",   "max_price": 1000, "min_grade": 9},
    # Football
    {"player": "Patrick Mahomes",         "sport": "Football",   "max_price": 1000, "min_grade": 9},
    {"player": "Joe Burrow",              "sport": "Football",   "max_price": 1000, "min_grade": 9},
    {"player": "Justin Herbert",          "sport": "Football",   "max_price": 1000, "min_grade": 9},
    {"player": "Lamar Jackson",           "sport": "Football",   "max_price": 1000, "min_grade": 9},
    {"player": "Josh Allen",              "sport": "Football",   "max_price": 1000, "min_grade": 9},
    {"player": "Justin Jefferson",        "sport": "Football",   "max_price": 1000, "min_grade": 9},
    {"player": "Jayden Daniels",          "sport": "Football",   "max_price": 1000, "min_grade": 9},
    {"player": "Drake Maye",              "sport": "Football",   "max_price": 1000, "min_grade": 9},
    {"player": "Tom Brady",               "sport": "Football",   "max_price": 1000, "min_grade": 8},
    {"player": "Bo Nix",                  "sport": "Football",   "max_price": 1000, "min_grade": 9},
    {"player": "Caleb Williams",          "sport": "Football",   "max_price": 1000, "min_grade": 9},
    # Pokemon
    {"player": "Charizard",               "sport": "Pokemon",    "max_price": 500,  "min_grade": 7},
    {"player": "Blastoise",               "sport": "Pokemon",    "max_price": 500,  "min_grade": 7},
    {"player": "Venusaur",                "sport": "Pokemon",    "max_price": 500,  "min_grade": 7},
    {"player": "Pikachu",                 "sport": "Pokemon",    "max_price": 300,  "min_grade": 8},
    {"player": "Mewtwo",                  "sport": "Pokemon",    "max_price": 500,  "min_grade": 7},
    {"player": "Gengar",                  "sport": "Pokemon",    "max_price": 300,  "min_grade": 8},
    {"player": "Lugia",                   "sport": "Pokemon",    "max_price": 500,  "min_grade": 8},
    {"player": "Ho-Oh",                   "sport": "Pokemon",    "max_price": 500,  "min_grade": 8},
    {"player": "Rayquaza",                "sport": "Pokemon",    "max_price": 300,  "min_grade": 8},
    {"player": "Umbreon",                 "sport": "Pokemon",    "max_price": 300,  "min_grade": 8},
    {"player": "Espeon",                  "sport": "Pokemon",    "max_price": 300,  "min_grade": 8},
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
 
# ── Seen / cooldown ───────────────────────────────────────────────────────────
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
 
# ── Grade extraction ──────────────────────────────────────────────────────────
PSA_GRADE_PATTERN = re.compile(r'\bPSA\s*(10|[1-9](?:\.5)?)\b', re.IGNORECASE)
 
def extract_grade_from_keywords(keywords):
    m = PSA_GRADE_PATTERN.search(keywords)
    return m.group(1).strip() if m else None
 
def extract_grade_from_title(title):
    matches = PSA_GRADE_PATTERN.findall(title)
    if len(matches) == 1:
        return matches[0].strip()
    return None  # none or multiple grades — skip
 
def grade_matches_title(title, required_grade):
    if required_grade is None:
        return True
    title_lower = title.lower()
    required_lower = required_grade.lower()
    if f"psa {required_lower}" not in title_lower and f"psa{required_lower}" not in title_lower:
        return False
    all_grades = PSA_GRADE_PATTERN.findall(title)
    for g in all_grades:
        if g.strip().lower() != required_lower:
            return False
    return True
 
# ── Set extractor ─────────────────────────────────────────────────────────────
YEAR_PATTERN = re.compile(r'\b(19\d{2}|20\d{2})\b')
 
def extract_set(title, sport):
    """Extract set identifier from listing title."""
    title_lower = title.lower()
    brands = SPORT_BRANDS.get(sport, [])
 
    if sport == "Pokemon":
        for brand in sorted(brands, key=len, reverse=True):
            if brand.lower() in title_lower:
                return brand
        return None
    else:
        year_match = YEAR_PATTERN.search(title)
        year = year_match.group(1) if year_match else None
        matched_brand = None
        for brand in sorted(brands, key=len, reverse=True):
            if brand.lower() in title_lower:
                matched_brand = brand
                break
        if year and matched_brand:
            return f"{year} {matched_brand}"
        elif matched_brand:
            return matched_brand
        elif year:
            return year
        return None
 
# ── Filters ───────────────────────────────────────────────────────────────────
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
    "new": "NEW", "like_new": "LIKE_NEW",
    "used": "USED_EXCELLENT,USED_GOOD,USED_ACCEPTABLE", "any": None,
}
 
def search_active(token, keywords, max_price, condition="any"):
    cond = CONDITION_MAP.get(condition)
    filters = [f"buyingOptions:{{FIXED_PRICE|BEST_OFFER}}",
               f"price:[..{max_price}]", "priceCurrency:USD"]
    if cond:
        filters.append(f"conditions:{{{cond}}}")
    
    for attempt in range(3):  # retry up to 3 times
        try:
            resp = requests.get(
                "https://api.ebay.com/buy/browse/v1/item_summary/search",
                params={"q": keywords, "filter": ",".join(filters),
                        "sort": "newlyListed", "limit": "50"},
                headers={"Authorization": f"Bearer {token}",
                         "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"},
                timeout=15,
            )
            if resp.status_code == 429:
                wait = 10 * (attempt + 1)  # 10s, 20s, 30s
                log.warning("  Rate limited, waiting %ds before retry %d...", wait, attempt + 1)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json().get("itemSummaries", [])
        except Exception as e:
            if attempt == 2:
                raise
            time.sleep(10)
    return []
 
# ── Market price from sold listings ───────────────────────────────────────────
# ── PriceCharting market price ────────────────────────────────────────────────
# Grade field mapping: PriceCharting returns prices in cents under these keys
PC_GRADE_FIELDS = {
    "1":  "grade-1-price",
    "2":  "grade-2-price",
    "3":  "grade-3-price",
    "4":  "grade-4-price",
    "5":  "grade-5-price",
    "6":  "grade-6-price",
    "7":  "grade-7-price",
    "8":  "grade-8-price",
    "9":  "grade-9-price",
    "9.5":"grade-9-5-price",
    "10": "grade-10-price",
}
 
PC_ID_CACHE_FILE = "pc_id_cache.json"
 
def load_pc_cache():
    try:
        with open(PC_ID_CACHE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
 
def save_pc_cache(cache):
    with open(PC_ID_CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)
 
PC_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.pricecharting.com/",
}
 
def search_pricecharting_id(player, card_set, pc_cache):
    """Search PriceCharting for a card and return its product ID. Uses cache."""
    cache_key = f"{player}|{card_set or 'any'}"
    if cache_key in pc_cache:
        return pc_cache[cache_key]
 
    query = f"{player} {card_set}" if card_set else player
    try:
        resp = requests.get(
            "https://www.pricecharting.com/api/products",
            params={"q": query, "format": "json"},
            headers=PC_HEADERS,
            timeout=15,
        )
        if resp.status_code != 200:
            log.warning("    PriceCharting search failed: %d", resp.status_code)
            return None
 
        products = resp.json().get("products", [])
        if not products:
            log.info("    No PriceCharting results for '%s'", query)
            return None
 
        # Pick the best match — product whose name contains the player name
        player_lower = player.lower().split()[0]
        for product in products[:5]:
            name = str(product.get("product-name", "")).lower()
            if player_lower in name:
                pc_id = product.get("id")
                if pc_id:
                    log.info("    PriceCharting match: '%s' (id: %s)", product.get("product-name"), pc_id)
                    pc_cache[cache_key] = pc_id
                    save_pc_cache(pc_cache)
                    return pc_id
 
        log.info("    No PriceCharting match for '%s'", query)
        return None
 
    except Exception as e:
        log.warning("    PriceCharting search error: %s", e)
        return None
 
def get_market_price(token, player, grade, card_set, max_price, pc_cache):
    """
    Get market price from PriceCharting for a specific player + grade + set.
    Falls back to None if not found.
    """
    pc_id = search_pricecharting_id(player, card_set, pc_cache)
    if not pc_id:
        return None
 
    try:
        resp = requests.get(
            "https://www.pricecharting.com/api/product",
            params={"id": pc_id},
            headers=PC_HEADERS,
            timeout=15,
        )
        if resp.status_code != 200:
            log.warning("    PriceCharting product fetch failed: %d", resp.status_code)
            return None
 
        data = resp.json()
 
        # Get grade-specific price field
        grade_str = str(grade).replace(".0", "")
        field = PC_GRADE_FIELDS.get(grade_str)
        if not field:
            log.warning("    No PriceCharting field for grade %s", grade_str)
            return None
 
        price_cents = data.get(field)
        if price_cents is None or price_cents == 0:
            log.info("    No PriceCharting price for grade %s", grade_str)
            return None
 
        market_price = price_cents / 100.0
        log.info("    PriceCharting market price: $%.2f (PSA %s)", market_price, grade_str)
        return market_price
 
    except Exception as e:
        log.warning("    PriceCharting product error: %s", e)
        return None
 
# ── Email ─────────────────────────────────────────────────────────────────────
def send_alert(subject, body):
    resp = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {RESEND_API_KEY}",
                 "Content-Type": "application/json"},
        json={"from": ALERT_FROM_EMAIL, "to": [ALERT_TO_EMAIL],
              "subject": subject, "text": body},
        timeout=15,
    )
    if resp.status_code == 200:
        log.info("Email sent: %s", subject)
    else:
        log.error("Email failed: %s %s", resp.status_code, resp.text)
 
def build_specific_alert(item, tier, alert_cfg):
    title  = item.get("title", "Unknown")
    price  = item.get("price", {}).get("value", "?")
    url    = item.get("itemWebUrl", "")
    opts   = ", ".join(item.get("buyingOptions", []))
    seller = item.get("seller", {})
    subject = f"eBay Alert [{tier['label']}] ${price} — {title[:50]}"
    body = (f"Alert: {tier['label']}\nSearch: {alert_cfg['keywords']}\n\n"
            f"Title: {title}\nPrice: ${price}\nBuying options: {opts}\n"
            f"Seller: {seller.get('feedbackPercentage','?')}% "
            f"({seller.get('feedbackScore','?')} transactions)\n\nView listing:\n{url}")
    return subject, body
 
def build_broad_alert(item, player, sport, price, market_price, discount_pct, card_set):
    title  = item.get("title", "Unknown")
    url    = item.get("itemWebUrl", "")
    opts   = ", ".join(item.get("buyingOptions", []))
    seller = item.get("seller", {})
    subject = f"🔥 {sport} {discount_pct:.0f}% Below Market — ${price:.2f} {player}"
    body = (f"UNDERVALUED CARD — {sport}\n"
            f"Player: {player}\nSet: {card_set or 'Unknown'}\n\n"
            f"Title: {title}\n"
            f"Listed price:   ${price:.2f}\n"
            f"Market average: ${market_price:.2f}\n"
            f"Discount:       {discount_pct:.1f}% below market\n"
            f"Est. profit:    ~${market_price - price:.2f}\n"
            f"Buying options: {opts}\n"
            f"Seller: {seller.get('feedbackPercentage','?')}% "
            f"({seller.get('feedbackScore','?')} transactions)\n\nView listing:\n{url}")
    return subject, body
 
# ── Layer 1 ───────────────────────────────────────────────────────────────────
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
        expected_grade = extract_grade_from_keywords(keywords)
        max_price = max(t["max_price"] for t in tiers)
        log.info("Scanning: '%s' (max $%.2f)", keywords, max_price)
        try:
            items = search_active(token, keywords, max_price, condition)
        except Exception as e:
            log.error("  Search failed: %s", e)
            continue
        log.info("  → %d results", len(items))
        matched = 0
        for item in items:
            item_id = item.get("itemId", "")
            if is_on_cooldown(seen, item_id):
                continue
            if not seller_passes(item):
                continue
            title = item.get("title", "")
            if not grade_matches_title(title, expected_grade):
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
            log.info("  MATCH [%s] $%s — %s", tier["label"],
                     item.get("price", {}).get("value", "?"), title[:50])
            send_alert(subject, body)
        log.info("  → %d new matches", matched)
    return total
 
# ── Layer 2 ───────────────────────────────────────────────────────────────────
def run_broad(token, seen):
    log.info("=== LAYER 2: Broad player searches ===")
    total = 0
    pc_cache = load_pc_cache()
    for cfg in PLAYER_SEARCHES:
        player    = cfg["player"]
        sport     = cfg["sport"]
        max_price = cfg["max_price"]
        min_grade = cfg["min_grade"]
 
        keywords = f"{player} PSA"
        log.info("Scanning: %s (%s, max $%d, min PSA %d)",
                 player, sport, max_price, min_grade)
        time.sleep(5)  # avoid eBay rate limit
        try:
            items = search_active(token, keywords, max_price)
        except Exception as e:
            log.error("  Search failed: %s", e)
            continue
        log.info("  → %d results", len(items))
        matched = 0
        for item in items:
            item_id = item.get("itemId", "")
            if is_on_cooldown(seen, item_id):
                continue
            if not seller_passes(item):
                continue
            title = item.get("title", "")
            if not title_passes(title, LOT_KEYWORDS):
                continue
 
            # Extract exactly one grade from title
            grade = extract_grade_from_title(title)
            if grade is None:
                continue
            try:
                if float(grade) < min_grade:
                    continue
            except ValueError:
                continue
 
            # Extract set from title
            card_set = extract_set(title, sport)
 
            price = float(item.get("price", {}).get("value", 0))
            if price <= 0:
                continue
 
            # Get market price — matched on player + grade + set
            market_price = get_market_price(token, player, grade, card_set, max_price, pc_cache)
            if market_price is None:
                continue
 
            discount_pct = ((market_price - price) / market_price) * 100
            if discount_pct < DISCOUNT_THRESHOLD * 100:
                continue
 
            mark_seen(seen, item_id)
            matched += 1
            total += 1
            subject, body = build_broad_alert(
                item, player, sport, price, market_price, discount_pct, card_set
            )
            log.info("  MATCH! $%.2f vs $%.2f (%.1f%% off) — %s",
                     price, market_price, discount_pct, title[:50])
            send_alert(subject, body)
        log.info("  → %d new matches", matched)
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
        # pc_id_cache is saved inside run_broad as IDs are discovered
    else:
        log.error("Unknown RUN_MODE: %s", RUN_MODE)
        return
    log.info("Done. Total matches: %d", total)
 
if __name__ == "__main__":
    main()
 
