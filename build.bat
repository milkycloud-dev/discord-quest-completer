@echo off
if not exist "venv\Scripts\pyinstaller.exe" (
    echo PyInstaller not found. Please ensure it is installed in venv.
    exit /b
)
echo Building Discord Quest Completer...
venv\Scripts\pyinstaller.exe --noconsole --onefile --icon=icon.ico --name="DiscordQuestCompleter" --add-data="icon.png;." --add-data="icon.ico;." src\app.py

if not exist release mkdir release
move dist\DiscordQuestCompleter.exe release\DiscordQuestCompleter.exe
rmdir /s /q build dist
del DiscordQuestCompleter.spec
echo Build complete. Executable is in the release folder.
pause
