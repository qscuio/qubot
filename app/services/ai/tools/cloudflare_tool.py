"""
Cloudflare tools for DNS, Workers, Pages, and KV operations.
"""

import httpx
from typing import List, Dict, Any
from app.services.ai.tools.base import Tool, ToolParameter, ToolResult
from app.services.ai.tools.registry import register_tool
from app.core.config import settings
from app.core.logger import Logger

logger = Logger("CloudflareTools")

CF_API = "https://api.cloudflare.com/client/v4"


def get_headers() -> Dict[str, str]:
    """Get Cloudflare API headers."""
    token = getattr(settings, "CLOUDFLARE_API_TOKEN", None)
    if not token:
        return {}
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }


def get_account_id() -> str:
    """Get Cloudflare account ID."""
    return getattr(settings, "CLOUDFLARE_ACCOUNT_ID", "") or ""


class CloudflareDNSTool(Tool):
    """Manage Cloudflare DNS records."""
    
    @property
    def name(self) -> str:
        return "cloudflare_dns"
    
    @property
    def description(self) -> str:
        return "List, get, create, update, or delete DNS records in a Cloudflare zone."
    
    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="action",
                type="string",
                description="Action: 'list', 'get', 'create', 'update', 'delete'",
                required=True,
                enum=["list", "get", "create", "update", "delete"]
            ),
            ToolParameter(
                name="zone_id",
                type="string",
                description="Cloudflare zone ID",
                required=True
            ),
            ToolParameter(
                name="record_id",
                type="string",
                description="DNS record ID (for get/update/delete)",
                required=False
            ),
            ToolParameter(
                name="type",
                type="string",
                description="DNS record type (A, AAAA, CNAME, TXT, MX, etc.)",
                required=False
            ),
            ToolParameter(
                name="name",
                type="string", 
                description="DNS record name (e.g., 'www.example.com')",
                required=False
            ),
            ToolParameter(
                name="content",
                type="string",
                description="DNS record content (e.g., IP address)",
                required=False
            ),
            ToolParameter(
                name="proxied",
                type="boolean",
                description="Whether the record is proxied through Cloudflare",
                required=False,
                default=False
            )
        ]
    
    async def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "list")
        zone_id = kwargs.get("zone_id", "")
        
        headers = get_headers()
        if not headers:
            return ToolResult(success=False, output=None, error="CLOUDFLARE_API_TOKEN not configured")
        
        try:
            async with httpx.AsyncClient() as client:
                if action == "list":
                    response = await client.get(
                        f"{CF_API}/zones/{zone_id}/dns_records",
                        headers=headers,
                        timeout=15.0
                    )
                    response.raise_for_status()
                    data = response.json()
                    
                    records = []
                    for r in data.get("result", []):
                        records.append({
                            "id": r.get("id"),
                            "type": r.get("type"),
                            "name": r.get("name"),
                            "content": r.get("content"),
                            "proxied": r.get("proxied")
                        })
                    
                    return ToolResult(success=True, output=records)
                
                elif action == "get":
                    record_id = kwargs.get("record_id")
                    if not record_id:
                        return ToolResult(success=False, output=None, error="record_id required")
                    
                    response = await client.get(
                        f"{CF_API}/zones/{zone_id}/dns_records/{record_id}",
                        headers=headers,
                        timeout=15.0
                    )
                    response.raise_for_status()
                    data = response.json()
                    
                    return ToolResult(success=True, output=data.get("result"))
                
                elif action == "create":
                    rec_type = kwargs.get("type")
                    name = kwargs.get("name")
                    content = kwargs.get("content")
                    proxied = kwargs.get("proxied", False)
                    
                    if not all([rec_type, name, content]):
                        return ToolResult(success=False, output=None, error="type, name, content required")
                    
                    response = await client.post(
                        f"{CF_API}/zones/{zone_id}/dns_records",
                        headers=headers,
                        json={"type": rec_type, "name": name, "content": content, "proxied": proxied},
                        timeout=15.0
                    )
                    response.raise_for_status()
                    data = response.json()
                    
                    return ToolResult(
                        success=True,
                        output={"id": data.get("result", {}).get("id"), "message": "DNS record created"}
                    )
                
                elif action == "update":
                    record_id = kwargs.get("record_id")
                    if not record_id:
                        return ToolResult(success=False, output=None, error="record_id required")
                    
                    update_data = {}
                    for field in ["type", "name", "content", "proxied"]:
                        if kwargs.get(field) is not None:
                            update_data[field] = kwargs.get(field)
                    
                    response = await client.patch(
                        f"{CF_API}/zones/{zone_id}/dns_records/{record_id}",
                        headers=headers,
                        json=update_data,
                        timeout=15.0
                    )
                    response.raise_for_status()
                    
                    return ToolResult(success=True, output="DNS record updated")
                
                elif action == "delete":
                    record_id = kwargs.get("record_id")
                    if not record_id:
                        return ToolResult(success=False, output=None, error="record_id required")
                    
                    response = await client.delete(
                        f"{CF_API}/zones/{zone_id}/dns_records/{record_id}",
                        headers=headers,
                        timeout=15.0
                    )
                    response.raise_for_status()
                    
                    return ToolResult(success=True, output="DNS record deleted")
                
                return ToolResult(success=False, output=None, error="Unknown action")
        except Exception as e:
            logger.error(f"Cloudflare DNS failed: {e}")
            return ToolResult(success=False, output=None, error=str(e))


