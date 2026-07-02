@echo off
title Final Project Dev Setup Launcher
cd /d "%~dp0"

if /I "%~1"=="status" goto STATUS_DIRECT
if /I "%~1"=="install_codex" goto INSTALL_CODEX_DIRECT

:MENU
cls
echo ============================================================
echo        Final Project Dev Setup Launcher
echo ============================================================
echo.
echo SETUP ORDER
echo  1. Run menu 2
echo  2. Close this window and run again
echo  3. Run menu 3
echo  4. Close this window and run again
echo  5. Run menu 4
echo  6. Close this window and run again
echo  7. Run menu 5
echo  8. Close this window and run again
echo  9. Run menu 6
echo 10. Run menu 1 to check
echo.
echo ------------------------------------------------------------
echo [1] Check status in a separate stay-open window
echo [2] Install Git / VS Code / Windows Terminal
echo [3] Install Node.js LTS
echo [4] Install Python
echo [5] Install Claude Code
echo [6] Install Codex in a separate stay-open window
echo [X] Exit
echo ------------------------------------------------------------
echo.
set /p choice=Choose number: 

if "%choice%"=="1" goto CHECK
if "%choice%"=="2" goto INSTALL_TOOLS
if "%choice%"=="3" goto INSTALL_NODE
if "%choice%"=="4" goto INSTALL_PYTHON
if "%choice%"=="5" goto INSTALL_CLAUDE
if "%choice%"=="6" goto INSTALL_CODEX
if /I "%choice%"=="X" goto END

echo.
echo Invalid number.
pause
goto MENU

:CHECK
echo.
echo Opening status window...
start "Final Project Status Check" cmd /k ""%~f0" status"
echo.
echo A separate status window should stay open.
pause
goto MENU

:STATUS_DIRECT
cls
echo ============================================================
echo        Final Project Status Check
echo ============================================================
echo.
echo [FOUND] means this launcher found the tool.
echo [MISSING] means this launcher could not find it.
echo.

echo ------------------------------------------------------------
echo winget
echo ------------------------------------------------------------
where winget 2>nul
if errorlevel 1 (
    echo [MISSING] winget
) else (
    echo [FOUND] winget
    winget --version 2>nul
)
echo.

echo ------------------------------------------------------------
echo Git
echo ------------------------------------------------------------
where git 2>nul
if errorlevel 1 (
    if exist "%ProgramFiles%\Git\cmd\git.exe" (
        echo [FOUND] Git direct path
        "%ProgramFiles%\Git\cmd\git.exe" --version 2>nul
    ) else (
        echo [MISSING] Git
    )
) else (
    echo [FOUND] Git
    git --version 2>nul
)
echo.

echo ------------------------------------------------------------
echo Node.js
echo ------------------------------------------------------------
where node 2>nul
if errorlevel 1 (
    if exist "%ProgramFiles%\nodejs\node.exe" (
        echo [FOUND] Node.js direct path
        "%ProgramFiles%\nodejs\node.exe" -v 2>nul
    ) else (
        echo [MISSING] Node.js
    )
) else (
    echo [FOUND] Node.js
    node -v 2>nul
)
echo.

echo ------------------------------------------------------------
echo npm
echo ------------------------------------------------------------
where npm 2>nul
if errorlevel 1 (
    if exist "%ProgramFiles%\nodejs\npm.cmd" (
        echo [FOUND] npm direct path
        call "%ProgramFiles%\nodejs\npm.cmd" -v 2>nul
    ) else if exist "%AppData%\npm\npm.cmd" (
        echo [FOUND] npm appdata path
        call "%AppData%\npm\npm.cmd" -v 2>nul
    ) else (
        echo [MISSING] npm
    )
) else (
    echo [FOUND] npm
    call npm -v 2>nul
)
echo.

echo ------------------------------------------------------------
echo Python launcher py
echo ------------------------------------------------------------
where py 2>nul
if errorlevel 1 (
    echo [MISSING] py launcher
) else (
    echo [FOUND] py launcher
    py --version 2>nul
)
echo.

echo ------------------------------------------------------------
echo Python
echo ------------------------------------------------------------
where python 2>nul
if errorlevel 1 (
    echo [MISSING] python from PATH
    echo Searching common Python folders...
    dir /b "%LocalAppData%\Programs\Python" 2>nul
    dir /b "%ProgramFiles%\Python*" 2>nul
) else (
    echo [FOUND] Python
    python --version 2>nul
)
echo.

echo ------------------------------------------------------------
echo pip
echo ------------------------------------------------------------
where py 2>nul
if not errorlevel 1 (
    py -m pip --version 2>nul
) else (
    where python 2>nul
    if not errorlevel 1 (
        python -m pip --version 2>nul
    ) else (
        echo [MISSING] pip check skipped because Python was not found
    )
)
echo.

