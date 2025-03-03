import os
import pytest
import responses
import tempfile
from unittest.mock import patch, MagicMock

from arkaine.utils.website import Website


@pytest.fixture
def reset_domain_loaders():
    """Reset the domain loaders before and after each test"""
    Website._Website__domain_loaders = {}
    yield
    Website._Website__domain_loaders = {}


@pytest.fixture
def mock_pdf_file():
    """Create a temporary PDF file for testing"""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_file:
        temp_file.write(b"%PDF-1.4\nTest PDF content")
        pdf_path = temp_file.name

    yield pdf_path

    # Clean up
    if os.path.exists(pdf_path):
        os.unlink(pdf_path)


def test_website_init():
    """Test basic Website initialization"""
    website = Website(
        url="https://example.com",
        title="Example Website",
        snippet="This is an example website",
        html="<html><body>Example content</body></html>",
        markdown="Example content",
    )

    assert website.url == "https://example.com"
    assert website.title == "Example Website"
    assert website.snippet == "This is an example website"
    assert website.domain == "example.com"
    assert website.raw_content == "<html><body>Example content</body></html>"
    assert website.markdown == "Example content"
    assert website.is_pdf is False


def test_extract_domain():
    """Test domain extraction from URLs"""
    assert Website.extract_domain("https://example.com") == "example.com"
    assert Website.extract_domain("http://www.example.com") == "example.com"
    assert Website.extract_domain("https://sub.example.com") == "example.com"
    assert Website.extract_domain("https://example.co.uk") == "example.co.uk"
    assert Website.extract_domain("https://example.com:8080") == "example.com"
    assert (
        Website.extract_domain("https://example.com?param=value")
        == "example.com"
    )
    assert (
        Website.extract_domain("https://sub1.sub2.sub3.example.com")
        == "example.com"
    )


@responses.activate
def test_load_html_content():
    """Test loading HTML content from a website"""
    url = "https://example.com"
    html_content = "<html><head><title>Test Title</title></head><body>Test content</body></html>"

    responses.add(
        responses.GET,
        url,
        body=html_content,
        status=200,
        content_type="text/html",
    )

    website = Website(url=url, load_content=True)

    assert website.raw_content == html_content
    assert website.title == "Test Title"
    assert "Test content" in website.get_markdown()
    assert website.is_pdf is False


@responses.activate
def test_load_pdf_content(mock_pdf_file):
    """Test loading PDF content from a website"""
    url = "https://example.com/document.pdf"

    with open(mock_pdf_file, "rb") as f:
        pdf_content = f.read()

    responses.add(
        responses.GET,
        url,
        body=pdf_content,
        status=200,
        content_type="application/pdf",
    )

    with patch(
        "arkaine.utils.website.to_markdown",
        return_value="PDF content in markdown",
    ):
        website = Website(url=url, load_content=True)

        assert website.is_pdf is True
        assert website.raw_content == "PDF content in markdown"
        assert website.get_markdown() == "PDF content in markdown"


def test_to_json_and_from_json():
    """Test serialization and deserialization of Website objects"""
    website = Website(
        url="https://example.com",
        title="Example Website",
        snippet="This is an example website",
        html="<html><body>Example content</body></html>",
    )

    json_data = website.to_json()
    restored_website = Website.from_json(json_data)

    assert restored_website.url == website.url
    assert restored_website.title == website.title
    assert restored_website.snippet == website.snippet
    assert restored_website.domain == website.domain


@pytest.mark.parametrize(
    "title_html,expected_title",
    [
        (
            "<html><head><title>Test Title</title></head><body></body></html>",
            "Test Title",
        ),
        ("<html><body><h1>H1 Title</h1></body></html>", "H1 Title"),
        ("<html><body></body></html>", "example.com"),
    ],
)
def test_get_title(title_html, expected_title):
    """Test title extraction from HTML content"""
    website = Website(url="https://example.com", html=title_html)
    assert website.get_title() == expected_title


@pytest.mark.usefixtures("reset_domain_loaders")
def test_custom_domain_loader():
    """Test adding and using a custom domain loader"""
    mock_loader = MagicMock()
    Website.add_custom_domain_loader("custom.com", mock_loader)

    website = Website(url="https://custom.com")
    website.load_content()

    mock_loader.assert_called_once_with(website)


@pytest.mark.usefixtures("reset_domain_loaders")
def test_fallback_to_default_loader():
    """Test fallback to default loader when no custom loader is available"""
    with patch("arkaine.utils.website.Website.load") as mock_default_loader:
        website = Website(url="https://example.com")
        website.load_content()

        mock_default_loader.assert_called_once_with(website)


@pytest.mark.usefixtures("reset_domain_loaders")
def test_wildcard_domain_loader():
    """Test wildcard domain loader that handles all domains"""
    mock_wildcard_loader = MagicMock()
    Website.add_custom_domain_loader("*", mock_wildcard_loader)

    website = Website(url="https://any-domain.com")
    website.load_content()

    mock_wildcard_loader.assert_called_once_with(website)
