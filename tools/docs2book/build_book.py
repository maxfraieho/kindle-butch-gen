#!/usr/bin/env python3
"""
docs2book: Convert a folder of Markdown documentation into a printable PDF book.
Supports Typst (via Pandoc) as primary engine and WeasyPrint as fallback engine.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Tuple, Dict, Set, Optional

# For WeasyPrint fallback engine
try:
    import markdown2
    from jinja2 import Template
    from pygments.formatters import HtmlFormatter
    import weasyprint
    WEASYPRINT_AVAILABLE = True
except ImportError:
    WEASYPRINT_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


def slugify(text: str) -> str:
    """Convert text into a URL/anchor slug."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    return text.strip('-') or 'heading'


def parse_numeric_prefix(name: str) -> Tuple[int, int, str]:
    """
    Extract numeric prefix for sorting.
    Returns (sort_category, prefix_num, clean_name)
    sort_category: 0 if numeric prefix exists, 1 otherwise.
    """
    m = re.match(r'^(\d+)[._-](.*)$', name)
    if m:
        return (0, int(m.group(1)), m.group(2).lower())
    return (1, 0, name.lower())


def sort_key_for_path(rel_path: Path) -> List[Tuple[int, int, str]]:
    """Generate sort key tuple for relative path components."""
    keys = []
    for part in rel_path.parts:
        keys.append(parse_numeric_prefix(part))
    return keys


def extract_frontmatter(content: str) -> Tuple[Optional[Dict[str, str]], str]:
    """Extract YAML frontmatter if present and return (metadata_dict, remaining_content)."""
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            front_text = parts[1]
            body = parts[2]
            meta = {}
            for line in front_text.splitlines():
                if ':' in line:
                    key, val = line.split(':', 1)
                    key = key.strip()
                    val = val.strip().strip('"\'')
                    meta[key] = val
            return meta, body
    return None, content


def clean_mdx_content(text: str) -> str:
    """Clean MDX content: strip JSX tags, clean code block info strings, normalize multi-backtick blocks."""
    # Strip JSX component tags
    text = re.sub(r'</?[A-Z][a-zA-Z0-9._-]*[^>]*>', '', text)
    # Clean code fence info strings e.g. ```ts title="agent.ts" -> ```ts
    # NOTE: use [ \t]+ (not \s+) — \s matches \n, so \s+.* previously crossed
    # the fence-line boundary and swallowed the code block's first content line
    # whenever the language tag had no trailing info string (e.g. plain ```ts).
    text = re.sub(r'^(```+)([a-zA-Z0-9_-]+)[ \t]+\S.*$', r'\1\2', text, flags=re.MULTILINE)
    # Normalize 4+ backtick code block fences to 3 backticks
    text = re.sub(r'^`{4,}', '```', text, flags=re.MULTILINE)
    return text


def find_first_h1(content: str) -> Optional[str]:
    """Find title from first H1 line in content."""
    for line in content.splitlines():
        line_s = line.strip()
        if line_s.startswith('# ') and not line_s.startswith('##'):
            title = line_s[2:].strip()
            title = re.sub(r'\s*\{#.*\}\s*$', '', title)
            return title
    return None


def derive_title_from_filename(filename: str) -> str:
    """Derive human-readable title from filename."""
    stem = Path(filename).stem
    clean = re.sub(r'^\d+[._-]', '', stem)
    clean = clean.replace('_', ' ').replace('-', ' ')
    return clean.title() or "Chapter"


def collect_markdown_files(docs_dir: Path) -> List[Path]:
    """Recursively collect all .md and .mdx files under docs_dir."""
    md_files = []
    for ext in ('*.md', '*.mdx'):
        md_files.extend(docs_dir.rglob(ext))
    
    valid_files = []
    for f in md_files:
        rel = f.relative_to(docs_dir)
        if not any(part.startswith('.') for part in rel.parts):
            valid_files.append(f)

    root_indices = ['readme.md', 'index.md', 'introduction.md', 'readme.mdx', 'index.mdx', 'introduction.mdx']
    
    def path_sort_rank(f: Path) -> Tuple[int, List[Tuple[int, int, str]]]:
        rel = f.relative_to(docs_dir)
        if len(rel.parts) == 1 and rel.name.lower() in root_indices:
            idx_priority = root_indices.index(rel.name.lower())
            return (0, [(0, idx_priority, rel.name)])
        return (1, sort_key_for_path(rel))

    valid_files.sort(key=path_sort_rank)
    return valid_files


