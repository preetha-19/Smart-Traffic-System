import os
import cv2
from ultralytics import YOLO

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

vehicle_model = YOLO("yolov8s.pt")
ambulance_model = YOLO("best.pt")

VEHICLE_CLASSES = {
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck"
}

BOX_COLORS = {
    "car": (0, 255, 0),
    "motorcycle": (255, 200, 0),
    "bus": (0, 165, 255),
    "truck": (255, 0, 255)
}

def detect_vehicles(frame):

    detected_frame = frame.copy()

    counts = {
        "car": 0,
        "bus": 0,
        "truck": 0,
        "motorcycle": 0,
        "ambulance": 0
    }

    vehicle_results = vehicle_model(frame, verbose=False)
    ambulance_results = ambulance_model(
    frame,
    verbose=False,
    conf=0.80
)

    # ---------------- NORMAL VEHICLE DETECTION ---------------- #

    for r in vehicle_results:

        boxes = r.boxes

        if boxes is None:
            continue

        for box in boxes:

            cls = int(box.cls[0].item())
            conf = float(box.conf[0].item())

            if cls not in VEHICLE_CLASSES:
                continue

            label = VEHICLE_CLASSES[cls]
            counts[label] += 1

            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())

            color = BOX_COLORS[label]

            cv2.rectangle(
                detected_frame,
                (x1, y1),
                (x2, y2),
                color,
                2
            )

            text = f"{label} {conf:.2f}"

            cv2.putText(
                detected_frame,
                text,
                (x1, max(20, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (255, 255, 255),
                2
            )

    # ---------------- AMBULANCE DETECTION ---------------- #

    for r in ambulance_results:

        boxes = r.boxes

        if boxes is None:
            continue

        for box in boxes:

            conf = float(box.conf[0].item())

            if conf < 0.85:
                continue

            counts["ambulance"] += 1

            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())

            cv2.rectangle(
                detected_frame,
                (x1, y1),
                (x2, y2),
                (0, 0, 255),
                3
            )

            cv2.putText(
                detected_frame,
                "AMBULANCE",
                (x1, max(20, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 0, 255),
                2
            )

    density = (
        counts["car"]
        + counts["bus"]
        + counts["truck"]
        + counts["motorcycle"]
    )

    return detected_frame, counts, density