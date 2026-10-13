import os
import time
import uuid
import csv
import io
from datetime import datetime, timezone
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, Response, current_app
from app.database import db, initialize_firebase
from app.email_service import send_event_ticket_confirmation_email

events_bp = Blueprint('events_bp', __name__)

# Fallback curated Unsplash banners for event categories
CATEGORY_DEFAULTS = {
    "bash": {
        "label": "Campus Bash 🎉",
        "img": "https://images.unsplash.com/photo-1516450360452-9312f5e86fc7?w=1200&q=80",
        "icon": "🎉"
    },
    "pool_party": {
        "label": "Pool Party 🏊",
        "img": "https://images.unsplash.com/photo-1533105079780-92b9be482077?w=1200&q=80",
        "icon": "🏊"
    },
    "house_party": {
        "label": "House Party 🏡",
        "img": "https://images.unsplash.com/photo-1527529482837-4698179dc6ce?w=1200&q=80",
        "icon": "🏡"
    },
    "birthday": {
        "label": "Birthday Party 🎂",
        "img": "https://images.unsplash.com/photo-1464349095431-e9a21285b5f3?w=1200&q=80",
        "icon": "🎂"
    },
    "speed_dating": {
        "label": "Speed Dating 💘",
        "img": "https://images.unsplash.com/photo-1511895426328-dc8714191300?w=1200&q=80",
        "icon": "💘"
    },
    "campus_mixer": {
        "label": "Campus Mixer 🍸",
        "img": "https://images.unsplash.com/photo-1533227260815-a56cf8af0d3c?w=1200&q=80",
        "icon": "🍸"
    },
    "rave": {
        "label": "Rave & Club Night 🎧",
        "img": "https://images.unsplash.com/photo-1470225620780-dba8ba36b745?w=1200&q=80",
        "icon": "🎧"
    },
    "custom": {
        "label": "Social Event 🌟",
        "img": "https://images.unsplash.com/photo-1511578314322-379afb476865?w=1200&q=80",
        "icon": "🌟"
    }
}

DEFAULT_HOTSPOTS = [
    {"id": "spot_lib", "name": "MMUST Library Cafe & Foyer", "count": 28, "trend": "up", "icon": "☕", "description": "Quiet study desks & casual catch-ups"},
    {"id": "spot_sc", "name": "Student Center Main Hub", "count": 54, "trend": "up", "icon": "🍔", "description": "High campus traffic, fast food & banter"},
    {"id": "spot_sig", "name": "Signature Lounge & Club", "count": 42, "trend": "up", "icon": "🍸", "description": "Evening cocktails, DJ beats & weekend vibes"},
    {"id": "spot_sports", "name": "Sports Pavilion & Track", "count": 22, "trend": "up", "icon": "🏀", "description": "Afternoon basketball & outdoor fitness"},
    {"id": "spot_boma", "name": "Boma Gardens & Grill", "count": 18, "trend": "down", "icon": "🌳", "description": "Chill weekend barbeque & open breeze"}
]


