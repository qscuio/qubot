"""
API tests for Chart endpoints.

Tests chart data, chip distribution, search, and navigation APIs.
Uses webapp_client fixture which has verify_webapp overridden for testing.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock


class TestChartDataEndpoint:
    """Test chart data endpoint."""
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_chart_data_success(self, webapp_client):
        """Should return OHLCV data for valid stock code."""
        with patch("app.services.stock_history.stock_history_service") as mock_service, \
             patch("app.core.database.db") as mock_db:
            
            mock_db.pool = MagicMock()
            mock_db.pool.fetchrow = AsyncMock(return_value={"name": "测试股票"})
            
            mock_service.get_stock_history = AsyncMock(return_value=[
                {"date": "2024-01-15", "open": 10.0, "high": 11.0, "low": 9.5, 
                 "close": 10.5, "volume": 100000, "amplitude": 5.0, "turnover_rate": 2.5},
                {"date": "2024-01-16", "open": 10.5, "high": 11.5, "low": 10.0, 
                 "close": 11.0, "volume": 120000, "amplitude": 4.5, "turnover_rate": 3.0},
                {"date": "2024-01-17", "open": 11.0, "high": 12.0, "low": 10.5, 
                 "close": 11.5, "volume": 130000, "amplitude": 4.0, "turnover_rate": 3.5},
                {"date": "2024-01-18", "open": 11.5, "high": 12.5, "low": 11.0, 
                 "close": 12.0, "volume": 140000, "amplitude": 4.0, "turnover_rate": 4.0},
                {"date": "2024-01-19", "open": 12.0, "high": 13.0, "low": 11.5, 
                 "close": 12.5, "volume": 150000, "amplitude": 4.0, "turnover_rate": 4.5},
            ])
            
            response = await webapp_client.get("/api/chart/data/600519?days=60&period=daily")
            
            assert response.status_code == 200
            data = response.json()
            assert "code" in data
            assert "data" in data
            assert data["code"] == "600519"
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_chart_data_no_auth(self, client):
        """Should reject requests without Telegram auth."""
        response = await client.get("/api/chart/data/600519")
        assert response.status_code in [401, 403, 422]
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_chart_data_not_found(self, webapp_client):
        """Should return 404 when no data available."""
        with patch("app.services.stock_history.stock_history_service") as mock_service, \
             patch("app.core.database.db") as mock_db:
            
            mock_db.pool = MagicMock()
            mock_db.pool.fetchrow = AsyncMock(return_value=None)
            mock_service.get_stock_history = AsyncMock(return_value=[])
            
            response = await webapp_client.get("/api/chart/data/999999?days=60&period=daily")
            
            assert response.status_code == 404


class TestChartChipsEndpoint:
    """Test chip distribution endpoint."""
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_chart_chips_success(self, webapp_client):
        """Should return chip distribution data."""
        with patch("app.services.chip_distribution.chip_distribution_service") as mock_service:
            
            mock_service.get_chip_distribution = AsyncMock(return_value={
                "code": "600519",
                "date": "2024-01-15",
                "distribution": [
                    {"price": 100.0, "volume_percent": 5.0},
                    {"price": 101.0, "volume_percent": 10.0},
                ],
                "cost_90": 1800.5,
                "cost_70": 1750.2,
                "avg_cost": 1820.3
            })
            
            response = await webapp_client.get("/api/chart/chips/600519")
            
            assert response.status_code == 200
            data = response.json()
            assert "distribution" in data
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_chart_chips_not_found(self, webapp_client):
        """Should return 404 when no data available."""
        with patch("app.services.chip_distribution.chip_distribution_service") as mock_service:
            
            mock_service.get_chip_distribution = AsyncMock(return_value=None)
            
            response = await webapp_client.get("/api/chart/chips/999999")
            
            assert response.status_code == 404


class TestChartSearchEndpoint:
    """Test stock search endpoint."""
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_chart_search_success(self, webapp_client):
        """Should return matching stocks."""
        with patch("app.core.database.db") as mock_db:
            
            mock_db.pool = MagicMock()
            mock_db.pool.fetch = AsyncMock(return_value=[
                {"code": "600519", "name": "贵州茅台"},
                {"code": "600518", "name": "康美药业"},
            ])
            
            response = await webapp_client.get("/api/chart/search?q=6005")
            
            assert response.status_code == 200
            data = response.json()
            assert "results" in data
            assert len(data["results"]) == 2
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_chart_search_empty_query(self, webapp_client):
        """Should return empty results for empty query."""
        response = await webapp_client.get("/api/chart/search?q=")
        
        assert response.status_code == 200
        data = response.json()
        assert data["results"] == []


class TestChartNavigationEndpoint:
    """Test chart navigation endpoint."""
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_navigation_default(self, webapp_client):
        """Should return null for default context."""
        response = await webapp_client.get("/api/chart/navigation?code=600519&context=default")
        
        assert response.status_code == 200
        data = response.json()
        assert "prev" in data
        assert "next" in data
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_navigation_watchlist(self, webapp_client):
        """Should navigate within watchlist."""
        with patch("app.core.database.db") as mock_db:
            
            mock_db.pool = MagicMock()
            mock_db.pool.fetch = AsyncMock(return_value=[
                {"code": "600518"},
                {"code": "600519"},
                {"code": "600520"},
            ])
            
            response = await webapp_client.get("/api/chart/navigation?code=600519&context=watchlist")
            
            assert response.status_code == 200
            data = response.json()
            assert data["prev"] == "600518"
            assert data["next"] == "600520"
