document.addEventListener('DOMContentLoaded', () => {
    // --- UI ELEMENTS ---
    const card = document.getElementById('profile-card');
    const shimmer = document.getElementById('shimmer');
    const profileImg = document.getElementById('profile-img');
    const aiTag = document.getElementById('ai-tag');
    const matchSignal = document.getElementById('is-match-signal');
    
    const overlay = document.getElementById('match-overlay');
    const feedbackModal = document.getElementById('feedback-modal');
    
    // --- STATE ---
    let profiles = []; 
    let currentIndex = 0;
    let isAnimating = false;
    let isDragging = false;
    let startX = 0;
    
    const myUserId = window.currentUserId || "MMUST_STUDENT"; 
    const hasGSAP = typeof gsap !== 'undefined';

    // 1. STARTUP
    init();

    async function init() {
        await fetchProfiles();
        // Check for feedback after a short delay
        setTimeout(checkPendingDateFeedback, 2000);
    }

    async function fetchProfiles() {
        try {
            // Show loading state initially
            if (shimmer) shimmer.style.display = 'block';
            
            const res = await fetch(`/api/profiles?user_id=${myUserId}`);
            if (!res.ok) throw new Error("Server error");
            
            profiles = await res.json();
            
            if (profiles && profiles.length > 0) {
                loadProfile();
            } else {
                showEmptyState();
            }
        } catch (err) {
            console.error("Failed to fetch profiles:", err);
            showEmptyState();
        }
    }

    function loadProfile() {
        if (currentIndex >= profiles.length) {
            showEmptyState();
            return;
        }
        
        isAnimating = false;
        const profile = profiles[currentIndex];
        
        // --- 1. Prepare UI for next profile ---
        if (shimmer) shimmer.style.display = 'block';
        if (profileImg) profileImg.style.display = 'none';
        if (aiTag) aiTag.classList.add('hidden');
        
        // NEW: Signal if this is a mutual match immediately
        if (typeof window.updateMatchSignal === 'function') {
            window.updateMatchSignal(profile.is_mutual_match);
        }

        // --- 2. Update Text Fields ---
        const nameEl = document.getElementById('profile-name');
        const bioEl = document.getElementById('profile-bio');
        const ageEl = document.getElementById('profile-age');

        if (nameEl) nameEl.innerText = profile.name || "Explorer";
        if (bioEl) bioEl.innerText = profile.bio || "Searching for connections...";
        if (ageEl) ageEl.innerText = profile.age ? `, ${profile.age}` : "";
        
        // --- 3. AI Badge Logic ---
        if (aiTag && (profile.is_perfect_match || (profile.bio && profile.bio.includes("✨")))) {
            aiTag.innerText = "✨ AI TOP PICK";
            aiTag.classList.remove('hidden');
        }

        // --- 4. Image Handling (Prevents White Screen) ---
        const img = new Image();
        img.src = profile.img || "/static/img/placeholder.png";
        
        // Set a timeout: if image takes too long, show placeholder
        const imgTimeout = setTimeout(() => {
            if (profileImg.style.display === 'none') {
                profileImg.src = "/static/img/placeholder.png";
                revealProfile();
            }
        }, 5000);

        img.onload = () => {
            clearTimeout(imgTimeout);
            profileImg.src = img.src;
            revealProfile();
        };

        img.onerror = () => {
            clearTimeout(imgTimeout);
            profileImg.src = "/static/img/placeholder.png";
            revealProfile();
        };
    }

    function revealProfile() {
        if (shimmer) shimmer.style.display = 'none';
        if (profileImg) profileImg.style.display = 'block';

        if (hasGSAP) {
            // Smooth reveal animation
            gsap.fromTo(['#profile-name', '#profile-age', '#profile-bio'], 
                { y: 15, opacity: 0 }, 
                { y: 0, opacity: 1, duration: 0.4, stagger: 0.08, ease: "power2.out" }
            );
            // Reset card visuals
            gsap.set(card, { x: 0, y: 0, rotation: 0, opacity: 1, scale: 1 });
            gsap.set(['.stamp'], { opacity: 0 });
        }
    }

    // --- SWIPE LOGIC ---
    window.handleSwipe = function(direction) {
        if (currentIndex >= profiles.length || isAnimating) return;
        isAnimating = true;

        const targetProfile = profiles[currentIndex];

        // 1. Update Database (Background)
        fetch('/api/swipe', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                user_id: myUserId, 
                target_id: targetProfile.id, 
                action: direction 
            })
        }).catch(e => console.error("Swipe sync failed:", e));

        // 2. Animation
        if (hasGSAP) {
            const endX = direction === 'like' ? 800 : -800;
            const rotation = direction === 'like' ? 35 : -35;
            const stamp = direction === 'like' ? '#stamp-like' : '#stamp-nope';

            // Show stamp fully during animation
            gsap.to(stamp, { opacity: 1, duration: 0.1 });
            
            gsap.to(card, {
                x: endX,
                rotation: rotation,
                opacity: 0,
                duration: 0.5,
                ease: "power2.in",
                onComplete: () => finalizeSwipe(direction, targetProfile)
            });
        } else {
            finalizeSwipe(direction, targetProfile);
        }
    };

    function finalizeSwipe(direction, profile) {
        // If it's a mutual match and they liked, show the big celebration
        if (direction === 'like' && profile.is_mutual_match) {
            if (typeof window.triggerMatchCelebration === 'function') {
                window.triggerMatchCelebration(profile);
            }
        } else {
            currentIndex++;
            loadProfile();
        }
    }

    // Called from Celebration Modal
    window.loadNextProfile = function() {
        currentIndex++;
        loadProfile();
    };

    function showEmptyState() {
        const activeProfileUI = document.getElementById('active-profile');
        const swipeButtonsUI = document.getElementById('swipe-buttons');
        const emptyStateUI = document.getElementById('empty-state');

        if (activeProfileUI) activeProfileUI.classList.add('hidden');
        if (swipeButtonsUI) swipeButtonsUI.classList.add('hidden');
        if (matchSignal) matchSignal.style.display = 'none';
        
        if (emptyStateUI) {
            emptyStateUI.classList.remove('hidden');
            emptyStateUI.style.display = 'flex';
            if (hasGSAP) gsap.from(emptyStateUI, { scale: 0.95, opacity: 0, duration: 0.5 });
        }
    }

    // --- INTERACTIVE PHYSICS ---
    if (card) {
        card.onpointerdown = (e) => {
            if (currentIndex >= profiles.length || isAnimating) return;
            isDragging = true;
            startX = e.clientX;
            card.style.transition = 'none';
            if (hasGSAP) gsap.killTweensOf(card);
        };

        document.addEventListener('pointermove', (e) => {
            if (!isDragging) return;
            
            const x = e.clientX - startX;
            const rotation = x * 0.1;
            
            // Calculate stamp opacities (appear as you drag further)
            const opacityLike = Math.max(0, Math.min(1, (x - 50) / 100));
            const opacityNope = Math.max(0, Math.min(1, (-x - 50) / 100));

            if (hasGSAP) {
                gsap.set(card, { x: x, rotation: rotation });
                gsap.set('#stamp-like', { opacity: opacityLike });
                gsap.set('#stamp-nope', { opacity: opacityNope });
            } else {
                card.style.transform = `translateX(${x}px) rotate(${rotation}deg)`;
            }
        });

        document.addEventListener('pointerup', (e) => {
            if (!isDragging) return;
            isDragging = false;
            
            const x = e.clientX - startX;
            const threshold = 130;

            if (Math.abs(x) > threshold) {
                window.handleSwipe(x > 0 ? 'like' : 'pass');
            } else {
                // Snap back to center
                if (hasGSAP) {
                    gsap.to(card, { x: 0, rotation: 0, duration: 0.5, ease: "elastic.out(1, 0.6)" });
                    gsap.to(['.stamp'], { opacity: 0, duration: 0.2 });
                } else {
                    card.style.transition = '0.3s ease';
                    card.style.transform = 'translate(0,0) rotate(0deg)';
                }
            }
        });
    }

    async function checkPendingDateFeedback() {
        try {
            const res = await fetch(`/api/check-pending-date?user_id=${myUserId}`);
            const data = await res.json();
            if (data.show_feedback && feedbackModal) {
                const fbName = document.getElementById('fb-name');
                if (fbName) fbName.innerText = data.match_name;
                feedbackModal.classList.remove('hidden');
            }
        } catch (e) {
            // Silently fail if route doesn't exist yet
        }
    }
});