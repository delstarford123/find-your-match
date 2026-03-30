import os
import sys
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import List, Dict, Any

# 1. Configure Production Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Ensure Python can find the app folder
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

try:
    from app.database import get_all_schedules
except ImportError:
    logger.error("Failed to import 'get_all_schedules'. Ensure you are running this from the correct directory.")
    # Mock fallback for development/Render logs
    def get_all_schedules(): return []

def get_overlap_minutes(start1: str, end1: str, start2: str, end2: str) -> int:
    """
    Calculates overlap in minutes. Standardized to HH:MM format.
    """
    fmt = "%H:%M"
    try:
        # Using a fixed date to perform time arithmetic safely
        t_start1 = datetime.strptime(start1, fmt)
        t_end1 = datetime.strptime(end1, fmt)
        t_start2 = datetime.strptime(start2, fmt)
        t_end2 = datetime.strptime(end2, fmt)
        
        # Validation: End must be after start
        if t_end1 <= t_start1 or t_end2 <= t_start2:
            return 0

        latest_start = max(t_start1, t_start2)
        earliest_end = min(t_end1, t_end2)

        delta = (earliest_end - latest_start).total_seconds()
        return max(0, int(delta / 60))
        
    except (ValueError, TypeError) as e:
        # Logs warning but doesn't crash the loop
        return 0

def get_schedule_matches(target_user_id: str, min_overlap: int = 30) -> Dict[str, List[Dict[str, Any]]]:
    """
    Finds students with overlapping free time. 
    Optimized O(N) grouping by day.
    """
    raw_schedules = get_all_schedules()
    if not raw_schedules:
        return {}

    target_blocks = []
    others_by_day = defaultdict(list)

    # Single Pass: Separate target user and group others by day
    # This avoids multiple loops over the entire database
    for block in raw_schedules:
        # Robust key validation
        uid = block.get('user_id')
        day = block.get('day_of_week')
        start = block.get('start_time')
        end = block.get('end_time')

        if not all([uid, day, start, end]):
            continue
            
        if uid == target_user_id:
            target_blocks.append(block)
        else:
            others_by_day[day].append(block)

    if not target_blocks:
        return {}

    matches = defaultdict(list)

    # Process Overlaps
    for my_block in target_blocks:
        day = my_block['day_of_week']
        
        # Only check people free on the SAME day
        for other in others_by_day.get(day, []):
            overlap = get_overlap_minutes(
                my_block['start_time'], my_block['end_time'],
                other['start_time'], other['end_time']
            )
            
            if overlap >= min_overlap:
                matches[other['user_id']].append({
                    "day": day,
                    "overlap_minutes": overlap,
                    "window": f"{max(my_block['start_time'], other['start_time'])} - {min(my_block['end_time'], other['end_time'])}",
                    "match_bio_hint": "🕒 Shares free time on " + day
                })

    return dict(matches)

if __name__ == "__main__":
    # Test simulation
    print("\n[MMUST AI] Testing Schedule Engine...")
    test_id = "USER_123"
    results = get_schedule_matches(test_id)
    
    if results:
        print(f"✅ Found {len(results)} potential date windows.")
    else:
        print("❌ No matching schedules found.")