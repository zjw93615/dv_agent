@echo off
REM DV-Agent Production Deployment Scripts for Windows
REM Usage: scripts\deploy.bat [command]

setlocal enabledelayedexpansion

if "%1"=="" goto help
if "%1"=="help" goto help
if "%1"=="build" goto build
if "%1"=="up" goto prod-up
if "%1"=="up-full" goto prod-up-full
if "%1"=="down" goto prod-down
if "%1"=="logs" goto prod-logs
if "%1"=="restart" goto restart
if "%1"=="status" goto status
if "%1"=="clean" goto clean

echo Unknown command: %1
goto help

:help
echo.
echo DV-Agent Production Deployment Scripts
echo ======================================
echo.
echo Usage: scripts\deploy.bat [command]
echo.
echo Commands:
echo   build     - Build Docker image
echo   up        - Start production stack (App + Redis)
echo   up-full   - Start with monitoring (Prometheus + Grafana)
echo   down      - Stop production stack
echo   logs      - View logs
echo   restart   - Restart the application
echo   status    - Show running containers
echo   clean     - Clean up Docker resources
echo.
goto end

:build
echo Building Docker image...
docker build -t dv-agent:latest .
echo Done!
goto end

:prod-up
echo Checking production environment...
if not exist .env.production (
    echo Creating .env.production from template...
    copy .env.production.example .env.production
    echo.
    echo WARNING: Please edit .env.production with your production settings!
    echo         Then run this command again.
    goto end
)
echo Starting production stack...
docker compose up -d --build
echo.
echo DV-Agent is running on http://localhost:8080
echo.
echo To view logs: scripts\deploy.bat logs
goto end

:prod-up-full
echo Starting full production stack with monitoring...
if not exist .env.production (
    copy .env.production.example .env.production
)
docker compose --profile monitoring up -d --build
echo.
echo Services:
echo   DV-Agent: http://localhost:8080
echo   Grafana: http://localhost:3000 (admin/admin)
echo   Prometheus: http://localhost:9090
goto end

:prod-down
echo Stopping production stack...
docker compose --profile monitoring --profile nginx --profile ollama down
echo Done!
goto end

:prod-logs
docker compose logs -f
goto end

:restart
echo Restarting DV-Agent...
docker compose restart dv-agent
echo Done!
goto end

:status
echo.
echo Running containers:
echo -------------------
docker compose ps
echo.
echo Resource usage:
echo ---------------
docker stats --no-stream
goto end

:clean
echo Cleaning up...
docker compose down -v --remove-orphans
docker image prune -f
echo Done!
goto end

:end
endlocal
