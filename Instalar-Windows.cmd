@echo off
setlocal
cd /d "%~dp0"
py -3 -c "import sys; sys.exit(sys.version_info < (3,12))" >nul 2>&1
if not errorlevel 1 (
    py -3 "%~dp0installer\install.py" %*
    goto done
)
python -c "import sys; sys.exit(sys.version_info < (3,12))" >nul 2>&1
if not errorlevel 1 (
    python "%~dp0installer\install.py" %*
    goto done
)
echo Instale Python 3.12 ou superior e marque Add Python to PATH.
echo Depois abra este arquivo novamente.
start "" "https://www.python.org/downloads/windows/"
:done
pause
