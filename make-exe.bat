@echo off

:: Check if PyInstaller is installed, install if not
where pyinstaller >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo Installing PyInstaller...
    pip install pyinstaller
    if %ERRORLEVEL% neq 0 (
        echo Error: Failed to install PyInstaller.
        exit /b 1
    )
)

:: Check if spec file exists, create if not
if not exist stt_whisper_npu_win_systray.spec (
    echo Error: Build failed - stt_whisper_npu_win_systray.spec not present. executable not created.
    exit /b 1
)

if exist dist\stt_whisper_npu_win_systray.exe (
    del dist\stt_whisper_npu_win_systray.exe
)
pyinstaller.exe --clean stt_whisper_npu_win_systray.spec

if exist dist\stt_whisper_npu_win_systray.exe (
    echo Build successful! Executable created at dist\stt_whisper_npu_win_systray.exe
) else (
    echo Error: Build failed - executable not created.
    exit /b 1
)