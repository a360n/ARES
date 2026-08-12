// Define primary camera IP address for routing endpoints
const cameraIP = "http://192.168.4.1";
let lastKey = null;

// Command mapping array matching the Pico.py controller expectations
const commands = {
    'w': 'w', 'W': 'w',
    's': 's', 'S': 's',
    'a': 'a', 'A': 'a',
    'd': 'd', 'D': 'd',
    ' ': 'x'
};

// Initialize live feed on page load with stream port 81
const robotStream = document.getElementById('robotStream');
const camStatusDot = document.getElementById('cam-status-dot');
const camStatusLabel = document.getElementById('cam-status-label');

robotStream.src = `${cameraIP}:81/stream`;

robotStream.onload = () => {
    camStatusDot.classList.add('active');
    camStatusLabel.innerText = "CONNECTED";
    camStatusLabel.style.color = "var(--success)";
};

robotStream.onerror = () => {
    camStatusDot.classList.remove('active');
    camStatusLabel.innerText = "DISCONNECTED";
    camStatusLabel.style.color = "var(--danger)";
    // Re-attempt loop to handle initial boot delays
    setTimeout(() => {
        robotStream.src = `${cameraIP}:81/stream?t=${new Date().getTime()}`;
    }, 3000);
};

// Send command to camera endpoint
function sendCommand(cmdLetter) {
    // Invert 'a' <-> 'd' and 'w' <-> 's' to match physical robot motor responses
    let actualCmd = cmdLetter;
    if (cmdLetter === 'a') actualCmd = 'd';
    else if (cmdLetter === 'd') actualCmd = 'a';
    else if (cmdLetter === 'w') actualCmd = 's';
    else if (cmdLetter === 's') actualCmd = 'w';

    console.log(`[MacBook -> Camera] Sending movement command: '${actualCmd}' (input: '${cmdLetter}') | URL: ${cameraIP}/move?dir=${actualCmd}`);
    const beacon = new Image();
    beacon.src = `${cameraIP}/move?dir=${actualCmd}&t=${new Date().getTime()}`;
}

// Fetch telemetry payloads from ESP32
function fetchTelemetry() {
    const url = `${cameraIP}/telemetry`;
    fetch(url)
        .then(response => {
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            return response.json();
        })
        .then(data => {
            console.log("[Camera -> MacBook] Telemetry payload received:", data);
            // Dynamic updates for environmental sensors
            document.getElementById('val-temp').innerText = `${data.temp} °C`;
            document.getElementById('val-hum').innerText = `${data.hum} %`;
            document.getElementById('val-mq9').innerText = `${data.mq9} ppm`;
            document.getElementById('val-mq135').innerText = `${data.mq135} ppm`;
            document.getElementById('val-ultra').innerText = `${data.distance} cm`;
            document.getElementById('val-gps').innerText = `${data.lat}, ${data.lng}`;
        })
        .catch(err => console.warn(`[Camera -> MacBook] Telemetry connection waiting or error: ${err.message}`));
}

// Run telemetry fetch loop every 500ms
setInterval(fetchTelemetry, 500);

// ============================================================================
// 🎮 Mode Management (Computer/Mobile - D-Pads/Joysticks)
// ============================================================================
let currentPan = 90;
let currentTilt = 30;
let targetPan = 90;
let targetTilt = 30;
let isMobileMode = false;
let isJoystickMode = false;
let isSliderInteracting = false;

// Device mode buttons routing
const deviceComputerBtn = document.getElementById('deviceComputerBtn');
const deviceMobileBtn = document.getElementById('deviceMobileBtn');
const mobileControlTypeRow = document.getElementById('mobileControlTypeRow');
const ctrlDpadBtn = document.getElementById('ctrlDpadBtn');
const ctrlJoystickBtn = document.getElementById('ctrlJoystickBtn');
const computerKeyboardCard = document.getElementById('computerKeyboardCard');
const mobileControlsContainer = document.getElementById('mobileControlsContainer');
const dpadInterface = document.getElementById('dpadInterface');
const joystickInterface = document.getElementById('joystickInterface');

