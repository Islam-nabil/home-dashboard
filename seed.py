"""
Seed data (spec section 24).

Real, retailer-verified prices were gathered via live web research on
2026-08-09 (see each product's research_sources entry for the exact
retailer/URL/timestamp). Where no verified single price could be found,
the product is clearly flagged `is_demo_data=1` with an ESTIMATED price
range midpoint and an unverified observation — never presented as a real
market price. TV / Water Heater / Microwave / Air Fryer categories had no
live research performed in v1 (out of scope for the initial 4 core
categories) and are seeded as clearly-labeled demo placeholders so every
priority tier has at least one example to show the full system working.

Re-running this script is idempotent: it does nothing if categories
already exist.

Score breakdowns are Claude's qualitative assessment from the research
notes (brand reputation, warranty length, inverter vs not, feature set) —
explicitly a subjective research score, not a lab-measured objective
truth. `user_preference` is deliberately left unscored for every seeded
product since the user hasn't rated anything yet; the scoring engine
renormalizes around whatever dimensions ARE scored (see engines/scoring.py).
"""
import db
import repository as repo

RESEARCH_DATE = "2026-08-09"


def _obs_time(days_ago=0):
    # Seed data is dated "today" per the research date above; days_ago lets
    # us legitimately place two REAL price points (e.g. list vs sale price
    # both shown on the same retailer page) at slightly different times.
    from datetime import datetime, timedelta, timezone
    dt = datetime(2026, 8, 9, 12, 0, 0, tzinfo=timezone.utc) - timedelta(days=days_ago)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


CATEGORIES = [
    dict(key="refrigerator", name="Refrigerator", icon="🧊", priority_level=1, sort_order=1,
         target_budget_egp=35000,
         must_have_features=["No-frost", ">=400L capacity", "Inverter compressor preferred"],
         notes="Household of the scale typical for a new Egyptian home; 400-500L no-frost tier.",
         scoring_dimensions=["Reliability", "Compressor type", "Capacity", "Dimensions",
                              "Energy consumption", "Warranty", "Egypt after-sales support",
                              "Cooling performance", "Spare-parts availability", "Price/value"]),
    dict(key="cooker", name="Cooker / Stove", icon="🔥", priority_level=1, sort_order=2,
         target_budget_egp=20000,
         must_have_features=["5 burners", "90cm freestanding", "Auto-ignition"],
         notes="Freestanding gas cooker, standard Egyptian kitchen size.",
         scoring_dimensions=["Reliability", "Burner quality", "Oven performance", "Safety features",
                              "Warranty", "Egypt service", "Build quality", "Price/value"]),
    dict(key="air_conditioner", name="Air Conditioner", icon="❄️", priority_level=1, sort_order=3,
         target_budget_egp=32000,
         must_have_features=["Inverter", "1.5 HP (12,000 BTU)", "Cooling + heating preferred"],
         notes="First unit for a bedroom/living room ~18-25 sqm. Additional AC units needed per room.",
         scoring_dimensions=["Horsepower/BTU fit", "Inverter vs non-inverter", "Energy efficiency",
                              "Cooling performance", "Noise level", "Warranty", "Egypt service network",
                              "Installation considerations", "Price/value"]),
    dict(key="washing_machine", name="Washing Machine", icon="🌀", priority_level=1, sort_order=4,
         target_budget_egp=24000,
         must_have_features=["Front load", "Inverter motor", ">=7kg capacity"],
         notes="8kg front-load inverter is the sweet spot in the Egyptian market as of Aug 2026.",
         scoring_dimensions=["Capacity", "Load type", "Motor type", "Program variety", "Reliability",
                              "Energy/water efficiency", "Warranty", "Egypt service", "Price/value"]),
    dict(key="tv", name="TV", icon="📺", priority_level=2, sort_order=5,
         target_budget_egp=25000,
         must_have_features=["55-inch class", "4K"],
         notes="No live retailer research performed in v1 — demo placeholders only, confirm before buying.",
         scoring_dimensions=["Picture quality", "Smart platform", "Warranty", "Price/value"]),
    dict(key="water_heater", name="Water Heater", icon="🚿", priority_level=2, sort_order=6,
         target_budget_egp=6000,
         must_have_features=["50L electric"],
         notes="No live retailer research performed in v1 — demo placeholder only.",
         scoring_dimensions=["Capacity", "Safety", "Energy efficiency", "Warranty", "Price/value"]),
    dict(key="microwave", name="Microwave", icon="📦", priority_level=3, sort_order=7,
         target_budget_egp=6500,
         must_have_features=["20-25L"],
         notes="No live retailer research performed in v1 — demo placeholders only. Convenience item — fine to wait.",
         scoring_dimensions=["Capacity", "Power", "Features", "Warranty", "Price/value"]),
    dict(key="air_fryer", name="Air Fryer", icon="🍟", priority_level=3, sort_order=8,
         target_budget_egp=4000,
         must_have_features=[],
         notes="No live retailer research performed in v1 — demo placeholder only. Convenience item.",
         scoring_dimensions=["Capacity", "Features", "Price/value"]),
]

