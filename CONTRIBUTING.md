# Contributing to YouTube Auto Intro

Thank you for your interest in contributing! This document provides guidelines for contributing to this project.

## Getting Started

1. Fork the repository
2. Clone your fork locally
3. Create a virtual environment and install dependencies:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   pip install -e .
   ```

## Development Setup

1. Copy `.env.example` to `.env` and configure
2. Set up Google OAuth credentials for testing
3. Add a test intro video

## Code Style

- Follow PEP 8 guidelines
- Use meaningful variable and function names
- Add docstrings to all functions
- Keep functions focused and single-purpose

## Making Changes

1. Create a new branch for your feature:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Make your changes with clear, descriptive commits

3. Test your changes thoroughly

4. Update documentation if needed

## Pull Request Process

1. Ensure your code follows the project style
2. Update the README.md if you've added new features
3. Test all functionality before submitting
4. Create a pull request with a clear description

## Reporting Issues

When reporting issues, please include:
- Python version
- Operating system
- Steps to reproduce
- Expected vs actual behavior
- Any error messages

## Feature Requests

Feature requests are welcome! Please:
- Check if the feature already exists
- Describe the use case
- Explain how it would benefit users

## Questions?

Feel free to open an issue for any questions about contributing.
