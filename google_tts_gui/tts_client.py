import os
from typing import List, Optional

from google.cloud import texttospeech


class GoogleTTSClient:
    def __init__(self, credentials_path: Optional[str] = None):
        if credentials_path:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
        self.client = texttospeech.TextToSpeechClient()

    def list_languages(self) -> List[str]:
        voices = self.client.list_voices().voices
        languages = set()
        for voice in voices:
            for code in voice.language_codes:
                languages.add(code)
        return sorted(languages)

    def list_voices_for_language(self, language_code: str) -> List[str]:
        response = self.client.list_voices(language_code=language_code)
        names = []
        for voice in response.voices:
            if language_code in voice.language_codes:
                names.append(voice.name)
        return sorted(set(names))

    def synthesize(self, text: str, language_code: str, voice_name: str, output_path: str) -> str:
        voice = texttospeech.VoiceSelectionParams(
            language_code=language_code,
            name=voice_name,
            ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL,
        )

        input_text = texttospeech.SynthesisInput(text=text)
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=1.0,
        )

        response = self.client.synthesize_speech(
            request={
                "input": input_text,
                "voice": voice,
                "audio_config": audio_config,
            }
        )

        directory = os.path.dirname(output_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)

        with open(output_path, "wb") as audio_file:
            audio_file.write(response.audio_content)

        return output_path
