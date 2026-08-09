#!/usr/bin/env python3
"""
Standalone entrypoint for the price-check pipeline, meant to be invoked by
a real OS-level scheduler (cron, systemd timer, Windows Task Scheduler, a
Vercel/Render cron job, etc.) once this app is deployed somewhere with
normal internet access.

Example crontab entry (every 12 hours):
    0 */12 * * * cd /path/to/home-dashboard && /usr/bin/python3 scripts/run_price_check.py >> price_check.log 2>&1

Run with: python scripts/run_price_check.py
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db
import price_check

if __name__ == "__main__":
    db.init_db()
    result = price_check.run_price_check()
    print(json.dumps(result, indent=2, default=str))