class CloudflareWorkersTool(Tool):
    """List and manage Cloudflare Workers."""
    
    @property
    def name(self) -> str:
        return "cloudflare_workers"
    
    @property
    def description(self) -> str:
        return "List Cloudflare Workers or get worker details."
    
    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="action",
                type="string",
                description="Action: 'list' or 'get'",
                required=True,
                enum=["list", "get"]
            ),
            ToolParameter(
                name="worker_name",
                type="string",
                description="Worker script name (for 'get' action)",
                required=False
            )
        ]
    
    async def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "list")
        
        headers = get_headers()
        account_id = get_account_id()
        
        if not headers:
            return ToolResult(success=False, output=None, error="CLOUDFLARE_API_TOKEN not configured")
        if not account_id:
            return ToolResult(success=False, output=None, error="CLOUDFLARE_ACCOUNT_ID not configured")
        
        try:
            async with httpx.AsyncClient() as client:
                if action == "list":
                    response = await client.get(
                        f"{CF_API}/accounts/{account_id}/workers/scripts",
                        headers=headers,
                        timeout=15.0
                    )
                    response.raise_for_status()
                    data = response.json()
                    
                    workers = []
                    for w in data.get("result", []):
                        workers.append({
                            "id": w.get("id"),
                            "name": w.get("id"),
                            "created_on": w.get("created_on"),
                            "modified_on": w.get("modified_on")
                        })
                    
                    return ToolResult(success=True, output=workers)
                
                elif action == "get":
                    worker_name = kwargs.get("worker_name")
                    if not worker_name:
                        return ToolResult(success=False, output=None, error="worker_name required")
                    
                    response = await client.get(
                        f"{CF_API}/accounts/{account_id}/workers/scripts/{worker_name}",
                        headers=headers,
                        timeout=15.0
                    )
                    response.raise_for_status()
                    
                    # Get worker settings
                    settings_resp = await client.get(
                        f"{CF_API}/accounts/{account_id}/workers/scripts/{worker_name}/settings",
                        headers=headers,
                        timeout=15.0
                    )
                    
                    settings_data = settings_resp.json() if settings_resp.status_code == 200 else {}
                    
                    return ToolResult(
                        success=True,
                        output={
                            "name": worker_name,
                            "settings": settings_data.get("result", {})
                        }
                    )
                
                return ToolResult(success=False, output=None, error="Unknown action")
        except Exception as e:
            logger.error(f"Cloudflare Workers failed: {e}")
            return ToolResult(success=False, output=None, error=str(e))


