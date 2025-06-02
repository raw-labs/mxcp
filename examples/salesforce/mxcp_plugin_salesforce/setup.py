from setuptools import setup, find_packages

setup(
    name="mxcp-plugin-salesforce",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "mxcp>=0.1.0",
        "simple-salesforce>=1.12.5",
    ],
    author="RAW Labs",
    author_email="hello@raw-labs.com",
    description="MXCP plugin for Salesforce integration",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/raw-labs/mxcp",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Business Source License 1.1",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.9",
) 