function switchDevice(mode) {
    if (mode === 'mobile') {
        isMobileMode = true;
        deviceMobileBtn.classList.add('btn-primary');
        deviceMobileBtn.style.background = 'var(--primary)';
        deviceMobileBtn.style.borderColor = 'var(--primary)';
        deviceComputerBtn.classList.remove('btn-primary');
        deviceComputerBtn.style.background = 'rgba(255,255,255,0.05)';
        deviceComputerBtn.style.borderColor = 'rgba(255,255,255,0.15)';
        
        mobileControlTypeRow.style.display = 'flex';
        computerKeyboardCard.style.display = 'none';
        mobileControlsContainer.style.display = 'flex';
        switchControlType(isJoystickMode ? 'joystick' : 'dpad');
    } else {
        isMobileMode = false;
        deviceComputerBtn.classList.add('btn-primary');
        deviceComputerBtn.style.background = 'var(--primary)';
        deviceComputerBtn.style.borderColor = 'var(--primary)';
        deviceMobileBtn.classList.remove('btn-primary');
        deviceMobileBtn.style.background = 'rgba(255,255,255,0.05)';
        deviceMobileBtn.style.borderColor = 'rgba(255,255,255,0.15)';
        
        mobileControlTypeRow.style.display = 'none';
        computerKeyboardCard.style.display = 'block';
        mobileControlsContainer.style.display = 'none';
        // Halt robot movement on switch
        sendCommand('x');
    }
}

// Touch control mode selector
function switchControlType(type) {
    if (type === 'joystick') {
        isJoystickMode = true;
        ctrlJoystickBtn.classList.add('btn-primary');
        ctrlJoystickBtn.style.background = 'var(--primary)';
        ctrlJoystickBtn.style.borderColor = 'var(--primary)';
        ctrlDpadBtn.classList.remove('btn-primary');
        ctrlDpadBtn.style.background = 'rgba(255,255,255,0.05)';
        ctrlDpadBtn.style.borderColor = 'rgba(255,255,255,0.15)';
        
        dpadInterface.style.display = 'none';
        joystickInterface.style.display = 'flex';
    } else {
        isJoystickMode = false;
        ctrlDpadBtn.classList.add('btn-primary');
        ctrlDpadBtn.style.background = 'var(--primary)';
        ctrlDpadBtn.style.borderColor = 'var(--primary)';
        ctrlJoystickBtn.classList.remove('btn-primary');
        ctrlJoystickBtn.style.background = 'rgba(255,255,255,0.05)';
        ctrlJoystickBtn.style.borderColor = 'rgba(255,255,255,0.15)';
        
        dpadInterface.style.display = 'flex';
        joystickInterface.style.display = 'none';
    }
    sendCommand('x');
}

deviceComputerBtn.addEventListener('click', () => switchDevice('computer'));
deviceMobileBtn.addEventListener('click', () => switchDevice('mobile'));
ctrlDpadBtn.addEventListener('click', () => switchControlType('dpad'));
ctrlJoystickBtn.addEventListener('click', () => switchControlType('joystick'));

// ============================================================================
// ⌨️ Keyboard arrow key and WASD handling
// ============================================================================
let activeArrowKeys = { ArrowUp: false, ArrowDown: false, ArrowLeft: false, ArrowRight: false };

window.addEventListener('keydown', (e) => {
    if (isMobileMode) return;
    const key = e.key;

    // 1. WASD Robot movement
    if (commands[key] && lastKey !== key) {
        lastKey = key;
        document.querySelectorAll('.key-btn, .space-btn').forEach(k => k.classList.remove('active'));
        let elementId = (key === ' ') ? 'key-space' : `key-${key.toLowerCase()}`;
        const el = document.getElementById(elementId);
        if (el) el.classList.add('active');

        document.getElementById('current-cmd').innerText = (key === ' ') ? "EMERGENCY STOP" : `DRIVING (${key.toUpperCase()})`;
        sendCommand(commands[key]);
    }
    
    // 2. Camera direction (Arrow Keys)
    if (activeArrowKeys[key] !== undefined) {
        e.preventDefault(); // Prevent page scroll
        activeArrowKeys[key] = true;
    }
});

window.addEventListener('keyup', (e) => {
    if (isMobileMode) return;
    const key = e.key;

    if (commands[key]) {
        lastKey = null;
        document.querySelectorAll('.key-btn, .space-btn').forEach(k => k.classList.remove('active'));
        document.getElementById('current-cmd').innerText = "STANDBY / STOP";
        sendCommand('x');
    }

    if (activeArrowKeys[key] !== undefined) {
        activeArrowKeys[key] = false;
    }
});

