import unittest
import json
import logging
import os
import sys
import tempfile
from flask import Flask, Blueprint, jsonify

# Add parent directory to path so imports work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.utils import setup_logger, retry_with_backoff, handle_exception, log_with_context

# Test blueprint with error-triggering endpoints
test_bp = Blueprint('test', __name__)

@test_bp.route('/test-error/value')
def test_value_error():
    raise ValueError("This is a test value error")

@test_bp.route('/test-error/unhandled')
def test_unhandled_error():
    # Trigger a KeyError
    bad_dict = {}
    return bad_dict['nonexistent_key']

@test_bp.route('/test-error/handled')
@handle_exception
def test_handled_error():
    # This error will be caught by the handle_exception decorator
    raise RuntimeError("This is a handled runtime error")

# Test endpoint with retries
retry_count = 0
@test_bp.route('/test-retry')
@retry_with_backoff(max_retries=2, backoff_factor=0.1)
def test_retry():
    global retry_count
    retry_count += 1
    if retry_count < 3:
        raise ConnectionError("Simulated connection error")
    return jsonify({"status": "success", "retries": retry_count})

class TestErrorHandling(unittest.TestCase):
    def setUp(self):
        # Create a test Flask app
        self.app = Flask(__name__)
        self.app.config['TESTING'] = True
        self.app.register_blueprint(test_bp)
        
        # Create a test client
        self.client = self.app.test_client()
        
        # Use a temporary directory for logs
        self.temp_log_dir = tempfile.mkdtemp()
        os.environ['LOG_DIR'] = self.temp_log_dir
        
        # Development environment for detailed errors
        os.environ['FLASK_ENV'] = 'development'
    
    def tearDown(self):
        # Clean up the temporary directory
        import shutil
        shutil.rmtree(self.temp_log_dir)
    
    def test_logger_setup(self):
        """Test that loggers are properly configured"""
        # Test development logger
        dev_logger = setup_logger('test_dev')
        self.assertEqual(dev_logger.level, logging.DEBUG)
        
        # Test production logger by changing environment
        orig_env = os.environ.get('FLASK_ENV')
        os.environ['FLASK_ENV'] = 'production'
        prod_logger = setup_logger('test_prod')
        self.assertEqual(prod_logger.level, logging.WARNING)
        
        # Restore environment
        if orig_env:
            os.environ['FLASK_ENV'] = orig_env
        else:
            del os.environ['FLASK_ENV']
    
    def test_value_error_response(self):
        """Test that ValueError produces a 500 error with appropriate message"""
        response = self.client.get('/test-error/value')
        self.assertEqual(response.status_code, 500)
        
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'error')
        self.assertEqual(data['error']['type'], 'server_error')
        self.assertIn('value error', data['error']['message'].lower())
    
    def test_unhandled_error(self):
        """Test that unhandled errors are properly caught by the global handler"""
        response = self.client.get('/test-error/unhandled')
        self.assertEqual(response.status_code, 500)
        
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'error')
        self.assertIn('key', data['error']['message'].lower())
    
    def test_handled_error(self):
        """Test that the handle_exception decorator properly formats errors"""
        response = self.client.get('/test-error/handled')
        self.assertEqual(response.status_code, 500)
        
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'error')
        self.assertEqual(data['error']['type'], 'system_error')
        self.assertIn('runtime error', data['error']['message'].lower())
    
    def test_production_error_messages(self):
        """Test that production error messages are sanitized"""
        # Change environment to production
        orig_env = os.environ.get('FLASK_ENV')
        os.environ['FLASK_ENV'] = 'production'
        
        response = self.client.get('/test-error/value')
        data = json.loads(response.data)
        
        # Should NOT contain the actual error details in production
        self.assertNotIn('test value error', data['error']['message'].lower())
        
        # Restore environment
        if orig_env:
            os.environ['FLASK_ENV'] = orig_env
        else:
            del os.environ['FLASK_ENV']
    
    def test_retry_mechanism(self):
        """Test that the retry mechanism works properly"""
        global retry_count
        retry_count = 0
        
        response = self.client.get('/test-retry')
        data = json.loads(response.data)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['retries'], 3)  # Should succeed on 3rd attempt

if __name__ == '__main__':
    unittest.main()