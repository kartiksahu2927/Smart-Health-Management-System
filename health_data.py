"""
health_data.py
==================================================
Master dataset for the Smart Health Surveillance System.

WHY THIS FILE EXISTS:
- Holds every village/location the system tracks, covering ALL 28 Indian
  states and 8 union territories (so the Register page dropdown is never
  short on options again).
- Every location name is stored in plain English on purpose, so the map
  never shows labels in another script. (See get_live_weather/MAP NOTE
  below for why the map page also switches tile providers.)
- Provides a "live" data layer: every time these functions are called,
  case numbers shift slightly and -- for our priority/hotspot cities --
  real current rainfall is pulled from the free Open-Meteo API (no key
  required). This is what powers "real-time" updates on the dashboard,
  map, and analytics pages.

HONESTY NOTE (documented for whoever reads this code, including future-you
in a viva): there is no public, free, real-time API that reports live
village-level water-borne disease case counts in India. Health ministries
do not expose that granularity openly. So the case numbers below are
realistic baseline figures, refreshed with a time-seeded variation each
time the app is accessed -- giving a genuinely "live updating" dashboard
without pretending to pull from a disease-surveillance API that doesn't
publicly exist. The RAINFALL data, however, is genuinely real-time and
pulled live from Open-Meteo when the server has internet access.
"""

import random
import urllib.request
import json
import time
from datetime import datetime

# --------------------------------------------------------------------------
# MASTER LOCATION LIST
# Every Indian state + union territory gets at least one entry so the
# Register page can offer a complete list. A few extra well-known cities
# are included as bonus "hotspots" for richer map/analytics demos.
# tier: 1=Critical baseline, 2=High, 3=Medium, 4=Low
# (tiers are starting points only -- the live layer adjusts them)
# --------------------------------------------------------------------------

