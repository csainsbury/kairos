# Document Upload and Summarisation Module for kAIros

import os
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
import magic

from app.utils import setup_logger, retry_with_backoff

# Setup module logger
logger = setup_logger(__name__)

# Create blueprint for document handling
document_bp = Blueprint('document', __name__, url_prefix='/documents')

def allowed_file(filename):
    """Check if file has an allowed extension"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']

def check_mime_type(file_path):
    """Verify file MIME type for security"""
    mime = magic.Magic(mime=True)
    file_type = mime.from_file(file_path)
    
    # List of allowed MIME types
    allowed_types = ['application/pdf', 'text/plain']
    
    if file_type not in allowed_types:
        logger.warning(f"Rejected file with MIME type: {file_type}")
        return False
    return True

@retry_with_backoff(max_retries=2)
def generate_summary(text_content):
    """Generate a summary using LLM API
    
    Args:
        text_content: The text to summarize
        
    Returns:
        Summary text
    """
    # Placeholder - Will be implemented in Task 4
    logger.info("Generating document summary")
    return "This is a placeholder summary. Actual LLM integration will be added in Task 4."

@document_bp.route('/upload', methods=['POST'])
def upload_document():
    """Endpoint for document uploads"""
    # Check if the post request has the file part
    if 'file' not in request.files:
        return jsonify({'status': 'error', 'message': 'No file part'}), 400
        
    file = request.files['file']
    project_id = request.form.get('project_id')
    
    # If user does not select file, browser also submits an empty part
    if file.filename == '':
        return jsonify({'status': 'error', 'message': 'No selected file'}), 400
        
    if not project_id:
        return jsonify({'status': 'error', 'message': 'Project ID is required'}), 400
        
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        upload_folder = current_app.config['UPLOAD_FOLDER']
        
        # Create upload directory if it doesn't exist
        os.makedirs(upload_folder, exist_ok=True)
        
        file_path = os.path.join(upload_folder, filename)
        file.save(file_path)
        
        # Verify file type for security
        if not check_mime_type(file_path):
            os.remove(file_path)  # Remove the unsafe file
            return jsonify({'status': 'error', 'message': 'Invalid file type'}), 400
        
        # Placeholder for future document processing
        # Will be expanded in Task 4
        logger.info(f"Document uploaded: {filename} for project {project_id}")
        
        return jsonify({
            'status': 'success',
            'filename': filename,
            'message': 'File uploaded successfully'
        })
        
    return jsonify({'status': 'error', 'message': 'File type not allowed'}), 400