echo off

set "CURRENT_DIR=%~dp0"

set "PYTHON=%CURRENT_DIR%interpreters\windows\python-3.8.10-embed-amd64\pythonw.exe"
set "ENTRYPOINT=%CURRENT_DIR%src\main.py"

start "" "%PYTHON%" "%ENTRYPOINT%"
