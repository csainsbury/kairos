# Tests for Document Upload and Summarisation Module

import unittest
import sys
import os
import tempfile
import json
from io import BytesIO
from unittest.mock import patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.models import db, Document, Project, TaskDomain

class DocumentTestCase(unittest.TestCase):
    """Test case for document upload and summarization"""
    
    def setUp(self):
        """Set up test environment"""
        self.app = create_app('testing')
        self.app.config['TESTING'] = True
        self.app.config['UPLOAD_FOLDER'] = tempfile.mkdtemp()
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.client = self.app.test_client()
        db.create_all()
        
        # Create a test project
        self.project = Project(name="Test Project", domain=TaskDomain.WORK)
        db.session.add(self.project)
        db.session.commit()
    
    def tearDown(self):
        """Clean up test environment"""
        db.session.remove()
        db.drop_all()
        self.app_context.pop()
    
    @patch('app.document.extract_text_from_pdf')
    @patch('app.document.check_mime_type')
    def test_upload_pdf(self, mock_check_mime, mock_extract_text):
        """Test uploading a PDF file"""
        # Mock file type check and text extraction
        mock_check_mime.return_value = (True, 'application/pdf')
        mock_extract_text.return_value = "This is sample PDF text content."
        
        # Create a mock PDF file
        pdf_data = BytesIO(b'%PDF-1.4 mock pdf content')
        pdf_data.name = 'test.pdf'
        
        # Mock the generate_summary function
        with patch('app.document.generate_summary') as mock_generate_summary:
            mock_generate_summary.return_value = "This is a summary of the PDF."
            
            # Upload the file
            response = self.client.post(
                '/documents/upload',
                data={'file': (pdf_data, 'test.pdf'), 'project_id': self.project.id},
                content_type='multipart/form-data'
            )
            
            # Check response
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertEqual(data['status'], 'success')
            self.assertEqual(data['filename'], 'test.pdf')
            
            # Verify the document was created in the database
            document = Document.query.filter_by(filename='test.pdf').first()
            self.assertIsNotNone(document)
            self.assertEqual(document.file_type, 'application/pdf')
            self.assertEqual(document.summary, "This is a summary of the PDF.")
            self.assertEqual(document.project_id, self.project.id)
    
    @patch('app.document.read_text_file')
    @patch('app.document.check_mime_type')
    def test_upload_text(self, mock_check_mime, mock_read_text):
        """Test uploading a text file"""
        # Mock file type check and text reading
        mock_check_mime.return_value = (True, 'text/plain')
        mock_read_text.return_value = "This is sample text file content."
        
        # Create a mock text file
        text_data = BytesIO(b'This is a text file')
        text_data.name = 'test.txt'
        
        # Mock the generate_summary function
        with patch('app.document.generate_summary') as mock_generate_summary:
            mock_generate_summary.return_value = "This is a summary of the text file."
            
            # Upload the file
            response = self.client.post(
                '/documents/upload',
                data={'file': (text_data, 'test.txt'), 'project_id': self.project.id},
                content_type='multipart/form-data'
            )
            
            # Check response
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertEqual(data['status'], 'success')
            self.assertEqual(data['filename'], 'test.txt')
            
            # Verify the document was created in the database
            document = Document.query.filter_by(filename='test.txt').first()
            self.assertIsNotNone(document)
            self.assertEqual(document.file_type, 'text/plain')
            self.assertEqual(document.summary, "This is a summary of the text file.")
            self.assertEqual(document.project_id, self.project.id)
    
    def test_upload_unsupported_file(self):
        """Test uploading an unsupported file type"""
        # Create a mock unsupported file
        file_data = BytesIO(b'Unsupported file type')
        file_data.name = 'test.exe'
        
        # Try to upload the file
        response = self.client.post(
            '/documents/upload',
            data={'file': (file_data, 'test.exe'), 'project_id': self.project.id},
            content_type='multipart/form-data'
        )
        
        # Check response
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'error')
        self.assertEqual(data['message'], 'File type not allowed')
    
    def test_upload_invalid_project(self):
        """Test uploading a file with an invalid project ID"""
        # Create a mock text file
        text_data = BytesIO(b'This is a text file')
        text_data.name = 'test.txt'
        
        # Try to upload the file with an invalid project ID
        response = self.client.post(
            '/documents/upload',
            data={'file': (text_data, 'test.txt'), 'project_id': 9999},
            content_type='multipart/form-data'
        )
        
        # Check response
        self.assertEqual(response.status_code, 404)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'error')
        self.assertEqual(data['message'], 'Project not found')
    
    def test_get_document_details(self):
        """Test getting document details"""
        # Create a test document
        document = Document(
            filename='test_doc.pdf',
            file_path='/path/to/test_doc.pdf',
            file_type='application/pdf',
            project_id=self.project.id,
            summary='Test document summary'
        )
        db.session.add(document)
        db.session.commit()
        
        # Get document details
        response = self.client.get(f'/documents/{document.id}')
        
        # Check response
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['filename'], 'test_doc.pdf')
        self.assertEqual(data['file_type'], 'application/pdf')
        self.assertEqual(data['summary'], 'Test document summary')
    
    def test_get_project_documents(self):
        """Test getting all documents for a project"""
        # Create multiple test documents
        documents = [
            Document(
                filename='doc1.pdf',
                file_path='/path/to/doc1.pdf',
                file_type='application/pdf',
                project_id=self.project.id,
                summary='Summary for doc1'
            ),
            Document(
                filename='doc2.txt',
                file_path='/path/to/doc2.txt',
                file_type='text/plain',
                project_id=self.project.id,
                summary='Summary for doc2'
            )
        ]
        db.session.add_all(documents)
        db.session.commit()
        
        # Get project documents
        response = self.client.get(f'/documents/project/{self.project.id}')
        
        # Check response
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['project_id'], self.project.id)
        self.assertEqual(data['project_name'], 'Test Project')
        self.assertEqual(data['document_count'], 2)
        self.assertEqual(len(data['documents']), 2)
        
        # Verify document details
        doc_filenames = [doc['filename'] for doc in data['documents']]
        self.assertIn('doc1.pdf', doc_filenames)
        self.assertIn('doc2.txt', doc_filenames)

    def test_basic_summarization_fallback(self):
        """Test the basic summarization fallback"""
        from app.document import generate_summary
        
        # Sample text with multiple sentences
        text = "This is the first sentence. This is the second sentence. " + \
               "This is the third sentence. This is the fourth sentence. " + \
               "This is the fifth sentence. This is the sixth sentence."
        
        # Mock the LLM API configuration to be missing so we use the fallback
        with patch('flask.current_app.config.get', return_value=None):
            summary = generate_summary(text)
            
            # Verify the fallback method was used
            self.assertIn("This is the first sentence", summary)
            self.assertIn("(Note: This is a basic extract", summary)

if __name__ == '__main__':
    unittest.main()