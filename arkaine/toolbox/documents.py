from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, as_completed
import json
import os
import re
from abc import ABC, abstractmethod
from pathlib import Path
import tempfile
from typing import Dict, List, Optional, Tuple, Union

import google.generativeai as genai
from PIL import Image as PILImage
from uuid import uuid4


class Document:
    """
    Document tracks information about a document and its location. All documents
    are stored in a directory. The file structure is always:

    <dir_path>/
        - document.ext      # where ext is pdf, doc, epub, etc
        - content           # markdown version of the original
        - *.jpg             # images extracted from the document
        - metadata.json     # This object as a json file for reloading.


    Document has the following fields accessible:

    - id: The unique identifier for the document.

    - location: The path to the directory containing the document, as described
        above

    - content: The markdown content of the document. This actually loads
        the content on request, and is not held in memory.

    - authors: The author(s) of the document in a list

    - title: The title of the document

    - description: The description of the document

    - file_type: The extension/filetype of the document - derived if not
        specified. To be used for readers to know what kind of raw data they
        may be handling.

    - category: The category of the document, ie "research paper", "legal
        document", "textbook", etc.

    - tags: The tags of the document. These are N user defined keywords for
        possible organization/filtering of the document

    - images: [Image] - a list of Image objects associated with the document

    - document: The raw data of the document in question. Loaded on request,
        not held in memory.

    - filepath: The path to the document's data

    - directory: The directory where all data, the original document, images,
        and metadata are stored.
    """

    def __init__(
        self,
        library_dir: str,
        id: str,
    ):
        self.__id = id
        # Ensure the directory for the document exists
        dir = os.path.join(library_dir, self.__id)
        if not os.path.exists(dir):
            raise ValueError("Document not found")

        self.__location = dir

        # Extract the filename from the location provided
        # IF it exists - it will be document.EXT
        # List all files and see if we have a document.EXT
        files = os.listdir(self.__location)
        # Starts with document?
        if any(file.startswith("document") for file in files):
            for file in files:
                if file.startswith("document"):
                    try:
                        self.file_type = os.path.splitext(file)[1]
                        break
                    except Exception:
                        self.file_type = ""
                        break
        else:
            raise ValueError("Document not found")

        # Load the metadata.json which contains all of the other
        # information
        metadata_path = os.path.join(self.__location, "metadata.json")
        if not os.path.exists(metadata_path):
            raise ValueError("Metadata not found")

        with open(metadata_path, "r") as f:
            metadata = json.load(f)

        self.authors = metadata["authors"]
        self.title = metadata["title"]
        self.description = metadata["description"]
        self.category = metadata["category"]
        self.tags = metadata["tags"]

        image_data = metadata["images"]
        # Each image has a dict of the following form:
        # {
        #     "path": str,
        #     "description": str,
        #     "page_number": int,
        #     "id": str,
        # }
        self.images = [
            Image(
                os.path.join(self.__location, image_data[key]["path"]),
                image_data[key]["description"],
                image_data[key]["page_number"],
                image_data[key]["id"],
            )
            for key in image_data
        ]

    @property
    def id(self):
        return self.__id

    @property
    def content(self):
        with open(os.path.join(self.location, "content"), "r") as f:
            return f.read()

    @property
    def filepath(self):
        return os.path.join(self.location, f"original.{self.file_type}")

    @property
    def directory(self):
        return self.__location

    @property
    def document(self):
        with open(self.filepath, "rb") as f:
            return f.read()

    @classmethod
    def from_content(
        self,
        library_dir: str,
        filepath: str,
        content: str,
        title: str,
        description: str,
        category: Optional[str] = None,
        authors: List[str] = [],
        tags: List[str] = [],
        id: Optional[str] = None,
    ) -> Document:
        if id is None:
            id = str(uuid4())

        if id not in os.listdir(library_dir):
            os.makedirs(os.path.join(library_dir, id))


class Image:
    def __init__(
        self,
        path: Union[str, Path],
        description: str,
        document: Union[Document, str],
        page_number: Optional[int] = None,
        id: Optional[str] = None,
    ):
        self.id = id or str(uuid4())
        self.path = path if isinstance(path, str) else str(path)
        self.description = description
        self.document = document if isinstance(document, str) else document.id
        self.page_number = page_number

    def __str__(self):
        return self.path

    def load(self) -> PILImage:
        return PILImage.open(self.path)


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

    def import_from_file(
        self,
        filepath: str,
        pages: Optional[List[Union[int, Tuple[int, int]]]] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
        category: Optional[str] = None,
        authors: Optional[List[str]] = None,
        tags: List[str] = [],
        ocr: Optional[OCR] = None,
        id: Optional[str] = None,
    ) -> Document:
        """
        Imports a document from the given filepath. If ocr is provided, the
        document will be extracted using the ocr tool. If not, it will check
        to see if a .ocr attribute is present on the implementing class. If
        not, it will raise an error, otherwise it will utilize that tool.

        Returns a document object, with images attached (if OCR could handle
        it).
        """
        if ocr is None:
            raise ValueError(
                "No OCR tool provided or available on "
                f"{self.__class__.__name__}"
            )

        text, images, metadata = ocr.extract(filepath, pages)

        document = Document(
            library_dir="",
            title=title if title else metadata["title"],
            description=description if description else metadata["description"],
            category=category if category else metadata["category"],
            authors=authors if authors else metadata["authors"],
            id=id if id else None,
            content=text,
            tags=tags,
        )
        document.save()
        for image in images:
            document.attach_image(image)

        return document


