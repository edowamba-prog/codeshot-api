"""
Brand kit API routes — CRUD for custom brand configurations.
"""

from fastapi import APIRouter, HTTPException
from ..brands import BrandKit, brand_store

router = APIRouter(prefix="/v1/brands", tags=["brands"])


@router.post("", response_model=BrandKit, status_code=201)
async def create_brand(brand: BrandKit):
    """Create a new brand kit. Name must be a unique slug (e.g., 'acme-corp')."""
    try:
        return await brand_store.create(brand)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("", response_model=list[BrandKit])
async def list_brands():
    """List all saved brand kits."""
    return await brand_store.list_all()


@router.get("/{name}", response_model=BrandKit)
async def get_brand(name: str):
    """Get a specific brand kit by name."""
    brand = await brand_store.get(name)
    if not brand:
        raise HTTPException(status_code=404, detail=f"Brand '{name}' not found")
    return brand


@router.put("/{name}", response_model=BrandKit)
async def update_brand(name: str, brand: BrandKit):
    """Update an existing brand kit."""
    try:
        return await brand_store.update(name, brand)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{name}", status_code=204)
async def delete_brand(name: str):
    """Delete a brand kit."""
    deleted = await brand_store.delete(name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Brand '{name}' not found")
