"""
Main entry point for DV-Agent.

This module provides the main entry points for running the application.
"""

import asyncio
import sys
from typing import Optional

from .app import Application, create_application
from .config.settings import get_settings, Settings
from .config.logging import setup_logging, get_logger


def run_server(
    host: Optional[str] = None,
    port: Optional[int] = None,
    debug: bool = False
) -> None:
    """
    Run the A2A server.
    
    Args:
        host: Server host (default from config)
        port: Server port (default from config)
        debug: Enable debug mode
    """
    settings = get_settings()
    
    if host:
        settings.a2a.host = host
    if port:
        settings.a2a.port = port
    if debug:
        settings.debug = True
        settings.logging.level = "DEBUG"
    
    setup_logging(level=settings.logging.level)
    logger = get_logger(__name__)
    
    logger.info(f"Starting DV-Agent server on {settings.a2a.host}:{settings.a2a.port}")
    
    async def main():
        app = Application(settings)
        await app.run()
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)


async def process_single(
    message: str,
    session_id: Optional[str] = None,
    settings: Optional[Settings] = None
) -> dict:
    """
    Process a single message.
    
    Args:
        message: User message
        session_id: Optional session ID for context
        settings: Optional settings override
        
    Returns:
        Response dictionary
    """
    settings = settings or get_settings()
    
    async with create_application(settings) as app:
        return await app.process_message(
            message=message,
            session_id=session_id
        )


def main() -> None:
    """Main entry point - runs CLI."""
    from .cli import main as cli_main
    cli_main()


if __name__ == "__main__":
    main()
