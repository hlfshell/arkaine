from __future__ import annotations

import os
import re
import tempfile
from threading import Lock
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from pymupdf4llm import to_markdown
from tldextract import extract


class Website:
    def __init__(
        self,
        url: str,
        title: str = "",
        snippet: str = "",
        html: str = "",
        markdown: str = "",
        load_content: bool = False,
    ):
        self.url = url
        self.title = title
        self.snippet = snippet
        self.domain = Website.extract_domain(url)
        self.raw_content: Optional[str] = None
        self.is_pdf = False
        self.raw_content = html
        self.markdown = markdown
        self.lock = Lock()

        if load_content:
            self.load_content()

    @property
    def content(self) -> str:
        if not self.raw_content:
            self.load_content()
        return self.get_markdown()

    def get_title(self) -> str:
        if self.title:
            return self.title

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
    def extract_domain(cls, url: str) -> str:
        parsed_url = extract(url)
        return f"{parsed_url.domain}." f"{parsed_url.suffix}"

    def load_content(self):
        loader = None
        with self.__domain_loader_lock:
            if self.domain in self.__domain_loaders:
                loader = self.__domain_loaders[self.domain]
            elif "*" in self.__domain_loaders:
                loader = self.__domain_loaders["*"]
            elif "all" in self.__domain_loaders:
                loader = self.__domain_loaders["all"]

        if not loader:
            Website.load(self)
        else:
            loader(self)

    @classmethod
    def load(cls, website: Website):
        with website.lock:

            session = requests.Session()
            session.headers.update(cls.headers)
            response = session.get(website.url, stream=True)
            response.raise_for_status()

            content_type = response.headers.get("Content-Type", "").lower()
            if "application/pdf" in content_type or (
                website.url.lower().endswith(".pdf")
            ):
                website.is_pdf = True
                temp_file = None
                try:
                    temp_file = tempfile.NamedTemporaryFile(
                        delete=False, suffix=".pdf"
                    )
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            temp_file.write(chunk)
                    temp_file.close()

                    website.raw_content = to_markdown(
                        temp_file.name, show_progress=False
                    )
                    website.markdown = website.raw_content
                finally:
                    if temp_file:
                        try:
                            os.unlink(temp_file.name)
                        except Exception:
                            pass
            else:
                if "Content-Encoding" in response.headers:
                    if response.headers["Content-Encoding"] == "gzip":
                        website.raw_content = response.content.decode(
                            "utf-8", errors="replace"
                        )
                else:
                    website.raw_content = response.text

                # Load the title from the title if it is not set
                website.get_title()

    def get_body(self):
        if not self.raw_content:
            self.load_content()
        soup = BeautifulSoup(self.raw_content, "html.parser")
        return soup.body

    def get_markdown(self):
        if self.markdown:
            return self.markdown

        if not self.raw_content:
            self.load_content()

        if self.is_pdf:
            return self.raw_content

        soup = BeautifulSoup(self.raw_content, "html.parser")
        markdown = md(soup.body.get_text())
        markdown = re.sub(r"\n+", "\n", markdown)
        self.markdown = markdown
        return markdown

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

    __domain_loaders: Dict[str, Callable[[Website], None]] = {}
    __domain_loader_lock = Lock()

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; "
        "x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip",
        "Connection": "keep-alive",
    }

    @classmethod
    def add_custom_domain_loader(
        cls, domain: str, func: Callable[[Website], None]
    ):
        with cls.__domain_loader_lock:
            cls.__domain_loaders[domain] = func
