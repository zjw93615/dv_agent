"""
Command Line Interface for DV-Agent.

Provides commands for running the agent server and interactive chat.
"""

import asyncio
import sys
import click
from typing import Optional
from pathlib import Path

from .config.settings import get_settings, Settings
from .config.logging import get_logger
from .app import Application, create_application


logger = get_logger(__name__)


@click.group()
@click.version_option(version="0.1.0", prog_name="dv-agent")
@click.option(
    "--debug/--no-debug",
    default=False,
    help="Enable debug mode"
)
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True),
    help="Path to configuration file"
)
@click.pass_context
def cli(ctx: click.Context, debug: bool, config: Optional[str]) -> None:
    """DV-Agent: Multi-Agent AI Framework with ReAct reasoning."""
    ctx.ensure_object(dict)
    
    # Load settings
    settings = get_settings()
    if debug:
        settings.debug = True
        settings.logging.level = "DEBUG"
    
    ctx.obj["settings"] = settings
    ctx.obj["debug"] = debug


@cli.command()
@click.option(
    "--host",
    "-h",
    default=None,
    help="Server host (default: from config)"
)
@click.option(
    "--port",
    "-p",
    type=int,
    default=None,
    help="Server port (default: from config)"
)
@click.option(
    "--workers",
    "-w",
    type=int,
    default=None,
    help="Number of workers"
)
@click.pass_context
def serve(
    ctx: click.Context,
    host: Optional[str],
    port: Optional[int],
    workers: Optional[int]
) -> None:
    """Start the A2A server."""
    settings: Settings = ctx.obj["settings"]
    
    # Override settings from CLI
    if host:
        settings.a2a.host = host
    if port:
        settings.a2a.port = port
    if workers:
        settings.a2a.workers = workers
    
    click.echo(f"Starting DV-Agent server on {settings.a2a.host}:{settings.a2a.port}")
    
    async def run_server():
        app = Application(settings)
        await app.run()
    
    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        click.echo("\nServer stopped.")


@cli.command()
@click.option(
    "--session",
    "-s",
    default=None,
    help="Session ID to resume"
)
@click.pass_context
def chat(ctx: click.Context, session: Optional[str]) -> None:
    """Start an interactive chat session."""
    settings: Settings = ctx.obj["settings"]
    
    click.echo("=" * 60)
    click.echo("  DV-Agent Interactive Chat")
    click.echo("  Type 'exit' or 'quit' to end the session")
    click.echo("  Type 'clear' to start a new conversation")
    click.echo("  Type 'status' to show session info")
    click.echo("=" * 60)
    click.echo()
    
    async def run_chat():
        async with create_application(settings) as app:
            current_session = session
            
            while True:
                try:
                    # Get user input
                    user_input = click.prompt(
                        click.style("You", fg="green", bold=True),
                        prompt_suffix=": "
                    )
                    
                    # Handle special commands
                    if user_input.lower() in ("exit", "quit"):
                        click.echo("Goodbye!")
                        break
                    
                    if user_input.lower() == "clear":
                        current_session = None
                        click.echo("Session cleared. Starting fresh conversation.")
                        continue
                    
                    if user_input.lower() == "status":
                        if current_session:
                            click.echo(f"Session ID: {current_session}")
                        else:
                            click.echo("No active session")
                        continue
                    
                    if not user_input.strip():
                        continue
                    
                    # Process message
                    click.echo()
                    with click.progressbar(
                        length=100,
                        label="Thinking",
                        show_eta=False,
                        show_percent=False
                    ) as bar:
                        # Start progress animation
                        import threading
                        stop_progress = threading.Event()
                        
                        def animate_progress():
                            i = 0
                            while not stop_progress.is_set():
                                bar.update(1)
                                if bar.pos >= 99:
                                    bar.pos = 0
                                stop_progress.wait(0.1)
                                i += 1
                        
                        progress_thread = threading.Thread(target=animate_progress)
                        progress_thread.start()
                        
                        try:
                            result = await app.process_message(
                                message=user_input,
                                session_id=current_session
                            )
                        finally:
                            stop_progress.set()
                            progress_thread.join()
                            bar.update(100 - bar.pos)
                    
                    # Update session
                    current_session = result.get("session_id")
                    
                    # Display response
                    click.echo()
                    response = result.get("response", "No response")
                    click.echo(click.style("Agent", fg="blue", bold=True) + f": {response}")
                    click.echo()
                    
                except click.exceptions.Abort:
                    click.echo("\nGoodbye!")
                    break
                except Exception as e:
                    click.echo(click.style(f"Error: {e}", fg="red"))
                    if ctx.obj.get("debug"):
                        import traceback
                        traceback.print_exc()
    
    try:
        asyncio.run(run_chat())
    except KeyboardInterrupt:
        click.echo("\nChat session ended.")


