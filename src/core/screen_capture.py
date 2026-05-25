import numpy as np
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage, QGuiApplication


class ScreenCaptureThread(QThread):
    """Captura una pantalla/monitor y emite frames"""
    frame_ready = Signal(QImage)
    error = Signal(str)

    def __init__(self, screen_index=0, fps=30):
        super().__init__()
        self.screen_index = screen_index
        self.fps = fps
        self.running = False

    def run(self):
        screens = QGuiApplication.screens()
        if self.screen_index >= len(screens):
            self.error.emit(f"Pantalla {self.screen_index} no encontrada")
            return

        screen = screens[self.screen_index]
        self.running = True
        delay = int(1000 / self.fps)

        while self.running:
            pixmap = screen.grabWindow(0)
            if pixmap.isNull():
                self.msleep(delay)
                continue
            img = pixmap.toImage().convertToFormat(QImage.Format_RGB888)
            self.frame_ready.emit(img.copy())
            self.msleep(delay)

    def stop(self):
        self.running = False
        self.wait(3000)

    @staticmethod
    def get_screens():
        """Devuelve lista de pantallas disponibles"""
        screens = QGuiApplication.screens()
        result = []
        for i, s in enumerate(screens):
            geo = s.geometry()
            result.append(f"Pantalla {i}: {s.name()} ({geo.width()}x{geo.height()})")
        return result
