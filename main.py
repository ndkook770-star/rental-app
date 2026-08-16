from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import date
import math
import uvicorn

app = FastAPI(title="Rental App API", version="1.2")

def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# --- מודלים ---

class User(BaseModel):
    id: int
    name: str
    phone: str
    rating: float = 5.0

class Item(BaseModel):
    id: int
    owner_id: int
    title: str
    category: str
    price_per_day: float
    deposit_amount: float
    latitude: float
    longitude: float
    is_available: bool = True

class BookingRequest(BaseModel):
    id: int
    item_id: int
    renter_id: int
    start_date: date
    end_date: date

# --- מסד נתונים זמני ---
db_users: List[User] = []
db_items: List[Item] = []
db_bookings: List[dict] = []

@app.get("/")
def read_root():
    return {"message": "Welcome to Rental App API"}

@app.post("/users/", response_model=User)
def create_user(user: User):
    db_users.append(user)
    return user

@app.post("/items/", response_model=Item)
def create_item(item: Item):
    db_items.append(item)
    return item

@app.get("/items/search/")
def search_items_by_location(user_lat: float, user_lon: float, max_distance_km: float = 10.0):
    results = []
    for item in db_items:
        if item.is_available:
            dist = calculate_distance(user_lat, user_lon, item.latitude, item.longitude)
            if dist <= max_distance_km:
                item_dict = item.model_dump()
                item_dict["distance_km"] = round(dist, 2)
                results.append(item_dict)
    return results

# --- יצירת בקשת השכרה חדשה ---
@app.post("/bookings/")
def create_booking(booking: BookingRequest):
    # מציאת הפריט
    item = next((i for i in db_items if i.id == booking.item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    
    if not item.is_available:
        raise HTTPException(status_code=400, detail="Item is not available")

    # חישוב ימי השכרה ומחיר
    days = (booking.end_date - booking.start_date).days
    if days <= 0:
        days = 1  # השכרה ליום אחד לפחות
    
    total_rental_price = days * item.price_per_day
    platform_fee = total_rental_price * 0.10  # 10% עמלת אפליקציה

    booking_data = {
        "booking_id": booking.id,
        "item_title": item.title,
        "renter_id": booking.renter_id,
        "rental_days": days,
        "total_price": total_rental_price,
        "platform_fee": platform_fee,
        "deposit_hold": item.deposit_amount,
        "status": "pending_approval"
    }
    
    db_bookings.append(booking_data)
    return booking_data

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
