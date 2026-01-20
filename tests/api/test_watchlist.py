"""
API tests for Watchlist endpoints.

Tests watchlist add, remove, status, and list APIs for the Mini App.
Uses webapp_client fixture which has verify_webapp overridden for testing.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock


class TestWatchlistAddEndpoint:
    """Test watchlist add endpoint."""
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_watchlist_add_success(self, webapp_client):
        """Should add stock to watchlist."""
        with patch("app.services.watchlist.watchlist_service") as mock_service:
            
            mock_service.add_stock = AsyncMock(return_value={
                "success": True,
                "code": "600519",
                "name": "贵州茅台"
            })
            
            response = await webapp_client.post(
                "/api/chart/watchlist/add",
                json={"code": "600519", "name": "贵州茅台"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_watchlist_add_no_auth(self, client):
        """Should reject unauthenticated requests."""
        response = await client.post(
            "/api/chart/watchlist/add",
            json={"code": "600519"}
        )
        assert response.status_code in [401, 403, 422]


class TestWatchlistRemoveEndpoint:
    """Test watchlist remove endpoint."""
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_watchlist_remove_success(self, webapp_client):
        """Should remove stock from watchlist."""
        with patch("app.services.watchlist.watchlist_service") as mock_service:
            
            mock_service.remove_stock = AsyncMock(return_value=True)
            
            response = await webapp_client.post(
                "/api/chart/watchlist/remove",
                json={"code": "600519"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_watchlist_remove_not_exists(self, webapp_client):
        """Should handle remove of non-existent stock."""
        with patch("app.services.watchlist.watchlist_service") as mock_service:
            
            mock_service.remove_stock = AsyncMock(return_value=False)
            
            response = await webapp_client.post(
                "/api/chart/watchlist/remove",
                json={"code": "999999"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is False


class TestWatchlistStatusEndpoint:
    """Test watchlist status endpoint."""
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_watchlist_status_in_list(self, webapp_client):
        """Should return true if stock in watchlist."""
        with patch("app.services.watchlist.watchlist_service") as mock_service:
            
            mock_service.get_watchlist = AsyncMock(return_value=[
                {"code": "600519", "name": "贵州茅台"},
                {"code": "000001", "name": "平安银行"},
            ])
            
            response = await webapp_client.get("/api/chart/watchlist/status?code=600519")
            
            assert response.status_code == 200
            data = response.json()
            assert data["in_watchlist"] is True
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_watchlist_status_not_in_list(self, webapp_client):
        """Should return false if stock not in watchlist."""
        with patch("app.services.watchlist.watchlist_service") as mock_service:
            
            mock_service.get_watchlist = AsyncMock(return_value=[
                {"code": "000001", "name": "平安银行"},
            ])
            
            response = await webapp_client.get("/api/chart/watchlist/status?code=600519")
            
            assert response.status_code == 200
            data = response.json()
            assert data["in_watchlist"] is False


class TestWatchlistListEndpoint:
    """Test watchlist list endpoint."""
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_watchlist_list_success(self, webapp_client):
        """Should return user's watchlist."""
        with patch("app.services.watchlist.watchlist_service") as mock_service:
            
            mock_service.get_watchlist = AsyncMock(return_value=[
                {"code": "600519", "name": "贵州茅台", "created_at": "2024-01-01"},
                {"code": "000001", "name": "平安银行", "created_at": "2024-01-02"},
            ])
            
            response = await webapp_client.get("/api/chart/watchlist/list")
            
            assert response.status_code == 200
            data = response.json()
            assert "watchlist" in data
            assert len(data["watchlist"]) == 2
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_watchlist_list_empty(self, webapp_client):
        """Should return empty list for new user."""
        with patch("app.services.watchlist.watchlist_service") as mock_service:
            
            mock_service.get_watchlist = AsyncMock(return_value=[])
            
            response = await webapp_client.get("/api/chart/watchlist/list")
            
            assert response.status_code == 200
            data = response.json()
            assert data["watchlist"] == []
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_watchlist_list_no_auth(self, client):
        """Should reject unauthenticated requests."""
        response = await client.get("/api/chart/watchlist/list")
        assert response.status_code in [401, 403, 422]
