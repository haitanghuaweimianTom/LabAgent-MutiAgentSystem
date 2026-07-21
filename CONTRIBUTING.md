# Contributing to LabAgent

Thank you for your interest in contributing to LabAgent! This document provides guidelines and information for contributors.

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 20+
- Git

### Development Setup

1. Fork and clone the repository:
   ```bash
   git clone https://github.com/your-username/LabAgent-MutiAgentSystem.git
   cd LabAgent-MutiAgentSystem
   ```

2. Set up the backend:
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # or
   venv\Scripts\activate  # Windows
   pip install -r requirements.txt
   ```

3. Set up the frontend:
   ```bash
   cd frontend
   npm install
   ```

4. Configure environment:
   ```bash
   cp .env.example backend/.env
   # Edit backend/.env with your API keys
   ```

## Development Workflow

### Code Style

- **Python**: Follow PEP 8, use type hints, run `ruff check` and `ruff format`
- **TypeScript**: Follow ESLint rules, use Prettier for formatting

### Testing

- Backend: `cd backend && python -m pytest tests/ -v`
- Frontend: `cd frontend && npm test`

### Commit Messages

Use conventional commits:
- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation changes
- `style:` Code style changes (formatting, etc.)
- `refactor:` Code refactoring
- `test:` Adding or updating tests
- `chore:` Maintenance tasks

Example:
```
feat: add new agent for data analysis
fix: resolve issue with task persistence
docs: update API documentation
```

### Pull Request Process

1. Create a feature branch from `main`
2. Make your changes
3. Run tests and linting
4. Commit with clear, descriptive messages
5. Push to your fork and create a pull request
6. Fill out the PR template
7. Wait for review and address feedback

## Reporting Issues

- Use GitHub Issues
- Include steps to reproduce
- Include expected vs actual behavior
- Include environment details (OS, Python version, etc.)

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
