@echo off
setlocal enabledelayedexpansion

:: Check if Python is installed
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo Error: Python is not installed or not in PATH.
    pause
    exit /b 1
)

:: Check if virtual environment already exists
if exist ".venv" (
    echo Virtual environment .venv already exists.
    echo Activating existing virtual environment...
    call .venv\Scripts\activate.bat
    echo Virtual environment activated.
    pause
    exit /b 0
)

:: Create virtual environment
python -m venv .venv
if %ERRORLEVEL% neq 0 (
    echo Error: Failed to create virtual environment.
    pause
    exit /b 1
)

echo Virtual environment .venv created successfully.

:: Activate virtual environment
call .venv\Scripts\activate.bat
if %ERRORLEVEL% neq 0 (
    echo Error: Failed to activate virtual environment.
    pause
    exit /b 1
)

echo Virtual environment activated.

:: Check if requirements.txt exists
if not exist "requirements.txt" (
    echo Error: requirements.txt not found.
    pause
    exit /b 1
)

:: Install requirements
pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo Error: Failed to install requirements.
    pause
    exit /b 1
)

echo All requirements installed successfully.
echo Setup complete. Virtual environment is ready to use.
pause