def ensure_seed_data():
    """Populates initial sample hotspots and events if the database nodes are empty."""
    try:
        hotspots_ref = db.reference('hotspots')
        existing_hotspots = hotspots_ref.get()
        if not existing_hotspots:
            for spot in DEFAULT_HOTSPOTS:
                hotspots_ref.child(spot['id']).set(spot)

        events_ref = db.reference('events')
        existing_events = events_ref.get()
        if not existing_events:
            seed_events = [
                {
                    "id": "evt_neon_pool_2026",
                    "title": "Neon Nights Pool Party 2026",
                    "category": "pool_party",
                    "category_label": "Pool Party 🏊",
                    "description": "The ultimate campus pool party! Glow sticks, live DJ set by DJ Flexx, poolside cocktails and barbecue. Bring your swimwear and good vibes.",
                    "date": "2026-10-24",
                    "date_str": "Saturday, Oct 24, 2026",
                    "time_str": "3:00 PM - 11:00 PM",
                    "venue_name": "Kakamega Forest Resort Villa",
                    "location_url": "https://maps.google.com/?q=Kakamega+Forest+Resort",
                    "dress_code": "Neon & Stylish Swimwear",
                    "price_type": "free",
                    "price": 0,
                    "price_display": "Free Admission (Guestlist Required)",
                    "capacity": 150,
                    "attendees_count": 68,
                    "organizer_name": "MMUST Entertainment Guild",
                    "organizer_phone": "254707605751",
                    "banner_img": "https://images.unsplash.com/photo-1533105079780-92b9be482077?w=1200&q=80",
                    "maintenance_fee_paid": True,
                    "created_at": int(time.time() * 1000),
                    "amenities": ["Heated Pool", "Live DJ", "Free Glowsticks", "Security", "Cocktail Bar"]
                },
                {
                    "id": "evt_all_white_bash",
                    "title": "All-White Semester Opening Bash",
                    "category": "bash",
                    "category_label": "Campus Bash 🎉",
                    "description": "Step into the new semester in pure style! An exclusive all-white party celebrating campus friendship and matches. Photo booth, red carpet entry.",
                    "date": "2026-10-30",
                    "date_str": "Friday, Oct 30, 2026",
                    "time_str": "7:00 PM Till Late",
                    "venue_name": "Signature VIP Club Kakamega",
                    "location_url": "https://maps.google.com/?q=Signature+Club+Kakamega",
                    "dress_code": "Strictly All-White Chic",
                    "price_type": "paid",
                    "price": 200,
                    "price_display": "200 KES (Early Bird)",
                    "capacity": 200,
                    "attendees_count": 94,
                    "organizer_name": "Delstarford Works & FYM",
                    "organizer_phone": "254707605751",
                    "banner_img": "https://images.unsplash.com/photo-1516450360452-9312f5e86fc7?w=1200&q=80",
                    "maintenance_fee_paid": True,
                    "created_at": int(time.time() * 1000),
                    "amenities": ["VIP Booths", "Red Carpet Photos", "Complimentary Welcome Drink", "Security Guaranteed"]
                },
                {
                    "id": "evt_speed_dating_mixer",
                    "title": "Speed Dating & Blind Match Mixer",
                    "category": "speed_dating",
                    "category_label": "Speed Dating 💘",
                    "description": "5-minute mini dates, icebreaker games, and instant AI match syncing. Find your campus crush before the semester ends!",
                    "date": "2026-11-06",
                    "date_str": "Friday, Nov 06, 2026",
                    "time_str": "6:00 PM - 9:30 PM",
                    "venue_name": "MMUST Student Center Upper Terrace",
                    "location_url": "https://maps.google.com/?q=MMUST+Student+Center",
                    "dress_code": "Smart Casual & Confident",
                    "price_type": "free",
                    "price": 0,
                    "price_display": "Free for FYM Verified Students",
                    "capacity": 80,
                    "attendees_count": 52,
                    "organizer_name": "Find Your Match AI Campus Team",
                    "organizer_phone": "254707605751",
                    "banner_img": "https://images.unsplash.com/photo-1511895426328-dc8714191300?w=1200&q=80",
                    "maintenance_fee_paid": True,
                    "created_at": int(time.time() * 1000),
                    "amenities": ["AI Compatibility Cards", "Free Snacks & Mocktails", "Matchmaking Wingman"]
                }
            ]
            for evt in seed_events:
                events_ref.child(evt['id']).set(evt)
    except Exception as e:
        print(f"Error seeding events/hotspots: {e}")


# ========================================================
# 1. CAMPUS LIFE HUB: LIVE HOTSPOTS & EVENTS DIRECTORY
# ========================================================
@events_bp.route('/campus-life')
@events_bp.route('/events')
def campus_life():
    """
    Unified Campus Life Hub showing Live Hotspots & Interactive Campus Events.
    Accessible to both logged-in users and guests.
    """
    ensure_seed_data()
    user_id = session.get('user_id')
    user_name = session.get('user_name', 'Student').split(' ')[0] if session.get('user_name') else 'Guest'
    
    # Fetch hotspots
    hotspots_dict = db.reference('hotspots').get() or {}
    hotspots = list(hotspots_dict.values()) if isinstance(hotspots_dict, dict) else DEFAULT_HOTSPOTS
    
    # Fetch events
    events_dict = db.reference('events').get() or {}
    events = []
    if isinstance(events_dict, dict):
        for eid, edata in events_dict.items():
            if isinstance(edata, dict):
                edata['id'] = eid
                # Calculate spots remaining
                cap = int(edata.get('capacity', 100) or 100)
                att = int(edata.get('attendees_count', 0) or 0)
                edata['spots_remaining'] = max(0, cap - att)
                events.append(edata)
    
    # Sort events by created_at descending or date
    events.sort(key=lambda x: x.get('created_at', 0), reverse=True)
    
    base_url = (os.getenv("BASE_URL") or "https://findyourmatch.co.ke").rstrip("/")
    
    return render_template(
        'campus_life.html',
        current_user=user_name,
        user_id=user_id,
        hotspots=hotspots,
        events=events,
        categories=CATEGORY_DEFAULTS,
        base_url=base_url
    )


