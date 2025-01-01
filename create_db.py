from app import db, app

with app.app_context():
    db.create_all()  # This will create the database tables
    print("Database created successfully!")