class DocFile:
    def __init__(self, full_path: Path, docs_dir: Path):
        self.full_path = full_path
        self.rel_path = full_path.relative_to(docs_dir)
        self.rel_path_no_ext = self.rel_path.with_suffix('')
        
        self.file_key = str(self.rel_path_no_ext).replace('/', '_').replace('\\', '_')
        self.file_anchor = f"doc__{self.file_key}"
        
        self.depth = len(self.rel_path.parent.parts)
        
        raw_text = full_path.read_text(encoding='utf-8', errors='replace')
        self.meta, body_text = extract_frontmatter(raw_text)
        
        self.body = clean_mdx_content(body_text)
        
        fm_title = self.meta.get('title') if self.meta else None
        h1_title = find_first_h1(self.body)
        if fm_title:
            self.title = fm_title
        elif h1_title:
            self.title = h1_title
        else:
            self.title = derive_title_from_filename(full_path.name)
            
        self.heading_anchors: Dict[str, str] = {}


def process_headings_and_anchors(docs: List[DocFile]) -> Set[str]:
    """Assign heading anchors and build set of all valid anchor IDs."""
    valid_anchors: Set[str] = set()
    
    for doc in docs:
        valid_anchors.add(doc.file_anchor)
        
        lines = doc.body.splitlines()
        for line in lines:
            line_s = line.strip()
            m = re.match(r'^(#{1,6})\s+(.*)', line_s)
            if m:
                heading_text = m.group(2).strip()
                heading_clean = re.sub(r'\s*\{#.*\}\s*$', '', heading_text)
                h_slug = slugify(heading_clean)
                h_anchor = f"{doc.file_anchor}__{h_slug}"
                
                uniq_anchor = h_anchor
                counter = 1
                while uniq_anchor in valid_anchors:
                    uniq_anchor = f"{h_anchor}_{counter}"
                    counter += 1
                
                valid_anchors.add(uniq_anchor)
                doc.heading_anchors[line_s] = uniq_anchor

    return valid_anchors


def transform_doc_content(
    doc: DocFile,
    docs_dir: Path,
    valid_anchors: Set[str],
    media_dir: Path,
    copied_media: Dict[Path, str]
) -> str:
    """Transform headings, rewrite links and images for a single document."""
    lines = doc.body.splitlines()
    transformed_lines = []
    
    file_heading_level = min(6, 1 + doc.depth)
    file_heading_hashes = '#' * file_heading_level
    
    top_heading_line = f"{file_heading_hashes} {doc.title} {{#{doc.file_anchor}}}"
    transformed_lines.append(top_heading_line)
    transformed_lines.append("")
    
    first_heading_processed = False

    for line in lines:
        line_s = line.strip()
        
        m = re.match(r'^(#{1,6})\s+(.*)', line_s)
        if m:
            hashes, heading_content = m.group(1), m.group(2).strip()
            heading_clean = re.sub(r'\s*\{#.*\}\s*$', '', heading_content)
            
            if not first_heading_processed and len(hashes) == 1 and heading_clean.lower() == doc.title.lower():
                first_heading_processed = True
                continue
            
            first_heading_processed = True
            
            new_level = min(6, len(hashes) + doc.depth)
            new_hashes = '#' * new_level
            
            anchor_id = doc.heading_anchors.get(line_s)
            if not anchor_id or anchor_id == doc.file_anchor:
                anchor_id = f"{doc.file_anchor}__{slugify(heading_clean)}"
            
            transformed_lines.append(f"{new_hashes} {heading_clean} {{#{anchor_id}}}")
            continue

        line_transformed = rewrite_links_and_images(
            line, doc, docs_dir, valid_anchors, media_dir, copied_media
        )
        transformed_lines.append(line_transformed)

    return "\n".join(transformed_lines)


