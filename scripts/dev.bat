@echo off
REM DV-Agent Development Scripts for Windows
REM Usage: scripts\dev.bat [command]

setlocal enabledelayedexpansion

if "%1"=="" goto help
if "%1"=="help" goto help
if "%1"=="install" goto install
if "%1"=="setup" goto setup
if "%1"=="up" goto dev-up
if "%1"=="up-full" goto dev-up-full
if "%1"=="down" goto dev-down
if "%1"=="logs" goto dev-logs
if "%1"=="run" goto run
if "%1"=="chat" goto chat
if "%1"=="test" goto test
if "%1"=="clean" goto clean

echo Unknown command: %1
goto help

:help
echo.
echo DV-Agent Development Scripts
echo ============================
echo.
echo Usage: scripts\dev.bat [command]
echo.
echo Commands:
echo   install   - Install Python dependencies
echo   setup     - Full development setup
echo   up        - Start Redis (development infrastructure)
echo   up-full   - Start Redis + Ollama + Redis Commander
echo   down      - Stop all development services
echo   logs      - View service logs
echo   run       - Run the application
echo   chat      - Start interactive chat
echo   test      - Run tests
echo   clean     - Clean up Docker resources
echo.
goto end

:install
echo Installing dependencies...
pip install -r requirements.txt
pip install -e .
echo Done!
goto end

:setup
call :install
echo.
echo Copying environment template...
if not exist .env (
    copy .env.example .env
    echo Created .env file. Please edit it with your API keys.
) else (
    echo .env already exists.
)
echo.
echo Development setup complete!
goto end

:dev-up
echo Starting development infrastructure...
docker compose -f docker-compose.dev.yml up -d
echo.
echo Redis is running on localhost:6379
echo.
echo Now run: scripts\dev.bat run
goto end

:dev-up-full
echo Starting full development stack...
docker compose -f docker-compose.dev.yml --profile debug --profile ollama up -d
echo.
echo Services:
echo   Redis: localhost:6379
echo   Redis Commander: http://localhost:8081
echo   Ollama: http://localhost:11434
echo.
echo To pull Ollama model: docker exec -it dv-agent-ollama ollama pull llama3.2
goto end

:dev-down
echo Stopping development services...
docker compose -f docker-compose.dev.yml --profile debug --profile ollama down
echo Done!
goto end

:dev-logs
docker compose -f docker-compose.dev.yml logs -f
goto end

:run
echo Starting DV-Agent...
python -m dv_agent.cli serve
goto end

:chat
echo Starting interactive chat...
python -m dv_agent.cli chat
goto end

:test
echo Running tests...
pytest tests/ -v
goto end

:clean
echo Cleaning up Docker resources...
docker compose -f docker-compose.dev.yml down -v --remove-orphans
docker compose down -v --remove-orphans
echo Done!
goto end

:end
endlocal
