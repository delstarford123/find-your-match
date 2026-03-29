import os
import sys
import logging
from collections import defaultdict
from datetime import datetime

# 1. Configure Production Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Ensure Python can find the app folder
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

try:
    from app.database import get_all_schedules
except ImportError:
    logger.error("Failed to import 'get_all_schedules'. Ensure you are running this from the correct directory.")
    get_all_schedules = lambda: [] # Fallback for local testing if DB is down

def load_schedules() -> list:
    """Safely loads schedule data from Firebase."""
    try:
        schedules = get_all_schedules()
        if not schedules:
            logger.info("No schedule data found in Firebase.")
            return []
        return schedules
    except Exception as e:
        logger.error(f"Failed to fetch schedules from database: {e}")
        return []

def get_overlap_minutes(start1: str, end1: str, start2: str, end2: str) -> int:
    """
    Calculates the exact overlap in minutes between two time blocks.
    Returns 0 if there is no overlap or if the time formats are invalid.
    """
    fmt = "%H:%M"
    try:
        t_start1 = datetime.strptime(start1, fmt)
        t_end1 = datetime.strptime(end1, fmt)
        t_start2 = datetime.strptime(start2, fmt)
        t_end2 = datetime.strptime(end2, fmt)
    except ValueError as e:
        logger.warning(f"Invalid time format detected (Expected HH:MM). Skipping block. Error: {e}")
        return 0

    # Ensure end time is strictly after start time
    if t_end1 <= t_start1 or t_end2 <= t_start2:
        return 0

    latest_start = max(t_start1, t_start2)
    earliest_end = min(t_end1, t_end2)

    if latest_start < earliest_end:
        overlap_seconds = (earliest_end - latest_start).total_seconds()
        return int(overlap_seconds / 60)
        
    return 0

def get_schedule_matches(target_user_id: str, min_overlap_minutes: int = 30) -> dict:
    """
    Finds all students who have at least 'min_overlap_minutes' of free time 
    overlapping with the target user. Optimized for scale.
    """
    schedules = load_schedules()
    if not schedules:
        return {}

    # 1. Separate Target User's blocks and group everyone else's by DAY OF WEEK.
    # This optimization changes the search from O(N*M) to O(N*K) where K is a tiny fraction.
    target_blocks = []
    others_by_day = defaultdict(list)

    for block in schedules:
        # Validate that the block has the required keys to prevent crashes
        if not all(k in block for k in ("user_id", "day_of_week", "start_time", "end_time")):
            continue
            
        if block['user_id'] == target_user_id:
            target_blocks.append(block)
        else:
            others_by_day[block['day_of_week']].append(block)

    if not target_blocks:
        logger.info(f"Target user '{target_user_id}' has no schedule configured.")
        return {}

    matched_users = defaultdict(list)

    # 2. Process Matches (Only comparing blocks on the exact same day)
    for my_block in target_blocks:
        day = my_block['day_of_week']
        
        # If no one else is free on this day, skip immediately
        if day not in others_by_day:
            continue
            
        for other_block in others_by_day[day]:
            overlap = get_overlap_minutes(
                my_block['start_time'], my_block['end_time'],
                other_block['start_time'], other_block['end_time']
            )
            
            if overlap >= min_overlap_minutes:
                matched_users[other_block['user_id']].append({
                    "day": day,
                    "overlap_minutes": overlap,
                    "target_user_block": f"{my_block['start_time']} - {my_block['end_time']}",
                    "match_user_block": f"{other_block['start_time']} - {other_block['end_time']}"
                })

    # Return as standard dict for easier JSON serialization in Flask
    return dict(matched_users)

if __name__ == "__main__":
    print("\n--- MMUST Schedule Matcher ---")
    
    # Mock data injection for local testing if DB is empty
    test_target = "MMUST_001"
    matches = get_schedule_matches(test_target)
    
    if matches:
        print(f"✅ Found schedule matches for {test_target}:")
        import json
        print(json.dumps(matches, indent=2))
    else:
        print(f"❌ No viable matches found for {test_target} (Min 30 mins required).")