import httpx
from bs4 import BeautifulSoup
from rich.console import Console

try:
    import trafilatura
except ImportError:
    trafilatura = None  # type: ignore[assignment]

console = Console()


def scrape_jd(url: str) -> str:
    """Fetch a job description URL and extract the text content.
    Falls back to asking the user to paste the JD if scraping fails.
    """
    try:
        return _fetch_and_extract(url)
    except Exception as e:
        console.print(f"[yellow]Could not scrape URL: {e}[/]")
        console.print("[yellow]Some sites block automated requests.[/]")
        console.print()
        console.print("[bold]Please paste the job description text below.[/]")
        console.print("[dim]Paste the content, then press Enter twice on an empty line to finish:[/]")
        console.print()
        return _read_multiline_input()


def _read_multiline_input() -> str:
    """Read multi-line input from the user, ending on a blank line."""
    lines: list[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line == "" and lines and lines[-1] == "":
            # Two consecutive empty lines — done
            lines.pop()  # remove trailing blank
            break
        lines.append(line)
    text = "\n".join(lines).strip()
    if not text:
        raise ValueError("No job description text provided")
    return text


def _fetch_and_extract(url: str) -> str:
    """Fetch URL and extract text content."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    response = httpx.get(url, headers=headers, follow_redirects=True, timeout=30)
    response.raise_for_status()
    html = response.text

    # Try trafilatura first — better at extracting main content from job boards
    if trafilatura is not None:
        extracted = trafilatura.extract(html, include_links=False, include_tables=True)
        if extracted and len(extracted) > 100:
            return extracted

    # Fallback to BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")

    # Remove script and style elements
    for element in soup(["script", "style", "nav", "footer", "header"]):
        element.decompose()

    text = soup.get_text(separator="\n", strip=True)

    # Clean up excessive whitespace
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    result = "\n".join(lines)

    if len(result) < 100:
        raise ValueError(f"Extracted text too short ({len(result)} chars) — likely blocked or empty page")

    return result