echo ------------------------------------------------------------
echo VS Code command
echo ------------------------------------------------------------
where code 2>nul
if errorlevel 1 (
    if exist "%LocalAppData%\Programs\Microsoft VS Code\bin\code.cmd" (
        echo [FOUND] VS Code direct path
        call "%LocalAppData%\Programs\Microsoft VS Code\bin\code.cmd" --version 2>nul
    ) else if exist "%ProgramFiles%\Microsoft VS Code\bin\code.cmd" (
        echo [FOUND] VS Code direct path
        call "%ProgramFiles%\Microsoft VS Code\bin\code.cmd" --version 2>nul
    ) else (
        echo [MISSING] VS Code command
    )
) else (
    echo [FOUND] VS Code command
    call code --version 2>nul
)
echo.

echo ------------------------------------------------------------
echo Claude Code
echo ------------------------------------------------------------
where claude 2>nul
if errorlevel 1 (
    echo [MISSING] Claude Code
) else (
    echo [FOUND] Claude Code
    call claude --version 2>nul
)
echo.

echo ------------------------------------------------------------
echo Codex CLI
echo ------------------------------------------------------------
where codex 2>nul
if errorlevel 1 (
    if exist "%AppData%\npm\codex.cmd" (
        echo [FOUND] Codex direct path
        call "%AppData%\npm\codex.cmd" --version 2>nul
    ) else (
        echo [MISSING] Codex CLI
    )
) else (
    echo [FOUND] Codex CLI
    call codex.cmd --version 2>nul
)
echo.

echo ============================================================
echo STATUS CHECK FINISHED.
echo This window should remain open.
echo ============================================================
echo.
pause
goto END

:INSTALL_TOOLS
cls
echo Installing Git, VS Code, Windows Terminal...
echo.
winget install --id Git.Git -e --accept-source-agreements --accept-package-agreements
winget install --id Microsoft.VisualStudioCode -e --accept-source-agreements --accept-package-agreements
winget install --id Microsoft.WindowsTerminal -e --accept-source-agreements --accept-package-agreements
echo.
echo Done. Close this window and run again.
pause
goto MENU

:INSTALL_NODE
cls
echo Installing Node.js LTS...
echo.
winget install --id OpenJS.NodeJS.LTS -e --accept-source-agreements --accept-package-agreements
echo.
echo Check:
where node
node -v
where npm
call npm -v
echo.
echo Done. Close this window and run again.
pause
goto MENU

:INSTALL_PYTHON
cls
echo Installing Python...
echo.
winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements
echo.
echo Check:
where py
py --version
where python
python --version
py -m pip --version
echo.
echo Done. Close this window and run again.
pause
goto MENU

:INSTALL_CLAUDE
cls
echo Installing Claude Code...
echo.
winget install Anthropic.ClaudeCode --accept-source-agreements --accept-package-agreements
echo.
echo Check:
where claude
call claude --version
echo.
echo Done. Close this window and run again.
pause
goto MENU

:INSTALL_CODEX
echo.
echo Opening Codex installer window...
start "Codex Installer" cmd /k ""%~f0" install_codex"
echo.
echo A separate Codex installer window should stay open.
pause
goto MENU

:INSTALL_CODEX_DIRECT
cls
echo ============================================================
echo        Codex Installer - STAY OPEN MODE
echo ============================================================
echo.
echo This window should stay open even if npm fails.
echo Codex requires Node.js and npm.
echo.
echo Checking node...
where node 2>nul
if errorlevel 1 (
    echo [MISSING] node
) else (
    echo [FOUND] node
    node -v
)
echo.
echo Checking npm...
where npm 2>nul
if errorlevel 1 (
    if exist "%ProgramFiles%\nodejs\npm.cmd" (
        echo [FOUND] npm direct path
        call "%ProgramFiles%\nodejs\npm.cmd" -v
        set "NPM_CMD=%ProgramFiles%\nodejs\npm.cmd"
    ) else if exist "%AppData%\npm\npm.cmd" (
        echo [FOUND] npm appdata path
        call "%AppData%\npm\npm.cmd" -v
        set "NPM_CMD=%AppData%\npm\npm.cmd"
    ) else (
        echo [MISSING] npm
        echo Run menu 3 first.
        pause
        goto END
    )
) else (
    echo [FOUND] npm
    call npm -v
    set "NPM_CMD=npm"
)
echo.
echo Installing Codex with npm...
echo Command: npm install -g @openai/codex
echo.
call %NPM_CMD% install -g @openai/codex
echo.
echo npm install finished.
echo.
echo Checking codex...
where codex 2>nul
if errorlevel 1 (
    if exist "%AppData%\npm\codex.cmd" (
        echo [FOUND] codex direct path
        call "%AppData%\npm\codex.cmd" --version
    ) else (
        echo [MISSING] codex
        echo.
        echo Try closing all terminals and opening this launcher again.
        echo If still missing, npm global path may not be in PATH:
        echo %AppData%\npm
    )
) else (
    echo [FOUND] codex
    call codex.cmd --version
)
echo.
echo ============================================================
echo CODEX INSTALLER FINISHED.
echo This window should remain open.
echo ============================================================
pause
goto END

:END
exit /b 0