// Arrow checking loop and smooth servo panning lerp (50ms interval)
setInterval(() => {
    const step = 6;

    // 1. Target values updates
    if (!isMobileMode || (isMobileMode && !isJoystickMode)) {
        if (!isSliderInteracting) {
            if (activeArrowKeys.ArrowLeft) { targetPan = Math.min(180, targetPan + step); }
            if (activeArrowKeys.ArrowRight) { targetPan = Math.max(0, targetPan - step); }
            if (activeArrowKeys.ArrowUp) { targetTilt = Math.max(0, targetTilt - step); }
            if (activeArrowKeys.ArrowDown) { targetTilt = Math.min(90, targetTilt + step); }

            const noArrowsPressed = !activeArrowKeys.ArrowLeft && !activeArrowKeys.ArrowRight && !activeArrowKeys.ArrowUp && !activeArrowKeys.ArrowDown;
            if (noArrowsPressed) {
                targetPan = 90;
                targetTilt = 30;
            }
        }
    }

    // 2. Low-pass filter approximation for smooth movement
    const amt = 0.20;
    
    let nextPan;
    if (Math.abs(targetPan - currentPan) < 2.5) {
        nextPan = targetPan;
    } else {
        nextPan = Math.round(currentPan + (targetPan - currentPan) * amt);
    }

    let nextTilt;
    if (Math.abs(targetTilt - currentTilt) < 2.5) {
        nextTilt = targetTilt;
    } else {
        nextTilt = Math.round(currentTilt + (targetTilt - currentTilt) * amt);
    }

    if (nextPan !== currentPan || nextTilt !== currentTilt) {
        currentPan = nextPan;
        currentTilt = nextTilt;
        panSlider.value = currentPan;
        tiltSlider.value = currentTilt;
        sendServoCommand(currentPan, currentTilt);
    }
}, 50);

// ============================================================================
// 📱 Mobile D-Pad touch handling
// ============================================================================
function bindDpadButton(btnId, cmdOrArrow, isRobot = true) {
    const btn = document.getElementById(btnId);
    if (!btn) return;

    const pressEvent = 'touchstart';

    btn.addEventListener(pressEvent, (e) => {
        e.preventDefault();
        if (isRobot) {
            sendCommand(cmdOrArrow);
        } else {
            activeArrowKeys[cmdOrArrow] = true;
        }
    });

    const releaseHandler = (e) => {
        e.preventDefault();
        if (isRobot) {
            sendCommand('x');
        } else {
            activeArrowKeys[cmdOrArrow] = false;
        }
    };

    btn.addEventListener('touchend', releaseHandler);
    btn.addEventListener('touchcancel', releaseHandler);
}

// Bind Robot drive buttons
bindDpadButton('dpad-robot-up', 'w', true);
bindDpadButton('dpad-robot-down', 's', true);
bindDpadButton('dpad-robot-left', 'a', true);
bindDpadButton('dpad-robot-right', 'd', true);

// Bind Camera pan/tilt buttons
bindDpadButton('dpad-cam-up', 'ArrowUp', false);
bindDpadButton('dpad-cam-down', 'ArrowDown', false);
bindDpadButton('dpad-cam-left', 'ArrowLeft', false);
bindDpadButton('dpad-cam-right', 'ArrowRight', false);

// Halt and center commands
document.getElementById('dpad-robot-stop').addEventListener('touchstart', (e) => {
    e.preventDefault();
    sendCommand('x');
});
document.getElementById('dpad-cam-center').addEventListener('touchstart', (e) => {
    e.preventDefault();
    currentPan = 90;
    currentTilt = 30;
    panSlider.value = 90;
    tiltSlider.value = 30;
    sendServoCommand(90, 30, true);
});

