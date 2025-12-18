"""PersonaGym-R CLI interface."""
import typer
from pathlib import Path
from rich.console import Console
from rich.table import Table
from typing import Optional

from .orchestrator import run_task

app = typer.Typer()
console = Console()

@app.command()
def main(
    task: str = typer.Option(..., "--task", help="Path to task directory"),
    white: str = typer.Option(..., "--white", help="White agent to use (prompt/tool/llm)"),
    seed: Optional[int] = typer.Option(None, "--seed", help="Optional RNG seed override")
):
    """Run a PersonaGym-R evaluation task."""
    # Validate task directory
    task_path = Path(task)
    if not task_path.is_dir():
        console.print(f"[red]Error:[/] Task directory not found: {task}")
        raise typer.Exit(1)
    
    # Validate white agent
    if white not in ["prompt", "tool", "bad", "llm", "openai", "claude"]:
        console.print(f"[red]Error:[/] Invalid white agent: {white}")
        console.print("Must be one of: prompt, tool, bad, llm, openai, claude")
        raise typer.Exit(1)
    
    # Run evaluation
    console.print(f"\nRunning evaluation with {white} agent...")
    exit_code = run_task(str(task_path), white, seed)
    
    if exit_code != 0:
        console.print("\n[red]Evaluation failed[/]")
    
    raise typer.Exit(exit_code)

if __name__ == "__main__":
    app()