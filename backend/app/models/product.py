"""
Pydantic models for products.
"""
from pydantic import BaseModel


class Rating(BaseModel):
    rate: float
    count: int


class Product(BaseModel):
    id: int
    title: str
    price: float
    description: str
    category: str
    image: str
    rating: Rating
