#!/usr/bin/env python3
"""
Strategy Evolution Test Runner

Runs tests for the Strategy Evolution Layer components.
"""

import subprocess
import sys
import os

def run_tests():
    """Run strategy evolution tests"""
    print("Running Strategy Evolution Layer tests...")
    
    # Change to src directory
    src_dir = os.path.join(os.path.dirname(__file__), 'src')
    os.chdir(src_dir)
    
    # Add src to Python path
    sys.path.insert(0, src_dir)
    
    try:
        # Run pytest on strategy tests
        result = subprocess.run([
            sys.executable, '-m', 'pytest', 
            'tests/strategy/', 
            '-v',
            '--tb=short',
            '--color=yes'
        ], capture_output=True, text=True)
        
        print("STDOUT:")
        print(result.stdout)
        
        if result.stderr:
            print("STDERR:")
            print(result.stderr)
        
        return result.returncode == 0
        
    except Exception as e:
        print(f"Failed to run tests: {e}")
        return False

if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)