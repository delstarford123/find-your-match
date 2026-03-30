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
    
    const myUserId = window.currentUserId || "MMUST_001"; 

    // GSAP Registration
    if (typeof gsap !== 'undefined') {
        gsap.registerPlugin(SplitText, TextPlugin);
    } else {
        console.warn("GSAP is not loaded. Animations will fallback to CSS.");
    }

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

        const nameEl = document.getElementById('profile-name');
        const bioEl = document.getElementById('profile-bio');

        nameEl.innerText = profile.name;
        bioEl.innerText = profile.bio;
        
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

            // GSAP ANIMATION: Cascade Reveal for Text
            if (typeof gsap !== 'undefined' && typeof SplitText !== 'undefined') {
                const splitName = new SplitText(nameEl, { type: "chars" });
                gsap.from(splitName.chars, {
                    y: -40, rotation: -10, opacity: 0,
                    stagger: { each: 0.03, from: "start" },
                    duration: 0.4, ease: "back.out(1.4)"
                });
                
                gsap.from(bioEl, {
                    y: 20, opacity: 0, delay: 0.2,
                    duration: 0.5, ease: "power2.out"
                });
            }
        };

        // Reset Card Position
        card.className = 'card'; 
        gsap.set(card, { x: 0, y: 0, rotation: 0, scale: 1 }); // GSAP Reset
    }

    // --- NEW: THE MATCH MODAL LOGIC (WITH GSAP) ---
    function triggerMatchModal(targetProfile) {
        document.getElementById('match-name-text').innerText = targetProfile.name.split(',')[0];
        document.getElementById('match-avatar').src = targetProfile.img || "/static/img/placeholder.png";
        
        const icebreakerContainer = document.getElementById('icebreaker-container');
        icebreakerContainer.innerHTML = '<div class="spinner text-center text-secondary">🤖 Thinking of Kakamega banter...</div>';
        
        // Show the modal
        modal.classList.remove('hidden');

        // GSAP ANIMATION: 3D Unfold + Elastic Snap for the Modal Pop
        if (typeof gsap !== 'undefined') {
            gsap.from(".modal-content", {
                scale: 0.5, rotationX: 45, opacity: 0,
                transformPerspective: 800,
                duration: 1.2, ease: "elastic.out(1, 0.4)"
            });
            
            // GSAP ANIMATION: Slot Machine effect for "IT'S A MATCH" text
            if (typeof SplitText !== 'undefined') {
                const matchTitle = new SplitText(".match-title", { type: "chars" });
                gsap.from(matchTitle.chars, {
                    yPercent: -200, opacity: 0,
                    stagger: { each: 0.05, from: "start" },
                    duration: 0.5, ease: "power4.out", delay: 0.3
                });
            }
        }

        fetch('/api/icebreakers', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ match_bio: targetProfile.bio })
        })
        .then(res => res.json())
        .then(data => {
            icebreakerContainer.innerHTML = '';
            const lines = data.icebreakers ? data.icebreakers.split('\n').filter(l => l.trim()) : ["Hey! We matched!"];
            
            lines.forEach((line, index) => {
                const cleanText = line.replace(/^\d+\.\s*/, '');
                const bubble = document.createElement('div');
                // Updated styles to match the new Maroon/Red palette
                bubble.style.cssText = "background: #FFD6DD; padding: 12px; margin-bottom: 10px; border-radius: 12px; cursor: pointer; font-size: 14px; color: #720000; font-weight: 500; text-align: left; box-shadow: 0 2px 5px rgba(114,0,0,0.1);";
                
                icebreakerContainer.appendChild(bubble);

                // GSAP ANIMATION: Typewriter effect for AI Icebreakers
                if (typeof gsap !== 'undefined') {
                    gsap.to(bubble, {
                        text: cleanText,
                        duration: Math.min(cleanText.length * 0.03, 2), // Speed based on length
                        ease: "none",
                        delay: 0.8 + (index * 0.5) // Stagger the typing
                    });
                } else {
                    bubble.innerText = cleanText;
                }
                
                bubble.onclick = () => {
                    navigator.clipboard.writeText(cleanText);
                    const originalText = bubble.innerText;
                    bubble.innerText = "📋 Copied to clipboard!";
                    bubble.style.background = "#E60026";
                    bubble.style.color = "white";
                    
                    // GSAP Pulse on click
                    if (typeof gsap !== 'undefined') {
                        gsap.from(bubble, { scale: 1.05, duration: 0.2, ease: "power1.out" });
                    }
                    
                    setTimeout(() => {
                        bubble.innerText = originalText;
                        bubble.style.background = "#FFD6DD";
                        bubble.style.color = "#720000";
                    }, 2000);
                };
            });
        })
        .catch(() => {
            icebreakerContainer.innerHTML = '<div style="background: #FFD6DD; padding: 10px; border-radius: 10px; font-size: 14px; color: #720000;">Hey! We matched! (AI is resting right now)</div>';
        });
    }

    // --- SWIPE PROCESSING ---
    function handleSwipe(direction) {
        if (currentIndex >= profiles.length) return;

        const targetProfile = profiles[currentIndex];

        fetch('/api/swipe', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                user_id: myUserId, 
                target_id: targetProfile.id, 
                action: direction 
            })
        });

        // GSAP ANIMATION: Whip Slide for swiping away
        if (typeof gsap !== 'undefined') {
            const endX = direction === 'like' ? window.innerWidth + 200 : -window.innerWidth - 200;
            const rotation = direction === 'like' ? 30 : -30;
            
            gsap.to(card, {
                x: endX,
                rotation: rotation,
                opacity: 0,
                duration: 0.6,
                ease: "power3.in",
                onComplete: () => {
                    if (direction === 'like') {
                        triggerMatchModal(targetProfile);
                    } else {
                        currentIndex++;
                        loadProfile();
                    }
                }
            });
        } else {
            // Fallback CSS animation
            card.classList.add(direction === 'like' ? 'swipe-right' : 'swipe-left');
            if (direction === 'like') {
                setTimeout(() => triggerMatchModal(targetProfile), 300); 
            } else {
                setTimeout(() => {
                    currentIndex++;
                    loadProfile();
                }, 400); 
            }
        }
    }

    async function checkPendingDateFeedback() {
        try {
            const res = await fetch(`/api/check-pending-date?user_id=${myUserId}`);
            const data = await res.json();
            if (data.show_feedback) {
                document.getElementById('fb-name').innerText = data.match_name;
                document.getElementById('fb-venue').innerText = data.venue;
                feedbackModal.classList.remove('hidden');
                
                // GSAP Reveal for Feedback Modal
                if (typeof gsap !== 'undefined') {
                     gsap.from(feedbackModal.querySelector('.modal-content'), {
                        y: 100, opacity: 0, duration: 0.6, ease: "back.out(1.2)"
                    });
                }
            }
        } catch (e) { console.log("No feedback needed."); }
    }

    function showEmptyState() {
        document.getElementById('active-profile').classList.add('hidden');
        document.getElementById('swipe-buttons').classList.add('hidden');
        
        const emptyState = document.getElementById('empty-state');
        emptyState.classList.remove('hidden');
        emptyState.style.display = 'flex';

        // GSAP ANIMATION: Float up the empty state
        if (typeof gsap !== 'undefined') {
            gsap.from(emptyState, {
                y: 50, opacity: 0, duration: 0.8, ease: "power2.out"
            });
        }

        card.onpointerdown = null; 
        gsap.set(card, { clearProps: "all" });
        card.style.cursor = 'default';
    }

    // --- EVENT LISTENERS ---
    document.getElementById('btn-like').onclick = () => handleSwipe('like');
    document.getElementById('btn-pass').onclick = () => handleSwipe('pass');
    
    document.getElementById('btn-close-modal').onclick = () => {
        // GSAP Fallaway
        if (typeof gsap !== 'undefined') {
             gsap.to(".modal-content", {
                scale: 0.8, opacity: 0, y: 50, duration: 0.3, ease: "power2.in",
                onComplete: () => {
                    modal.classList.add('hidden');
                    gsap.set(".modal-content", { clearProps: "all" }); // Reset for next time
                    currentIndex++;
                    loadProfile();
                }
             });
        } else {
            modal.classList.add('hidden');
            currentIndex++;
            loadProfile();
        }
    };

    // --- SWIPE PHYSICS (GSAP ENHANCED) ---
    let isDragging = false;
    let startX = 0;

    card.onpointerdown = (e) => {
        if (currentIndex >= profiles.length) return;
        isDragging = true;
        startX = e.clientX;
        // Kill any active tweens on the card so the user can grab it
        if (typeof gsap !== 'undefined') gsap.killTweensOf(card);
    };

    document.onpointermove = (e) => {
        if (!isDragging) return;
        let x = e.clientX - startX;
        // Snap dragging to pointer
        if (typeof gsap !== 'undefined') {
             gsap.set(card, { x: x, rotation: x * 0.05 });
        } else {
             card.style.transform = `translateX(${x}px) rotate(${x * 0.05}deg)`;
        }
    };

    document.onpointerup = (e) => {
        if (!isDragging) return;
        isDragging = false;
        let x = e.clientX - startX;
        
        if (Math.abs(x) > 120) {
            handleSwipe(x > 0 ? 'like' : 'pass');
        } else {
            // GSAP ANIMATION: Spring Scale (Rubber Band snap back to center)
            if (typeof gsap !== 'undefined') {
                gsap.to(card, {
                    x: 0, rotation: 0, 
                    duration: 0.8, ease: "elastic.out(1, 0.4)"
                });
            } else {
                card.style.transition = '0.3s';
                card.style.transform = '';
            }
        }
    };
});