from flask import Flask, render_template, request, redirect, url_for, Response, jsonify, session
import cv2
import os
import time
import threading
import numpy as np
from werkzeug.utils import secure_filename
from detector import detect_vehicles

print("🔥 THIS APP.PY IS RUNNING and runinggggggg 🔥")

app = Flask(__name__)
app.secret_key = "itms_secret_key_123"
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024

USERNAME = "traffic-admin"
PASSWORD = "admin123"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
ALLOWED_EXTENSIONS = {"mp4", "avi", "mov", "mkv"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# app restart ஆனதும் பழைய uploaded videos clear ஆகும்
for old_file in os.listdir(UPLOAD_FOLDER):
    old_path = os.path.join(UPLOAD_FOLDER, old_file)
    if os.path.isfile(old_path):
        try:
            os.remove(old_path)
        except Exception as e:
            print("Could not remove old file:", old_path, e)

latest_lane_stats = {
    1: {"density": 0, "total": 0, "ambulance": "No"},
    2: {"density": 0, "total": 0, "ambulance": "No"},
    3: {"density": 0, "total": 0, "ambulance": "No"},
    4: {"density": 0, "total": 0, "ambulance": "No"},
}

cumulative_stats = {
    1: {"car": 0, "bus": 0, "truck": 0, "motorcycle": 0, "ambulance": 0},
    2: {"car": 0, "bus": 0, "truck": 0, "motorcycle": 0, "ambulance": 0},
    3: {"car": 0, "bus": 0, "truck": 0, "motorcycle": 0, "ambulance": 0},
    4: {"car": 0, "bus": 0, "truck": 0, "motorcycle": 0, "ambulance": 0},
}

signal_state = {
    1: {"state": "red", "timer": "--"},
    2: {"state": "red", "timer": "--"},
    3: {"state": "red", "timer": "--"},
    4: {"state": "red", "timer": "--"},
}

ambulance_memory = {
    1: 0,
    2: 0,
    3: 0,
    4: 0
}

current_green_lane = None
next_green_lane = None
current_phase = "green"
phase_start_time = time.time()

YELLOW_TIME = 3
MIN_GREEN_TIME = 5
SWITCH_MARGIN = 2

current_mode = "NORMAL"
rain_mode = False
pedestrian_request = False

emergency_detected = {
    1: False,
    2: False,
    3: False,
    4: False
}

lane_video_files = {
    1: None,
    2: None,
    3: None,
    4: None,
}

lock = threading.Lock()


def is_logged_in():
    return session.get("logged_in", False)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def get_current_mode():
    global current_mode

    if any(emergency_detected.values()):
        current_mode = "EMERGENCY"
    elif pedestrian_request:
        current_mode = "PEDESTRIAN"
    elif rain_mode:
        current_mode = "RAIN"
    elif sum(latest_lane_stats[l]["total"] for l in range(1, 5)) > 30:
        current_mode = "PEAK"
    else:
        current_mode = "NORMAL"

    return current_mode


def get_lane_video_path(lane_number):
    filename = lane_video_files.get(lane_number)
    if not filename:
        return None

    file_path = os.path.join(UPLOAD_FOLDER, filename)
    if os.path.isfile(file_path):
        return file_path

    return None

current_green_lane = None

def update_all_signals():

    global current_green_lane

    # ---------------- EMERGENCY PRIORITY ---------------- #

    for lane in range(1, 5):

        if emergency_detected[lane]:

            # same ambulance lane already green
            if current_green_lane == lane:
                return

            # old green -> yellow first
            if current_green_lane is not None:

                signal_state[current_green_lane]["state"] = "YELLOW"

                time.sleep(3)

                signal_state[current_green_lane]["state"] = "RED"
                

            # all red
            for i in range(1, 5):
                signal_state[i]["state"] = "RED"

            # ambulance lane green
            signal_state[lane]["state"] = "GREEN"

            current_green_lane = lane

            print(f"🚑 Emergency GREEN -> Lane {lane}")

            return

    # ---------------- NORMAL DENSITY LOGIC ---------------- #

    max_lane = 1
    max_density = latest_lane_stats[1]["density"]

    for lane in range(2, 5):

        if latest_lane_stats[lane]["density"] > max_density:
            max_density = latest_lane_stats[lane]["density"]
            max_lane = lane

    # same lane already green
    if current_green_lane == max_lane:
        return

    # previous green -> yellow
    if current_green_lane is not None:

        signal_state[current_green_lane]["state"] = "YELLOW"

        time.sleep(3)

        signal_state[current_green_lane]["state"] = "RED"

    # all red
    for lane in range(1, 5):
        signal_state[lane]["state"] = "RED"

    # highest density green
    signal_state[max_lane]["state"] = "GREEN"

    current_green_lane = max_lane

    print(f"✅ Density GREEN -> Lane {max_lane}")

def generate_video(lane_number):
    current_video_path = None
    cap = None

    frame_count = 0
    last_counts = {"car": 0, "bus": 0, "truck": 0, "motorcycle": 0, "ambulance": 0}
    last_density = 0
    last_detected_frame = None

    while True:
        try:
            new_video_path = get_lane_video_path(lane_number)

            if new_video_path is None:
                if cap is not None:
                    cap.release()
                    cap = None
                    current_video_path = None

    # 🔥 important: force reset previous frame data
                frame_count = 0
                last_detected_frame = None

                with lock:
                    latest_lane_stats[lane_number] = {
                        "density": 0,
                        "total": 0,
                        "ambulance": "No"
                    }
                

                blank = 255 * np.ones((340, 420, 3), dtype="uint8")
                cv2.putText(blank, f"Lane {lane_number}", (145, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2)
                cv2.putText(blank, "No video uploaded", (100, 160), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
                cv2.putText(blank, "Choose file and upload", (85, 205), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)

                ret, buffer = cv2.imencode(".jpg", blank)
                if ret:
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
                    )

                time.sleep(1)
                continue

            if current_video_path != new_video_path:
                current_video_path = new_video_path

                if cap is not None:
                    cap.release()

                cap = cv2.VideoCapture(current_video_path)
                frame_count = 0
                last_counts = {"car": 0, "bus": 0, "truck": 0, "motorcycle": 0, "ambulance": 0}
                last_density = 0
                last_detected_frame = None
                print(f"🎥 Lane {lane_number} switched to: {current_video_path}")

            if cap is None or not cap.isOpened():
                blank = 255 * np.ones((340, 420, 3), dtype="uint8")
                cv2.putText(blank, f"Lane {lane_number} video not opening", (40, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 0, 255), 2)

                ret, buffer = cv2.imencode(".jpg", blank)
                if ret:
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
                    )

                time.sleep(1)
                continue

            success, frame = cap.read()

            if not success or frame is None:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                time.sleep(0.05)
                continue

            frame = cv2.resize(frame, (420, 340))
            frame_count += 1

            if frame_count % 3 == 0:
                detected_frame, counts, density = detect_vehicles(frame)
                last_counts = counts
                last_density = density
                last_detected_frame = detected_frame.copy()
            else:
                detected_frame = last_detected_frame.copy() if last_detected_frame is not None else frame.copy()
                counts = last_counts
                density = last_density

            total = counts["car"] + counts["bus"] + counts["truck"] + counts["motorcycle"]

            if counts["ambulance"] > 0:
                ambulance_memory[lane_number] = 15
            else:
                if ambulance_memory[lane_number] > 0:
                    ambulance_memory[lane_number] -= 1

            emergency_detected[lane_number] = ambulance_memory[lane_number] > 0

            with lock:
                ambulance_text = "Yes" if emergency_detected[lane_number] else "No"

                latest_lane_stats[lane_number] = {
                    "density": density,
                    "total": total,
                    "ambulance": ambulance_text
                }

                cumulative_stats[lane_number]["car"] = counts.get("car", 0)
                cumulative_stats[lane_number]["bus"] = counts.get("bus", 0)
                cumulative_stats[lane_number]["truck"] = counts.get("truck", 0)
                cumulative_stats[lane_number]["motorcycle"] = counts.get("motorcycle", 0)

# ambulance cumulative update
                if counts.get("ambulance", 0) > 0 and cumulative_stats[lane_number]["ambulance"] == 0:
                    cumulative_stats[lane_number]["ambulance"] = 1
                print(f"Lane {lane_number} | density={density} | signals={[signal_state[i]['state'] for i in range(1,5)]}")

                signal_color = signal_state[lane_number]["state"]
                timer = signal_state[lane_number]["timer"]
                mode = get_current_mode()
                
                print(f"Lane {lane_number} | density={density} | signals={[signal_state[i]['state'] for i in range(1,5)]}")

                signal_color = signal_state[lane_number]["state"]
                timer = signal_state[lane_number]["timer"]
                mode = get_current_mode()

            cv2.rectangle(detected_frame, (0, 285), (420, 340), (0, 0, 0), -1)
            cv2.putText(detected_frame, f"Mode: {mode}", (10, 305), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (255, 255, 255), 1)
            cv2.putText(detected_frame, f"Density: {density}", (145, 305), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (255, 255, 255), 1)
            cv2.putText(detected_frame, f"Emergency: {ambulance_text}", (10, 327), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (255, 255, 255), 1)

            ret, buffer = cv2.imencode(".jpg", detected_frame)
            if not ret:
                continue

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
            )

        except Exception as e:
            import traceback
            print("Lane error:", repr(e))
            traceback.print_exc()

            error_img = 255 * np.ones((340, 420, 3), dtype="uint8")
            cv2.putText(error_img, f"Lane {lane_number} Error", (90, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
            cv2.putText(error_img, str(e)[:40], (20, 200), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2)

            ret, buffer = cv2.imencode(".jpg", error_img)
            if ret:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
                )

            time.sleep(1)


@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = request.form.get("username", "").strip()
        pwd = request.form.get("password", "").strip()

        if user == USERNAME and pwd == PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("dashboard"))

        return render_template("login.html", error="Invalid username or password")

    return render_template("login.html", error="")


