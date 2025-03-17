# kAIros: Domain-Aware Task Management System

kAIros is an intelligent task management application that uses domain awareness, document context, and optimization algorithms to suggest the most efficient use of your time.

## Project Scope

kAIros integrates multiple data sources to provide smart task recommendations:

- **Domain-aware task parsing**: Categorizes tasks into work, life_admin, and general_life domains
- **External integrations**: 
  - **Todoist**: Sync tasks from your Todoist account
  - **Google Calendar**: Schedule tasks as calendar events and track available time
- **Document context**: Uploads and summarizes documents to provide project context
- **Task ranking engine**: Suggests optimal tasks based on deadlines, estimated duration, and domain weights
- **Natural language interface**: Simple chat-like interface for task interaction
- **Reporting**: Daily email summaries of task completion and trends

## Quick Start

The easiest way to get started is using our deployment scripts:

```bash
# For development environment
./scripts/deploy.sh --env development

# For production environment
./scripts/deploy.sh --env production
```

## Development Setup

### Prerequisites

- Python 3.9+
- Docker and docker-compose
- Git

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/kAIros.git
   cd kAIros
   ```

2. Configure environment variables:
   ```bash
   # Copy the development environment template
   cp .env.development.template .env.development
   
   # Edit the environment file with your API keys and settings
   ```

3. Deploy the development environment:
   ```bash
   ./scripts/deploy.sh --env development
   ```

4. Access the application at http://localhost:5000

### Manual Development Setup

If you prefer to set up without Docker:

1. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows, use: venv\Scripts\activate
   
   # Install dependencies
   pip install -r requirements.txt
   ```

2. Initialize the database:
   ```bash
   flask db init
   flask db migrate -m "Initial migration"
   flask db upgrade
   ```

3. Run the development server:
   ```bash
   flask run
   ```

## Production Deployment

### Prerequisites

- Ubuntu server (20.04 LTS or newer recommended)
- Docker and docker-compose installed
- Domain name with DNS configured
- SSL certificates (Let's Encrypt recommended)

### Automated Deployment

1. Clone the repository on your server:
   ```bash
   git clone https://github.com/yourusername/kAIros.git
   cd kAIros
   ```

2. Configure production environment:
   ```bash
   # Copy the production environment template
   cp .env.production.template .env.production
   
   # Edit .env.production with secure values
   nano .env.production
   ```

3. Deploy using the script:
   ```bash
   ./scripts/deploy.sh --env production
   ```

4. Follow the post-deployment instructions for SSL setup

### Manual Deployment Steps

See our [detailed deployment guide](docs/deployment.md) for manual deployment instructions and more advanced configuration options.

## Database Management

The application includes built-in database management scripts:

```bash
# Create database backup
./scripts/backup_database.sh

# Restore from backup
./scripts/restore_database.sh /backups/kairos_20250301_120000.backup
```

## Monitoring

Check the status of your deployment:

```bash
./scripts/status.sh --env production
```

## Project Structure

```
kAIros/
  ├── app/                     # Application code
  │    ├── __init__.py         # App initialization
  │    ├── models.py           # Database models
  │    ├── routes.py           # API endpoints
  │    ├── todoist.py          # Todoist integration
  │    ├── calendar.py         # Google Calendar integration
  │    ├── document.py         # Document upload and summarization
  │    ├── ranking.py          # Task ranking algorithm
  │    ├── chat.py             # Conversational interface
  │    └── utils.py            # Utility functions
  ├── tests/                   # Unit and integration tests
  ├── scripts/                 # Deployment and maintenance scripts
  │    ├── deploy.sh           # Deployment script
  │    ├── backup_database.sh  # Database backup script
  │    ├── restore_database.sh # Database restore script
  │    └── status.sh           # Status monitoring script
  ├── static/                  # Static assets
  │    └── error_pages/        # Custom error pages
  ├── config.py                # Configuration settings
  ├── run.py                   # Application entry point
  ├── docker/                  # Docker configuration
  │    ├── Dockerfile          # Container definition
  │    ├── docker-compose.dev.yml  # Development container setup
  │    └── docker-compose.prod.yml # Production container setup
  ├── nginx/                   # NGINX configuration for production
  │    └── conf.d/             # Server configuration files
  ├── docs/                    # Documentation
  │    ├── deployment.md       # Detailed deployment guide
  │    └── google_calendar_setup.md # Google Calendar API setup
  └── migrations/              # Database migration scripts
```

## Documentation

- [Deployment Guide](docs/deployment.md)
- [Google Calendar Setup](docs/google_calendar_setup.md)

## License

[MIT License](LICENSE)

## Acknowledgements

This project was developed based on modern best practices for Python web applications, with inspiration from many open-source task management and time optimization tools.