class CloudflarePagesTool(Tool):
    """List Cloudflare Pages projects."""
    
    @property
    def name(self) -> str:
        return "cloudflare_pages"
    
    @property
    def description(self) -> str:
        return "List Cloudflare Pages projects and deployments."
    
    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="action",
                type="string",
                description="Action: 'list_projects', 'get_project', or 'list_deployments'",
                required=True,
                enum=["list_projects", "get_project", "list_deployments"]
            ),
            ToolParameter(
                name="project_name",
                type="string",
                description="Project name (for get_project/list_deployments)",
                required=False
            )
        ]
    
    async def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "list_projects")
        
        headers = get_headers()
        account_id = get_account_id()
        
        if not headers:
            return ToolResult(success=False, output=None, error="CLOUDFLARE_API_TOKEN not configured")
        if not account_id:
            return ToolResult(success=False, output=None, error="CLOUDFLARE_ACCOUNT_ID not configured")
        
        try:
            async with httpx.AsyncClient() as client:
                if action == "list_projects":
                    response = await client.get(
                        f"{CF_API}/accounts/{account_id}/pages/projects",
                        headers=headers,
                        timeout=15.0
                    )
                    response.raise_for_status()
                    data = response.json()
                    
                    projects = []
                    for p in data.get("result", []):
                        projects.append({
                            "name": p.get("name"),
                            "subdomain": p.get("subdomain"),
                            "created_on": p.get("created_on")
                        })
                    
                    return ToolResult(success=True, output=projects)
                
                elif action == "get_project":
                    project_name = kwargs.get("project_name")
                    if not project_name:
                        return ToolResult(success=False, output=None, error="project_name required")
                    
                    response = await client.get(
                        f"{CF_API}/accounts/{account_id}/pages/projects/{project_name}",
                        headers=headers,
                        timeout=15.0
                    )
                    response.raise_for_status()
                    data = response.json()
                    
                    project = data.get("result", {})
                    return ToolResult(
                        success=True,
                        output={
                            "name": project.get("name"),
                            "subdomain": project.get("subdomain"),
                            "domains": project.get("domains", []),
                            "latest_deployment": project.get("latest_deployment", {}).get("url")
                        }
                    )
                
                elif action == "list_deployments":
                    project_name = kwargs.get("project_name")
                    if not project_name:
                        return ToolResult(success=False, output=None, error="project_name required")
                    
                    response = await client.get(
                        f"{CF_API}/accounts/{account_id}/pages/projects/{project_name}/deployments",
                        headers=headers,
                        params={"per_page": 10},
                        timeout=15.0
                    )
                    response.raise_for_status()
                    data = response.json()
                    
                    deployments = []
                    for d in data.get("result", []):
                        deployments.append({
                            "id": d.get("id"),
                            "url": d.get("url"),
                            "environment": d.get("environment"),
                            "created_on": d.get("created_on")
                        })
                    
                    return ToolResult(success=True, output=deployments)
                
                return ToolResult(success=False, output=None, error="Unknown action")
        except Exception as e:
            logger.error(f"Cloudflare Pages failed: {e}")
            return ToolResult(success=False, output=None, error=str(e))


