import os
import re
import time
import uuid
import csv
import io
import threading
import logging
from datetime import datetime, timezone
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, Response, current_app
from app.database import db, initialize_firebase
from app.email_service import send_event_ticket_confirmation_email
from app.payments import initiate_stk_push, check_payment_status, format_phone_number
from app.payout_service import schedule_event_organizer_payout

logger = logging.getLogger(__name__)

events_bp = Blueprint('events_bp', __name__)

def format_event_account_ref(event_title, event_id=None):
    """
    Formats Safaricom Daraja AccountReference for event registration STK push.
    Safaricom strictly restricts AccountReference to max 12 alphanumeric characters.
    - If event title is short enough (<= 12 chars), use the clean name for maximum legitimacy.
    - If long, shorten it cleanly to 12 characters.
    - If missing or invalid, fallback to EVT_<id[:8]>.
    """
    if not event_title:
        return f"EVT_{event_id[:8]}" if event_id else "EventTicket"
    
    # Strip spaces and non-alphanumeric chars (preserving casing for readability)
    clean = re.sub(r'[^a-zA-Z0-9]', '', str(event_title))
    if not clean:
        return f"EVT_{event_id[:8]}" if event_id else "EventTicket"
    
    return clean[:12]

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
    {"id": "spot_lib", "name": "MMUST Library Cafe & Foyer", "count": 0, "trend": "quiet", "icon": "☕", "description": "Quiet study desks & casual catch-ups"},
    {"id": "spot_sc", "name": "Student Center Main Hub", "count": 0, "trend": "quiet", "icon": "🍔", "description": "High campus traffic, fast food & banter"},
    {"id": "spot_sig", "name": "Signature Lounge & Club", "count": 0, "trend": "quiet", "icon": "🍸", "description": "Evening cocktails, DJ beats & weekend vibes"},
    {"id": "spot_sports", "name": "Sports Pavilion & Track", "count": 0, "trend": "quiet", "icon": "🏀", "description": "Afternoon basketball & outdoor fitness"},
    {"id": "spot_boma", "name": "Boma Gardens & Grill", "count": 0, "trend": "quiet", "icon": "🌳", "description": "Chill weekend barbeque & open breeze"}
]


def ensure_seed_data():
    """Ensures base campus hotspot locations exist in database with real baseline."""
    try:
        hotspots_ref = db.reference('hotspots')
        existing_hotspots = hotspots_ref.get()
        if not existing_hotspots:
            for spot in DEFAULT_HOTSPOTS:
                hotspots_ref.child(spot['id']).set(spot)
    except Exception as e:
        logger.warning(f"Error ensuring hotspots: {e}")


