from flask import Blueprint, render_template, abort

import config
import repository as repo

pages_bp = Blueprint("pages", __name__)


@pages_bp.get("/")
def dashboard():
    data = repo.get_dashboard()
    return render_template("dashboard.html", page="dashboard", **data)


@pages_bp.get("/appliances/<key>")
def category_page(key):
    category = repo.get_category_by_key(key)
    if category is None:
        abort(404)
    products = repo.list_products(category_id=category["id"])
    budget = repo.get_budget_summary(exclude_category_id=category["id"] if category["priority_level"] == 1 else None)
    recs = {}
    for p in products:
        recs[p["id"]] = repo.get_recommendation_for_product(p["id"])
    return render_template("category.html", page="category", category=category, products=products,
                            budget=budget, recommendations=recs)


@pages_bp.get("/products/<int:product_id>")
def product_page(product_id):
    product = repo.get_product(product_id)
    if product is None:
        abort(404)
    history = repo.get_price_history(product_id)
    rec = repo.get_recommendation_for_product(product_id)
    retailers = repo.list_retailers()
    return render_template("product.html", page="product", product=product, history=history,
                            recommendation=rec, retailers=retailers)


@pages_bp.get("/wishlist")
def wishlist_page():
    categories = repo.list_categories()
    retailers = repo.list_retailers()
    researching = repo.list_products(status="researching")
    return render_template("wishlist.html", page="wishlist", categories=categories, retailers=retailers,
                            researching=researching)


@pages_bp.get("/my-home")
def my_home_page():
    purchases = repo.list_purchases()
    budget = repo.get_budget_summary()
    return render_template("my_home.html", page="my_home", purchases=purchases, budget=budget)


@pages_bp.get("/alerts")
def alerts_page():
    alerts = repo.list_alerts(limit=200)
    return render_template("alerts_page.html", page="alerts", alerts=alerts)


@pages_bp.get("/settings")
def settings_page():
    import db
    categories = repo.list_categories()
    settings = {
        "total_budget_egp": db.get_setting("total_budget_egp", config.TOTAL_BUDGET_EGP),
        "price_check_frequency_hours": db.get_setting("price_check_frequency_hours", config.PRICE_CHECK_FREQUENCY_HOURS),
        "notification_channels": db.get_setting("notification_channels", config.NOTIFICATION_CHANNELS),
    }
    retailers = repo.list_retailers()
    return render_template("settings.html", page="settings", categories=categories, settings=settings,
                            retailers=retailers)