def resolve_file_anchor(current_doc: DocFile, href_file: str, docs_dir: Path) -> Optional[str]:
    """Find matching file in docs_dir even if extension (.md vs .mdx) differs."""
    clean_href = href_file.lstrip('/')
    target_full = (current_doc.full_path.parent / clean_href).resolve()
    try:
        target_rel = target_full.relative_to(docs_dir)
        target_file_key = str(target_rel.with_suffix('')).replace('/', '_').replace('\\', '_')
        return f"doc__{target_file_key}"
    except ValueError:
        pass
    
    if href_file.startswith('/'):
        root_full = (docs_dir / clean_href).resolve()
        try:
            target_rel = root_full.relative_to(docs_dir)
            target_file_key = str(target_rel.with_suffix('')).replace('/', '_').replace('\\', '_')
            return f"doc__{target_file_key}"
        except ValueError:
            pass

    stem = Path(clean_href).stem
    for rel_p in current_doc.full_path.parent.glob(f"{stem}.*"):
        try:
            target_rel = rel_p.relative_to(docs_dir)
            target_file_key = str(target_rel.with_suffix('')).replace('/', '_').replace('\\', '_')
            return f"doc__{target_file_key}"
        except ValueError:
            pass
            
    return None


def rewrite_links_and_images(
    line: str,
    doc: DocFile,
    docs_dir: Path,
    valid_anchors: Set[str],
    media_dir: Path,
    copied_media: Dict[Path, str]
) -> str:
    """Rewrite relative markdown links and copy/rewrite images."""
    
    # 1. Process Images: ![alt](src)
    def replace_image(match: re.Match) -> str:
        alt = match.group(1)
        src = match.group(2).strip()
        
        if src.startswith(('http://', 'https://', 'data:', 'ftp://')):
            return f"![{alt}]({src})"
        
        img_full_path = (doc.full_path.parent / src.lstrip('/')).resolve()
        if img_full_path.is_file():
            if img_full_path not in copied_media:
                ext = img_full_path.suffix
                unique_name = f"{doc.file_key}_{len(copied_media)}{ext}"
                dest_path = media_dir / unique_name
                shutil.copy2(img_full_path, dest_path)
                copied_media[img_full_path] = f"media/{unique_name}"
            
            new_src = copied_media[img_full_path]
            return f"![{alt}]({new_src})"
        return match.group(0)

    line = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', replace_image, line)

    # 2. Process Links: [text](href) (excluding images)
    def replace_link(match: re.Match) -> str:
        text = match.group(1)
        href = match.group(2).strip()
        
        if href.startswith(('http://', 'https://', 'mailto:', 'ftp://')):
            return f"[{text}]({href})"
        
        if '#' in href:
            target_path_str, anchor_part = href.split('#', 1)
        else:
            target_path_str, anchor_part = href, None

        if target_path_str:
            target_file_anchor = resolve_file_anchor(doc, target_path_str, docs_dir)
            if target_file_anchor:
                if anchor_part:
                    target_h_anchor = f"{target_file_anchor}__{slugify(anchor_part)}"
                    if target_h_anchor in valid_anchors:
                        return f"[{text}](#{target_h_anchor})"
                if target_file_anchor in valid_anchors:
                    return f"[{text}](#{target_file_anchor})"
            return text
        else:
            if anchor_part:
                if anchor_part.startswith('doc__'):
                    if anchor_part in valid_anchors:
                        return f"[{text}](#{anchor_part})"
                    parts = anchor_part.split('__')
                    for i in range(len(parts) - 1, 1, -1):
                        file_key_candidate = "doc__" + "_".join(parts[1:i])
                        if file_key_candidate in valid_anchors:
                            return f"[{text}](#{file_key_candidate})"
                    return text
                else:
                    in_file_anchor = f"{doc.file_anchor}__{slugify(anchor_part)}"
                    if in_file_anchor in valid_anchors:
                        return f"[{text}](#{in_file_anchor})"
                    elif doc.file_anchor in valid_anchors:
                        return f"[{text}](#{doc.file_anchor})"
                    return text
            return f"[{text}]({href})"

    pattern = r'(?<!\!)\[([^\]]+)\]\(([^)]+)\)'
    line = re.sub(pattern, replace_link, line)
    
    return line


