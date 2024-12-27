import os
import tempfile
from urllib.parse import urlparse

import requests
from pymupdf4llm import to_markdown

from arkaine.tools.tool import Argument, Context, Example, List, Optional, Tool


class PDFReader(Tool):
    """
    Convert local or remote hosted PDFs to markdown. Optionally limit which
    pages are converted.

    Args:
        temp_dir (Optional[str]): Directory for storing temporary files when
            processing remote PDFs. If not provided, uses system's default temp
            directory.

    Raises:
        ValueError: If the source file is invalid or inaccessible Exception: If
        there's an error processing the PDF
    """

    def __init__(self, temp_dir: Optional[str] = None):

        self.temp_dir = temp_dir or tempfile.gettempdir()

        super().__init__(
            name="pdf_reader",
            description=(
                "Reads PDF files from local filesystem or URLs and converts "
                "them to text or markdown"
            ),
            args=[
                Argument(
                    name="source",
                    description=(
                        "Path to PDF file or URL. For URLs, must end in .pdf"
                    ),
                    type="str",
                    required=True,
                ),
                Argument(
                    name="pages",
                    description=(
                        "Page numbers to extract (e.g., '1,2,3' or '1-5'). "
                        "Defaults to all pages."
                    ),
                    type="str",
                    required=False,
                    default="",
                ),
            ],
            func=self.read,
            examples=[
                Example(
                    name="Read Local PDF",
                    args={
                        "source": "/path/to/document.pdf",
                    },
                    output="Text content of the PDF...",
                    description="Extract text from a local PDF file",
                ),
                Example(
                    name="Read Remote PDF first 3 pages",
                    args={
                        "source": "https://example.com/document.pdf",
                        "pages": "1-3",
                    },
                    output="# Markdown content...",
                    description=(
                        "Download and convert PDF to markdown, pages 1-3 only"
                    ),
                ),
            ],
        )

    def _is_url(self, source: str) -> bool:
        """Check if the source is a URL."""
        try:
            result = urlparse(source)
            return all([result.scheme, result.netloc])
        except ValueError:
            return False

    def _download_pdf(self, url: str) -> str:
        """Download a PDF from URL to temporary file."""
        response = requests.get(url, stream=True)
        response.raise_for_status()

        # Create temp file with .pdf extension
        temp_file = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".pdf",
            dir=self.temp_dir,
        )

        with temp_file as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        return temp_file.name

    def _parse_pages(self, pages_str: Optional[str]) -> Optional[List[int]]:
        """
        Parse page numbers from string specification.

        Returns:
            List[int]: List of page numbers
            None: If no pages are specified

        Example:
            "1,2,3" -> [1, 2, 3]
            "1-3" -> [1, 2, 3]
            "" -> None
            "1-3,5-7" -> [1, 2, 3, 5, 6, 7]
        """
        if not pages_str:
            return None

        pages = set()
        for part in pages_str.split(","):
            if "-" in part:
                start, end = map(int, part.split("-"))
                pages.update(range(start, end + 1))
            else:
                pages.add(int(part))
        return sorted(list(pages))

    def read(
        self, context: Context, source: str = "", pages: Optional[str] = None
    ) -> str:
        """
        Read a PDF file and return its content.

        Args:
            source: Path to PDF file or URL
            to_markdown: Whether to convert to markdown format
            pages: Page numbers to extract (e.g., '1,2,3' or '1-5')

        Returns:
            str: Text or markdown content of the PDF

        Raises:
            ValueError: If source is invalid or PDF is inaccessible
            Exception: If there's an error processing the PDF
        """

        temp_file = None
        try:
            # Handle URL source
            if self._is_url(source):
                temp_file = self._download_pdf(source)
                pdf_path = temp_file
            else:
                if not os.path.exists(source):
                    raise ValueError(f"PDF file not found: {source}")
                pdf_path = source

            page_numbers = self._parse_pages(pages)

            # Read PDF
            md = to_markdown(pdf_path, pages=page_numbers, show_progress=False)

            return md

        except Exception as e:
            raise Exception(f"Failed to process PDF: {str(e)}")

        finally:
            # Cleanup temporary file
            if temp_file:
                try:
                    os.unlink(temp_file)
                except Exception:
                    pass
