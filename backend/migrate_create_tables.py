# backend/migrate_create_tables.py
"""Create all database tables"""
from app.database import engine, Base
from app.db_models_users import User, UsageLog

print("Creating all database tables...")
print(f"Using database: {engine.url}")

# Create all tables
Base.metadata.create_all(engine)

print("✅ All tables created successfully!")
print("\nTables created:")
print("  - extractions")
print("  - parser_outputs")
print("  - cache_entries")
print("  - job_states")
print("  - users")
print("  - usage_logs")
print("\nNext steps:")
print("1. Log in to your app to create your user account")
print("2. Run 'python make_admin.py' to make yourself an admin")
