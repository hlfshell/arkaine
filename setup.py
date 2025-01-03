from setuptools import find_packages, setup

setup(
    name="arkaine",
    version="0.1",
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
