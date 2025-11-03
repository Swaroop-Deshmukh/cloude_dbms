@echo off
echo 🚀 Starting Flask Dashboard...

REM --- Start Flask in background so the script continues ---
start "" cmd /c "python app.py"

REM --- Wait a bit to let Flask start ---
timeout /t 3 >nul

REM --- Open the browser (use explorer for VS Code terminal compatibility) ---
explorer "http://127.0.0.1:5000/dashboard-react"
