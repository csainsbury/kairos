# Database migrations script for kAIros

from flask_migrate import Migrate
from app import create_app, models

# Create application instance
app = create_app()

# Initialize Flask-Migrate
migrate = Migrate(app, models.db)

# This allows us to run migrations using Flask-Migrate CLI
# Example: flask db init, flask db migrate, flask db upgrade
if __name__ == '__main__':
    print("This script is meant to be used with the Flask CLI.")
    print("Run 'flask db init' to initialize migrations.")
    print("Run 'flask db migrate -m \"message\"' to create a migration.")
    print("Run 'flask db upgrade' to apply migrations.")