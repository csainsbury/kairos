# Entry point for the kAIros application

import os
from app import create_app

# Create the application instance based on environment
app = create_app(os.environ.get('FLASK_ENV', 'development'))

if __name__ == '__main__':
    # Only for development - in production, use Gunicorn
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))