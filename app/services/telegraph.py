from typing import Optional, Dict, Any, List
import httpx
from app.core.logger import Logger

logger = Logger("TelegraphService")

class TelegraphService:
    BASE_URL = "https://api.telegra.ph"
    
    def __init__(self):
        self.access_token = None
        self.client = httpx.AsyncClient(timeout=10.0)

    async def create_account(self, short_name: str, author_name: str) -> Optional[str]:
        """Create a new Telegraph account and return access token."""
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
    ) -> Optional[str]:
        """Create a page on Telegraph. Returns the URL."""
        if not self.access_token:
            # Create a default account if none exists
            await self.create_account("QuBot", "QuBot Monitor")
            
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
                logger.error(f"Failed to create page: {data}")
                return None
        except Exception as e:
            logger.error(f"Error creating page: {e}")
            return None

telegraph_service = TelegraphService()
