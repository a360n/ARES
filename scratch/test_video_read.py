import cv2
import os

video_path = '/Users/alial-khazali/Documents/ARES/uploads/First_Simulator_Video.mov'
print("File exists:", os.path.exists(video_path))
print("File size:", os.path.getsize(video_path))

cap = cv2.VideoCapture(video_path)
print("Is opened:", cap.isOpened())
if cap.isOpened():
    print("FPS:", cap.get(cv2.CAP_PROP_FPS))
    print("Frame count:", cap.get(cv2.CAP_PROP_FRAME_COUNT))
    ret, frame = cap.read()
    print("Read first frame:", ret, frame is not None)
    if ret and frame is not None:
        print("Frame shape:", frame.shape)
cap.release()
