# Database initialization for kAIros

import os
import argparse
import datetime
from flask_migrate import Migrate, upgrade, init, migrate, stamp
from app import create_app, models
from app.models import db, Project, Task, TaskStatus, TaskDomain

def setup_migrations(app):
    """Initialize and apply migrations"""
    migrate = Migrate(app, db)
    
    # Check if migrations directory exists
    if not os.path.exists('migrations'):
        print("Initializing migrations...")
        init()
    
    # Generate migration if changes detected
    print("Creating migration...")
    migrate(message="Initial database setup" if not os.path.exists('migrations/versions') else "Update database")
    
    # Apply all migrations
    print("Applying migrations...")
    upgrade()
    
    # Make sure DB is stamped with the latest migration
    print("Stamping database with current migration...")
    stamp()

def create_demo_data(app):
    """Create demo data for development"""
    with app.app_context():
        # Check if we already have demo data
        if Project.query.count() > 0:
            print("Demo data already exists. Skipping...")
            return
        
        print("Creating demo projects...")
        work_project = Project(name="Work Project", domain=TaskDomain.WORK, 
                            description="A demo work project for kAIros")
        admin_project = Project(name="Home Admin", domain=TaskDomain.LIFE_ADMIN,
                             description="Administrative tasks for home life")
        hobby_project = Project(name="Learning Python", domain=TaskDomain.GENERAL_LIFE,
                             description="Personal development project")
        
        db.session.add_all([work_project, admin_project, hobby_project])
        db.session.commit()
        
        print("Creating demo tasks...")
        # Work tasks
        work_tasks = [
            Task(description="Prepare quarterly report", deadline=datetime.datetime.now() + datetime.timedelta(days=5), 
                 estimated_duration=120, domain=TaskDomain.WORK, project=work_project),
            Task(description="Update project documentation", deadline=datetime.datetime.now() + datetime.timedelta(days=2), 
                 estimated_duration=60, domain=TaskDomain.WORK, project=work_project),
            Task(description="Schedule team meeting", deadline=datetime.datetime.now() + datetime.timedelta(days=1), 
                 estimated_duration=15, domain=TaskDomain.WORK, project=work_project),
        ]
        
        # Life admin tasks
        admin_tasks = [
            Task(description="Pay electricity bill", deadline=datetime.datetime.now() + datetime.timedelta(days=10), 
                 estimated_duration=10, domain=TaskDomain.LIFE_ADMIN, project=admin_project),
            Task(description="Book car service", deadline=datetime.datetime.now() + datetime.timedelta(days=14), 
                 estimated_duration=15, domain=TaskDomain.LIFE_ADMIN, project=admin_project),
        ]
        
        # General life tasks
        general_tasks = [
            Task(description="Complete Python course module 3", deadline=datetime.datetime.now() + datetime.timedelta(days=7), 
                 estimated_duration=90, domain=TaskDomain.GENERAL_LIFE, project=hobby_project),
            Task(description="Practice data structures", deadline=datetime.datetime.now() + datetime.timedelta(days=3), 
                 estimated_duration=45, domain=TaskDomain.GENERAL_LIFE, project=hobby_project),
        ]
        
        # Add all tasks
        db.session.add_all(work_tasks + admin_tasks + general_tasks)
        db.session.commit()
        
        print(f"Added {len(work_tasks + admin_tasks + general_tasks)} tasks to {Project.query.count()} projects.")

def main():
    """Main function to initialize database"""
    parser = argparse.ArgumentParser(description='Initialize kAIros database')
    parser.add_argument('--env', choices=['development', 'production', 'testing'], 
                      default='development', help='Environment to initialize')
    parser.add_argument('--demo', action='store_true', help='Create demo data (development only)')
    args = parser.parse_args()
    
    print(f"Initializing {args.env} database...")
    
    # Create app with specified environment
    app = create_app(args.env)
    
    # Setup database
    with app.app_context():
        db.create_all()
        print("Database tables created.")
    
    # Setup migrations
    setup_migrations(app)
    
    # Create demo data if requested and in development environment
    if args.demo and args.env == 'development':
        create_demo_data(app)
    
    print(f"{args.env.capitalize()} database initialization complete!")

if __name__ == '__main__':
    main()