from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from pydantic import BaseModel


class EyeTrackingResult(BaseModel):
    face_bbox: list[int] | None = None
    left_eye_bbox: list[int] | None = None
    right_eye_bbox: list[int] | None = None
    eye_midpoint: list[float] | None = None
    eye_confidence: float = 0.0
    tracking_source: str = "person_center"


class FaceEyeTracker:
    def __init__(self) -> None:
        cascades = Path(cv2.data.haarcascades)
        self.face = cv2.CascadeClassifier(str(cascades / "haarcascade_frontalface_default.xml"))
        self.eye = cv2.CascadeClassifier(str(cascades / "haarcascade_eye_tree_eyeglasses.xml"))

    def locate(
        self,
        frame: np.ndarray,
        person_bbox: list[int],
        person_center_x_norm: float,
    ) -> EyeTrackingResult:
        x1, y1, x2, y2 = person_bbox
        roi = frame[max(0, y1):max(y1 + 1, y2), max(0, x1):max(x1 + 1, x2)]
        if roi.size == 0:
            return EyeTrackingResult(eye_midpoint=[person_center_x_norm, 0.4], tracking_source="person_center")
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        faces = self.face.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40))
        if len(faces) == 0:
            return EyeTrackingResult(eye_midpoint=[person_center_x_norm, 0.4], tracking_source="person_center")

        fx, fy, fw, fh = max(faces, key=lambda item: item[2] * item[3])
        face_gray = gray[fy:fy + fh, fx:fx + fw]
        eyes = self.eye.detectMultiScale(face_gray, scaleFactor=1.1, minNeighbors=4, minSize=(12, 12))
        abs_face = [x1 + int(fx), y1 + int(fy), x1 + int(fx + fw), y1 + int(fy + fh)]
        if len(eyes) >= 2:
            eyes_sorted = sorted(eyes, key=lambda item: item[0])[:2]
            left, right = eyes_sorted[0], eyes_sorted[1]
            left_abs = [x1 + int(fx + left[0]), y1 + int(fy + left[1]), x1 + int(fx + left[0] + left[2]), y1 + int(fy + left[1] + left[3])]
            right_abs = [x1 + int(fx + right[0]), y1 + int(fy + right[1]), x1 + int(fx + right[0] + right[2]), y1 + int(fy + right[1] + right[3])]
            eye_center_x = ((left_abs[0] + left_abs[2] + right_abs[0] + right_abs[2]) / 4) / frame.shape[1]
            eye_center_y = ((left_abs[1] + left_abs[3] + right_abs[1] + right_abs[3]) / 4) / frame.shape[0]
            return EyeTrackingResult(
                face_bbox=abs_face,
                left_eye_bbox=left_abs,
                right_eye_bbox=right_abs,
                eye_midpoint=[round(float(eye_center_x), 4), round(float(eye_center_y), 4)],
                eye_confidence=0.9,
                tracking_source="eye_midpoint",
            )
        face_center_x = (abs_face[0] + abs_face[2]) / 2 / frame.shape[1]
        face_center_y = (abs_face[1] + abs_face[3]) / 2 / frame.shape[0]
        return EyeTrackingResult(
            face_bbox=abs_face,
            eye_midpoint=[round(float(face_center_x), 4), round(float(face_center_y), 4)],
            eye_confidence=0.4,
            tracking_source="face_center",
        )

