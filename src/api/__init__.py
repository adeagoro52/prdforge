"""PRDForge Web API.

This module provides:
- REST API endpoints for the dashboard
- WebSocket support for real-time updates
- HTMX-powered templates for the dashboard UI

The API is built with FastAPI and uses Jinja2 templates
with HTMX for dynamic updates without a full SPA.
"""

from .main import create_app

__all__ = ["create_app"]