@cli.command()
@click.argument("message")
@click.option(
    "--session",
    "-s",
    default=None,
    help="Session ID"
)
@click.option(
    "--json",
    "-j",
    "output_json",
    is_flag=True,
    help="Output as JSON"
)
@click.pass_context
def ask(
    ctx: click.Context,
    message: str,
    session: Optional[str],
    output_json: bool
) -> None:
    """Send a single message and get a response."""
    settings: Settings = ctx.obj["settings"]
    
    async def run_ask():
        async with create_application(settings) as app:
            result = await app.process_message(
                message=message,
                session_id=session
            )
            
            if output_json:
                import json
                click.echo(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                click.echo(result.get("response", "No response"))
    
    try:
        asyncio.run(run_ask())
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        if ctx.obj.get("debug"):
            import traceback
            traceback.print_exc()
        sys.exit(1)


@cli.command()
@click.pass_context
def config(ctx: click.Context) -> None:
    """Show current configuration."""
    settings: Settings = ctx.obj["settings"]
    
    import json
    config_dict = settings.to_dict()
    click.echo(json.dumps(config_dict, indent=2, ensure_ascii=False))


@cli.command()
@click.pass_context
def health(ctx: click.Context) -> None:
    """Check system health."""
    settings: Settings = ctx.obj["settings"]
    
    async def check_health():
        click.echo("Checking system health...\n")
        
        results = []
        
        # Check Redis
        try:
            from .session.redis_client import RedisClient
            redis = RedisClient(
                host=settings.redis.host,
                port=settings.redis.port
            )
            await redis.connect()
            await redis.close()
            results.append(("Redis", "OK", "green"))
        except Exception as e:
            results.append(("Redis", f"Failed: {e}", "red"))
        
        # Check LLM providers
        for provider in ["openai", "deepseek", "ollama"]:
            try:
                if provider == "openai" and not settings.llm.openai_api_key:
                    results.append(("OpenAI", "No API key", "yellow"))
                elif provider == "deepseek" and not settings.llm.deepseek_api_key:
                    results.append(("DeepSeek", "No API key", "yellow"))
                else:
                    results.append((provider.capitalize(), "Configured", "green"))
            except Exception as e:
                results.append((provider.capitalize(), f"Error: {e}", "red"))
        
        # Display results
        click.echo("Component Health Status:")
        click.echo("-" * 40)
        for name, status, color in results:
            status_text = click.style(status, fg=color)
            click.echo(f"  {name:15} {status_text}")
        click.echo("-" * 40)
    
    asyncio.run(check_health())


@cli.group()
def tools() -> None:
    """Manage tools and skills."""
    pass


@tools.command("list")
@click.pass_context
def list_tools(ctx: click.Context) -> None:
    """List available tools."""
    settings: Settings = ctx.obj["settings"]
    
    async def show_tools():
        from .tools.registry import ToolRegistry
        from .tools.builtin_skills import CalculatorTool, DateTimeTool
        
        registry = ToolRegistry()
        
        if settings.tool.enable_calculator:
            registry.register(CalculatorTool())
        if settings.tool.enable_datetime:
            registry.register(DateTimeTool())
        
        click.echo("\nAvailable Tools:")
        click.echo("-" * 60)
        
        for tool in registry.list_tools():
            click.echo(f"\n  {click.style(tool.name, bold=True)}")
            click.echo(f"    {tool.description}")
            click.echo(f"    Category: {tool.category}")
        
        click.echo()
    
    asyncio.run(show_tools())


@cli.group()
def session() -> None:
    """Manage sessions."""
    pass


@session.command("info")
@click.argument("session_id")
@click.pass_context
def session_info(ctx: click.Context, session_id: str) -> None:
    """Show session information."""
    settings: Settings = ctx.obj["settings"]
    
    async def show_info():
        from .session.redis_client import RedisClient
        from .session.manager import SessionManager
        
        redis = RedisClient(
            host=settings.redis.host,
            port=settings.redis.port
        )
        await redis.connect()
        
        try:
            manager = SessionManager(redis)
            session = await manager.get_session(session_id)
            
            if session:
                import json
                click.echo(json.dumps(session.model_dump(), indent=2, default=str))
            else:
                click.echo(f"Session not found: {session_id}")
        finally:
            await redis.close()
    
    asyncio.run(show_info())


@session.command("delete")
@click.argument("session_id")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
@click.pass_context
def session_delete(ctx: click.Context, session_id: str, yes: bool) -> None:
    """Delete a session."""
    settings: Settings = ctx.obj["settings"]
    
    if not yes:
        click.confirm(f"Delete session {session_id}?", abort=True)
    
    async def delete_session():
        from .session.redis_client import RedisClient
        from .session.manager import SessionManager
        
        redis = RedisClient(
            host=settings.redis.host,
            port=settings.redis.port
        )
        await redis.connect()
        
        try:
            manager = SessionManager(redis)
            await manager.delete_session(session_id)
            click.echo(f"Session {session_id} deleted")
        finally:
            await redis.close()
    
    asyncio.run(delete_session())


def main() -> None:
    """Main entry point."""
    cli(obj={})


if __name__ == "__main__":
    main()
