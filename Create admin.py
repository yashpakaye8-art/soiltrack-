"""
One-time script to force-create the default admin account.
Run this ONCE if admin login isn't working:
    python create_admin.py
"""
from app import app, db, User
from werkzeug.security import generate_password_hash

with app.app_context():
    # Check if any user with username 'admin' exists
    existing = User.query.filter_by(username='admin').first()

    if existing:
        print(f"⚠️  User 'admin' already exists with role: {existing.role}")
        existing.password = generate_password_hash('admin123')
        existing.role = 'admin'
        existing.fullname = existing.fullname or 'Administrator'
        db.session.commit()
        print("✅ Password reset to 'admin123' and role confirmed as 'admin'.")
    else:
        new_admin = User(
            fullname='Administrator',
            username='admin',
            password=generate_password_hash('admin123'),
            role='admin'
        )
        db.session.add(new_admin)
        db.session.commit()
        print("✅ New admin account created!")

    print("\nLogin with:")
    print("   username: admin")
    print("   password: admin123")