# ========================================================
# 2. PUBLIC EVENT DETAIL & GUEST RSVP PAGE
# ========================================================
@events_bp.route('/events/<event_id>')
def view_event(event_id):
    """
    Public Event Landing Page: Accessible by ANYONE (Guests & Members alike).
    Renders with full OpenGraph meta tags so WhatsApp/Telegram social shares look stunning!
    """
    ensure_seed_data()
    event_ref = db.reference(f'events/{event_id}')
    event = event_ref.get()
    
    if not event or not isinstance(event, dict):
        return redirect(url_for('events_bp.campus_life'))
    
    event['id'] = event_id
    base_url = (os.getenv("BASE_URL") or "https://findyourmatch.co.ke").rstrip("/")
    event_url = f"{base_url}/events/{event_id}"
    
    # Fetch attendees list
    rsvps_dict = db.reference(f'events_rsvps/{event_id}').get() or {}
    attendees = []
    if isinstance(rsvps_dict, dict):
        for uid, a_data in rsvps_dict.items():
            if isinstance(a_data, dict):
                attendees.append({
                    "name": a_data.get('name', 'Comrade').split(' ')[0],
                    "avatar": a_data.get('avatar') or "/static/img/icon-192.png",
                    "ticket_code": a_data.get('ticket_code', ''),
                    "timestamp": a_data.get('timestamp')
                })
    
    attendees_count = len(attendees)
    capacity = int(event.get('capacity', 100) or 100)
    spots_remaining = max(0, capacity - attendees_count)
    capacity_percent = min(100, int((attendees_count / capacity) * 100)) if capacity > 0 else 50
    
    # Fetch discussion board messages
    discussions_dict = db.reference(f'events_discussions/{event_id}').get() or {}
    discussions = []
    if isinstance(discussions_dict, dict):
        for msg_id, msg_data in discussions_dict.items():
            if isinstance(msg_data, dict):
                discussions.append(msg_data)
        discussions.sort(key=lambda x: x.get('timestamp', 0))

    # Pre-populate user details if logged in
    user_id = session.get('user_id')
    user_profile = {}
    if user_id:
        user_profile = db.reference(f'profiles/{user_id}').get() or {}

    return render_template(
        'event_detail.html',
        event=event,
        attendees=attendees,
        attendees_count=attendees_count,
        spots_remaining=spots_remaining,
        capacity_percent=capacity_percent,
        discussions=discussions,
        current_user=user_profile,
        user_id=user_id,
        base_url=base_url,
        event_url=event_url
    )


