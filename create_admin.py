from getpass import getpass

from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models import User, Wallet

app = create_app()


def create_admin():
    with app.app_context():
        username = input("Enter Admin Username: ").strip()
        email = input("Enter Admin Email: ").strip().lower()
        password = getpass("Enter Admin Password: ")
        if password != getpass("Confirm Admin Password: "):
            print("Passwords do not match.")
            return
        if len(password) < 8:
            print("Password must be at least 8 characters.")
            return

        if User.query.filter((User.username == username) | (User.email == email)).first():
            print("User already exists!")
            return

        admin = User(username=username, email=email, password_hash=generate_password_hash(password), role='admin')
        db.session.add(admin)
        db.session.flush()  # assigns admin.id

        db.session.add(Wallet(user_id=admin.id, balance=0))
        db.session.commit()
        print(f"Admin user {username} created successfully!")


if __name__ == "__main__":
    create_admin()
