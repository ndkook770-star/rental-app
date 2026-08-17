from fastapi import FastAPI, HTTPException, File, UploadFile, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from datetime import date
from typing import Optional
import sqlite3
import math
import uvicorn
import os
import shutil

app = FastAPI(title="Rental App API", version="8.0")

# יצירת תיקייה לתמונות
os.makedirs("static/images", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

def init_db():
    conn = sqlite3.connect("rental_app.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER,
            title TEXT,
            category TEXT,
            price_per_day REAL,
            deposit_amount REAL,
            latitude REAL,
            longitude REAL,
            image_url TEXT,
            is_available INTEGER
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER,
            renter_id INTEGER,
            start_date TEXT,
            end_date TEXT,
            total_price REAL,
            platform_fee REAL,
            deposit_hold REAL,
            status TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER,
            reviewer_name TEXT,
            rating INTEGER,
            comment TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

class BookingCreate(BaseModel):
    item_id: int
    renter_id: int
    start_date: date
    end_date: date

class StatusUpdate(BaseModel):
    status: str

class ReviewCreate(BaseModel):
    item_id: int
    reviewer_name: str
    rating: int
    comment: str

@app.get("/", response_class=HTMLResponse)
def get_ui():
    return """
    <!DOCTYPE html>
    <html dir="rtl" lang="he">
    <head>
        <link rel="manifest" href="/manifest.json">
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>RentX - השכרת ציוד</title>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <style>
            body { font-family: system-ui, sans-serif; background: #f4f6f8; margin: 0; padding: 15px; }
            .card { background: white; padding: 15px; border-radius: 12px; box-shadow: 0 2px 6px rgba(0,0,0,0.1); margin-bottom: 15px; }
            h2, h3 { margin-top: 0; color: #333; }
            input, button, select, textarea { width: 100%; padding: 10px; margin: 5px 0 10px 0; border-radius: 8px; border: 1px solid #ccc; box-sizing: border-box; }
            button { background: #2563eb; color: white; border: none; font-weight: bold; cursor: pointer; }
            .btn-book { background: #16a34a; margin-top: 10px; }
            .btn-approve { background: #16a34a; width: 48%; display: inline-block; }
            .btn-reject { background: #dc2626; width: 48%; display: inline-block; }
            #map { height: 250px; width: 100%; border-radius: 12px; margin-bottom: 15px; }
            .badge { background: #fef08a; padding: 4px 8px; border-radius: 6px; font-size: 12px; }
            .review-box { background: #f9fafb; padding: 8px; border-radius: 8px; margin-top: 6px; border: 1px solid #e5e7eb; font-size: 13px; }
            .item-img { width: 100%; height: 180px; object-fit: cover; border-radius: 8px; margin-bottom: 10px; }
        </style>
    </head>
    <body>
        <div class="card">
            <h2>🗺️ מפת ציוד בסביבה</h2>
            <div id="map"></div>
        </div>

        <div class="card">
            <h2>🔍 חיפוש וסינון ציוד</h2>
            <input id="search_text" placeholder="חפש לפי שם פריט...">
            <select id="search_category">
                <option value="">כל הקטגוריות</option>
                <option value="סאונד">סאונד והגברה</option>
                <option value="צילום">צילום ווידאו</option>
                <option value="קמפינג">קמפינג וטיולים</option>
            </select>
            <button onclick="searchItems()">סינון וחיפוש ציוד</button>
        </div>

        <div class="card">
            <h2>➕ העלאת ציוד להשכרה</h2>
            <form id="uploadForm">
                <input name="title" placeholder="שם הציוד (למשל: רמקול מוגבר)" required>
                <input name="category" placeholder="קטגוריה (סאונד/צילום/קמפינג)" required>
                <input name="price_per_day" type="number" placeholder="מחיר ליום (₪)" required>
                <input name="deposit_amount" type="number" placeholder="גובה פיקדון (₪)" required>
                <input name="latitude" type="number" step="any" value="32.0853" required>
                <input name="longitude" type="number" step="any" value="34.7818" required>
                <label>תמונת הציוד:</label>
                <input type="file" name="file" accept="image/*">
                <button type="button" onclick="addItem()">פרסם ציוד</button>
            </form>
        </div>

        <div class="card">
            <h2>📋 בקשות השכרה שממתינות לאישור</h2>
            <button onclick="loadBookings()">רענן בקשות</button>
            <div id="bookings-list"></div>
        </div>

        <div id="results"></div>

        <script>
            let map = L.map('map').setView([32.0853, 34.7818], 12);
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);
            let markers = [];

            async function addItem() {
                const form = document.getElementById('uploadForm');
                const formData = new FormData(form);
                formData.append('owner_id', '101');

                const res = await fetch('/items/', {
                    method: 'POST',
                    body: formData
                });
                if(res.ok) { alert('הציוד פורסם בהצלחה!'); form.reset(); searchItems(); }
            }

            async function searchItems() {
                const query = document.getElementById('search_text').value;
                const cat = document.getElementById('search_category').value;
                
                let url = `/items/search/?user_lat=32.0853&user_lon=34.7818&max_distance_km=20`;
                if(query) url += `&query=${encodeURIComponent(query)}`;
                if(cat) url += `&category=${encodeURIComponent(cat)}`;

                const res = await fetch(url);
                const data = await res.json();
                
                markers.forEach(m => map.removeLayer(m));
                markers = [];

                const container = document.getElementById('results');
                container.innerHTML = '';

                for(const item of data) {
                    let marker = L.marker([item.latitude, item.longitude]).addTo(map)
                        .bindPopup(`<b>${item.title}</b><br>${item.price_per_day} ₪ / יום`);
                    markers.push(marker);

                    const revRes = await fetch(`/reviews/${item.id}`);
                    const reviews = await revRes.json();
                    let reviewsHTML = '';
                    reviews.forEach(r => {
                        reviewsHTML += `<div class="review-box">⭐ ${r.rating}/5 - <b>${r.reviewer_name}</b>: ${r.comment}</div>`;
                    });

                    const imgTag = item.image_url ? `<img src="${item.image_url}" class="item-img">` : '';

                    container.innerHTML += `
                        <div class="card">
                            ${imgTag}
                            <h3>${item.title}</h3>
                            <p>🏷️ קטגוריה: ${item.category}</p>
                            <p>💰 מחיר: ${item.price_per_day} ₪ / יום (פיקדון: ${item.deposit_amount} ₪)</p>
                            <p>📍 מרחק ממך: <b>${item.distance_km} ק"מ</b></p>
                            <hr>
                            <label>תאריך התחלה:</label>
                            <input type="date" id="start_${item.id}" value="2026-08-20">
                            <label>תאריך סיום:</label>
                            <input type="date" id="end_${item.id}" value="2026-08-22">
                            <button class="btn-book" onclick="bookItem(${item.id})">הזמן ציוד זה</button>
                            
                            <hr>
                            <h4>💬 חוות דעת ודירוגים</h4>
                            ${reviewsHTML || '<p style="font-size:12px; color:#666;">אין עדיין ביקורות לפריט זה.</p>'}
                            
                            <input id="rev_name_${item.id}" placeholder="שמך">
                            <select id="rev_rate_${item.id}">
                                <option value="5">⭐⭐⭐⭐⭐ (5)</option>
                                <option value="4">⭐⭐⭐⭐ (4)</option>
                                <option value="3">⭐⭐⭐ (3)</option>
                            </select>
                            <input id="rev_comment_${item.id}" placeholder="כתוב ביקורת...">
                            <button style="background:#4b5563;" onclick="addReview(${item.id})">הוסף דירוג</button>
                        </div>
                    `;
                }
            }

            async function addReview(itemId) {
                const review = {
                    item_id: itemId,
                    reviewer_name: document.getElementById(`rev_name_${itemId}`).value,
                    rating: parseInt(document.getElementById(`rev_rate_${itemId}`).value),
                    comment: document.getElementById(`rev_comment_${itemId}`).value
                };
                const res = await fetch('/reviews/', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(review)
                });
                if(res.ok) { alert('הביקורת נוספה!'); searchItems(); }
            }

            async function bookItem(itemId) {
                const booking = {
                    item_id: itemId,
                    renter_id: 202,
                    start_date: document.getElementById(`start_${itemId}`).value,
                    end_date: document.getElementById(`end_${itemId}`).value
                };

                const res = await fetch('/bookings/', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(booking)
                });
                const data = await res.json();
                if(res.ok) {
                    alert(`הבקשה נשלחה למשכיר!\\nסה"כ לתשלום: ${data.total_price} ₪\\nפיקדון נעול: ${data.deposit_hold} ₪`);
                    loadBookings();
                }
            }

            async function loadBookings() {
                const res = await fetch('/bookings/');
                const data = await res.json();
                const container = document.getElementById('bookings-list');
                container.innerHTML = '';
                data.forEach(b => {
                    container.innerHTML += `
                        <div style="border-top: 1px solid #eee; padding-top: 10px; margin-top: 10px;">
                            <p><b>הזמנה #${b.id}</b> | פריט #${b.item_id}</p>
                            <p>📅 מתאריך: ${b.start_date} עד ${b.end_date}</p>
                            <p>💵 סה"כ לתשלום: ${b.total_price} ₪ (עמלה: ${b.platform_fee} ₪)</p>
                            <p>🔒 פיקדון נעול: ${b.deposit_hold} ₪</p>
                            <p>סטטוס: <span class="badge">${b.status}</span></p>
                            ${b.status === 'pending_approval' ? `
                                <button class="btn-approve" onclick="updateStatus(${b.id}, 'approved')">אישור</button>
                                <button class="btn-reject" onclick="updateStatus(${b.id}, 'rejected')">דחייה</button>
                            ` : ''}
                        </div>
                    `;
                });
            }

            async function updateStatus(bookingId, status) {
                const res = await fetch(`/bookings/${bookingId}/status`, {
                    method: 'PUT',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ status: status })
                });
                if(res.ok) { loadBookings(); }
            }

            searchItems();
            loadBookings();
        </script>
    </body>
    </html>
    """

@app.post("/items/")
async def create_item(
    owner_id: int = Form(...),
    title: str = Form(...),
    category: str = Form(...),
    price_per_day: float = Form(...),
    deposit_amount: float = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    file: Optional[UploadFile] = File(None)
):
    image_url = ""
    if file:
        file_path = f"static/images/{file.filename}"
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        image_url = f"/static/images/{file.filename}"

    conn = sqlite3.connect("rental_app.db")
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO items (owner_id, title, category, price_per_day, deposit_amount, latitude, longitude, image_url, is_available)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
    ''', (owner_id, title, category, price_per_day, deposit_amount, latitude, longitude, image_url))
    conn.commit()
    conn.close()
    return {"message": "Item saved successfully"}

@app.get("/items/search/")
def search_items(user_lat: float, user_lon: float, max_distance_km: float = 20.0, query: Optional[str] = None, category: Optional[str] = None):
    conn = sqlite3.connect("rental_app.db")
    cursor = conn.cursor()
    
    sql = "SELECT * FROM items WHERE is_available = 1"
    params = []
    
    if query:
        sql += " AND title LIKE ?"
        params.append(f"%{query}%")
    if category:
        sql += " AND category = ?"
        params.append(category)
        
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for row in rows:
        dist = calculate_distance(user_lat, user_lon, row[6], row[7])
        if dist <= max_distance_km:
            results.append({
                "id": row[0],
                "title": row[2],
                "category": row[3],
                "price_per_day": row[4],
                "deposit_amount": row[5],
                "latitude": row[6],
                "longitude": row[7],
                "image_url": row[8],
                "distance_km": round(dist, 2)
            })
    return results

@app.post("/bookings/")
def create_booking(booking: BookingCreate):
    conn = sqlite3.connect("rental_app.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM items WHERE id = ?", (booking.item_id,))
    item = cursor.fetchone()
    
    if not item:
        conn.close()
        raise HTTPException(status_code=404, detail="Item not found")

    days = (booking.end_date - booking.start_date).days
    if days <= 0:
        days = 1
    
    price_per_day = item[4]
    deposit_amount = item[5]
    total_price = days * price_per_day
    platform_fee = total_price * 0.10

    cursor.execute('''
        INSERT INTO bookings (item_id, renter_id, start_date, end_date, total_price, platform_fee, deposit_hold, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (booking.item_id, booking.renter_id, str(booking.start_date), str(booking.end_date), total_price, platform_fee, deposit_amount, "pending_approval"))
    
    conn.commit()
    conn.close()

    return {
        "message": "Booking request saved to DB",
        "total_price": total_price,
        "platform_fee": platform_fee,
        "deposit_hold": deposit_amount
    }

@app.get("/bookings/")
def get_bookings():
    conn = sqlite3.connect("rental_app.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, item_id, renter_id, start_date, end_date, total_price, platform_fee, deposit_hold, status FROM bookings")
    rows = cursor.fetchall()
    conn.close()
    
    return [{
        "id": r[0], "item_id": r[1], "renter_id": r[2],
        "start_date": r[3], "end_date": r[4], "total_price": r[5],
        "platform_fee": r[6], "deposit_hold": r[7], "status": r[8]
    } for r in rows]

@app.put("/bookings/{booking_id}/status")
def update_booking_status(booking_id: int, status_update: StatusUpdate):
    conn = sqlite3.connect("rental_app.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE bookings SET status = ? WHERE id = ?", (status_update.status, booking_id))
    conn.commit()
    conn.close()
    return {"message": "Status updated successfully"}

@app.post("/reviews/")
def create_review(review: ReviewCreate):
    conn = sqlite3.connect("rental_app.db")
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO reviews (item_id, reviewer_name, rating, comment)
        VALUES (?, ?, ?, ?)
    ''', (review.item_id, review.reviewer_name, review.rating, review.comment))
    conn.commit()
    conn.close()
    return {"message": "Review added successfully"}

@app.get("/reviews/{item_id}")
def get_reviews(item_id: int):
    conn = sqlite3.connect("rental_app.db")
    cursor = conn.cursor()
    cursor.execute("SELECT reviewer_name, rating, comment FROM reviews WHERE item_id = ?", (item_id,))
    rows = cursor.fetchall()
    conn.close()
    return [{"reviewer_name": r[0], "rating": r[1], "comment": r[2]} for r in rows]

@app.get("/manifest.json")
def get_manifest():
    return JSONResponse(content={
        "name": "RentX - השכרת ציוד",
        "short_name": "RentX",
        "description": "אפליקציה מתקדמת להשכרת ציוד בסביבה הקרובה",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#2563eb",
        "orientation": "portrait",
        "icons": [
            {
                "src": "/icon.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable"
            }
        ]
    })

@app.get("/icon.png")
def get_icon():
    return FileResponse("icon.png")

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
