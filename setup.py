#!/usr/bin/env python3
"""
Setup script for PersonaGym-R production deployment
"""
from setuptools import setup, find_packages

setup(
    name="personagym_r",
    version="0.1.0",
    description="PersonaGym-R: Adversarial persona adherence benchmark",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.11",
    install_requires=[
        "pydantic>=2.7",
        "typer>=0.12", 
        "rich>=13.7",
        "numpy>=1.26",
        "scikit-learn>=1.5",
    ],
)