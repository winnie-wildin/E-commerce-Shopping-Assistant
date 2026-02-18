"""
Fake Store API client.
"""
import os
import httpx
from typing import List, Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from app.models.product import Product


class FakeStoreClient:
    """Async HTTP client for the Fake Store API with retry logic."""
    
    def __init__(self):
        self.base_url = os.getenv("FAKESTORE_API_URL", "https://fakestoreapi.com")
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=10.0,
            follow_redirects=True
        )
    
    async def close(self):
        await self.client.aclose()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4)
    )
    async def _request(self, method: str, endpoint: str, **kwargs):
        try:
            response = await self.client.request(method, endpoint, **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as e:
            raise Exception(f"API error: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            raise Exception(f"Request error: {str(e)}")
    
    async def get_all_products(self) -> List[Product]:
        response = await self._request("GET", "/products")
        return [Product(**p) for p in response.json()]
    
    async def get_product_by_id(self, product_id: int) -> Product:
        response = await self._request("GET", f"/products/{product_id}")
        return Product(**response.json())
    
    async def get_all_categories(self) -> List[str]:
        response = await self._request("GET", "/products/categories")
        return response.json()
    
    async def search_products(
        self,
        query: Optional[str] = None,
        category: Optional[str] = None,
        max_price: Optional[float] = None
    ) -> List[Product]:
        """Keyword search fallback — fetches all products and filters client-side."""
        products = await self.get_all_products()
        
        if category:
            products = [p for p in products if p.category.lower() == category.lower()]
        
        if query:
            words = [w for w in query.lower().split() if len(w) > 2]
            if words:
                products = [
                    p for p in products
                    if any(
                        w in p.title.lower() or w in p.description.lower()
                        for w in words
                    )
                ]
        
        if max_price is not None:
            products = [p for p in products if p.price <= max_price]
        
        return products
