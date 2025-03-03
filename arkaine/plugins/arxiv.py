import os
import re
import tempfile

from pymupdf4llm import to_markdown

from arkaine.utils.website import Website


def register_arxiv_plugin():
    # Ensure that we have the necessary imports
    try:
        import arxiv  # noqa: F401
    except ImportError:
        raise ImportError("Arxiv plugin requires arxiv package version 2.1.3")

    Website.add_custom_domain_loader("arxiv.org", load_arxiv_content)


def load_arxiv_content(website: Website):
    # Isolate paper code from the website url, such as
    # https://arxiv.org/abs/1706.03762 -> 1706.03762
    paper_code = None
    if len(website.url.split("/")) > 1:
        paper_code = website.url.split("/")[-1]
        # Remove any extraneous tracking or query parameters
        paper_code = paper_code.split("?")[0]

        # Ensure that the code is actually a valid arXiv identifier
        # Papers from 2007 to 2015 used one style, and a new style
        # thereafter. Ensure that our code fits one of these.
        # Pattern for new-style identifiers (YYMM.NNNNN or YYMM.NNNN)
        new_pattern = r"^(\d{4}\.\d{4,5})(v\d+)?$"
        # Pattern for old-style identifiers (archive/YYMMNNN)
        old_pattern = r"^([a-z-]+(?:\.[A-Z]{2})?\/\d{7})(v\d+)?$"

        if not (
            re.match(new_pattern, paper_code)
            or re.match(old_pattern, paper_code)
        ):
            paper_code = None

    # If we don't have the paper code here, we need to just load the
    # page normally.
    if not paper_code:
        Website.load(website)

    else:
        try:
            markdown = load_arvix_pdf(paper_code)

            website.raw_content = markdown
            website.markdown = markdown
        except Exception:  # noqa: B902
            # Fall back to loading the page normally
            Website.load(website)


def load_arvix_pdf(paper_code: str):
    import arxiv

    paper = next(arxiv.Client().results(arxiv.Search(id_list=[paper_code])))

    with tempfile.TemporaryDirectory() as temp_dir:
        pdf_path = os.path.join(temp_dir, f"{paper_code}.pdf")
        paper.download_pdf(filename=str(pdf_path))

        markdown = to_markdown(pdf_path, show_progress=False)

        return markdown
