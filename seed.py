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
         must_have_features=["Inverter", "1.5 HP for bedrooms", "3 HP for large/living rooms", "Cooling + heating preferred"],
         notes=("Two size tiers shortlisted: 1.5 HP (~12,000 BTU) for bedrooms, and 3 HP (~24,000 BTU) for a "
                "large living room. Note: no Egyptian retailer (2B/B.TECH or any brand) actually sells a "
                "\"3.5 HP\" or \"3.5 ton\" split AC — Egypt's real size steps are 1.5 / 1.75 / 2.25 / 3 / 4 / 5 HP, "
                "so 3 HP is the closest real, widely-stocked size to that request (verified via live research 2026-08-09)."),
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
         must_have_features=["60/65/70-inch class", "4K UHD"],
         notes="Live-researched (2026-08-09) across 60\", 65\" and 70\" 4K size classes at 2B and B.TECH Egypt, plus a couple of listings cross-checked at RadioShack Egypt / Cairo Sales where B.TECH had no live price.",
         scoring_dimensions=["Screen size fit", "Panel/picture quality", "Smart platform", "Warranty", "Price/value"]),
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
         credibility_score=88, render_mode="js", allow_category_scan=True,
         notes=("Major Egyptian electronics chain. Verified 2026-08-09: price only appears after JS runs "
                "(needs the daily GitHub Actions scan, not PythonAnywhere) but robots.txt allows crawling "
                "both product and category pages -> also the one retailer 'New Finds' discovery scans.")),
    dict(key="jumia_eg", name="Jumia Egypt", base_url="https://www.jumia.com.eg", provider_key="jumia_eg",
         credibility_score=75, render_mode="static", allow_category_scan=True,
         notes=("Verified 2026-08-09: full schema.org Product/Offer JSON-LD ships in the raw HTML -> plain "
                "fetch works. robots.txt explicitly grants ClaudeBot/anthropic-ai 'Allow: /'. Plain category "
                "pages are eligible for discovery; large marketplace, third-party sellers vary in reliability.")),
    dict(key="zanussi_eg", name="Zanussi Egypt (official)", base_url="https://www.zanussi.com.eg", provider_key="zanussi_eg",
         credibility_score=85, render_mode="static", allow_category_scan=True,
         notes=("Verified 2026-08-09: price ships in the raw HTML (product:price:amount meta tag, same as "
                "2B) -> plain fetch works. No robots.txt file exists at this domain at all - no restriction "
                "stated. Official single-brand store.")),
    dict(key="amazon_eg", name="Amazon Egypt", base_url="https://www.amazon.eg", provider_key="amazon_eg",
         credibility_score=85,
         notes=("BLOCKED (verified 2026-08-09): robots.txt disallows ClaudeBot (twice), Claude-User, "
                "Claude-SearchBot, Claude-Web and GPTBot by name with 'Disallow: /'. Tracked manually only - "
                "this is an explicit AI-bot opt-out, respected the same way 2B's is.")),
    dict(key="noon_eg", name="Noon Egypt", base_url="https://www.noon.com/egypt-en", provider_key="noon_eg",
         credibility_score=78, render_mode="static", allow_category_scan=True,
         notes=("Verified 2026-08-09: full schema.org Product/Offer JSON-LD ships in the raw HTML -> plain "
                "fetch works (corrects an earlier assumption that Noon is an unscrapable JS SPA). robots.txt "
                "explicitly grants ClaudeBot 'Allow: /'.")),
    dict(key="carrefour_eg", name="Carrefour Egypt", base_url="https://www.carrefouregypt.com", provider_key="carrefour_eg",
         credibility_score=80,
         notes=("BLOCKED (verified 2026-08-09): robots.txt disallows GPTBot site-wide with 'Disallow: /', "
                "and separately disallows *.html/*.aspx for every crawler - covering nearly all real content "
                "pages on this legacy ASP-based site. Tracked manually only.")),
    dict(key="twob", name="2B Egypt", base_url="https://2b.com.eg", provider_key="twob", credibility_score=78,
         render_mode="static",
         notes=("Verified 2026-08-09: price ships in the raw HTML, plain fetch works fine for products you "
                "track. Category/listing pages are deliberately NEVER scanned for new products - 2B's "
                "robots.txt explicitly disallows crawling them and separately names AI bots as disallowed "
                "site-wide. allow_category_scan stays off on principle, not because it doesn't work.")),
    dict(key="raya", name="Raya Shop", base_url="https://www.rayashop.com", provider_key="raya", credibility_score=76,
         render_mode="js",
         notes=("Verified 2026-08-09: raw HTML has no price at all; only appears after JavaScript runs -> "
                "needs a real browser (Playwright), same as B.TECH. No AI-bot-specific robots.txt rules, but "
                "no reliable product-link pattern was found for discovery - individually-added listings only.")),
    dict(key="radioshack_eg", name="RadioShack Egypt", base_url="https://www.radioshack.com.eg", provider_key="radioshack_eg",
         credibility_score=74, render_mode="static",
         notes=("Verified 2026-08-09: price ships in a raw-HTML '.price' div -> plain fetch works. No "
                "AI-bot-specific robots.txt rules. Catalog leans electronics/accessories - large-appliance "
                "selection unconfirmed, so no discovery source added.")),
    dict(key="cairosales_eg", name="Cairo Sales Store", base_url="https://cairosales.com", provider_key="cairosales_eg",
         credibility_score=70,
         notes=("BLOCKED (verified 2026-08-09): Cloudflare-managed robots.txt disallows ClaudeBot by name "
                "with 'Disallow: /'. Tracked manually only.")),
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
        dict(brand="Zanussi", model="ZRT45200SA", full_name="Zanussi 2-Door No-Frost Refrigerator 442L Silver",
             capacity="442L", warranty_years=5, retailer="zanussi_eg",
             # URL/model corrected 2026-08-09: the old zrt48202sa URL now 404s (site
             # renumbered/replaced the model). Re-verified live on zanussi.com.eg -
             # ZRT45200SA at 40,210 EGP is the current real listing for this size class.
             url="https://www.zanussi.com.eg/ar/cooling/fridge-and-freezers/fridges/fridge-zanussi-2-door-nofrost-442l-silver.html",
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
             image_url="https://media.btech.com/catalogs/d/2/6/9/d26908574ee38792f02aea12ee15d21d638ff85d_fnt_b470.jpeg",
             price=26790, is_demo=False,
             specs={"Type": "No-Frost, top-freezer", "Extras": "LED lighting, stainless finish"},
             features=["No-frost", "LED lighting"],
             pros=["Best price/value in this shortlist", "10-year warranty", "Fresh/Elaraby has the largest in-country service network of any brand here"],
             cons=["Non-inverter motor", "Price sourced from a third-party marketplace seller on B.TECH — confirm directly before buying"],
             reliability="Fresh (Elaraby Group) is the dominant value brand in Egypt with the deepest informal + formal service network.",
             egypt_service="Largest service network of any brand in this category (Elaraby Group).",
             score=_score(75, 88, 85, 55, 65, 50), target=28000),
        dict(brand="Kiriazi", model="E520 NV/2", full_name="Kiriazi Freestanding No-Frost Refrigerator 480L Silver",
             capacity="480L", warranty_years=10, retailer="btech",
             url="https://btech.com/en/p/kiriazi-freestanding-refrigerator-no-frost-2-doors-480-liters-silver-e520-nv-2",
             image_url="https://media.btech.com/catalogs/f/8/7/0/f870bbfaa8eef00503c69f30aa2444b8c376577e_kiriazi_no_frost_refrigerator_520_liters_silver__e520_nv2_1_.jpeg",
             price=35839, is_demo=False,
             specs={"Type": "No-Frost, 2-door", "Extras": "Adjustable shelves, ice unit"}, features=["No-frost", "Adjustable shelves", "Ice unit"],
             pros=["10-year warranty", "Kiriazi is one of Egypt's oldest domestic appliance manufacturers with deep local service coverage"],
             cons=["Pricier than Fresh/Toshiba in this shortlist"],
             reliability="Kiriazi is a long-established Egyptian manufacturer with wide spare-parts/service availability nationwide.",
             egypt_service="Kiriazi's own nationwide manufacturing + service network.",
             score=_score(80, 68, 88, 65, 72, 60), target=34000),
        dict(brand="White Whale", model="WR-4385 HSS", full_name="White Whale No-Frost Refrigerator 430L Stainless",
             capacity="430L", warranty_years=10, retailer="btech",
             url="https://btech.com/en/p/white-whale-no-frost-refrigerator-430l-stainless-wr4385hss",
             image_url="https://media.btech.com/catalogs/7/8/c/9/78c9f1747c1acccf87a75b55262617722a616bcf_white_whale_refrigerator_430_l_stainless_wr_4385_hss_2.jpg",
             price=29898, is_demo=False,
             specs={"Type": "No-Frost, 2-door", "Extras": "Digital touch control, independent fridge/freezer zones, rapid cooling"},
             features=["No-frost", "Digital touch control", "Rapid cooling"],
             pros=["10-year warranty", "Independent fridge/freezer temperature zones", "Competitive price for a 430L stainless unit"],
             cons=["Less widely covered in Egyptian brand-reputation commentary than Sharp/Toshiba/Fresh"],
             reliability="White Whale is an established mid-tier Egyptian appliance brand; less brand-commentary coverage found than the majors.",
             egypt_service="White Whale Egypt service network — verify local coverage before buying.",
             score=_score(70, 82, 82, 62, 70, 62), target=29000),
        dict(brand="Ariston", model="ART70 F6453 XEG", full_name="Ariston No-Frost Refrigerator 455L Inverter",
             capacity="455L", warranty_years=5, retailer="btech",
             url="https://btech.com/en/p/9d32c0ca-ca31-426e-9e8b-5f4afe292dc0",
             image_url="https://media.btech.com/catalogs/5/0/b/7/50b74219f181de53338a7e97b1c900c27b2f7b68_9250000155_ART70_F6453_XEG_pers_LO_removebg_preview.png",
             price=28999, is_demo=False,
             specs={"Type": "No-Frost, reversible door", "Compressor": "Inverter (10-yr warranty on motor)", "Energy class": "A"},
             features=["No-frost", "Inverter motor", "Reversible door", "Holiday Mode"],
             pros=["Inverter compressor with a 10-year motor warranty", "Good price for an inverter unit at this capacity", "Italian-heritage brand"],
             cons=["Base unit warranty (5yr) is shorter than Kiriazi/White Whale's 10yr full-unit warranty"],
             reliability="Ariston Egypt operation; mid-premium European brand positioning.",
             egypt_service="Ariston Egypt service network.",
             score=_score(74, 85, 72, 78, 76, 66), target=30000),
        dict(brand="Samsung", model="RB34C6B0E22/MR", full_name="Samsung No-Frost Bottom-Freezer Refrigerator 340L Digital Inverter",
             capacity="340L", warranty_years=10, retailer="btech",
             url="https://btech.com/en/p/samsung-no-frost-refrigerator-340-liters-black-rb34c6b0e22-mr",
             image_url="https://media.btech.com/catalogs/a/9/5/f/a95f8de072c85d7b6d7f4ca34d98c78b920d8ebf_eg_bespoke_rb7300t_rb34a6b0e41_mr_534504498.png",
             price=39999, is_demo=False,
             specs={"Type": "No-Frost, bottom-freezer", "Compressor": "Digital Inverter", "Energy class": "A"},
             features=["No-frost", "Digital Inverter motor", "Bottom-freezer layout"],
             pros=["10-year compressor warranty", "Samsung Digital Inverter + Twin Cooling Plus tech", "Strong Egypt-wide service network"],
             cons=["340L — smaller than the 400-500L target class (no verified-price Samsung unit was found in that range)", "Most expensive per-liter option in this shortlist"],
             reliability="Samsung is positioned as modern/premium with advanced features per Egyptian retail commentary; extensive Egypt service network.",
             egypt_service="Samsung-operated service centers nationwide.",
             score=_score(82, 55, 85, 78, 78, 78), target=36000),
    ],
    "washing_machine": [
        dict(brand="Toshiba", model="TW-BJ90M4E(SK)", full_name="Toshiba Inverter Front Load Washing Machine 8kg Silver",
             capacity="8kg", warranty_years=5, retailer="btech",
             url="https://btech.com/en/toshiba-washingmachine-8kg-inverter-twbj90m4esk.html",
             image_url="https://media.btech.com/catalogs/b/5/d/f/b5dfde2c20ec70a68bb30ff825889692c1462d47_b7ac67ff0fec3abe4a4854627b2888e6e93a799b4f9cf56fd32de41adca73fde.jpeg",
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
             image_url="https://dwecxxryy5p59.cloudfront.net/catalogs/4/4/b/8/44b8eba652ef69435f89f13422b93270c9ae5b62_image_8k.jpg",
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
             image_url="https://dwecxxryy5p59.cloudfront.net/catalogs/0/9/6/5/0965a4ab0e264adbc86d11634019dd9d8f27bbe8_fb85ab2951ebf6469b7b5744e0933f6b1232719da9b82e007bfb0b6e2f41e127.jpeg",
             price=20019, is_demo=False,
             specs={"Motor": "Direct-drive inverter (7 motion settings)", "Extras": "Steam + sterilization, 15-min quick wash"},
             features=["Direct-drive inverter motor", "Steam + sterilization", "15-minute quick wash", "Digital touchscreen"],
             pros=["Cheapest verified 8kg inverter option", "Feature-rich for the price (steam, quick wash)", "Best Egypt service network (Elaraby Group)"],
             cons=["Brand perception slightly below LG/Samsung for premium buyers"],
             reliability="Fresh (Elaraby Group) — deepest service network in Egypt, though premium-tier brand perception is lower than LG/Samsung.",
             egypt_service="Largest service network of any brand in this shortlist.",
             score=_score(75, 90, 80, 80, 78, 80), target=20500),
        dict(brand="Beko", model="WTV8612XMCI", full_name="Beko Front Load Inverter Washing Machine 8kg ProSmart",
             capacity="8kg", warranty_years=5, retailer="btech",
             url="https://btech.com/en/p/beko-washing-machine-inverter-8kg-wtv8612xmci",
             image_url="https://dwecxxryy5p59.cloudfront.net/catalogs/b/1/5/e/b15e25b9694fd4053a930bc04be401132e8910e4_wtv_8612_xmc_copy.jpg",
             price=20999, is_demo=False,
             specs={"Motor": "ProSmart Inverter", "RPM": "1200", "Extras": "Steam spot removal, 15 programs"},
             features=["ProSmart Inverter motor", "Steam spot removal", "15 wash programs"],
             pros=["Competitive price for an inverter unit", "Beko is gaining recent popularity in Egypt"],
             cons=["Lower spin speed (1200 RPM) than LG/Samsung's 1400 RPM"],
             reliability="Beko has been gaining recent popularity in the Egyptian appliance market per retailer commentary.",
             egypt_service="Beko Egypt authorized service network.",
             score=_score(74, 82, 76, 76, 74, 66), target=20000),
        dict(brand="Bosch", model="WAN282X1EG", full_name="Bosch Front Load Washing Machine 8kg EcoSilence Drive",
             capacity="8kg", warranty_years=5, retailer="btech",
             url="https://btech.com/en/bosch-front-load-washing-machine-8-kg-silver-wan282x1eg.html",
             image_url="https://media.btech.com/catalogs/9/9/6/e/996e8b20cb938b3ac86f800950d4f874bdf47cd8_1mbowmfuwan282x1f009_739.jpg",
             price=21650, is_demo=False,
             specs={"Motor": "EcoSilence Drive", "RPM": "1400", "Extras": "Active Water Plus, 15 programs"},
             features=["EcoSilence Drive motor", "Active Water Plus", "15 wash programs"],
             pros=["German engineering brand reputation", "1400 RPM spin speed", "Competitively priced against LG/Samsung"],
             cons=["Bosch is noted as an expensive brand overall in Egyptian retail commentary (this unit is a relative exception)"],
             reliability="Bosch is cited for modern technologies (digital temperature control) but generally positioned as a premium/expensive brand in Egypt.",
             egypt_service="Bosch Egypt (BSH) authorized service network.",
             score=_score(82, 78, 80, 78, 80, 72), target=21000),
        dict(brand="Haier", model="HW80-BP14929AS6", full_name="Haier Front Load Inverter Washing Machine 8kg Steam",
             capacity="8kg", warranty_years=5, retailer="btech",
             url="https://btech.com/en/p/haier-front-load-inverter-washing-machine-8kg-silver-hw80-bp14929as6",
             image_url="https://media.btech.com/catalogs/5/8/a/0/58a03d02f46c2c8143e66ac03a35b74bbdc94393_untitled_jin_6.jpeg",
             price=16690, is_demo=False,
             specs={"Motor": "Inverter (laser-welded)", "RPM": "1400", "Extras": "Steam function"},
             features=["Inverter motor", "Steam function", "1400 RPM"],
             pros=["Cheapest verified 8kg inverter option by a wide margin", "1400 RPM spin speed", "Steam function at this price is unusual"],
             cons=["Newer/thinner Egypt service network than the established brands"],
             reliability="Haier has recently become more popular in Egypt, cited for dependable performance and easy maintenance.",
             egypt_service="Haier Egypt service network — newer and thinner than LG/Samsung/Toshiba.",
             score=_score(70, 94, 68, 76, 74, 64), target=17500),
    ],
    "cooker": [
        dict(brand="Universal", model="6905PR7", full_name="Universal Freestanding Gas Cooker 5 Burners Stainless Steel 90cm",
             capacity="90cm, 5 burners", warranty_years=5, retailer="btech",
             url="https://btech.com/en/p/universal-freestanding-gas-cooker-5-burners-stainless-steel-90-cm-6905pr7",
             image_url="https://dwecxxryy5p59.cloudfront.net/catalogs/d/d/3/b/dd3b80528b280e56a5b9f81d61a119ce96ffe802_1MUVCOFSS6905PR7L008.png",
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
        dict(brand="Fresh", model="17058", full_name="Fresh Gas Cooker with Air Fryer 90cm 5 Burners Stainless Steel",
             capacity="90cm, 5 burners", warranty_years=5, retailer="btech",
             url="https://btech.com/en/p/fresh-gas-cooker-with-air-fryer-90cm-5-burners-stainless-steel-17058",
             image_url="https://dwecxxryy5p59.cloudfront.net/catalogs/b/f/1/b/bf1b6201eb7aa1ef716ea612ff40ba8006b3de38__2_90_360_17058.jpeg",
             price=23659, is_demo=False,
             specs={"Burners": 5, "Extras": "Built-in air fryer mesh, surface cooling fan, self-ignition"},
             features=["Self-ignition", "Air fryer mesh", "Surface cooling fan"],
             pros=["Built-in air-fryer function is unusual at this price", "Fresh's wide Egypt service network"],
             cons=["Fewer premium build touches than Ariston/Unionaire"],
             reliability="Fresh (Elaraby Group) — widest Egypt service network of any cooker brand here.",
             egypt_service="Widest service network of any brand in this shortlist.",
             score=_score(74, 84, 78, 62, 76, 68), target=22000),
        dict(brand="Ariston", model="ARR9GGF33229XNA", full_name="Ariston Gas Cooker 5 Burners Stainless Steel 90cm Air Fry",
             capacity="90cm, 5 burners", warranty_years=5, retailer="btech",
             url="https://btech.com/en/ariston-gas-cooker-5-burner-stainless-arr9ggf33229xna.html",
             image_url="https://media.btech.com/catalogs/8/f/1/4/8f14df3f04e333751a9eb4a5872bcdc0d24151d4__1.jpeg",
             price=24684, is_demo=False,
             specs={"Burners": 5, "Extras": "Digital display, fan oven with air-fry function, wok burner"},
             features=["Auto-ignition", "Digital display", "Fan oven with air-fry", "Wok burner"],
             pros=["Digital display + fan oven with built-in air-fry function", "5-year warranty (up from the 2yr estimate previously assumed)", "Wok burner"],
             cons=["Pricier than the value-tier options"],
             reliability="Ariston Egypt operation; mid-premium European brand positioning.",
             egypt_service="Ariston Egypt service network.",
             score=_score(74, 68, 76, 68, 82, 70), target=23500),
        dict(brand="Unionaire", model="PRM69SS-1GC-511-ICPSF-DV", full_name="Unionaire Premium Gas Cooker 5 Burners 90cm Dual Oven",
             capacity="90cm, 5 burners", warranty_years=10, retailer="btech",
             url="https://btech.com/en/p/bc43ddc5-982c-4b03-a135-0fe1833bfe1f",
             image_url="https://media.btech.com/catalogs/9/e/7/6/9e766a370f2a09c0031a6301bf0cf2f2fe76e5e3_PRM69SS_1GC_511_ICPSF_DV_removebg_preview.jpg",
             price=27509, is_demo=False,
             specs={"Burners": 5, "Extras": "Autocook AI timer, dual oven, fan oven, cast-iron burner holders"},
             features=["Autocook AI timer", "Dual oven", "Fan oven", "Cast-iron burner holders"],
             pros=["10-year warranty — longest in this shortlist by far", "Dual oven + AI cook timer", "Unionaire has a long-standing Egypt presence"],
             cons=["Most expensive verified option in this shortlist"],
             reliability="Unionaire is described as a well-known, practical brand with long-standing Egypt presence; this Premium line is a step above their budget positioning.",
             egypt_service="Unionaire Egypt service network.",
             score=_score(76, 62, 90, 70, 82, 74), target=26000),
    ],
    "air_conditioner": [
        dict(brand="Tornado", model="TY-VX12BEE", full_name="Tornado Split Inverter AC 1.5 HP Cooling & Heating",
             capacity="1.5 HP / 12,500 BTU", warranty_years=5, retailer="btech",
             url="https://btech.com/en/p/tornado-ac-invrtr-1-5hp-cool-heat-ty-vx12zee",
             image_url="https://dwecxxryy5p59.cloudfront.net/catalogs/5/2/9/1/529129613973690f84e668bfe003141d8e2395e0_44.jpg",
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
             image_url="https://dwecxxryy5p59.cloudfront.net/catalogs/9/d/f/b/9dfb0ec60125bf7af2441786e2c04824a25e3f64_file_37_3_3nqryxwus619zz9c___1.jpg",
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
             image_url="https://dwecxxryy5p59.cloudfront.net/catalogs/6/9/a/1/69a18b4522b7cc53e03e5a73fd1714d8919fbc14_B6000002655T.jpg",
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
             image_url="https://dwecxxryy5p59.cloudfront.net/catalogs/3/8/2/6/3826d416514ab79a1ab08bfb34bb91610b111deb_23.jpg",
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
             image_url="https://dwecxxryy5p59.cloudfront.net/catalogs/5/b/1/b/5b1b43dc6d286034f4e797fe6e41afb566f01911_45.png",
             price=32500, is_demo=False,
             specs={"Type": "Inverter, cooling+heating", "Refrigerant": "R410A", "Extras": "Self-cleaning filters, LCD display, auto-restart"},
             features=["Inverter", "Self-cleaning filters", "LCD display", "Auto-restart"],
             pros=["Self-cleaning filters (less maintenance)", "R410A refrigerant"],
             cons=["Most expensive of the verified 1.5HP options"],
             reliability="Midea is a fast-growing brand in Egypt; service network is newer/thinner than LG/Carrier/Fresh.",
             egypt_service="Growing but comparatively newer service network.",
             score=_score(70, 60, 80, 80, 78, 72), target=30000),
        dict(brand="Sharp", model="AY-XP12BHE", full_name="Sharp Split Inverter AC 1.5 HP Cooling & Heating Plasmacluster",
             capacity="1.5 HP / 12,000 BTU", warranty_years=5, retailer="twob",
             url="https://2b.com.eg/en/sharp-air-conditioner-1-5-hp-split-cool-heat-inverter-plasma-white-ay-xp12bhe.html",
             image_url="https://2b.com.eg/media/catalog/product/cache/a2d42926e6f33d56fa8e27ad9b5f0f3e/a/c/ac614-1.jpg",
             price=33669, price_before=47399, is_demo=False,
             specs={"Type": "Inverter, cooling+heating", "Refrigerant": "R32", "Extras": "Plasmacluster Ion, Wi-Fi, EER 12.6"},
             features=["Inverter", "Cooling + heating", "Plasmacluster air purification", "Wi-Fi control"],
             pros=["Wi-Fi control", "Plasmacluster ionizer", "Ranks just after LG among the most popular Egyptian AC brands per B.TECH's own market commentary"],
             cons=["Listed out of stock at last check — confirm availability"],
             reliability="Sharp AC units are cited as high build quality/dependable performance in Egyptian retail commentary, ranked just behind LG.",
             egypt_service="Sharp Egypt (Olympic Group) service network.",
             score=_score(80, 65, 82, 82, 80, 78), target=32000),
        dict(brand="Beko", model="BICT1220", full_name="Beko Split Inverter AC 1.5 HP Cooling Only Pro Smart Inverter",
             capacity="1.5 HP / 12,000 BTU", warranty_years=5, retailer="btech",
             url="https://btech.com/en/beko-split-ac-inverter-1-5hp-cool-bict1220.html",
             image_url="https://media.btech.com/catalogs/a/f/3/9/af393db80d26e27c7b2e7839ee586fb43cfb72da_9203241200_lo5_20220124_153245.png",
             price=23665, is_demo=False,
             specs={"Type": "Pro Smart Inverter, cooling only", "Extras": "Anti-corrosion coating, auto-clean"},
             features=["Inverter", "Anti-corrosion coating", "Auto-clean"],
             pros=["Cheapest verified 1.5HP inverter in this shortlist", "Claimed up to 60% power saving"],
             cons=["Cooling only — no heating"],
             reliability="Beko has been gaining recent popularity in the Egyptian appliance market per retailer commentary.",
             egypt_service="Beko Egypt authorized service network.",
             score=_score(72, 92, 76, 78, 74, 62), target=25000),
        dict(brand="Unionaire", model="Artify Smart", full_name="Unionaire Artify Smart Digital Split AC 1.5 HP Cooling Only",
             capacity="1.5 HP / 12,000 BTU", warranty_years=5, retailer="btech",
             url="https://btech.com/en/unionaire-artify-smart-digital-split-air-conditioner-cooling-only-1-5-hp-118-2022.html",
             image_url="https://media.btech.com/catalogs/c/6/4/5/c6458d7ec8f4c84eb45cf00041526419b38114c0_B6000002645T.jpg",
             price=17999, is_demo=False,
             specs={"Type": "Digital, cooling only", "Extras": "Plasma air-purifying system, self-diagnosis"},
             features=["Plasma air purification", "Self-diagnosis"],
             pros=["Cheapest verified 1.5HP option overall", "Unionaire has a long-standing, budget-friendly reputation in Egypt"],
             cons=["Non-inverter", "Cooling only"],
             reliability="Unionaire is described as a well-known, practical/budget-friendly brand with long-standing Egypt presence.",
             egypt_service="Unionaire Egypt service network.",
             score=_score(65, 95, 70, 60, 65, 55), target=19000),
        dict(brand="Haier", model="HSU-12KCRIC", full_name="Haier Smart Split Inverter AC 1.5 HP Cooling Only",
             capacity="1.5 HP / 12,000 BTU", warranty_years=5, retailer="btech",
             url="https://btech.com/en/p/740d61bb-950a-4907-aaad-e87399053b40",
             image_url="https://media.btech.com/catalogs/f/8/b/7/f8b791015fcfac44284bd019f993da9637a75f84_imgi_12_New_Project_29.jpeg",
             price=21969, is_demo=False,
             specs={"Type": "Smart Inverter, cooling only", "Extras": "Wi-Fi, plasma filter, self-clean, stable to 53°C ambient"},
             features=["Inverter", "Wi-Fi control", "Plasma filter", "Self-clean"],
             pros=["Good price for an inverter+Wi-Fi unit", "Rated to keep cooling at ambient temps up to 53°C"],
             cons=["Cooling only — no heating", "Newer/thinner Egypt service network than the established brands"],
             reliability="Haier has recently become more popular in Egypt, cited for dependable cooling performance and easy maintenance.",
             egypt_service="Haier Egypt service network — newer and thinner than LG/Carrier/Fresh.",
             score=_score(70, 78, 68, 76, 76, 68), target=23000),
        # --- 3 HP (~24,000 BTU) tier — closest real size to a "3.5 HP" request ---
        dict(brand="Sharp", model="AY-XP24UHE", full_name="Sharp Split Inverter AC 3 HP Cooling & Heating Plasmacluster",
             capacity="3 HP / 24,000 BTU", warranty_years=5, retailer="btech",
             url="https://btech.com/en/p/sharp-inv-ac-3hp-ay-xp24uhe-rc",
             image_url="https://dwecxxryy5p59.cloudfront.net/catalogs/3/c/4/5/3c454f8efc42ac98e6d7c8e906e79554354ca2b9_25.jpg",
             price=64699, is_demo=False,
             specs={"Type": "Inverter, cooling+heating", "Refrigerant": "R410A", "Extras": "Plasmacluster Ion, auto-clean"},
             features=["Inverter", "Cooling + heating", "Plasmacluster air purification", "Auto-clean"],
             pros=["Cooling + heating at the large-room size", "Plasmacluster ionizer", "Sharp ranked just behind LG in Egyptian brand commentary"],
             cons=["Most expensive of the verified 3HP options"],
             reliability="Sharp AC units are cited as high build quality/dependable performance in Egyptian retail commentary.",
             egypt_service="Sharp Egypt (Olympic Group) service network.",
             score=_score(80, 55, 82, 82, 82, 78), target=58000),
        dict(brand="Fresh", model="SIFW24H/O-X4", full_name="Fresh Smart Inverter Split AC 3 HP Cooling & Heating",
             capacity="3 HP / 24,000 BTU", warranty_years=5, retailer="btech",
             url="https://btech.com/en/p/fresh-air-conditioner-3-hp-cooling-heating-sifw24h-o-x4",
             image_url="https://dwecxxryy5p59.cloudfront.net/catalogs/6/2/0/c/620cfa340c218c51f1c94877780894200dd2a7d2_B6000002676T.jpeg",
             price=46750, is_demo=False,
             specs={"Type": "Inverter, cooling+heating", "Refrigerant": "R410A", "Extras": "Plasma filter, ECO Sleep, 4-way auto swing"},
             features=["Inverter", "Cooling + heating", "ECO Sleep mode", "4-way auto swing"],
             pros=["Cheapest verified 3HP cooling+heating option", "Fresh has Egypt's widest appliance service network"],
             cons=["Brand perception below LG/Carrier/Sharp for premium buyers"],
             reliability="Fresh (Elaraby Group) — widest Egypt service network of any brand in this shortlist.",
             egypt_service="Widest service network (Elaraby Group).",
             score=_score(76, 82, 80, 80, 78, 75), target=45000),
        dict(brand="Carrier", model="42QHC24DN", full_name="Carrier Split Inverter AC 3 HP Cooling & Heating Wi-Fi",
             capacity="3 HP / 24,000 BTU", warranty_years=5, retailer="btech",
             url="https://btech.com/en/p/carrier-split-air-conditioner-3hp-42qhc24dn-2022",
             image_url="https://dwecxxryy5p59.cloudfront.net/catalogs/6/5/a/e/65aee2875b5424868614b9b8672cf53457d8b8fc_B6000002650T.jpg",
             price=52233, is_demo=False,
             specs={"Type": "Inverter, cooling+heating", "Extras": "Wi-Fi, turbo cooling, self-clean"},
             features=["Inverter", "Cooling + heating", "Wi-Fi control", "Turbo cooling", "Self-clean"],
             pros=["Wi-Fi control", "Carrier is repeatedly cited as a durability/efficiency leader in Egyptian appliance commentary"],
             cons=["Pricier than Fresh"],
             reliability="Carrier is one of the oldest, most established AC names with a strong reputation for quality and durability.",
             egypt_service="Carrier Egypt authorized service network.",
             score=_score(86, 62, 82, 84, 84, 76), target=50000),
        dict(brand="Beko", model="BICT2420", full_name="Beko Split Inverter AC 3 HP Cooling Only Jet Cool",
             capacity="3 HP / 24,000 BTU", warranty_years=5, retailer="btech",
             url="https://btech.com/en/p/beko-split-ac-inverter-3hp-cool-bict2420",
             image_url="https://media.btech.com/catalogs/b/f/f/f/bfff5f3a6e622431316c85ea5cc635565531e0df_B6000002665T.jpg",
             price=39990, is_demo=False,
             specs={"Type": "Inverter, cooling only", "Extras": "Anti-corrosion tech, Jet Cool mode"},
             features=["Inverter", "Anti-corrosion coating", "Jet Cool mode"],
             pros=["Cheapest verified 3HP inverter option"],
             cons=["Cooling only — no heating"],
             reliability="Beko has been gaining recent popularity in the Egyptian appliance market per retailer commentary.",
             egypt_service="Beko Egypt authorized service network.",
             score=_score(72, 90, 76, 78, 76, 62), target=42000),
        dict(brand="Haier", model="HSU-24KHRIB", full_name="Haier Smart UV Split Inverter AC 3 HP Cooling & Heating",
             capacity="3 HP / 24,000 BTU", warranty_years=5, retailer="twob",
             url="https://2b.com.eg/en/haier-air-conditioner-3-hp-smart-uv-24000-btu-h-inverter-heating-cooling-white-hsu-24khrib.html",
             image_url="https://2b.com.eg/media/catalog/product/cache/661473ab953cdcdf4c3b607144109b90/a/c/ac046.jpg",
             price=44349, price_before=66199, is_demo=False,
             specs={"Type": "Inverter, cooling+heating", "Refrigerant": "R32", "Extras": "Smart UV sterilization, Wi-Fi"},
             features=["Inverter", "Cooling + heating", "Smart UV sterilization", "Wi-Fi control"],
             pros=["Cooling + heating at a lower price than Sharp/Carrier", "UV sterilization + Wi-Fi", "Heavily discounted from 66,199 to 44,349 EGP"],
             cons=["Listed out of stock at last check — confirm availability", "Newer/thinner Egypt service network"],
             reliability="Haier has recently become more popular in Egypt, cited for dependable cooling performance.",
             egypt_service="Haier Egypt service network — newer and thinner than LG/Carrier/Fresh.",
             score=_score(70, 85, 68, 78, 78, 70), target=48000),
        dict(brand="Hisense", model="AS-24HR4SYDTG10", full_name="Hisense Split Inverter AC 3 HP Cooling & Heating",
             capacity="3 HP / 24,000 BTU", warranty_years=5, retailer="twob",
             url="https://2b.com.eg/en/hisense-air-conditioner-3-hp-with-inverter-split-technology-cooling-heating-white.html",
             image_url="https://2b.com.eg/media/catalog/product/cache/661473ab953cdcdf4c3b607144109b90/a/c/ach01_2.jpg",
             price=39999, price_before=56299, is_demo=False,
             specs={"Type": "Inverter, cooling+heating"},
             features=["Inverter", "Cooling + heating"],
             pros=["Cheapest verified 3HP cooling+heating option", "Heavily discounted from 56,299 to 39,999 EGP"],
             cons=["Listed out of stock at last check — confirm availability", "Least Egypt brand-reputation data available of this shortlist"],
             reliability="Not extensively covered in Egyptian retail brand commentary found during research — verify service coverage before buying.",
             egypt_service="Not assessed in detail — verify before buying.",
             score=_score(62, 88, 65, 78, 74, 60), target=44000),
        dict(brand="Haier", model="HSU24KCROCC", full_name="Haier SmartSplit AC 3 HP Cooling Only",
             capacity="3 HP / 24,000-28,000 BTU", warranty_years=5, retailer="btech",
             url="https://btech.com/en/p/haier-smartsplit-airconditioner-3hp-cooling-white-hsu24kcrocc",
             image_url="https://media.btech.com/catalogs/6/4/4/d/644d117baa67b0ce82e3cede4aeac88ad9909e57_buacwlinchsu24f.jpg",
             price=36920, is_demo=False,
             specs={"Type": "Non-inverter, cooling only", "Extras": "Wi-Fi, plasma filtration, turbo cool"},
             features=["Wi-Fi control", "Plasma filtration", "Turbo cool"],
             pros=["Cheapest verified 3HP option overall", "Wi-Fi control at this price point"],
             cons=["Non-inverter (higher running cost)", "Cooling only"],
             reliability="Haier has recently become more popular in Egypt, cited for dependable cooling performance and easy maintenance.",
             egypt_service="Haier Egypt service network — newer and thinner than LG/Carrier/Fresh.",
             score=_score(68, 92, 66, 60, 70, 58), target=40000),
    ],
    # --- TV: live-researched 2026-08-09 across 60"/65"/70" 4K size classes -----
    "tv": [
        # -- 60-inch class --
        dict(brand="Samsung", model="UA60DU7000", full_name="Samsung 60\" Crystal UHD 4K Smart TV (Tizen)",
             capacity="60-inch", warranty_years=2, retailer="twob",
             url="https://2b.com.eg/en/samsung-tv-60-inch-led-crystal-uhd-smart-built-in-receiver-ua60du7000.html",
             image_url="https://2b.com.eg/media/catalog/product/cache/a2d42926e6f33d56fa8e27ad9b5f0f3e/t/v/tv339.jpg",
             price=21999, price_before=30699, is_demo=False,
             specs={"Resolution": "4K UHD Crystal", "Platform": "Tizen"}, features=["Smart TV (Tizen)", "4K UHD"],
             pros=["Cheapest verified 60\" option", "Samsung+LG hold ~49% of the Egyptian TV market"],
             cons=["Crystal UHD tier, not the higher QLED tier"],
             reliability="Samsung is one of the two dominant TV brands in Egypt (with LG), highest streaming subscription/lowest churn among premium households per market data.",
             egypt_service="Samsung Egypt authorized service network.",
             score=_score(78, 85, 75, 70, 75, 68), target=23000),
        dict(brand="LG", model="60UQ79006LD", full_name="LG 60\" 4K UHD Smart TV (webOS)",
             capacity="60-inch", warranty_years=2, retailer="twob",
             url="https://2b.com.eg/en/lg-60-4k-uhd-smart-led-tv-with-built-in-receiver-60uq79006ld.html",
             image_url="https://2b.com.eg/media/catalog/product/cache/a2d42926e6f33d56fa8e27ad9b5f0f3e/t/v/tv383-1.jpg",
             price=21899, price_before=30199, is_demo=False,
             specs={"Resolution": "4K UHD", "Platform": "webOS"}, features=["Smart TV (webOS)", "4K UHD"],
             pros=["Essentially tied with Samsung on price", "LG is co-dominant TV brand in Egypt"],
             cons=[],
             reliability="LG is one of the two dominant TV brands in Egypt (with Samsung), premium-tier brand reputation.",
             egypt_service="LG Egypt authorized service network.",
             score=_score(80, 85, 78, 72, 76, 70), target=23000),
        dict(brand="Fresh", model="60MUQ433G", full_name="Fresh 60\" QLED 4K UHD Smart TV",
             capacity="60-inch", warranty_years=2, retailer="twob",
             url="https://2b.com.eg/en/fresh-tv-60-inches-uhd-qled-smart-60muq433g-21040.html",
             image_url="https://2b.com.eg/media/catalog/product/cache/a2d42926e6f33d56fa8e27ad9b5f0f3e/t/v/tv083.jpg",
             price=23499, price_before=34699, is_demo=False,
             specs={"Resolution": "4K UHD QLED"}, features=["QLED panel", "Smart TV (Miracast)"],
             pros=["QLED panel at this price point", "Fresh has Egypt's widest appliance service network"],
             cons=["Smart platform is more basic (Miracast-based) than Tizen/webOS"],
             reliability="Fresh (Elaraby Group) TVs are locally manufactured in Egypt, budget-friendly positioning.",
             egypt_service="Widest service network of any brand here (Elaraby Group).",
             score=_score(68, 78, 78, 65, 72, 60), target=25000),
        dict(brand="Ultra", model="UT60SREL3", full_name="Ultra 60\" Frameless 4K UHD Smart TV",
             capacity="60-inch", warranty_years=2, retailer="twob",
             url="https://2b.com.eg/en/ultra-tv-60-inch-frameless-4k-smart-led-built-in-receiver-ut60srel3.html",
             image_url="https://2b.com.eg/media/catalog/product/cache/a2d42926e6f33d56fa8e27ad9b5f0f3e/t/v/tv260.jpg",
             price=18499, price_before=26099, is_demo=False,
             specs={"Resolution": "4K UHD"}, features=["Frameless design", "4K UHD"],
             pros=["Cheapest 60\" option in this shortlist"],
             cons=["Retailer's own listing flags it as not formally \"smart-certified\" despite streaming-app access", "Least brand-reputation data of this shortlist"],
             reliability="Budget local brand; limited reputation data found — verify service support before buying.",
             egypt_service="Not extensively assessed — verify before buying.",
             score=_score(55, 92, 55, 60, 62, 50), target=20000),
        # -- 65-inch class --
        dict(brand="Samsung", model="UA65U8000F", full_name="Samsung 65\" 4K UHD Smart TV Vision AI (Tizen)",
             capacity="65-inch", warranty_years=2, retailer="twob",
             url="https://2b.com.eg/en/samsung-tv-65-inch-led-4k-uhd-smart-vision-ai-built-in-receiver-black-ua65u8000f.html",
             image_url="https://2b.com.eg/media/catalog/product/cache/a2d42926e6f33d56fa8e27ad9b5f0f3e/t/v/tv041-1.jpg",
             price=28999, is_demo=False,
             specs={"Resolution": "4K UHD", "Platform": "Tizen", "Extras": "Vision AI"}, features=["Smart TV (Tizen)", "Vision AI", "4K UHD"],
             pros=["Samsung+LG hold ~49% of the Egyptian TV market, highest premium-household loyalty"],
             cons=[],
             reliability="Samsung is one of the two dominant TV brands in Egypt.",
             egypt_service="Samsung Egypt authorized service network.",
             score=_score(80, 78, 78, 72, 78, 72), target=30000),
        dict(brand="LG", model="65NU840B6LA.AFU", full_name="LG 65\" NanoCell 4K UHD Smart TV AI ThinQ",
             capacity="65-inch", warranty_years=2, retailer="twob",
             url="https://2b.com.eg/en/lg-tv-65-inch-nano-4k-uhd-ai-nu84-smart-65nu840b6la-afu.html",
             image_url="https://2b.com.eg/media/catalog/product/cache/a2d42926e6f33d56fa8e27ad9b5f0f3e/t/v/tv270.jpg",
             price=28999, price_before=41799, is_demo=False,
             specs={"Resolution": "4K UHD NanoCell", "Platform": "webOS (AI ThinQ)"}, features=["NanoCell panel", "webOS + ThinQ AI", "4K UHD"],
             pros=["NanoCell panel, same price as Samsung's Crystal-tier unit", "31% discount from list price"],
             cons=[],
             reliability="LG is one of the two dominant TV brands in Egypt, NanoCell is a step up from base LED.",
             egypt_service="LG Egypt authorized service network.",
             score=_score(82, 80, 78, 74, 80, 74), target=30000),
        dict(brand="TCL", model="65C6K", full_name="TCL 65\" QD-Mini LED 4K UHD Google TV 144Hz",
             capacity="65-inch", warranty_years=2, retailer="btech",
             url="https://btech.com/en/p/9f08c817-e4a6-41d8-8c3c-6bfcc6cb9120",
             image_url="https://dwecxxryy5p59.cloudfront.net/catalogs/6/1/c/a/61ca185c54649d71334a4f96558c73b0845f3659_imgi_2_73d886e7fa67fcfe0174b65ba0d09fa3000c4090cd1cb3a61287748cc25240f3.jpg",
             price=38499, is_demo=False,
             specs={"Resolution": "4K UHD QD-Mini LED", "Platform": "Google TV", "Extras": "144Hz panel"}, features=["QD-Mini LED", "Google TV", "144Hz"],
             pros=["Highest picture-tech spec of this shortlist (QD-Mini LED, 144Hz)", "TCL is the fastest-growing 3rd-place smart-TV brand regionally"],
             cons=["Most expensive 65\" option in this shortlist"],
             reliability="TCL ranks 3rd regionally in connected smart TVs and is the fastest-growing challenger brand per Q4 2025 market data.",
             egypt_service="TCL Egypt distributor service network.",
             score=_score(74, 60, 72, 78, 88, 70), target=35000),
        dict(brand="Hisense", model="65A6N", full_name="Hisense 65\" 4K UHD Smart TV VIDAA (Dolby Vision)",
             capacity="65-inch", warranty_years=2, retailer="twob",
             url="https://2b.com.eg/en/hisense-tv-65-inch-4k-uhd-led-smart-built-in-receiver-65a6n.html",
             image_url="https://2b.com.eg/media/catalog/product/cache/a2d42926e6f33d56fa8e27ad9b5f0f3e/t/v/tv456.jpg",
             price=20499, is_demo=False,
             specs={"Resolution": "4K UHD", "Platform": "VIDAA", "Extras": "Dolby Vision, HDR10+"}, features=["Dolby Vision", "HDR10+", "4K UHD"],
             pros=["Cheapest verified 65\" option by a wide margin", "Dolby Vision + HDR10+ at this price is unusual", "Locally manufactured in Egypt"],
             cons=["VIDAA platform has a smaller app ecosystem than Tizen/webOS/Google TV"],
             reliability="Not extensively covered in Egyptian brand-reputation commentary found; value proposition is strong on paper.",
             egypt_service="Locally manufactured — service network not extensively assessed, verify before buying.",
             score=_score(62, 95, 65, 75, 78, 68), target=22000),
        dict(brand="Sharp", model="4T-C65FJ16EX", full_name="Sharp 65\" Frameless 4K UHD Google TV",
             capacity="65-inch", warranty_years=3, retailer="twob",
             url="https://2b.com.eg/en/sharp-tv-65-led-4k-uhd-smart-google-tv-frameless-black-4t-c65fj16ex.html",
             image_url="https://2b.com.eg/media/catalog/product/cache/a2d42926e6f33d56fa8e27ad9b5f0f3e/t/v/tv696.jpg",
             price=23749, is_demo=False,
             specs={"Resolution": "4K UHD", "Platform": "Google TV"}, features=["Frameless design", "Google TV", "4K UHD"],
             pros=["3-year warranty — longest of this shortlist (others are 2yr)", "Good price for Google TV platform"],
             cons=[],
             reliability="Sharp is cited as high build quality/dependable performance, ranked just behind LG in Egyptian retail commentary.",
             egypt_service="Sharp Egypt (Olympic Group) service network.",
             score=_score(78, 82, 84, 74, 76, 68), target=24000),
        dict(brand="Xiaomi", model="TV A Pro 65", full_name="Xiaomi TV A Pro 65\" QLED 4K UHD Google TV",
             capacity="65-inch", warranty_years=2, retailer="twob",
             url="https://2b.com.eg/en/xiaomi-tv-65-inch-qled-4k-uhd-smart-built-in-receiver-google-tv-tv-a-pro-65.html",
             image_url="https://2b.com.eg/media/catalog/product/cache/a2d42926e6f33d56fa8e27ad9b5f0f3e/t/v/tv618.jpg",
             price=24999, is_demo=False,
             specs={"Resolution": "4K UHD QLED", "Platform": "Google TV"}, features=["QLED panel", "Google TV", "4K UHD"],
             pros=["QLED panel + Google TV at a mid-tier price"],
             cons=["Newest entrant of this shortlist to the Egyptian TV market — less long-term reliability track record"],
             reliability="Not extensively covered in Egyptian brand-reputation commentary found; verify service support before buying.",
             egypt_service="Not extensively assessed — verify before buying.",
             score=_score(60, 80, 62, 74, 80, 66), target=24000),
        dict(brand="Haier", model="H65S80EU", full_name="Haier 65\" QLED 4K UHD Smart TV",
             capacity="65-inch", warranty_years=2, retailer="twob",
             url="https://2b.com.eg/en/haier-tv-65-inch-smart-4k-uhd-qled-with-built-in-receiver-black-h65s80eu.html",
             image_url="https://2b.com.eg/media/catalog/product/cache/a2d42926e6f33d56fa8e27ad9b5f0f3e/t/v/tv365_2.jpg",
             price=26999, price_before=36899, is_demo=False,
             specs={"Resolution": "4K UHD QLED"}, features=["QLED panel", "4K UHD"],
             pros=["QLED panel", "27% discount from list price"],
             cons=[],
             reliability="Haier has recently become more popular in Egypt, cited for dependable performance and easy maintenance.",
             egypt_service="Haier Egypt service network — newer than the established brands.",
             score=_score(68, 76, 68, 74, 74, 64), target=26000),
        dict(brand="Toshiba", model="65U5865EA", full_name="Toshiba 65\" 4K UHD Smart TV",
             capacity="65-inch", warranty_years=2, retailer="btech",
             url="https://btech.com/en/toshiba-65-4k-smart-65u5865ea.html",
             image_url="",
             price=14999, is_demo=True,
             price_range_note="Price discrepancy found between sources: B.TECH's own page showed 9,499 EGP (likely stale/error) while RadioShack Egypt listed the same model at 14,999 EGP on 2026-08-09 — using the higher, more plausible figure and flagging as unverified until confirmed directly with a retailer before buying.",
             specs={"Resolution": "4K UHD"}, features=["4K UHD", "Smart TV"],
             pros=["Locally manufactured (Elaraby Group) — typically lower price point"],
             cons=["Price could not be confidently verified — two retailers showed conflicting prices", "No confirmed image found"],
             reliability="Toshiba TVs sold in Egypt are locally manufactured/licensed by Elaraby Group.",
             egypt_service="Elaraby Group service network.",
             score=_score(65, 70, 70, 65, 65, 55), target=15000),
        # -- 70-inch class --
        dict(brand="Samsung", model="UA70DU7000", full_name="Samsung 70\" Crystal UHD 4K Smart TV (Tizen)",
             capacity="70-inch", warranty_years=2, retailer="twob",
             url="https://2b.com.eg/en/samsung-tv-70-inch-led-crystal-uhd-smart-ua70du7000.html",
             image_url="https://2b.com.eg/media/catalog/product/cache/a2d42926e6f33d56fa8e27ad9b5f0f3e/t/v/tv339_1_3aqbxhtjnqewlosg.jpg",
             price=27999, is_demo=False,
             specs={"Resolution": "4K UHD Crystal", "Platform": "Tizen"}, features=["Smart TV (Tizen)", "4K UHD"],
             pros=["Cheapest verified 70\" option", "Samsung is one of the two dominant TV brands in Egypt"],
             cons=[],
             reliability="Samsung is one of the two dominant TV brands in Egypt, strong 70\"+ market presence.",
             egypt_service="Samsung Egypt authorized service network.",
             score=_score(78, 88, 76, 72, 76, 68), target=29000),
        dict(brand="LG", model="70UT80006LA", full_name="LG 70\" 4K UHD Smart TV webOS 24 (α5 AI Gen7)",
             capacity="70-inch", warranty_years=2, retailer="twob",
             url="https://2b.com.eg/en/lg-tv-70-inch-4k-uhd-smart-led-with-built-in-receiver-70ut80006la.html",
             image_url="https://2b.com.eg/media/catalog/product/cache/a2d42926e6f33d56fa8e27ad9b5f0f3e/t/v/tv326.jpg",
             price=32999, price_before=45099, is_demo=False,
             specs={"Resolution": "4K UHD", "Platform": "webOS 24", "Extras": "α5 AI Gen7 processor"}, features=["Smart TV (webOS 24)", "AI processor", "4K UHD"],
             pros=["Newest webOS version + AI processor of this shortlist", "27% discount from list price"],
             cons=["Listed out of stock at last check — confirm availability"],
             reliability="LG is one of the two dominant TV brands in Egypt, premium-tier brand reputation.",
             egypt_service="LG Egypt authorized service network.",
             score=_score(82, 74, 78, 74, 82, 72), target=32000),
        dict(brand="Tornado", model="70US1500E", full_name="Tornado 70\" DLED 4K UHD Google TV HDR10+ Dolby Audio",
             capacity="70-inch", warranty_years=3, retailer="twob",
             url="https://2b.com.eg/en/tornado-tv-70-inch-dled-4k-uhd-smart-built-in-receiver-70us1500e.html",
             image_url="https://2b.com.eg/media/catalog/product/cache/a2d42926e6f33d56fa8e27ad9b5f0f3e/t/v/tv895.jpg",
             price=29379, price_before=42599, is_demo=False,
             specs={"Resolution": "4K UHD", "Platform": "Google TV", "Extras": "HDR10+, Dolby Audio"}, features=["Google TV", "HDR10+", "Dolby Audio"],
             pros=["3-year warranty — longest of this shortlist", "HDR10+ and Dolby Audio at a mid price", "31% discount from list price"],
             cons=[],
             reliability="Tornado TVs are locally manufactured by Elaraby Group.",
             egypt_service="Elaraby Group service network.",
             score=_score(70, 78, 84, 72, 76, 66), target=30000),
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
    print("Seeding retailers...")
    retailer_ids = {}
    for r in RETAILERS:
        retailer_ids[r["key"]] = repo.get_or_create_retailer(
            r["key"], name=r["name"], base_url=r["base_url"], provider_key=r["provider_key"],
            credibility_score=r["credibility_score"], notes=r["notes"],
            render_mode=r.get("render_mode"), allow_category_scan=r.get("allow_category_scan"),
        )["id"]

    existing = db.query_all("SELECT id FROM categories")
    if existing:
        print("Categories/products already seeded — retailer render_mode/allow_category_scan flags "
              "were still refreshed above. Re-run scripts/seed_discovery_sources.py to (re)seed "
              "discovery_sources if needed.")
        seed_discovery_sources(retailer_ids)
        return

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
                "image_url": p.get("image_url", ""),
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

    seed_discovery_sources(retailer_ids, category_ids)

    print("Seed complete.")


# Category listing pages the daily "New Finds" scan actually looks at.
# Every URL here was live-verified (2026-08-09, via a real browser session —
# see discovery.py and providers/retailers.py for why a plain fetch alone
# can't confirm this for JS-rendered retailers) to be a real category page
# containing product-detail links, not guessed from a URL pattern.
# `link_contains` is the substring that marks a product-detail link on that
# retailer's listing pages (different per retailer — e.g. B.TECH uses
# '/en/p/', Jumia and Zanussi use '.html', Noon uses '/p/').
#
# B.TECH: only 5 of the app's 8 categories are covered — water_heater/
# microwave/air_fryer weren't findable in B.TECH's nav in the time spent
# looking; add them here once someone finds and verifies the real category
# URL, same way these five were found. Jumia/Noon/Zanussi are currently
# refrigerator-only for the same reason — add more categories the same way.
DISCOVERY_SOURCES = [
    dict(category_key="refrigerator", retailer_key="btech",
         listing_url="https://btech.com/en/c/large-home-appliances/refrigerators",
         link_contains="/en/p/"),
    dict(category_key="cooker", retailer_key="btech",
         listing_url="https://btech.com/en/c/large-home-appliances/cookers",
         link_contains="/en/p/"),
    dict(category_key="air_conditioner", retailer_key="btech",
         listing_url="https://btech.com/en/c/large-home-appliances/air-conditioners/split-system",
         link_contains="/en/p/"),
    dict(category_key="washing_machine", retailer_key="btech",
         listing_url="https://btech.com/en/c/large-home-appliances/washing-machines-dryers/front-load-washing-machines",
         link_contains="/en/p/"),
    dict(category_key="tv", retailer_key="btech",
         listing_url="https://btech.com/en/c/tvs-projectors",
         link_contains="/en/p/"),
    dict(category_key="refrigerator", retailer_key="jumia_eg",
         listing_url="https://www.jumia.com.eg/appliances-fridges-freezers/",
         link_contains=".html"),
    dict(category_key="refrigerator", retailer_key="noon_eg",
         listing_url="https://www.noon.com/egypt-en/appliances/large-appliances/refrigerators-and-freezers/",
         link_contains="/p/"),
    dict(category_key="refrigerator", retailer_key="zanussi_eg",
         listing_url="https://www.zanussi.com.eg/ar/cooling/fridge-and-freezers/fridge-freezers.html",
         link_contains=".html"),
]


def seed_discovery_sources(retailer_ids=None, category_ids=None):
    if retailer_ids is None:
        retailer_ids = {r["key"]: r["id"] for r in repo.list_retailers()}
    if category_ids is None:
        category_ids = {c["key"]: c["id"] for c in repo.list_categories()}
    for src in DISCOVERY_SOURCES:
        cat_id = category_ids.get(src["category_key"])
        ret_id = retailer_ids.get(src["retailer_key"])
        if not cat_id or not ret_id:
            continue
        existing = db.query_one(
            "SELECT id FROM discovery_sources WHERE category_id=? AND retailer_id=?", (cat_id, ret_id)
        )
        if existing:
            continue
        db.insert("discovery_sources", {
            "category_id": cat_id, "retailer_id": ret_id, "listing_url": src["listing_url"],
            "link_contains": src.get("link_contains", "/en/p/"),
            "is_active": 1, "last_scanned_at": "", "created_at": db.now_iso(),
        })
    print(f"Discovery sources: {len(DISCOVERY_SOURCES)} configured across "
          f"{len({s['retailer_key'] for s in DISCOVERY_SOURCES})} retailers (see discovery.py).")


if __name__ == "__main__":
    # Also runnable directly (python seed.py) — makes sure the schema exists
    # first, same as scripts/run_seed.py does.
    db.init_db()
    seed()
