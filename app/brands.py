"""
Brand kit store — persistent storage for custom brand configurations.
"""

import json
import asyncio
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field

STORE_PATH = Path(__file__).parent.parent / "data" / "brands.json"


class BrandKit(BaseModel):
    """Custom branding configuration."""
    name: str = Field(..., description="Unique brand kit identifier (slug)")
    label: str = Field(..., description="Human-readable name")
    background: Optional[str] = Field(None, description="Background color")
    text: Optional[str] = Field(None, description="Text color")
    accent: Optional[str] = Field(None, description="Accent color for badges")
    gutter: Optional[str] = Field(None, description="Line number / gutter color")
    border: Optional[str] = Field(None, description="Border color")
    font_family: Optional[str] = Field(None, description="CSS font-family")
    font_size: Optional[str] = Field(None, description="CSS font-size")
    padding: Optional[str] = Field(None, description="Padding around code")
    border_radius: Optional[str] = Field(None, description="Window border radius")
    shadow: Optional[str] = Field(None, description="CSS box-shadow")
    line_highlight: Optional[str] = Field(None, description="Line highlight color")
    watermark_color: Optional[str] = Field(None, description="Watermark text color")
    watermark: Optional[str] = Field(None, description="Default watermark text")
    logo_url: Optional[str] = Field(None, description="URL to brand logo")


class BrandStore:
    """In-memory brand kit store with JSON file persistence."""
    
    def __init__(self):
        self._brands: dict[str, BrandKit] = {}
        self._lock = asyncio.Lock()
        self._load()
    
    def _load(self):
        """Load brands from JSON file."""
        try:
            if STORE_PATH.exists():
                with open(STORE_PATH) as f:
                    data = json.load(f)
                for b in data:
                    self._brands[b["name"]] = BrandKit(**b)
        except Exception:
            pass
    
    def _save(self):
        """Persist brands to JSON file."""
        STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(STORE_PATH, 'w') as f:
            json.dump([b.model_dump() for b in self._brands.values()], f, indent=2)
    
    async def create(self, brand: BrandKit) -> BrandKit:
        async with self._lock:
            if brand.name in self._brands:
                raise ValueError(f"Brand '{brand.name}' already exists")
            self._brands[brand.name] = brand
            self._save()
            return brand
    
    async def update(self, name: str, brand: BrandKit) -> BrandKit:
        async with self._lock:
            if name not in self._brands:
                raise ValueError(f"Brand '{name}' not found")
            self._brands[name] = brand
            self._save()
            return brand
    
    async def get(self, name: str) -> Optional[BrandKit]:
        return self._brands.get(name)
    
    async def list_all(self) -> list[BrandKit]:
        return list(self._brands.values())
    
    async def delete(self, name: str) -> bool:
        async with self._lock:
            if name not in self._brands:
                return False
            del self._brands[name]
            self._save()
            return True
    
    def to_theme_dict(self, brand: BrandKit) -> dict:
        """Convert a brand kit to a theme override dict for the renderer."""
        return {
            k: v for k, v in brand.model_dump().items()
            if v is not None and k not in ("name", "label")
        }


# Singleton
brand_store = BrandStore()