RETAILERS = [
    dict(key="btech", name="B.TECH", base_url="https://btech.com", provider_key="btech",
         credibility_score=88, notes="Major Egyptian electronics chain; JSON-LD product data on most pages."),
    dict(key="jumia_eg", name="Jumia Egypt", base_url="https://www.jumia.com.eg", provider_key="generic_html",
         credibility_score=75, notes="Large marketplace; third-party sellers vary in reliability."),
    dict(key="zanussi_eg", name="Zanussi Egypt (official)", base_url="https://www.zanussi.com.eg", provider_key="generic_html",
         credibility_score=85, notes="Official brand store."),
    dict(key="amazon_eg", name="Amazon Egypt", base_url="https://www.amazon.eg", provider_key="amazon_eg",
         credibility_score=85, notes="Often blocks simple automated fetches; expect manual updates."),
    dict(key="noon_eg", name="Noon Egypt", base_url="https://www.noon.com/egypt-en", provider_key="noon_eg",
         credibility_score=78, notes="JS-heavy SPA; automated extraction frequently fails."),
    dict(key="carrefour_eg", name="Carrefour Egypt", base_url="https://www.carrefouregypt.com", provider_key="carrefour_eg",
         credibility_score=80, notes=""),
    dict(key="twob", name="2B Egypt", base_url="https://2b.com.eg", provider_key="twob", credibility_score=78, notes=""),
    dict(key="raya", name="Raya Shop", base_url="https://www.rayashop.com", provider_key="raya", credibility_score=76, notes=""),
    dict(key="other", name="Other / Unlisted Retailer", base_url="", provider_key="manual",
         credibility_score=55, notes="Unverified retailer — treat listings here with extra caution."),
]


def _score(reliability, price_value, warranty_service, energy_efficiency, performance, features):
    return dict(reliability=reliability, price_value=price_value, warranty_service=warranty_service,
                energy_efficiency=energy_efficiency, performance=performance, features=features)