class OCR(ABC):

    def __init__(self):
        super().__init__()

    @abstractmethod
    def extract(
        self,
        filepath: str,
        pages: Optional[List[Union[int, Tuple[int, int]]]] = None,
    ) -> Tuple[str, List[Image], Dict[str, str]]:
        """
        Extracts a document from the given filepath by processing it, pulling
        out the text and images, and returning them as a tuple of text, images,
        and metadata. metadata is a dict of:

        {
            "title": str,
            "authors": List[str],
            "category": str,
        }

        Args:
            filepath: The path to the PDF file to extract
            pages: The pages to extract from the PDF
        """
        pass


class MarkerOCR(OCR):
    """
    MarkerOCR is an OCR tool that converts PDF files to markdown or HTML
    utilizing Marker (https://github.com/VikParuchuri/marker).

    It requires the use of a Google API key that has access to their generative
    AI models. Otherwise it runs locally, using GPU acceleration if available.

    MarkerOCR requires two additional dependencies:

    - marker-pdf[full]==1.6.1
    - pypdf==5.3.1
    """

    def __init__(
        self,
        render_to: str = "markdown",
        api_key: Optional[str] = None,
        convert_images_to_text: bool = True,
        max_image_transcribe_workers: int = 10,
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

        self.__image_transcribe_workers = max_image_transcribe_workers
        self.__image_transcribe_threadpool = ThreadPoolExecutor(
            max_workers=self.__image_transcribe_workers
        )

        self.__converter = PdfConverter(
            config=config_parser.generate_config_dict(),
            artifact_dict=create_model_dict(),
            processor_list=config_parser.get_processors(),
            renderer=config_parser.get_renderer(),
            llm_service=config_parser.get_llm_service(),
        )

    def __images_to_text(
        self,
        images: List[PILImage.Image],
    ) -> List[str]:
        descriptions: List[str] = []

        futures: List[Future] = []
        for image in images:
            futures.append(
                self.__image_transcribe_threadpool.submit(
                    self.__google_model.generate_content,
                    [
                        "You are an OCR agent. You will transcribe this "
                        "image (if there is text), then describe it in "
                        "detail. If it is an equation, write it in latex. "
                        "If it is a table, write it in markdown",
                        image,
                    ],
                )
            )

        for future in as_completed(futures):
            try:
                response = future.result()
                description = response.text
                descriptions.append(description)
            except Exception as e:
                print(f"Error transcribing image: {e}")
                descriptions.append("")

        return descriptions

    def __add_image_description_to_tags(
        self, text: str, images: List[str], descriptions: List[str]
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

        We are also going to use this opportunity to rename the images to
        "00000#.jpeg" or equivalent for the image number, since the default
        names refer to incorrect pages.
        """
        for index, key in enumerate(images):
            # Generate the new image name
            # Isolate the extension of the image
            extension = os.path.splitext(key)[1]
            new_name = f"{index:06d}.{extension}"

            description = descriptions[index]

            if self.render_to == "markdown":
                # Ensure the body text is stripped of new lines and any
                # symbols that could break the markdown parser
                input = (
                    description.replace("\n", " ")
                    .replace("[", "\\[")
                    .replace("]", "\\]")
                    .replace('"', '\\"')
                )
                text = text.replace(f"![]({key})", f"![{input}]({new_name})")
            elif self.render_to == "html":
                input = description.replace("\n", " ").replace('"', '\\"')
                text = text.replace(
                    f"<img src={key}>", f"<img src={new_name} alt={input}>"
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
        self,
        filepath: str,
        pages: Optional[List[Union[int, Tuple[int, int]]]] = None,
    ) -> Tuple[str, List[Image], Dict[str, str]]:
        """
        Extracts a document from the given filepath by processing the PDF,
        converting images to text if enabled, and appending page numbers
        to headers. It then uses available metadata (or supplements missing
        data via an LLM based on the table of contents) to populate a Document.

        Args:
            filepath: The path to the PDF file to extract

            pages: The pages to extract from the PDF

            id: The id of the generated document. If not provided, a uuid will
                be generated

        Returns:
            text: The text of the document
            images: A list of PIL Image objects from the document in order of
                appearance/id
            metadata: The metadata of the document, consisting of llm
                generated title, authors, and category
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

        if self.__convert_images_to_text:
            image_explanations: List[str] = self.__images_to_text(
                response.images.values()
            )

            text = self.__add_image_description_to_tags(
                text, response.images.keys(), image_explanations
            )

        # Extract additional metadata (such as title and author).
        # Since this is based off of the start of the document, we need
        # to make sure we have it. Thus if we have pages specified, and it
        # doesn't include the first page, we need to add it.
        if pages is not None and 1 not in pages:
            with tempfile.TemporaryDirectory() as temp_dir:
                # Get the length of the document
                reader = self.__pdf_reader(filepath)
                total_pages = len(reader.pages)
                modified_file = self.__limit_to_pages(
                    filepath,
                    temp_dir,
                    [(1, min(3, total_pages + 1))],
                )
                response = self.__converter(modified_file)
                beginning_text = response.markdown
                doc_metadata = self._extract_additional_metadata(beginning_text)
        else:
            doc_metadata = self._extract_additional_metadata(text)

        return text, response.images.values(), doc_metadata
