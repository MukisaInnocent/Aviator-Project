import os
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

def setup_database():
    print("=== Aviator Database Setup ===")
    print("Authentication failed with the default password.")
    print("Please enter your PostgreSQL credentials to correct the configuration.")
    
    username = input("Postgres Username (default: postgres): ") or "postgres"
    password = input(f"Password for user '{username}': ")
    
    # Try to connect to default 'postgres' database to create the new one
    try:
        conn = psycopg2.connect(
            dbname="postgres",
            user=username,
            password=password,
            host="localhost"
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()
        
        # Check if db exists
        cur.execute("SELECT 1 FROM pg_database WHERE datname = 'aviator_db'")
        exists = cur.fetchone()
        
        if not exists:
            print("Creating database 'aviator_db'...")
            cur.execute("CREATE DATABASE aviator_db")
            print("Database created successfully!")
        else:
            print("Database 'aviator_db' already exists.")
            
        cur.close()
        conn.close()
        
        # Update .env file
        db_url = f"postgresql://{username}:{password}@localhost/aviator_db"
        with open(".env", "w") as f:
            f.write(f"DATABASE_URL={db_url}\n")
            f.write("SECRET_KEY=dev_secret_key_change_in_production\n")
            
        print("\nSUCCESS! .env file updated.")
        print("You can now run 'python run.py'")
        
    except psycopg2.OperationalError as e:
        print("\nERROR: Authentication failed again. Please check your password.")
        print(f"Details: {e}")
    except Exception as e:
        print(f"\nERROR: {e}")

if __name__ == "__main__":
    setup_database()