LOCATIONS = [
    # ---- North-Eastern Region ----
    {"name": "Guwahati", "state": "Assam", "region": "North-Eastern",
     "lat": 26.1445, "lon": 91.7362, "population": 1095000,
     "water_source": "Brahmaputra River", "tier": 2},
    {"name": "Shillong", "state": "Meghalaya", "region": "North-Eastern",
     "lat": 25.5788, "lon": 91.8933, "population": 372000,
     "water_source": "Local Wells & Springs", "tier": 1},
    {"name": "Aizawl", "state": "Mizoram", "region": "North-Eastern",
     "lat": 23.7271, "lon": 92.7176, "population": 280000,
     "water_source": "Mountain Springs", "tier": 3},
    {"name": "Itanagar", "state": "Arunachal Pradesh", "region": "North-Eastern",
     "lat": 27.0844, "lon": 93.6053, "population": 59000,
     "water_source": "Hill Streams", "tier": 3},
    {"name": "Imphal", "state": "Manipur", "region": "North-Eastern",
     "lat": 24.8170, "lon": 93.9368, "population": 268000,
     "water_source": "Local Wells", "tier": 3},
    {"name": "Kohima", "state": "Nagaland", "region": "North-Eastern",
     "lat": 25.6751, "lon": 94.1086, "population": 99000,
     "water_source": "Hill Springs", "tier": 4},
    {"name": "Gangtok", "state": "Sikkim", "region": "North-Eastern",
     "lat": 27.3389, "lon": 88.6065, "population": 100000,
     "water_source": "Mountain Streams", "tier": 4},
    {"name": "Agartala", "state": "Tripura", "region": "North-Eastern",
     "lat": 23.8315, "lon": 91.2868, "population": 400000,
     "water_source": "Local Wells & Ponds", "tier": 3},

    # ---- Northern Region ----
    {"name": "Delhi", "state": "Delhi", "region": "Northern",
     "lat": 28.7041, "lon": 77.1025, "population": 16753235,
     "water_source": "Yamuna River & Municipal Supply", "tier": 2},
    {"name": "Lucknow", "state": "Uttar Pradesh", "region": "Northern",
     "lat": 26.8467, "lon": 80.9462, "population": 3382000,
     "water_source": "Gomti River & Municipal Supply", "tier": 2},
    {"name": "Varanasi", "state": "Uttar Pradesh", "region": "Northern",
     "lat": 25.3176, "lon": 82.9739, "population": 1200000,
     "water_source": "Ganges River", "tier": 1},
    {"name": "Jaipur", "state": "Rajasthan", "region": "Northern",
     "lat": 26.9124, "lon": 75.7873, "population": 3073000,
     "water_source": "Bisalpur Pipeline & Wells", "tier": 3},
    {"name": "Chandigarh", "state": "Chandigarh", "region": "Northern",
     "lat": 30.7333, "lon": 76.7794, "population": 1056000,
     "water_source": "Municipal Supply", "tier": 4},
    {"name": "Ludhiana", "state": "Punjab", "region": "Northern",
     "lat": 30.9010, "lon": 75.8573, "population": 1618000,
     "water_source": "Sutlej River & Tubewells", "tier": 3},
    {"name": "Gurugram", "state": "Haryana", "region": "Northern",
     "lat": 28.4595, "lon": 77.0266, "population": 1153000,
     "water_source": "Municipal Supply", "tier": 3},
    {"name": "Shimla", "state": "Himachal Pradesh", "region": "Northern",
     "lat": 31.1048, "lon": 77.1734, "population": 171000,
     "water_source": "Gravity-fed Hill Springs", "tier": 4},
    {"name": "Dehradun", "state": "Uttarakhand", "region": "Northern",
     "lat": 30.3165, "lon": 78.0322, "population": 803000,
     "water_source": "Tons River & Wells", "tier": 3},
    {"name": "Srinagar", "state": "Jammu and Kashmir", "region": "Northern",
     "lat": 34.0837, "lon": 74.7973, "population": 1180000,
     "water_source": "Jhelum River & Dal Lake", "tier": 3},
    {"name": "Leh", "state": "Ladakh", "region": "Northern",
     "lat": 34.1526, "lon": 77.5771, "population": 31000,
     "water_source": "Glacial Streams", "tier": 4},

    # ---- Eastern Region ----
    {"name": "Kolkata", "state": "West Bengal", "region": "Eastern",
     "lat": 22.5726, "lon": 88.3639, "population": 14681000,
     "water_source": "Hooghly River", "tier": 1},
    {"name": "Patna", "state": "Bihar", "region": "Eastern",
     "lat": 25.5941, "lon": 85.1376, "population": 2046000,
     "water_source": "Ganges River & Municipal Supply", "tier": 2},
    {"name": "Ranchi", "state": "Jharkhand", "region": "Eastern",
     "lat": 23.3441, "lon": 85.3096, "population": 1456000,
     "water_source": "Wells & Reservoirs", "tier": 2},
    {"name": "Jamshedpur", "state": "Jharkhand", "region": "Eastern",
     "lat": 22.8045, "lon": 86.1849, "population": 620000,
     "water_source": "Subarnarekha River & Wells", "tier": 2},
    {"name": "Bhubaneswar", "state": "Odisha", "region": "Eastern",
     "lat": 20.2961, "lon": 85.8245, "population": 837000,
     "water_source": "Kuakhai River & Wells", "tier": 3},

    # ---- Central Region ----
    {"name": "Bhopal", "state": "Madhya Pradesh", "region": "Central",
     "lat": 23.2599, "lon": 77.4126, "population": 1798000,
     "water_source": "Upper Lake & Wells", "tier": 2},
    {"name": "Raipur", "state": "Chhattisgarh", "region": "Central",
     "lat": 21.2514, "lon": 81.6296, "population": 1123000,
     "water_source": "Kharun River & Wells", "tier": 3},

    # ---- Western Region ----
    {"name": "Mumbai", "state": "Maharashtra", "region": "Western",
     "lat": 19.0760, "lon": 72.8777, "population": 12442373,
     "water_source": "Tansa & Vaitarna Reservoirs", "tier": 3},
    {"name": "Ahmedabad", "state": "Gujarat", "region": "Western",
     "lat": 23.0225, "lon": 72.5714, "population": 5570000,
     "water_source": "Sabarmati River & Municipal Supply", "tier": 3},
    {"name": "Panaji", "state": "Goa", "region": "Western",
     "lat": 15.4909, "lon": 73.8278, "population": 115000,
     "water_source": "Mandovi River & Municipal Supply", "tier": 4},
    {"name": "Daman", "state": "Dadra and Nagar Haveli and Daman and Diu", "region": "Western",
     "lat": 20.3974, "lon": 72.8328, "population": 191000,
     "water_source": "Municipal Supply & Wells", "tier": 4},

    # ---- Southern Region ----
    {"name": "Chennai", "state": "Tamil Nadu", "region": "Southern",
     "lat": 13.0827, "lon": 80.2707, "population": 7088000,
     "water_source": "Cooum & Adyar Rivers", "tier": 3},
    {"name": "Bengaluru", "state": "Karnataka", "region": "Southern",
     "lat": 12.9716, "lon": 77.5946, "population": 8443675,
     "water_source": "Cauvery Pipeline & Borewells", "tier": 4},
    {"name": "Hyderabad", "state": "Telangana", "region": "Southern",
     "lat": 17.3850, "lon": 78.4867, "population": 6809970,
     "water_source": "Krishna & Godavari Pipelines", "tier": 4},
    {"name": "Visakhapatnam", "state": "Andhra Pradesh", "region": "Southern",
     "lat": 17.6868, "lon": 83.2185, "population": 2035922,
     "water_source": "Godavari Pipeline & Wells", "tier": 3},
    {"name": "Kochi", "state": "Kerala", "region": "Southern",
     "lat": 9.9312, "lon": 76.2673, "population": 2405000,
     "water_source": "Backwaters & Municipal Supply", "tier": 4},
    {"name": "Puducherry", "state": "Puducherry", "region": "Southern",
     "lat": 11.9416, "lon": 79.8083, "population": 950000,
     "water_source": "Municipal Supply & Wells", "tier": 4},
    {"name": "Port Blair", "state": "Andaman and Nicobar Islands", "region": "Southern",
     "lat": 11.6234, "lon": 92.7265, "population": 144000,
     "water_source": "Rainwater Harvesting & Wells", "tier": 4},
    {"name": "Kavaratti", "state": "Lakshadweep", "region": "Southern",
     "lat": 10.5593, "lon": 72.6358, "population": 11000,
     "water_source": "Rainwater & Desalination", "tier": 4},
]

