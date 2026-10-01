# Google TTS Desktop GUI

This project creates a desktop app for Google Cloud Text-to-Speech using PyQt6.

Features:
- Select a Google Cloud service account JSON file
- Choose a language and voice
- Enter text to synthesize
- Save generated audio to MP3
- Play the generated file from the app

Requirements:
1. A Google Cloud project with the Text-to-Speech API enabled
2. A service account JSON key with access to the API
3. Python 3.10+

Setup:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

How to create credentials:
1. Open the Google Cloud Console
2. Create or select a project
3. Enable the Text-to-Speech API
4. Create a service account
5. Download the JSON key
6. Select that file in the app

Note:
Google Cloud TTS is a paid service. This app does not provide free speech conversion.
