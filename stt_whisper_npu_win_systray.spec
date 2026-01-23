# PyInstaller spec file for Speech-to-Text Whisper NPU application
# Generated for stt_whisper_npu_win_systray

# Suppress SyntaxWarning from pyautogui library
import warnings
warnings.filterwarnings("ignore", category=SyntaxWarning)

block_cipher = None


# Manual dependencies list - starting with requirements.txt contents
MANUAL_DEPENDENCIES = [
    'pynput',
    'pystray', 
    'pyautogui',
    'sounddevice',
    'numpy',
    'openai',
    'requests',
    'pygame',
    'pywin32',
    # Add any additional manual dependencies here
    # Example: 'some_optional_package',
]


# Import scanning function to discover all imports from Python files
def scan_imports():
    """
    Scan all Python files in the project directory to discover imports.
    Returns a list of unique module names that are actually importable.
    """
    import os
    import ast
    import importlib
    
    discovered_imports = set()
    
    # Walk through all Python files in the current directory
    for root, dirs, files in os.walk('.'):
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        
                    # Parse the file to find imports
                    try:
                        tree = ast.parse(content)
                        for node in ast.walk(tree):
                            # Handle import statements
                            if isinstance(node, ast.Import):
                                for alias in node.names:
                                    module_name = alias.name.split('.')[0]  # Get top-level module
                                    # Only add if it's not a standard library module and can be imported
                                    if not module_name.startswith('_') and '.' not in module_name:
                                        discovered_imports.add(module_name)
                            # Handle from imports
                            elif isinstance(node, ast.ImportFrom):
                                if node.module:  # Skip relative imports without module
                                    module_name = node.module.split('.')[0]
                                    # Only add if it's not a standard library module and can be imported
                                    if not module_name.startswith('_') and '.' not in module_name:
                                        discovered_imports.add(module_name)
                    except SyntaxError:
                        # Skip files with syntax errors
                        continue
                except (IOError, UnicodeDecodeError):
                    # Skip files that can't be read
                    continue
    
    # Filter to only include modules that are actually importable
    importable_imports = set()
    for import_name in discovered_imports:
        try:
            # Try to import the module to see if it exists
            importlib.import_module(import_name)
            importable_imports.add(import_name)
        except (ImportError, ModuleNotFoundError):
            # Module doesn't exist, skip it
            continue
    
    return sorted(list(importable_imports))

# Get automatically discovered imports
auto_discovered_imports = scan_imports()

# Combine manual and auto-discovered imports
# Filter out standard library modules and keep only third-party ones
import sys
STANDARD_LIBRARY = set(sys.stdlib_module_names)

# Filter to get only third-party modules
third_party_imports = []
for import_name in auto_discovered_imports:
    if import_name not in STANDARD_LIBRARY and not import_name.startswith('_'):
        third_party_imports.append(import_name)

# Combine manual dependencies with discovered third-party imports
all_hidden_imports = MANUAL_DEPENDENCIES + third_party_imports

# Remove duplicates while preserving order
seen = set()
unique_hidden_imports = []
for import_name in all_hidden_imports:
    if import_name not in seen:
        seen.add(import_name)
        unique_hidden_imports.append(import_name)

print(f"Discovered {len(auto_discovered_imports)} imports from Python files")
print(f"Third-party imports: {len(third_party_imports)}")
print(f"Manual dependencies: {len(MANUAL_DEPENDENCIES)}")
print(f"Total unique hidden imports: {len(unique_hidden_imports)}")
print(f"Hidden imports: {unique_hidden_imports}")

# Main application details
a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[],
    hiddenimports=unique_hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
    optimize=2,
)

# Windows executable configuration
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

ex = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='stt_whisper_npu_win_systray',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Windows GUI application (no console)
    icon='images/mic.ico',
)

# Create the final executable
coll = COLLECT(
    ex,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='stt_whisper_npu_win_systray',
)
