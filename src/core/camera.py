import cv2
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage


class CameraThread(QThread):
    frame_ready = Signal(QImage)
    error = Signal(str)

    def __init__(self, source=0):
        super().__init__()
        self.source = source  # int para cámara, str para archivo
        self.running = False

    def run(self):
        if isinstance(self.source, int):
            cap = cv2.VideoCapture(self.source, cv2.CAP_DSHOW)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        else:
            cap = cv2.VideoCapture(self.source)

        if not cap.isOpened():
            self.error.emit(f"No se pudo abrir: {self.source}")
            return

        self.running = True
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        delay = int(1000 / fps)

        while self.running:
            ret, frame = cap.read()
            if not ret:
                if isinstance(self.source, str):
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # loop video
                    continue
                else:
                    self.msleep(delay)
                    continue
            if frame is None or frame.size == 0:
                self.msleep(delay)
                continue
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = frame.shape
            bytes_per_line = ch * w
            img = QImage(frame.data, w, h, bytes_per_line, QImage.Format_RGB888)
            self.frame_ready.emit(img.copy())
            self.msleep(delay)

        cap.release()

    def stop(self):
        self.running = False
        self.wait(3000)
