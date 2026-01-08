"""
API endpoint tests for QuBot REST API.

Tests HTTP endpoints with mocked services.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock


class TestHealthEndpoint:
    """Test health check endpoint."""
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_health_returns_ok(self, client, auth_headers):
        """Health endpoint should return status ok."""
        with patch("app.api.routes.telegram_service") as mock_tg, \
             patch("app.api.routes.ai_service") as mock_ai, \
             patch("app.api.routes.monitor_service") as mock_mon:
            
            mock_tg.connected = True
            mock_ai.is_available = MagicMock(return_value=True)
            mock_mon.is_running = False
            
            response = await client.get("/api/health", headers=auth_headers)
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert "telegram" in data
            assert "ai_available" in data


class TestAuthMiddleware:
    """Test API authentication."""
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_missing_auth_rejected(self, client):
        """Request without auth header should be rejected."""
        response = await client.get("/api/ai/providers")
        assert response.status_code == 401
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_invalid_key_rejected(self, client):
        """Request with invalid API key should be rejected."""
        headers = {"Authorization": "Bearer invalid-key"}
        response = await client.get("/api/ai/providers", headers=headers)
        assert response.status_code == 401
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_valid_key_accepted(self, client, auth_headers):
        """Request with valid API key should be accepted."""
        with patch("app.api.routes.ai_service") as mock_ai:
            mock_ai.list_providers = MagicMock(return_value=[])
            
            response = await client.get("/api/ai/providers", headers=auth_headers)
            assert response.status_code == 200


class TestAIEndpoints:
    """Test AI-related endpoints."""
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_get_providers(self, client, auth_headers):
        """Should return list of AI providers."""
        with patch("app.api.routes.ai_service") as mock_ai:
            mock_ai.list_providers = MagicMock(return_value=[
                {"key": "groq", "name": "Groq", "configured": True},
                {"key": "openai", "name": "OpenAI", "configured": False},
            ])
            
            response = await client.get("/api/ai/providers", headers=auth_headers)
            
            assert response.status_code == 200
            data = response.json()
            assert "providers" in data
            assert len(data["providers"]) == 2
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_get_models(self, client, auth_headers):
        """Should return models for a provider."""
        with patch("app.api.routes.ai_service") as mock_ai:
            mock_ai.get_models = AsyncMock(return_value=[
                "model-1", "model-2", "model-3"
            ])
            
            response = await client.get("/api/ai/models/groq", headers=auth_headers)
            
            assert response.status_code == 200
            data = response.json()
            assert data["provider"] == "groq"
            assert "models" in data
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_chat_success(self, client, auth_headers):
        """Should return AI response for chat."""
        with patch("app.api.routes.ai_service") as mock_ai:
            mock_ai.is_available = MagicMock(return_value=True)
            mock_ai.generate_response = AsyncMock(return_value="Hello! I'm an AI.")
            mock_ai.active_provider = MagicMock()
            mock_ai.active_provider.name = "groq"
            
            response = await client.post(
                "/api/ai/chat",
                headers=auth_headers,
                json={"message": "Hello!"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "content" in data
            assert data["content"] == "Hello! I'm an AI."
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_chat_service_unavailable(self, client, auth_headers):
        """Should return 503 when AI not configured."""
        with patch("app.api.routes.ai_service") as mock_ai:
            mock_ai.is_available = MagicMock(return_value=False)
            
            response = await client.post(
                "/api/ai/chat",
                headers=auth_headers,
                json={"message": "Hello!"}
            )
            
            assert response.status_code == 503
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_summarize(self, client, auth_headers):
        """Should summarize text."""
        with patch("app.api.routes.ai_service") as mock_ai:
            mock_ai.is_available = MagicMock(return_value=True)
            mock_ai.summarize = AsyncMock(return_value="This is a summary.")
            
            response = await client.post(
                "/api/ai/summarize",
                headers=auth_headers,
                json={
                    "text": "A very long article about technology...",
                    "max_length": 100,
                    "language": "en"
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["summary"] == "This is a summary."
            assert data["language"] == "en"


class TestMonitorEndpoints:
    """Test monitor-related endpoints."""
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_monitor_status(self, client, auth_headers):
        """Should return monitor status."""
        with patch("app.api.routes.monitor_service") as mock_mon:
            mock_mon.is_running = True
            mock_mon.source_channels = ["-1001", "-1002", "-1003"]
            mock_mon.target_channel = "-1001234567890"
            
            response = await client.get("/api/monitor/status", headers=auth_headers)
            
            assert response.status_code == 200
            data = response.json()
            assert data["running"] is True
            assert data["sources"] == 3
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_monitor_start(self, client, auth_headers):
        """Should start monitoring."""
        with patch("app.api.routes.monitor_service") as mock_mon:
            mock_mon.start = AsyncMock()
            
            response = await client.post("/api/monitor/start", headers=auth_headers)
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "started"
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_monitor_stop(self, client, auth_headers):
        """Should stop monitoring."""
        with patch("app.api.routes.monitor_service") as mock_mon:
            mock_mon.stop = AsyncMock()
            
            response = await client.post("/api/monitor/stop", headers=auth_headers)
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "stopped"


class TestRSSEndpoints:
    """Test RSS-related endpoints."""
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_list_subscriptions(self, client, auth_headers):
        """Should list RSS subscriptions."""
        with patch("app.api.routes.rss_service") as mock_rss:
            mock_rss.get_subscriptions = AsyncMock(return_value=[
                {"id": 1, "url": "https://example.com/feed.xml", "title": "Example"}
            ])
            
            response = await client.get("/api/rss/subscriptions", headers=auth_headers)
            
            assert response.status_code == 200
            data = response.json()
            assert "subscriptions" in data
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_subscribe(self, client, auth_headers):
        """Should subscribe to RSS feed."""
        with patch("app.api.routes.rss_service") as mock_rss:
            mock_rss.subscribe = AsyncMock(return_value={
                "added": True,
                "title": "New Feed",
                "url": "https://example.com/feed.xml"
            })
            
            response = await client.post(
                "/api/rss/subscribe",
                headers=auth_headers,
                json={"url": "https://example.com/feed.xml"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["added"] is True
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_unsubscribe(self, client, auth_headers):
        """Should unsubscribe from RSS feed."""
        with patch("app.api.routes.rss_service") as mock_rss:
            mock_rss.unsubscribe = AsyncMock(return_value={"removed": True})
            
            response = await client.delete(
                "/api/rss/unsubscribe/1",
                headers=auth_headers
            )
            
            assert response.status_code == 200