// ============================================================================
// 🕹️ Mobile Analog Joysticks
// ============================================================================
function initJoystick(baseId, knobId, onChange, onRelease) {
    const base = document.getElementById(baseId);
    const knob = document.getElementById(knobId);
    if (!base || !knob) return;

    let startX = 0;
    let startY = 0;
    let isMoving = false;
    let activeTouchId = null;
    const maxDist = 35;

    base.addEventListener('touchstart', (e) => {
        if (activeTouchId !== null) return;
        e.preventDefault();
        const touch = e.changedTouches[0];
        if (!touch) return;
        activeTouchId = touch.identifier;
        isMoving = true;
        const rect = base.getBoundingClientRect();
        startX = rect.left + rect.width / 2;
        startY = rect.top + rect.height / 2;
        handleMove(touch.clientX, touch.clientY);
    });

    window.addEventListener('touchmove', (e) => {
        if (base.offsetParent === null) {
            if (isMoving) {
                isMoving = false;
                activeTouchId = null;
                knob.style.transform = 'translate(0px, 0px)';
                if (onRelease) onRelease();
            }
            return;
        }
        if (!isMoving || activeTouchId === null) return;

        if (e.cancelable) e.preventDefault();

        let touch = null;
        for (let i = 0; i < e.touches.length; i++) {
            if (e.touches[i].identifier === activeTouchId) {
                touch = e.touches[i];
                break;
            }
        }
        if (touch) {
            let dx = touch.clientX - startX;
            let dy = touch.clientY - startY;
            const dist = Math.sqrt(dx * dx + dy * dy);

            // Safety limit trigger
            if (dist > 120) {
                isMoving = false;
                activeTouchId = null;
                knob.style.transform = 'translate(0px, 0px)';
                if (onRelease) onRelease();
            } else {
                handleMove(touch.clientX, touch.clientY);
            }
        }
    }, { passive: false });

    const endHandler = (e) => {
        if (!isMoving || activeTouchId === null) return;
        let touchEnded = false;
        if (e.touches.length === 0) {
            touchEnded = true;
        } else {
            for (let i = 0; i < e.changedTouches.length; i++) {
                if (e.changedTouches[i].identifier === activeTouchId) {
                    touchEnded = true;
                    break;
                }
            }
        }
        if (touchEnded) {
            isMoving = false;
            activeTouchId = null;
            knob.style.transform = 'translate(0px, 0px)';
            if (onRelease) onRelease();
        }
    };

    window.addEventListener('touchend', endHandler);
    window.addEventListener('touchcancel', endHandler);

    function handleMove(clientX, clientY) {
        let dx = clientX - startX;
        let dy = clientY - startY;
        const dist = Math.sqrt(dx * dx + dy * dy);

        if (dist > maxDist) {
            dx = (dx / dist) * maxDist;
            dy = (dy / dist) * maxDist;
        }

        knob.style.transform = `translate(${dx}px, ${dy}px)`;
        if (onChange) {
            onChange(dx / maxDist, dy / maxDist);
        }
    }
}

// Drive control joystick
let lastJoyDir = 'x';
initJoystick('joy-robot-base', 'joy-robot-knob', 
    (nx, ny) => {
        const dist = Math.sqrt(nx * nx + ny * ny);
        if (dist < 0.25) {
            if (lastJoyDir !== 'x') {
                lastJoyDir = 'x';
                sendCommand('x');
            }
            return;
        }

        let dir = 'x';
        if (Math.abs(ny) > Math.abs(nx)) {
            dir = (ny < 0) ? 'w' : 's';
        } else {
            dir = (nx < 0) ? 'a' : 'd';
        }

        if (dir !== lastJoyDir) {
            lastJoyDir = dir;
            sendCommand(dir);
        }
    },
    () => {
        lastJoyDir = 'x';
        sendCommand('x');
    }
);

// Camera control joystick
initJoystick('joy-cam-base', 'joy-cam-knob',
    (nx, ny) => {
        targetPan = Math.round(90 - nx * 90);
        targetTilt = ny < 0 ? Math.round(30 + ny * 30) : Math.round(30 + ny * 60);
    },
    () => {
        targetPan = 90;
        targetTilt = 30;
    }
);

// ============================================================================
// 💡 Tactical LED controller
// ============================================================================
const slider = document.getElementById('lightSlider');
const lightVal = document.getElementById('light-val');
const toggleBtn = document.getElementById('toggleLightBtn');
let isLightOn = false;

function setFlashIntensity(value) {
    lightVal.innerText = value;
    slider.value = value;

    if (value > 0) {
        isLightOn = true;
        toggleBtn.innerText = "Turn OFF Light (ON)";
        toggleBtn.classList.add('btn-active');
    } else {
        isLightOn = false;
        toggleBtn.innerText = "Turn ON Light (OFF)";
        toggleBtn.classList.remove('btn-active');
    }

    const url = `${cameraIP}/control?var=led_intensity&val=${value}&t=${new Date().getTime()}`;
    console.log(`[MacBook -> Camera] Setting Flashlight intensity: ${value} | URL: ${url}`);
    const beacon = new Image();
    beacon.src = url;
}

toggleBtn.addEventListener('click', () => {
    if (isLightOn) {
        setFlashIntensity(0);
    } else {
        setFlashIntensity(128);
    }
});

