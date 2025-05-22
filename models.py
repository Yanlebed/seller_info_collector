from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set


@dataclass
class SellerInfo:
    """Structure to hold seller information"""
    seller_id: str
    country: str
    category: str
    amazon_store_url: str
    seller_name: str = ""
    business_name: str = ""
    business_type: str = ""
    trade_registry_number: str = ""
    phone_number: str = ""
    email: str = ""
    address: str = ""
    rating: float = 0.0
    rating_count: int = 0
    product_count: str = ""  # Number of products the seller has (e.g., "685", "over 1,000")
    product_asin: str = ""  # Store the ASIN of the product where this seller was found
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "seller_id": self.seller_id,
            "seller_name": self.seller_name,
            "business_name": self.business_name,
            "business_type": self.business_type,
            "trade_registry_number": self.trade_registry_number,
            "phone_number": self.phone_number,
            "email": self.email,
            "address": self.address,
            "rating": self.rating,
            "rating_count": self.rating_count,
            "product_count": self.product_count,
            "country": self.country,
            "category": self.category,
            "amazon_store_url": self.amazon_store_url,
            "product_asin": self.product_asin,
            "timestamp": self.timestamp
        }