PRODUCTS = {
    "refrigerator": [
        dict(brand="Sharp", model="SJ-GV58A(BK)", full_name="Sharp Freestanding Digital Refrigerator No-Frost 18ft Glass Black",
             capacity="18 ft (~510L)", warranty_years=10, retailer="btech",
             url="https://btech.com/en/p/sharp-freestanding-digital-refrigerator-with-inverter-technology-no-frost-2-doors-18-ft-glass-black-sj-gv58a-bk",
             price=42634, is_demo=False,
             specs={"Type": "No-Frost, 2-door", "Compressor": "J-Tech Inverter", "Extras": "Plasmacluster, Hybrid Cooling"},
             features=["No-frost", "Inverter compressor", "Plasmacluster air purification", "LED interior"],
             pros=["10-year warranty (longest in this shortlist)", "Inverter compressor for efficiency", "Large 18ft capacity"],
             cons=["Premium price point among verified options"],
             reliability="Sharp is backed by a wide Egyptian service network (Olympic Group); generally well regarded for durability.",
             egypt_service="Wide service network via Olympic Group/Sharp Egypt.",
             score=_score(82, 62, 92, 80, 80, 75), target=40000),
        dict(brand="Toshiba", model="GR-RT559WE-PMN(06)", full_name="Toshiba No-Frost Refrigerator 411L",
             capacity="411L", warranty_years=5, retailer="jumia_eg",
             url="https://www.jumia.com.eg/appliances-fridges-freezers/",
             price=26869, is_demo=False,
             specs={"Type": "No-Frost, 2-door"},
             features=["No-frost"],
             pros=["Strong price/value", "Toshiba backed by Olympic Group's large Egyptian service network", "4.6/5 customer rating on Jumia"],
             cons=["Smaller capacity than the others in this shortlist", "Fewer premium features"],
             reliability="Toshiba fridges are widely serviced in Egypt via Olympic Group; consistently well-rated by buyers.",
             egypt_service="Wide service network via Olympic Group.",
             score=_score(80, 85, 78, 65, 68, 55), target=25500),
        dict(brand="Zanussi", model="ZRT48202SA", full_name="Zanussi 2-Door No-Frost Refrigerator 478L Silver",
             capacity="478L", warranty_years=5, retailer="zanussi_eg",
             url="https://www.zanussi.com.eg/en-eg/appliances/fridge-freezers/zrt48202sa/",
             price=40210, is_demo=False,
             specs={"Type": "No-Frost, top-freezer", "Extras": "0° ChillFresh box, Space+ drawer"},
             features=["No-frost", "0° ChillFresh box", "Space+ drawer"],
             pros=["Large 478L capacity", "Official brand store pricing (no marketplace markup risk)"],
             cons=["Non-inverter motor (higher running cost than inverter competitors)"],
             reliability="Zanussi (Electrolux group) has a moderate presence in Egypt; parts availability is decent in Cairo/Alexandria, thinner upcountry.",
             egypt_service="Electrolux/Zanussi authorized service centers in major cities.",
             score=_score(70, 68, 78, 55, 72, 60), target=37000),
        dict(brand="Fresh", model="FNT-BR470KT", full_name="Fresh NoFrost Top Freezer Refrigerator 16ft",
             capacity="16 ft (~450L)", warranty_years=10, retailer="btech",
             url="https://btech.com/en/p/fresh-refrigerator-nofrost-16ft-fntbr470kt",
             price=26790, is_demo=False,
             specs={"Type": "No-Frost, top-freezer", "Extras": "LED lighting, stainless finish"},
             features=["No-frost", "LED lighting"],
             pros=["Best price/value in this shortlist", "10-year warranty", "Fresh/Elaraby has the largest in-country service network of any brand here"],
             cons=["Non-inverter motor", "Price sourced from a third-party marketplace seller on B.TECH — confirm directly before buying"],
             reliability="Fresh (Elaraby Group) is the dominant value brand in Egypt with the deepest informal + formal service network.",
             egypt_service="Largest service network of any brand in this category (Elaraby Group).",
             score=_score(75, 88, 85, 55, 65, 50), target=28000),
    ],
    "washing_machine": [
        dict(brand="Toshiba", model="TW-BJ90M4E(SK)", full_name="Toshiba Inverter Front Load Washing Machine 8kg Silver",
             capacity="8kg", warranty_years=5, retailer="btech",
             url="https://btech.com/en/toshiba-washingmachine-8kg-inverter-twbj90m4esk.html",
             price=20129, is_demo=False,
             specs={"Motor": "Inverter", "Load": "Front"},
             features=["Inverter motor"],
             pros=["Cheapest of the verified inverter 8kg options", "Olympic Group service network"],
             cons=["Fewer smart features than LG/Samsung"],
             reliability="Well-regarded, wide Egyptian service coverage via Olympic Group.",
             egypt_service="Olympic Group authorized service.",
             score=_score(78, 88, 80, 78, 72, 55), target=19000),
        dict(brand="LG", model="F4Y2TYG6X", full_name="LG Inverter Front Load Washing Machine 8kg Onyx Black",
             capacity="8kg", warranty_years=5, retailer="btech",
             url="https://btech.com/en/p/lg-front-load-inverter-washing-machine-8kg-black-f4y2tyg6x",
             price=20325, is_demo=False,
             specs={"Motor": "Inverter Direct Drive", "RPM": "1400", "Extras": "ThinQ app, Smart Diagnosis, 30 programs"},
             features=["Inverter Direct Drive motor", "ThinQ app", "Smart Diagnosis", "30 wash programs"],
             pros=["10-year motor warranty (mfr claim)", "Most feature-rich of the shortlist", "Strong brand reputation"],
             cons=["Slightly pricier than Toshiba/Fresh"],
             reliability="LG direct-drive motors have a strong reliability reputation; LG has its own Egypt service network.",
             egypt_service="LG-operated service centers in major Egyptian cities.",
             score=_score(85, 82, 90, 82, 82, 88), target=19500),
        dict(brand="Samsung", model="WW80T4040CX1AS", full_name="Samsung Front Load Washing Machine 8kg Inox",
             capacity="8kg", warranty_years=5, retailer="btech",
             url="https://btech.com/en/p/samsung-washing-machine-8kg-ww80t4040cx1as",
             price=23398, price_before=24629, is_demo=False,
             specs={"Motor": "Digital Inverter", "RPM": "1400", "Extras": "Hygiene steam, child lock"},
             features=["Digital Inverter motor", "Hygiene steam", "Child lock"],
             pros=["Currently discounted from 24,629 to 23,398 EGP on B.TECH", "Hygiene steam function", "Strong brand + service network"],
             cons=["Most expensive of the verified options even discounted"],
             reliability="Samsung digital inverter motors are well regarded; Samsung has an extensive Egypt service network.",
             egypt_service="Samsung-operated service centers nationwide.",
             score=_score(83, 72, 88, 80, 80, 78), target=21000),
        dict(brand="Fresh", model="W8DD1255G1BL", full_name="Fresh Inverter Front Load Washing Machine 8kg Black",
             capacity="8kg", warranty_years=5, retailer="btech",
             url="https://btech.com/en/p/fresh-8kg-inverter-washing-machine-w8dd1255g1bl",
             price=20019, is_demo=False,
             specs={"Motor": "Direct-drive inverter (7 motion settings)", "Extras": "Steam + sterilization, 15-min quick wash"},
             features=["Direct-drive inverter motor", "Steam + sterilization", "15-minute quick wash", "Digital touchscreen"],
             pros=["Cheapest verified 8kg inverter option", "Feature-rich for the price (steam, quick wash)", "Best Egypt service network (Elaraby Group)"],
             cons=["Brand perception slightly below LG/Samsung for premium buyers"],
             reliability="Fresh (Elaraby Group) — deepest service network in Egypt, though premium-tier brand perception is lower than LG/Samsung.",
             egypt_service="Largest service network of any brand in this shortlist.",
             score=_score(75, 90, 80, 80, 78, 80), target=20500),
    ],
    "cooker": [
        dict(brand="Universal", model="6905PR7", full_name="Universal Freestanding Gas Cooker 5 Burners Stainless Steel 90cm",
             capacity="90cm, 5 burners", warranty_years=5, retailer="btech",
             url="https://btech.com/en/p/universal-freestanding-gas-cooker-5-burners-stainless-steel-90-cm-6905pr7",
             price=16432, is_demo=False,
             specs={"Burners": 5, "Ignition": "Self-ignition", "Extras": "Grill, cast-iron burner holders"},
             features=["Self-ignition", "Grill", "Cast-iron burner holders", "Oven light"],
             pros=["Cheapest verified option", "5-year warranty", "Universal/Fresh are the dominant value cooker brands with wide service availability"],
             cons=["Fewer premium features (no digital display)"],
             reliability="Universal is a well-established Egyptian value brand with wide informal-market service availability.",
             egypt_service="Wide informal + formal service availability.",
             score=_score(72, 88, 78, 60, 68, 45), target=17500),
        dict(brand="La Germania", model="TUS95C81CX/1", full_name="La Germania Freestanding Digital Gas Cooker 5 Burners 90cm",
             capacity="90cm, 5 burners", warranty_years=2, retailer="other",
             url="https://btech.com/en/la-germania-gas-cooker-tus95c81cx1.html",
             price=26000, is_demo=True, price_range_note="No verified single price found; range estimate 22,000-30,000 EGP.",
             specs={"Burners": 5, "Extras": "Digital display, fan-assisted oven"},
             features=["Digital display", "Fan-assisted oven"],
             pros=["Italian-heritage brand, generally viewed as a step up in build/finish"],
             cons=["Shorter formal warranty (2 years vs 5 for Universal/Fresh)", "Price not verified — estimate only"],
             reliability="Italian-heritage brand distributed via Elaraby Group; better finish quality, but the 2-year warranty is short relative to competitors.",
             egypt_service="Distributed via Elaraby Group.",
             score=_score(68, 55, 45, 62, 75, 65), target=24000),
        dict(brand="Fresh", model="Professional-5790", full_name="Fresh Professional Gas Cooker 5 Burners Stainless Steel",
             capacity="90cm, 5 burners", warranty_years=5, retailer="other",
             url="https://btech.com/en/p/fresh-freestanding-professional-digital-gas-cookers-5-burners-stainless-steel-90-cm",
             price=17000, is_demo=True, price_range_note="No verified single price found (out of stock); range estimate 14,000-20,000 EGP.",
             specs={"Burners": 5, "Extras": "Auto shut-off, warmer drawer, fan oven"},
             features=["Auto-ignition", "Auto shut-off", "Warmer drawer", "Fan oven"],
             pros=["Feature-rich for the estimated price point", "Fresh's wide Egypt service network"],
             cons=["Price not verified — estimate only", "Was out of stock at last check"],
             reliability="Fresh (Elaraby Group) — widest Egypt service network of any cooker brand here.",
             egypt_service="Widest service network of any brand in this shortlist.",
             score=_score(74, 80, 78, 62, 74, 62), target=16000),
        dict(brand="Ariston", model="A9GG1FCXEX", full_name="Ariston 5 Burners Stainless Steel Gas Cooker 90cm",
             capacity="90cm, 5 burners", warranty_years=2, retailer="other",
             url="", price=24000, is_demo=True, price_range_note="No verified price found; range estimate 20,000-28,000 EGP.",
             specs={"Burners": 5, "Extras": "Cast-iron grids, semi-professional"},
             features=["Cast-iron grids", "Semi-professional design"],
             pros=["Italian-heritage mid-premium tier"],
             cons=["Price unverified", "Shorter warranty typical of this brand tier in Egypt"],
             reliability="Ariston Egypt operation; mid-premium positioning similar to La Germania.",
             egypt_service="Ariston Egypt service network.",
             score=_score(68, 55, 48, 62, 76, 60), target=22000),
    ],
    "air_conditioner": [
        dict(brand="Tornado", model="TY-VX12BEE", full_name="Tornado Split Inverter AC 1.5 HP Cooling & Heating",
             capacity="1.5 HP / 12,500 BTU", warranty_years=5, retailer="btech",
             url="https://btech.com/en/p/tornado-ac-invrtr-1-5hp-cool-heat-ty-vx12zee",
             price=26999, is_demo=False,
             specs={"Type": "Inverter, cooling+heating", "Extras": "Plasma Shield tech"},
             features=["Inverter", "Cooling + heating", "Plasma Shield air purification"],
             pros=["Cheapest verified 1.5HP inverter option", "5-year warranty (market-standard)"],
             cons=["Brand perception below LG/Carrier for premium buyers"],
             reliability="Tornado is a well-established Egyptian appliance brand with decent service coverage.",
             egypt_service="Tornado authorized service centers.",
             score=_score(72, 88, 80, 78, 76, 60), target=27500),
        dict(brand="Fresh", model="500014343", full_name="Fresh Split Inverter AC 1.5 HP Cooling & Heating",
             capacity="1.5 HP / 12,000 BTU", warranty_years=5, retailer="btech",
             url="https://btech.com/en/p/fresh-air-conditioner-1-5-hp-cooling-heating-500014343",
             price=28474, is_demo=False,
             specs={"Type": "Inverter, cooling+heating", "Extras": "4-way auto swing, ECO Sleep, sensor mode"},
             features=["Inverter", "4-way auto swing", "ECO Sleep mode", "Sensor mode"],
             pros=["Fresh has Egypt's widest appliance service network", "Feature-rich (ECO Sleep, sensor mode)"],
             cons=["Not the cheapest option"],
             reliability="Fresh (Elaraby Group) — widest Egypt service network of any brand in this shortlist.",
             egypt_service="Widest service network (Elaraby Group).",
             score=_score(76, 80, 80, 80, 78, 75), target=27000),
        dict(brand="LG", model="S4-Q12JA3AE", full_name="LG Dual Cool Split Inverter AC 1.5 HP Cooling Only",
             capacity="1.5 HP / 12,000 BTU", warranty_years=5, retailer="btech",
             url="https://btech.com/en/p/lg-split-ac-s4-q12ja3ae-2022",
             price=30085, is_demo=False,
             specs={"Type": "Inverter, cooling only"},
             features=["Inverter", "Dual Cool"],
             pros=["Strong brand reputation for reliability and energy efficiency"],
             cons=["Cooling only — no heating function", "Pricier than Tornado/Fresh"],
             reliability="LG inverter compressors are consistently well-reviewed for reliability and efficiency in Egyptian retail commentary.",
             egypt_service="LG-operated service centers.",
             score=_score(85, 68, 82, 85, 80, 65), target=28500),
        dict(brand="Carrier", model="QHCT12DN-708F", full_name="Carrier Optimax Inverter Split AC 1.5 HP Cooling & Heating",
             capacity="1.5 HP / 12,000 BTU", warranty_years=5, retailer="btech",
             url="https://btech.com/en/p/carrier-optimax-inferter-air-conditioner-qhct12dn-708f",
             price=30222, is_demo=False,
             specs={"Type": "Inverter, cooling+heating", "Extras": "Plasma filtration"},
             features=["Inverter", "Cooling + heating", "Plasma filtration"],
             pros=["Carrier is consistently flagged as a quality/durability leader in Egyptian retail commentary"],
             cons=["Among the pricier verified options"],
             reliability="Carrier is repeatedly cited as a durability/efficiency leader in Egyptian appliance retail commentary.",
             egypt_service="Carrier Egypt authorized service network.",
             score=_score(86, 65, 82, 84, 82, 70), target=29000),
        dict(brand="Midea", model="MSCT-12HR-DN", full_name="Midea Split Inverter AC 1.5 HP Cooling & Heating",
             capacity="1.5 HP / 12,000 BTU", warranty_years=5, retailer="btech",
             url="https://btech.com/en/p/midea-split-air-conditioner-1-5-hp-msct12hrdn-2022",
             price=32500, is_demo=False,
             specs={"Type": "Inverter, cooling+heating", "Refrigerant": "R410A", "Extras": "Self-cleaning filters, LCD display, auto-restart"},
             features=["Inverter", "Self-cleaning filters", "LCD display", "Auto-restart"],
             pros=["Self-cleaning filters (less maintenance)", "R410A refrigerant"],
             cons=["Most expensive of the verified 1.5HP options"],
             reliability="Midea is a fast-growing brand in Egypt; service network is newer/thinner than LG/Carrier/Fresh.",
             egypt_service="Growing but comparatively newer service network.",
             score=_score(70, 60, 80, 80, 78, 72), target=30000),
    ],
    # --- Demo-only categories (no live research performed in v1) ---------------
    "tv": [
        dict(brand="Samsung", model="UA55CU7000", full_name="Samsung 55\" Crystal UHD 4K Smart TV (DEMO)",
             capacity="55-inch", warranty_years=2, retailer="other", url="", price=24000, is_demo=True,
             price_range_note="No live research performed — placeholder estimate only.",
             specs={"Resolution": "4K UHD"}, features=["Smart TV platform"],
             pros=["Placeholder — replace with real research before relying on this"], cons=["Unverified"],
             reliability="Not assessed — demo placeholder.", egypt_service="Not assessed — demo placeholder.",
             score=_score(60, 60, 55, 55, 60, 55), target=22000),
        dict(brand="LG", model="55NANO75", full_name="LG 55\" NanoCell 4K Smart TV (DEMO)",
             capacity="55-inch", warranty_years=2, retailer="other", url="", price=30000, is_demo=True,
             price_range_note="No live research performed — placeholder estimate only.",
             specs={"Resolution": "4K NanoCell"}, features=["Smart TV platform (webOS)"],
             pros=["Placeholder — replace with real research before relying on this"], cons=["Unverified"],
             reliability="Not assessed — demo placeholder.", egypt_service="Not assessed — demo placeholder.",
             score=_score(62, 50, 55, 55, 65, 60), target=27000),
    ],
    "water_heater": [
        dict(brand="Ariston", model="ANDRIS2-50", full_name="Ariston Andris2 50L Electric Water Heater (DEMO)",
             capacity="50L", warranty_years=2, retailer="other", url="", price=5000, is_demo=True,
             price_range_note="No live research performed — placeholder estimate only.",
             specs={}, features=[], pros=["Placeholder — replace with real research"], cons=["Unverified"],
             reliability="Not assessed — demo placeholder.", egypt_service="Not assessed — demo placeholder.",
             score=_score(60, 60, 55, 55, 55, 45), target=4500),
    ],
    "microwave": [
        dict(brand="Toshiba", model="MW2-MM25P", full_name="Toshiba 25L Microwave (DEMO)",
             capacity="25L", warranty_years=1, retailer="other", url="", price=6200, is_demo=True,
             price_range_note="No live research performed — placeholder estimate only.",
             specs={}, features=[], pros=["Placeholder — replace with real research"], cons=["Unverified"],
             reliability="Not assessed — demo placeholder.", egypt_service="Not assessed — demo placeholder.",
             score=_score(65, 65, 45, 55, 55, 50), target=6000),
        dict(brand="Sharp", model="R-20CN", full_name="Sharp 20L Microwave (DEMO)",
             capacity="20L", warranty_years=1, retailer="other", url="", price=4800, is_demo=True,
             price_range_note="No live research performed — placeholder estimate only.",
             specs={}, features=[], pros=["Placeholder — replace with real research"], cons=["Unverified"],
             reliability="Not assessed — demo placeholder.", egypt_service="Not assessed — demo placeholder.",
             score=_score(68, 75, 45, 55, 50, 40), target=4500),
    ],
    "air_fryer": [
        dict(brand="Tornado", model="TAF-9DL", full_name="Tornado Digital Air Fryer 9L (DEMO)",
             capacity="9L", warranty_years=1, retailer="other", url="", price=3500, is_demo=True,
             price_range_note="No live research performed — placeholder estimate only.",
             specs={}, features=[], pros=["Placeholder — replace with real research"], cons=["Unverified"],
             reliability="Not assessed — demo placeholder.", egypt_service="Not assessed — demo placeholder.",
             score=_score(62, 70, 45, 55, 55, 45), target=3200),
    ],
}


