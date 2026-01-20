"""
Pytest configuration and shared fixtures.

This module provides fixtures for:
- Mocking database connections
- Mocking AI providers
- Mocking Telegram services
- FastAPI test client
"""

import os
import sys
import asyncio
from typing import AsyncGenerator, Dict, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

# Set testing environment before importing app modules
import os
os.environ["TESTING"] = "true"
os.environ["LOG_LEVEL"] = "ERROR"
os.environ["API_ENABLED"] = "true"
os.environ["API_KEYS"] = "testkey:1"


# ─────────────────────────────────────────────────────────────────────────────
# Database Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_db():
    """Mock database connection that returns empty results."""
    mock = MagicMock()
    mock.fetch = AsyncMock(return_value=[])
    mock.fetchrow = AsyncMock(return_value=None)
    mock.fetchval = AsyncMock(return_value=None)
    mock.execute = AsyncMock(return_value="INSERT 0 1")
    mock.executemany = AsyncMock(return_value=None)
    return mock


@pytest.fixture
def mock_db_with_data():
    """Mock database that can be configured with test data."""
    class MockDB:
        def __init__(self):
            self.data: Dict[str, list] = {}
            
        def set_data(self, table: str, rows: list):
            self.data[table] = rows
            
        async def fetch(self, query: str, *args):
            # Simple mock - return data based on table name in query
            for table, rows in self.data.items():
                if table in query.lower():
                    return rows
            return []
            
        async def fetchrow(self, query: str, *args):
            rows = await self.fetch(query, *args)
            return rows[0] if rows else None
            
        async def fetchval(self, query: str, *args):
            row = await self.fetchrow(query, *args)
            return list(row.values())[0] if row else None
            
        async def execute(self, query: str, *args):
            return "INSERT 0 1"
            
        async def executemany(self, query: str, args_list):
            return None
    
    return MockDB()


# ─────────────────────────────────────────────────────────────────────────────
# AI Provider Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_ai_response():
    """Standard mock AI response."""
    return {
        "content": "This is a mock AI response for testing.",
        "thinking": None,
        "model": "test-model",
    }


@pytest.fixture
def mock_ai_provider(mock_ai_response):
    """Mock AI provider that returns predictable responses."""
    provider = MagicMock()
    provider.name = "mock"
    provider.is_configured = MagicMock(return_value=True)
    provider.chat = AsyncMock(return_value=mock_ai_response)
    provider.list_models = AsyncMock(return_value=["test-model-1", "test-model-2"])
    return provider


@pytest.fixture
def mock_ai_service(mock_ai_provider):
    """Mock AI service with a configured provider."""
    with patch("app.services.ai.service.ai_service") as mock_service:
        mock_service.active_provider = mock_ai_provider
        mock_service.is_available = MagicMock(return_value=True)
        mock_service.list_providers = MagicMock(return_value=[
            {"key": "mock", "name": "Mock Provider", "configured": True}
        ])
        mock_service.get_models = AsyncMock(return_value=["test-model-1", "test-model-2"])
        mock_service.generate_response = AsyncMock(return_value="Mock response")
        mock_service.summarize = AsyncMock(return_value="Mock summary")
        yield mock_service


# ─────────────────────────────────────────────────────────────────────────────
# Telegram Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_telegram_service():
    """Mock Telegram service."""
    with patch("app.core.bot.telegram_service") as mock:
        mock.connected = True
        mock.client = MagicMock()
        mock.send_message = AsyncMock(return_value=MagicMock(id=12345))
        yield mock


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI Test Client
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
async def app():
    """Create FastAPI app for testing."""
    # Import here to ensure env vars are set first
    from app.main import app as fastapi_app
    return fastapi_app


@pytest.fixture
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client for testing API endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def auth_headers():
    """Authentication headers for API requests."""
    return {"X-API-Key": "testkey"}


# ─────────────────────────────────────────────────────────────────────────────
# WebApp Auth Fixtures (for Chart/Watchlist endpoints)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
async def webapp_client(app) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client with webapp auth overridden for testing."""
    from app.api.auth import verify_webapp, verify_webapp_optional
    
    # Override dependencies to return mock user ID
    async def mock_verify_webapp():
        return 12345
    
    async def mock_verify_webapp_optional():
        return 12345
    
    app.dependency_overrides[verify_webapp] = mock_verify_webapp
    app.dependency_overrides[verify_webapp_optional] = mock_verify_webapp_optional
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    
    # Cleanup
    app.dependency_overrides.clear()


# ─────────────────────────────────────────────────────────────────────────────
# Helper Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_messages():
    """Sample messages for testing message processing."""
    return [
        {"id": 1, "text": "BTC突破10万美元，创历史新高！", "sender": "user1"},
        {"id": 2, "text": "今天大盘涨停，沪指突破4000点", "sender": "user2"},
        {"id": 3, "text": "This is a test message without market keywords", "sender": "user3"},
        {"id": 4, "text": "ETH/USD看涨，建议持有", "sender": "user4"},
    ]


@pytest.fixture
def sample_rss_feed():
    """Sample RSS feed data."""
    return {
        "title": "Test Blog",
        "link": "https://example.com",
        "entries": [
            {"title": "Post 1", "link": "https://example.com/1", "summary": "Summary 1"},
            {"title": "Post 2", "link": "https://example.com/2", "summary": "Summary 2"},
        ]
    }
