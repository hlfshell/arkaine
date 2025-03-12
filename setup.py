import os

from setuptools import find_packages, setup


def _local_path(filename: str) -> str:
    return os.path.join(os.path.dirname(__file__), filename)


# Hardcode all dependencies to ensure they're included in the wheel
install_requires = [
    # Core LLM dependencies
    "anthropic==0.49.0",
    "groq==0.18.0",
    "openai==1.61.0",
    "google-generativeai==0.8.4",
    "ollama==0.4.7",
    # Web/API dependencies
    "fastapi==0.115.8",
    "uvicorn==0.34.0",
    "websockets==14.1",
    "Requests==2.32.3",
    "tldextract==5.1.3",
    # Code execution
    "docker==7.1.0",
    # Data processing
    "numpy==2.2.2",
    "scikit_learn==1.6.1",
    "beautifulsoup4==4.13.1",
    "markdownify==0.13.1",
    "pydantic==2.10.6",
    "PyJWT==2.10.1",
    # Utilities
    "click==8.1.8",
    "feedparser==6.0.11",
    "parsedatetime==2.6",
    "pytz==2024.2",
    "typing_extensions==4.12.2",
    "pymupdf4llm==0.0.17",
    "wikipedia==1.4.0",
    "googlemaps==4.10.0",
    "setuptools==75.8.0",
]


with open(_local_path("README.md"), "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="arkaine",
    version="0.0.17",
    author="Keith Chester",
    author_email="keith@hlfshell.ai",
    description="A batteries-included framework for DIY AI agents",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/hlfshell/arkaine",
    packages=find_packages(),
    install_requires=install_requires,
    extras_require={
        "dev": [
            "pytest",
            "responses",
        ],
    },
    python_requires=">=3.8",
    license="MIT",
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
    entry_points={
        "console_scripts": [
            "spellbook=arkaine.spellbook.server:main",
        ],
    },
)
