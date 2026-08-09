#!/usr/bin/env python3
"""Run with: python scripts/run_seed.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db
import seed

if __name__ == "__main__":
    db.init_db()
    seed.seed()
