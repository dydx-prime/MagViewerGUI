@echo off

IF "%1"=="setup" GOTO setup
IF "%1"=="run" GOTO run
IF "%1"=="freeze" GOTO freeze
IF "%1"=="install" GOTO install
IF "%1"=="clean" GOTO clean
GOTO help

:setup
    echo [*] Creating virtual environment...
    py -m venv venv
    echo [*] Activating and installing requirements...
    call venv\Scripts\activate
    call pip install -r requirements.txt
    echo [*] Setup complete. Run: make.bat run
    GOTO end

:run
    echo [*] Activating venv and launching app...
    call venv\Scripts\activate && py sandbox.py
    GOTO end

:freeze
    echo [*] Freezing packages to requirements.txt...
    call venv\Scripts\activate && pip freeze > requirements.txt
    echo [*] requirements.txt updated.
    GOTO end

:install
    IF "%2"=="" (
        echo [!] Usage: make.bat install ^<package^>
        GOTO end
    )
    echo [*] Installing %2...
    call venv\Scripts\activate && pip install %2
    GOTO end

:clean
    echo [*] Removing virtual environment...
    rmdir /s /q venv
    echo [*] Cleaned.
    GOTO end

:help
    echo.
    echo Usage: make.bat [command]
    echo.
    echo   setup              Create venv and install requirements.txt
    echo   run                Activate venv and launch main.py
    echo   install ^<package^>  Install a new package into the venv
    echo   freeze             Freeze installed packages to requirements.txt
    echo   clean              Delete the venv folder
    echo.

:end