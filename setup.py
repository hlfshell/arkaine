from setuptools import find_packages, setup

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="arkaine",
    version="0.0.1",  # Follow semantic versioning
    author="Keith Chester",
    author_email="k@hlfshell.ai",
    description="A batteries-included framework for DIY AI agents",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/hlfshell/arkaine",
    packages=find_packages(),
    install_requires=[],
    extras_require={
        "dev": [
            "pytest",
        ],
        "sms": [
            "twilio",
            "boto3",
            "messagebird",
            "vonage",
        ],
    },
    python_requires=">=3.8",  # Specify minimum Python version
    author="Keith Chester",
    author_email="kchester@gmail.com",
    description="",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/hlfshell/arkaine",
    license="MIT",
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
)