def preprocess_mermaid_blocks(text: str, media_dir: Path) -> str:
    """
    Replace ```mermaid...``` fences with rendered SVG images.
    Uses Kroki public API (https://kroki.io); falls back to a code block
    with a caption if the API is unreachable or requests is unavailable.
    """
    counter = [0]

    def replace_mermaid(match: re.Match) -> str:
        diagram_src = match.group(1)
        counter[0] += 1
        fname = f"mermaid_{counter[0]}.svg"
        img_path = media_dir / fname

        if REQUESTS_AVAILABLE:
            try:
                resp = requests.post(
                    "https://kroki.io/mermaid/svg",
                    data=diagram_src.strip().encode("utf-8"),
                    headers={"Content-Type": "text/plain"},
                    timeout=15,
                )
                if resp.ok:
                    img_path.write_bytes(resp.content)
                    return f"\n\n![Diagram {counter[0]}](media/{fname})\n\n"
                print(f"Warning: Kroki API returned {resp.status_code} for diagram {counter[0]}. Using fallback.")
            except Exception as exc:
                print(f"Warning: Mermaid render via Kroki failed ({exc}). Using fallback.")

        return (
            f"\n\n```\n{diagram_src.strip()}\n```\n\n"
            f"*[Diagram source — rendering unavailable]*\n\n"
        )

    return re.sub(
        r"```mermaid[ \t]*\n(.*?)\n```",
        replace_mermaid,
        text,
        flags=re.DOTALL,
    )


def build_typst(
    merged_md_path: Path,
    template_path: Path,
    out_pdf_path: Path,
    build_dir: Path,
    title: str,
    author: str,
    lang: str
) -> bool:
    """Compile PDF using Pandoc + Typst pipeline."""
    pandoc_bin = shutil.which('pandoc')
    typst_bin = shutil.which('typst')
    
    if not pandoc_bin or not typst_bin:
        print("Typst engine requirement missing: pandoc or typst binary not found in PATH.")
        return False
        
    outline_title = "Зміст" if lang.lower() == 'uk' else "Contents"
    
    template_content = template_path.read_text(encoding='utf-8')
    template_content = template_content.replace('OUTLINE_TITLE_PLACEHOLDER', outline_title)
    template_content = template_content.replace('TITLE_PLACEHOLDER', title)
    template_content = template_content.replace('AUTHOR_PLACEHOLDER', author)
    template_content = template_content.replace('LANG_PLACEHOLDER', lang)
    
    prepared_template = build_dir / "prepared_template.typ"
    prepared_template.write_text(template_content, encoding='utf-8')
    
    book_typ = build_dir / "book.typ"
    
    pandoc_cmd = [
        pandoc_bin,
        "-f", "markdown+header_attributes-citations+lists_without_preceding_blankline",
        "-t", "typst",
        str(merged_md_path),
        "-o", str(book_typ),
        f"--template={prepared_template}",
    ]
    
    res_pandoc = subprocess.run(pandoc_cmd, cwd=build_dir, capture_output=True, text=True)
    if res_pandoc.returncode != 0:
        print(f"Pandoc failed (exit code {res_pandoc.returncode}):\n{res_pandoc.stderr}")
        return False

    # TTS/book quality audit (2026-08-02) Phase 0.6: Typst on this device
    # only sees its 4 built-in font families by default (no Liberation
    # Serif, despite book_template.typ requesting it) -- every book
    # rendered before this fix silently fell back to Libertinus Serif.
    # --font-path makes the installed Source Serif 4 (and anything else
    # under this directory) visible.
    font_path = os.path.expanduser("~/.local/share/fonts")
    typst_cmd = [
        typst_bin,
        "compile",
        "--font-path", font_path,
        str(book_typ),
        str(out_pdf_path.resolve())
    ]

    res_typst = subprocess.run(typst_cmd, cwd=build_dir, capture_output=True, text=True)
    if res_typst.returncode != 0:
        print(f"Typst compile failed (exit code {res_typst.returncode}):\n{res_typst.stderr}")
        return False

    # Print warnings even on success -- this is exactly how the missing-font
    # fallback above went unnoticed through every prior book render (the
    # old code only surfaced stderr on a non-zero exit code).
    if res_typst.stderr.strip():
        print(f"Typst compile warnings:\n{res_typst.stderr}")

    return out_pdf_path.exists() and out_pdf_path.stat().st_size > 0


