@echo off
if exist dist\stt_whisper_npu_win_systray.exe (
    del dist\stt_whisper_npu_win_systray.exe
)
pyinstaller.exe --clean stt_whisper_npu_win_systray.spec