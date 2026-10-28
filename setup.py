# -*- coding: utf-8 -*-
from setuptools import setup, find_packages

setup(
    name="banano2live",
    version="1.0.0",
    author="Mag1cFall",
    author_email="lk25611295@gmail.com",
    description="All-in-One AI Video & Sprite Grid to Live Photo (Google Motion Photo .jpg & Apple Live Photo .zip) Engine - Pure Web & HrioAPI SDK",
    long_description=open("README.md", encoding="utf-8").read() if __import__("os").path.exists("README.md") else "",
    long_description_content_type="text/markdown",
    url="https://github.com/Mag1cFall/banano2live",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
    install_requires=[
        "Pillow>=10.0.0",
        "numpy>=1.24.0",
        "imageio>=2.30.0",
        "imageio-ffmpeg>=0.4.8",
    ],
    entry_points={
        "console_scripts": [
            "banano2live=banano2live.cli:main",
        ],
    },
)