def build_weasyprint(
    merged_md_path: Path,
    out_pdf_path: Path,
    build_dir: Path,
    title: str,
    author: str,
    lang: str
) -> bool:
    """Compile PDF using Python + WeasyPrint fallback engine."""
    if not WEASYPRINT_AVAILABLE:
        print("WeasyPrint dependencies (weasyprint, markdown2, jinja2, pygments) are not available.")
        return False
        
    merged_md_text = merged_md_path.read_text(encoding='utf-8')
    
    clean_md_text = re.sub(r'```\{=typst\}.*?```', '', merged_md_text, flags=re.DOTALL)
    clean_md_text = re.sub(r'\s*\{#[^\}]+\}', '', clean_md_text)
    
    html_body = markdown2.markdown(
        clean_md_text,
        extras=['fenced-code-blocks', 'tables', 'footnotes', 'header-ids', 'toc']
    )
    
    formatter = HtmlFormatter(style='default')
    css_code = formatter.get_style_defs('.codehilite') + '\n' + formatter.get_style_defs('.highlight')
    
    outline_title = "Зміст" if lang.lower() == 'uk' else "Contents"

    html_template_str = """<!DOCTYPE html>
<html lang="{{ lang }}">
<head>
<meta charset="utf-8">
<title>{{ title }}</title>
<style>
@page {
  size: A4;
  margin: 2.5cm 2cm;
  @bottom-center {
    content: counter(page);
    font-family: 'Liberation Serif', serif;
    font-size: 9pt;
  }
}

@page cover {
  margin: 0;
  @bottom-center {
    content: none;
  }
}

body {
  font-family: 'Liberation Serif', serif;
  font-size: 10.5pt;
  line-height: 1.6;
  text-align: justify;
  color: #212529;
}

.cover-page {
  page: cover;
  height: 100vh;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  text-align: center;
  page-break-after: always;
  padding: 4cm 2cm;
  box-sizing: border-box;
}

.cover-title {
  font-size: 32pt;
  font-weight: bold;
  margin-bottom: 20px;
  line-height: 1.2;
}

.cover-divider {
  width: 40%;
  height: 2px;
  background-color: #333;
  margin: 20px auto;
}

.cover-author {
  font-size: 14pt;
  font-style: italic;
  color: #495057;
  margin-top: 15px;
}

h1, h2, h3, h4, h5, h6 {
  font-family: 'Liberation Serif', serif;
  page-break-after: avoid;
  color: #111;
  margin-top: 1.4em;
  margin-bottom: 0.5em;
}

h1 { font-size: 20pt; border-bottom: 1px solid #dee2e6; padding-bottom: 0.3em; }
h2 { font-size: 16pt; }
h3 { font-size: 13pt; }

p { margin-top: 0; margin-bottom: 1em; }

a { color: #0366d6; text-decoration: none; }
a[href^="http"]:after {
  content: " (" attr(href) ")";
  font-size: 0.85em;
  color: #6c757d;
}

pre {
  background-color: #f8f9fa;
  padding: 10pt;
  border-radius: 4pt;
  border: 1pt solid #e9ecef;
  white-space: pre-wrap;
  word-wrap: break-word;
  font-family: monospace;
  font-size: 9.5pt;
  page-break-inside: avoid;
}

code {
  background-color: #f8f9fa;
  padding: 2pt 4pt;
  border-radius: 3pt;
  font-family: monospace;
  font-size: 9.5pt;
}

table {
  width: 100%;
  border-collapse: collapse;
  margin-bottom: 1em;
  page-break-inside: avoid;
}

th, td {
  border: 1pt solid #dee2e6;
  padding: 6pt 10pt;
  text-align: left;
}

th {
  background-color: #f1f3f5;
  font-weight: bold;
}

img {
  max-width: 100%;
  height: auto;
  display: block;
  margin: 1em auto;
}

blockquote {
  border-left: 4pt solid #0366d6;
  padding-left: 10pt;
  color: #495057;
  margin-left: 0;
  margin-right: 0;
}

{{ css_code }}
</style>
</head>
<body>

<div class="cover-page">
  <div class="cover-title">{{ title }}</div>
  <div class="cover-divider"></div>
  <div class="cover-author">{{ author }}</div>
</div>

<div class="book-body">
{{ body }}
</div>

</body>
</html>
"""
    template = Template(html_template_str)
    rendered_html = template.render(
        title=title,
        author=author,
        lang=lang,
        body=html_body,
        css_code=css_code
    )
    
    out_pdf_path.parent.mkdir(parents=True, exist_ok=True)
    weasyprint.HTML(string=rendered_html, base_url=str(build_dir)).write_pdf(out_pdf_path)
    return out_pdf_path.exists() and out_pdf_path.stat().st_size > 0


