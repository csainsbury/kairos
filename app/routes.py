# Routes for kAIros application

from flask import Blueprint, jsonify, render_template, current_app
from app.models import Project, Task, Document

bp = Blueprint('main', __name__)

@bp.route('/', methods=['GET'])
def index():
    """Main landing page - redirects to projects page"""
    return render_template('projects.html', title='kAIros - Projects', projects=Project.query.all())

@bp.route('/health', methods=['GET'])
def health_check():
    """Simple endpoint to verify the server is running"""
    return jsonify({
        'status': 'healthy',
        'version': '0.1.0',
        'environment': current_app.config.get('ENV', 'development')
    })

@bp.route('/api/projects', methods=['GET'])
def get_projects():
    """API endpoint to get all projects"""
    projects = Project.query.all()
    result = []
    
    for project in projects:
        result.append({
            'id': project.id,
            'name': project.name,
            'domain': project.domain.value if project.domain else None
        })
    
    return jsonify({
        'projects': result
    })

@bp.route('/upload', methods=['GET'])
def upload_page():
    """Render the document upload page"""
    return render_template('upload.html', title='Upload Document - kAIros')

@bp.route('/projects', methods=['GET'])
def projects_overview():
    """Render the projects overview page"""
    projects = Project.query.all()
    return render_template('projects.html', title='Projects - kAIros', projects=projects)