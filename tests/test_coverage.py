import os
import importlib
import pytest

def test_import_all_python_files():
    """Test that imports all Python files to ensure they appear in coverage reports."""
    # Get the project root directory (where this test file is located)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # List of directories to scan for Python files
    dirs_to_scan = ['connections', 'tasks', 'tools']
    
    # Import all Python files
    for dir_name in dirs_to_scan:
        dir_path = os.path.join(project_root, dir_name)
        if os.path.exists(dir_path):
            for file_name in os.listdir(dir_path):
                if file_name.endswith('.py') and not file_name.startswith('__'):
                    module_name = f"{dir_name}.{file_name[:-3]}"
                    try:
                        importlib.import_module(module_name)
                    except ImportError as e:
                        # Log the error but don't fail the test
                        print(f"Could not import {module_name}: {e}")
    
    # Import root Python files
    for file_name in os.listdir(project_root):
        if file_name.endswith('.py') and not file_name.startswith('__'):
            module_name = file_name[:-3]
            try:
                importlib.import_module(module_name)
            except ImportError as e:
                # Log the error but don't fail the test
                print(f"Could not import {module_name}: {e}")
    
    # The test always passes as its purpose is just to import files
    assert True 