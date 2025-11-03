#!/usr/bin/env python3
"""Quick script to check if job_states table exists"""

import sqlite3

conn = sqlite3.connect('sandcloud_dev.db')
cursor = conn.cursor()

# Get all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()

print("Tables in database:")
for table in tables:
    print(f"  - {table[0]}")

# Check if job_states exists
if any('job_states' in table for table in tables):
    print("\n✓ job_states table EXISTS")

    # Show schema
    cursor.execute("PRAGMA table_info(job_states);")
    columns = cursor.fetchall()
    print("\nColumns:")
    for col in columns:
        print(f"  - {col[1]} ({col[2]})")
else:
    print("\n✗ job_states table DOES NOT EXIST")
    print("\nYou need to run the migration:")
    print("  python migrate_add_job_state.py")

conn.close()
