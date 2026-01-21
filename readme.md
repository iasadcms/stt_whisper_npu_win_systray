# Speech-to_text using Whistper and AMD NPU.

A lightweight Windows System Tray utility that provides real-time speech-to-text transcription directly into your active window.
Originally developed as a personal productivity tool to explore the capabilities of Whisper running on an NPU, it will also work with other Whisper servers.

## Prerequisites - Whisper endpoint using FastFlowLM

Skip this step if you're using a different Whisper endpoint.

To utilize the AMD NPU, you must first set up FastFlowLM as your local Whisper server.

1. Download & Install: Get the latest version from https://fastflowlm.com/.

2. Verify Installation: Open your terminal and run:

```DOS
flm --version
```

3. Start the Server: Launch the API server (Port 52625) by running:

```DOS
flm serve -a 1
```

*Note: On the first run, it will automatically download the necessary Whisper models.*
```
Downloading model...
Loading model into memory...
API server started on http://127.0.0.1:52625
```

## Run from Source

Ensure you have Python 3.13+ installed, then:

1. Clone the repository:

```cmd
git clone https://github.com/iasadcms/stt_whisper_npu_win_systray.git
cd stt_whisper_npu_win_systray
```

2. Set up a virtual environment:

```cmd
python -m venv .venv
.venv/scripts/activate.bat
pip install -r requirements.txt
```

3. Launch the script

```
python main.py
```

### Building an Executable

If you prefer a standalone .exe:

1. Install PyInstaller: `pip install pyinstaller`

2. Run the build script: `.\make-exe.bat`

3. Find the executable in the `\dist` folder, named `stt_whisper_npu_win_systray.exe`.



## Usage

Once launched, the application will live in your Windows system tray. It creates a `transcription_config.json` file on its first run, which you can edit to customise settings.

**Default Hotkeys**
|Hotkey|Action|
|--|--|
|CTRL+SHIFT+F1|Toggle Recording (Resume / Pause)|
|CTRL+SHIFT+F2|Stop recording and clear the current audio queue|
|CTRL+SHIFT+F3|Force analysis of the current buffer (without stopping)|

**CLI Options**

```
python main.py --config custom.json  # Use a specific config file
python main.py --list-devices        # List available audio input devices
```


## Customization & Output
You can configure how your transcriptions are delivered via the config file:
- Direct Injection: Text is typed directly into your active cursor.
- Notepad Mode: Text is sent to a specific .txt file.
- Logging: The app maintains a transcription_log for all conversations (can be disabled).


## Alternative Whisper Servers
While optimized for FastFlowLM, this utility is compatible with any OpenAI-compatible Whisper endpoint, including:

- Faster-Whisper-Server - https://github.com/fedirz/faster-whisper-server
- LocalAI - https://localai.io/
- Whisper.cpp HTTP server - https://github.com/ggerganov/whisper.cpp

The default configuration expects the server at `http://127.0.0.1:52625/v1`


## License and Credits

Built with:
AI assistance from "every model under the sun."

**MIT License**

Copyright 2026 iasadcms

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), to deal in the Software without restriction, including without limitation |the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL |THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER |DEALINGS IN THE SOFTWARE.


.
