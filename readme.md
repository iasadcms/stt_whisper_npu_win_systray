# Speech-To-Text Whisper NPU Windows System Tray

This project is a Windows system tray application that transcribes microphone input and inserts the resulting text into the currently active window at the cursor position.

It leverages FlowLightLM (https://fastflowlm.com/) to expose the Whisper model running on the NPU.


## Installation Guide

- Install Python 3.13+

- Download and install fastflowlm. Ensure it's available at the command line by typing `flm --version`

```cmd
C:\Users\username>flm --version
FLM v0.9.24
```

- Clone the repository.

- Create a custom python environment and install requirements:

```cmd
python -m venv .venv
.venv/scripts/activate.bat
pip install -r requirements.txt
```



## Running

Start the python script. Use --help for options.

```
Usage:
    python script.py                               # Run with default config
    python script.py --config my_config.json       # Use custom config
    python script.py --list-devices                # List audio devices
```

When launched, the application will live in the Windows system tray.

To start and stop transcription, use the following hotkeys:
- CTRL+SHIFT+F1 - Resume/Pause recording.
- CTRL+SHIFT+F2 - Stop recordings and clear queued audio.


On the first run, the config file `transcription_config.json` will be created with defaults.


### Starting the FLM server

```cmd
flm serve -a 1
```

You'll see output similar to like:

```
Downloading model...
Loading model into memory...
API server started on http://127.0.0.1:52625
```


## Compiling to Executable



```cmd
pyinstaller --onefile --windowed stt_whisper_npu_win_systray.py
```