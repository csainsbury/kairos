# kAIros: Domain-Aware Task Management System

kAIros is an intelligent task management application that uses domain awareness, document context, and optimization algorithms to suggest the most efficient use of your time.

## Project Scope

kAIros integrates multiple data sources to provide smart task recommendations:

- **Domain-aware task parsing**: Categorizes tasks into work, life_admin, and general_life domains
- **External integrations**: Todoist, Google Calendar
- **Document context**: Uploads and summarizes documents to provide project context
- **Task ranking engine**: Suggests optimal tasks based on deadlines, estimated duration, and domain weights
- **Natural language interface**: Simple chat-like interface for task interaction
- **Reporting**: Daily email summaries of task completion and trends

## Development Setup

### Prerequisites

- Python 3.9+
- Docker and docker-compose
- Git

### Installation

1. Clone the repository:
   ```bash
   git clone https://your-repository/kAIros.git
   cd kAIros
   ```

2. Set up the development environment:
   ```bash
   # Create a virtual environment
   python -m venv venv
   source venv/bin/activate  # On Windows, use: venv\Scripts\activate
   
   # Install dependencies
   pip install -r requirements.txt
   ```

3. Configure environment variables:
   ```bash
   # Copy the development environment template
   cp .env.development .env
   
   # Edit the .env file with your API keys and settings
   ```

4. Initialize the database:
   ```bash
   flask db init
   flask db migrate -m "Initial migration"
   flask db upgrade
   ```

5. Run the development server:
   ```bash
   flask run
   ```

### Using Docker for Development

1. Make sure Docker and docker-compose are installed
2. Start the development containers:
   ```bash
   docker-compose -f docker/docker-compose.dev.yml up
   ```
3. The application will be available at http://localhost:5000

## Production Deployment

### Prerequisites

- Ubuntu 22.04 LTS server
- Docker and docker-compose installed
- Domain name with DNS configured
- SSL certificates (Let's Encrypt recommended)

### Deployment Steps

1. Clone the repository on your server:
   ```bash
   git clone https://your-repository/kAIros.git
   cd kAIros
   ```

2. Configure production environment:
   ```bash
   # Copy the production environment template
   cp .env.production.template .env.production
   
   # Edit .env.production with secure values
   nano .env.production
   ```

3. Update NGINX configuration:
   ```bash
   # Edit the NGINX configuration with your domain
   nano nginx/conf.d/kairos.conf
   ```

4. Set up SSL certificates:
   ```bash
   # Create a directory for SSL certificates
   mkdir -p ssl_certs
   
   # Copy your SSL certificates or use Let's Encrypt
   # For Let's Encrypt, use certbot on your host machine
   ```

5. Launch the production stack:
   ```bash
   docker-compose -f docker/docker-compose.prod.yml up -d
   ```

6. Initialize the production database:
   ```bash
   docker-compose -f docker/docker-compose.prod.yml exec app flask db upgrade
   ```

## Project Structure

```
kAIros/
  ├── app/
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
  ├── config.py                # Configuration settings
  ├── run.py                   # Application entry point
  ├── docker/                  # Docker configuration
  │    ├── Dockerfile          # Container definition
  │    ├── docker-compose.dev.yml  # Development container setup
  │    └── docker-compose.prod.yml # Production container setup
  ├── nginx/                   # NGINX configuration for production
  │    └── conf.d/             # Server configuration files
  └── migrations/              # Database migration scripts
```

## License

[MIT License](LICENSE)

## Acknowledgements

This project was developed based on modern best practices for Python web applications, with inspiration from many open-source task management and time optimization tools.