# Assign a stable integer id to every location (1-indexed) so the rest of
# the app can reference locations consistently.
for _i, _loc in enumerate(LOCATIONS, start=1):
    _loc["id"] = _i

# Diseases this system tracks, in a fixed order used everywhere
DISEASES = ["diarrhea", "typhoid", "cholera", "hepatitis_a", "malaria"]

# Baseline case counts per tier (tier 1 = worst). These are realistic
# starting points modelled loosely on publicly reported monsoon-season
# outbreak patterns; the live layer below adds time-based variation.
_TIER_BASELINES = {
    1: {"diarrhea": 420, "typhoid": 140, "cholera": 20, "hepatitis_a": 80, "malaria": 90},
    2: {"diarrhea": 230, "typhoid": 70, "cholera": 6, "hepatitis_a": 45, "malaria": 120},
    3: {"diarrhea": 120, "typhoid": 30, "cholera": 1, "hepatitis_a": 20, "malaria": 60},
    4: {"diarrhea": 45, "typhoid": 10, "cholera": 0, "hepatitis_a": 6, "malaria": 25},
}

_TIER_WATER_QUALITY = {
    1: {"ph": 6.3, "turbidity": 8.2, "chlorine": 0.15, "bacteria_count": 520},
    2: {"ph": 6.9, "turbidity": 5.5, "chlorine": 0.35, "bacteria_count": 260},
    3: {"ph": 7.2, "turbidity": 3.2, "chlorine": 0.55, "bacteria_count": 110},
    4: {"ph": 7.5, "turbidity": 1.6, "chlorine": 0.75, "bacteria_count": 40},
}

