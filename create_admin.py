from app import create_app, db
from app.models import User
from werkzeug.security import generate_password_hash

app = create_app()

def create_admin():
    with app.app_context():
        username = input("Enter Admin Username: ")
        email = input("Enter Admin Email: ")
        password = input("Enter Admin Password: ")
        
        if User.query.filter((User.username == username) | (User.email == email)).first():
            print("User already exists!")
            return

        hashed_password = generate_password_hash(password)
        admin = User(username=username, email=email, password_hash=hashed_password, role='admin')
        
        # Create wallet too
        from app.models import Wallet
        wallet = Wallet(user_id=None, balance=0) # will be linked after flush? No, need ID.
        
        db.session.add(admin)
        db.session.flush()
        
        wallet.user_id = admin.id
        db.session.add(wallet)
        
        db.session.commit()
        print(f"Admin user {username} created successfully!")

if __name__ == "__main__":
    create_admin()
