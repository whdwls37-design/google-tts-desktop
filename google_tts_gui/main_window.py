import os
import sys
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QComboBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from google_tts_gui.tts_client import GoogleTTSClient


class GoogleTTSApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Google TTS Desktop")
        self.resize(900, 650)
        self.generated_audio_path: Optional[str] = None
        self.client: Optional[GoogleTTSClient] = None
        self.credentials_path: Optional[str] = None

        self._build_ui()
        self._populate_default_languages()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("Google Text-to-Speech Desktop GUI")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        layout.addWidget(title)

        credentials_row = QHBoxLayout()
        self.credentials_button = QPushButton("Select Service Account JSON")
        self.credentials_button.clicked.connect(self.select_credentials)
        self.credentials_label = QLabel("No service account file selected")
        self.credentials_label.setWordWrap(True)
        credentials_row.addWidget(self.credentials_button)
        credentials_row.addWidget(self.credentials_label, 1)
        layout.addLayout(credentials_row)

        language_row = QHBoxLayout()
        language_label = QLabel("Language:")
        self.language_combo = QComboBox()
        self.language_combo.currentTextChanged.connect(self.on_language_changed)
        language_row.addWidget(language_label)
        language_row.addWidget(self.language_combo, 1)
        layout.addLayout(language_row)

        voice_row = QHBoxLayout()
        voice_label = QLabel("Voice:")
        self.voice_combo = QComboBox()
        voice_row.addWidget(voice_label)
        voice_row.addWidget(self.voice_combo, 1)
        layout.addLayout(voice_row)

        output_row = QHBoxLayout()
        output_label = QLabel("Output file:")
        self.output_path_edit = QLabel()
        self.output_path_edit.setText("output/tts_output.mp3")
        self.output_path_edit.setWordWrap(True)
        self.output_path_edit.setStyleSheet("border: 1px solid #bbb; padding: 6px;")
        output_row.addWidget(output_label)
        output_row.addWidget(self.output_path_edit, 1)
        layout.addLayout(output_row)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlaceholderText("Type the text you want to convert to speech...")
        layout.addWidget(self.text_edit, 2)

        action_row = QHBoxLayout()
        self.generate_button = QPushButton("Generate Audio")
        self.generate_button.clicked.connect(self.generate_audio)

        self.play_button = QPushButton("Play Audio")
        self.play_button.clicked.connect(self.play_audio)

        self.save_button = QPushButton("Save As...")
        self.save_button.clicked.connect(self.choose_output_file)

        action_row.addWidget(self.generate_button)
        action_row.addWidget(self.play_button)
        action_row.addWidget(self.save_button)
        layout.addLayout(action_row)

        self.status_label = QLabel("Ready")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

    def _populate_default_languages(self):
        self.language_combo.clear()
        self.voice_combo.clear()
        self.language_combo.addItem("en-US")
        self.voice_combo.addItem("en-US-Wavenet-A")

    def select_credentials(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Service Account JSON",
            str(Path.home()),
            "JSON Files (*.json)",
        )
        if not file_path:
            return

        self.credentials_path = file_path
        self.credentials_label.setText(file_path)
        self.status_label.setText("Credentials selected. Loading voices...")

        try:
            self.client = GoogleTTSClient(credentials_path=file_path)
            languages = self.client.list_languages()
            self.language_combo.clear()
            for language in languages:
                self.language_combo.addItem(language)

            if languages:
                self.on_language_changed(languages[0])
                self.status_label.setText("Ready. Voices loaded.")
        except Exception as exc:  # pragma: no cover
            self.status_label.setText(f"Error loading credentials: {exc}")
            QMessageBox.critical(self, "Initialization Error", str(exc))

    def on_language_changed(self, language: str):
        if not self.client or not language:
            return

        try:
            voices = self.client.list_voices_for_language(language)
            self.voice_combo.clear()
            for voice in voices:
                self.voice_combo.addItem(voice, voice)
        except Exception as exc:  # pragma: no cover
            self.status_label.setText(f"Error loading voices: {exc}")

    def choose_output_file(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Choose output file",
            "output/tts_output.mp3",
            "MP3 Files (*.mp3)",
        )
        if file_path:
            self.generated_audio_path = file_path
            self.output_path_edit.setText(file_path)
            self.status_label.setText(f"Output path set to: {file_path}")

    def generate_audio(self):
        if not self.client:
            QMessageBox.warning(self, "Missing credentials", "Please select a Google Cloud service account JSON file first.")
            return

        text = self.text_edit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "No text", "Please enter some text before generating audio.")
            return

        language = self.language_combo.currentText()
        voice_name = self.voice_combo.currentText()
        output_path = self.output_path_edit.text().strip()

        try:
            self.status_label.setText("Generating audio...")
            self.generated_audio_path = self.client.synthesize(text, language, voice_name, output_path)
            self.status_label.setText(f"Audio saved to: {self.generated_audio_path}")
        except Exception as exc:
            self.status_label.setText(f"Generation failed: {exc}")
            QMessageBox.critical(self, "TTS Error", str(exc))

    def play_audio(self):
        if not self.generated_audio_path or not os.path.exists(self.generated_audio_path):
            QMessageBox.warning(self, "No file", "Generate audio first before playing it.")
            return

        try:
            if sys.platform.startswith("darwin"):
                import subprocess
                subprocess.run(["open", self.generated_audio_path], check=True)
            elif sys.platform.startswith("linux"):
                import subprocess
                subprocess.run(["xdg-open", self.generated_audio_path], check=True)
            elif sys.platform.startswith("win"):
                os.startfile(self.generated_audio_path)  # type: ignore[attr-defined]
            self.status_label.setText(f"Playing: {self.generated_audio_path}")
        except Exception as exc:
            QMessageBox.critical(self, "Playback Error", str(exc))


def main():
    app = QApplication([])
    window = GoogleTTSApp()
    window.show()
    app.exec()