_TIER_MORTALITY = {1: 3.6, 2: 2.0, 3: 1.0, 4: 0.5}

_RISK_LABELS = {1: "Critical", 2: "High", 3: "Medium", 4: "Low"}

# Cities that get a genuine live-internet weather lookup (kept small on
# purpose -- fetching 38 locations on every page load would make the app
# feel slow or break entirely if the network hiccups). Everything else
# still updates dynamically using the time-seeded simulation, just without
# the live network call.
PRIORITY_WEATHER_CITIES = {"Shillong", "Varanasi", "Kolkata", "Guwahati", "Delhi"}

# In-memory cache so we don't hit the weather API more than once every
# 15 minutes per city, even if many people are using the dashboard.
_weather_cache = {}
_WEATHER_CACHE_SECONDS = 15 * 60


def get_live_weather(lat, lon, cache_key):
    """
    Fetch REAL current weather (temperature + rainfall) from Open-Meteo,
    a free API that needs no key. Falls back gracefully if there is no
    internet connection, the request times out, or the API is unreachable
    -- the app must never crash because of this.
    """
    now = time.time()
    cached = _weather_cache.get(cache_key)
    if cached and (now - cached["fetched_at"]) < _WEATHER_CACHE_SECONDS:
        return cached["data"]

    fallback = {"temperature_c": None, "rainfall_mm": 0.0, "source": "estimated"}

    try:
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            "&current=temperature_2m,precipitation"
            "&timezone=auto"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "SmartHealthSystem/1.0"})
        with urllib.request.urlopen(req, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
        current = payload.get("current", {})
        data = {
            "temperature_c": current.get("temperature_2m"),
            "rainfall_mm": current.get("precipitation", 0.0) or 0.0,
            "source": "live",
        }
        _weather_cache[cache_key] = {"fetched_at": now, "data": data}
        return data
    except Exception:
        # No internet / API down / timeout -- fail quietly, app keeps working
        if cached:
            return cached["data"]
        return fallback


def _time_seed(location_id):
    """Changes once per hour, so numbers visibly shift between visits
    without jumping around wildly inside a single short session."""
    hour_bucket = datetime.now().strftime("%Y-%m-%d-%H")
    return f"{location_id}-{hour_bucket}"


def _live_cases_for(location):
    """Apply a small, realistic, time-seeded fluctuation (+/- ~18%) to the
    baseline case numbers for one location."""
    rng = random.Random(_time_seed(location["id"]))
    baseline = _TIER_BASELINES[location["tier"]]
    cases = {}
    for disease, base_value in baseline.items():
        variation = rng.uniform(-0.18, 0.18)
        cases[disease] = max(0, round(base_value * (1 + variation)))
    return cases


def _live_water_quality_for(location, rainfall_mm):
    """Water quality drifts slightly with simulated time AND gets nudged
    by real rainfall when we have it (heavier rain -> higher turbidity,
    lower chlorine effectiveness -- a real, well-documented relationship)."""
    rng = random.Random(_time_seed(location["id"]) + "-water")
    base = _TIER_WATER_QUALITY[location["tier"]]
    rainfall_factor = min(1.5, 1 + (rainfall_mm or 0) / 40)

    return {
        "ph": round(base["ph"] + rng.uniform(-0.2, 0.2), 1),
        "turbidity": round(base["turbidity"] * rainfall_factor + rng.uniform(-0.3, 0.3), 1),
        "chlorine": round(max(0.05, base["chlorine"] - (rainfall_factor - 1) * 0.2), 2),
        "bacteria_count": round(base["bacteria_count"] * rainfall_factor),
    }


def _recompute_risk(total_cases, water_quality):
    """Combine live case load + live water quality into a single risk
    label, so a real rainfall spike can genuinely push a village's risk
    level up -- this is the link between 'live weather' and 'live risk'."""
    score = (total_cases / 80) + (water_quality["turbidity"] / 2) + (water_quality["bacteria_count"] / 200)
    if score >= 9:
        return "Critical"
    elif score >= 6:
        return "High"
    elif score >= 3:
        return "Medium"
    return "Low"


def get_live_snapshot(location):
    """The core 'live data' function: returns a fresh snapshot for one
    location, recomputed every time it's called."""
    weather = None
    if location["name"] in PRIORITY_WEATHER_CITIES:
        weather = get_live_weather(location["lat"], location["lon"], location["name"])

    rainfall_mm = weather["rainfall_mm"] if weather else random.Random(_time_seed(location["id"]) + "-rain").uniform(0, 12)

    cases = _live_cases_for(location)
    total_cases = sum(cases.values())
    water_quality = _live_water_quality_for(location, rainfall_mm)
    risk_level = _recompute_risk(total_cases, water_quality)
    baseline_mortality = _TIER_MORTALITY[location["tier"]]

    return {
        "id": location["id"],
        "name": location["name"],
        "state": location["state"],
        "region": location["region"],
        "latitude": location["lat"],
        "longitude": location["lon"],
        "population": location["population"],
        "water_source": location["water_source"],
        "recent_cases": cases,
        "total_cases": total_cases,
        "risk_level": risk_level,
        "water_quality": water_quality,
        "mortality_rate": baseline_mortality,
        "rainfall_mm": round(rainfall_mm, 1),
        "weather_source": "live" if (weather and weather.get("source") == "live") else "estimated",
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def get_all_locations_live():
    """Returns every tracked location with a fresh live snapshot. This is
    what dashboard/map/analytics call -- so every page load reflects
    current conditions."""
    return [get_live_snapshot(loc) for loc in LOCATIONS]


def get_location_by_id(location_id):
    for loc in LOCATIONS:
        if loc["id"] == location_id:
            return get_live_snapshot(loc)
    return None


def get_locations_grouped_by_region():
    """Used by the Register page to build the Village/Area dropdown,
    grouped by region so a long list of 38 places is easy to scan."""
    grouped = {}
    for loc in LOCATIONS:
        grouped.setdefault(loc["region"], []).append(loc)
    for region in grouped:
        grouped[region].sort(key=lambda l: l["name"])
    return grouped


def get_hotspot_points():
    """Lat/lng/intensity triples for the heatmap layer on the map page."""
    points = []
    for snapshot in get_all_locations_live():
        intensity = min(1.0, snapshot["total_cases"] / 600)
        points.append({
            "lat": snapshot["latitude"],
            "lng": snapshot["longitude"],
            "intensity": intensity,
            "cases": snapshot["total_cases"],
            "name": snapshot["name"],
            "risk": snapshot["risk_level"],
        })
    return points


def get_region_summary():
    summary = {}
    for snapshot in get_all_locations_live():
        region = snapshot["region"]
        bucket = summary.setdefault(region, {
            "total_cases": 0, "villages": 0,
            "critical_count": 0, "high_count": 0,
            "medium_count": 0, "low_count": 0,
        })
        bucket["total_cases"] += snapshot["total_cases"]
        bucket["villages"] += 1
        bucket[f"{snapshot['risk_level'].lower()}_count"] += 1
    return summary


def get_disease_distribution():
    totals = {d: 0 for d in DISEASES}
    for snapshot in get_all_locations_live():
        for disease, count in snapshot["recent_cases"].items():
            totals[disease] += count
    return totals


if __name__ == "__main__":
    print(f"Total locations loaded: {len(LOCATIONS)}")
    states = sorted(set(l["state"] for l in LOCATIONS))
    print(f"States/UTs covered: {len(states)}")
    for s in states:
        print(f"  - {s}")
    print("\nSample live snapshot (Shillong):")
    sample = get_location_by_id(2)
    print(json.dumps(sample, indent=2))
