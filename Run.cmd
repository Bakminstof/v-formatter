echo off

set "CURRENT_DIR=%~dp0"

set "PYTHON=%CURRENT_DIR%interpreters\win\python-3.14.5-embed-amd64\pythonw.exe"
set "ENTRYPOINT=%CURRENT_DIR%src\main.py"

start "" "%PYTHON%" "%ENTRYPOINT%"
