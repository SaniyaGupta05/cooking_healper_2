#!/usr/bin/env python3
"""
Basic validation script for CI/CD pipeline
"""

import os
import sys

def check_imports():
    """Check if all required packages can be imported"""
    packages = [
        ('flask', 'Flask'),
        ('flask_cors', 'CORS'),
        ('groq', 'Groq'),
        ('firebase_admin', 'credentials'),
        ('hashlib', 'sha256'),
        ('re', 'compile'),
        ('datetime', 'datetime'),
        ('json', 'loads'),
        ('random', 'randint'),
        ('os', 'getenv')
    ]
    
    all_imports_ok = True
    for module_name, attribute in packages:
        try:
            if module_name == 'flask_cors':
                __import__('flask_cors')
            else:
                __import__(module_name)
            print(f"✓ {module_name} imported successfully")
        except ImportError as e:
            print(f"✗ {module_name} import failed: {e}")
            all_imports_ok = False
            
    return all_imports_ok

def check_files():
    """Check if essential files exist"""
    essential_files = [
        'app/app.py',
        'requirements.txt', 
        'Dockerfile',
        '.github/workflows/ci-cd.yml'
    ]
    
    all_exist = True
    for file in essential_files:
        if os.path.exists(file):
            print(f"✓ {file} exists")
        else:
            print(f"✗ {file} missing")
            all_exist = False
            
    return all_exist

def check_environment():
    """Check environment variables"""
    if os.getenv('GROQ_API_KEY'):
        print("✓ GROQ_API_KEY is set in environment")
    else:
        print("⚠ GROQ_API_KEY not set (expected in CI environment)")

if __name__ == "__main__":
    print("Running CI/CD validation checks...")
    print("=" * 50)
    
    files_ok = check_files()
    imports_ok = check_imports() 
    check_environment()
    
    print("=" * 50)
    
    if files_ok:
        print("✓ All file checks passed!")
        if imports_ok:
            print("✓ All import checks passed!")
            print("✓ Validation completed successfully!")
            sys.exit(0)
        else:
            print("⚠ Some imports failed (check requirements.txt)")
            sys.exit(1)
    else:
        print("✗ Some file checks failed")
        sys.exit(1)
