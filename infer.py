import cv2
import json
import argparse
import numpy as np
import pandas as pd
from datetime import datetime
from ultralytics import YOLO

def compute_urgency_score(area_m2, depth_cm=6.0, lane_impact=1.2):
    """Computes Urgency Score (US) = min(10.0, Area_Weight * Depth_Factor * Impact)"""
    area_weight = min(area_m2 * 2.5, 4.0)
    depth_factor = min(depth_cm / 2.0, 3.0)
    raw_score = area_weight * depth_factor * lane_impact
    return round(min(10.0, max(1.0, raw_score)), 1)

def run_inference(video_path, model_path="yolov8n-seg.pt", output_video="outputs/annotated_demo.mp4"):
    model = YOLO(model_path)
    cap = cv2.VideoCapture(video_path)
    
    fps = int(cap.get(cv2.CAP_PROP_FPS)) or 30
    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1280
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 720
    
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_video, fourcc, fps, (width, height))
    
    incidents = []
    frame_count = 0
    
    print(f"[+] Running Edge Inference on: {video_path}")
    
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
            
        frame_count += 1
        results = model(frame, verbose=False)
        
        for r in results:
            if r.masks is not None:
                for mask, box in zip(r.masks.xy, r.boxes):
                    cls_id = int(box.cls[0])
                    conf = float(box.conf[0])
                    
                    # Convert pixel area to approximate physical area (m²)
                    pixel_area = cv2.contourArea(mask.astype(np.int32))
                    area_m2 = round((pixel_area / (width * height)) * 12.5, 2)
                    
                    if area_m2 > 0.1:
                        urgency = compute_urgency_score(area_m2)
                        
                        # Draw segmentation polygon
                        pts = mask.astype(np.int32).reshape((-1, 1, 2))
                        color = (0, 0, 255) if urgency >= 8.0 else (0, 255, 255)
                        cv2.polylines(frame, [pts], True, color, 2)
                        
                        # Label text
                        label = f"Defect | Area: {area_m2}m2 | Score: {urgency}"
                        x, y = int(mask[0][0]), int(mask[0][1])
                        cv2.putText(frame, label, (x, max(y - 10, 20)), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                        
                        # Save log entry
                        if frame_count % fps == 0:  # Sample every 1 second
                            incidents.append({
                                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "incident_id": f"INF-20260811-{len(incidents)+1:03d}",
                                "zone_id": "ELCIA_WEST_PHASE_GATE4",
                                "defect_type": "POTHOLE_SEVERITY_HIGH" if urgency >= 8.0 else "WATERLOGGING_ZONE",
                                "surface_area_m2": area_m2,
                                "urgency_score": urgency,
                                "action_status": "DISPATCH_REQUIRED" if urgency >= 8.0 else "LOGGED"
                            })

        out.write(frame)
        
    cap.release()
    out.release()
    
    # Export CSV Log
    df = pd.DataFrame(incidents)
    df.to_csv("outputs/incidents_log.csv", index=False)
    print(f"[+] Processing Complete! Saved annotated video to '{output_video}' & CSV to 'outputs/incidents_log.csv'.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=str, default="data/sample_road.mp4", help="Path to input video")
    args = parser.parse_args()
    run_inference(args.source)