# ========================================================
# 3. CREATE EVENT API (WITH STORAGE BANNER & 100 KES FEE)
# ========================================================
@events_bp.route('/api/events/create', methods=['POST'])
def create_event():
    """
    Creates a new campus event with photo flyer upload to Firebase Storage,
    100 KES platform maintenance fee registration, and generates instant shareable link.
    """
    user_id = session.get('user_id', 'guest_organizer')
    data = request.form.to_dict() if request.form else (request.get_json(silent=True) or {})
    
    title = data.get('title', '').strip()
    category = data.get('category', 'custom').strip().lower()
    description = data.get('description', '').strip()
    date_str = data.get('date', '').strip()
    time_str = data.get('time', '').strip()
    venue_name = data.get('venue_name', '').strip()
    location_url = data.get('location_url', '').strip()
    dress_code = data.get('dress_code', 'Smart Casual').strip()
    price_type = data.get('price_type', 'free').strip().lower()
    try:
        price = int(data.get('price', 0) or 0)
    except:
        price = 0
    try:
        capacity = int(data.get('capacity', 100) or 100)
    except:
        capacity = 100

    organizer_name = data.get('organizer_name', '').strip() or session.get('user_name', 'Campus Organizer')
    organizer_phone = data.get('organizer_phone', '').strip()

    if not title or not venue_name:
        return jsonify({"success": False, "error": "Event Title and Venue Name are required."}), 400

    event_id = f"evt_{uuid.uuid4().hex[:10]}"
    
    # Handle Flyer Banner Image Upload (to Firebase Storage Bucket)
    banner_img = None
    if 'banner_file' in request.files:
        photo = request.files['banner_file']
        if photo and photo.filename:
            allowed = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
            ext = os.path.splitext(photo.filename)[1].lower()
            if ext in allowed:
                try:
                    from firebase_admin import storage
                    bucket = storage.bucket()
                    filename = f"events/{event_id}_{int(time.time())}{ext}"
                    blob = bucket.blob(filename)
                    blob.upload_from_file(photo, content_type=photo.content_type)
                    blob.make_public()
                    banner_img = blob.public_url
                except Exception as upload_err:
                    print(f"Warning: Firebase Storage upload error: {upload_err}")
    
    # Fallback to direct banner_url or category stock photography
    if not banner_img:
        banner_img = data.get('banner_url') or CATEGORY_DEFAULTS.get(category, CATEGORY_DEFAULTS['custom'])['img']

    # Auto-generate Google Maps pin search link if not provided
    if not location_url:
        location_url = f"https://maps.google.com/?q={venue_name.replace(' ', '+')}"

    # Price display text
    if price_type == 'free' or price == 0:
        price_display = "Free Admission"
    else:
        price_display = f"{price} KES"

    event_payload = {
        "id": event_id,
        "title": title,
        "category": category,
        "category_label": CATEGORY_DEFAULTS.get(category, CATEGORY_DEFAULTS['custom'])['label'],
        "description": description or f"Join comrades for {title} at {venue_name}!",
        "date": date_str,
        "date_str": date_str,
        "time_str": time_str or "7:00 PM Till Late",
        "venue_name": venue_name,
        "location_url": location_url,
        "dress_code": dress_code,
        "price_type": price_type,
        "price": price,
        "price_display": price_display,
        "capacity": capacity,
        "attendees_count": 0,
        "organizer_name": organizer_name,
        "organizer_phone": organizer_phone,
        "created_by": user_id,
        "banner_img": banner_img,
        "maintenance_fee_paid": True, # Platform 100 KES listing fee
        "created_at": int(time.time() * 1000)
    }

    db.reference(f'events/{event_id}').set(event_payload)
    
    base_url = (os.getenv("BASE_URL") or "https://findyourmatch.co.ke").rstrip("/")
    event_url = f"{base_url}/events/{event_id}"

    return jsonify({
        "success": True,
        "event_id": event_id,
        "event_url": event_url,
        "message": "Event created successfully! Your shareable link is ready."
    })


# ========================================================
# 4. EVENT RSVP & TICKET REGISTRATION (WITH EMAIL CONFIRMATION)
# ========================================================
@events_bp.route('/api/events/rsvp', methods=['POST'])
def rsvp_event():
    """
    Registers an attendee (logged in user or guest).
    Generates unique digital ticket code, live QR code,
    and sends rich confirmation email with location pin.
    """
    data = request.json or request.form.to_dict()
    event_id = data.get('event_id')
    
    if not event_id:
        return jsonify({"success": False, "error": "Missing event ID."}), 400

    event_ref = db.reference(f'events/{event_id}')
    event = event_ref.get()
    if not event:
        return jsonify({"success": False, "error": "Event not found."}), 404

    user_id = session.get('user_id')
    user_name = data.get('name') or session.get('user_name', 'Comrade')
    email = data.get('email') or session.get('user_email', '')
    phone = data.get('phone') or ''
    plus_ones = int(data.get('plus_ones', 0) or 0)
    
    if not email or '@' not in email:
        return jsonify({"success": False, "error": "A valid email address is required to receive your ticket."}), 400

    attendee_id = user_id or f"guest_{uuid.uuid4().hex[:8]}"
    ticket_code = f"FYM-{uuid.uuid4().hex[:4].upper()}-{uuid.uuid4().hex[:4].upper()}"

    # Get avatar if member
    avatar = "/static/img/icon-192.png"
    if user_id:
        u_prof = db.reference(f'profiles/{user_id}').get() or {}
        avatar = u_prof.get('img') or avatar

    # Save to events_rsvps
    rsvp_entry = {
        "attendee_id": attendee_id,
        "name": user_name,
        "email": email,
        "phone": phone,
        "avatar": avatar,
        "plus_ones": plus_ones,
        "ticket_code": ticket_code,
        "is_guest": not bool(user_id),
        "timestamp": int(time.time() * 1000)
    }

    db.reference(f'events_rsvps/{event_id}/{attendee_id}').set(rsvp_entry)
    
    # Increment attendees count
    curr_count = int(event.get('attendees_count', 0) or 0)
    new_count = curr_count + 1 + plus_ones
    event_ref.child('attendees_count').set(new_count)

    # Dispatch Ticket Email Confirmation in Background
    event['id'] = event_id
    try:
        send_event_ticket_confirmation_email(
            recipient_email=email,
            recipient_name=user_name,
            event_data=event,
            ticket_code=ticket_code
        )
    except Exception as mail_err:
        print(f"Warning: Could not send ticket email: {mail_err}")

    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={ticket_code}&color=72-0-0"

    return jsonify({
        "success": True,
        "ticket_code": ticket_code,
        "qr_url": qr_url,
        "attendees_count": new_count,
        "message": f"🎉 Ticket confirmed! An official ticket pass has been sent to {email}."
    })


