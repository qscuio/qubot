import asyncio
import re
import time
from typing import Optional, Dict, Any, List
import httpx
from app.core.logger import Logger

logger = Logger("TelegraphService")

class TelegraphService:
    BASE_URL = "https://api.telegra.ph"
    
    def __init__(self):
        self.access_token = None
        self.client = httpx.AsyncClient(timeout=10.0)
        # Rate limiting: track last request time
        self._last_request_time = 0.0
        self._min_interval = 1.0  # Minimum 1 second between requests

    async def _wait_rate_limit(self):
        """Wait for rate limit interval."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_interval:
            await asyncio.sleep(self._min_interval - elapsed)
        self._last_request_time = time.time()

    def _parse_flood_wait(self, error: str) -> int:
        """Parse FLOOD_WAIT_N error and return wait time in seconds."""
        match = re.search(r'FLOOD_WAIT_(\d+)', error)
        if match:
            return int(match.group(1))
        return 0

    async def create_account(self, short_name: str, author_name: str) -> Optional[str]:
        """Create a new Telegraph account and return access token."""
        await self._wait_rate_limit()
        try:
            response = await self.client.get(
                f"{self.BASE_URL}/createAccount",
                params={
                    "short_name": short_name,
                    "author_name": author_name
                }
            )
            data = response.json()
            if data.get("ok"):
                self.access_token = data["result"]["access_token"]
                logger.info(f"Created Telegraph account for {author_name}")
                return self.access_token
            else:
                logger.error(f"Failed to create account: {data}")
                return None
        except Exception as e:
            logger.error(f"Error creating account: {e}")
            return None

    async def create_page(
        self,
        title: str,
        content_html: str = "",
        author_name: str = None,
        content_nodes: Optional[List[Dict[str, Any]]] = None,
        max_retries: int = 3,
    ) -> Optional[str]:
        """Create a page on Telegraph. Returns the URL.
        
        Handles FLOOD_WAIT errors by waiting and retrying.
        """
        if not self.access_token:
            # Create a default account if none exists
            await self.create_account("QuBot", "QuBot Monitor")
        
        for attempt in range(max_retries):
            await self._wait_rate_limit()
            
            try:
                # Telegraph expects a JSON list of Nodes. Fallback to a plain paragraph.
                if content_nodes is None:
                    content_nodes = [{"tag": "p", "children": [content_html or ""]}]
                
                import json
                params = {
                    "access_token": self.access_token,
                    "title": title,
                    "content": json.dumps(content_nodes),
                    "return_content": False
                }
                if author_name:
                    params["author_name"] = author_name
                    
                response = await self.client.post(f"{self.BASE_URL}/createPage", data=params)
                data = response.json()
                
                if data.get("ok"):
                    return data["result"]["url"]
                else:
                    error = data.get("error", "")
                    
                    # Handle FLOOD_WAIT - wait and retry
                    wait_time = self._parse_flood_wait(error)
                    if wait_time > 0 and attempt < max_retries - 1:
                        logger.warn(f"Rate limited, waiting {wait_time}s before retry ({attempt + 1}/{max_retries})")
                        await asyncio.sleep(wait_time + 1)  # Add 1s buffer
                        continue
                    
                    logger.error(f"Failed to create page: {data}")
                    return None
                    
            except Exception as e:
                logger.error(f"Error creating page: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)  # Wait before retry on error
                    continue
                return None
        
        return None

telegraph_service = TelegraphService()

