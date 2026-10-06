"""
app/pricing.py
==============
Centralised pricing engine for FindYourMatch.
All payment amounts, access rules, and gender-based logic live here.
Import from this file everywhere — never hardcode amounts.
"""

# ==========================================
# PRICING CONSTANTS
# ==========================================

# Student subscription (existing — DO NOT CHANGE)
STUDENT_SUBSCRIPTION_AMOUNT = 150          # KSH — male students only

# Sponsor registration (non-student one-time fee)
SPONSOR_REGISTRATION_AMOUNT = 1000         # KSH — ALL sponsors (male & female)

# Sponsors Room access for students (monthly)
SPONSORS_ROOM_MALE_AMOUNT   = 200          # KSH — male students
SPONSORS_ROOM_FEMALE_AMOUNT = 0            # KSH — free for female students

# Sponsors Room access duration
SPONSORS_ROOM_ACCESS_DAYS   = 30           # days per payment


def get_sponsor_registration_fee(gender: str) -> int:
    """
    Returns the registration fee for a sponsor.
    ALL sponsors (male and female) pay 1000 KSH — only female STUDENTS are free.
    """
    return SPONSOR_REGISTRATION_AMOUNT


def get_sponsors_room_fee(gender: str) -> int:
    """
    Returns the Sponsors Room access fee for a student.
    - Female students: FREE (0 KSH)
    - Male students:   200 KSH/month
    """
    g = str(gender).strip().lower()
    if g in ("female", "f"):
        return SPONSORS_ROOM_FEMALE_AMOUNT
    return SPONSORS_ROOM_MALE_AMOUNT


def is_sponsors_room_free(gender: str) -> bool:
    """Returns True if this student gets free Sponsors Room access."""
    return get_sponsors_room_fee(gender) == 0


def is_sponsor_registration_free(gender: str) -> bool:
    """Sponsors are NEVER free — always returns False."""
    return False
