import os
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional, Union

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


class MarkerLocalOCR(OCR):

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
                "for arkaine. To install, run marker-pdf[full]==1.6.1"
            )

        config_parser = ConfigParser(
            {
                "output_format": self.render_to,
                "use_llm": True,
                "gemini_api_key": api_key,
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

    def __normalize_text(self, text: str) -> str:
        # Replace newlines and asterisks, collapse multiple spaces, and
        # lower-case the text.
        normalized = text.replace("\n", " ").replace("*", "")
        normalized = " ".join(normalized.split())
        return normalized.lower().strip()

    def __add_page_numbers_to_headers(self, text: str, toc: List[Dict]) -> str:
        """
        Add page numbers to headers/titles throughout the text so that we can
        reference back to the original document's source. For both markdown and
        HTML, we append an inline comment to the header line indicating the
        page number.

        It is expected that the table of contents will be passed in,
        structured as a list of dictionaries. Each dictionary should include,
        at a minimum, a "title" and a "page_id". An illustrative example is
        provided below:

        [
            {
                "title": "THE STRANGE CASE\nOF DOCTOR JEKYLL\nAND MR. HYDE",
                "page_id": 0,
                ...
            },
            {
                "title": "Robert Louis Stevenson",
                "page_id": 0,
                ...
            },
            ...
        ]
        """
        lines = text.split("\n")
        header_line_indexes = []
        header_texts = []

        # Loop through the lines and record the index and content of header
        # lines.
        for i, line in enumerate(lines):
            stripped_line = line.strip()
            header_text = None
            if self.render_to == "markdown" and stripped_line.startswith("#"):
                # Remove leading '#' characters for markdown headers.
                header_text = stripped_line.lstrip("#").strip()
            elif self.render_to == "html" and (
                any(stripped_line.startswith(f"<h{j}>") for j in range(1, 7))
                or stripped_line.startswith("<title>")
            ):
                for tag_name in ["h1", "h2", "h3", "h4", "h5", "h6", "title"]:
                    opening_tag = f"<{tag_name}>"
                    closing_tag = f"</{tag_name}>"
                    if (
                        stripped_line.startswith(opening_tag)
                        and closing_tag in stripped_line
                    ):
                        header_text = stripped_line[
                            len(opening_tag) : stripped_line.find(closing_tag)
                        ].strip()
                        break
            if header_text:
                header_line_indexes.append(i)
                header_texts.append(header_text)

        # Use the metadata to append the page number comment on matching
        # headers.
        modified_lines = list(lines)

        for entry in toc:
            toc_title = entry.get("title", "")
            page_id = entry.get("page_id")
            if not toc_title or page_id is None:
                continue

            norm_toc_title = self.__normalize_text(toc_title)

            for idx, header in enumerate(header_texts):
                norm_header = self.__normalize_text(header)
                # Check for a match using containment after normalization.
                if (
                    norm_toc_title in norm_header
                    or norm_header in norm_toc_title
                ):
                    line_index = header_line_indexes[idx]
                    original_line = modified_lines[line_index]
                    # Use regex to check if a page comment is already appended.
                    if not re.search(
                        r"<!--\s*Page:\s*\d+\s*-->", original_line
                    ):
                        comment = f" <!-- Page: {page_id} -->"
                        modified_lines[line_index] = f"{original_line}{comment}"
                    break  # Only modify the first matching header for this toc entry.

        return "\n".join(modified_lines)

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

    def extract(self, filepath: str) -> Document:
        """
        Extracts a document from the given filepath by processing the PDF,
        converting images to text if enabled, and appending page numbers
        to headers. It then uses available metadata (or supplements missing
        data via an LLM based on the table of contents) to populate a Document.
        Returns a Document instance populated with the content and metadata.
        """
        response = self.__converter(filepath)

        if self.render_to == "markdown":
            text = response.markdown
        elif self.render_to == "html":
            text = response.html

        # Save the images to disk.
        for key, image in response.images.items():
            # image is a PIL Image object
            image.save(key)

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

        # Add page numbers to headers so that we can reference back to the
        # original document's source.
        text = self.__add_page_numbers_to_headers(
            text, metadata["table_of_contents"]
        )

        # Extract additional metadata (such as title and author).
        doc_metadata = self._extract_additional_metadata(text)

        raise "dead"

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
