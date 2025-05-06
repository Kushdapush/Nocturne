from fastapi import FastAPI, Response
from fastapi.responses import StreamingResponse
import cv2
import os
import subprocess
import time
from fastapi.middleware.cors import CORSMiddleware
import subprocess
import shutil
import re


app = FastAPI()
cap = None
detection_process = None

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/drowsiness/start")
def start_drowsiness():
    global detection_process
    if detection_process is None:
        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'prediction/src/main.py'))
        python_path = subprocess.check_output(['pyenv', 'prefix', 'edp']).decode('utf-8').strip()
        python_path = os.path.join(python_path, 'bin', 'python')
        detection_process = subprocess.Popen([python_path, script_path, "--config", os.path.join(os.path.dirname(script_path), '..', 'config/config.yaml')])

    return {"status": "started"}

@app.post("/drowsiness/stop")
def stop_drowsiness():
    global detection_process
    if detection_process:
        detection_process.terminate()
        detection_process = None
    return {"status": "stopped"}

@app.get("/drowsiness/live_status")
def live_status():
    def event_stream():
        last_status = "AWAKE"
        while True:
            try:
                with open("/tmp/drowsiness_status.txt", "r") as f:
                    current_status = f.read().strip()
                if current_status != last_status:
                    last_status = current_status
                    yield f"data: {current_status}\n\n"
            except:
                yield "data: unknown\n\n"
            time.sleep(1)
    return StreamingResponse(event_stream(), media_type="text/event-stream")

@app.get("/camera/start")
def start_camera():
    global cap
    cap = cv2.VideoCapture(0)
    return {"status": "camera started"}

@app.get("/camera/stop")
def stop_camera():
    global cap
    if cap:
        cap.release()
        cap = None
    return {"status": "camera stopped"}

def gen_frames():
    global cap
    while cap and cap.isOpened():
        success, frame = cap.read()
        if not success:
            break
        _, buffer = cv2.imencode('.jpg', frame)
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

@app.get("/video")
def video_feed():
    return StreamingResponse(gen_frames(), media_type="multipart/x-mixed-replace; boundary=frame")

@app.post("/volume/{direction}")
def volume_control(direction: str):
    if direction == "up":
        subprocess.run(["amixer", "set", "Master", "5%+"])
    elif direction == "down":
        subprocess.run(["amixer", "set", "Master", "5%-"])
    return {"volume": direction}

@app.post("/system/shutdown")
def shutdown():
    subprocess.run(["sudo", "shutdown", "now"])
    return {"status": "shutting down"}

@app.get("/gemini_response")
def get_gemini_response():
    def event_stream():
        while True:
            try:
                with open("/tmp/gemini_response.txt", "r") as f:
                    current_text = f.read().strip()
                yield f"data: {current_text}\n\n"
            except:
                yield "data: \n\n"
            time.sleep(1)
    return StreamingResponse(event_stream(), media_type="text/event-stream")

@app.get("/system/battery")
def get_battery_status():
    """Get current battery status (level and charging state)"""
    try:
        # Check if we're running on Linux with available battery info
        if shutil.which("upower"):
            # Get battery info using upower
            output = subprocess.check_output(
                ["upower", "-i", "/org/freedesktop/UPower/devices/battery_BAT0"], 
                universal_newlines=True
            )
            
            # Extract percentage
            percentage_match = re.search(r'percentage:\s+(\d+)%', output)
            percentage = int(percentage_match.group(1)) if percentage_match else 50
            
            # Extract charging state
            charging_match = re.search(r'state:\s+(\w+)', output)
            charging_state = charging_match.group(1) if charging_match else "unknown"
            is_charging = charging_state in ["charging", "fully-charged"]
            
            return {"level": percentage, "charging": is_charging}
        
        # Alternative for Raspberry Pi
        elif shutil.which("vcgencmd"):
            # Get power supply state
            power_state = subprocess.check_output(
                ["vcgencmd", "get_throttled"], 
                universal_newlines=True
            )
            # This doesn't give percentage but can detect power issues
            # Ideally, you'd implement a proper voltage/current measurement
            # For now, just return a default value
            return {"level": 80, "charging": True}
        
        # Fallback for development environments
        else:
            return {"level": 75, "charging": False}
            
    except Exception as e:
        print(f"Error getting battery status: {e}")
        return {"level": 50, "charging": False}