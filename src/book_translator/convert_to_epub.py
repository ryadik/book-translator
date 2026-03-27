"""
EPUB conversion module for book-translator.

Converts translated text files to EPUB format using ebooklib.
"""
from __future__ import annotations

from pathlib import Path

try:
    from ebooklib import epub
    _EBOOKLIB_AVAILABLE = True
except ImportError:
    _EBOOKLIB_AVAILABLE = False


def convert_txt_to_epub(
    input_file: Path,
    output_file: Path,
    title: str,
    author: str = '',
    language: str = 'ru',
) -> None:
    """Convert a plain text file to an EPUB file.

    Args:
        input_file: Path to the source .txt file.
        output_file: Path to write the resulting .epub file.
        title: Book title (used in EPUB metadata).
        author: Author name (used in EPUB metadata).

    Raises:
        ImportError: if ebooklib is not installed.
        FileNotFoundError: if input_file does not exist.
    """
    if not _EBOOKLIB_AVAILABLE:
        raise ImportError(
            "ebooklib is not installed. Run: pip install -e .[dev] or pip install ebooklib"
        )

    if not input_file.is_file():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    content = input_file.read_text(encoding='utf-8')

    # Split into paragraphs
    paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]

    if not paragraphs:
        raise ValueError("Документ пуст — невозможно создать EPUB из пустого файла.")

    # Build EPUB
    book = epub.EpubBook()
    book.set_title(title)
    book.set_language(language)
    if author:
        book.add_author(author)

    # Build HTML chapter content
    html_paragraphs = '\n'.join(f'<p>{para}</p>' for para in paragraphs)
    html_content = f'''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <title>{title}</title>
  <meta charset="utf-8"/>
</head>
<body>
{html_paragraphs}
</body>
</html>'''

    # Create chapter
    chapter = epub.EpubHtml(
        title=title,
        file_name='chapter.xhtml',
        lang=language,
    )
    chapter.set_content(html_content)
    book.add_item(chapter)

    # Table of contents and spine
    book.toc = [epub.Link('chapter.xhtml', title, 'chapter')]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ['nav', chapter]

    epub.write_epub(str(output_file), book)
