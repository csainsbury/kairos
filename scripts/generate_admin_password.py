#!/usr/bin/env python3
"""
Generate admin password hash for kAIros
This script creates a strong password hash for the admin user
"""

import os
import hashlib
import base64
import argparse
import getpass
import secrets
import string

def generate_password(length=16):
    """Generate a secure random password
    
    Args:
        length: Length of the password
        
    Returns:
        Secure random password
    """
    alphabet = string.ascii_letters + string.digits + string.punctuation
    while True:
        password = ''.join(secrets.choice(alphabet) for _ in range(length))
        # Ensure password has at least one of each character type
        if (any(c.islower() for c in password) and
            any(c.isupper() for c in password) and
            any(c.isdigit() for c in password) and
            any(c in string.punctuation for c in password)):
            return password

def hash_password(password):
    """Hash a password using PBKDF2 with SHA-256
    
    Args:
        password: Plain text password
        
    Returns:
        Tuple of (salt_hex, hashed_password_hex)
    """
    salt = os.urandom(32)  # 32 bytes salt
    
    # Use 100,000 iterations of PBKDF2
    key = hashlib.pbkdf2_hmac(
        'sha256',  # Hash algorithm
        password.encode('utf-8'),  # Password as bytes
        salt,  # Salt
        100000,  # Iterations
        dklen=64  # Get a 64 byte key
    )
    
    # Convert to hex for storage
    salt_hex = salt.hex()
    key_hex = key.hex()
    
    return salt_hex, key_hex

def main():
    parser = argparse.ArgumentParser(description='Generate admin password hash for kAIros')
    parser.add_argument('--generate', action='store_true', help='Generate a secure password')
    parser.add_argument('--length', type=int, default=16, help='Length of generated password')
    parser.add_argument('--quiet', action='store_true', help='Quiet mode - no prompts')
    parser.add_argument('--username', type=str, help='Admin username (default is "admin")')
    
    args = parser.parse_args()
    
    # Set username
    username = args.username or 'admin'
    
    # Generate or prompt for password
    if args.generate:
        password = generate_password(args.length)
        print(f"Generated secure password: {password}")
    else:
        if args.quiet:
            # Use environment variable or default in quiet mode
            password = os.environ.get('ADMIN_PASSWORD', 'admin')
        else:
            # Prompt for password interactively
            password = getpass.getpass('Enter password: ')
            confirm = getpass.getpass('Confirm password: ')
            
            if password != confirm:
                print("Passwords do not match!")
                return 1
                
            if len(password) < 8:
                print("Warning: Password is less than 8 characters!")
    
    # Hash the password
    salt_hex, key_hex = hash_password(password)
    
    # Print configuration values
    print("\nAdd these values to your .env.production file:")
    print("=" * 50)
    print(f"ADMIN_USERNAME={username}")
    print(f"ADMIN_PASSWORD_SALT={salt_hex}")
    print(f"ADMIN_PASSWORD_HASH={key_hex}")
    print("=" * 50)
    
    return 0

if __name__ == '__main__':
    exit(main())