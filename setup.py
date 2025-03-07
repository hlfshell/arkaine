from typing import List

from setuptools import find_packages, setup


def read_requirements(filename: str) -> List[str]:
    """Read requirements from file, cleaning up formatting."""
    with open(filename) as f:
        requirements = []
        for line in f:
            line = line.strip()
            # Skip empty lines, comments, and section headers
            if not line or line.startswith("#") or line.startswith("["):
                continue
            # Keep version specifiers to ensure reproducible builds
            requirements.append(line)
        return requirements


with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="arkaine",
    version="0.0.15",
    author="Keith Chester",
    author_email="keith@hlfshell.ai",
    description="A batteries-included framework for DIY AI agents",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/hlfshell/arkaine",
    packages=find_packages(),
    install_requires=read_requirements("requirements.txt"),
    extras_require={
        "dev": [
            "pytest",
            "responses",
        ],
    },
    python_requires=">=3.8",  # Specify minimum Python version
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
