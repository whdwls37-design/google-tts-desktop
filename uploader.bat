@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
echo YouTube uploader ready. Example: python -m youtube_uploader upload jobs/test1 --dry-run
cmd /k