def main():
    parser = argparse.ArgumentParser(
        description="Convert a folder of Markdown documentation into a printable PDF book."
    )
    parser.add_argument("--docs", required=True, type=Path, help="Path to input documentation directory")
    parser.add_argument("--out", required=True, type=Path, help="Path to output PDF file")
    parser.add_argument("--title", default="Documentation", help="Book title")
    parser.add_argument("--author", default="docs2book", help="Book author")
    parser.add_argument("--lang", default="en", help="Language code (e.g. en, uk)")
    parser.add_argument(
        "--engine",
        choices=["auto", "typst", "weasyprint"],
        default="auto",
        help="PDF generation engine (default: auto)"
    )

    args = parser.parse_args()

    docs_dir = args.docs.resolve()
    if not docs_dir.is_dir():
        print(f"Error: --docs directory '{docs_dir}' does not exist or is not a directory.", file=sys.stderr)
        sys.exit(1)

    out_pdf = args.out.resolve()

    script_dir = Path(__file__).parent.resolve()
    typst_template = script_dir / "book_template.typ"

    md_files = collect_markdown_files(docs_dir)
    if not md_files:
        print(f"Error: No markdown (.md or .mdx) files found under '{docs_dir}'.", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(md_files)} markdown files in '{docs_dir}'. Processing...")

    doc_objects = [DocFile(f, docs_dir) for f in md_files]
    valid_anchors = process_headings_and_anchors(doc_objects)

    with tempfile.TemporaryDirectory(prefix="docs2book_") as tmp_dir_str:
        build_dir = Path(tmp_dir_str)
        media_dir = build_dir / "media"
        media_dir.mkdir(parents=True, exist_ok=True)
        
        copied_media: Dict[Path, str] = {}
        merged_chunks = []

        for doc in doc_objects:
            transformed_content = transform_doc_content(
                doc, docs_dir, valid_anchors, media_dir, copied_media
            )
            merged_chunks.append(transformed_content)

        merged_md_content = "\n\n```{=typst}\n#pagebreak()\n```\n\n".join(merged_chunks)
        merged_md_content = preprocess_mermaid_blocks(merged_md_content, media_dir)
        merged_md_path = build_dir / "merged.md"
        merged_md_path.write_text(merged_md_content, encoding='utf-8')

        success = False

        if args.engine in ("typst", "auto"):
            print("Attempting build with Typst engine (Pandoc + Typst)...")
            try:
                success = build_typst(
                    merged_md_path,
                    typst_template,
                    out_pdf,
                    build_dir,
                    args.title,
                    args.author,
                    args.lang
                )
                if success:
                    print(f"Successfully generated PDF using Typst engine -> '{out_pdf}'")
                else:
                    print("Typst build failed or generated empty PDF.")
            except Exception as e:
                print(f"Typst engine encountered error: {e}")
                success = False

        if not success and args.engine in ("weasyprint", "auto"):
            print("Running build with WeasyPrint fallback engine...")
            try:
                success = build_weasyprint(
                    merged_md_path,
                    out_pdf,
                    build_dir,
                    args.title,
                    args.author,
                    args.lang
                )
                if success:
                    print(f"Successfully generated PDF using WeasyPrint engine -> '{out_pdf}'")
                else:
                    print("WeasyPrint build failed.", file=sys.stderr)
            except Exception as e:
                print(f"WeasyPrint engine encountered error: {e}", file=sys.stderr)
                success = False

        if not success:
            print("Error: Failed to generate PDF book with selected engine(s).", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
