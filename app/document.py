# Document Upload and Summarisation Module for kAIros

import os
import io
import re
import time
import json
import base64
import requests
import tempfile
import PyPDF2
from flask import Blueprint, request, jsonify, current_app, send_file
from werkzeug.utils import secure_filename
import magic
from datetime import datetime

from app.utils import setup_logger, retry_with_backoff
from app.models import db, Document, Project

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
    return True, file_type

def extract_text_from_pdf(file_path):
    """Extract text content from PDF file
    
    Args:
        file_path: Path to the PDF file
        
    Returns:
        Extracted text content
    """
    try:
        text = ""
        with open(file_path, 'rb') as pdf_file:
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            for page_num in range(len(pdf_reader.pages)):
                page = pdf_reader.pages[page_num]
                text += page.extract_text() + "\n\n"
        return text
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {str(e)}")
        return None

def read_text_file(file_path):
    """Read text content from file
    
    Args:
        file_path: Path to the text file
        
    Returns:
        File text content
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        return content
    except UnicodeDecodeError:
        # Try with different encoding if utf-8 fails
        try:
            with open(file_path, 'r', encoding='latin-1') as file:
                content = file.read()
            return content
        except Exception as e:
            logger.error(f"Error reading text file with latin-1 encoding: {str(e)}")
            return None
    except Exception as e:
        logger.error(f"Error reading text file: {str(e)}")
        return None

@retry_with_backoff(max_retries=3)
def generate_summary_with_llm(text_content, max_length=4000):
    """Generate a summary using LLM API
    
    Args:
        text_content: The text to summarize
        max_length: Maximum length to send to the API
        
    Returns:
        Summary text
    """
    # Trim text content if too long
    if len(text_content) > max_length:
        logger.info(f"Trimming content from {len(text_content)} to {max_length} chars")
        text_content = text_content[:max_length]
    
    # Get API details from config
    api_key = current_app.config.get('LLM_API_KEY')
    api_url = current_app.config.get('LLM_API_URL')
    
    if not api_key or not api_url:
        logger.error("LLM API key or URL not configured")
        return "Summary could not be generated. LLM API not configured."
    
    # Prepare prompt for summary
    prompt = f"""Please provide a concise summary of the following document. 
Focus on extracting the key information, main points, and any important details.
The summary should be comprehensive but brief (200-300 words).

DOCUMENT TEXT:
{text_content}

