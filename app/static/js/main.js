
function updateLiveOnlineCount() {
        fetch('/api/online_count')
            .then(res => res.json())
            .then(data => {
                // Update the number inside the button
                const countElement = document.getElementById('liveUserCount');
                if (countElement) {
                    countElement.innerText = data.count;
                }
            })
            .catch(err => console.error("Failed to fetch live users", err));
    }
    
    // Fetch the count immediately when the page loads
    updateLiveOnlineCount();
    
    // Silently update the count in the background every 60 seconds (reduced from 15s to save server load)
    setInterval(updateLiveOnlineCount, 60000);

    /* DISABLED FOR HOSTPINNACLE
                // Start Persistent Alarm (1 Hour Loop)
                stopEmergencyAlert(); // Clear any old ones
                
                const playLoop = () => {
                    sosAudio1.play().catch(e => console.log("Audio blocked"));
                    setTimeout(() => {
                        sosAudio2.play().catch(e => console.log("Audio blocked"));
                    }, 3000);
                };

                playLoop();
                sosAlarmInterval = setInterval(playLoop, 7000);

                // Auto-stop after 1 hour
                sosTimeout = setTimeout(() => {
                    stopEmergencyAlert();
                }, 3600000); 
                
                if (navigator.vibrate) navigator.vibrate([500, 200, 500, 200, 500]);
            });

            globalSocket.on('receive_sos_stop', (data) => {
                // Remote signal to stop the alarm
                stopEmergencyAlert();
                if (data.sender_id !== myUserId) {
                    alert("✅ Emergency Resolved: The student is now safe.");
                }
            });

            window.stopGlobalEmergencySOS = function() {
                if (!confirm("Confirm you are safe? This will silence the alarm for ALL students.")) return;
                globalSocket.emit('stop_emergency_sos', { sender_id: myUserId });
                stopEmergencyAlert();
            };

            window.stopEmergencyAlert = function() {
                document.getElementById('emergencyOverlay').classList.remove('active');
                clearInterval(sosAlarmInterval);
                clearTimeout(sosTimeout);
                sosAudio1.pause(); sosAudio1.currentTime = 0;
                sosAudio2.pause(); sosAudio2.currentTime = 0;
            };

            // === 💡 SOS TOOLTIP LOGIC ===
            window.closeSosTooltip = function() {
                document.getElementById('sosTooltip').style.display = 'none';
                localStorage.setItem('sos_tooltip_closed', 'true');
            };

            // Show tooltip on load if not previously closed
            setTimeout(() => {
                if (!localStorage.getItem('sos_tooltip_closed')) {
                    document.getElementById('sosTooltip').style.display = 'block';
                }
            }, 2000);

            window.triggerEmergencySOS = function() {
                if (!confirm("🚨 CONFIRM EMERGENCY 🚨\n\nAre you in immediate danger? This will alert ALL online users and share your current location.")) return;

                const btn = document.getElementById('sosTriggerBtn');
                btn.disabled = true;
                btn.style.opacity = '0.5';

                // Try to get location
                if (navigator.geolocation) {
                    navigator.geolocation.getCurrentPosition((pos) => {
                        const payload = {
                            sender_id: myUserId,
                            latitude: pos.coords.latitude,
                            longitude: pos.coords.longitude
                        };
                        globalSocket.emit('emergency_sos', payload);
                        alert("🚨 SOS DISPATCHED! Stay safe, help is being notified.");
                        setTimeout(() => { btn.disabled = false; btn.style.opacity = '1'; }, 10000);
                    }, (err) => {
                        // Emit even without location
                        globalSocket.emit('emergency_sos', { sender_id: myUserId });
                        alert("🚨 SOS DISPATCHED! (Location access denied, but users notified)");
                        setTimeout(() => { btn.disabled = false; btn.style.opacity = '1'; }, 10000);
                    });
                } else {
                    globalSocket.emit('emergency_sos', { sender_id: myUserId });
                    alert("🚨 SOS DISPATCHED!");
                    setTimeout(() => { btn.disabled = false; btn.style.opacity = '1'; }, 10000);
                }
            };
            
            globalSocket.on('incoming_call', (data) => {
                // Prevent popup if already on the call page
                if (window.location.pathname.includes('/call/')) return; 

                globalIncomingCallerId = data.caller_id;
                
                // Configure UI elements
                document.getElementById('gIncImg').src = data.caller_img || '/static/img/placeholder.png';
                document.getElementById('gIncName').innerText = data.caller_name || 'A Student';
                
                const isVideo = data.is_video === true || data.is_video === 'true';
                const callColor = isVideo ? '#A855F7' : '#38BDF8';
                
                document.getElementById('gIncType').innerText = isVideo ? '📹 Incoming Video Call' : '🎙 Incoming Voice Call';
                document.getElementById('gIncType').style.color = callColor;
                document.getElementById('gIncImg').style.borderColor = callColor;
                
                // Update ring animation colors
                document.querySelectorAll('.g-ring').forEach(ring => {
                    ring.style.borderColor = callColor;
                });

                // Configure answer button redirection
                document.getElementById('gBtnAnswer').onclick = function() {
                    playGlobalRingtone(false);
                    document.getElementById('globalIncomingCall').classList.remove('active');
                    window.location.href = `/call/${data.caller_id}?action=answer&video=${isVideo}`;
                };

                // Trigger modal and audio
                document.getElementById('globalIncomingCall').classList.add('active');
                playGlobalRingtone(true);
            });

            globalSocket.on('call_ended', () => {
                playGlobalRingtone(false);
                document.getElementById('globalIncomingCall').classList.remove('active');
                globalIncomingCallerId = null;
            });
        }

        function globalDeclineCall() {
            playGlobalRingtone(false);
            document.getElementById('globalIncomingCall').classList.remove('active');
            if (globalIncomingCallerId) {
                globalSocket.emit('end_call', { target_id: globalIncomingCallerId, reason: 'declined' });
                globalIncomingCallerId = null;
            }
        }
    }
    */

