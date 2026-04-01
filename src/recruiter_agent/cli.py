from pathlib import Path
from typing import Annotated, Optional

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from recruiter_agent.agent.graph import create_app

load_dotenv()

console = Console()

app = typer.Typer(
    name="recruiter-agent",
    help="Enhance your LaTeX resume for a specific job description using AI.",
    no_args_is_help=True,
)


@app.command()
def enhance(
    resume_path: Annotated[
        Path,
        typer.Argument(
            help="Path to your .tex resume file",
            exists=True,
            dir_okay=False,
            readable=True,
        ),
    ],
    jd_url: Annotated[
        Optional[str],
        typer.Option("--jd-url", "-j", help="URL of the job description"),
    ] = None,
    jd_file: Annotated[
        Optional[Path],
        typer.Option(
            "--jd-file",
            "-f",
            help="Path to a text file containing the job description",
        ),
    ] = None,
    output: Annotated[
        Optional[Path],
        typer.Option(
            "--output", "-o", help="Output path for enhanced .tex file"
        ),
    ] = None,
    model: Annotated[
        Optional[str],
        typer.Option("--model", "-m", help="LLM model name"),
    ] = None,
    provider: Annotated[
        str,
        typer.Option(
            "--provider", "-p", help="LLM provider (anthropic, openai, google)"
        ),
    ] = "google",
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show detailed agent reasoning"),
    ] = False,
    no_interactive: Annotated[
        bool,
        typer.Option("--no-interactive", help="Skip clarifying questions"),
    ] = False,
):
    """Enhance a LaTeX resume to match a job description and improve ATS score."""

    # Validate input
    if resume_path.suffix != ".tex":
        console.print("[red]Error: Resume file must be a .tex file[/]")
        raise typer.Exit(1)

    if not jd_url and not jd_file:
        console.print("[red]Error: Provide either --jd-url or --jd-file[/]")
        raise typer.Exit(1)

    # If --jd-file is provided, read it and pass as pre-loaded JD text
    jd_text_override: str | None = None
    if jd_file:
        if not jd_file.exists():
            console.print(f"[red]Error: JD file not found: {jd_file}[/]")
            raise typer.Exit(1)
        jd_text_override = jd_file.read_text(encoding="utf-8")

    # Default output path
    if output is None:
        output = resume_path.with_stem(f"{resume_path.stem}_enhanced")

    console.print()
    console.print("[bold]Resume Enhancer Agent[/]", highlight=False)
    console.print(f"  Resume:   {resume_path}")
    if jd_url:
        console.print(f"  JD URL:   {jd_url}")
    if jd_file:
        console.print(f"  JD File:  {jd_file}")
    console.print(f"  Output:   {output}")
    console.print(f"  Provider: {provider}")
    console.print(f"  Model:    {model or 'default'}")
    console.print()

    # Build and run the agent
    agent = create_app()

    initial_state = {
        "resume_path": str(resume_path),
        "jd_url": jd_url or "",
        "output_path": str(output),
        "provider": provider,
        "model": model,
        "no_interactive": no_interactive,
        "verbose": verbose,
        "jd_text_override": jd_text_override,
    }

    result = agent.invoke(initial_state)

    # Display comparison table
    before = result["before_score"]
    after = result["after_score"]

    console.print()
    table = Table(
        title="ATS Score Comparison", show_header=True, header_style="bold"
    )
    table.add_column("Category", style="bold")
    table.add_column("Before", justify="center")
    table.add_column("After", justify="center")
    table.add_column("Change", justify="center")

    rows = [
        ("Keyword Match", before.keyword_match, after.keyword_match),
        ("Relevance", before.relevance, after.relevance),
        ("Quantification", before.quantification, after.quantification),
        ("Formatting", before.formatting, after.formatting),
        ("Overall", before.overall, after.overall),
    ]

    for name, b, a in rows:
        diff = a - b
        if diff > 0:
            change_str = f"[green]+{diff}[/]"
        elif diff < 0:
            change_str = f"[red]{diff}[/]"
        else:
            change_str = "[dim]0[/]"

        before_style = (
            "[red]" if b < 50 else "[yellow]" if b < 70 else "[green]"
        )
        after_style = "[red]" if a < 50 else "[yellow]" if a < 70 else "[green]"

        table.add_row(
            name,
            f"{before_style}{b}[/]",
            f"{after_style}{a}[/]",
            change_str,
        )

    console.print(table)
    console.print()
    console.print(f"[bold green]Enhanced resume written to:[/] {output}")
    console.print()