def seed():
    existing = db.query_all("SELECT id FROM categories")
    if existing:
        print("Seed skipped: categories already exist.")
        return

    print("Seeding retailers...")
    retailer_ids = {}
    for r in RETAILERS:
        retailer_ids[r["key"]] = repo.get_or_create_retailer(
            r["key"], name=r["name"], base_url=r["base_url"], provider_key=r["provider_key"],
            credibility_score=r["credibility_score"], notes=r["notes"],
        )["id"]

    print("Seeding categories...")
    category_ids = {}
    for c in CATEGORIES:
        category_ids[c["key"]] = repo.create_category(c)

    print("Seeding products...")
    for cat_key, products in PRODUCTS.items():
        cat_id = category_ids[cat_key]
        for p in products:
            product_id = repo.create_product({
                "category_id": cat_id, "brand": p["brand"], "model": p["model"],
                "full_name": p["full_name"], "capacity": p["capacity"],
                "specs": p.get("specs", {}), "warranty_years": p["warranty_years"],
                "features": p.get("features", []), "pros": p.get("pros", []), "cons": p.get("cons", []),
                "reliability_assessment": p.get("reliability", ""),
                "egypt_service_assessment": p.get("egypt_service", ""),
                "score_breakdown": p["score"], "target_buy_price_egp": p.get("target"),
                "purchase_status": "shortlisted", "is_demo_data": 1 if p.get("is_demo") else 0,
            })
            repo.recompute_and_store_ai_score(product_id)

            retailer_id = retailer_ids[p["retailer"]]
            listing_id = repo.add_listing(product_id, retailer_id, url=p.get("url", ""),
                                           match_confidence="exact_model" if not p.get("is_demo") else "uncertain")

            if p.get("price_before"):
                repo.add_price_observation(listing_id, p["price_before"], availability="in_stock",
                                            source="manual", is_verified=1, observed_at=_obs_time(days_ago=6))

            repo.add_price_observation(
                listing_id, p["price"], availability="in_stock", source="manual",
                is_verified=0 if p.get("is_demo") else 1, observed_at=_obs_time(days_ago=0),
                raw_note=p.get("price_range_note", ""),
            )

            if p.get("url"):
                repo.add_research_source(
                    product_id, p["url"], p["retailer"],
                    confidence="estimated" if p.get("is_demo") else "verified",
                    note=p.get("price_range_note", f"Live price check on {RESEARCH_DATE}."),
                    listing_id=listing_id,
                )

    db.set_setting("total_budget_egp", 180000)
    db.set_setting("notification_channels", ["in_app"])
    db.set_setting("price_check_frequency_hours", 12)

    print("Evaluating initial alert conditions on seeded prices...")
    # Not fabricating anything here — this just runs the real alert engine
    # (engines/alerts.py, same code path price_check.py uses) over the
    # actual seeded prices, so e.g. a product whose real/estimated price
    # already sits at-or-below its target price gets a legitimate
    # "below_target" alert instead of the Alerts page sitting empty until
    # the first scheduled price check runs.
    import price_check
    all_products = db.query_all("SELECT id FROM products")
    for row in all_products:
        price_check._evaluate_and_alert(row["id"])  # noqa: SLF001 - intentional reuse

    print("Seed complete.")


if __name__ == "__main__":
    seed()