class CloudflareKVTool(Tool):
    """Read and write to Cloudflare Workers KV."""
    
    @property
    def name(self) -> str:
        return "cloudflare_kv"
    
    @property
    def description(self) -> str:
        return "Read, write, or list keys in a Cloudflare Workers KV namespace."
    
    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="action",
                type="string",
                description="Action: 'list_namespaces', 'list_keys', 'get', 'put', 'delete'",
                required=True,
                enum=["list_namespaces", "list_keys", "get", "put", "delete"]
            ),
            ToolParameter(
                name="namespace_id",
                type="string",
                description="KV namespace ID",
                required=False
            ),
            ToolParameter(
                name="key",
                type="string",
                description="Key name (for get/put/delete)",
                required=False
            ),
            ToolParameter(
                name="value",
                type="string",
                description="Value to store (for put)",
                required=False
            )
        ]
    
    async def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "list_namespaces")
        
        headers = get_headers()
        account_id = get_account_id()
        
        if not headers:
            return ToolResult(success=False, output=None, error="CLOUDFLARE_API_TOKEN not configured")
        if not account_id:
            return ToolResult(success=False, output=None, error="CLOUDFLARE_ACCOUNT_ID not configured")
        
        try:
            async with httpx.AsyncClient() as client:
                if action == "list_namespaces":
                    response = await client.get(
                        f"{CF_API}/accounts/{account_id}/storage/kv/namespaces",
                        headers=headers,
                        timeout=15.0
                    )
                    response.raise_for_status()
                    data = response.json()
                    
                    namespaces = []
                    for ns in data.get("result", []):
                        namespaces.append({
                            "id": ns.get("id"),
                            "title": ns.get("title")
                        })
                    
                    return ToolResult(success=True, output=namespaces)
                
                namespace_id = kwargs.get("namespace_id")
                if not namespace_id:
                    return ToolResult(success=False, output=None, error="namespace_id required")
                
                if action == "list_keys":
                    response = await client.get(
                        f"{CF_API}/accounts/{account_id}/storage/kv/namespaces/{namespace_id}/keys",
                        headers=headers,
                        timeout=15.0
                    )
                    response.raise_for_status()
                    data = response.json()
                    
                    keys = [k.get("name") for k in data.get("result", [])]
                    return ToolResult(success=True, output=keys)
                
                elif action == "get":
                    key = kwargs.get("key")
                    if not key:
                        return ToolResult(success=False, output=None, error="key required")
                    
                    response = await client.get(
                        f"{CF_API}/accounts/{account_id}/storage/kv/namespaces/{namespace_id}/values/{key}",
                        headers=headers,
                        timeout=15.0
                    )
                    
                    if response.status_code == 404:
                        return ToolResult(success=False, output=None, error="Key not found")
                    
                    response.raise_for_status()
                    return ToolResult(success=True, output=response.text)
                
                elif action == "put":
                    key = kwargs.get("key")
                    value = kwargs.get("value", "")
                    if not key:
                        return ToolResult(success=False, output=None, error="key required")
                    
                    response = await client.put(
                        f"{CF_API}/accounts/{account_id}/storage/kv/namespaces/{namespace_id}/values/{key}",
                        headers={**headers, "Content-Type": "text/plain"},
                        content=value,
                        timeout=15.0
                    )
                    response.raise_for_status()
                    
                    return ToolResult(success=True, output=f"Stored key: {key}")
                
                elif action == "delete":
                    key = kwargs.get("key")
                    if not key:
                        return ToolResult(success=False, output=None, error="key required")
                    
                    response = await client.delete(
                        f"{CF_API}/accounts/{account_id}/storage/kv/namespaces/{namespace_id}/values/{key}",
                        headers=headers,
                        timeout=15.0
                    )
                    response.raise_for_status()
                    
                    return ToolResult(success=True, output=f"Deleted key: {key}")
                
                return ToolResult(success=False, output=None, error="Unknown action")
        except Exception as e:
            logger.error(f"Cloudflare KV failed: {e}")
            return ToolResult(success=False, output=None, error=str(e))


def register_cloudflare_tools():
    """Register all Cloudflare tools."""
    register_tool(CloudflareDNSTool())
    register_tool(CloudflareWorkersTool())
    register_tool(CloudflarePagesTool())
    register_tool(CloudflareKVTool())
    logger.info("Registered Cloudflare tools")