# ========================================================
# 1. CAMPUS LIFE HUB: LIVE HOTSPOTS & EVENTS DIRECTORY
# ========================================================
@events_bp.route('/campus-life')
@events_bp.route('/events')
def campus_life():
    """
    Unified Campus Life Hub showing Live Hotspots & Real Campus Events.
    Accessible to both logged-in users and guests.
    """
    ensure_seed_data()
    user_id = session.get('user_id')
    user_name = session.get('user_name', 'Student').split(' ')[0] if session.get('user_name') else 'Guest'
    
    # Fetch real hotspots and calculate real check-in counts
    hotspots_dict = db.reference('hotspots').get() or {}
    checkins_dict = db.reference('hotspot_checkins').get() or {}
    
    hotspots = []
    if isinstance(hotspots_dict, dict) and hotspots_dict:
        for sid, sdata in hotspots_dict.items():
            if isinstance(sdata, dict):
                sdata['id'] = sid
                spot_checkins = checkins_dict.get(sid, {}) if isinstance(checkins_dict, dict) else {}
                real_count = len(spot_checkins) if isinstance(spot_checkins, dict) else int(sdata.get('count', 0) or 0)
                sdata['count'] = real_count
                sdata['trend'] = 'up' if real_count > 0 else 'quiet'
                hotspots.append(sdata)
    else:
        hotspots = DEFAULT_HOTSPOTS
    
    # Fetch real events and compute accurate attendee numbers from real RSVPs
    events_dict = db.reference('events').get() or {}
    rsvps_all = db.reference('events_rsvps').get() or {}
    events = []
    if isinstance(events_dict, dict):
        for eid, edata in events_dict.items():
            if isinstance(edata, dict):
                edata['id'] = eid
                # Calculate real attendees count from actual RSVP records
                event_rsvps = rsvps_all.get(eid, {}) if isinstance(rsvps_all, dict) else {}
                real_att = sum(1 + int(r.get('plus_ones', 0) or 0) for r in event_rsvps.values() if isinstance(r, dict)) if isinstance(event_rsvps, dict) else 0
                edata['attendees_count'] = real_att
                cap = int(edata.get('capacity', 100) or 100)
                edata['spots_remaining'] = max(0, cap - real_att)
                events.append(edata)
    
    # Sort events by created_at descending or date
    events.sort(key=lambda x: x.get('created_at', 0), reverse=True)
    
    # Platform event creation fee (controlled dynamically by super admin)
    system_settings = db.reference('system_settings').get() or {}
    try:
        event_creation_fee = max(0, int(system_settings.get('event_creation_fee', 100)))
    except (ValueError, TypeError):
        event_creation_fee = 100
        
    base_url = (os.getenv("BASE_URL") or "https://findyourmatch.co.ke").rstrip("/")
    
    return render_template(
        'campus_life.html',
        current_user=user_name,
        user_id=user_id,
        hotspots=hotspots,
        events=events,
        categories=CATEGORY_DEFAULTS,
        event_creation_fee=event_creation_fee,
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
    
    # Compute real attendees including registered plus ones
    attendees_count = sum(1 + int(a_data.get('plus_ones', 0) or 0) for a_data in rsvps_dict.values() if isinstance(a_data, dict)) if isinstance(rsvps_dict, dict) else 0
    capacity = int(event.get('capacity', 100) or 100)
    spots_remaining = max(0, capacity - attendees_count)
    capacity_percent = min(100, int((attendees_count / capacity) * 100)) if capacity > 0 else 0
    
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

    # Check if current user is the Event Admin or Super Admin
    is_super_admin = bool(session.get('is_super_admin') or session.get('account_type') == 'super_admin' or user_profile.get('is_super_admin'))
    if not is_super_admin and user_id:
        super_admins = db.reference('super_admins').get() or {}
        if user_id in super_admins:
            is_super_admin = True

    organizer_phone_clean = str(event.get('organizer_phone', '')).replace('+', '').replace(' ', '').strip()
    user_phone_clean = str(user_profile.get('phone', '')).replace('+', '').replace(' ', '').strip()

    is_event_admin = bool(
        is_super_admin or
        (user_id and event.get('created_by') == user_id) or
        (user_phone_clean and organizer_phone_clean and user_phone_clean == organizer_phone_clean) or
        request.args.get('admin') == '1'
    )

    admin_guestlist = []
    admitted_count = 0
    if isinstance(rsvps_dict, dict):
        for aid, a_data in rsvps_dict.items():
            if isinstance(a_data, dict):
                is_in = bool(a_data.get('checked_in'))
                if is_in:
                    admitted_count += 1 + int(a_data.get('plus_ones', 0) or 0)
                
                check_in_time_str = ""
                if a_data.get('checked_in_at'):
                    try:
                        check_in_time_str = datetime.fromtimestamp(a_data['checked_in_at'] / 1000).strftime('%I:%M %p')
                    except:
                        check_in_time_str = "Admitted"

                reg_time_str = ""
                if a_data.get('timestamp'):
                    try:
                        reg_time_str = datetime.fromtimestamp(a_data['timestamp'] / 1000).strftime('%b %d, %I:%M %p')
                    except:
                        reg_time_str = ""

                admin_guestlist.append({
                    "attendee_id": aid,
                    "name": a_data.get('name', 'Attendee'),
                    "email": a_data.get('email', ''),
                    "phone": a_data.get('phone', ''),
                    "avatar": a_data.get('avatar') or "/static/img/icon-192.png",
                    "ticket_code": a_data.get('ticket_code', ''),
                    "lovi_code": a_data.get('lovi_code', ''),
                    "plus_ones": a_data.get('plus_ones', 0),
                    "checked_in": is_in,
                    "checked_in_at": a_data.get('checked_in_at'),
                    "checked_in_at_str": check_in_time_str,
                    "checked_in_by": a_data.get('checked_in_by', ''),
                    "paid": a_data.get('paid', False),
                    "amount_paid": a_data.get('amount_paid', 0),
                    "mpesa_receipt": a_data.get('mpesa_receipt', ''),
                    "timestamp": a_data.get('timestamp'),
                    "timestamp_str": reg_time_str
                })

    if admin_guestlist:
        # Sort pending arrivals first, then by registration timestamp descending
        admin_guestlist.sort(key=lambda x: (1 if x.get('checked_in') else 0, -(x.get('timestamp') or 0)))

    pending_count = max(0, attendees_count - admitted_count)

    return render_template(
        'event_detail.html',
        event=event,
        attendees=attendees,
        attendees_count=attendees_count,
        admitted_count=admitted_count,
        pending_count=pending_count,
        spots_remaining=spots_remaining,
        capacity_percent=capacity_percent,
        discussions=discussions,
        current_user=user_profile,
        user_id=user_id,
        is_event_admin=is_event_admin,
        admin_guestlist=admin_guestlist,
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

    # Platform event creation fee set by super admin
    system_settings = db.reference('system_settings').get() or {}
    try:
        event_creation_fee = max(0, int(system_settings.get('event_creation_fee', 100)))
    except (ValueError, TypeError):
        event_creation_fee = 100

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
        "creation_fee": event_creation_fee,
        "maintenance_fee_paid": True, # Platform listing fee recorded
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
def finalize_event_ticket(event_id: str, attendee_data: dict, receipt: str = None, amount: int = 0):
    """
    Finalizes an event registration:
    1. Generates unique ticket_code and door lovi_code
    2. Writes to events_rsvps, tickets_lookup, and lovi_lookup
    3. Increments event attendees_count
    4. Dispatches confirmation email with QR and LOVI Code
    5. If amount > 0, schedules 2-MINUTE AUTOMATIC PAYOUT to the event admin's phone number!
    """
    event_ref = db.reference(f'events/{event_id}')
    event = event_ref.get() or {}
    event['id'] = event_id

    user_name = attendee_data.get('name') or attendee_data.get('attendee_name') or 'Comrade'
    email = attendee_data.get('email', '')
    phone = attendee_data.get('phone', '')
    plus_ones = int(attendee_data.get('plus_ones', 0) or 0)
    user_id = attendee_data.get('user_id')
    attendee_id = user_id or f"guest_{uuid.uuid4().hex[:8]}"

    ticket_code = f"FYM-{uuid.uuid4().hex[:4].upper()}-{uuid.uuid4().hex[:4].upper()}"
    lovi_code = f"LOVI-{uuid.uuid4().hex[:4].upper()}"

    avatar = "/static/img/icon-192.png"
    if user_id:
        u_prof = db.reference(f'profiles/{user_id}').get() or {}
        avatar = u_prof.get('img') or avatar

    rsvp_entry = {
        "attendee_id": attendee_id,
        "name": user_name,
        "email": email,
        "phone": phone,
        "avatar": avatar,
        "plus_ones": plus_ones,
        "ticket_code": ticket_code,
        "lovi_code": lovi_code,
        "checked_in": False,
        "checked_in_at": None,
        "is_guest": not bool(user_id),
        "paid": bool(amount > 0),
        "amount_paid": amount,
        "mpesa_receipt": receipt,
        "timestamp": int(time.time() * 1000)
    }

    db.reference(f'events_rsvps/{event_id}/{attendee_id}').set(rsvp_entry)

    lookup_record = {
        "ticket_code": ticket_code,
        "lovi_code": lovi_code,
        "event_id": event_id,
        "attendee_id": attendee_id,
        "name": user_name,
        "email": email,
        "phone": phone,
        "plus_ones": plus_ones,
        "paid": bool(amount > 0),
        "amount_paid": amount,
        "mpesa_receipt": receipt,
        "checked_in": False,
        "checked_in_at": None,
        "timestamp": int(time.time() * 1000)
    }
    db.reference(f'tickets_lookup/{ticket_code}').set(lookup_record)
    db.reference(f'lovi_lookup/{lovi_code}').set(lookup_record)

    # Increment attendees count
    curr_count = int(event.get('attendees_count', 0) or 0)
    new_count = curr_count + 1 + plus_ones
    event_ref.child('attendees_count').set(new_count)

    # Dispatch Ticket Email in Background Thread
    try:
        email_kwargs = {
            "recipient_email": email,
            "recipient_name": user_name,
            "event_data": dict(event),
            "ticket_code": ticket_code,
            "lovi_code": lovi_code
        }
        threading.Thread(target=send_event_ticket_confirmation_email, kwargs=email_kwargs, daemon=True).start()
    except Exception as mail_err:
        logger.warning(f"Could not launch email thread: {mail_err}")

    # Build QR and verification URLs
    base_url = (os.getenv("BASE_URL") or "https://findyourmatch.co.ke").rstrip("/")
    verify_url = f"{base_url}/events/verify-ticket/{ticket_code}"
    import urllib.parse
    encoded_verify_url = urllib.parse.quote(verify_url, safe='')
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=280x280&data={encoded_verify_url}&color=72-0-0"

    # =========================================================================
    # 2-MINUTE AUTOMATIC PAYOUT TO EVENT ORGANIZER/ADMIN NUMBER
    # =========================================================================
    if amount > 0:
        organizer_phone = event.get('organizer_phone')
        logger.info(f"💰 Ticket fee of KES {amount} received! Scheduling payout to organizer {organizer_phone} in 2 minutes (120s)...")
        schedule_event_organizer_payout(
            event_id=event_id,
            ticket_code=ticket_code,
            amount=amount,
            organizer_phone=organizer_phone,
            delay_seconds=120
        )

    return {
        "ticket_code": ticket_code,
        "lovi_code": lovi_code,
        "qr_url": qr_url,
        "verify_url": verify_url,
        "attendees_count": new_count
    }


@events_bp.route('/api/events/rsvp', methods=['POST'])
def rsvp_event():
    """
    Registers an attendee for an event.
    - If event is free: instantly confirms and issues ticket pass with QR and LOVI code.
    - If event is paid: initiates M-Pesa STK push. Once paid, funds are directed to event admin
      number 2 minutes later automatically via M-Pesa B2C.
    """
    data = request.json or request.form.to_dict()
    event_id = data.get('event_id')

    if not event_id:
        return jsonify({"success": False, "error": "Missing event ID."}), 400

    event_ref = db.reference(f'events/{event_id}')
    event = event_ref.get()
    if not event or not isinstance(event, dict):
        return jsonify({"success": False, "error": "Event not found."}), 404

    user_id = session.get('user_id')
    user_name = (data.get('name') or session.get('user_name', 'Comrade')).strip()
    email = (data.get('email') or session.get('user_email', '')).strip()
    phone = (data.get('phone') or '').strip()
    plus_ones = int(data.get('plus_ones', 0) or 0)

    if not email or '@' not in email:
        return jsonify({"success": False, "error": "A valid email address is required to receive your ticket."}), 400

    # Check capacity
    capacity = int(event.get('capacity', 100) or 100)
    current_attendees = int(event.get('attendees_count', 0) or 0)
    if current_attendees + 1 + plus_ones > capacity:
        return jsonify({"success": False, "error": "Sorry, this event is at maximum capacity!"}), 400

    price_type = str(event.get('price_type', 'free')).lower()
    try:
        price = int(event.get('price', 0) or 0)
    except:
        price = 0

    total_tickets = 1 + plus_ones
    total_amount = price * total_tickets

    # If PAID event, initiate STK Push
    if price > 0 and price_type != 'free':
        formatted_phone = format_phone_number(phone)
        if not formatted_phone or len(formatted_phone) != 12:
            return jsonify({"success": False, "error": "Please provide a valid M-Pesa phone number (e.g. 07XXXXXXXX or 01XXXXXXXX)."}), 400

        callback_url = "https://www.findyourmatch.co.ke/api/mpesa/event_callback"
        event_title = event.get('title', '').strip()
        account_ref = format_event_account_ref(event_title, event_id)
        desc = f"{account_ref[:8]} Pass" if account_ref else "Event Ticket"
        logger.info(f"Initiating STK push of KES {total_amount} to {formatted_phone} for event '{event_title}' (AccountRef: '{account_ref}')...")
        res = initiate_stk_push(formatted_phone, total_amount, account_ref, callback_url, desc)

        if not res or 'error' in res:
            err_msg = res.get('error', 'Failed to initiate M-Pesa prompt.') if res else 'Payment gateway error.'
            return jsonify({"success": False, "error": f"M-Pesa Error: {err_msg}"}), 400

        checkout_id = res.get('CheckoutRequestID')
        if not checkout_id:
            return jsonify({"success": False, "error": "Did not receive valid CheckoutRequestID from Safaricom."}), 400

        db.reference(f'pending_event_payments/{checkout_id}').set({
            "checkout_id": checkout_id,
            "event_id": event_id,
            "event_title": event_title,
            "account_reference": account_ref,
            "amount": total_amount,
            "attendee_name": user_name,
            "name": user_name,
            "email": email,
            "phone": formatted_phone,
            "plus_ones": plus_ones,
            "user_id": user_id,
            "organizer_phone": event.get('organizer_phone'),
            "status": "pending",
            "created_at": int(time.time() * 1000)
        })

        return jsonify({
            "success": True,
            "requires_payment": True,
            "checkout_id": checkout_id,
            "amount": total_amount,
            "phone": formatted_phone,
            "message": f"📱 M-Pesa prompt of KES {total_amount} sent to {formatted_phone}. Enter your M-Pesa PIN on your phone to complete your ticket reservation."
        })

    # Otherwise FREE event
    attendee_data = {
        "name": user_name,
        "email": email,
        "phone": phone,
        "plus_ones": plus_ones,
        "user_id": user_id
    }
    ticket_info = finalize_event_ticket(event_id, attendee_data, receipt="FREE_ADMISSION", amount=0)

    return jsonify({
        "success": True,
        "requires_payment": False,
        "ticket_code": ticket_info['ticket_code'],
        "lovi_code": ticket_info['lovi_code'],
        "qr_url": ticket_info['qr_url'],
        "verify_url": ticket_info['verify_url'],
        "attendees_count": ticket_info['attendees_count'],
        "message": f"🎉 Ticket confirmed! An official ticket pass with QR Code & LOVI Code has been emailed to {email}."
    })


@events_bp.route('/api/events/check-payment/<checkout_id>', methods=['GET'])
def check_event_payment_status(checkout_id):
    """
    Real-time status poller for event ticket payment.
    Queries pending_event_payments and falls back to Safaricom query API if webhook is pending.
    """
    pending_ref = db.reference(f'pending_event_payments/{checkout_id}')
    payment_record = pending_ref.get()
    if not payment_record or not isinstance(payment_record, dict):
        return jsonify({"success": False, "status": "NOT_FOUND", "error": "Payment record not found."}), 404

    status = payment_record.get('status')
    if status == 'success':
        return jsonify({
            "success": True,
            "status": "COMPLETED",
            "ticket_code": payment_record.get('ticket_code'),
            "lovi_code": payment_record.get('lovi_code'),
            "qr_url": payment_record.get('qr_url'),
            "verify_url": payment_record.get('verify_url'),
            "message": "Payment confirmed! Your ticket pass is ready."
        })
    elif status == 'failed':
        return jsonify({
            "success": False,
            "status": "FAILED",
            "error": payment_record.get('reason') or "Payment was not completed."
        })

    # If still pending, query Safaricom directly to catch dropped webhooks
    query_res = check_payment_status(checkout_id)
    if query_res.get('status') == 'SUCCESS':
        event_id = payment_record.get('event_id')
        amount = payment_record.get('amount', 0)
        receipt = query_res.get('receipt') or "QUERY_SUCCESS"
        ticket_info = finalize_event_ticket(event_id, payment_record, receipt=receipt, amount=amount)

        pending_ref.update({
            "status": "success",
            "receipt": receipt,
            "ticket_code": ticket_info['ticket_code'],
            "lovi_code": ticket_info['lovi_code'],
            "qr_url": ticket_info['qr_url'],
            "verify_url": ticket_info['verify_url'],
            "completed_at": int(time.time() * 1000)
        })
        return jsonify({
            "success": True,
            "status": "COMPLETED",
            "ticket_code": ticket_info['ticket_code'],
            "lovi_code": ticket_info['lovi_code'],
            "qr_url": ticket_info['qr_url'],
            "verify_url": ticket_info['verify_url'],
            "message": "Payment verified! Your ticket pass is ready."
        })
    elif query_res.get('status') in ['CANCELED', 'FAILED']:
        reason = query_res.get('reason', 'Payment cancelled')
        pending_ref.update({"status": "failed", "reason": reason})
        return jsonify({"success": False, "status": "FAILED", "error": reason})

    return jsonify({"success": True, "status": "PENDING", "message": "Waiting for PIN entry..."})


@events_bp.route('/api/mpesa/event_callback', methods=['POST'])
def mpesa_event_callback():
    """
    Webhook called by Safaricom when attendee enters PIN for an event ticket.
    Finalizes ticket pass and schedules 2-minute organizer payout.
    """
    data = request.get_json(silent=True) or {}
    try:
        body = data.get('Body', {})
        stk_callback = body.get('stkCallback', {})
        if not stk_callback:
            return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"})

        result_code = stk_callback.get('ResultCode')
        checkout_id = stk_callback.get('CheckoutRequestID')

        pending_ref = db.reference(f'pending_event_payments/{checkout_id}')
        payment_record = pending_ref.get()
        if not payment_record or not isinstance(payment_record, dict):
            return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"})

        if payment_record.get('status') == 'success':
            return jsonify({"ResultCode": 0, "ResultDesc": "Already processed"})

        if result_code == 0:
            metadata = stk_callback.get('CallbackMetadata', {}).get('Item', [])
            receipt = next((item['Value'] for item in metadata if item['Name'] == 'MpesaReceiptNumber'), None)
            amount = next((item['Value'] for item in metadata if item['Name'] == 'Amount'), payment_record.get('amount', 0))

            event_id = payment_record.get('event_id')
            ticket_info = finalize_event_ticket(event_id, payment_record, receipt=receipt, amount=amount)

            pending_ref.update({
                "status": "success",
                "receipt": receipt,
                "ticket_code": ticket_info['ticket_code'],
                "lovi_code": ticket_info['lovi_code'],
                "qr_url": ticket_info['qr_url'],
                "verify_url": ticket_info['verify_url'],
                "completed_at": int(time.time() * 1000)
            })
            logger.info(f"✅ EVENT TICKET ISSUED via callback: {ticket_info['ticket_code']} receipt={receipt}")
        else:
            fail_desc = stk_callback.get('ResultDesc', 'Payment failed')
            pending_ref.update({
                "status": "failed",
                "reason": fail_desc,
                "result_code": result_code
            })
    except Exception as e:
        logger.error(f"Error in mpesa_event_callback: {e}")

    return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"})



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
# 7. TICKET & LOVI CODE VERIFICATION (DOOR ADMIN PORTAL)
# ========================================================
def find_ticket_record(code: str):
    """
    Looks up a ticket by either Ticket Code (FYM-XXXX-YYYY) or Door LOVI Code (LOVI-XXXX).
    Case-insensitive, trims whitespace, handles leading/trailing spaces.
    Returns (ticket_record, event_data, error_msg)
    """
    if not code:
        return None, None, "No ticket or LOVI code provided."
    
    clean_code = code.strip().upper()
    
    # 1. Direct tickets_lookup
    ticket_record = db.reference(f'tickets_lookup/{clean_code}').get()
    
    # 2. Direct lovi_lookup
    if not ticket_record:
        ticket_record = db.reference(f'lovi_lookup/{clean_code}').get()
        
    # 3. Check if user typed code without 'LOVI-' prefix (e.g. 4 hex characters)
    if not ticket_record and not clean_code.startswith("LOVI-") and len(clean_code) == 4:
        ticket_record = db.reference(f'lovi_lookup/LOVI-{clean_code}').get()

    # 4. Fallback search across events_rsvps in case index is missing
    if not ticket_record:
        events_dict = db.reference('events_rsvps').get() or {}
        if isinstance(events_dict, dict):
            for eid, attendees in events_dict.items():
                if isinstance(attendees, dict):
                    for aid, a in attendees.items():
                        if isinstance(a, dict):
                            t_code = (a.get('ticket_code') or '').strip().upper()
                            l_code = (a.get('lovi_code') or '').strip().upper()
                            if clean_code in (t_code, l_code) or clean_code == f"LOVI-{l_code}":
                                ticket_record = {
                                    "ticket_code": t_code or clean_code,
                                    "lovi_code": l_code or f"LOVI-{clean_code[-4:]}",
                                    "event_id": eid,
                                    "attendee_id": aid,
                                    "name": a.get('name', 'Attendee'),
                                    "email": a.get('email', ''),
                                    "phone": a.get('phone', ''),
                                    "plus_ones": a.get('plus_ones', 0),
                                    "checked_in": a.get('checked_in', False),
                                    "checked_in_at": a.get('checked_in_at'),
                                    "timestamp": a.get('timestamp')
                                }
                                break
                    if ticket_record:
                        break

    if not ticket_record:
        return None, None, f"No ticket or registration found matching code '{code}'."

    # Fetch event details
    event_id = ticket_record.get('event_id')
    event_data = {}
    if event_id:
        event_data = db.reference(f'events/{event_id}').get() or {}
        event_data['id'] = event_id
        
    return ticket_record, event_data, None


@events_bp.route('/events/verify-ticket/<ticket_code>', methods=['GET'])
@events_bp.route('/events/verify-ticket', methods=['GET'])
def verify_ticket_page(ticket_code=None):
    """
    Dedicated door entrance scanner & ticket verification portal for Event Admins / Managers.
    Opened directly when scanning the QR code with any phone camera, or by manually typing LOVI code.
    Also displays the live guestlist roster with one-click admission fallback.
    """
    base_url = (os.getenv("BASE_URL") or "https://findyourmatch.co.ke").rstrip("/")
    query_code = ticket_code or request.args.get('code') or request.args.get('ticket') or request.args.get('lovi')
    event_id = request.args.get('event') or request.args.get('event_id')
    
    ticket = None
    event = None
    status = 'PROMPT' # Default state if no code provided yet
    error_msg = None
    
    if query_code:
        ticket, event, error_msg = find_ticket_record(query_code)
        if ticket:
            if ticket.get('checked_in'):
                status = 'ALREADY_CHECKED_IN'
            else:
                status = 'VALID'
            if not event_id and ticket.get('event_id'):
                event_id = ticket.get('event_id')
        else:
            status = 'NOT_FOUND'

    # Fetch event by ID if provided or derived
    if not event and event_id:
        event = db.reference(f'events/{event_id}').get() or {}
        if event:
            event['id'] = event_id

    # Fetch all events created by admin (or all events for super admin)
    user_id = session.get('user_id')
    user_profile = db.reference(f'profiles/{user_id}').get() or {} if user_id else {}
    is_super_admin = bool(session.get('is_super_admin') or session.get('account_type') == 'super_admin' or user_profile.get('is_super_admin'))
    
    all_events_raw = db.reference('events').get() or {}
    admin_events = []
    if isinstance(all_events_raw, dict):
        for eid, edata in all_events_raw.items():
            if isinstance(edata, dict):
                edata['id'] = eid
                admin_events.append(edata)
        admin_events.sort(key=lambda x: x.get('created_at', 0), reverse=True)

    if not event and admin_events:
        event = admin_events[0]
        event_id = event['id']

    # Load attendee roster for this active event
    attendees_list = []
    admitted_count = 0
    total_registered = 0
    if event_id:
        rsvps_dict = db.reference(f'events_rsvps/{event_id}').get() or {}
        if isinstance(rsvps_dict, dict):
            for aid, a in rsvps_dict.items():
                if isinstance(a, dict):
                    count_delta = 1 + int(a.get('plus_ones', 0) or 0)
                    total_registered += count_delta
                    is_in = bool(a.get('checked_in'))
                    if is_in:
                        admitted_count += count_delta
                    
                    check_in_time_str = ""
                    if a.get('checked_in_at'):
                        try:
                            check_in_time_str = datetime.fromtimestamp(a['checked_in_at'] / 1000).strftime('%I:%M %p')
                        except:
                            check_in_time_str = "Admitted"

                    attendees_list.append({
                        "attendee_id": aid,
                        "name": a.get('name', 'Attendee'),
                        "email": a.get('email', ''),
                        "phone": a.get('phone', ''),
                        "avatar": a.get('avatar') or "/static/img/icon-192.png",
                        "ticket_code": a.get('ticket_code', ''),
                        "lovi_code": a.get('lovi_code', ''),
                        "plus_ones": a.get('plus_ones', 0),
                        "checked_in": is_in,
                        "checked_in_at": a.get('checked_in_at'),
                        "checked_in_at_str": check_in_time_str,
                        "checked_in_by": a.get('checked_in_by', ''),
                        "paid": a.get('paid', False),
                        "timestamp": a.get('timestamp')
                    })
        # Sort pending arrivals first, then newest
        attendees_list.sort(key=lambda x: (1 if x.get('checked_in') else 0, -(x.get('timestamp') or 0)))

    pending_count = max(0, total_registered - admitted_count)

    return render_template(
        'event_ticket_verify.html',
        ticket=ticket,
        event=event,
        status=status,
        query_code=query_code or '',
        error_msg=error_msg,
        base_url=base_url,
        event_id=event_id,
        attendees_list=attendees_list,
        admitted_count=admitted_count,
        pending_count=pending_count,
        total_registered=total_registered,
        admin_events=admin_events
    )


@events_bp.route('/api/events/verify-ticket', methods=['POST'])
def api_verify_ticket():
    """
    Real-time AJAX endpoint to verify a Ticket Code or LOVI Code instantly without full page reload.
    """
    data = request.json or {}
    code = data.get('code', '').strip()
    if not code:
        return jsonify({"success": False, "error": "Please provide a ticket code or LOVI code."}), 400
        
    ticket, event, error_msg = find_ticket_record(code)
    if not ticket:
        return jsonify({"success": False, "status": "NOT_FOUND", "error": error_msg or "Ticket not found."}), 404
        
    status = "ALREADY_CHECKED_IN" if ticket.get('checked_in') else "VALID"
    return jsonify({
        "success": True,
        "status": status,
        "ticket": ticket,
        "event": event
    })


@events_bp.route('/api/events/checkin-ticket', methods=['POST'])
def checkin_ticket():
    """
    Door Entrance Check-in Action:
    Marks attendee as admitted/checked in, sets timestamp, records admin,
    and updates tickets_lookup, lovi_lookup, and events_rsvps.
    """
    data = request.json or {}
    code = data.get('code') or data.get('ticket_code') or data.get('lovi_code')
    
    # Fallback to direct event_id and attendee_id if called from roster table
    if not code and data.get('event_id') and data.get('attendee_id'):
        eid = data['event_id']
        aid = data['attendee_id']
        att_rec = db.reference(f'events_rsvps/{eid}/{aid}').get() or {}
        code = att_rec.get('ticket_code') or att_rec.get('lovi_code')

    if not code:
        return jsonify({"success": False, "error": "Missing ticket or LOVI code."}), 400

    ticket, event, err = find_ticket_record(code)
    if not ticket:
        return jsonify({"success": False, "error": err or "Ticket not found."}), 404

    ticket_code = ticket.get('ticket_code')
    lovi_code = ticket.get('lovi_code')
    event_id = ticket.get('event_id')
    attendee_id = ticket.get('attendee_id')

    if ticket.get('checked_in'):
        check_time_str = "earlier"
        if ticket.get('checked_in_at'):
            check_time_str = datetime.fromtimestamp(ticket['checked_in_at'] / 1000).strftime('%I:%M %p')
        return jsonify({
            "success": False,
            "already_checked_in": True,
            "error": f"⚠️ Attendee was already admitted at {check_time_str}! Do not allow duplicate entry.",
            "ticket": ticket
        }), 409

    now_ms = int(time.time() * 1000)
    admin_name = session.get('user_name', 'Event Admin / Door Manager')

    updates = {
        "checked_in": True,
        "checked_in_at": now_ms,
        "checked_in_by": admin_name
    }

    if ticket_code:
        db.reference(f'tickets_lookup/{ticket_code}').update(updates)
    if lovi_code:
        db.reference(f'lovi_lookup/{lovi_code}').update(updates)
    if event_id and attendee_id:
        db.reference(f'events_rsvps/{event_id}/{attendee_id}').update(updates)

    ticket.update(updates)

    # Compute updated live admitted count
    updated_admitted = 0
    if event_id:
        rsvps_dict = db.reference(f'events_rsvps/{event_id}').get() or {}
        if isinstance(rsvps_dict, dict):
            updated_admitted = sum(1 + int(a.get('plus_ones', 0) or 0) for a in rsvps_dict.values() if isinstance(a, dict) and a.get('checked_in'))

    return jsonify({
        "success": True,
        "message": f"✅ {ticket.get('name', 'Attendee')} ({lovi_code}) successfully admitted!",
        "ticket": ticket,
        "attendee_id": attendee_id,
        "ticket_code": ticket_code,
        "lovi_code": lovi_code,
        "admitted_count": updated_admitted,
        "checked_in_at": now_ms,
        "checked_in_at_str": datetime.fromtimestamp(now_ms / 1000).strftime('%I:%M %p')
    })


# ========================================================
# 8. EXPORT ATTENDEES (CSV FOR DOOR ENTRANCE SCANNER)
# ========================================================
@events_bp.route('/events/<event_id>/export-attendees')
def export_attendees(event_id):
    """
    Exports attendee guestlist as a clean CSV for the event organizer to check tickets at the door.
    Includes both Ticket Code and Door LOVI Code.
    """
    rsvps_dict = db.reference(f'events_rsvps/{event_id}').get() or {}
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Ticket Code", "LOVI Code", "Name", "Email", "Phone",
        "Plus Ones", "Checked In", "Check-in Time", "Registration Time"
    ])
    
    if isinstance(rsvps_dict, dict):
        for uid, a in rsvps_dict.items():
            if isinstance(a, dict):
                reg_time = datetime.fromtimestamp(a.get('timestamp', 0) / 1000).strftime('%Y-%m-%d %H:%M') if a.get('timestamp') else 'N/A'
                checked_time = datetime.fromtimestamp(a.get('checked_in_at', 0) / 1000).strftime('%Y-%m-%d %H:%M') if a.get('checked_in_at') else '-'
                writer.writerow([
                    a.get('ticket_code', ''),
                    a.get('lovi_code', ''),
                    a.get('name', ''),
                    a.get('email', ''),
                    a.get('phone', ''),
                    a.get('plus_ones', 0),
                    'YES' if a.get('checked_in') else 'NO',
                    checked_time,
                    reg_time
                ])
                
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename=attendees_{event_id}.csv"}
    )