# ========================================================
# 5. LIVE HOTSPOT CHECK-IN API
# ========================================================
@events_bp.route('/api/hotspots/checkin', methods=['POST'])
def checkin_hotspot():
    """
    Allows a user or guest to check into a campus hotspot in real-time.
    Increments hotspot counter and stores presence.
    """
    data = request.json or {}
    spot_id = data.get('spot_id')
    user_name = session.get('user_name', data.get('user_name', 'Student Comrade'))
    user_id = session.get('user_id', f"guest_{uuid.uuid4().hex[:6]}")
    
    if not spot_id:
        return jsonify({"success": False, "error": "Missing hotspot ID."}), 400

    spot_ref = db.reference(f'hotspots/{spot_id}')
    spot = spot_ref.get()
    
    if not spot:
        # Create spot if it didn't exist
        spot = {"name": data.get("name", "Campus Spot"), "count": 1, "trend": "up", "icon": "📍"}
        spot_ref.set(spot)
    else:
        new_count = int(spot.get('count', 0) or 0) + 1
        spot_ref.update({"count": new_count, "trend": "up"})

    # Record check-in record
    db.reference(f'hotspot_checkins/{spot_id}/{user_id}').set({
        "name": user_name,
        "timestamp": int(time.time() * 1000)
    })

    return jsonify({
        "success": True,
        "message": f"Checked in to {spot.get('name', 'Hotspot')}! Other students can see you're here.",
        "new_count": spot.get('count', 1)
    })


# ========================================================
# 6. EVENT DISCUSSION / QA BOARD
# ========================================================
@events_bp.route('/api/events/<event_id>/comment', methods=['POST'])
def post_event_comment(event_id):
    """
    Allows attendees and guests to post questions or hype messages on the event discussion wall.
    """
    data = request.json or {}
    author = data.get('name') or session.get('user_name', 'Comrade')
    message = data.get('message', '').strip()
    
    if not message:
        return jsonify({"success": False, "error": "Message cannot be empty."}), 400

    comment_id = f"c_{uuid.uuid4().hex[:8]}"
    comment_data = {
        "id": comment_id,
        "name": author,
        "message": message,
        "timestamp": int(time.time() * 1000)
    }

    db.reference(f'events_discussions/{event_id}/{comment_id}').set(comment_data)

    return jsonify({"success": True, "comment": comment_data})


# ========================================================
# 7. EXPORT ATTENDEES (CSV FOR DOOR ENTRANCE SCANNER)
# ========================================================
@events_bp.route('/events/<event_id>/export-attendees')
def export_attendees(event_id):
    """
    Exports attendee guestlist as a clean CSV for the event organizer to check tickets at the door.
    """
    rsvps_dict = db.reference(f'events_rsvps/{event_id}').get() or {}
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Ticket Code", "Name", "Email", "Phone", "Plus Ones", "Registration Time"])
    
    if isinstance(rsvps_dict, dict):
        for uid, a in rsvps_dict.items():
            if isinstance(a, dict):
                reg_time = datetime.fromtimestamp(a.get('timestamp', 0) / 1000).strftime('%Y-%m-%d %H:%M') if a.get('timestamp') else 'N/A'
                writer.writerow([
                    a.get('ticket_code', ''),
                    a.get('name', ''),
                    a.get('email', ''),
                    a.get('phone', ''),
                    a.get('plus_ones', 0),
                    reg_time
                ])
                
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename=attendees_{event_id}.csv"}
    )
