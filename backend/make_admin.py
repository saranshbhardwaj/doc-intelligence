# backend/make_admin.py
"""Make a user an admin by email"""
from app.database import get_db
from app.db_models_users import User

db = next(get_db())

# Replace with YOUR email from Clerk
admin_email = input("Enter admin email address: ").strip()

user = db.query(User).filter(User.email == admin_email).first()
if user:
    user.tier = "admin"
    user.pages_limit = -1  # Unlimited
    db.commit()
    print(f"✅ {admin_email} is now an admin with unlimited pages!")
else:
    print(f"❌ User {admin_email} not found. Please log in to the app first, then run this script.")

db.close()
