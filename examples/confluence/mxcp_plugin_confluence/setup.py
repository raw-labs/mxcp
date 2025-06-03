from setuptools import setup, find_packages

setup(
    name="mxcp-plugin-confluence",
    version="0.1.0",
    packages=find_packages(include=["mxcp_plugin_confluence"]),
    install_requires=[
        "atlassian-python-api>=4.0.0",
    ],
    python_requires=">=3.8",
    author="MXCP Team",
    author_email="example@example.com",
    description="MXCP plugin for querying Atlassian Confluence using CQL",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
)
