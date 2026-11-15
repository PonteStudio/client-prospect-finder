"""Default settings. Every value here can be overridden from the command line."""

# Search area: a circle around a centre point.
# Default: centred on Workington, radius reaching Carlisle (~47 km away).
DEFAULT_CENTRE_NAME = "Workington"
DEFAULT_CENTRE = (54.6425, -3.5444)  # lat, lon
DEFAULT_RADIUS_KM = 48.0

# Known town centres so a run can say --centre Keswick without a lookup.
TOWNS = {
    "workington": (54.6425, -3.5444),
    "carlisle": (54.8925, -2.9329),
    "whitehaven": (54.5481, -3.5865),
    "cockermouth": (54.6631, -3.3626),
    "maryport": (54.7140, -3.4950),
    "keswick": (54.6013, -3.1347),
    "wigton": (54.8236, -3.1605),
    "silloth": (54.8692, -3.3869),
    "egremont": (54.4826, -3.5303),
    "penrith": (54.6641, -2.7524),
    "kendal": (54.3280, -2.7463),
    "ambleside": (54.4325, -2.9630),
    "windermere": (54.3800, -2.9070),
    "brampton": (54.9410, -2.7330),
    "aspatria": (54.7660, -3.3290),
}

# Sectors. "hospitality" is the core market and is flagged in its own column.
CORE_SECTOR = "Hospitality"

# Opening the search to every sector by default; filter in the Sheet.
DEFAULT_SECTORS = [
    "Hospitality",
    "Retail",
    "Health & Beauty",
    "Professional services",
    "Trades & Home",
    "Leisure & Attractions",
    "Food production",
    "Automotive",
    "Other",
]

# Scoring weights (max points per part). Sum = 100.
WEIGHTS = {
    "opportunity": 55,
    "distance": 20,
    "strength": 15,
    "contactability": 10,
}

# Network politeness
USER_AGENT = "PonteStudio-ProspectFinder/0.1 (business research tool)"
HTTP_TIMEOUT = 15
AUDIT_WORKERS = 12

OVERPASS_URLS = [
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]
FSA_URL = "https://api.ratings.food.gov.uk/Establishments"
