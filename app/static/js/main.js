document.addEventListener('DOMContentLoaded', () => {
    // --- UI ELEMENTS ---
    const card = document.getElementById('profile-card');
    const shimmer = document.getElementById('shimmer');
    const profileImg = document.getElementById('profile-img');
    const aiTag = document.getElementById('ai-tag');
    
    const modal = document.getElementById('match-modal');
    const feedbackModal = document.getElementById('feedback-modal');
    
    let profiles = []; 
    let currentIndex = 0;
    
    // In production, these come from the session via a hidden input or global variable
    // Since this is an external JS file, we use a global variable set in base.html, 
    // or just fetch it securely. For MVP, we'll assume myUserId is passed globally.
    // If it's missing, ensure you render it in a <script> tag in swipe.html before this file loads.
    const myUserId = window.currentUserId || "MMUST_001"; 

    // 1. INITIAL FETCH
    fetchProfiles();
    setTimeout(checkPendingDateFeedback, 1500);

    function fetchProfiles() {
        fetch(`/api/profiles?user_id=${myUserId}`)
            .then(res => res.json())
            .then(data => {
                profiles = data;
                setTimeout(loadProfile, 800); 
            })
            .catch(err => {
                console.error("Failed to fetch profiles", err);
                showEmptyState();
            });
    }

    function loadProfile() {
        if (currentIndex >= profiles.length) {
            showEmptyState();
            return;
        }
        
        const profile = profiles[currentIndex];
        
        // --- THE TRANSITION ---
        shimmer.style.display = 'block';
        profileImg.style.display = 'none';
        aiTag.classList.add('hidden');

        // Update Text
        document.getElementById('profile-name').innerText = profile.name;
        document.getElementById('profile-bio').innerText = profile.bio;
        
        // Handle AI Tags
        if (profile.bio.includes("MATCHING FREE TIME") || profile.bio.includes("🕒")) {
            aiTag.innerText = " SCHEDULE MATCH";
            aiTag.classList.remove('hidden');
        } else if (profile.bio.includes("AI Top Pick") || profile.bio.includes("✨")) {
            aiTag.innerText = "AI TOP PICK";
            aiTag.classList.remove('hidden');
        }

        // Load Image
        const img = new Image();
        img.src = profile.img || "/static/img/placeholder.png";
        img.onload = () => {
            profileImg.src = img.src;
            shimmer.style.display = 'none';
            profileImg.style.display = 'block';
        };

        // Reset Card Position
        card.className = 'card'; 
        card.style.transform = '';
    }

    // --- NEW: THE MATCH MODAL LOGIC ---
    function triggerMatchModal(targetProfile) {
        // Set match details
        document.getElementById('match-name-text').innerText = targetProfile.name.split(',')[0];
        document.getElementById('match-avatar').src = targetProfile.img || "/static/img/placeholder.png";
        
        const icebreakerContainer = document.getElementById('icebreaker-container');
        icebreakerContainer.innerHTML = '<div class="spinner"> Thinking of Kakamega banter...</div>';
        
        // Show the modal
        modal.classList.remove('hidden');

        // Fetch AI Icebreakers (Optional: You can build this endpoint in main.py later)
        fetch('/api/icebreakers', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ match_bio: targetProfile.bio })
        })
        .then(res => res.json())
        .then(data => {
            icebreakerContainer.innerHTML = '';
            const lines = data.icebreakers ? data.icebreakers.split('\n').filter(l => l.trim()) : ["Hey! We matched!"];
            
            lines.forEach(line => {
                const cleanText = line.replace(/^\d+\.\s*/, '');
                const bubble = document.createElement('div');
                bubble.innerText = cleanText;
                // Add quick inline styles for the bubbles
                bubble.style.cssText = "background: #ffe6ea; padding: 10px; margin-bottom: 8px; border-radius: 10px; cursor: pointer; font-size: 14px; color: #4a0404;";
                
                bubble.onclick = () => {
                    navigator.clipboard.writeText(cleanText);
                    bubble.innerText = " Copied to clipboard!";
                    setTimeout(() => bubble.innerText = cleanText, 2000);
                };
                icebreakerContainer.appendChild(bubble);
            });
        })
        .catch(() => {
            // Fallback if the AI is offline
            icebreakerContainer.innerHTML = '<div style="background: #ffe6ea; padding: 10px; border-radius: 10px; font-size: 14px; color: #4a0404;">Hey! We matched! (AI is resting right now)</div>';
        });
    }

    // --- SWIPE PROCESSING ---
    function handleSwipe(direction) {
        if (currentIndex >= profiles.length) return;

        const targetProfile = profiles[currentIndex];

        // Send to Backend
        fetch('/api/swipe', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                user_id: myUserId, 
                target_id: targetProfile.id, 
                action: direction 
            })
        });

        // Visual Animation
        card.classList.add(direction === 'like' ? 'swipe-right' : 'swipe-left');
        
        if (direction === 'like') {
            // For MVP: We assume every right swipe is a match to test the UI.
            // In production, the backend /api/swipe will return {is_match: true}
            setTimeout(() => triggerMatchModal(targetProfile), 300); 
        } else {
            setTimeout(() => {
                currentIndex++;
                loadProfile();
            }, 400); 
        }
    }

    // --- REAL POST-DATE FEEDBACK TRIGGER ---
    async function checkPendingDateFeedback() {
        try {
            const res = await fetch(`/api/check-pending-date?user_id=${myUserId}`);
            const data = await res.json();
            if (data.show_feedback) {
                document.getElementById('fb-name').innerText = data.match_name;
                document.getElementById('fb-venue').innerText = data.venue;
                feedbackModal.classList.remove('hidden');
            }
        } catch (e) { console.log("No feedback needed."); }
    }

    // --- EMPTY STATE FIX ---
    function showEmptyState() {
        // 1. Hide active elements
        document.getElementById('active-profile').classList.add('hidden');
        document.getElementById('swipe-buttons').classList.add('hidden');
        
        // 2. Show the empty state graphic
        const emptyState = document.getElementById('empty-state');
        emptyState.classList.remove('hidden');
        emptyState.style.display = 'flex';

        // 3. Disable swiping physics so the empty screen doesn't drag
        card.onpointerdown = null; 
        card.style.transform = '';
        card.style.cursor = 'default';
    }

    // --- EVENT LISTENERS ---
    document.getElementById('btn-like').onclick = () => handleSwipe('like');
    document.getElementById('btn-pass').onclick = () => handleSwipe('pass');
    
    // Close match modal and load next profile
    document.getElementById('btn-close-modal').onclick = () => {
        modal.classList.add('hidden');
        currentIndex++;
        loadProfile();
    };

    // --- SWIPE PHYSICS (DRAG) ---
    let isDragging = false;
    let startX = 0;

    card.onpointerdown = (e) => {
        if (currentIndex >= profiles.length) return;
        isDragging = true;
        startX = e.clientX;
        card.style.transition = 'none';
    };

    document.onpointermove = (e) => {
        if (!isDragging) return;
        let x = e.clientX - startX;
        card.style.transform = `translateX(${x}px) rotate(${x * 0.05}deg)`;
    };

    document.onpointerup = (e) => {
        if (!isDragging) return;
        isDragging = false;
        let x = e.clientX - startX;
        if (Math.abs(x) > 120) {
            handleSwipe(x > 0 ? 'like' : 'pass');
        } else {
            card.style.transition = '0.3s';
            card.style.transform = '';
        }
    };
});