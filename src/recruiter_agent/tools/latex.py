import re
from pathlib import Path

from pylatexenc.latexwalker import (
    LatexEnvironmentNode,
    LatexMacroNode,
    LatexWalker,
    LatexWalkerParseError,
)

from recruiter_agent.models.schemas import ResumeSection

# Characters that must be escaped in LaTeX text content.
# We skip $ (math mode) and ~ (non-breaking space) as they have
# legitimate unescaped uses in resumes.
_SPECIAL_CHARS = {"&": r"\&", "#": r"\#", "%": r"\%"}


def parse_latex(file_path: Path) -> tuple[str, str, list[ResumeSection]]:
    """Parse a .tex file into preamble, postamble, and content sections.

    Returns (preamble, postamble, sections) where:
    - preamble: everything up to and including \\begin{document}
    - postamble: \\end{document} and anything after
    - sections: list of ResumeSection objects
    """
    raw = file_path.read_text(encoding="utf-8")

    begin_match = re.search(r"(\\begin\{document\})", raw)
    if not begin_match:
        raise ValueError("No \\begin{document} found in the .tex file")

    preamble = raw[: begin_match.end()]
    rest = raw[begin_match.end() :]

    end_match = re.search(r"(\\end\{document\})", rest)
    if not end_match:
        raise ValueError("No \\end{document} found in the .tex file")

    body = rest[: end_match.start()]
    postamble = rest[end_match.start() :]

    section_pattern = r"(\\section\*?\{[^}]*\})"
    parts = re.split(section_pattern, body)

    sections: list[ResumeSection] = []

    header_content = parts[0].strip()
    if header_content:
        sections.append(
            ResumeSection(name="__header__", content=header_content)
        )

    for i in range(1, len(parts), 2):
        section_cmd = parts[i]
        section_content = parts[i + 1] if i + 1 < len(parts) else ""

        name_match = re.match(r"\\section\*?\{([^}]*)\}", section_cmd)
        name = name_match.group(1) if name_match else section_cmd

        sections.append(ResumeSection(name=name, content=section_content))

    return preamble, postamble, sections


def reconstruct_latex(
    preamble: str,
    postamble: str,
    sections: list[ResumeSection],
    use_section_star: bool = True,
) -> str:
    """Reconstruct a full .tex file from preamble, postamble, and sections."""
    parts = [preamble]

    for section in sections:
        if section.name == "__header__":
            parts.append(section.content)
        else:
            cmd = "\\section*" if use_section_star else "\\section"
            parts.append(f"\n{cmd}{{{section.name}}}")
            parts.append(section.content)

    parts.append(postamble)
    return "\n".join(parts)


def escape_special_chars(content: str) -> str:
    """Escape LaTeX special characters that the LLM left unescaped.

    Handles &, #, % while avoiding double-escaping already-escaped characters
    and preserving LaTeX commands that use these characters structurally.
    """
    for char, escaped in _SPECIAL_CHARS.items():
        # Replace bare char that isn't already escaped (not preceded by \)
        # For #, also skip when followed by { (e.g. color codes like #fff)
        if char == "#":
            content = re.sub(r"(?<!\\)#(?!\{)", escaped, content)
        elif char == "%":
            # Don't escape % at start of line (LaTeX comments)
            content = re.sub(
                r"(?<!\\)(?<!^)%", escaped, content, flags=re.MULTILINE
            )
        else:
            content = re.sub(rf"(?<!\\)\{char}", escaped, content)

    return content


def format_latex(content: str) -> str:
    """Format LaTeX content with proper line breaks and indentation.

    LLMs often collapse LaTeX into single lines when returning structured output.
    This restores readable formatting.
    """
    # Ensure \begin{env} is on its own line
    content = re.sub(r"(?<!\n)(\\begin\{)", r"\n\1", content)
    content = re.sub(r"(\\begin\{[^}]+\})(?!\n)", r"\1\n", content)

    # Ensure \end{env} is on its own line
    content = re.sub(r"(?<!\n)(\\end\{)", r"\n\1", content)
    content = re.sub(r"(\\end\{[^}]+\})(?!\n)", r"\1\n", content)

    # Each \item on its own line, indented
    content = re.sub(r"(?<!\n)\s*(\\item\s)", r"\n  \1", content)

    # Company/role header lines (\textbf{...} \\ or \textbf{...} \hfill)
    # should start on their own line when outside \item
    content = re.sub(
        r"(?<!\n)(\\textbf\{[^}]+\}\s*(?:\\\\|\\hfill))", r"\n\1", content
    )

    # Collapse 3+ consecutive newlines to 2
    content = re.sub(r"\n{3,}", "\n\n", content)

    return "\n" + content.strip() + "\n"


def validate_latex(content: str) -> list[str]:
    """Validate LaTeX content using pylatexenc's parser.

    Returns a list of warning strings. Empty list means no issues found.
    """
    warnings: list[str] = []

    # Use pylatexenc's walker to parse and catch structural errors
    try:
        walker = LatexWalker(content, tolerant_parsing=True)
        nodelist, _, _ = walker.get_latex_nodes()

        # Walk the node tree to check for mismatched environments
        _check_environments(nodelist, warnings)
    except LatexWalkerParseError as e:
        warnings.append(f"LaTeX parse error: {e}")

    # Additional checks that pylatexenc doesn't cover well

    # Check balanced braces (pylatexenc is tolerant, so we double-check)
    depth = 0
    for i, char in enumerate(content):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        if depth < 0:
            # Find surrounding context for the error
            start = max(0, i - 20)
            end = min(len(content), i + 20)
            context = content[start:end].replace("\n", "\\n")
            warnings.append(
                f"Unbalanced braces: extra '}}' near: ...{context}..."
            )
            break
    if depth > 0:
        warnings.append(f"Unbalanced braces: {depth} unclosed '{{' remaining")

    # Check for unescaped special characters in text content
    # (outside of commands and math mode)
    for char, escaped in _SPECIAL_CHARS.items():
        # Find bare occurrences not preceded by backslash
        if char == "%":
            # Skip start-of-line % (comments)
            matches = list(
                re.finditer(r"(?<!\\)(?<!^)%", content, re.MULTILINE)
            )
        elif char == "#":
            matches = list(re.finditer(r"(?<!\\)#(?!\{)", content))
        else:
            matches = list(re.finditer(rf"(?<!\\)\{char}", content))

        if matches:
            warnings.append(
                f"Found {len(matches)} unescaped '{char}' — should be '{escaped}'"
            )

    return warnings


def _check_environments(nodelist, warnings: list[str]) -> None:
    """Recursively check environment nodes for issues."""
    if nodelist is None:
        return

    for node in nodelist:
        if isinstance(node, LatexEnvironmentNode):
            env_name = node.environmentname
            # Check that the environment has content (not empty \begin{}\end{})
            if env_name and not node.nodelist:
                warnings.append(
                    f"Empty environment: \\begin{{{env_name}}}...\\end{{{env_name}}}"
                )
            # Recurse into environment content
            _check_environments(node.nodelist, warnings)

        elif isinstance(node, LatexMacroNode):
            # Recurse into macro arguments
            if node.nodeargd and node.nodeargd.argnlist:
                for arg in node.nodeargd.argnlist:
                    if hasattr(arg, "nodelist"):
                        _check_environments(arg.nodelist, warnings)
