from setuptools import find_packages, setup

setup(
    name="composable-agents",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        "openai",  # For OpenAI backend
        "numpy",  # Likely needed for embeddings/vectors
        "requests",  # For API calls
        "beautifulsoup4",  # For web scraping
        "markdownify",  # For HTML to markdown conversion
        "groq",  # For Groq LLM integration
        "ollama",  # For Ollama LLM integration
        "bs4",  # BeautifulSoup alias used in some imports
        "pydantic",  # For data validation (if using OpenAI's latest client)
    ],
    extras_require={
        "dev": [
            "pytest",
        ],
    },
    python_requires=">=3.8",  # Specify minimum Python version
    author="Keith Chester",
    author_email="your.email@example.com",
    description="A framework for composable LLM agents",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/composable-agents",
    license="MIT",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
)