document.addEventListener("DOMContentLoaded", () => {
        const totalImages = 16; // Optimized from 27 for premium mobile performance
        const bgContainer = document.getElementById('dreamscape-bg');
        
        // 1. Generate the 27 Orbs
        for (let i = 1; i <= totalImages; i++) {
            let orb = document.createElement('div');
            orb.className = 'love-orb';
            
            // Link to your static folder images
            orb.style.backgroundImage = `url('/static/img/${i}.jpg')`; 
            
            // Randomize their sizes so it looks natural (between 50px and 140px)
            let size = gsap.utils.random(50, 140);
            orb.style.width = `${size}px`;
            orb.style.height = `${size}px`;
            
            bgContainer.appendChild(orb);
            
            // Start the infinite animation loop for this specific orb
            animateOrb(orb);
        }

        // 2. The GSAP Floating Logic
        function animateOrb(orb) {
            // Pick a random starting point at the bottom of the screen
            let startX = gsap.utils.random(0, window.innerWidth);
            let startY = window.innerHeight + 150; // Starts below the screen
            
            // Randomize how long it takes to float up (between 20 and 45 seconds - very slow and peaceful)
            let duration = gsap.utils.random(20, 45); 
            
            // Randomize when it starts, so they don't all clump together at the beginning
            let delay = gsap.utils.random(0, 30);

            // Reset the orb to the bottom
            gsap.set(orb, {
                x: startX,
                y: startY,
                opacity: 0,
                scale: gsap.utils.random(0.6, 1.2),
                rotation: gsap.utils.random(-30, 30) // Give it a slight tilt
            });

            // Create the timeline
            let tl = gsap.timeline({
                delay: delay,
                onComplete: () => animateOrb(orb) // When it finishes, restart it infinitely
            });

            // The Animation Sequence
            tl.to(orb, {
                // Fade in softly (Keep opacity low so it doesn't distract from the app text)
                opacity: gsap.utils.random(0.15, 0.35), 
                duration: duration * 0.2, 
                ease: "power1.inOut"
            })
            .to(orb, {
                // Float up to above the top of the screen
                y: -200, 
                // Drift slightly left or right like a balloon in the wind
                x: startX + gsap.utils.random(-150, 150), 
                rotation: gsap.utils.random(-60, 60),
                duration: duration,
                ease: "none"
            }, "<") // The "<" symbol tells GSAP to run this at the same time as the fade-in
            .to(orb, {
                // Fade back out before it disappears
                opacity: 0,
                duration: duration * 0.2,
                ease: "power1.inOut"
            }, `-=${duration * 0.2}`); // Start fading out near the end of the duration
        }
    });