// Camera pan/tilt manual sliders
const panSlider = document.getElementById('panSlider');
const tiltSlider = document.getElementById('tiltSlider');
const panVal = document.getElementById('pan-val');
const tiltVal = document.getElementById('tilt-val');
const centerServoBtn = document.getElementById('centerServoBtn');

let lastServoTime = 0;
let servoTimeout = null;

function sendServoCommand(pan, tilt, immediate = false) {
    panVal.innerText = `${pan}°`;
    tiltVal.innerText = `${tilt}°`;

    const now = Date.now();
    const delay = 80;

    if (immediate || now - lastServoTime > delay) {
        lastServoTime = now;
        clearTimeout(servoTimeout);
        
        const url = `${cameraIP}/servo?pan=${pan}&tilt=${tilt}&t=${now}`;
        console.log(`[MacBook -> Camera] Sending Servo angles: Pan=${pan}°, Tilt=${tilt}° | URL: ${url}`);
        const beacon = new Image();
        beacon.src = url;
    } else {
        clearTimeout(servoTimeout);
        servoTimeout = setTimeout(() => {
            sendServoCommand(pan, tilt, true);
        }, delay - (now - lastServoTime));
    }
}

function resetSlidersToCenter() {
    isSliderInteracting = false;
    targetPan = 90;
    targetTilt = 30;
    panSlider.value = 90;
    tiltSlider.value = 30;
}

panSlider.addEventListener('input', () => {
    isSliderInteracting = true;
    targetPan = parseInt(panSlider.value);
});

tiltSlider.addEventListener('input', () => {
    isSliderInteracting = true;
    targetTilt = parseInt(tiltSlider.value);
});

['change', 'mouseup', 'touchend', 'touchcancel'].forEach(evt => {
    panSlider.addEventListener(evt, resetSlidersToCenter);
    tiltSlider.addEventListener(evt, resetSlidersToCenter);
});

centerServoBtn.addEventListener('click', () => {
    resetSlidersToCenter();
});

slider.addEventListener('input', (e) => {
    setFlashIntensity(e.target.value);
});

// ============================================================================
// 🎥 Stream recorder (saves to WebM/MP4 format)
// ============================================================================
const startBtn = document.getElementById('startRecordBtn');
const stopBtn = document.getElementById('stopRecordBtn');
const recStatus = document.getElementById('recordStatus');
const canvas = document.getElementById('hiddenCanvas');
const ctx = canvas.getContext('2d');

let mediaRecorder;
let recordedChunks = [];
let videoCounter = 0;
let canvasRenderLoop;

function drawImageToCanvas() {
    if (robotStream.complete && robotStream.naturalWidth > 0) {
        ctx.drawImage(robotStream, 0, 0, canvas.width, canvas.height);
    }
    canvasRenderLoop = requestAnimationFrame(drawImageToCanvas);
}

startBtn.addEventListener('click', () => {
    recordedChunks = [];
    drawImageToCanvas();

    const canvasStream = canvas.captureStream(30);
    let options = { mimeType: 'video/mp4;codecs=avc1.42E01E,mp4a.40.2' };

    if (!MediaRecorder.isTypeSupported(options.mimeType)) {
        options = { mimeType: 'video/webm;codecs=h264' };
    }

    try {
        mediaRecorder = new MediaRecorder(canvasStream, options);
        mediaRecorder.ondataavailable = (e) => {
            if (e.data.size > 0) recordedChunks.push(e.data);
        };

        mediaRecorder.onstop = () => {
            cancelAnimationFrame(canvasRenderLoop);
            const blob = new Blob(recordedChunks, { type: 'video/mp4' });
            const url = URL.createObjectURL(blob);

            const a = document.createElement('a');
            a.href = url;
            a.download = `ARES_LiveStream_${videoCounter++}.mp4`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);

            recStatus.innerText = "Status: Video exported & saved to Downloads!";
            recStatus.style.color = "var(--success)";
        };

        mediaRecorder.start(1000);
        startBtn.disabled = true;
        stopBtn.disabled = false;
        recStatus.innerText = "🔴 Recording Live Stream...";
        recStatus.style.color = "var(--danger)";
    } catch (err) {
        console.error("Failed to initialize MediaRecorder:", err);
        recStatus.innerText = "Status: Recording format error.";
    }
});

stopBtn.addEventListener('click', () => {
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
        mediaRecorder.stop();
        startBtn.disabled = false;
        stopBtn.disabled = true;
    }
});