@app.route("/home")
def home():
    if not is_logged_in():
        return redirect(url_for("login"))
    return redirect(url_for("dashboard"))


@app.route("/logout")
def logout():
    with lock:
        reset_all_lanes()

    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
def dashboard():
    if not is_logged_in():
        return redirect(url_for("login"))
    return render_template("dashboard.html")

def reset_all_lanes():
    global pedestrian_request, rain_mode, current_mode
    global current_green_lane, next_green_lane, current_phase, phase_start_time

    for i in range(1, 5):
        lane_video_files[i] = None
        latest_lane_stats[i] = {
            "density": 0,
            "total": 0,
            "ambulance": "No"
        }
        cumulative_stats[i] = {
            "car": 0,
            "bus": 0,
            "truck": 0,
            "motorcycle": 0,
            "ambulance": 0
        }
        emergency_detected[i] = False
        signal_state[i] = {
            "state": "red",
            "timer": "--"
        }

    pedestrian_request = False
    rain_mode = False
    current_mode = "NORMAL"
    current_green_lane = None
    next_green_lane = None
    current_phase = "green"
    phase_start_time = time.time()

@app.route("/upload/<int:lane_number>", methods=["POST"])
def upload_video(lane_number):
    if not is_logged_in():
        return redirect(url_for("login"))

    if lane_number not in [1, 2, 3, 4]:
        return "Invalid lane number", 400

    if "video" not in request.files:
        return "No video part found in request", 400

    file = request.files["video"]

    if file.filename is None or file.filename.strip() == "":
        return "No file selected", 400

    if not allowed_file(file.filename):
        return "Only mp4, avi, mov, mkv files are allowed", 400

    ext = secure_filename(file.filename).rsplit(".", 1)[1].lower()
    saved_name = f"lane{lane_number}.{ext}"
    file_path = os.path.join(UPLOAD_FOLDER, saved_name)

    try:
        for old_ext in ["mp4", "avi", "mov", "mkv"]:
            old_path = os.path.join(UPLOAD_FOLDER, f"lane{lane_number}.{old_ext}")
            if os.path.exists(old_path) and old_path != file_path:
                os.remove(old_path)

        file.save(file_path)

        with lock:
            lane_video_files[lane_number] = saved_name
            latest_lane_stats[lane_number] = {
                "density": 0,
                "total": 0,
                "ambulance": "No"
            }
            

        print(f"✅ Lane {lane_number} uploaded: {file_path}")
        return "OK", 200

    except Exception as e:
        print("❌ Upload failed:", str(e))
        return f"Upload failed: {str(e)}", 500


