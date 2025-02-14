import os
import re
import tempfile
from threading import Lock
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from pymupdf4llm import to_markdown


class Website:
    def __init__(
        self,
        url: str,
        title: str = "",
        snippet: str = "",
        load_content: bool = False,
    ):
        self.url = url
        self.title = title
        self.snippet = snippet
        self.domain = Website.extract_domain(url)
        self.raw_content: Optional[str] = None
        self.is_pdf = False
        self.lock = Lock()

        if load_content:
            self.load_content()

    @property
    def content(self) -> str:
        if not self.raw_content:
            self.load_content()
        return self.get_markdown()

    def get_title(self) -> str:
        if not self.raw_content:
            self.load_content()

        if self.is_pdf:
            # For PDFs, use the filename as the title if no title set
            if not self.title:
                self.title = os.path.basename(self.url)
            return self.title

        soup = BeautifulSoup(self.raw_content, "html.parser")
        title_tag = soup.title
        if title_tag and title_tag.string:
            self.title = title_tag.string.strip()
        else:
            # Fallback to h1 if no title tag
            h1 = soup.find("h1")
            if h1:
                self.title = h1.get_text().strip()
            else:
                # Last resort - use domain name
                self.title = self.domain

        return self.title

    @classmethod
    def extract_domain(self, url: str) -> str:
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        domain = domain.split(":")[0]
        domain = re.sub(r"^www\.", "", domain)
        parts = domain.split(".")
        if len(parts) > 2:
            domain = ".".join(parts[-2:])
        return domain

    def load_content(self):
        with self.lock:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip",
                "Connection": "keep-alive",
            }

            session = requests.Session()
            session.headers.update(headers)
            response = session.get(self.url, stream=True)
            response.raise_for_status()

            content_type = response.headers.get("Content-Type", "").lower()
            if "application/pdf" in content_type or self.url.lower().endswith(
                ".pdf"
            ):
                self.is_pdf = True
                temp_file = None
                try:
                    temp_file = tempfile.NamedTemporaryFile(
                        delete=False, suffix=".pdf"
                    )
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            temp_file.write(chunk)
                    temp_file.close()

                    self.raw_content = to_markdown(
                        temp_file.name, show_progress=False
                    )
                finally:
                    if temp_file:
                        try:
                            os.unlink(temp_file.name)
                        except Exception:
                            pass
            else:
                if "Content-Encoding" in response.headers:
                    if response.headers["Content-Encoding"] == "gzip":
                        self.raw_content = response.content.decode(
                            "utf-8", errors="replace"
                        )
                else:
                    self.raw_content = response.text

    def get_body(self):
        if not self.raw_content:
            self.load_content()
        soup = BeautifulSoup(self.raw_content, "html.parser")
        return soup.body

    def get_markdown(self):
        if not self.raw_content:
            self.load_content()

        if self.is_pdf:
            return self.raw_content

        soup = BeautifulSoup(self.raw_content, "html.parser")
        markdown = md(soup.body.get_text())
        markdown = re.sub(r"\n+", "\n", markdown)
        return markdown

    def format(self, template: str) -> str:
        return template.format(
            url=self.url,
            domain=self.domain,
            title=self.title,
            snippet=self.snippet,
        )

    def __str__(self):
        return f"{self.title}\n{self.url}\n\t{self.snippet}"

    def __repr__(self):
        return self.__str__()

    def to_json(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "snippet": self.snippet,
            "domain": self.domain,
            "raw_content": self.raw_content,
            "is_pdf": self.is_pdf,
        }

    @classmethod
    def from_json(cls, json_data: Dict[str, Any]) -> "Website":
        return cls(
            url=json_data["url"],
            title=json_data["title"],
            snippet=json_data["snippet"],
            load_content=False,
        )
