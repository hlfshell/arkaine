import os
import re
from abc import ABC, abstractmethod
from pathlib import Path
import tempfile
from typing import Dict, List, Optional, Tuple, Union

import google.generativeai as genai
from PIL import Image


class Document(ABC):
    def __init__(self):
        super().__init__()

        self.id = None
        self.content = None
        self.source = None
        self.author = None
        self.title = None
        self.description = None
        self.type = None
        # Keyword tags ("research paper", "legal document", "textbook", "etc")
        self.tags = []
        self.__table_of_contents = None

    @property
    def content(self):
        """
        todo - if the content is not yet loaded, load it
        """
        pass


class DocumentStore(ABC):
    def __init__(self):
        super().__init__()

    @abstractmethod
    def save(self, document: Document):
        pass

    @abstractmethod
    def load(self, id: str) -> Document:
        pass

    def delete(self, id: str):
        pass

    # def search(self, query: Query) -> List[Document]:
    #     pass


class OCR(ABC):

    def __init__(self):
        super().__init__()

    @abstractmethod
    def extract(self, filepath: str) -> Document:
        pass


class MarkerOCR(OCR):

    def __init__(
        self,
        render_to: str = "markdown",
        api_key: Optional[str] = None,
        convert_images_to_text: bool = True,
        directory: Optional[str] = None,
    ):
        super().__init__()

        if api_key is None:
            api_key = os.getenv("GOOGLE_API_KEY")
        if api_key is None:
            api_key = os.getenv("GOOGLE_AISTUDIO_API_KEY")
        if api_key is None:
            raise ValueError(
                "API Key not set - either pass it in or set one of "
                "GOOGLE_API_KEY or GOOGLE_AISTUDIO_API_KEY"
            )

        self.__directory = directory

        self.__convert_images_to_text = convert_images_to_text
        if self.__convert_images_to_text:
            genai.configure(api_key=api_key)
            self.__google_model = genai.GenerativeModel("gemini-1.5-flash")

        self.render_to = render_to
        if self.render_to not in ["markdown", "html"]:
            raise ValueError("render_to must be one of: markdown, html")

        try:
            from marker.config.parser import ConfigParser
            from marker.converters.pdf import PdfConverter
            from marker.models import create_model_dict
        except ImportError:
            raise ImportError(
                "Marker is not installed - it is an optional dependency "
                "for arkaine and required when using the MarkerLocalOCR "
                "class. To install, run marker-pdf[full]==1.6.1"
            )

        try:
            from pypdf import PdfReader, PdfWriter

            self.__pdf_reader = PdfReader
            self.__pdf_writer = PdfWriter
        except ImportError:
            raise ImportError(
                "pypdf is not installed - it is an optional dependency "
                "for arkaine and required when using the MarkerLocalOCR "
                "class. To install, run pypdf==5.3.1"
            )

        config_parser = ConfigParser(
            {
                "output_format": self.render_to,
                "use_llm": True,
                "gemini_api_key": api_key,
                "paginate_output": True,
            }
        )

        self.__converter = PdfConverter(
            config=config_parser.generate_config_dict(),
            artifact_dict=create_model_dict(),
            processor_list=config_parser.get_processors(),
            renderer=config_parser.get_renderer(),
            llm_service=config_parser.get_llm_service(),
        )

    def __images_to_text(
        self, images: Union[str, Path, List[Union[str, Path]]]
    ) -> str:
        if isinstance(images, str):
            images = [images]
        elif isinstance(images, Path):
            images = [images]

        for image_path in images:
            response = self.__google_model.generate_content(
                [
                    "You are an OCR agent. You will transcribe this "
                    "image (if there is text), then describe it in "
                    "detail. If it is an equation, write it in latex. "
                    "If it is a table, write it in markdown",
                    Image.open(image_path),
                ]
            )

            # Extract and print the description
            description = response.text
            return description

    def __add_image_description_to_tags(
        self, text: str, images: Dict[str, str]
    ) -> str:
        """
        __image_tags_to_text takes a dict or image keys (filepaths) and block
        explanations of what the image contains. It then finds all instances of
        that image in the provided text, modifying that tag to include the
        explanation of the image to have the explainer text in optional tags.

        For markdown, this means:

        ![](some_image.jpeg)

        becomes

        ![Explanation: The image contains a picture of a frog in a
        hat](some_image.jpeg)

        For HTML, this means:

        <img src="some_image.jpeg">

        ...becomes:

        <img src="some_image.jpeg" alt="Explanation: The image contains a
        picture of a frog in a hat">

        The explanations can be *quite* long, so we strip out new lines since
        it's meant for LLM consumption. This can be disabled by turning off the
        images_to_text flag in the class init.
        """
        for key, body in images.items():
            if self.render_to == "markdown":
                # Ensure the body text is stripped of new lines and any
                # symbols that could break the markdown parser
                input = (
                    body.replace("\n", " ")
                    .replace("[", "\\[")
                    .replace("]", "\\]")
                    .replace('"', '\\"')
                )
                text = text.replace(f"![]({key})", f"![{input}]({key})")
            elif self.render_to == "html":
                input = body.replace("\n", " ").replace('"', '\\"')
                text = text.replace(
                    f"<img src={key}>", f"<img src={key} alt={input}>"
                )

        return text

    def _extract_additional_metadata(self, text: str) -> Dict:
        """
        Attempt to extract document metadata such as title and author. First,
        check if the supplied table_of_contents metadata contains these fields.
        If not, use the LLM (Google Gemini) to extract the information based
        on the document's table of contents metadata.
        """

        # Extract the first few pages of the document
        input = text[:1000]

        extracted = {}

        prompt = (
            "You are an expert in extracting document metadata. "
            "Based on the the first few pages of the provided document, "
            "please extract the "
            "document's title and author(s). If any information is "
            "missing, output 'unknown'. Also try attempt to identify "
            "what that category of the document is (e.g. 'research paper', "
            "'legal document', 'textbook', etc.).\n\n"
            "Document:\n"
            f"{input}\n\n"
            "Output in the following format:\n"
            "TITLE: <DOCUMENT TITLE>\n"
            "AUTHORS: <DOCUMENT AUTHOR(S) COMMA DELIMITED>\n"
            "CATEGORY: <DOCUMENT CATEGORY>\n"
        )
        # Use the LLM to extract metadata
        response = self.__google_model.generate_content([prompt])
        response_text = response.text

        # Parse the response for title and author.
        extracted_title = "unknown"
        extracted_authors = "unknown"
        extracted_category = "unknown"
        for line in response_text.splitlines():
            if line.strip().lower().startswith("title:"):
                extracted_title = line.split(":", 1)[1].strip()
            elif line.strip().lower().startswith("authors:"):
                extracted_authors = line.split(":", 1)[1].strip()
            elif line.strip().lower().startswith("author:"):
                extracted_authors = line.split(":", 1)[1].strip()
            elif line.strip().lower().startswith("category:"):
                extracted_category = line.split(":", 1)[1].strip()

        extracted_authors = extracted_authors.split(",")

        extracted = {
            "title": extracted_title,
            "authors": extracted_authors,
            "category": extracted_category,
        }

        return extracted

    def __limit_to_pages(
        self,
        filepath: str,
        target_dir: str,
        pages: List[Union[int, Tuple[int, int]]],
    ) -> str:
        """
        Given a target pdf and a list of pages, create a new pdf in the target
        directory (passing back the filepath for it) with only the pages
        specified.

        pages is a list of integers or tuples. If a single value is specified,
        that page is included on its own. If a tuple is specified, the first
        value is the start page and the second value is the end page, inclusive.
        A value of -1 specifies the end of the document, so (30, -1) would be
        from page 30 to the end of the document.

        The pages written are done *in the order specified*. This means that
        you can end up duplicating pages. If I have, for instance:

        __limit_to_pages(filepath, target_dir, [(1, 10), (5, 12)])

        ...would create a document of pages 1-10, then 5-12, IE 18 pages.

        Also note that page "0" doesn't exist, we are 1-indexed for the page
        count.

        If pages specified exceed the total number of pages in the document,
        an error will be raised.
        """
        reader = self.__pdf_reader(filepath)
        writer = self.__pdf_writer()

        total_pages = len(reader.pages)

        for page_spec in pages:
            if isinstance(page_spec, int):
                # Single page
                page_num = page_spec
                if page_num <= 0:
                    raise ValueError(
                        "Single page specification cannot be negative: "
                        f"{page_num}"
                    )
                if page_num >= total_pages:
                    raise ValueError(
                        "Page specification cannot exceed document length: "
                        f"{page_num}"
                    )
                writer.add_page(reader.pages[page_num - 1])
            else:
                # Page range (start, end)
                start, end = page_spec

                # Handle negative end value (meaning "to the end of document")
                if end < 0:
                    end = total_pages - 1

                # Validate page range
                if start <= 0:
                    raise ValueError(
                        f"Start page cannot be negative or zero: {start}"
                    )
                if start >= total_pages:
                    raise ValueError(
                        f"Start page {start} exceeds document length of "
                        f"{total_pages} pages"
                    )
                if end >= total_pages:
                    raise ValueError(
                        f"End page {end} exceeds document length of "
                        f"{total_pages} pages"
                    )
                if start > end:
                    raise ValueError(
                        f"Start page {start} cannot be greater than end page "
                        f"{end}"
                    )

                # Add all pages in the range (inclusive)
                for page_num in range(start, end + 1):
                    writer.add_page(reader.pages[page_num - 1])

        output_path = os.path.join(target_dir, "output.pdf")

        with open(output_path, "wb") as output_file:
            writer.write(output_file)

        return output_path

    def __map_page_numbers(
        self,
        filepath: str,
        pages: List[Union[int, Tuple[int, int]]],
    ) -> Dict[int, int]:
        """
        Creates a mapping from page numbers in the limited document to page
        numbers
        in the original document.

        For example, if we extract pages [5, (10, 12)] from the original
        document,
        the mapping would be:
        {
            0: 5,    # First page in limited doc is page 5 in original
            1: 10,   # Second page in limited doc is page 10 in original
            2: 11,   # Third page in limited doc is page 11 in original
            3: 12    # Fourth page in limited doc is page 12 in original
        }

        Note: The pages parameter uses 1-indexed page numbers (where page 1 is
        the first page), but the returned mapping uses 0-indexed values for both
        keys and values.

        Args:
            filepath: Path to the original PDF file
            pages: List of page specifications (integers or tuples) using
                1-indexed page numbers

        Returns:
            Dictionary mapping limited document page numbers (0-indexed) to
            original document page numbers (0-indexed)
        """
        reader = self.__pdf_reader(filepath)
        total_pages = len(reader.pages)

        # Create the mapping
        mapping = {}
        limited_page_idx = 0

        for page_spec in pages:
            if isinstance(page_spec, int):
                # Single page (convert from 1-indexed to 0-indexed)
                page_num = page_spec
                if 0 <= page_num < total_pages:
                    mapping[limited_page_idx] = page_num
                    limited_page_idx += 1
            else:
                # Page range (start, end) - convert from 1-indexed to 0-indexed
                start, end = page_spec

                # Handle negative end value (meaning "to the end of document")
                if end < 0:
                    end = total_pages - 1
                else:
                    end = end - 1  # Convert to 0-indexed

                # Ensure values are within bounds
                start = max(0, min(start, total_pages - 1))
                end = max(0, min(end, total_pages - 1))

                # Add all pages in the range (inclusive)
                if start <= end:
                    for page_num in range(start, end + 1):
                        mapping[limited_page_idx] = page_num
                        limited_page_idx += 1

        return mapping

    def __adjust_page_numbers(self, text: str, page_map: Dict[int, int]) -> str:
        """
        Throughout the text, marker has added page numbers in a comment
        fashion -

        For markdown, this looks like:
        {#}------------------------------------------------

        For HTML, this looks like:
        <div class="page" data-page-id="#">

        We replace those page numbers with the actual page numbers
        from the original document, on the line to be removed in the
        form of:
        <!-- PAGE NUMBER: # -->
        ...for both modes.
        """
        lines = text.split("\n")
        modified_lines = []
        if self.render_to == "markdown":
            pattern = r"^\{(\d+)\}-+$"
        elif self.render_to == "html":
            pattern = r'<div class="page" data-page-id="(\d+)">'

        for line in lines:
            # Check for markdown page marker
            match = re.match(pattern, line.strip())
            if match:
                current_page = int(match.group(1))
                if current_page in page_map:
                    original_page = page_map[current_page]
                    line = f"<!-- PAGE NUMBER: {original_page} -->"
            modified_lines.append(line)

        return "\n".join(modified_lines)

    def extract(
        self, filepath: str, pages: Optional[List[Union[int, Tuple]]] = None
    ) -> Document:
        """
        Extracts a document from the given filepath by processing the PDF,
        converting images to text if enabled, and appending page numbers
        to headers. It then uses available metadata (or supplements missing
        data via an LLM based on the table of contents) to populate a Document.
        Returns a Document instance populated with the content and metadata.
        """
        if pages is not None:
            with tempfile.TemporaryDirectory() as temp_dir:
                modified_file = self.__limit_to_pages(
                    filepath,
                    temp_dir,
                    pages,
                )
                response = self.__converter(modified_file)
                # Add page numbers to headers so that we can reference back to
                # the original document's source.
                page_map = self.__map_page_numbers(filepath, pages)
                if self.render_to == "markdown":
                    text = response.markdown
                elif self.render_to == "html":
                    text = response.html
                text = self.__adjust_page_numbers(text, page_map)
        else:
            response = self.__converter(filepath)

            if self.render_to == "markdown":
                text = response.markdown
            elif self.render_to == "html":
                text = response.html

        # Save the images to disk.
        # TODO adjust the image names as they refer to page numbers
        # that aren't quite right
        for key, image in response.images.items():
            # image is a PIL Image object
            image.save(os.path.join(self.__directory, key))

        if self.__convert_images_to_text:
            image_explanations: Dict[str, str] = {
                key: self.__images_to_text(
                    [os.path.join(self.__directory, key)]
                )
                for key in response.images.keys()
            }

            text = self.__add_image_description_to_tags(
                text, image_explanations
            )

        metadata = response.metadata

        # Extract additional metadata (such as title and author).
        doc_metadata = self._extract_additional_metadata(text)

        # Create and populate a Document instance.
        # doc = Document(
        #     title=doc_metadata.get("title", ""),
        #     authors=doc_metadata.get("authors", []),
        #     category=doc_metadata.get("category", ""),
        #     filepath=filepath,
        # )
        # doc.content = text
        # doc.title = doc_metadata.get("title")
        # doc.author = doc_metadata.get("author")
        # doc.source = filepath
        # # Set other fields (such as tags, type, etc.) as needed.

        # return doc
        return text, doc_metadata