SUMMARY:"""
    
    # Prepare request
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    payload = {
        "model": "deepseek-ai/deepseek-llm-7b-chat", # Default for demonstration
        "messages": [
            {"role": "system", "content": "You are a helpful assistant that summarizes documents accurately."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,  # Low temperature for more factual response
        "max_tokens": 500    # Limit response length
    }
    
    try:
        # Make request to LLM API
        response = requests.post(api_url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        
        # Parse response
        result = response.json()
        
        # Extract summary from response
        if 'choices' in result and len(result['choices']) > 0:
            summary = result['choices'][0]['message']['content'].strip()
            return summary
        else:
            logger.error(f"Unexpected API response format: {result}")
            return "Error generating summary. Unexpected API response format."
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Error calling LLM API: {str(e)}")
        raise  # Allow retry mechanism to handle this
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        logger.error(f"Error parsing LLM API response: {str(e)}")
        return "Error generating summary. Could not parse API response."

def generate_summary(text_content):
    """Generate a summary using LLM API or fallback to a simpler approach
    
    Args:
        text_content: The text to summarize
        
    Returns:
        Summary text
    """
    # Check if we have a valid LLM API configuration
    if current_app.config.get('ENV') == 'production' or (
            current_app.config.get('LLM_API_KEY') and 
            current_app.config.get('LLM_API_URL')):
        try:
            # Use LLM API for summarization
            return generate_summary_with_llm(text_content)
        except Exception as e:
            logger.error(f"LLM summarization failed, falling back to basic summary: {str(e)}")
    
    # Fallback: Basic summarization for development/testing or if API fails
    logger.info("Using basic summarization as fallback")
    
    # Simple summarization: extract first few sentences and key phrases
    sentences = re.split(r'(?<=[.!?])\s+', text_content)
    word_count = len(text_content.split())
    
    # Calculate how many sentences to include based on document length
    if word_count > 1000:
        intro_sentences = sentences[:3]
        # Take some sentences from middle and end too for longer docs
        mid_point = len(sentences) // 2
        middle_sentences = sentences[mid_point:mid_point+2]
        end_sentences = sentences[-3:]
        selected_sentences = intro_sentences + middle_sentences + end_sentences
    else:
        # For shorter docs, just take first few sentences
        selected_sentences = sentences[:5]
    
    basic_summary = " ".join(selected_sentences)
    
    # Add note about fallback method
    if len(basic_summary) > 10:
        return basic_summary + "\n\n(Note: This is a basic extract, not a semantic summary.)"
    else:
        return "Could not generate a meaningful summary from the provided document."

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
    
    # Verify project exists
    project = Project.query.get(project_id)
    if not project:
        return jsonify({'status': 'error', 'message': 'Project not found'}), 404
        
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        timestamp = int(time.time())
        unique_filename = f"{timestamp}_{filename}"
        
        # Generate directory path with project subfolder
        project_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], f"project_{project_id}")
        os.makedirs(project_folder, exist_ok=True)
        
        file_path = os.path.join(project_folder, unique_filename)
        file.save(file_path)
        
        # Verify file type for security
        mime_check, file_type = check_mime_type(file_path)
        if not mime_check:
            os.remove(file_path)  # Remove the unsafe file
            return jsonify({'status': 'error', 'message': 'Invalid file type'}), 400
        
        # Extract text from the file based on type
        if file_type == 'application/pdf':
            text_content = extract_text_from_pdf(file_path)
        elif file_type == 'text/plain':
            text_content = read_text_file(file_path)
        else:
            text_content = None
        
        # Generate summary if text was extracted
        if text_content:
            summary = generate_summary(text_content)
            logger.info(f"Generated summary for {filename}")
        else:
            summary = "Could not extract text content from this file."
            logger.warning(f"Failed to extract text from {filename}")
        
        # Create document record in database
        document = Document(
            filename=filename,
            file_path=file_path,
            file_type=file_type,
            project_id=project.id,
            summary=summary,
            created_at=datetime.utcnow()
        )
        db.session.add(document)
        db.session.commit()
        
        logger.info(f"Document uploaded and processed: {filename} for project {project_id}")
        
        return jsonify({
            'status': 'success',
            'document_id': document.id,
            'filename': filename,
            'summary': summary[:200] + "..." if len(summary) > 200 else summary,
            'message': 'Document uploaded and summarized successfully'
        })
        
    return jsonify({'status': 'error', 'message': 'File type not allowed'}), 400

@document_bp.route('/<int:document_id>', methods=['GET'])
def get_document(document_id):
    """Get document details"""
    document = Document.query.get_or_404(document_id)
    
    return jsonify({
        'id': document.id,
        'filename': document.filename,
        'file_type': document.file_type,
        'project_id': document.project_id,
        'summary': document.summary,
        'created_at': document.created_at.isoformat()
    })

@document_bp.route('/<int:document_id>/summary', methods=['GET'])
def get_document_summary(document_id):
    """Get just the document summary"""
    document = Document.query.get_or_404(document_id)
    
    return jsonify({
        'id': document.id,
        'filename': document.filename,
        'summary': document.summary
    })

@document_bp.route('/<int:document_id>/download', methods=['GET'])
def download_document(document_id):
    """Download the original document file"""
    document = Document.query.get_or_404(document_id)
    
    try:
        return send_file(document.file_path, 
                      as_attachment=True, 
                      download_name=document.filename)
    except FileNotFoundError:
        return jsonify({'status': 'error', 'message': 'File not found on server'}), 404

@document_bp.route('/project/<int:project_id>', methods=['GET'])
def get_documents_for_project(project_id):
    """Get all documents for a project"""
    # Verify project exists
    project = Project.query.get_or_404(project_id)
    
    # Get all documents for the project
    documents = Document.query.filter_by(project_id=project_id).all()
    
    result = []
    for doc in documents:
        result.append({
            'id': doc.id,
            'filename': doc.filename,
            'file_type': doc.file_type,
            'summary': doc.summary[:100] + "..." if len(doc.summary) > 100 else doc.summary,
            'created_at': doc.created_at.isoformat()
        })
    
    return jsonify({
        'project_id': project_id,
        'project_name': project.name,
        'document_count': len(result),
        'documents': result
    })