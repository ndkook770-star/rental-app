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

@app.get("/app", response_class=HTMLResponse)
def get_ui():
    return """
<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RentX - השכרת ציוד</title>
    
    <!-- פונט מודרני מגוגל -->
    <link href="https://fonts.googleapis.com/css2?family=Assistant:wght@400;600;700&display=swap" rel="stylesheet">
    
    <!-- Leaflet CSS למפה -->
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />

    <style>
        :root {
            --primary: #2563eb;
            --primary-hover: #1d4ed8;
            --bg-color: #f8fafc;
            --card-bg: #ffffff;
            --text-main: #0f172a;
            --text-muted: #64748b;
            --border-color: #e2e8f0;
            --radius: 16px;
            --shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.05);
        }

        * {
            box-sizing: border-box;
            font-family: 'Assistant', sans-serif;
            margin: 0;
            padding: 0;
        }

        body {
            background-color: var(--bg-color);
            color: var(--text-main);
            padding-bottom: 40px;
        }

        /* סרגל עליון */
        .navbar {
            background: var(--card-bg);
            padding: 16px 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 2px 10px rgba(0,0,0,0.03);
            position: sticky;
            top: 0;
            z-index: 100;
        }

        .logo {
            font-size: 22px;
            font-weight: 700;
            color: var(--primary);
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .container {
            max-width: 600px;
            margin: 0 auto;
            padding: 20px 16px;
            display: flex;
            flex-direction: column;
            gap: 20px;
        }

        /* מסך בחירת תפקיד */
        .hero-selection {
            background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%);
            border-radius: var(--radius);
            padding: 24px 20px;
            color: white;
            text-align: center;
            box-shadow: var(--shadow);
        }

        .hero-selection h1 {
            font-size: 24px;
            margin-bottom: 8px;
        }

        .hero-selection p {
            font-size: 15px;
            opacity: 0.9;
            margin-bottom: 20px;
        }

        .role-buttons {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
        }

        .btn-role {
            background: rgba(255, 255, 255, 0.15);
            border: 1px solid rgba(255, 255, 255, 0.3);
            color: white;
            padding: 14px 10px;
            border-radius: 12px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            backdrop-filter: blur(5px);
            transition: all 0.2s ease;
        }

        .btn-role:hover, .btn-role.active {
            background: white;
            color: var(--primary);
            border-color: white;
        }

        /* כרטיסיות עבודה */
        .card {
            background: var(--card-bg);
            border-radius: var(--radius);
            padding: 20px;
            box-shadow: var(--shadow);
            border: 1px solid var(--border-color);
        }

        .card-title {
            font-size: 18px;
            font-weight: 700;
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        /* אלמנטים של המפה */
        #map {
            height: 250px;
            width: 100%;
            border-radius: 12px;
            z-index: 1;
        }

        /* טפסים ושדות קלט */
        .form-group {
            margin-bottom: 14px;
        }

        .form-group label {
            display: block;
            font-size: 14px;
            font-weight: 600;
            margin-bottom: 6px;
            color: var(--text-muted);
        }

        input, select {
            width: 100%;
            padding: 12px 14px;
            border: 1px solid var(--border-color);
            border-radius: 10px;
            font-size: 15px;
            background: #f8fafc;
            outline: none;
            transition: border 0.2s;
        }

        input:focus, select:focus {
            border-color: var(--primary);
            background: white;
        }

        .btn-primary {
            width: 100%;
            background: var(--primary);
            color: white;
            border: none;
            padding: 14px;
            border-radius: 10px;
            font-size: 16px;
            font-weight: 700;
            cursor: pointer;
            transition: background 0.2s;
        }

        .btn-primary:hover {
            background: var(--primary-hover);
        }
    </style>
</head>
<body>

    <nav class="navbar">
        <div class="logo">⚡ RentX</div>
    </nav>

    <div class="container">
        
        <!-- בחירת תפקיד בכניסה -->
        <section class="hero-selection">
            <h1>ברוכים הבאים ל-RentX</h1>
            <p>מה ברצונך לעשות היום?</p>
            <div class="role-buttons">
                <button class="btn-role active" onclick="selectRole('renter')">🔍 אני רוצה לשכור</button>
                <button class="btn-role" onclick="selectRole('lessor')">➕ אני רוצה להשכיר</button>
            </div>
        </section>

        <!-- מפה (תצוגה לשוכר ולמשכיר) -->
        <div class="card">
            <div class="card-title">🗺️ מפת ציוד ועמדות בסביבה</div>
            <div id="map"></div>
        </div>

        <!-- אזור חיפוש (עבור שוכר) -->
        <div class="card" id="searchSection">
            <div class="card-title">🔍 חיפוש וסינון פריטים</div>
            <div class="form-group">
                <input type="text" placeholder="מה תרצה לשכור? (ציוד, עמדה...)">
            </div>
            <div class="form-group">
                <select>
                    <option value="">כל הקטגוריות</option>
                    <option value="equipment">ציוד מקצועי</option>
                    <option value="workspace">עמדת עבודה / חדר</option>
                </select>
            </div>
            <button class="btn-primary">חפש פריטים</button>
        </div>

        <!-- אזור העלאת פריט (עבור משכיר) -->
        <div class="card" id="uploadSection" style="display: none;">
            <div class="card-title">📦 העלאת ציוד/עמדה להשכרה</div>
            <div class="form-group">
                <label>שם הפריט / העמדה</label>
                <input type="text" placeholder="לדוגמה: עמדת עבודה / מכשיר לייזר">
            </div>
            <div class="form-group">
                <label>מחיר ליום (₪)</label>
                <input type="number" placeholder="00">
            </div>
            <button class="btn-primary">פרסם להשכרה</button>
        </div>

    </div>

    <!-- Leaflet JS למפות -->
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        // אתחול המפה עם ספק תקין שמנע את שגיאת 403
        const map = L.map('map').setView([32.0853, 34.7818], 12);
        
        L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
            maxZoom: 19,
            attribution: '&copy; CartoDB'
        }).addTo(map);

        // החלפת מצבים בין שוכר למשכיר
        function selectRole(role) {
            document.querySelectorAll('.btn-role').forEach(btn => btn.classList.remove('active'));
            
            if (role === 'renter') {
                event.target.classList.add('active');
                document.getElementById('searchSection').style.display = 'block';
                document.getElementById('uploadSection').style.display = 'none';
            } else {
                event.target.classList.add('active');
                document.getElementById('searchSection').style.display = 'none';
                document.getElementById('uploadSection').style.display = 'block';
            }
        }
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
    return [{"reviewer_name": r[0], "rating": r[1], "comment": r[2]for r in rows]
@app.get("/manifest.json")
def get_manifest():
    return JSONResponse(content={
        "name": "RentX - השכרת ציוד",
        "short_name": "RentX",
                "description": "RentX App",
        "start_url": "/app",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#ffffff",
        "icons": [
            {
                "src": "/icon.png",
                "sizes": "512x512",
                "type": "image/png"
            }
        ]
    })
@app.get("/icon.png")
def get_icon():
    return FileResponse("icon.png")
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
