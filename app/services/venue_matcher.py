def get_venue_recommendations(overlap_minutes, combined_vibe):
    """
    Filters the Kakamega database based on how much time the students have
    and what their shared vibe is.
    """
    all_venues = get_all_venues_from_firebase()
    perfect_spots = []
    
    for venue in all_venues:
        # Rule 1: Do they have enough time to go here?
        if overlap_minutes >= venue['min_time_minutes']:
            
            # Rule 2: Does the venue match their vibe?
            if combined_vibe in venue['vibe_tags']:
                perfect_spots.append(venue)
                
    return perfect_spots