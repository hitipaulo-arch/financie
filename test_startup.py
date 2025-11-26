#!/usr/bin/env python
"""
Test script to verify Flask app can start with lazy database initialization.
This tests the core fix: deferring engine creation to avoid import failures.
"""

import os
import sys
import time

# Set minimal environment for testing
os.environ.setdefault("FLASK_ENV", "development")
os.environ.setdefault("DEBUG", "False")

print("[TEST] Starting Flask app import test...")
start_time = time.time()

try:
    print("[TEST] Importing backend module...")
    from backend import create_app
    print("[TEST] ✅ Backend module imported successfully")
    
    print("[TEST] Creating Flask app...")
    app = create_app()
    print("[TEST] ✅ Flask app created successfully")
    
    print("[TEST] Checking Flask app has routes...")
    routes_count = len([rule for rule in app.url_map.iter_rules()])
    print(f"[TEST] ✅ Flask app has {routes_count} routes")
    
    if routes_count < 10:
        print("[TEST] ⚠️  WARNING: Less than 10 routes found, expected 30+")
        sys.exit(1)
    
    print("[TEST] Checking health endpoint...")
    with app.test_client() as client:
        response = client.get('/api/health')
        if response.status_code == 200:
            print("[TEST] ✅ Health endpoint works")
        else:
            print(f"[TEST] ❌ Health endpoint failed: {response.status_code}")
            sys.exit(1)
    
    elapsed = time.time() - start_time
    print(f"[TEST] ✅ All tests passed in {elapsed:.2f}s")
    sys.exit(0)
    
except Exception as e:
    elapsed = time.time() - start_time
    print(f"[TEST] ❌ Test failed after {elapsed:.2f}s")
    print(f"[TEST] Error: {str(e)}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