@app.route("/video1")
def video1():
    if not is_logged_in():
        return redirect(url_for("login"))
    return Response(generate_video(1), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/video2")
def video2():
    if not is_logged_in():
        return redirect(url_for("login"))
    return Response(generate_video(2), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/video3")
def video3():
    if not is_logged_in():
        return redirect(url_for("login"))
    return Response(generate_video(3), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/video4")
def video4():
    if not is_logged_in():
        return redirect(url_for("login"))
    return Response(generate_video(4), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/lane_data")
def lane_data():
    if not is_logged_in():
        return jsonify({"error": "unauthorized"}), 401

    with lock:
        update_all_signals()

        data = {}
        for i in range(1, 5):
            data[f"lane{i}"] = {
                "signal": signal_state[i]["state"],
                "timer": signal_state[i]["timer"],
                "density": latest_lane_stats[i]["density"],
                "ambulance": latest_lane_stats[i]["ambulance"],
                "total": latest_lane_stats[i]["total"]
            }

        data["current_mode"] = current_mode

    return jsonify(data)


@app.route("/analysis")
def analysis():
    if not is_logged_in():
        return redirect(url_for("login"))

    with lock:
        stats = {k: v.copy() for k, v in cumulative_stats.items()}
        current_total = {k: latest_lane_stats[k]["total"] for k in range(1, 5)}
        current_density = {k: latest_lane_stats[k]["density"] for k in range(1, 5)}
        mode = current_mode

    return render_template(
        "analysis.html",
        stats=stats,
        current_total=current_total,
        current_density=current_density,
        current_mode=mode
    )


@app.route("/live_dashboard")
def live_dashboard():
    if not is_logged_in():
        return redirect(url_for("login"))

    with lock:
        current_density = {i: latest_lane_stats[i]["density"] for i in range(1, 5)}
        emergency = {i: emergency_detected[i] for i in range(1, 5)}
        lane_signals = {i: signal_state[i]["state"] for i in range(1, 5)}
        uploaded = {i: lane_video_files[i] is not None for i in range(1, 5)}

    return render_template(
        "live_dashboard.html",
        current_density=current_density,
        emergency=emergency,
        lane_signals=lane_signals,
        uploaded=uploaded
    )


if __name__ == "__main__":
    app.run(debug=True, port=5001, threaded=True, use_reloader=False)