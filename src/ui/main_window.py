import warnings
import os
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QSplitter, QLabel, QPushButton, QListWidget, QSlider,
    QGroupBox, QCheckBox, QLineEdit, QComboBox, QSpinBox, QFileDialog,
    QTabWidget, QTextEdit, QScrollArea, QTreeView, QFileSystemModel,
    QColorDialog, QMenu, QProgressBar, QTreeWidget, QTreeWidgetItem,
    QListWidgetItem
)
from PySide6.QtCore import Qt, QDir, QRect, QTimer, QSortFilterProxyModel
from PySide6.QtGui import QFont, QPixmap, QFontDatabase, QPainter, QColor, QPen, QIcon, QPainterPath, QImage
from src.core.camera import CameraThread
from src.core.audio_player import AudioMixer
from src.core.screen_capture import ScreenCaptureThread


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GBSturio - Video Studio")
        self.setMinimumSize(1400, 960)
        # Icono de la ventana
        app_icon = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "icono.png")
        if os.path.exists(app_icon):
            self.setWindowIcon(QIcon(app_icon))
        self.setStyleSheet(self._get_stylesheet())
        self.camera_thread = None
        self._dark_mode = True  # Arranca en tema oscuro
        # Ruta de iconos
        self._icons_path = os.path.join(os.path.dirname(__file__), "icons", "png_botones")
        self.live_window = None
        self.saved_overlays = []
        self.active_preview = "A"  # Foco activo: "A" o "B"
        # Screen capture
        self.screen_capture_thread = None
        # Camera PiP (picture in picture)
        self.pip_camera_thread = None
        self.pip_enabled = False
        self.pip_shape = "circle"  # circle, square, none
        self.pip_frame = None  # último frame de la cámara PiP
        self._pip_target = "LIVE"  # A, B, o LIVE
        # Transición activa
        self._transition_active = False
        # Audio player
        self.audio_mixer = AudioMixer(self)
        self.audio_target = "A"  # A qué canal se envió el último audio
        # Frame base (sin overlay) para cada preview
        self.base_frame_a = None  # QPixmap limpio de preview A
        self.base_frame_b = None  # QPixmap limpio de preview B
        self.base_frame_live = None  # QPixmap limpio del live
        # Colores del zócalo
        self.overlay_text_color = QColor(255, 255, 255)  # blanco
        self.overlay_bg_color = QColor(0, 0, 0, 160)     # negro semi-transparente
        # Overlay de texto activo (lista para multi-zócalo)
        self.overlays_preview = []  # lista de dicts
        self.overlays_live = []     # lista de dicts
        self.overlay_timer_preview = QTimer(self)
        self.overlay_timer_preview.setSingleShot(True)
        self.overlay_timer_preview.timeout.connect(self._clear_overlay_preview)
        self.overlay_timer_live = QTimer(self)
        self.overlay_timer_live.setSingleShot(True)
        self.overlay_timer_live.timeout.connect(self._clear_overlay_live)
        self._build_ui()

    def closeEvent(self, event):
        if self.camera_thread:
            self.camera_thread.stop()
        if self.screen_capture_thread:
            self.screen_capture_thread.stop()
        if self.pip_camera_thread:
            self.pip_camera_thread.stop()
        self.audio_mixer.stop_all()
        if self.live_window:
            self.live_window.close()
        event.accept()

    # --- Acciones ---
    def _start_camera(self):
        if self.camera_thread:
            self.camera_thread.stop()
            self.camera_thread.deleteLater()
        cam_index = self.cmb_cameras.currentIndex()
        self.camera_thread = CameraThread(cam_index)
        if self.active_preview == "A":
            self.camera_thread.frame_ready.connect(self._update_preview_a)
        else:
            self.camera_thread.frame_ready.connect(self._update_preview_b)
        self.camera_thread.error.connect(self._camera_error)
        self.camera_thread.start()

    def _detect_cameras(self):
        import cv2
        self.cmb_cameras.clear()
        for i in range(10):
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            if cap.isOpened():
                self.cmb_cameras.addItem(f"Cámara {i}")
                cap.release()
            else:
                break

    def _load_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Cargar archivo de video", "",
            "Videos (*.mp4 *.avi *.mkv *.mov *.webm);;Imágenes (*.png *.jpg *.bmp);;Todos (*)"
        )
        if path:
            self.file_list.addItem(path)
            # Mostrar en pre-escucha B
            if path.lower().endswith(('.png', '.jpg', '.bmp', '.jpeg')):
                pixmap = QPixmap(path)
                self.preview_b.setPixmap(pixmap.scaled(
                    self.preview_b.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
                ))
            else:
                self._play_video_file(path)

    def _play_video_file(self, path):
        if self.camera_thread:
            self.camera_thread.stop()
            self.camera_thread.deleteLater()
        self.camera_thread = CameraThread(path)
        self.camera_thread.frame_ready.connect(self._update_preview_b)
        self.camera_thread.error.connect(self._camera_error)
        self.camera_thread.start()

    def _update_preview_b(self, img):
        img = self._apply_camera_effects(img)
        pixmap = QPixmap.fromImage(img)
        self.base_frame_b = pixmap.copy()
        if self.pip_enabled and self.pip_frame and self._pip_target == "B":
            pixmap = self._composite_pip(pixmap)
        if self.overlays_preview and self.active_preview == "B":
            for ov in self.overlays_preview:
                pixmap = self._paint_overlay_on_pixmap(pixmap, ov)
        self.preview_b.setPixmap(pixmap.scaled(
            self.preview_b.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        ))

    def _camera_error(self, msg):
        self.preview_a.setText(f"Error: {msg}")

    def _update_preview_a(self, img):
        img = self._apply_camera_effects(img)
        pixmap = QPixmap.fromImage(img)
        self.base_frame_a = pixmap.copy()
        if self.pip_enabled and self.pip_frame and self._pip_target == "A":
            pixmap = self._composite_pip(pixmap)
        if self.overlays_preview and self.active_preview == "A":
            for ov in self.overlays_preview:
                pixmap = self._paint_overlay_on_pixmap(pixmap, ov)
        self.preview_a.setPixmap(pixmap.scaled(
            self.preview_a.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        ))

    def _send_a_to_live(self):
        pixmap = self.preview_a.pixmap()
        if pixmap:
            self.live_label.setPixmap(pixmap.scaled(
                self.live_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            ))
            if self.camera_thread:
                try:
                    self.camera_thread.frame_ready.disconnect(self._update_live)
                except (RuntimeError, TypeError):
                    pass
                self.camera_thread.frame_ready.connect(self._update_live)

    def _send_b_to_live(self):
        pixmap = self.preview_b.pixmap()
        if pixmap:
            self.live_label.setPixmap(pixmap.scaled(
                self.live_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            ))

    def _update_live(self, img):
        if self._transition_active:
            return
        img = self._apply_camera_effects(img)
        pixmap = QPixmap.fromImage(img)
        self.base_frame_live = pixmap.copy()
        if self.pip_enabled and self.pip_frame and self._pip_target == "LIVE":
            pixmap = self._composite_pip(pixmap)
        if self.overlays_live:
            for ov in self.overlays_live:
                pixmap = self._paint_overlay_on_pixmap(pixmap, ov)
        # Pintar alerta si está activa en el vivo
        if hasattr(self, '_alert_visible') and self._alert_visible and self._alert_target == "live":
            pixmap = self._draw_alert_on_pixmap(pixmap, self._alert_text, self._alert_position)
        self.live_label.setPixmap(pixmap.scaled(
            self.live_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        ))
        if self.live_window:
            self.live_window.update_frame(pixmap)

    def _text_to_preview(self):
        text = self.txt_overlay.toPlainText().strip()
        if not text:
            return
        overlay_data = self._build_overlay_data(text)
        if self.chk_multi_overlay.isChecked():
            # Multi: reemplazar si ya hay uno en la misma posición, sino agregar
            pos = overlay_data["position"]
            self.overlays_preview = [ov for ov in self.overlays_preview if ov["position"] != pos]
            self.overlays_preview.append(overlay_data)
        else:
            # Simple: reemplazar todo
            self.overlays_preview = [overlay_data]
        # Pintar inmediatamente
        preview = self._get_active_preview()
        self._draw_overlays_on_label(preview, self.overlays_preview)
        # Timer
        duration = self.spn_duration.value() * 1000
        if duration > 0:
            self.overlay_timer_preview.start(int(duration))
        else:
            self.overlay_timer_preview.stop()

    def _text_to_live(self):
        text = self.txt_overlay.toPlainText().strip()
        if not text:
            return
        overlay_data = self._build_overlay_data(text)
        if self.chk_multi_overlay.isChecked():
            pos = overlay_data["position"]
            self.overlays_live = [ov for ov in self.overlays_live if ov["position"] != pos]
            self.overlays_live.append(overlay_data)
        else:
            self.overlays_live = [overlay_data]
        self._draw_overlays_on_label(self.live_label, self.overlays_live)
        duration = self.spn_duration.value() * 1000
        if duration > 0:
            self.overlay_timer_live.start(int(duration))
        else:
            self.overlay_timer_live.stop()

    def _build_overlay_data(self, text):
        return {
            "text": text,
            "font": self.cmb_font.currentText(),
            "size": self.spn_font_size.value(),
            "position": self.cmb_position.currentText(),
            "height_offset": self.spn_height.value(),
            "text_color": QColor(self.overlay_text_color),
            "bg_color": QColor(self.overlay_bg_color),
        }

    def _clear_overlay_preview(self):
        self.overlays_preview = []
        # Repintar con frame base limpio
        preview = self._get_active_preview()
        pixmap = self._get_base_frame_for(preview)
        preview.setPixmap(pixmap.scaled(
            preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        ))

    def _clear_overlay_live(self):
        self.overlays_live = []
        pixmap = self._get_base_frame_for(self.live_label)
        self.live_label.setPixmap(pixmap.scaled(
            self.live_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        ))

    def _clear_all_overlays(self):
        """Limpia todos los zócalos activos de preview y live"""
        self.overlays_preview = []
        self.overlays_live = []
        self.overlay_timer_preview.stop()
        self.overlay_timer_live.stop()
        # Repintar frames limpios
        preview = self._get_active_preview()
        pixmap = self._get_base_frame_for(preview)
        preview.setPixmap(pixmap.scaled(
            preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        ))
        pixmap_live = self._get_base_frame_for(self.live_label)
        self.live_label.setPixmap(pixmap_live.scaled(
            self.live_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        ))

    # --- Audio controls ---
    def _on_vol_a_changed(self, value):
        """Slider Pre A cambia volumen"""
        self.lbl_vol_a.setText(f"{value}%")
        master = self.slider_master_vol.value() / 100.0
        self.audio_mixer.channel_a.set_volume((value / 100.0) * master)

    def _on_vol_b_changed(self, value):
        """Slider Pre B cambia volumen"""
        self.lbl_vol_b.setText(f"{value}%")
        master = self.slider_master_vol.value() / 100.0
        self.audio_mixer.channel_b.set_volume((value / 100.0) * master)

    def _on_master_volume_changed(self, value):
        self.lbl_master_vol.setText(f"{value}%")
        self.audio_mixer.channel_master.set_volume(value / 100.0)
        # También afecta a los canales A y B proporcionalmente
        vol_a = self.slider_vol_a.value() / 100.0
        vol_b = self.slider_vol_b.value() / 100.0
        self.audio_mixer.channel_a.set_volume(vol_a * (value / 100.0))
        self.audio_mixer.channel_b.set_volume(vol_b * (value / 100.0))

    def _on_master_device_changed(self, index):
        """Cambia el dispositivo de salida de audio del master"""
        if hasattr(self, '_audio_devices') and index < len(self._audio_devices):
            device = self._audio_devices[index]
            self.audio_mixer.channel_master.set_device(device)

    def _on_device_a_changed(self, index):
        """Cambia el dispositivo de salida de Pre A"""
        if hasattr(self, '_audio_devices') and index < len(self._audio_devices):
            device = self._audio_devices[index]
            self.audio_mixer.channel_a.set_device(device)

    def _on_device_b_changed(self, index):
        """Cambia el dispositivo de salida de Pre B"""
        if hasattr(self, '_audio_devices') and index < len(self._audio_devices):
            device = self._audio_devices[index]
            self.audio_mixer.channel_b.set_device(device)

    def _mute_a(self):
        ch = self.audio_mixer.channel_a
        ch.mute(not ch.is_muted())
        if ch.is_muted():
            self.led_a.setStyleSheet("color: #e53935; font-size: 14px;")
        else:
            self.led_a.setStyleSheet("color: #4caf50; font-size: 14px;")

    def _mute_b(self):
        ch = self.audio_mixer.channel_b
        ch.mute(not ch.is_muted())
        if ch.is_muted():
            self.led_b.setStyleSheet("color: #e53935; font-size: 14px;")
        else:
            self.led_b.setStyleSheet("color: #4caf50; font-size: 14px;")

    def _mute_master(self):
        ch = self.audio_mixer.channel_master
        ch.mute(not ch.is_muted())
        if ch.is_muted():
            self.led_master.setStyleSheet("color: #e53935; font-size: 14px;")
        else:
            self.led_master.setStyleSheet("color: #4caf50; font-size: 14px;")

    def _solo_a(self):
        """Solo canal A: mutea B y Master, deja solo A"""
        self.audio_mixer.channel_b.mute(True)
        self.audio_mixer.channel_master.mute(True)
        self.audio_mixer.channel_a.mute(False)
        self.led_a.setStyleSheet("color: #ffeb3b; font-size: 16px;")
        self.led_b.setStyleSheet("color: #e53935; font-size: 16px;")
        self.led_master.setStyleSheet("color: #e53935; font-size: 16px;")
        self.btn_mute_a.setStyleSheet("background-color: #4caf50; border-radius: 4px;")
        self.btn_mute_b.setStyleSheet("background-color: #e53935; border-radius: 4px;")
        self.btn_mute_master.setStyleSheet("background-color: #4caf50; border-radius: 4px;")

    def _solo_b(self):
        """Solo canal B: mutea A y Master, deja solo B"""
        self.audio_mixer.channel_a.mute(True)
        self.audio_mixer.channel_master.mute(True)
        self.audio_mixer.channel_b.mute(False)
        self.led_b.setStyleSheet("color: #ffeb3b; font-size: 16px;")
        self.led_a.setStyleSheet("color: #e53935; font-size: 16px;")
        self.led_master.setStyleSheet("color: #e53935; font-size: 16px;")
        self.btn_mute_b.setStyleSheet("background-color: #4caf50; border-radius: 4px;")
        self.btn_mute_a.setStyleSheet("background-color: #e53935; border-radius: 4px;")
        self.btn_mute_master.setStyleSheet("background-color: #4caf50; border-radius: 4px;")

    def _assign_a_to_master(self):
        """Envía Pre A al Master con transición y lo saca del Pre A"""
        # Audio
        ch_a = self.audio_mixer.channel_a
        if ch_a.current_file:
            self.audio_mixer.channel_master.play(ch_a.current_file)
            ch_a.stop()
        # Video: aplicar transición al live
        if self.base_frame_a:
            self._apply_transition_to_live(self.base_frame_a)
        # Limpiar Pre A
        self.base_frame_a = None
        pixmap = QPixmap(self.preview_a.size())
        pixmap.fill(QColor(26, 26, 46))
        self.preview_a.setPixmap(pixmap)
        # Si hay camera thread conectado a A, reconectar a live
        if self.camera_thread:
            try:
                self.camera_thread.frame_ready.disconnect(self._update_preview_a)
            except (RuntimeError, TypeError):
                pass
            try:
                self.camera_thread.frame_ready.disconnect(self._update_live)
            except (RuntimeError, TypeError):
                pass
            self.camera_thread.frame_ready.connect(self._update_live)
        # Screen capture
        if self.screen_capture_thread:
            try:
                self.screen_capture_thread.frame_ready.disconnect(self._update_screen_frame_a)
            except (RuntimeError, TypeError):
                pass
            try:
                self.screen_capture_thread.frame_ready.disconnect(self._update_live_screen)
            except (RuntimeError, TypeError):
                pass
            self.screen_capture_thread.frame_ready.connect(self._update_live_screen)

    def _assign_b_to_master(self):
        """Envía Pre B al Master con transición y lo saca del Pre B"""
        # Audio
        ch_b = self.audio_mixer.channel_b
        if ch_b.current_file:
            self.audio_mixer.channel_master.play(ch_b.current_file)
            ch_b.stop()
        # Video: aplicar transición al live
        if self.base_frame_b:
            self._apply_transition_to_live(self.base_frame_b)
        # Limpiar Pre B
        self.base_frame_b = None
        pixmap = QPixmap(self.preview_b.size())
        pixmap.fill(QColor(26, 26, 46))
        self.preview_b.setPixmap(pixmap)
        # Si hay camera thread conectado a B, reconectar a live
        if self.camera_thread:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                try:
                    self.camera_thread.frame_ready.disconnect(self._update_preview_b)
                except (RuntimeError, TypeError):
                    pass
                try:
                    self.camera_thread.frame_ready.disconnect(self._update_live)
                except (RuntimeError, TypeError):
                    pass
            self.camera_thread.frame_ready.connect(self._update_live)
        # Screen capture
        if self.screen_capture_thread:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                try:
                    self.screen_capture_thread.frame_ready.disconnect(self._update_screen_frame_b)
                except (RuntimeError, TypeError):
                    pass
                try:
                    self.screen_capture_thread.frame_ready.disconnect(self._update_live_screen)
                except (RuntimeError, TypeError):
                    pass
            self.screen_capture_thread.frame_ready.connect(self._update_live_screen)

    def _update_live_screen(self, img):
        """Actualiza el live con frame de pantalla + PiP"""
        if self._transition_active:
            return
        pixmap = QPixmap.fromImage(img)
        if self.pip_enabled and self.pip_frame:
            pixmap = self._composite_pip(pixmap)
        self.base_frame_live = pixmap.copy()
        if self.overlays_live:
            for ov in self.overlays_live:
                pixmap = self._paint_overlay_on_pixmap(pixmap, ov)
        # Pintar alerta si está activa
        if hasattr(self, '_alert_visible') and self._alert_visible and self._alert_target == "live":
            pixmap = self._draw_alert_on_pixmap(pixmap, self._alert_text, self._alert_position)
        self.live_label.setPixmap(pixmap.scaled(
            self.live_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        ))
        if self.live_window:
            self.live_window.update_frame(pixmap)

    def _stop_audio(self):
        self.audio_mixer.stop_all()
        self.lbl_now_playing.setText("Sin reproducción")
        self.lbl_time.setText("00:00 / 00:00")
        self.progress_bar.setValue(0)
        # Ocultar indicadores
        self.lbl_audio_icon_a.setVisible(False)
        self.lbl_audio_name_a.setText("")
        self.progress_a.setVisible(False)
        self.lbl_audio_icon_b.setVisible(False)
        self.lbl_audio_name_b.setText("")
        self.progress_b.setVisible(False)

    def _show_speaker_in_preview(self, preview):
        """Muestra un icono de parlante en la pre-escucha cuando se carga audio sin video"""
        icons_path = os.path.join(os.path.dirname(__file__), "icons")
        speaker_path = os.path.join(icons_path, "speaker.svg")
        pixmap = QPixmap(preview.size())
        pixmap.fill(QColor(26, 26, 46))
        # Dibujar parlante centrado
        if os.path.exists(speaker_path):
            speaker_pix = QPixmap(speaker_path).scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            painter = QPainter(pixmap)
            x = (pixmap.width() - speaker_pix.width()) // 2
            y = (pixmap.height() - speaker_pix.height()) // 2
            painter.drawPixmap(x, y, speaker_pix)
            painter.end()
        # Guardar como base frame
        if preview == self.preview_a:
            self.base_frame_a = pixmap.copy()
        else:
            self.base_frame_b = pixmap.copy()
        preview.setPixmap(pixmap.scaled(
            preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        ))

    def _pause_audio(self):
        self.audio_mixer.channel_a.pause()
        self.audio_mixer.channel_b.pause()
        self.audio_mixer.channel_master.pause()

    def _resume_audio(self):
        self.audio_mixer.channel_a.resume()
        self.audio_mixer.channel_b.resume()
        self.audio_mixer.channel_master.resume()

    def _on_playback_started(self, name):
        # Mostrar indicador en la pre-escucha correspondiente
        if self.audio_target == "A":
            self.lbl_audio_icon_a.setVisible(True)
            self.lbl_audio_name_a.setText(name)
            self.progress_a.setVisible(True)
            self.progress_a.setValue(0)
        elif self.audio_target == "B":
            self.lbl_audio_icon_b.setVisible(True)
            self.lbl_audio_name_b.setText(name)
            self.progress_b.setVisible(True)
            self.progress_b.setValue(0)

    # Handlers de posición/duración por canal
    def _on_pos_a(self, pos_ms):
        if pos_ms <= 0 or self._dur_a <= 0:
            return
        pct = min(int((pos_ms / self._dur_a) * 100), 100)
        self.progress_ch_a.setValue(pct)
        self.lbl_time_a.setText(f"{self._ms_to_time(pos_ms)}/{self._ms_to_time(self._dur_a)}")
        self.progress_a.setValue(pct)
        self.lbl_audio_time_a.setText(f"{self._ms_to_time(pos_ms)}/{self._ms_to_time(self._dur_a)}")

    def _on_dur_a(self, dur):
        if dur > 0:
            self._dur_a = dur

    def _on_pos_b(self, pos_ms):
        if pos_ms <= 0 or self._dur_b <= 0:
            return
        pct = min(int((pos_ms / self._dur_b) * 100), 100)
        self.progress_ch_b.setValue(pct)
        self.lbl_time_b.setText(f"{self._ms_to_time(pos_ms)}/{self._ms_to_time(self._dur_b)}")
        self.progress_b.setValue(pct)
        self.lbl_audio_time_b.setText(f"{self._ms_to_time(pos_ms)}/{self._ms_to_time(self._dur_b)}")

    def _on_dur_b(self, dur):
        if dur > 0:
            self._dur_b = dur

    def _on_pos_m(self, pos_ms):
        if pos_ms <= 0 or self._dur_m <= 0:
            return
        pct = min(int((pos_ms / self._dur_m) * 100), 100)
        self.progress_ch_m.setValue(pct)
        self.lbl_time_m.setText(f"{self._ms_to_time(pos_ms)}/{self._ms_to_time(self._dur_m)}")

    def _on_dur_m(self, dur):
        if dur > 0:
            self._dur_m = dur

    # Samples
    def _play_sample(self, idx):
        """Toggle play/stop de un sample - pisa el vivo sin cortarlo"""
        if not self.sample_files[idx]:
            return
        ch = self.audio_mixer.channel_samples
        if ch.current_file == self.sample_files[idx] and ch.is_playing():
            ch.stop()
            colors = ["#e53935", "#ff9800", "#4caf50", "#1565c0", "#9c27b0", "#00bcd4", "#ffeb3b", "#795548"]
            self.sample_buttons[idx].setStyleSheet(
                f"background-color:{colors[idx]};color:white;font-weight:bold;font-size:10px;border-radius:4px;"
            )
        else:
            ch.play(self.sample_files[idx])
            colors = ["#e53935", "#ff9800", "#4caf50", "#1565c0", "#9c27b0", "#00bcd4", "#ffeb3b", "#795548"]
            self.sample_buttons[idx].setStyleSheet(
                f"background-color:{colors[idx]};color:white;font-weight:bold;font-size:10px;border-radius:4px;border:2px solid white;"
            )

    def _load_sample(self, idx):
        """Carga un archivo de audio en un slot de sample"""
        path, _ = QFileDialog.getOpenFileName(
            self, f"Cargar sample {idx+1}", "",
            "Audio (*.mp3 *.wav *.ogg *.flac *.aac *.m4a);;Todos (*)"
        )
        if path:
            self.sample_files[idx] = path
            name = os.path.basename(path)[:8]
            self.sample_buttons[idx].setText(name)
            self.sample_buttons[idx].setToolTip(os.path.basename(path))

    # --- Programación ---
    def _open_schedule_modal(self, edit_task=None, edit_idx=None):
        """Abre modal para crear/editar una programación con playlist"""
        from PySide6.QtWidgets import QDialog, QDateTimeEdit, QTimeEdit
        from datetime import datetime

        dialog = QDialog(self)
        dialog.setWindowTitle("Editar Programación" if edit_task else "Nueva Programación")
        dialog.setMinimumSize(550, 450)
        dialog.setStyleSheet("""
            QDialog { background-color: #2b2b2b; }
            QLabel { color: #ffffff; font-size: 12px; }
            QLineEdit { background-color: #333333; border: 1px solid #4a4a4a; border-radius: 3px; padding: 6px; color: #ffffff; font-size: 12px; }
            QListWidget { background-color: #333333; border: 1px solid #4a4a4a; border-radius: 3px; color: #ffffff; font-size: 11px; }
            QDateTimeEdit { background-color: #333333; border: 1px solid #4a4a4a; border-radius: 3px; padding: 6px; color: #ffffff; font-size: 12px; }
            QPushButton { background-color: #3a3a3a; border: 1px solid #4a4a4a; border-radius: 3px; padding: 6px 12px; color: #ffffff; font-size: 11px; }
            QPushButton:hover { background-color: #4a4a4a; }
        """)
        dl = QVBoxLayout(dialog)

        # Fecha y hora con selector desplegable
        dt_row = QHBoxLayout()
        dt_row.addWidget(QLabel("Fecha y hora:"))
        init_dt = edit_task["datetime"] if edit_task else datetime.now()
        self._sched_datetime = QDateTimeEdit(init_dt)
        self._sched_datetime.setDisplayFormat("dd/MM/yyyy HH:mm")
        self._sched_datetime.setCalendarPopup(True)
        dt_row.addWidget(self._sched_datetime)
        dl.addLayout(dt_row)

        # Playlist
        dl.addWidget(QLabel("Playlist (archivos multimedia):"))
        self._sched_playlist = QListWidget()
        if edit_task:
            for f in edit_task["files"]:
                self._sched_playlist.addItem(f)
        dl.addWidget(self._sched_playlist, 1)

        # Botones de playlist
        pl_btns = QHBoxLayout()
        btn_add_files = QPushButton("📂 Agregar archivos")
        btn_add_files.setStyleSheet("background-color: #4caf50; color: white;")
        btn_add_files.clicked.connect(self._sched_add_files)
        pl_btns.addWidget(btn_add_files)
        btn_remove = QPushButton("✕ Quitar")
        btn_remove.setStyleSheet("background-color: #e53935; color: white;")
        btn_remove.clicked.connect(lambda: self._sched_playlist.takeItem(self._sched_playlist.currentRow()) if self._sched_playlist.currentRow() >= 0 else None)
        pl_btns.addWidget(btn_remove)
        btn_up = QPushButton("▲")
        btn_up.setFixedWidth(30)
        btn_up.clicked.connect(self._sched_move_up)
        pl_btns.addWidget(btn_up)
        btn_down = QPushButton("▼")
        btn_down.setFixedWidth(30)
        btn_down.clicked.connect(self._sched_move_down)
        pl_btns.addWidget(btn_down)
        pl_btns.addStretch()
        dl.addLayout(pl_btns)

        # Zócalo
        ov_row = QHBoxLayout()
        ov_row.addWidget(QLabel("Zócalo:"))
        self._sched_overlay_input = QLineEdit()
        self._sched_overlay_input.setPlaceholderText("Texto del zócalo (opcional)...")
        if edit_task and edit_task.get("overlay"):
            self._sched_overlay_input.setText(edit_task["overlay"])
        ov_row.addWidget(self._sched_overlay_input, 1)
        dl.addLayout(ov_row)

        # Confirmar
        btn_text = "✓ Guardar cambios" if edit_task else "✓ Crear Programación"
        btn_confirm = QPushButton(btn_text)
        btn_confirm.setStyleSheet("background-color: #4caf50; color: white; font-weight: bold; padding: 10px; font-size: 13px;")
        btn_confirm.clicked.connect(lambda: self._confirm_schedule(dialog, edit_idx))
        dl.addWidget(btn_confirm)

        dialog.exec()

    def _sched_add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Agregar archivos a la playlist", "",
            "Media (*.mp4 *.avi *.mkv *.mov *.webm *.mp3 *.wav *.ogg *.png *.jpg);;Todos (*)"
        )
        for p in paths:
            self._sched_playlist.addItem(p)

    def _sched_move_up(self):
        row = self._sched_playlist.currentRow()
        if row > 0:
            item = self._sched_playlist.takeItem(row)
            self._sched_playlist.insertItem(row - 1, item)
            self._sched_playlist.setCurrentRow(row - 1)

    def _sched_move_down(self):
        row = self._sched_playlist.currentRow()
        if row < self._sched_playlist.count() - 1:
            item = self._sched_playlist.takeItem(row)
            self._sched_playlist.insertItem(row + 1, item)
            self._sched_playlist.setCurrentRow(row + 1)

    def _confirm_schedule(self, dialog, edit_idx=None):
        """Confirma y agrega/edita la programación"""
        dt = self._sched_datetime.dateTime().toPython()
        overlay = self._sched_overlay_input.text()
        files = []
        for i in range(self._sched_playlist.count()):
            files.append(self._sched_playlist.item(i).text())

        if not files:
            return

        task = {
            "datetime": dt,
            "files": files,
            "overlay": overlay,
            "executed": False
        }

        if edit_idx is not None:
            self._scheduled_tasks[edit_idx] = task
        else:
            self._scheduled_tasks.append(task)

        self._refresh_schedule_tree()
        dialog.accept()

    def _refresh_schedule_tree(self):
        """Refresca el árbol de programaciones"""
        self.schedule_tree.clear()
        for task in self._scheduled_tasks:
            dt = task["datetime"]
            files = task["files"]
            overlay = task.get("overlay", "")
            item = QTreeWidgetItem([
                dt.strftime("%d/%m/%Y %H:%M"),
                f"{len(files)} archivos: " + ", ".join([os.path.basename(f) for f in files[:3]]) + ("..." if len(files) > 3 else ""),
                overlay if overlay else "-"
            ])
            self.schedule_tree.addTopLevelItem(item)

    def _edit_schedule(self):
        """Edita la programación seleccionada"""
        idx = self.schedule_tree.currentIndex().row()
        if idx < 0 or idx >= len(self._scheduled_tasks):
            return
        task = self._scheduled_tasks[idx]
        self._open_schedule_modal(edit_task=task, edit_idx=idx)

    def _save_schedule_list(self):
        """Guarda la lista de programaciones a un archivo .gbs"""
        import json
        path, _ = QFileDialog.getSaveFileName(self, "Guardar lista de programación", "", "GBSturio Playlist (*.gbs)")
        if path:
            if not path.endswith('.gbs'):
                path += '.gbs'
            data = []
            for task in self._scheduled_tasks:
                data.append({
                    "datetime": task["datetime"].isoformat(),
                    "files": task["files"],
                    "overlay": task.get("overlay", "")
                })
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

    def _load_schedule_list(self):
        """Carga una lista de programaciones desde .gbs"""
        import json
        from datetime import datetime
        path, _ = QFileDialog.getOpenFileName(self, "Cargar lista de programación", "", "GBSturio Playlist (*.gbs);;JSON (*.json);;Todos (*)")
        if path:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._scheduled_tasks = []
            for item in data:
                self._scheduled_tasks.append({
                    "datetime": datetime.fromisoformat(item["datetime"]),
                    "files": item["files"],
                    "overlay": item.get("overlay", ""),
                    "executed": False
                })
            self._refresh_schedule_tree()

    def _sched_browse_file(self):
        pass

    def _sched_browse_audio(self):
        pass

    def _add_schedule(self):
        self._open_schedule_modal()

    def _del_schedule(self):
        idx = self.schedule_tree.currentIndex().row()
        if idx >= 0 and idx < len(self._scheduled_tasks):
            self._scheduled_tasks.pop(idx)
            self._refresh_schedule_tree()

    def _check_schedule(self):
        """Verifica si alguna tarea programada debe ejecutarse ahora"""
        from datetime import datetime
        now = datetime.now()

        for task in self._scheduled_tasks:
            if task["executed"]:
                continue
            dt = task["datetime"]
            if dt.year == now.year and dt.month == now.month and dt.day == now.day and dt.hour == now.hour and dt.minute == now.minute:
                self._execute_scheduled_task(task)
                task["executed"] = True

    def _launch_schedule_now(self):
        """Lanza la programación seleccionada inmediatamente"""
        idx = self.schedule_tree.currentIndex().row()
        if idx >= 0 and idx < len(self._scheduled_tasks):
            self._execute_scheduled_task(self._scheduled_tasks[idx])

    def _execute_scheduled_task(self, task):
        """Ejecuta una tarea programada: reproduce la playlist al vivo"""
        import random
        files = task.get("files", [])
        overlay_text = task.get("overlay", "")

        if not files:
            return

        # Modo random o ordenado
        mode = self.cmb_sched_mode.currentText()
        if mode == "Random":
            random.shuffle(files)

        # Guardar playlist para reproducción secuencial
        self._sched_playlist_files = files
        self._sched_current_idx = 0
        self._sched_overlay_text = overlay_text

        # Reproducir el primer archivo
        self._play_next_scheduled()

    def _play_next_scheduled(self):
        """Reproduce el siguiente archivo de la playlist programada"""
        if not hasattr(self, '_sched_playlist_files') or self._sched_current_idx >= len(self._sched_playlist_files):
            return  # Playlist terminada

        file_path = self._sched_playlist_files[self._sched_current_idx]
        self._sched_current_idx += 1
        ext = file_path.lower()

        # Desconectar fuentes anteriores
        self._disconnect_all_from_live()
        # Desconectar señal de fin anterior
        try:
            self.audio_mixer.channel_master.player.mediaStatusChanged.disconnect(self._on_sched_media_status)
        except (RuntimeError, TypeError):
            pass

        if ext.endswith(('.mp4', '.avi', '.mkv', '.mov', '.webm')):
            if self.camera_thread:
                self.camera_thread.stop()
                self.camera_thread.deleteLater()
            self.camera_thread = CameraThread(file_path)
            self.camera_thread.frame_ready.connect(self._update_live)
            self.camera_thread.error.connect(self._camera_error)
            self.camera_thread.start()
            self.audio_mixer.channel_master.play(file_path)
            # Conectar señal para detectar fin del video/audio
            self.audio_mixer.channel_master.player.mediaStatusChanged.connect(self._on_sched_media_status)
        elif ext.endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif')):
            pixmap = QPixmap(file_path)
            self.base_frame_live = pixmap.copy()
            self.live_label.setPixmap(pixmap.scaled(
                self.live_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            # Para imágenes, mostrar 5 segundos y pasar al siguiente
            QTimer.singleShot(5000, self._play_next_scheduled)
        elif ext.endswith(('.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a')):
            self.audio_mixer.channel_master.play(file_path)
            self.audio_mixer.channel_master.player.mediaStatusChanged.connect(self._on_sched_media_status)

        # Aplicar zócalo si hay
        if hasattr(self, '_sched_overlay_text') and self._sched_overlay_text:
            overlay_data = self._build_overlay_data(self._sched_overlay_text)
            self.overlays_live = [overlay_data]

    def _on_sched_media_status(self, status):
        """Detecta cuando un medio termina y pasa al siguiente de la playlist"""
        from PySide6.QtMultimedia import QMediaPlayer
        if status == QMediaPlayer.EndOfMedia:
            try:
                self.audio_mixer.channel_master.player.mediaStatusChanged.disconnect(self._on_sched_media_status)
            except (RuntimeError, TypeError):
                pass
            QTimer.singleShot(500, self._play_next_scheduled)

    # --- Versículos Bíblicos ---
    def _search_bible(self):
        """Busca un versiculo biblico en espanol"""
        import requests
        ref = self.txt_bible_ref.text().strip()
        if not ref:
            return
        self.txt_bible_result.setText('Buscando...')
        try:
            book_codes = {
                'genesis':'gn','exodo':'ex','levitico':'lv','numeros':'nm','deuteronomio':'dt',
                'josue':'jos','jueces':'jue','rut':'rt','1 samuel':'1s','2 samuel':'2s',
                '1 reyes':'1r','2 reyes':'2r','1 cronicas':'1cr','2 cronicas':'2cr',
                'esdras':'esd','nehemias':'neh','ester':'est','job':'job',
                'salmos':'sal','salmo':'sal','proverbios':'pr','eclesiastes':'ec',
                'cantares':'cnt','isaias':'is','jeremias':'jer','lamentaciones':'lm',
                'ezequiel':'ez','daniel':'dn','oseas':'os','joel':'jl','amos':'am',
                'abdias':'abd','jonas':'jon','miqueas':'mi','nahum':'nah','habacuc':'hab',
                'sofonias':'sof','hageo':'hag','zacarias':'zac','malaquias':'mal',
                'mateo':'mt','marcos':'mr','lucas':'lc','juan':'jn','hechos':'hch',
                'romanos':'ro','1 corintios':'1co','2 corintios':'2co','galatas':'ga',
                'efesios':'ef','filipenses':'fil','colosenses':'col',
                '1 tesalonicenses':'1ts','2 tesalonicenses':'2ts',
                '1 timoteo':'1ti','2 timoteo':'2ti','tito':'tit','filemon':'flm',
                'hebreos':'he','santiago':'stg','1 pedro':'1p','2 pedro':'2p',
                '1 juan':'1jn','2 juan':'2jn','3 juan':'3jn','judas':'jud','apocalipsis':'ap',
            }
            ref_lower = ref.lower().strip()
            parts = ref_lower.replace(':', ' ').split()
            book_name = ''
            chapter = ''
            verse = ''
            if len(parts) >= 4 and parts[0] in ['1','2','3']:
                book_name = f'{parts[0]} {parts[1]}'
                chapter = parts[2]
                verse = parts[3]
            elif len(parts) >= 3 and parts[0] in ['1','2','3']:
                book_name = f'{parts[0]} {parts[1]}'
                chapter = parts[2]
            elif len(parts) >= 3:
                book_name = parts[0]
                chapter = parts[1]
                verse = parts[2]
            elif len(parts) >= 2:
                book_name = parts[0]
                chapter = parts[1]
            else:
                self.txt_bible_result.setText(f'Agrega capitulo. Ej: {ref} 3:16')
                return
            book_code = book_codes.get(book_name, '')
            if not book_code:
                self.txt_bible_result.setText(f'Libro no encontrado: {book_name}\nEj: Juan 3:16')
                return
            version_map = {'reina-valera-1960':'rv1960','nvi':'nvi','ntv':'pdt','lbla':'rv1995','dhh':'dhh'}
            version = version_map.get(self.cmb_bible_version.currentText(), 'rv1960')
            if not verse:
                verse = '1'
            url = f'https://bible-api.deno.dev/api/read/{version}/{book_code}/{chapter}/{verse}'
            response = requests.get(url, timeout=8)
            if response.status_code == 200:
                data = response.json()
                text = data.get('verse', '')
                if text:
                    self.txt_bible_result.setText(f'{book_name.title()} {chapter}:{verse}\n\n{text}')
                else:
                    self.txt_bible_result.setText('Versiculo no encontrado.')
            else:
                self.txt_bible_result.setText(f'No encontrado: {book_name.title()} {chapter}:{verse}')
        except Exception as e:
            self.txt_bible_result.setText(f'Error: {str(e)}')

    def _search_bible_smart(self):
        """Búsqueda inteligente por palabras clave usando bible-api.com"""
        import requests
        query = self.txt_bible_smart.text().strip()
        if not query:
            return
        self.txt_bible_result.setText("Buscando por tema...")
        try:
            # Usar bible-api.com que acepta búsqueda por texto
            # Buscar en inglés y mostrar resultado
            url = f"https://bible-api.com/{query}"
            response = requests.get(url, timeout=8)
            if response.status_code == 200:
                data = response.json()
                text = data.get("text", "")
                reference = data.get("reference", "")
                if text:
                    self.txt_bible_result.setText(f"📖 {reference}\n\n{text.strip()}")
                else:
                    # Intentar como búsqueda temática con versículos conocidos
                    self._search_bible_by_keywords(query)
            else:
                self._search_bible_by_keywords(query)
        except Exception as e:
            self._search_bible_by_keywords(query)

    def _search_bible_by_keywords(self, query):
        """Busca versículos por palabras clave en una base local de temas"""
        # Base de versículos por tema (español)
        temas = {
            "amor": ["jn/3/16", "ro/8/38", "1co/13/4", "1jn/4/8"],
            "fe": ["he/11/1", "ro/10/17", "stg/2/17", "mr/11/24"],
            "esperanza": ["ro/15/13", "jer/29/11", "sal/27/14", "ro/8/28"],
            "paz": ["fil/4/7", "jn/14/27", "is/26/3", "sal/29/11"],
            "fuerza": ["fil/4/13", "is/40/31", "dt/31/6", "sal/27/1"],
            "sanidad": ["is/53/5", "jer/17/14", "sal/103/3", "stg/5/15"],
            "perdon": ["ef/4/32", "1jn/1/9", "col/3/13", "mt/6/14"],
            "salvacion": ["ro/10/9", "ef/2/8", "hch/4/12", "jn/14/6"],
            "oracion": ["fil/4/6", "1ts/5/17", "mt/7/7", "stg/5/16"],
            "proteccion": ["sal/91/1", "sal/23/4", "is/41/10", "sal/121/7"],
            "provision": ["fil/4/19", "mt/6/33", "sal/23/1", "dt/28/12"],
            "sabiduria": ["stg/1/5", "pr/3/5", "pr/2/6", "col/2/3"],
            "gozo": ["sal/16/11", "neh/8/10", "ro/15/13", "gal/5/22"],
            "jesus": ["jn/14/6", "jn/3/16", "hch/4/12", "fil/2/10"],
            "leproso": ["mt/8/2", "mr/1/40", "lc/5/12", "lc/17/12"],
            "milagro": ["jn/2/11", "mr/5/34", "hch/3/6", "mt/14/19"],
            "juan": ["jn/1/1", "jn/1/14", "jn/3/16", "jn/14/6"],
            "genesis": ["gn/1/1", "gn/1/27", "gn/12/1", "gn/28/15"],
            "salmo": ["sal/23/1", "sal/91/1", "sal/121/1", "sal/139/14"],
            "mateo": ["mt/5/14", "mt/6/33", "mt/11/28", "mt/28/19"],
            "lucas": ["lc/1/37", "lc/6/38", "lc/10/27", "lc/12/32"],
            "marcos": ["mr/10/27", "mr/11/24", "mr/16/15", "mr/9/23"],
            "romanos": ["ro/8/28", "ro/8/38", "ro/10/9", "ro/12/2"],
            "muerte": ["jn/11/25", "ro/6/23", "1co/15/55", "ap/21/4"],
            "vida": ["jn/10/10", "jn/14/6", "gal/2/20", "fil/1/21"],
            "gracia": ["ef/2/8", "2co/12/9", "ro/3/24", "tit/2/11"],
            "bendicion": ["nm/6/24", "dt/28/6", "sal/1/1", "ef/1/3"],
        }
        import requests
        query_lower = query.lower()
        refs_to_search = []
        for tema, refs in temas.items():
            if tema in query_lower:
                refs_to_search = refs
                break
        if not refs_to_search:
            # Buscar en todas las palabras
            for tema, refs in temas.items():
                for word in query_lower.split():
                    if word in tema or tema in word:
                        refs_to_search = refs
                        break
                if refs_to_search:
                    break
        if not refs_to_search:
            self.txt_bible_result.setText(f"Sin resultados para: '{query}'\nProbá: amor, fe, paz, sanidad, perdón, oración, jesús, milagro")
            return
        # Buscar los versículos
        version_map = {"reina-valera-1960": "rv1960", "nvi": "nvi", "ntv": "pdt", "lbla": "rv1995", "dhh": "dhh"}
        version = version_map.get(self.cmb_bible_version.currentText(), "rv1960")
        results = []
        for ref in refs_to_search[:4]:
            try:
                url = f"https://bible-api.deno.dev/api/read/{version}/{ref}"
                r = requests.get(url, timeout=5)
                if r.status_code == 200:
                    data = r.json()
                    text = data.get("verse", "")
                    if text:
                        results.append(f"📖 {ref.upper()}\n{text}\n")
            except:
                pass
        if results:
            self.txt_bible_result.setText("\n".join(results))
        else:
            self.txt_bible_result.setText(f"Error al buscar. Verificá tu conexión.")

    def _bible_to_preview(self):
        """Envía el versículo seleccionado (o todo) como zócalo a la pre-escucha"""
        # Si hay texto seleccionado, usar solo ese
        cursor = self.txt_bible_result.textCursor()
        text = cursor.selectedText().strip() if cursor.hasSelection() else self.txt_bible_result.toPlainText().strip()
        if text:
            old_size = self.spn_font_size.value()
            old_color = QColor(self.overlay_text_color)
            self.spn_font_size.setValue(self.spn_bible_size.value())
            self.overlay_text_color = self._bible_text_color
            self.txt_overlay.setPlainText(text)
            self._text_to_preview()
            self.spn_font_size.setValue(old_size)
            self.overlay_text_color = old_color

    def _bible_to_live(self):
        """Envía el versículo seleccionado (o todo) como zócalo directo al vivo"""
        cursor = self.txt_bible_result.textCursor()
        text = cursor.selectedText().strip() if cursor.hasSelection() else self.txt_bible_result.toPlainText().strip()
        if text:
            old_size = self.spn_font_size.value()
            old_color = QColor(self.overlay_text_color)
            self.spn_font_size.setValue(self.spn_bible_size.value())
            self.overlay_text_color = self._bible_text_color
            self.txt_overlay.setPlainText(text)
            self._text_to_live()
            self.spn_font_size.setValue(old_size)
            self.overlay_text_color = old_color

    def _pick_bible_color(self):
        color = QColorDialog.getColor(self._bible_text_color, self, "Color del texto bíblico")
        if color.isValid():
            self._bible_text_color = color
            self.btn_bible_color.setStyleSheet(
                f"background-color: {color.name()}; border: 1px solid #666; border-radius: 3px;"
            )

    # --- Playlist ---
    def _playlist_add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Agregar a playlist", "",
            "Media (*.mp4 *.avi *.mkv *.mov *.webm *.mp3 *.wav *.ogg *.png *.jpg);;Todos (*)"
        )
        for p in paths:
            self.playlist_widget.addItem(p)

    def _playlist_remove(self):
        row = self.playlist_widget.currentRow()
        if row >= 0:
            self.playlist_widget.takeItem(row)

    def _playlist_play(self):
        """Reproduce la playlist al vivo"""
        import random
        files = []
        for i in range(self.playlist_widget.count()):
            files.append(self.playlist_widget.item(i).text())
        if not files:
            return
        mode = self.cmb_sched_mode.currentText()
        if mode == "Random":
            random.shuffle(files)
        self._sched_playlist_files = files
        self._sched_current_idx = 0
        self._sched_overlay_text = ""
        self._play_next_scheduled()

    # --- Alertas ---
    def _send_alert_to_preview(self):
        self._start_alert("preview")

    def _send_alert_to_live(self):
        self._start_alert("live")

    def _start_alert(self, target):
        text = self.txt_alert.text().strip()
        if not text:
            return
        self._alert_target = target
        self._alert_text = text
        self._alert_position = self.cmb_alert_pos.currentText()
        self._alert_blink_count = 0
        self._alert_blink_max = self.spn_alert_blinks.value()
        self._alert_visible = True
        self._alert_phase = "on"  # "on" = visible, "off" = oculto brevemente
        # Obtener duración del ComboBox
        dur_text = self.cmb_alert_dur.currentText().replace(" seg", "")
        self._alert_duration_ms = int(dur_text) * 1000
        # Timer: la alerta se muestra y cada cierto tiempo hace un "flash off" breve
        self._alert_timer.start(800)  # Cada 800ms revisa
        self._alert_start_time = None
        # Pintar primera vez
        self._paint_alert()

    def _alert_blink_tick(self):
        import time
        if not hasattr(self, '_alert_elapsed'):
            self._alert_elapsed = 0
        self._alert_elapsed += 800

        # Si pasó la duración total, terminar
        if self._alert_elapsed >= self._alert_duration_ms:
            self._alert_timer.stop()
            self._alert_visible = False
            self._alert_elapsed = 0
            # Limpiar
            if self._alert_target == "preview":
                preview = self._get_active_preview()
                base = self._get_base_frame_for(preview)
                preview.setPixmap(base.scaled(preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            elif self._alert_target == "live":
                base = self._get_base_frame_for(self.live_label)
                self.live_label.setPixmap(base.scaled(self.live_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
                if self.live_window:
                    self.live_window.update_frame(base)
            return

        # Parpadeo sutil: visible la mayor parte, se apaga brevemente cada N ciclos
        self._alert_blink_count += 1
        if self._alert_blink_max > 0 and self._alert_blink_count % 4 == 0:
            # Flash off por un ciclo (200ms efecto)
            self._alert_visible = False
            self._paint_alert()
            QTimer.singleShot(150, self._alert_flash_back)
        else:
            self._alert_visible = True
            self._paint_alert()

    def _alert_flash_back(self):
        """Vuelve a mostrar la alerta después del flash"""
        self._alert_visible = True
        self._paint_alert()

    def _paint_alert(self):
        """Pinta o quita la alerta parpadeante"""
        if self._alert_target == "preview":
            preview = self._get_active_preview()
            base = self._get_base_frame_for(preview)
            if self._alert_visible:
                base = self._draw_alert_on_pixmap(base, self._alert_text, self._alert_position)
            preview.setPixmap(base.scaled(preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        elif self._alert_target == "live":
            base = self._get_base_frame_for(self.live_label)
            if self._alert_visible:
                base = self._draw_alert_on_pixmap(base, self._alert_text, self._alert_position)
            self.live_label.setPixmap(base.scaled(self.live_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            if self.live_window:
                self.live_window.update_frame(base)

    def _draw_alert_on_pixmap(self, pixmap, text, position):
        """Dibuja una alerta roja parpadeante sobre el pixmap"""
        pixmap = pixmap.copy()
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # Fondo rojo semi-transparente - altura adaptable al texto
        scale = pixmap.width() / 640
        font_size = max(12, int(16 * scale))
        font = QFont("Arial", font_size, QFont.Bold)
        painter.setFont(font)

        # Calcular altura necesaria para el texto con word wrap
        fm = painter.fontMetrics()
        text_rect = fm.boundingRect(QRect(10, 0, pixmap.width() - 20, pixmap.height()),
                                    Qt.AlignCenter | Qt.TextWordWrap, text)
        h = text_rect.height() + int(20 * scale)

        if position == "Arriba":
            y = 0
        elif position == "Medio":
            y = (pixmap.height() - h) // 2
        else:
            y = pixmap.height() - h

        bg_rect = QRect(0, y, pixmap.width(), h)
        painter.fillRect(bg_rect, QColor(220, 20, 20, 180))

        # Texto blanco negrita centrado con word wrap
        painter.setPen(QPen(QColor(255, 255, 255)))
        painter.drawText(bg_rect, Qt.AlignCenter | Qt.TextWordWrap, text)

        painter.end()
        return pixmap

    def _auto_load_samples(self):
        """Auto-carga samples desde la carpeta src/ui/samples/"""
        samples_dir = os.path.join(os.path.dirname(__file__), "samples")
        if not os.path.exists(samples_dir):
            return
        audio_exts = ('.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a')
        files = sorted([f for f in os.listdir(samples_dir) if f.lower().endswith(audio_exts)])
        for i, fname in enumerate(files[:8]):
            path = os.path.join(samples_dir, fname)
            self.sample_files[i] = path
            name = os.path.splitext(fname)[0][:8]
            self.sample_buttons[i].setText(name)
            self.sample_buttons[i].setToolTip(fname)

    def _drop_on_preview(self, event, target):
        """Maneja el drop de archivos en los previews"""
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path:
                self._send_file_to_target(path, target)

    # --- Tabs de medios (Imágenes, Audio, Videos) ---
    def _choose_images_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Carpeta de imágenes")
        if folder:
            self.list_images.clear()
            self._images_folder = folder
            medios_icons = os.path.join(os.path.dirname(__file__), "icons", "medios")
            icon = QIcon(os.path.join(medios_icons, "item_imagen.png"))
            for f in sorted(os.listdir(folder)):
                if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif')):
                    item = QListWidgetItem(icon, f)
                    item.setData(Qt.UserRole, os.path.join(folder, f))
                    item.setToolTip(os.path.join(folder, f))
                    self.list_images.addItem(item)

    def _choose_audio_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Carpeta de audio")
        if folder:
            self.list_audios.clear()
            self._audio_folder = folder
            medios_icons = os.path.join(os.path.dirname(__file__), "icons", "medios")
            icon = QIcon(os.path.join(medios_icons, "item_audio.png"))
            for f in sorted(os.listdir(folder)):
                if f.lower().endswith(('.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a')):
                    item = QListWidgetItem(icon, f)
                    item.setData(Qt.UserRole, os.path.join(folder, f))
                    item.setToolTip(os.path.join(folder, f))
                    self.list_audios.addItem(item)

    def _choose_video_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Carpeta de videos")
        if folder:
            self.list_videos.clear()
            self._video_folder = folder
            medios_icons = os.path.join(os.path.dirname(__file__), "icons", "medios")
            icon = QIcon(os.path.join(medios_icons, "item_video.png"))
            for f in sorted(os.listdir(folder)):
                if f.lower().endswith(('.mp4', '.avi', '.mkv', '.mov', '.webm')):
                    item = QListWidgetItem(icon, f)
                    item.setData(Qt.UserRole, os.path.join(folder, f))
                    item.setToolTip(os.path.join(folder, f))
                    self.list_videos.addItem(item)

    def _image_double_click(self, index):
        item = self.list_images.currentItem()
        if item:
            path = item.data(Qt.UserRole)
            self._send_file_to_target(path, self.active_preview)

    def _audio_double_click(self, index):
        item = self.list_audios.currentItem()
        if item:
            path = item.data(Qt.UserRole)
            self.audio_mixer.get_channel(self.active_preview).play(path)

    def _video_double_click(self, index):
        item = self.list_videos.currentItem()
        if item:
            path = item.data(Qt.UserRole)
            self._send_file_to_target(path, self.active_preview)

    def _send_selected_media(self, list_widget, dest):
        """Envía el archivo seleccionado al pre o al vivo"""
        item = list_widget.currentItem()
        if not item:
            return
        path = item.data(Qt.UserRole)
        if not path:
            path = item.text()
        if dest == "preview":
            self._send_file_to_target(path, self.active_preview)
        elif dest == "live":
            self._send_file_to_target(path, "LIVE")

    def _ms_to_time(self, ms):
        seconds = ms // 1000
        m = seconds // 60
        s = seconds % 60
        return f"{m:02d}:{s:02d}"

    # --- Transiciones ---
    def _on_transition_changed(self, text):
        descriptions = {
            "Corte (instantáneo)": "Cambio instantáneo sin animación",
            "Fundido (fade)": "Fundido gradual entre la imagen actual y la nueva",
            "Deslizar izquierda": "La nueva imagen entra deslizando desde la derecha",
            "Deslizar derecha": "La nueva imagen entra deslizando desde la izquierda",
            "Deslizar arriba": "La nueva imagen entra deslizando desde abajo",
            "Deslizar abajo": "La nueva imagen entra deslizando desde arriba",
            "Zoom in": "La nueva imagen aparece con zoom desde el centro",
            "Zoom out": "La imagen actual se aleja y revela la nueva",
            "Disolver": "Disolución gradual pixel a pixel",
        }
        self.lbl_transition_info.setText(descriptions.get(text, ""))

    def _apply_transition_to_live(self, new_pixmap):
        """Aplica la transición seleccionada al cambiar el contenido del vivo"""
        transition = self.cmb_transition.currentText()
        duration = self.spn_transition_dur.value()

        if transition == "Corte (instantáneo)" or duration == 0:
            self._transition_active = False
            self.live_label.setPixmap(new_pixmap.scaled(
                self.live_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            ))
            self.base_frame_live = new_pixmap.copy()
            if self.live_window:
                self.live_window.update_frame(new_pixmap)
            return

        # Para transiciones animadas, usar pasos
        old_pixmap = self.live_label.pixmap()
        if not old_pixmap or old_pixmap.isNull():
            self._transition_active = False
            self.live_label.setPixmap(new_pixmap.scaled(
                self.live_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            ))
            self.base_frame_live = new_pixmap.copy()
            if self.live_window:
                self.live_window.update_frame(new_pixmap)
            return

        # Bloquear actualizaciones del live durante la transición
        self._transition_active = True

        # Escalar ambos al tamaño del label
        size = self.live_label.size()
        old_scaled = old_pixmap.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        new_scaled = new_pixmap.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        steps = max(duration // 33, 5)  # ~30fps
        step_delay = duration // steps

        self._transition_old = old_scaled
        self._transition_new = new_scaled
        self._transition_step = 0
        self._transition_steps = steps
        self._transition_type = transition
        self._transition_timer = QTimer(self)
        self._transition_timer.timeout.connect(self._transition_tick)
        self._transition_timer.start(step_delay)
        self.base_frame_live = new_pixmap.copy()

    def _transition_tick(self):
        self._transition_step += 1
        progress = self._transition_step / self._transition_steps

        if progress >= 1.0:
            self._transition_timer.stop()
            self._transition_active = False
            self.live_label.setPixmap(self._transition_new)
            if self.live_window:
                self.live_window.update_frame(self._transition_new)
            return

        old = self._transition_old
        new = self._transition_new
        size = self.live_label.size()
        result = QPixmap(size)
        result.fill(QColor(0, 0, 0))
        painter = QPainter(result)

        t = self._transition_type
        if t == "Fundido (fade)":
            painter.setOpacity(1.0 - progress)
            painter.drawPixmap(0, 0, old)
            painter.setOpacity(progress)
            painter.drawPixmap(0, 0, new)
        elif t == "Deslizar izquierda":
            offset = int(size.width() * progress)
            painter.drawPixmap(-offset, 0, old)
            painter.drawPixmap(size.width() - offset, 0, new)
        elif t == "Deslizar derecha":
            offset = int(size.width() * progress)
            painter.drawPixmap(offset, 0, old)
            painter.drawPixmap(-size.width() + offset, 0, new)
        elif t == "Deslizar arriba":
            offset = int(size.height() * progress)
            painter.drawPixmap(0, -offset, old)
            painter.drawPixmap(0, size.height() - offset, new)
        elif t == "Deslizar abajo":
            offset = int(size.height() * progress)
            painter.drawPixmap(0, offset, old)
            painter.drawPixmap(0, -size.height() + offset, new)
        elif t == "Zoom in":
            scale = progress
            w = int(new.width() * scale)
            h = int(new.height() * scale)
            painter.drawPixmap(0, 0, old)
            if w > 0 and h > 0:
                scaled_new = new.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                x = (size.width() - scaled_new.width()) // 2
                y = (size.height() - scaled_new.height()) // 2
                painter.setOpacity(progress)
                painter.drawPixmap(x, y, scaled_new)
        elif t == "Zoom out":
            scale = 1.0 - progress * 0.5
            w = int(old.width() * scale)
            h = int(old.height() * scale)
            painter.drawPixmap(0, 0, new)
            if w > 0 and h > 0:
                scaled_old = old.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                x = (size.width() - scaled_old.width()) // 2
                y = (size.height() - scaled_old.height()) // 2
                painter.setOpacity(1.0 - progress)
                painter.drawPixmap(x, y, scaled_old)
        elif t == "Disolver":
            painter.setOpacity(1.0 - progress)
            painter.drawPixmap(0, 0, old)
            painter.setOpacity(progress)
            painter.drawPixmap(0, 0, new)
        elif t == "Borrado pizarrón":
            # La nueva imagen se revela de izquierda a derecha como borrando
            cut_x = int(size.width() * progress)
            painter.drawPixmap(0, 0, old)
            painter.setClipRect(0, 0, cut_x, size.height())
            painter.drawPixmap(0, 0, new)
            painter.setClipping(False)
        elif t == "Burbujas":
            # Círculos que revelan la nueva imagen
            import random
            painter.drawPixmap(0, 0, old)
            path = QPainterPath()
            num_circles = int(progress * 30) + 1
            random.seed(42)  # Seed fijo para consistencia
            for _ in range(num_circles):
                cx = random.randint(0, size.width())
                cy = random.randint(0, size.height())
                r = int(size.width() * progress * 0.3)
                path.addEllipse(cx - r, cy - r, r * 2, r * 2)
            painter.setClipPath(path)
            painter.drawPixmap(0, 0, new)
            painter.setClipping(False)
        elif t == "Quemar imagen":
            # La imagen vieja se oscurece y la nueva aparece
            painter.drawPixmap(0, 0, new)
            painter.setOpacity(1.0 - progress)
            painter.drawPixmap(0, 0, old)
            # Efecto de "quemado" - overlay naranja
            painter.setOpacity(progress * 0.5 if progress < 0.5 else (1.0 - progress) * 0.5)
            painter.fillRect(0, 0, size.width(), size.height(), QColor(255, 100, 0, 100))
        elif t == "Pixelar":
            # La imagen se pixela y se transforma en la nueva
            import cv2
            import numpy as np
            painter.end()
            # Convertir pixmaps a arrays
            old_img = old.toImage().convertToFormat(QImage.Format_RGB888)
            new_img = new.toImage().convertToFormat(QImage.Format_RGB888)
            w, h = old_img.width(), old_img.height()
            if w > 0 and h > 0:
                old_arr = np.array(old_img.bits()).reshape(h, w, 3).copy()
                new_arr = np.array(new_img.bits()).reshape(h, w, 3).copy()
                # Pixelar: reducir resolución
                pixel_size = max(1, int((1.0 - abs(progress - 0.5) * 2) * 20) + 1)
                if progress < 0.5:
                    arr = old_arr
                else:
                    arr = new_arr
                small = cv2.resize(arr, (w // pixel_size, h // pixel_size), interpolation=cv2.INTER_NEAREST)
                arr = cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)
                result = QPixmap.fromImage(QImage(arr.data, w, h, w * 3, QImage.Format_RGB888).copy())
            else:
                result = new
            self.live_label.setPixmap(result)
            if self.live_window:
                self.live_window.update_frame(result)
            return
        elif t == "Cortina horizontal":
            # Barras horizontales que revelan la nueva imagen
            painter.drawPixmap(0, 0, old)
            num_bars = 8
            bar_h = size.height() // num_bars
            for i in range(num_bars):
                bar_progress = min(1.0, progress * 1.5 - (i * 0.05))
                if bar_progress > 0:
                    cut_w = int(size.width() * bar_progress)
                    painter.setClipRect(0, i * bar_h, cut_w, bar_h)
                    painter.drawPixmap(0, 0, new)
            painter.setClipping(False)
        elif t == "Cortina vertical":
            # Barras verticales que revelan la nueva imagen
            painter.drawPixmap(0, 0, old)
            num_bars = 10
            bar_w = size.width() // num_bars
            for i in range(num_bars):
                bar_progress = min(1.0, progress * 1.5 - (i * 0.05))
                if bar_progress > 0:
                    cut_h = int(size.height() * bar_progress)
                    painter.setClipRect(i * bar_w, 0, bar_w, cut_h)
                    painter.drawPixmap(0, 0, new)
            painter.setClipping(False)
        else:
            painter.drawPixmap(0, 0, new)

        painter.end()
        self.live_label.setPixmap(result)
        if self.live_window:
            self.live_window.update_frame(result)

    def _paint_overlay_on_pixmap(self, pixmap, overlay_data):
        """Pinta el texto overlay sobre un pixmap y devuelve el resultado"""
        pixmap = pixmap.copy()
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # Escalar tamaño de fuente proporcionalmente al pixmap
        # Base: 22px para un pixmap de 640px de ancho
        base_width = 640
        raw_size = overlay_data["size"]
        scale_factor = pixmap.width() / base_width
        scaled_size = max(8, int(raw_size * scale_factor))

        font = QFont(overlay_data["font"], scaled_size, QFont.Bold)
        painter.setFont(font)

        text = overlay_data["text"]
        position = overlay_data["position"]
        height_offset = int(overlay_data["height_offset"] * scale_factor)
        text_color = overlay_data.get("text_color", QColor(255, 255, 255))
        bg_color = overlay_data.get("bg_color", QColor(0, 0, 0, 160))

        fm = painter.fontMetrics()
        text_rect = fm.boundingRect(QRect(0, 0, pixmap.width() - 20, pixmap.height()),
                                    Qt.AlignHCenter | Qt.TextWordWrap, text)

        x = (pixmap.width() - text_rect.width()) // 2
        if position == "Arriba":
            y = height_offset
        elif position == "Medio":
            y = (pixmap.height() - text_rect.height()) // 2
        else:  # Abajo
            y = pixmap.height() - text_rect.height() - height_offset

        bg_rect = QRect(x - 10, y - 5, text_rect.width() + 20, text_rect.height() + 10)
        painter.fillRect(bg_rect, bg_color)

        painter.setPen(QPen(text_color))
        draw_rect = QRect(x, y, text_rect.width(), text_rect.height())
        painter.drawText(draw_rect, Qt.AlignHCenter | Qt.TextWordWrap, text)

        painter.end()
        return pixmap

    def _draw_overlays_on_label(self, label, overlays):
        """Dibuja todos los overlays sobre el frame base limpio del label"""
        # Obtener frame base limpio
        pixmap = self._get_base_frame_for(label)

        for ov in overlays:
            pixmap = self._paint_overlay_on_pixmap(pixmap, ov)

        label.setPixmap(pixmap.scaled(
            label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        ))

    def _get_base_frame_for(self, label):
        """Obtiene el frame base limpio para un label. Si no existe, lo crea."""
        if label == self.preview_a:
            if self.base_frame_a:
                return self.base_frame_a.copy()
            else:
                # Crear frame base desde el pixmap actual (sin overlay) o negro
                pixmap = QPixmap(label.size())
                pixmap.fill(QColor(26, 26, 46))
                self.base_frame_a = pixmap.copy()
                return pixmap
        elif label == self.preview_b:
            if self.base_frame_b:
                return self.base_frame_b.copy()
            else:
                pixmap = QPixmap(label.size())
                pixmap.fill(QColor(26, 26, 46))
                self.base_frame_b = pixmap.copy()
                return pixmap
        elif label == self.live_label:
            if self.base_frame_live:
                return self.base_frame_live.copy()
            else:
                pixmap = QPixmap(label.size())
                pixmap.fill(QColor(26, 26, 46))
                self.base_frame_live = pixmap.copy()
                return pixmap
        else:
            pixmap = QPixmap(label.size())
            pixmap.fill(QColor(26, 26, 46))
            return pixmap

    def _save_overlay(self):
        """Guarda el overlay actual en la lista interna"""
        text = self.txt_overlay.toPlainText().strip()
        if text:
            font_name = self.cmb_font.currentText()
            font_size = self.spn_font_size.value()
            position = self.cmb_position.currentText()
            height_offset = self.spn_height.value()
            line_spacing = self.spn_line_spacing.value()
            self.saved_overlays.append({
                "text": text, "font": font_name, "size": font_size,
                "position": position, "height": height_offset, "spacing": line_spacing
            })

    def _detach_live(self):
        if self.live_window:
            self.live_window.close()
            self.live_window = None
        else:
            self.live_window = LiveWindow()
            pixmap = self.live_label.pixmap()
            if pixmap:
                self.live_window.update_frame(pixmap)
            self.live_window.show()

    def _set_focus_a(self):
        self.active_preview = "A"
        self.preview_a.setStyleSheet(
            "background-color: #1a1a2e; color: #555555; border: 3px solid #4fc3f7; border-radius: 8px;"
        )
        self.preview_b.setStyleSheet(
            "background-color: #1a1a2e; color: #555555; border: 2px solid #455a64; border-radius: 8px;"
        )

    def _set_focus_b(self):
        self.active_preview = "B"
        self.preview_b.setStyleSheet(
            "background-color: #1a1a2e; color: #555555; border: 3px solid #4fc3f7; border-radius: 8px;"
        )
        self.preview_a.setStyleSheet(
            "background-color: #1a1a2e; color: #555555; border: 2px solid #455a64; border-radius: 8px;"
        )

    def _get_active_preview(self):
        """Devuelve el QLabel de la pre-escucha con foco"""
        return self.preview_a if self.active_preview == "A" else self.preview_b

    def _send_focused_to_live(self):
        """Envía la pre-escucha con foco al master/vivo con transición. Limpia el pre."""
        preview = self._get_active_preview()
        base = self._get_base_frame_for(preview)
        if self.overlays_preview:
            for ov in self.overlays_preview:
                base = self._paint_overlay_on_pixmap(base, ov)
        if not base or base.isNull():
            return

        # 1. Desconectar y detener TODAS las fuentes
        self._disconnect_all_from_live()
        if self.camera_thread:
            try:
                self.camera_thread.frame_ready.disconnect()
            except (RuntimeError, TypeError):
                pass
        if self.screen_capture_thread:
            try:
                self.screen_capture_thread.frame_ready.disconnect()
            except (RuntimeError, TypeError):
                pass

        # 2. Aplicar transición
        self._apply_transition_to_live(base)
        self.overlays_live = list(self.overlays_preview)

        # 3. Determinar qué fuente estaba en el pre con foco y conectarla SOLO al live
        # Si hay video (camera_thread con archivo), conectar al live
        if self.camera_thread and self.camera_thread.running and isinstance(self.camera_thread.source, str):
            self.camera_thread.frame_ready.connect(self._update_live)
            # Detener screen capture si estaba corriendo
            if self.screen_capture_thread and self.screen_capture_thread.running:
                self.screen_capture_thread.stop()
        elif self.screen_capture_thread and self.screen_capture_thread.running:
            self.screen_capture_thread.frame_ready.connect(self._update_live_screen)
            # Detener camera si era de archivo
            if self.camera_thread and self.camera_thread.running and isinstance(self.camera_thread.source, str):
                self.camera_thread.stop()
        elif self.camera_thread and self.camera_thread.running:
            self.camera_thread.frame_ready.connect(self._update_live)

        # 4. Pasar audio del pre al master
        if self.active_preview == "A":
            ch = self.audio_mixer.channel_a
            # Si el canal tiene archivo, usarlo. Si no, usar el del camera_thread
            file_to_play = ch.current_file
            if not file_to_play and self.camera_thread and isinstance(self.camera_thread.source, str):
                file_to_play = self.camera_thread.source
            if file_to_play:
                self.audio_mixer.channel_master.stop()
                self.audio_mixer.channel_master.play(file_to_play)
            ch.stop()
            # Limpiar Pre A
            self.base_frame_a = None
            pix = QPixmap(self.preview_a.size())
            pix.fill(QColor(26, 26, 46))
            self.preview_a.setPixmap(pix)
            self.lbl_audio_icon_a.setVisible(False)
            self.lbl_audio_name_a.setText("")
            self.progress_a.setVisible(False)
        else:
            ch = self.audio_mixer.channel_b
            file_to_play = ch.current_file
            if not file_to_play and self.camera_thread and isinstance(self.camera_thread.source, str):
                file_to_play = self.camera_thread.source
            if file_to_play:
                self.audio_mixer.channel_master.stop()
                self.audio_mixer.channel_master.play(file_to_play)
            ch.stop()
            # Limpiar Pre B
            self.base_frame_b = None
            pix = QPixmap(self.preview_b.size())
            pix.fill(QColor(26, 26, 46))
            self.preview_b.setPixmap(pix)
            self.lbl_audio_icon_b.setVisible(False)
            self.lbl_audio_name_b.setText("")
            self.progress_b.setVisible(False)

        # 5. Limpiar overlays del pre
        self.overlays_preview = []

    def _disconnect_all_from_live(self):
        """Desconecta todas las fuentes de video del live de forma segura"""
        if self.camera_thread:
            for slot in [self._update_live, self._update_preview_a, self._update_preview_b]:
                try:
                    self.camera_thread.frame_ready.disconnect(slot)
                except (RuntimeError, TypeError):
                    pass
        if self.screen_capture_thread:
            for slot in [self._update_live_screen, self._update_screen_frame_a, self._update_screen_frame_b]:
                try:
                    self.screen_capture_thread.frame_ready.disconnect(slot)
                except (RuntimeError, TypeError):
                    pass

    def _send_camera_to_live(self):
        """Envía la cámara directamente al vivo"""
        if not self.camera_thread:
            cam_index = self.cmb_cameras.currentIndex()
            self.camera_thread = CameraThread(cam_index)
            self.camera_thread.error.connect(self._camera_error)
            self.camera_thread.start()
        self._disconnect_all_from_live()
        try:
            self.camera_thread.frame_ready.disconnect(self._update_preview_a)
        except (RuntimeError, TypeError):
            pass
        try:
            self.camera_thread.frame_ready.disconnect(self._update_preview_b)
        except (RuntimeError, TypeError):
            pass
        self.camera_thread.frame_ready.connect(self._update_live)

    def _apply_camera_effects(self, img):
        """Aplica brillo, contraste, saturación y efectos al QImage"""
        import cv2
        import numpy as np

        brightness = self.slider_brightness.value() - 100  # -100 a +100
        contrast = self.slider_contrast.value() / 100.0    # 0.0 a 2.0
        saturation = self.slider_saturation.value() / 100.0  # 0.0 a 2.0
        effect = self.cmb_effect.currentText()

        # Si todo está en default, no procesar
        if brightness == 0 and contrast == 1.0 and saturation == 1.0 and effect == "Ninguno":
            return img

        # Convertir QImage a numpy array
        w, h = img.width(), img.height()
        ptr = img.bits()
        if ptr is None:
            return img
        arr = np.array(ptr).reshape(h, w, 3).copy()

        # Brillo y contraste
        if brightness != 0 or contrast != 1.0:
            arr = cv2.convertScaleAbs(arr, alpha=contrast, beta=brightness)

        # Saturación
        if saturation != 1.0:
            hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV).astype(np.float32)
            hsv[:, :, 1] = np.clip(hsv[:, :, 1] * saturation, 0, 255)
            arr = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB)

        # Efectos
        if effect == "Blur":
            arr = cv2.GaussianBlur(arr, (15, 15), 0)
        elif effect == "Sepia":
            kernel = np.array([[0.272, 0.534, 0.131],
                               [0.349, 0.686, 0.168],
                               [0.393, 0.769, 0.189]])
            arr = cv2.transform(arr, kernel)
            arr = np.clip(arr, 0, 255).astype(np.uint8)
        elif effect == "B/N":
            gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
            arr = cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)
        elif effect == "Espejo":
            arr = cv2.flip(arr, 1)
        elif effect == "Viñeta":
            rows, cols = arr.shape[:2]
            X = cv2.getGaussianKernel(cols, cols * 0.4)
            Y = cv2.getGaussianKernel(rows, rows * 0.4)
            M = Y * X.T
            M = M / M.max()
            for i in range(3):
                arr[:, :, i] = (arr[:, :, i] * M).astype(np.uint8)

        # Convertir de vuelta a QImage
        h2, w2, ch = arr.shape
        result = QImage(arr.data, w2, h2, ch * w2, QImage.Format_RGB888)
        return result.copy()

    def _explorer_double_click(self, index):
        """Al hacer doble clic en un archivo del explorador, lo carga en la pre-escucha con foco"""
        source_index = self.file_proxy.mapToSource(index)
        path = self.file_model.filePath(source_index)
        if self.file_model.isDir(source_index):
            return
        ext = path.lower()
        if ext.endswith(('.png', '.jpg', '.bmp', '.jpeg', '.gif')):
            pixmap = QPixmap(path)
            preview = self._get_active_preview()
            # Guardar como frame base
            if self.active_preview == "A":
                self.base_frame_a = pixmap.copy()
            else:
                self.base_frame_b = pixmap.copy()
            preview.setPixmap(pixmap.scaled(
                preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            ))
        elif ext.endswith(('.mp4', '.avi', '.mkv', '.mov', '.webm')):
            self._play_video_to_focused(path)
        elif ext.endswith(('.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a')):
            self.audio_target = self.active_preview
            self.audio_mixer.get_channel(self.active_preview).play(path)
            preview = self._get_active_preview()
            self._show_speaker_in_preview(preview)

    def _explorer_context_menu(self, pos):
        """Menú contextual del explorador: enviar a Pre A, Pre B o Vivo"""
        index = self.file_tree.indexAt(pos)
        if not index.isValid():
            return
        source_index = self.file_proxy.mapToSource(index)
        if self.file_model.isDir(source_index):
            return
        path = self.file_model.filePath(source_index)
        ext = path.lower()
        if not ext.endswith(('.png', '.jpg', '.bmp', '.jpeg', '.gif',
                             '.mp4', '.avi', '.mkv', '.mov', '.webm',
                             '.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a')):
            return

        is_audio = ext.endswith(('.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a'))

        menu = QMenu(self)
        action_a = menu.addAction("▶ Reproducir en Pre-escucha A")
        action_b = menu.addAction("▶ Reproducir en Pre-escucha B")
        menu.addSeparator()
        action_live = menu.addAction("🔴 Reproducir en Vivo")

        action = menu.exec(self.file_tree.viewport().mapToGlobal(pos))
        if action == action_a:
            self._send_file_to_target(path, "A")
        elif action == action_b:
            self._send_file_to_target(path, "B")
        elif action == action_live:
            self._send_file_to_target(path, "LIVE")

    def _send_file_to_target(self, path, target):
        """Envía un archivo a Pre A, Pre B o Vivo directamente"""
        ext = path.lower()
        is_image = ext.endswith(('.png', '.jpg', '.bmp', '.jpeg', '.gif'))
        is_video = ext.endswith(('.mp4', '.avi', '.mkv', '.mov', '.webm'))
        is_audio = ext.endswith(('.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a'))

        # Si se envía al LIVE, detener todo lo anterior
        if target == "LIVE":
            self._disconnect_all_from_live()
            if self.screen_capture_thread and self.screen_capture_thread.running:
                self.screen_capture_thread.stop()
            # Detener audio anterior del master
            self.audio_mixer.channel_master.stop()

        if is_image:
            pixmap = QPixmap(path)
            if target == "A":
                self.base_frame_a = pixmap.copy()
                self.preview_a.setPixmap(pixmap.scaled(
                    self.preview_a.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
                ))
            elif target == "B":
                self.base_frame_b = pixmap.copy()
                self.preview_b.setPixmap(pixmap.scaled(
                    self.preview_b.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
                ))
            elif target == "LIVE":
                self.base_frame_live = pixmap.copy()
                self.live_label.setPixmap(pixmap.scaled(
                    self.live_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
                ))
                if self.live_window:
                    self.live_window.update_frame(pixmap)
        elif is_video:
            if self.camera_thread:
                self.camera_thread.stop()
                self.camera_thread.deleteLater()
            self.camera_thread = CameraThread(path)
            if target == "A":
                self.camera_thread.frame_ready.connect(self._update_preview_a)
                # NO reproducir audio en pre, solo video
            elif target == "B":
                self.camera_thread.frame_ready.connect(self._update_preview_b)
                # NO reproducir audio en pre, solo video
            elif target == "LIVE":
                self.camera_thread.frame_ready.connect(self._update_live)
                # Reproducir audio solo cuando va al vivo
                self.audio_mixer.channel_master.play(path)
            self.camera_thread.error.connect(self._camera_error)
            self.camera_thread.start()
            self.audio_target = target
        elif is_audio:
            if target == "LIVE":
                # Audio al vivo: reproducir por master
                self.audio_mixer.channel_master.play(path)
            elif target in ("A", "B"):
                # Audio al pre: cargar pero NO reproducir
                ch = self.audio_mixer.get_channel(target)
                ch.current_file = path
            self.audio_target = target
            # Mostrar icono de parlante en la pre-escucha si no es video
            if target == "A":
                self._show_speaker_in_preview(self.preview_a)
            elif target == "B":
                self._show_speaker_in_preview(self.preview_b)

    def _play_video_to_focused(self, path):
        """Reproduce un video en la pre-escucha con foco"""
        if self.camera_thread:
            self.camera_thread.stop()
            self.camera_thread.deleteLater()
        self.camera_thread = CameraThread(path)
        if self.active_preview == "A":
            self.camera_thread.frame_ready.connect(self._update_preview_a)
        else:
            self.camera_thread.frame_ready.connect(self._update_preview_b)
        self.camera_thread.error.connect(self._camera_error)
        self.camera_thread.start()
        # Reproducir audio del video
        self.audio_target = self.active_preview
        self.audio_mixer.get_channel(self.active_preview).play(path)

    def _choose_explorer_folder(self):
        """Permite elegir la carpeta raíz del explorador"""
        folder = QFileDialog.getExistingDirectory(self, "Elegir carpeta de medios")
        if folder:
            source_index = self.file_model.index(folder)
            self.file_tree.setRootIndex(self.file_proxy.mapFromSource(source_index))

    def _start_screen_capture(self):
        """Inicia captura de pantalla y la envía a la pre-escucha con foco"""
        if self.camera_thread:
            for slot in [self._update_preview_a, self._update_preview_b]:
                try:
                    self.camera_thread.frame_ready.disconnect(slot)
                except (RuntimeError, TypeError):
                    pass
        if self.screen_capture_thread:
            self.screen_capture_thread.stop()
        screen_idx = self.cmb_screens.currentIndex()
        self.screen_capture_thread = ScreenCaptureThread(screen_idx, fps=20)
        if self.active_preview == "A":
            self.screen_capture_thread.frame_ready.connect(self._update_screen_frame_a)
        else:
            self.screen_capture_thread.frame_ready.connect(self._update_screen_frame_b)
        self.screen_capture_thread.error.connect(self._camera_error)
        self.screen_capture_thread.start()

    def _start_screen_capture_to_live(self):
        """Inicia captura de pantalla directo al vivo"""
        # Desconectar todo del live
        self._disconnect_all_from_live()
        if self.camera_thread and self.camera_thread.running:
            try:
                self.camera_thread.frame_ready.disconnect()
            except (RuntimeError, TypeError):
                pass
        if self.screen_capture_thread:
            self.screen_capture_thread.stop()
        screen_idx = self.cmb_screens.currentIndex()
        self.screen_capture_thread = ScreenCaptureThread(screen_idx, fps=20)
        self.screen_capture_thread.frame_ready.connect(self._update_live_screen)
        self.screen_capture_thread.error.connect(self._camera_error)
        self.screen_capture_thread.start()

    def _update_screen_frame_a(self, img):
        """Actualiza preview A con frame de pantalla + PiP si corresponde"""
        pixmap = QPixmap.fromImage(img)
        if self.pip_enabled and self.pip_frame and self._pip_target == "A":
            pixmap = self._composite_pip(pixmap)
        self.base_frame_a = pixmap.copy()
        if self.overlays_preview and self.active_preview == "A":
            for ov in self.overlays_preview:
                pixmap = self._paint_overlay_on_pixmap(pixmap, ov)
        self.preview_a.setPixmap(pixmap.scaled(
            self.preview_a.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        ))

    def _update_screen_frame_b(self, img):
        """Actualiza preview B con frame de pantalla + PiP si corresponde"""
        pixmap = QPixmap.fromImage(img)
        if self.pip_enabled and self.pip_frame and self._pip_target == "B":
            pixmap = self._composite_pip(pixmap)
        self.base_frame_b = pixmap.copy()
        if self.overlays_preview and self.active_preview == "B":
            for ov in self.overlays_preview:
                pixmap = self._paint_overlay_on_pixmap(pixmap, ov)
        self.preview_b.setPixmap(pixmap.scaled(
            self.preview_b.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        ))

    def _start_pip_camera(self):
        """Inicia la cámara PiP (se superpone sobre la captura de pantalla)"""
        if self.pip_camera_thread:
            self.pip_camera_thread.stop()
            self.pip_camera_thread = None
        cam_index = self.cmb_cameras.currentIndex()
        # Si la cámara principal ya usa este índice, compartir frames
        if self.camera_thread and self.camera_thread.source == cam_index and self.camera_thread.running:
            self.camera_thread.frame_ready.connect(self._update_pip_frame)
            self.pip_enabled = True
            return
        self.pip_camera_thread = CameraThread(cam_index)
        self.pip_camera_thread.frame_ready.connect(self._update_pip_frame)
        self.pip_camera_thread.error.connect(self._camera_error)
        self.pip_camera_thread.start()
        self.pip_enabled = True

    def _update_pip_frame(self, img):
        """Guarda el último frame de la cámara PiP y lo pinta en el destino"""
        img = self._apply_camera_effects(img)
        self.pip_frame = QPixmap.fromImage(img)
        if not self.pip_enabled:
            return
        # Siempre pintar en el destino
        if self._pip_target == "A":
            if not self.base_frame_a:
                self.base_frame_a = QPixmap(self.preview_a.size())
                self.base_frame_a.fill(QColor(26, 26, 46))
            pixmap = self._composite_pip(self.base_frame_a.copy())
            self.preview_a.setPixmap(pixmap.scaled(
                self.preview_a.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        elif self._pip_target == "B":
            if not self.base_frame_b:
                self.base_frame_b = QPixmap(self.preview_b.size())
                self.base_frame_b.fill(QColor(26, 26, 46))
            pixmap = self._composite_pip(self.base_frame_b.copy())
            self.preview_b.setPixmap(pixmap.scaled(
                self.preview_b.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        elif self._pip_target == "LIVE" and not self._transition_active:
            if not self.base_frame_live:
                self.base_frame_live = QPixmap(self.live_label.size())
                self.base_frame_live.fill(QColor(26, 26, 46))
            pixmap = self._composite_pip(self.base_frame_live.copy())
            self.live_label.setPixmap(pixmap.scaled(
                self.live_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _pip_to_live(self):
        """Toggle PiP en el vivo"""
        if self.pip_enabled and self._pip_target == "LIVE":
            self.pip_enabled = False
            if self.pip_camera_thread:
                self.pip_camera_thread.stop()
                self.pip_camera_thread = None
            self.pip_frame = None
            # Repintar live sin PiP
            if self.base_frame_live:
                self.live_label.setPixmap(self.base_frame_live.scaled(
                    self.live_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.btn_pip_live.setStyleSheet("background-color: #e53935; color: white; font-weight: bold; padding: 4px;")
        else:
            self._pip_target = "LIVE"
            if not self.pip_camera_thread:
                self._start_pip_camera()
            self.pip_enabled = True
            self.btn_pip_live.setStyleSheet("background-color: #e53935; color: white; font-weight: bold; padding: 4px; border: 2px solid #4fc3f7;")
            self.btn_pip_a.setStyleSheet("")
            self.btn_pip_b.setStyleSheet("")

    def _pip_to_a(self):
        """Toggle PiP en Pre A"""
        if self.pip_enabled and self._pip_target == "A":
            self.pip_enabled = False
            if self.pip_camera_thread:
                self.pip_camera_thread.stop()
                self.pip_camera_thread = None
            self.pip_frame = None
            # Repintar Pre A sin PiP
            if self.base_frame_a:
                self.preview_a.setPixmap(self.base_frame_a.scaled(
                    self.preview_a.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.btn_pip_a.setStyleSheet("")
        else:
            self._pip_target = "A"
            if not self.pip_camera_thread:
                self._start_pip_camera()
            self.pip_enabled = True
            self.btn_pip_a.setStyleSheet(" border: 2px solid #4fc3f7;")
            self.btn_pip_b.setStyleSheet("")
            self.btn_pip_live.setStyleSheet("background-color: #e53935; color: white; font-weight: bold; padding: 4px;")

    def _pip_to_b(self):
        """Toggle PiP en Pre B"""
        if self.pip_enabled and self._pip_target == "B":
            self.pip_enabled = False
            if self.pip_camera_thread:
                self.pip_camera_thread.stop()
                self.pip_camera_thread = None
            self.pip_frame = None
            # Repintar Pre B sin PiP
            if self.base_frame_b:
                self.preview_b.setPixmap(self.base_frame_b.scaled(
                    self.preview_b.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.btn_pip_b.setStyleSheet("")
        else:
            self._pip_target = "B"
            if not self.pip_camera_thread:
                self._start_pip_camera()
            self.pip_enabled = True
            self.btn_pip_b.setStyleSheet(" border: 2px solid #4fc3f7;")
            self.btn_pip_a.setStyleSheet("")
            self.btn_pip_live.setStyleSheet("background-color: #e53935; color: white; font-weight: bold; padding: 4px;")

    def _on_pip_shape_changed(self, text):
        if text == "Desactivado":
            self.pip_enabled = False
            if self.pip_camera_thread:
                self.pip_camera_thread.stop()
                self.pip_camera_thread = None
        elif text == "Círculo":
            self.pip_shape = "circle"
            self.pip_enabled = True
        elif text == "Cuadrado":
            self.pip_shape = "square"
            self.pip_enabled = True

    def _composite_pip(self, base_pixmap):
        """Compone la cámara PiP sobre el pixmap base"""
        result = base_pixmap.copy()
        pip_size = min(result.width(), result.height()) // 4
        pip_scaled = self.pip_frame.scaled(pip_size, pip_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        painter = QPainter(result)
        painter.setRenderHint(QPainter.Antialiasing)

        # Posición: esquina inferior derecha
        x = result.width() - pip_scaled.width() - 10
        y = result.height() - pip_scaled.height() - 10

        if self.pip_shape == "circle":
            # Crear máscara circular
            path = QPainterPath()
            path.addEllipse(x, y, pip_scaled.width(), pip_scaled.height())
            painter.setClipPath(path)
            painter.drawPixmap(x, y, pip_scaled)
            painter.setClipping(False)
            # Borde del círculo
            painter.setPen(QPen(QColor(255, 255, 255), 3))
            painter.drawEllipse(x, y, pip_scaled.width(), pip_scaled.height())
        else:  # square
            painter.drawPixmap(x, y, pip_scaled)
            painter.setPen(QPen(QColor(255, 255, 255), 2))
            painter.drawRect(x, y, pip_scaled.width(), pip_scaled.height())

        painter.end()
        return result

    def _pick_text_color(self):
        color = QColorDialog.getColor(self.overlay_text_color, self, "Color del texto")
        if color.isValid():
            self.overlay_text_color = color
            self.btn_text_color.setStyleSheet(
                f"background-color: {color.name()}; border: 1px solid #999; border-radius: 3px;"
            )
            self._update_text_preview_label()

    def _pick_bg_color(self):
        color = QColorDialog.getColor(self.overlay_bg_color, self, "Color de fondo",
                                      QColorDialog.ShowAlphaChannel)
        if color.isValid():
            self.overlay_bg_color = color
            r, g, b, a = color.red(), color.green(), color.blue(), color.alpha()
            self.btn_bg_color.setStyleSheet(
                f"background-color: rgba({r},{g},{b},{a}); border: 1px solid #999; border-radius: 3px;"
            )
            self._update_text_preview_label()

    def _update_text_preview_label(self):
        """Actualiza la muestra de texto con la fuente y colores actuales"""
        text = self.txt_overlay.toPlainText().strip()
        if not text:
            text = "Muestra"
        # Mostrar solo los primeros 20 chars
        display = text[:20] + ("..." if len(text) > 20 else "")
        self.lbl_text_preview.setText(display)
        font_name = self.cmb_font.currentText()
        self.lbl_text_preview.setFont(QFont(font_name, 11, QFont.Bold))
        tc = self.overlay_text_color
        bg = self.overlay_bg_color
        self.lbl_text_preview.setStyleSheet(
            f"background-color: rgba({bg.red()},{bg.green()},{bg.blue()},{bg.alpha()}); "
            f"color: {tc.name()}; border-radius: 4px; padding: 4px 12px; font-weight: bold;"
        )

    # --- UI ---
    def _build_ui(self):
        # Menú principal
        from PySide6.QtWidgets import QMenuBar
        menubar = self.menuBar()
        menu_archivo = menubar.addMenu("Archivo")
        menu_archivo.addAction("Abrir proyecto", self._load_schedule_list)
        menu_archivo.addAction("Guardar proyecto", self._save_schedule_list)
        menu_archivo.addSeparator()
        menu_archivo.addAction("Cerrar", self.close)
        menu_config = menubar.addMenu("Configuración")
        menu_config.addAction("Pantalla de salida del Vivo", self._config_output_screen)
        menu_config.addAction("Streaming (YouTube/Facebook/Twitch)", self._config_streaming)
        menu_config.addSeparator()
        menu_config.addAction("Restablecer paneles", self._reset_panels)
        menu_ayuda = menubar.addMenu("Ayuda")
        menu_ayuda.addAction("Acerca de", self._show_about)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(5, 5, 5, 5)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_center_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setSizes([320, 760, 320])
        layout.addWidget(splitter)

    def _show_about(self):
        from PySide6.QtWidgets import QMessageBox
        msg = QMessageBox(self)
        msg.setWindowTitle("Acerca de GBSturio")
        msg.setStyleSheet("QMessageBox { background-color: #ffffff; } QLabel { color: #000000; font-size: 13px; }")
        msg.setText(
            "<h2 style='color:#000;'>GBSturio - Video Studio</h2>"
            "<p style='color:#000;'><b>Software desarrollado por:</b><br>"
            "Ing. Gabrielli Gabriel</p>"
            "<p style='color:#000;'><b>Contacto:</b><br>"
            "📧 gabgabrielligabriel@gmail.com<br>"
            "📧 virtualgaby361@gmail.com<br>"
            "📱 WhatsApp: 1121674227</p>"
            "<hr>"
            "<p style='color:#000;'>Este software fue desarrollado sin fines de lucro.<br>"
            "Si te resulta útil, podés enviar una donación<br>"
            "para seguir mejorando el programa.</p>"
            "<p style='color:#000;'><b>💰 Mercado Pago - Alias: gaby28894178</b><br>"
            "Se apreciará cualquier monto. ¡Gracias!</p>"
            "<hr>"
            "<p style='color:#000;'><i>© 2026 GBSturio - Todos los derechos reservados</i></p>"
        )
        msg.exec()

    def _config_output_screen(self):
        """Configurar pantalla de salida del vivo"""
        from PySide6.QtWidgets import QDialog
        from PySide6.QtGui import QGuiApplication
        dialog = QDialog(self)
        dialog.setWindowTitle("Pantalla de salida del Vivo")
        dialog.setMinimumSize(400, 250)
        dialog.setStyleSheet("QDialog{background:#2b2b2b;} QLabel{color:#fff;font-size:12px;} QComboBox{background:#333;color:#fff;border:1px solid #4a4a4a;padding:5px;} QPushButton{background:#3a3a3a;color:#fff;border:1px solid #4a4a4a;padding:8px;border-radius:3px;} QPushButton:hover{border:1px solid #4fc3f7;}")
        dl = QVBoxLayout(dialog)
        dl.addWidget(QLabel("Seleccionar pantalla para la salida en vivo:"))
        screens = QGuiApplication.screens()
        cmb_screen = QComboBox()
        for i, s in enumerate(screens):
            geo = s.geometry()
            cmb_screen.addItem(f"Pantalla {i}: {s.name()} ({geo.width()}x{geo.height()})")
        dl.addWidget(cmb_screen)
        dl.addWidget(QLabel("\nResolución de salida:"))
        res_row = QHBoxLayout()
        spn_w = QSpinBox()
        spn_w.setRange(320, 3840)
        spn_w.setValue(1920)
        spn_w.setSuffix(" px")
        res_row.addWidget(QLabel("Ancho:"))
        res_row.addWidget(spn_w)
        spn_h = QSpinBox()
        spn_h.setRange(240, 2160)
        spn_h.setValue(1080)
        spn_h.setSuffix(" px")
        res_row.addWidget(QLabel("Alto:"))
        res_row.addWidget(spn_h)
        dl.addLayout(res_row)
        dl.addWidget(QLabel("\nFPS:"))
        spn_fps = QSpinBox()
        spn_fps.setRange(15, 60)
        spn_fps.setValue(30)
        dl.addWidget(spn_fps)
        btn_ok = QPushButton("Aplicar y abrir pantalla de salida")
        btn_ok.clicked.connect(lambda: self._apply_output_screen(cmb_screen.currentIndex(), dialog))
        dl.addWidget(btn_ok)
        dialog.exec()

    def _apply_output_screen(self, screen_index, dialog):
        """Abre la pantalla de salida fullscreen en el monitor elegido"""
        from PySide6.QtGui import QGuiApplication
        try:
            screens = QGuiApplication.screens()
            if screen_index >= len(screens):
                return
            screen = screens[screen_index]
            geo = screen.geometry()

            # Cerrar ventana de salida anterior si existe
            if self.live_window:
                self.live_window.close()

            # Crear ventana fullscreen en el monitor elegido
            self.live_window = LiveWindow()
            self.live_window.setGeometry(geo)
            self.live_window.showFullScreen()

            # Conectar para que se actualice con el vivo
            pixmap = self.live_label.pixmap()
            if pixmap:
                self.live_window.update_frame(pixmap)

            dialog.accept()
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Error", f"No se pudo abrir la pantalla de salida:\n{str(e)}")

    def _config_streaming(self):
        """Configurar plataformas de streaming"""
        from PySide6.QtWidgets import QDialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Configuración de Streaming")
        dialog.setMinimumSize(500, 350)
        dialog.setStyleSheet("QDialog{background:#2b2b2b;} QLabel{color:#fff;font-size:12px;} QLineEdit{background:#333;color:#fff;border:1px solid #4a4a4a;padding:5px;} QPushButton{background:#3a3a3a;color:#fff;border:1px solid #4a4a4a;padding:8px;border-radius:3px;} QPushButton:hover{border:1px solid #4fc3f7;} QCheckBox{color:#fff;}")
        dl = QVBoxLayout(dialog)
        dl.addWidget(QLabel("Configurar URLs de streaming:"))
        # YouTube
        dl.addWidget(QLabel("\n🔴 YouTube Live:"))
        yt_row = QHBoxLayout()
        yt_row.addWidget(QLabel("RTMP URL:"))
        self._yt_url = QLineEdit()
        self._yt_url.setPlaceholderText("rtmp://a.rtmp.youtube.com/live2/...")
        yt_row.addWidget(self._yt_url, 1)
        dl.addLayout(yt_row)
        yt_key = QHBoxLayout()
        yt_key.addWidget(QLabel("Stream Key:"))
        self._yt_key = QLineEdit()
        self._yt_key.setPlaceholderText("Tu clave de stream...")
        self._yt_key.setEchoMode(QLineEdit.Password)
        yt_key.addWidget(self._yt_key, 1)
        dl.addLayout(yt_key)
        # Facebook
        dl.addWidget(QLabel("\n🔵 Facebook Live:"))
        fb_row = QHBoxLayout()
        fb_row.addWidget(QLabel("RTMP URL:"))
        self._fb_url = QLineEdit()
        self._fb_url.setPlaceholderText("rtmps://live-api-s.facebook.com:443/rtmp/...")
        fb_row.addWidget(self._fb_url, 1)
        dl.addLayout(fb_row)
        # Twitch
        dl.addWidget(QLabel("\n🟣 Twitch:"))
        tw_row = QHBoxLayout()
        tw_row.addWidget(QLabel("RTMP URL:"))
        self._tw_url = QLineEdit()
        self._tw_url.setPlaceholderText("rtmp://live.twitch.tv/app/...")
        tw_row.addWidget(self._tw_url, 1)
        dl.addLayout(tw_row)
        # Custom
        dl.addWidget(QLabel("\n⚙️ RTMP Personalizado:"))
        custom_row = QHBoxLayout()
        custom_row.addWidget(QLabel("URL:"))
        self._custom_url = QLineEdit()
        self._custom_url.setPlaceholderText("rtmp://tu-servidor.com/live/...")
        custom_row.addWidget(self._custom_url, 1)
        dl.addLayout(custom_row)
        btn_ok = QPushButton("Guardar configuración")
        btn_ok.clicked.connect(dialog.accept)
        dl.addWidget(btn_ok)
        dialog.exec()

    def _reset_panels(self):
        """Restablece los paneles a su posición original"""
        pass

    def _stop_output_screen(self):
        """Cierra la pantalla de salida"""
        if self.live_window:
            self.live_window.close()
            self.live_window = None

    def _toggle_streaming(self):
        """Toggle iniciar/detener streaming"""
        panel_icons = os.path.join(os.path.dirname(__file__), "icons", "panel_derecho")
        if self._streaming_active:
            self._streaming_active = False
            self.btn_streaming.setText(" Iniciar Streaming")
            self.btn_streaming.setIcon(QIcon(os.path.join(panel_icons, "streaming_off.png")))
        else:
            self._streaming_active = True
            self.btn_streaming.setText(" Detener Streaming")
            self.btn_streaming.setIcon(QIcon(os.path.join(panel_icons, "streaming_on.png")))

    def _build_left_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)

        logo = QLabel("GBSTURIO")
        logo.setFont(QFont("Arial", 12, QFont.Bold))
        logo.setStyleSheet("color: #4fc3f7;")
        layout.addWidget(logo)

        # Tabs del panel izquierdo
        self.left_tabs = QTabWidget()
        self.left_tabs.setStyleSheet("QTabBar::tab { padding: 4px 10px; font-size: 10px; }")

        # --- Tab 1: Medios (Explorador + Fuentes de Video) ---
        tab_medios = QWidget()
        medios_layout = QVBoxLayout(tab_medios)
        medios_layout.setContentsMargins(3, 3, 3, 3)
        medios_layout.setSpacing(3)

        # Explorador de Archivos
        grp_explorer = QGroupBox("Explorador de Archivos")
        el = QVBoxLayout(grp_explorer)

        # Botón para elegir carpeta raíz
        btn_choose_folder = QPushButton(" Elegir carpeta")
        btn_choose_folder.setIcon(QIcon(os.path.join(self._icons_path, "carpeta.png")))
        btn_choose_folder.setIconSize(self._icon_size())
        btn_choose_folder.clicked.connect(self._choose_explorer_folder)
        el.addWidget(btn_choose_folder)

        # TreeView con modelo de archivos
        self.file_model = QFileSystemModel()
        self.file_model.setRootPath(QDir.homePath())
        self.file_model.setNameFilters([
            "*.mp4", "*.avi", "*.mkv", "*.mov", "*.webm",
            "*.png", "*.jpg", "*.jpeg", "*.bmp", "*.gif",
            "*.mp3", "*.wav", "*.ogg", "*.flac", "*.aac", "*.m4a"
        ])
        self.file_model.setNameFilterDisables(False)
        self.file_model.setFilter(QDir.AllDirs | QDir.Files | QDir.NoDotAndDotDot)

        # Proxy para filtrar carpetas que empiezan con "."
        self.file_proxy = QSortFilterProxyModel()
        self.file_proxy.setSourceModel(self.file_model)
        self.file_proxy.setFilterRole(QFileSystemModel.FileNameRole)
        self.file_proxy.setRecursiveFilteringEnabled(True)
        self.file_proxy.setFilterRegularExpression(r"^[^\.].*")

        self.file_tree = QTreeView()
        self.file_tree.setModel(self.file_proxy)
        self.file_tree.setRootIndex(self.file_proxy.mapFromSource(self.file_model.index(QDir.homePath())))
        self.file_tree.setColumnHidden(1, True)  # Ocultar tamaño
        self.file_tree.setColumnHidden(2, True)  # Ocultar tipo
        self.file_tree.setColumnHidden(3, True)  # Ocultar fecha
        self.file_tree.setHeaderHidden(True)
        self.file_tree.setDragEnabled(True)
        self.file_tree.setDragDropMode(QTreeView.DragOnly)
        self.file_tree.doubleClicked.connect(self._explorer_double_click)
        self.file_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_tree.customContextMenuRequested.connect(self._explorer_context_menu)
        self.file_tree.setStyleSheet("QTreeView { font-size: 11px; }")
        self.file_tree.setMinimumHeight(200)
        el.addWidget(self.file_tree, 1)

        lbl_hint = QLabel("Doble clic o clic derecho para enviar")
        lbl_hint.setStyleSheet("color: #666; font-size: 10px; font-style: italic;")
        el.addWidget(lbl_hint)
        medios_layout.addWidget(grp_explorer, 3)

        # Fuentes de Cámaras
        grp_cams = QGroupBox("Fuentes de Video")
        cl = QVBoxLayout(grp_cams)

        # Cámara
        cl.addWidget(QLabel("Cámara:"))
        self.cmb_cameras = QComboBox()
        self.cmb_cameras.addItems(["Webcam USB (0)", "Capturadora HDMI (1)"])
        cl.addWidget(self.cmb_cameras)
        btn_row_cam = QHBoxLayout()
        btn_detect = QPushButton(" Detectar")
        btn_detect.setIcon(QIcon(os.path.join(self._icons_path, "detectar.png")))
        btn_detect.setIconSize(self._icon_size())
        btn_detect.clicked.connect(self._detect_cameras)
        btn_row_cam.addWidget(btn_detect)
        btn_start_cam = QPushButton(" Iniciar")
        btn_start_cam.setIcon(QIcon(os.path.join(self._icons_path, "play.png")))
        btn_start_cam.setIconSize(self._icon_size())
        btn_start_cam.clicked.connect(self._start_camera)
        btn_row_cam.addWidget(btn_start_cam)
        cl.addLayout(btn_row_cam)
        btn_cam_live = QPushButton(" Cámara al Vivo")
        btn_cam_live.setIcon(QIcon(os.path.join(self._icons_path, "live-1.png")))
        btn_cam_live.setIconSize(self._icon_size())
        btn_cam_live.setStyleSheet("")
        btn_cam_live.clicked.connect(self._send_camera_to_live)
        cl.addWidget(btn_cam_live)

        # Captura de pantalla
        cl.addWidget(QLabel("Captura de pantalla:"))
        self.cmb_screens = QComboBox()
        self.cmb_screens.addItems(ScreenCaptureThread.get_screens())
        cl.addWidget(self.cmb_screens)
        btn_start_screen = QPushButton(" Capturar Pantalla")
        btn_start_screen.setIcon(QIcon(os.path.join(self._icons_path, "pantalla.png")))
        btn_start_screen.setIconSize(self._icon_size())
        btn_start_screen.clicked.connect(self._start_screen_capture)
        cl.addWidget(btn_start_screen)
        btn_screen_live = QPushButton(" Capturar al Vivo")
        btn_screen_live.setIcon(QIcon(os.path.join(self._icons_path, "live-1.png")))
        btn_screen_live.setIconSize(self._icon_size())
        btn_screen_live.clicked.connect(self._start_screen_capture_to_live)
        cl.addWidget(btn_screen_live)

        # PiP (cámara sobre captura)
        cl.addWidget(QLabel("PiP (cámara sobre video):"))
        pip_row = QHBoxLayout()
        self.cmb_pip_shape = QComboBox()
        self.cmb_pip_shape.addItems(["Círculo", "Cuadrado", "Desactivado"])
        self.cmb_pip_shape.currentTextChanged.connect(self._on_pip_shape_changed)
        pip_row.addWidget(self.cmb_pip_shape)
        self.btn_pip_cam = QPushButton("📷 PiP Cam")
        self.btn_pip_cam.clicked.connect(self._start_pip_camera)
        pip_row.addWidget(self.btn_pip_cam)
        cl.addLayout(pip_row)
        pip_dest_row = QHBoxLayout()
        pre_icons = os.path.join(os.path.dirname(__file__), "icons", "pre")
        self.btn_pip_a = QPushButton(" A")
        self.btn_pip_a.setIcon(QIcon(os.path.join(pre_icons, "pre_a.png")))
        self.btn_pip_a.setIconSize(self._icon_size())
        self.btn_pip_a.setStyleSheet("")
        self.btn_pip_a.clicked.connect(self._pip_to_a)
        pip_dest_row.addWidget(self.btn_pip_a)
        self.btn_pip_b = QPushButton(" B")
        self.btn_pip_b.setIcon(QIcon(os.path.join(pre_icons, "pre_b.png")))
        self.btn_pip_b.setIconSize(self._icon_size())
        self.btn_pip_b.setStyleSheet("")
        self.btn_pip_b.clicked.connect(self._pip_to_b)
        pip_dest_row.addWidget(self.btn_pip_b)
        self.btn_pip_live = QPushButton(" Vivo")
        self.btn_pip_live.setIcon(QIcon(os.path.join(self._icons_path, "live-1.png")))
        self.btn_pip_live.setIconSize(self._icon_size())
        self.btn_pip_live.clicked.connect(self._pip_to_live)
        pip_dest_row.addWidget(self.btn_pip_live)
        cl.addLayout(pip_dest_row)

        medios_layout.addWidget(grp_cams)

        self.left_tabs.addTab(tab_medios, "📁 Medios")

        # --- Tab 2: Biblia ---
        tab_biblia = QWidget()
        biblia_layout = QVBoxLayout(tab_biblia)
        biblia_layout.setContentsMargins(3, 3, 3, 3)
        biblia_layout.setSpacing(3)

        # Versículos Bíblicos
        grp_bible = QGroupBox("📖 Biblia")
        bl = QVBoxLayout(grp_bible)
        # Versión
        ver_row = QHBoxLayout()
        ver_row.addWidget(QLabel("Versión:"))
        self.cmb_bible_version = QComboBox()
        self.cmb_bible_version.addItems(["reina-valera-1960", "nvi", "ntv", "lbla", "dhh"])
        ver_row.addWidget(self.cmb_bible_version)
        bl.addLayout(ver_row)
        # Búsqueda por referencia
        search_row = QHBoxLayout()
        self.txt_bible_ref = QLineEdit()
        self.txt_bible_ref.setPlaceholderText("Ej: Juan 3:16")
        search_row.addWidget(self.txt_bible_ref, 1)
        btn_search = QPushButton()
        btn_search.setIcon(QIcon(os.path.join(self._icons_path, "buscar.png")))
        btn_search.setIconSize(self._icon_size())
        btn_search.setFixedSize(32, 28)
        btn_search.clicked.connect(self._search_bible)
        search_row.addWidget(btn_search)
        bl.addLayout(search_row)
        # Búsqueda inteligente por tema
        smart_row = QHBoxLayout()
        self.txt_bible_smart = QLineEdit()
        self.txt_bible_smart.setPlaceholderText("Buscar por tema: ej. jesús sana leproso")
        smart_row.addWidget(self.txt_bible_smart, 1)
        btn_smart = QPushButton("🔎")
        btn_smart.setFixedSize(32, 28)
        btn_smart.setToolTip("Búsqueda inteligente por palabras clave")
        btn_smart.clicked.connect(self._search_bible_smart)
        smart_row.addWidget(btn_smart)
        bl.addLayout(smart_row)
        # Resultado
        self.txt_bible_result = QTextEdit()
        self.txt_bible_result.setReadOnly(True)
        self.txt_bible_result.setPlaceholderText("Versículo...")
        self.txt_bible_result.setMaximumHeight(240)
        bl.addWidget(self.txt_bible_result)
        # Tamaño y color del texto
        style_row = QHBoxLayout()
        style_row.addWidget(QLabel("Tam:"))
        self.spn_bible_size = QSpinBox()
        self.spn_bible_size.setRange(10, 80)
        self.spn_bible_size.setValue(22)
        self.spn_bible_size.setSuffix("px")
        self.spn_bible_size.setFixedWidth(65)
        style_row.addWidget(self.spn_bible_size)
        style_row.addWidget(QLabel("Color:"))
        self.btn_bible_color = QPushButton("  ")
        self.btn_bible_color.setFixedSize(24, 20)
        self.btn_bible_color.setStyleSheet("background-color: #ffffff; border: 1px solid #666; border-radius: 3px;")
        self.btn_bible_color.clicked.connect(self._pick_bible_color)
        style_row.addWidget(self.btn_bible_color)
        style_row.addStretch()
        bl.addLayout(style_row)
        self._bible_text_color = QColor(255, 255, 255)
        # Botones
        bible_btns = QHBoxLayout()
        btn_bp = QPushButton(" Pre")
        btn_bp.setIcon(QIcon(os.path.join(os.path.dirname(__file__), "icons", "pre", "pre_a.png")))
        btn_bp.setIconSize(self._icon_size())
        btn_bp.setStyleSheet("")
        btn_bp.clicked.connect(self._bible_to_preview)
        bible_btns.addWidget(btn_bp)
        btn_bl = QPushButton(" Vivo")
        btn_bl.setIcon(QIcon(os.path.join(self._icons_path, "live-1.png")))
        btn_bl.setIconSize(self._icon_size())
        btn_bl.setStyleSheet("")
        btn_bl.clicked.connect(self._bible_to_live)
        bible_btns.addWidget(btn_bl)
        bl.addLayout(bible_btns)
        biblia_layout.addWidget(grp_bible)
        biblia_layout.addStretch()
        self.left_tabs.addTab(tab_biblia, QIcon(os.path.join(self._icons_path, "buscar.png")), "Biblia")

        # --- Tab 3: Imágenes ---
        tab_imgs = QWidget()
        imgs_layout = QVBoxLayout(tab_imgs)
        imgs_layout.setContentsMargins(3, 3, 3, 3)
        btn_imgs_folder = QPushButton(" Elegir carpeta de imágenes")
        btn_imgs_folder.setIcon(QIcon(os.path.join(self._icons_path, "carpeta.png")))
        btn_imgs_folder.setIconSize(self._icon_size())
        btn_imgs_folder.clicked.connect(self._choose_images_folder)
        imgs_layout.addWidget(btn_imgs_folder)
        self.list_images = QListWidget()
        self.list_images.doubleClicked.connect(self._image_double_click)
        imgs_layout.addWidget(self.list_images, 1)
        img_btns = QHBoxLayout()
        btn_img_pre = QPushButton(" Pre")
        btn_img_pre.setIcon(QIcon(os.path.join(os.path.dirname(__file__), "icons", "pre", "pre_a.png")))
        btn_img_pre.clicked.connect(lambda: self._send_selected_media(self.list_images, "preview"))
        img_btns.addWidget(btn_img_pre)
        btn_img_live = QPushButton(" Vivo")
        btn_img_live.setIcon(QIcon(os.path.join(self._icons_path, "live-1.png")))
        btn_img_live.clicked.connect(lambda: self._send_selected_media(self.list_images, "live"))
        img_btns.addWidget(btn_img_live)
        imgs_layout.addLayout(img_btns)
        medios_icons = os.path.join(os.path.dirname(__file__), "icons", "medios")
        self.left_tabs.addTab(tab_imgs, QIcon(os.path.join(medios_icons, "tab_imagenes..png")), "Imágenes")

        # --- Tab 4: Audio ---
        tab_audios = QWidget()
        audios_layout = QVBoxLayout(tab_audios)
        audios_layout.setContentsMargins(3, 3, 3, 3)
        btn_audio_folder = QPushButton(" Elegir carpeta de audio")
        btn_audio_folder.setIcon(QIcon(os.path.join(self._icons_path, "carpeta.png")))
        btn_audio_folder.setIconSize(self._icon_size())
        btn_audio_folder.clicked.connect(self._choose_audio_folder)
        audios_layout.addWidget(btn_audio_folder)
        self.list_audios = QListWidget()
        self.list_audios.doubleClicked.connect(self._audio_double_click)
        audios_layout.addWidget(self.list_audios, 1)
        aud_btns = QHBoxLayout()
        btn_aud_pre = QPushButton(" Pre")
        btn_aud_pre.setIcon(QIcon(os.path.join(os.path.dirname(__file__), "icons", "pre", "pre_a.png")))
        btn_aud_pre.clicked.connect(lambda: self._send_selected_media(self.list_audios, "preview"))
        aud_btns.addWidget(btn_aud_pre)
        btn_aud_live = QPushButton(" Vivo")
        btn_aud_live.setIcon(QIcon(os.path.join(self._icons_path, "live-1.png")))
        btn_aud_live.clicked.connect(lambda: self._send_selected_media(self.list_audios, "live"))
        aud_btns.addWidget(btn_aud_live)
        audios_layout.addLayout(aud_btns)
        self.left_tabs.addTab(tab_audios, QIcon(os.path.join(medios_icons, "tab_audio.png")), "Audio")

        # --- Tab 5: Videos ---
        tab_videos = QWidget()
        videos_layout = QVBoxLayout(tab_videos)
        videos_layout.setContentsMargins(3, 3, 3, 3)
        btn_video_folder = QPushButton(" Elegir carpeta de videos")
        btn_video_folder.setIcon(QIcon(os.path.join(self._icons_path, "carpeta.png")))
        btn_video_folder.setIconSize(self._icon_size())
        btn_video_folder.clicked.connect(self._choose_video_folder)
        videos_layout.addWidget(btn_video_folder)
        self.list_videos = QListWidget()
        self.list_videos.doubleClicked.connect(self._video_double_click)
        videos_layout.addWidget(self.list_videos, 1)
        vid_btns = QHBoxLayout()
        btn_vid_pre = QPushButton(" Pre")
        btn_vid_pre.setIcon(QIcon(os.path.join(os.path.dirname(__file__), "icons", "pre", "pre_a.png")))
        btn_vid_pre.clicked.connect(lambda: self._send_selected_media(self.list_videos, "preview"))
        vid_btns.addWidget(btn_vid_pre)
        btn_vid_live = QPushButton(" Vivo")
        btn_vid_live.setIcon(QIcon(os.path.join(self._icons_path, "live-1.png")))
        btn_vid_live.clicked.connect(lambda: self._send_selected_media(self.list_videos, "live"))
        vid_btns.addWidget(btn_vid_live)
        videos_layout.addLayout(vid_btns)
        self.left_tabs.addTab(tab_videos, QIcon(os.path.join(medios_icons, "tab_videos.png")), "Videos")

        layout.addWidget(self.left_tabs)

        # Sliders ocultos para efectos (mantener compatibilidad)
        self.slider_brightness = QSlider(Qt.Horizontal)
        self.slider_brightness.setRange(0, 200)
        self.slider_brightness.setValue(100)
        self.slider_brightness.setVisible(False)
        self.slider_contrast = QSlider(Qt.Horizontal)
        self.slider_contrast.setRange(0, 200)
        self.slider_contrast.setValue(100)
        self.slider_contrast.setVisible(False)
        self.slider_saturation = QSlider(Qt.Horizontal)
        self.slider_saturation.setRange(0, 200)
        self.slider_saturation.setValue(100)
        self.slider_saturation.setVisible(False)
        self.cmb_effect = QComboBox()
        self.cmb_effect.addItems(["Ninguno"])
        self.cmb_effect.setVisible(False)

        return panel

    def _build_center_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(5, 2, 5, 2)
        layout.setSpacing(2)

        top_bar = QHBoxLayout()
        self.lbl_rec = QLabel("● REC 00:00:00")
        self.lbl_rec.setStyleSheet("color: red; font-weight: bold;")
        top_bar.addWidget(self.lbl_rec)
        top_bar.addWidget(QLabel("60 FPS"))
        top_bar.addWidget(QLabel("5.2 Mbps"))
        top_bar.addStretch()
        # Botón tema con icono PNG
        from PySide6.QtCore import QSize
        self.btn_theme = QPushButton()
        theme_icon = os.path.join(self._icons_path, "tema_claro.png")
        if os.path.exists(theme_icon):
            self.btn_theme.setIcon(QIcon(theme_icon))
            self.btn_theme.setIconSize(QSize(20, 20))
        else:
            self.btn_theme.setText("☀️")
        self.btn_theme.setFixedSize(28, 28)
        self.btn_theme.setToolTip("Cambiar tema")
        self.btn_theme.clicked.connect(self._toggle_theme)
        top_bar.addWidget(self.btn_theme)
        # Botón configuración de salida
        self.btn_config = QPushButton()
        config_icon = os.path.join(os.path.dirname(__file__), "icons", "config", "config.png")
        if os.path.exists(config_icon):
            self.btn_config.setIcon(QIcon(config_icon))
            self.btn_config.setIconSize(QSize(20, 20))
        else:
            self.btn_config.setText("⚙")
        self.btn_config.setFixedSize(28, 28)
        self.btn_config.setToolTip("Configurar pantalla de salida")
        self.btn_config.clicked.connect(self._config_output_screen)
        top_bar.addWidget(self.btn_config)
        layout.addLayout(top_bar)

        # Splitter vertical: previews arriba, pestañas abajo
        center_splitter = QSplitter(Qt.Vertical)

        # Widget superior (previews + botón vivo)
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(2)

        # Botón enviar al vivo
        focus_row = QHBoxLayout()
        btn_send_live = QPushButton(" ENVIAR AL VIVO")
        pre_icons = os.path.join(os.path.dirname(__file__), "icons", "pre")
        btn_send_live.setIcon(QIcon(os.path.join(pre_icons, "enviar_vivo.png")))
        btn_send_live.setIconSize(self._icon_size())
        btn_send_live.clicked.connect(self._send_focused_to_live)
        focus_row.addWidget(btn_send_live)
        focus_row.addStretch()
        top_layout.addLayout(focus_row)

        # Dos pre-escuchas
        previews = QHBoxLayout()

        # Pre-escucha A
        box_a = QVBoxLayout()
        box_a.setSpacing(2)
        self.preview_a = QLabel("A")
        self.preview_a.setFont(QFont("Arial", 120, QFont.Bold))
        self.preview_a.setMinimumSize(200, 120)
        self.preview_a.setAlignment(Qt.AlignCenter)
        self.preview_a.setScaledContents(False)
        self.preview_a.setStyleSheet(
            "background-color: #1a1a2e; color: #555555; border: 3px solid #1565c0; border-radius: 8px;"
        )
        box_a.addWidget(self.preview_a, 1)
        self.preview_a.mousePressEvent = lambda e: self._set_focus_a()
        self.preview_a.setAcceptDrops(True)
        self.preview_a.dragEnterEvent = lambda e: e.acceptProposedAction() if e.mimeData().hasUrls() else None
        self.preview_a.dropEvent = lambda e: self._drop_on_preview(e, "A")
        # Audio indicator A
        audio_a_row = QHBoxLayout()
        self.lbl_audio_icon_a = QLabel("🔊")
        self.lbl_audio_icon_a.setFixedWidth(20)
        self.lbl_audio_icon_a.setStyleSheet("font-size: 14px;")
        self.lbl_audio_icon_a.setVisible(False)
        audio_a_row.addWidget(self.lbl_audio_icon_a)
        self.lbl_audio_name_a = QLabel("")
        self.lbl_audio_name_a.setStyleSheet("font-size: 10px; color: #1565c0;")
        audio_a_row.addWidget(self.lbl_audio_name_a, 1)
        self.lbl_audio_time_a = QLabel("")
        self.lbl_audio_time_a.setStyleSheet("font-size: 10px; color: #666;")
        audio_a_row.addWidget(self.lbl_audio_time_a)
        box_a.addLayout(audio_a_row)
        self.progress_a = QProgressBar()
        self.progress_a.setRange(0, 100)
        self.progress_a.setValue(0)
        self.progress_a.setFixedHeight(6)
        self.progress_a.setTextVisible(False)
        self.progress_a.setStyleSheet("""
            QProgressBar { background: #2a2a4e; border-radius: 3px; }
            QProgressBar::chunk { background: #1565c0; border-radius: 3px; }
        """)
        self.progress_a.setVisible(False)
        box_a.addWidget(self.progress_a)
        previews.addLayout(box_a)

        # Pre-escucha B
        box_b = QVBoxLayout()
        box_b.setSpacing(2)
        self.preview_b = QLabel("B")
        self.preview_b.setFont(QFont("Arial", 120, QFont.Bold))
        self.preview_b.setMinimumSize(200, 120)
        self.preview_b.setAlignment(Qt.AlignCenter)
        self.preview_b.setScaledContents(False)
        self.preview_b.setStyleSheet(
            "background-color: #1a1a2e; color: #555555; border: 2px solid #455a64; border-radius: 8px;"
        )
        box_b.addWidget(self.preview_b, 1)
        self.preview_b.mousePressEvent = lambda e: self._set_focus_b()
        self.preview_b.setAcceptDrops(True)
        self.preview_b.dragEnterEvent = lambda e: e.acceptProposedAction() if e.mimeData().hasUrls() else None
        self.preview_b.dropEvent = lambda e: self._drop_on_preview(e, "B")
        # Audio indicator B
        audio_b_row = QHBoxLayout()
        self.lbl_audio_icon_b = QLabel("🔊")
        self.lbl_audio_icon_b.setFixedWidth(20)
        self.lbl_audio_icon_b.setStyleSheet("font-size: 14px;")
        self.lbl_audio_icon_b.setVisible(False)
        audio_b_row.addWidget(self.lbl_audio_icon_b)
        self.lbl_audio_name_b = QLabel("")
        self.lbl_audio_name_b.setStyleSheet("font-size: 10px; color: #1565c0;")
        audio_b_row.addWidget(self.lbl_audio_name_b, 1)
        self.lbl_audio_time_b = QLabel("")
        self.lbl_audio_time_b.setStyleSheet("font-size: 10px; color: #666;")
        audio_b_row.addWidget(self.lbl_audio_time_b)
        box_b.addLayout(audio_b_row)
        self.progress_b = QProgressBar()
        self.progress_b.setRange(0, 100)
        self.progress_b.setValue(0)
        self.progress_b.setFixedHeight(6)
        self.progress_b.setTextVisible(False)
        self.progress_b.setStyleSheet("""
            QProgressBar { background: #2a2a4e; border-radius: 3px; }
            QProgressBar::chunk { background: #1565c0; border-radius: 3px; }
        """)
        self.progress_b.setVisible(False)
        box_b.addWidget(self.progress_b)
        previews.addLayout(box_b)

        top_layout.addLayout(previews, 1)
        center_splitter.addWidget(top_widget)

        # Widget inferior (pestañas)
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)

        # --- PANEL INFERIOR CON PESTAÑAS ---
        self.bottom_tabs = QTabWidget()
        self.bottom_tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #d0d8e0; border-radius: 4px; padding: 6px; background: #ffffff; }
            QTabBar::tab { padding: 8px 20px; font-weight: bold; font-size: 12px; min-width: 120px; }
            QTabBar::tab:selected { background: #1565c0; color: white; border-radius: 4px 4px 0 0; }
            QTabBar::tab:!selected { background: #e8ecf0; color: #333; }
        """)

        # --- Tab 1: Escribir Zócalo ---
        tab_write = QWidget()
        tw_layout = QVBoxLayout(tab_write)
        tw_layout.setContentsMargins(10, 10, 10, 10)
        tw_layout.setSpacing(8)

        tw_layout.addWidget(QLabel("Texto del zócalo:"))
        self.txt_overlay = QTextEdit()
        self.txt_overlay.setPlaceholderText("Escribí el texto del zócalo aquí...\nPodés usar varias líneas.")
        self.txt_overlay.setMaximumHeight(70)
        self.txt_overlay.setStyleSheet(
            "background-color: #333333; border: 1px solid #4a4a4a; border-radius: 4px; padding: 6px; font-size: 13px; color: #ffffff;"
        )
        tw_layout.addWidget(self.txt_overlay)

        # Fuente
        font_row = QHBoxLayout()
        font_row.addWidget(QLabel("Fuente:"))
        self.cmb_font = QComboBox()
        self.cmb_font.setMaxVisibleItems(20)
        self.cmb_font.setMinimumWidth(200)
        self.cmb_font.setStyleSheet("QComboBox { min-height: 26px; font-size: 12px; }")
        self.cmb_font.addItems(QFontDatabase.families())
        idx = self.cmb_font.findText("Arial")
        if idx >= 0:
            self.cmb_font.setCurrentIndex(idx)
        font_row.addWidget(self.cmb_font, 1)
        tw_layout.addLayout(font_row)

        # Colores y muestra
        color_row = QHBoxLayout()
        color_row.addWidget(QLabel("Color texto:"))
        self.btn_text_color = QPushButton("  ")
        self.btn_text_color.setFixedSize(30, 26)
        self.btn_text_color.setStyleSheet("background-color: #ffffff; border: 1px solid #999; border-radius: 3px;")
        self.btn_text_color.clicked.connect(self._pick_text_color)
        color_row.addWidget(self.btn_text_color)
        color_row.addWidget(QLabel("Color fondo:"))
        self.btn_bg_color = QPushButton("  ")
        self.btn_bg_color.setFixedSize(30, 26)
        self.btn_bg_color.setStyleSheet("background-color: rgba(0,0,0,160); border: 1px solid #999; border-radius: 3px;")
        self.btn_bg_color.clicked.connect(self._pick_bg_color)
        color_row.addWidget(self.btn_bg_color)
        color_row.addStretch()

        # Muestra de texto
        self.lbl_text_preview = QLabel("Muestra")
        self.lbl_text_preview.setFixedHeight(32)
        self.lbl_text_preview.setAlignment(Qt.AlignCenter)
        self.lbl_text_preview.setStyleSheet(
            "background-color: rgba(0,0,0,160); color: #ffffff; border-radius: 4px; padding: 4px 12px; font-weight: bold;"
        )
        color_row.addWidget(self.lbl_text_preview)
        tw_layout.addLayout(color_row)

        # Conectar cambios para actualizar muestra
        self.cmb_font.currentTextChanged.connect(self._update_text_preview_label)
        self.txt_overlay.textChanged.connect(self._update_text_preview_label)

        # Controles numéricos
        nums_row = QHBoxLayout()
        nums_row.addWidget(QLabel("Tamaño:"))
        self.spn_font_size = QSpinBox()
        self.spn_font_size.setRange(8, 120)
        self.spn_font_size.setValue(22)
        self.spn_font_size.setSuffix(" px")
        self.spn_font_size.setFixedWidth(75)
        nums_row.addWidget(self.spn_font_size)
        nums_row.addWidget(QLabel("Altura:"))
        self.spn_height = QSpinBox()
        self.spn_height.setRange(0, 500)
        self.spn_height.setValue(20)
        self.spn_height.setSuffix(" px")
        self.spn_height.setFixedWidth(75)
        nums_row.addWidget(self.spn_height)
        nums_row.addWidget(QLabel("Interlineado:"))
        self.spn_line_spacing = QSpinBox()
        self.spn_line_spacing.setRange(0, 100)
        self.spn_line_spacing.setValue(4)
        self.spn_line_spacing.setSuffix(" px")
        self.spn_line_spacing.setFixedWidth(75)
        nums_row.addWidget(self.spn_line_spacing)
        nums_row.addWidget(QLabel("Posición:"))
        self.cmb_position = QComboBox()
        self.cmb_position.addItems(["Abajo", "Medio", "Arriba"])
        self.cmb_position.setFixedWidth(100)
        nums_row.addWidget(self.cmb_position)
        nums_row.addWidget(QLabel("Duración:"))
        self.spn_duration = QSpinBox()
        self.spn_duration.setRange(0, 300)
        self.spn_duration.setValue(0)
        self.spn_duration.setSuffix(" seg")
        self.spn_duration.setToolTip("0 = permanente (no se quita solo)")
        self.spn_duration.setFixedWidth(85)
        nums_row.addWidget(self.spn_duration)
        nums_row.addStretch()
        tw_layout.addLayout(nums_row)

        # Botones
        btn_row_ov = QHBoxLayout()
        btn_txt_prev = QPushButton(" Enviar a Pre")
        btn_txt_prev.setIcon(QIcon(os.path.join(os.path.dirname(__file__), "icons", "pre", "pre_a.png")))
        btn_txt_prev.setIconSize(self._icon_size())
        btn_txt_prev.clicked.connect(self._text_to_preview)
        btn_row_ov.addWidget(btn_txt_prev)
        btn_txt_live = QPushButton("→ Enviar al Vivo")
        btn_txt_live.clicked.connect(self._text_to_live)
        btn_row_ov.addWidget(btn_txt_live)
        self.chk_multi_overlay = QCheckBox("Multi zócalo")
        self.chk_multi_overlay.setToolTip("Activar para acumular varios zócalos en distintas posiciones")
        self.chk_multi_overlay.setStyleSheet("font-weight: bold; margin-left: 10px;")
        btn_row_ov.addWidget(self.chk_multi_overlay)
        btn_clear_overlays = QPushButton("✕ Limpiar")
        btn_clear_overlays.setStyleSheet("background-color: #666; color: white; padding: 6px 12px;")
        btn_clear_overlays.setToolTip("Quitar todos los zócalos activos")
        btn_clear_overlays.clicked.connect(self._clear_all_overlays)
        btn_row_ov.addWidget(btn_clear_overlays)
        btn_row_ov.addStretch()
        tw_layout.addLayout(btn_row_ov)

        tabs_icons = os.path.join(os.path.dirname(__file__), "icons", "tabs")
        self.bottom_tabs.addTab(tab_write, QIcon(os.path.join(tabs_icons, "zocalo.png")), "Zócalo")

        # --- Tab 2: Transiciones de Vivo ---
        tab_transitions = QWidget()
        tt_layout = QVBoxLayout(tab_transitions)
        tt_layout.setContentsMargins(10, 10, 10, 10)
        tt_layout.setSpacing(8)

        tt_layout.addWidget(QLabel("Transición al enviar al Vivo:"))

        # Tipo de transición
        tr_row = QHBoxLayout()
        tr_row.addWidget(QLabel("Efecto:"))
        self.cmb_transition = QComboBox()
        self.cmb_transition.addItems([
            "Corte (instantáneo)", "Fundido (fade)", "Deslizar izquierda",
            "Deslizar derecha", "Deslizar arriba", "Deslizar abajo",
            "Zoom in", "Zoom out", "Disolver",
            "Borrado pizarrón", "Burbujas", "Quemar imagen",
            "Pixelar", "Cortina horizontal", "Cortina vertical"
        ])
        self.cmb_transition.setStyleSheet("min-width: 160px;")
        tr_row.addWidget(self.cmb_transition)
        tr_row.addWidget(QLabel("Duración:"))
        self.spn_transition_dur = QSpinBox()
        self.spn_transition_dur.setRange(0, 10000)
        self.spn_transition_dur.setValue(2000)
        self.spn_transition_dur.setSuffix(" ms")
        self.spn_transition_dur.setFixedWidth(100)
        tr_row.addWidget(self.spn_transition_dur)
        tr_row.addStretch()
        tt_layout.addLayout(tr_row)

        # Controles de Fade In / Fade Out con sliders visuales
        fade_row = QHBoxLayout()
        # Fade In
        fade_in_col = QVBoxLayout()
        self.chk_fade_in = QCheckBox("Fade In")
        self.chk_fade_in.setChecked(True)
        fade_in_col.addWidget(self.chk_fade_in)
        self.slider_fade_in = QSlider(Qt.Horizontal)
        self.slider_fade_in.setRange(0, 100)
        self.slider_fade_in.setValue(50)
        self.slider_fade_in.setFixedHeight(20)
        self.slider_fade_in.setToolTip("Velocidad del Fade In (0=rápido, 100=lento)")
        fade_in_col.addWidget(self.slider_fade_in)
        self.lbl_fade_in = QLabel("50%")
        self.lbl_fade_in.setAlignment(Qt.AlignCenter)
        self.lbl_fade_in.setStyleSheet("font-size: 9px;")
        fade_in_col.addWidget(self.lbl_fade_in)
        self.slider_fade_in.valueChanged.connect(lambda v: self.lbl_fade_in.setText(f"{v}%"))
        fade_row.addLayout(fade_in_col)

        # Fade Out
        fade_out_col = QVBoxLayout()
        self.chk_fade_out = QCheckBox("Fade Out")
        self.chk_fade_out.setChecked(True)
        fade_out_col.addWidget(self.chk_fade_out)
        self.slider_fade_out = QSlider(Qt.Horizontal)
        self.slider_fade_out.setRange(0, 100)
        self.slider_fade_out.setValue(50)
        self.slider_fade_out.setFixedHeight(20)
        self.slider_fade_out.setToolTip("Velocidad del Fade Out (0=rápido, 100=lento)")
        fade_out_col.addWidget(self.slider_fade_out)
        self.lbl_fade_out = QLabel("50%")
        self.lbl_fade_out.setAlignment(Qt.AlignCenter)
        self.lbl_fade_out.setStyleSheet("font-size: 9px;")
        fade_out_col.addWidget(self.lbl_fade_out)
        self.slider_fade_out.valueChanged.connect(lambda v: self.lbl_fade_out.setText(f"{v}%"))
        fade_row.addLayout(fade_out_col)

        fade_row.addStretch()
        tt_layout.addLayout(fade_row)

        # Preview de transición
        self.lbl_transition_info = QLabel("Corte: cambio instantáneo sin animación")
        self.lbl_transition_info.setStyleSheet("color: #999; font-style: italic; font-size: 11px;")
        tt_layout.addWidget(self.lbl_transition_info)
        self.cmb_transition.currentTextChanged.connect(self._on_transition_changed)

        # Botón MEZCLAR
        btn_mix = QPushButton(" MEZCLAR AL VIVO")
        btn_mix.setIcon(QIcon(os.path.join(self._icons_path, "mezclar.png")))
        btn_mix.setIconSize(self._icon_size())
        btn_mix.clicked.connect(self._send_focused_to_live)
        tt_layout.addWidget(btn_mix)

        tt_layout.addStretch()

        self.bottom_tabs.addTab(tab_transitions, QIcon(os.path.join(tabs_icons, "transiciones.png")), "Transiciones")

        # --- Tab 3: Mezclador de Audio ---
        tab_mixer = QWidget()
        tm_layout = QHBoxLayout(tab_mixer)
        tm_layout.setContentsMargins(5, 4, 5, 4)
        tm_layout.setSpacing(8)
        icons_path = os.path.join(os.path.dirname(__file__), "icons")
        from PySide6.QtMultimedia import QMediaDevices
        audio_devices = QMediaDevices.audioOutputs()
        device_names = [d.description() for d in audio_devices]
        hover_style = "background-color: transparent; border: 1px solid transparent; border-radius: 4px; } QPushButton:hover { background-color: rgba(21,101,192,0.3); border: 1px solid #1565c0; border-radius: 4px;"
        self._build_audio_channels(tm_layout, icons_path, device_names, hover_style)
        self._build_sample_pad(tm_layout, icons_path)
        # Señales
        self.audio_mixer.channel_a.position_changed.connect(self._on_pos_a)
        self.audio_mixer.channel_a.duration_changed.connect(self._on_dur_a)
        self.audio_mixer.channel_b.position_changed.connect(self._on_pos_b)
        self.audio_mixer.channel_b.duration_changed.connect(self._on_dur_b)
        self.audio_mixer.channel_master.position_changed.connect(self._on_pos_m)
        self.audio_mixer.channel_master.duration_changed.connect(self._on_dur_m)
        self.audio_mixer.channel_a.playback_started.connect(self._on_playback_started)
        self.audio_mixer.channel_b.playback_started.connect(self._on_playback_started)
        self.audio_mixer.channel_master.playback_started.connect(self._on_playback_started)
        self._dur_a = self._dur_b = self._dur_m = self._audio_duration_ms = 0
        self._audio_devices = audio_devices
        self.bottom_tabs.addTab(tab_mixer, QIcon(os.path.join(tabs_icons, "audio.png")), "Audio")

        # --- Tab 4: Lista de Reproducción ---
        tab_playlist = QWidget()
        pl_layout = QVBoxLayout(tab_playlist)
        pl_layout.setContentsMargins(8, 6, 8, 6)
        pl_layout.setSpacing(4)

        # Botones
        pl_top = QHBoxLayout()
        btn_pl_add = QPushButton(" Agregar")
        btn_pl_add.setIcon(QIcon(os.path.join(self._icons_path, "agregar.png")))
        btn_pl_add.setIconSize(self._icon_size())
        btn_pl_add.setStyleSheet("")
        btn_pl_add.clicked.connect(self._playlist_add_files)
        pl_top.addWidget(btn_pl_add)
        btn_pl_del = QPushButton(" Quitar")
        btn_pl_del.setIcon(QIcon(os.path.join(self._icons_path, "delete.png")))
        btn_pl_del.setIconSize(self._icon_size())
        btn_pl_del.setStyleSheet("")
        btn_pl_del.clicked.connect(self._playlist_remove)
        pl_top.addWidget(btn_pl_del)
        btn_pl_play = QPushButton(" Reproducir")
        btn_pl_play.setIcon(QIcon(os.path.join(self._icons_path, "play.png")))
        btn_pl_play.setIconSize(self._icon_size())
        btn_pl_play.setStyleSheet("")
        btn_pl_play.clicked.connect(self._playlist_play)
        pl_top.addWidget(btn_pl_play)
        pl_top.addStretch()
        pl_top.addWidget(QLabel("Modo:"))
        self.cmb_sched_mode = QComboBox()
        self.cmb_sched_mode.addItems(["Ordenado", "Random"])
        pl_top.addWidget(self.cmb_sched_mode)
        btn_pl_save = QPushButton()
        btn_pl_save.setIcon(QIcon(os.path.join(self._icons_path, "guardar.png")))
        btn_pl_save.setIconSize(self._icon_size())
        btn_pl_save.setFixedSize(32, 28)
        btn_pl_save.setToolTip("Guardar lista .gbs")
        btn_pl_save.clicked.connect(self._save_schedule_list)
        pl_top.addWidget(btn_pl_save)
        btn_pl_load = QPushButton()
        btn_pl_load.setIcon(QIcon(os.path.join(self._icons_path, "cargar.png")))
        btn_pl_load.setIconSize(self._icon_size())
        btn_pl_load.setFixedSize(32, 28)
        btn_pl_load.setToolTip("Cargar lista .gbs")
        btn_pl_load.clicked.connect(self._load_schedule_list)
        pl_top.addWidget(btn_pl_load)
        pl_layout.addLayout(pl_top)

        # Lista
        self.playlist_widget = QListWidget()
        pl_layout.addWidget(self.playlist_widget, 1)

        self._scheduled_tasks = []
        self._sched_current_idx = 0

        self.bottom_tabs.addTab(tab_playlist, QIcon(os.path.join(tabs_icons, "playlist.png")), "Playlist")

        # --- Tab 5: Alertas ---
        tab_alert = QWidget()
        alert_layout = QVBoxLayout(tab_alert)
        alert_layout.setContentsMargins(10, 8, 10, 8)
        alert_layout.setSpacing(6)

        alert_layout.addWidget(QLabel("Texto de la alerta:"))
        self.txt_alert = QLineEdit()
        self.txt_alert.setPlaceholderText("Ej: ¡URGENTE! Atención...")
        self.txt_alert.setStyleSheet("font-size: 14px; padding: 8px;")
        alert_layout.addWidget(self.txt_alert)

        # Posición
        alert_opts = QHBoxLayout()
        alert_opts.addWidget(QLabel("Posición:"))
        self.cmb_alert_pos = QComboBox()
        self.cmb_alert_pos.addItems(["Arriba", "Medio", "Abajo"])
        alert_opts.addWidget(self.cmb_alert_pos)
        alert_opts.addWidget(QLabel("Duración:"))
        self.cmb_alert_dur = QComboBox()
        self.cmb_alert_dur.addItems(["5 seg", "10 seg", "15 seg", "20 seg", "25 seg", "30 seg", "35 seg", "40 seg", "45 seg", "50 seg"])
        self.cmb_alert_dur.setCurrentIndex(1)  # 10 seg default
        alert_opts.addWidget(self.cmb_alert_dur)
        alert_opts.addWidget(QLabel("Parpadeos:"))
        self.spn_alert_blinks = QSpinBox()
        self.spn_alert_blinks.setRange(0, 20)
        self.spn_alert_blinks.setValue(5)
        alert_opts.addWidget(self.spn_alert_blinks)
        alert_opts.addStretch()
        alert_layout.addLayout(alert_opts)

        # Botones
        alert_btns = QHBoxLayout()
        btn_alert_pre = QPushButton(" Alerta a Pre")
        btn_alert_pre.setIcon(QIcon(os.path.join(self._icons_path, "enviar_pre.png")))
        btn_alert_pre.setIconSize(self._icon_size())
        btn_alert_pre.clicked.connect(self._send_alert_to_preview)
        alert_btns.addWidget(btn_alert_pre)
        btn_alert_live = QPushButton(" Alerta al Vivo")
        btn_alert_live.setIcon(QIcon(os.path.join(self._icons_path, "live-1.png")))
        btn_alert_live.setIconSize(self._icon_size())
        btn_alert_live.clicked.connect(self._send_alert_to_live)
        alert_btns.addWidget(btn_alert_live)
        alert_btns.addStretch()
        alert_layout.addLayout(alert_btns)
        alert_layout.addStretch()

        # Timer para parpadeo
        self._alert_timer = QTimer(self)
        self._alert_timer.timeout.connect(self._alert_blink_tick)
        self._alert_blink_count = 0
        self._alert_blink_max = 0
        self._alert_visible = True
        self._alert_target = None

        self.bottom_tabs.addTab(tab_alert, "⚠️ Alerta")

        # --- Tab 6: Entradas de Audio ---
        tab_inputs = QWidget()
        inputs_layout = QVBoxLayout(tab_inputs)
        inputs_layout.setContentsMargins(10, 8, 10, 8)
        inputs_layout.setSpacing(6)

        inputs_layout.addWidget(QLabel("Entradas de Audio (Micrófono / Línea):"))

        # Obtener dispositivos de entrada
        from PySide6.QtMultimedia import QMediaDevices
        input_devices = QMediaDevices.audioInputs()
        input_names = [d.description() for d in input_devices]

        # Micrófono 1
        mic1_row = QHBoxLayout()
        mic1_row.addWidget(QLabel("Mic 1:"))
        self.cmb_mic1 = QComboBox()
        self.cmb_mic1.addItems(input_names if input_names else ["Sin dispositivo"])
        mic1_row.addWidget(self.cmb_mic1, 1)
        self.slider_mic1 = QSlider(Qt.Horizontal)
        self.slider_mic1.setRange(0, 100)
        self.slider_mic1.setValue(80)
        self.slider_mic1.setFixedWidth(120)
        mic1_row.addWidget(self.slider_mic1)
        self.lbl_mic1_vol = QLabel("80%")
        self.lbl_mic1_vol.setFixedWidth(35)
        mic1_row.addWidget(self.lbl_mic1_vol)
        self.slider_mic1.valueChanged.connect(lambda v: self.lbl_mic1_vol.setText(f"{v}%"))
        inputs_layout.addLayout(mic1_row)

        # Micrófono 2
        mic2_row = QHBoxLayout()
        mic2_row.addWidget(QLabel("Mic 2:"))
        self.cmb_mic2 = QComboBox()
        self.cmb_mic2.addItems(input_names if input_names else ["Sin dispositivo"])
        mic2_row.addWidget(self.cmb_mic2, 1)
        self.slider_mic2 = QSlider(Qt.Horizontal)
        self.slider_mic2.setRange(0, 100)
        self.slider_mic2.setValue(80)
        self.slider_mic2.setFixedWidth(120)
        mic2_row.addWidget(self.slider_mic2)
        self.lbl_mic2_vol = QLabel("80%")
        self.lbl_mic2_vol.setFixedWidth(35)
        mic2_row.addWidget(self.lbl_mic2_vol)
        self.slider_mic2.valueChanged.connect(lambda v: self.lbl_mic2_vol.setText(f"{v}%"))
        inputs_layout.addLayout(mic2_row)

        # Línea de entrada
        line_row = QHBoxLayout()
        line_row.addWidget(QLabel("Línea:"))
        self.cmb_line = QComboBox()
        self.cmb_line.addItems(input_names if input_names else ["Sin dispositivo"])
        line_row.addWidget(self.cmb_line, 1)
        self.slider_line = QSlider(Qt.Horizontal)
        self.slider_line.setRange(0, 100)
        self.slider_line.setValue(100)
        self.slider_line.setFixedWidth(120)
        line_row.addWidget(self.slider_line)
        self.lbl_line_vol = QLabel("100%")
        self.lbl_line_vol.setFixedWidth(35)
        line_row.addWidget(self.lbl_line_vol)
        self.slider_line.valueChanged.connect(lambda v: self.lbl_line_vol.setText(f"{v}%"))
        inputs_layout.addLayout(line_row)

        # Destino de entrada
        dest_row = QHBoxLayout()
        dest_row.addWidget(QLabel("Enviar entrada a:"))
        self.cmb_input_dest = QComboBox()
        self.cmb_input_dest.addItems(["Vivo (Master)", "Pre A", "Pre B", "Todos"])
        dest_row.addWidget(self.cmb_input_dest)
        dest_row.addStretch()
        inputs_layout.addLayout(dest_row)
        inputs_layout.addStretch()

        self.bottom_tabs.addTab(tab_inputs, "🎤 Entradas")

        bottom_layout.addWidget(self.bottom_tabs)
        center_splitter.addWidget(bottom_widget)
        center_splitter.setSizes([400, 300])
        layout.addWidget(center_splitter)

        return panel

    def _build_audio_channels(self, parent_layout, icons_path, device_names, hover_style):
        """Construye los 3 canales de audio"""
        ch_row = QHBoxLayout()
        ch_row.setSpacing(10)

        # --- Pre A ---
        col_a = QVBoxLayout(); col_a.setSpacing(2)
        self.led_a = QLabel("●"); self.led_a.setAlignment(Qt.AlignCenter); self.led_a.setStyleSheet("color:#4caf50;font-size:14px;")
        col_a.addWidget(self.led_a)
        col_a.addWidget(self._make_lbl("Pre A", "#4fc3f7"))
        a_mid = QHBoxLayout()
        # Transport a la izquierda
        a_transport = QVBoxLayout(); a_transport.setSpacing(2)
        a_transport.addLayout(self._make_transport(icons_path, hover_style, self.audio_mixer.channel_a))
        a_mid.addLayout(a_transport)
        # Slider más alto
        self.slider_vol_a = QSlider(Qt.Vertical); self.slider_vol_a.setRange(0,100); self.slider_vol_a.setValue(100); self.slider_vol_a.setFixedHeight(80)
        self.slider_vol_a.valueChanged.connect(self._on_vol_a_changed)
        a_mid.addWidget(self.slider_vol_a)
        # Botones mute/live sin fondo
        a_btns = QVBoxLayout(); a_btns.setSpacing(3)
        self.btn_mute_a = self._make_icon_btn(icons_path, "mixer/mute.png", "transparent", self._mute_a)
        a_btns.addWidget(self.btn_mute_a)
        a_btns.addWidget(self._make_icon_btn(icons_path, "mixer/live-1.png", "transparent", self._assign_a_to_master))
        a_mid.addLayout(a_btns)
        col_a.addLayout(a_mid)
        self.lbl_vol_a = QLabel("100%"); self.lbl_vol_a.setAlignment(Qt.AlignCenter); self.lbl_vol_a.setStyleSheet("font-size:9px;")
        col_a.addWidget(self.lbl_vol_a)
        self.progress_ch_a = self._make_progress_bar("#4fc3f7"); col_a.addWidget(self.progress_ch_a)
        self.lbl_time_a = QLabel("--:--"); self.lbl_time_a.setAlignment(Qt.AlignCenter); self.lbl_time_a.setStyleSheet("font-size:9px;color:#888;")
        col_a.addWidget(self.lbl_time_a)
        self.cmb_device_a = QComboBox(); self.cmb_device_a.addItems(device_names if device_names else ["Default"])
        self.cmb_device_a.setStyleSheet("font-size:8px;"); self.cmb_device_a.currentIndexChanged.connect(self._on_device_a_changed)
        col_a.addWidget(self.cmb_device_a)
        ch_row.addLayout(col_a)

        # --- Pre B ---
        col_b = QVBoxLayout(); col_b.setSpacing(2)
        self.led_b = QLabel("●"); self.led_b.setAlignment(Qt.AlignCenter); self.led_b.setStyleSheet("color:#4caf50;font-size:14px;")
        col_b.addWidget(self.led_b)
        col_b.addWidget(self._make_lbl("Pre B", "#4fc3f7"))
        b_mid = QHBoxLayout()
        b_transport = QVBoxLayout(); b_transport.setSpacing(2)
        b_transport.addLayout(self._make_transport(icons_path, hover_style, self.audio_mixer.channel_b))
        b_mid.addLayout(b_transport)
        self.slider_vol_b = QSlider(Qt.Vertical); self.slider_vol_b.setRange(0,100); self.slider_vol_b.setValue(100); self.slider_vol_b.setFixedHeight(80)
        self.slider_vol_b.valueChanged.connect(self._on_vol_b_changed)
        b_mid.addWidget(self.slider_vol_b)
        b_btns = QVBoxLayout(); b_btns.setSpacing(3)
        self.btn_mute_b = self._make_icon_btn(icons_path, "mixer/mute.png", "transparent", self._mute_b)
        b_btns.addWidget(self.btn_mute_b)
        b_btns.addWidget(self._make_icon_btn(icons_path, "mixer/live-1.png", "transparent", self._assign_b_to_master))
        b_mid.addLayout(b_btns)
        col_b.addLayout(b_mid)
        self.lbl_vol_b = QLabel("100%"); self.lbl_vol_b.setAlignment(Qt.AlignCenter); self.lbl_vol_b.setStyleSheet("font-size:9px;")
        col_b.addWidget(self.lbl_vol_b)
        self.progress_ch_b = self._make_progress_bar("#4fc3f7"); col_b.addWidget(self.progress_ch_b)
        self.lbl_time_b = QLabel("--:--"); self.lbl_time_b.setAlignment(Qt.AlignCenter); self.lbl_time_b.setStyleSheet("font-size:9px;color:#888;")
        col_b.addWidget(self.lbl_time_b)
        self.cmb_device_b = QComboBox(); self.cmb_device_b.addItems(device_names if device_names else ["Default"])
        self.cmb_device_b.setStyleSheet("font-size:8px;"); self.cmb_device_b.currentIndexChanged.connect(self._on_device_b_changed)
        col_b.addWidget(self.cmb_device_b)
        ch_row.addLayout(col_b)

        # --- Master ---
        col_m = QVBoxLayout(); col_m.setSpacing(2)
        self.led_master = QLabel("●"); self.led_master.setAlignment(Qt.AlignCenter); self.led_master.setStyleSheet("color:#e53935;font-size:14px;")
        col_m.addWidget(self.led_master)
        col_m.addWidget(self._make_lbl("MASTER", "#e53935"))
        m_mid = QHBoxLayout()
        m_transport = QVBoxLayout(); m_transport.setSpacing(2)
        m_transport.addLayout(self._make_transport(icons_path, hover_style, self.audio_mixer.channel_master))
        m_mid.addLayout(m_transport)
        self.slider_master_vol = QSlider(Qt.Vertical); self.slider_master_vol.setRange(0,100); self.slider_master_vol.setValue(100); self.slider_master_vol.setFixedHeight(80)
        self.slider_master_vol.valueChanged.connect(self._on_master_volume_changed)
        m_mid.addWidget(self.slider_master_vol)
        self.btn_mute_master = self._make_icon_btn(icons_path, "mixer/mute.png", "transparent", self._mute_master)
        m_mid.addWidget(self.btn_mute_master)
        col_m.addLayout(m_mid)
        self.lbl_master_vol = QLabel("100%"); self.lbl_master_vol.setAlignment(Qt.AlignCenter); self.lbl_master_vol.setStyleSheet("font-size:9px;")
        col_m.addWidget(self.lbl_master_vol)
        self.progress_ch_m = self._make_progress_bar("#e53935"); col_m.addWidget(self.progress_ch_m)
        self.lbl_time_m = QLabel("--:--"); self.lbl_time_m.setAlignment(Qt.AlignCenter); self.lbl_time_m.setStyleSheet("font-size:9px;color:#888;")
        col_m.addWidget(self.lbl_time_m)
        self.cmb_device_master = QComboBox(); self.cmb_device_master.addItems(device_names if device_names else ["Default"])
        self.cmb_device_master.setStyleSheet("font-size:8px;"); self.cmb_device_master.currentIndexChanged.connect(self._on_master_device_changed)
        col_m.addWidget(self.cmb_device_master)
        ch_row.addLayout(col_m)

        parent_layout.addLayout(ch_row, 2)

    def _build_sample_pad(self, parent_layout, icons_path):
        """Construye el panel de samples"""
        from PySide6.QtWidgets import QGridLayout
        sample_col = QVBoxLayout(); sample_col.setSpacing(4)
        lbl = QLabel("SAMPLES"); lbl.setAlignment(Qt.AlignCenter); lbl.setStyleSheet("font-weight:bold;font-size:13px; color: #4fc3f7; margin-top: 30px;")
        sample_col.addWidget(lbl)
        grid = QGridLayout(); grid.setSpacing(2)
        colors = ["#e53935","#ff9800","#4caf50","#1565c0","#9c27b0","#00bcd4","#ffeb3b","#795548"]
        self.sample_buttons = []
        self.sample_files = [None]*8
        for i in range(8):
            btn = QPushButton(f"{i+1}")
            btn.setMinimumSize(80, 45)
            btn.setStyleSheet(f"background-color:{colors[i]};color:white;font-weight:bold;font-size:14px;border-radius:6px;")
            btn.clicked.connect(lambda c, idx=i: self._play_sample(idx))
            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            btn.customContextMenuRequested.connect(lambda p, idx=i: self._load_sample(idx))
            self.sample_buttons.append(btn)
            grid.addWidget(btn, i//2, i%2)
        sample_col.addLayout(grid)
        lbl2 = QLabel("Clic: play | Der: cargar"); lbl2.setStyleSheet("font-size:9px;color:#888;"); lbl2.setAlignment(Qt.AlignCenter)
        sample_col.addWidget(lbl2)
        sample_col.addStretch()
        parent_layout.addLayout(sample_col, 1)

        # Auto-cargar samples desde la carpeta src/ui/samples/
        self._auto_load_samples()

    def _make_lbl(self, text, color):
        l = QLabel(text); l.setAlignment(Qt.AlignCenter); l.setStyleSheet(f"font-weight:bold;font-size:9px;color:{color};")
        return l

    def _make_icon_btn(self, icons_path, icon_rel, bg_color, slot):
        btn = QPushButton()
        icon_name = os.path.basename(icon_rel)
        mixer_btns_path = os.path.join(os.path.dirname(__file__), "icons", "mixer_btns")
        if "mute" in icon_name:
            icon_path = os.path.join(mixer_btns_path, "mute_off.png")
        elif "live" in icon_name:
            icon_path = os.path.join(mixer_btns_path, "send_live.png")
        else:
            icon_path = os.path.join(self._icons_path, icon_name)
        if not os.path.exists(icon_path):
            icon_path = os.path.join(icons_path, icon_rel)
        btn.setIcon(QIcon(icon_path))
        btn.setIconSize(self._icon_size())
        btn.setFixedSize(32, 32)
        btn.setStyleSheet("background-color: transparent; border: 1px solid transparent; border-radius: 4px; } QPushButton:hover { border: 1px solid #4fc3f7; background-color: #3a3a3a; }")
        btn.clicked.connect(slot)
        return btn

    def _make_progress_bar(self, color):
        p = QProgressBar(); p.setRange(0,100); p.setFixedHeight(5); p.setTextVisible(False)
        p.setStyleSheet(f"QProgressBar{{background:#ddd;border-radius:2px;}}QProgressBar::chunk{{background:{color};border-radius:2px;}}")
        return p

    def _make_transport(self, icons_path, hover_style, channel):
        row = QHBoxLayout()
        for name, action in [("stop", channel.stop), ("pause", channel.pause), ("play", channel.resume)]:
            btn = QPushButton()
            icon_path = os.path.join(self._icons_path, f"{name}.png")
            if not os.path.exists(icon_path):
                icon_path = os.path.join(icons_path, "buttons", f"{name}.png")
            btn.setIcon(QIcon(icon_path))
            btn.setIconSize(self._icon_size())
            btn.setFixedSize(36, 36)
            btn.setStyleSheet("background-color: transparent; border: 1px solid transparent; border-radius: 4px; } QPushButton:hover { border: 1px solid #4fc3f7; background-color: #3a3a3a; }")
            btn.clicked.connect(action)
            row.addWidget(btn)
        return row

    def _build_right_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(5, 5, 5, 5)

        # VIVO chico arriba
        grp_live = QGroupBox("🔴 SALIDA EN VIVO")
        grp_live.setStyleSheet("QGroupBox { border: 1px solid #e53935; }")
        ll = QVBoxLayout(grp_live)
        self.live_label = QLabel("VIVO")
        self.live_label.setFont(QFont("Arial", 28, QFont.Bold))
        self.live_label.setMinimumSize(280, 160)
        self.live_label.setAlignment(Qt.AlignCenter)
        self.live_label.setScaledContents(True)
        self.live_label.setStyleSheet(
            "background-color: #1a1a2e; color: #aaa; border: 1px solid #ffffff; border-radius: 6px;"
        )
        ll.addWidget(self.live_label)
        btn_detach = QPushButton(" Desprender ventana")
        panel_icons = os.path.join(os.path.dirname(__file__), "icons", "panel_derecho")
        btn_detach.setIcon(QIcon(os.path.join(panel_icons, "desprender.png")))
        btn_detach.setIconSize(self._icon_size())
        btn_detach.clicked.connect(self._detach_live)
        ll.addWidget(btn_detach)
        btn_stop_screen = QPushButton(" Cerrar pantalla")
        btn_stop_screen.setIcon(QIcon(os.path.join(panel_icons, "cerrar_pantalla.png")))
        btn_stop_screen.setIconSize(self._icon_size())
        btn_stop_screen.clicked.connect(self._stop_output_screen)
        ll.addWidget(btn_stop_screen)
        layout.addWidget(grp_live)

        # Chat en vivo
        grp_chat = QGroupBox("CHAT EN VIVO")
        cl = QVBoxLayout(grp_chat)
        self.chat_list = QListWidget()
        self.chat_list.addItems([
            "PedroPérez: La calidad está increíble",
            "StreamerMod: ¡Bienvenidos!",
            "VideoKing: ¿Qué cámara usás?",
        ])
        cl.addWidget(self.chat_list)
        chat_input = QHBoxLayout()
        self.chat_entry = QLineEdit()
        self.chat_entry.setPlaceholderText("Escribe un mensaje...")
        chat_input.addWidget(self.chat_entry)
        btn_send = QPushButton("➤")
        chat_input.addWidget(btn_send)
        cl.addLayout(chat_input)
        layout.addWidget(grp_chat, 1)

        # Plataformas
        grp_platforms = QGroupBox("Plataformas Streaming")
        pl = QVBoxLayout(grp_platforms)
        for p in ["YouTube", "Facebook Live", "Twitch"]:
            row = QHBoxLayout()
            row.addWidget(QCheckBox(p))
            row.addWidget(QLineEdit())
            pl.addLayout(row)
        layout.addWidget(grp_platforms)

        self.btn_streaming = QPushButton(" Iniciar Streaming")
        self.btn_streaming.setIcon(QIcon(os.path.join(panel_icons, "streaming_off.png")))
        self.btn_streaming.setIconSize(self._icon_size())
        self.btn_streaming.clicked.connect(self._toggle_streaming)
        self._streaming_active = False
        layout.addWidget(self.btn_streaming)

        return panel

    def _icon_size(self):
        from PySide6.QtCore import QSize
        return QSize(24, 24)

    def _get_stylesheet(self):
        return self._dark_theme()

    def _dark_theme(self):
        return """
            QMainWindow { background-color: #1e1e1e; }
            QWidget { color: #cccccc; font-size: 11px; font-family: 'Segoe UI', sans-serif; }
            QGroupBox {
                border: 1px solid #3a3a3a; border-radius: 4px;
                margin-top: 8px; padding-top: 14px; font-weight: bold;
                background-color: #2b2b2b;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; color: #aaaaaa; }
            QListWidget { background-color: #2b2b2b; border: 1px solid #3a3a3a; border-radius: 3px; color: #cccccc; }
            QListWidget::item:selected { background-color: #3a3a3a; color: #ffffff; }
            QTreeView { background-color: #2b2b2b; border: 1px solid #3a3a3a; border-radius: 3px; color: #cccccc; }
            QTreeView::item:selected { background-color: #3a3a3a; }
            QTreeView::item:hover { background-color: #333333; }
            QSlider::groove:horizontal { height: 6px; background: #3a3a3a; border-radius: 3px; }
            QSlider::handle:horizontal { width: 16px; height: 16px; margin: -5px 0; background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.3, stop:0 #ffffff, stop:0.4 #cccccc, stop:1 #888888); border-radius: 8px; border: 1px solid #555555; }
            QSlider::sub-page:horizontal { background: #4fc3f7; border-radius: 3px; }
            QSlider::groove:vertical { width: 6px; background: #3a3a3a; border-radius: 3px; }
            QSlider::handle:vertical { height: 16px; width: 16px; margin: 0 -5px; background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.3, stop:0 #ffffff, stop:0.4 #cccccc, stop:1 #888888); border-radius: 8px; border: 1px solid #555555; }
            QSlider::add-page:vertical { background: #4fc3f7; border-radius: 3px; }
            QLineEdit { background-color: #333333; border: 1px solid #4a4a4a; border-radius: 3px; padding: 4px; color: #cccccc; }
            QLineEdit:focus { border: 1px solid #4fc3f7; }
            QComboBox { background-color: #333333; border: 1px solid #4a4a4a; border-radius: 3px; padding: 4px; color: #cccccc; }
            QComboBox::drop-down { border: none; width: 20px; }
            QComboBox::down-arrow { image: none; border-left: 4px solid transparent; border-right: 4px solid transparent; border-top: 5px solid #888888; }
            QComboBox QAbstractItemView { background-color: #2b2b2b; color: #cccccc; selection-background-color: #3a3a3a; border: 1px solid #4a4a4a; }
            QPushButton { background-color: #2a2a2a; border: 1px solid #4a4a4a; border-radius: 3px; padding: 5px 10px; color: #ffffff; }
            QPushButton:hover { background-color: #3a3a3a; border: 1px solid #4fc3f7; }
            QPushButton:pressed { background-color: #1a1a1a; border: 1px solid #ffffff; }
            QTabWidget::pane { border: 1px solid #3a3a3a; border-radius: 3px; background: #2b2b2b; }
            QTabWidget > QWidget { background: #2b2b2b; }
            QTabBar::tab { padding: 6px 16px; font-weight: bold; font-size: 11px; background: #333333; color: #999999; border: 1px solid #3a3a3a; border-bottom: none; border-radius: 3px 3px 0 0; margin-right: 1px; }
            QTabBar::tab:selected { background: #2b2b2b; color: #ffffff; border-bottom: 2px solid #4fc3f7; }
            QTabBar::tab:hover { background: #3a3a3a; color: #cccccc; }
            QProgressBar { background: #3a3a3a; border-radius: 3px; border: none; }
            QProgressBar::chunk { background: #4fc3f7; border-radius: 3px; }
            QTextEdit { background-color: #333333; border: 1px solid #4a4a4a; border-radius: 3px; padding: 5px; color: #cccccc; }
            QTextEdit:focus { border: 1px solid #4fc3f7; }
            QSpinBox { background-color: #333333; border: 1px solid #4a4a4a; border-radius: 3px; padding: 3px; color: #cccccc; }
            QSpinBox:focus { border: 1px solid #4fc3f7; }
            QCheckBox { color: #cccccc; }
            QCheckBox::indicator { width: 14px; height: 14px; border-radius: 3px; border: 1px solid #4a4a4a; background: #333333; }
            QCheckBox::indicator:checked { background: #4fc3f7; border: 1px solid #4fc3f7; }
            QLabel { color: #cccccc; }
            QSplitter::handle { background-color: #3a3a3a; width: 2px; }
            QScrollBar:vertical { background: #2b2b2b; width: 10px; border-radius: 5px; }
            QScrollBar::handle:vertical { background: #4a4a4a; border-radius: 5px; min-height: 20px; }
            QScrollBar::handle:vertical:hover { background: #5a5a5a; }
            QScrollBar:horizontal { background: #2b2b2b; height: 10px; border-radius: 5px; }
            QScrollBar::handle:horizontal { background: #4a4a4a; border-radius: 5px; min-width: 20px; }
            QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
            QMenuBar { background-color: #2b2b2b; color: #ffffff; border-bottom: 1px solid #3a3a3a; }
            QMenuBar::item { padding: 6px 12px; }
            QMenuBar::item:selected { background-color: #3a3a3a; }
            QMenu { background-color: #2b2b2b; color: #ffffff; border: 1px solid #3a3a3a; }
            QMenu::item { padding: 6px 24px; }
            QMenu::item:selected { background-color: #1565c0; }
            QMenu::separator { height: 1px; background: #3a3a3a; margin: 4px 8px; }
        """

    def _light_theme(self):
        return """
            QMainWindow { background-color: #f0f2f5; }
            QWidget { color: #1a2a3a; font-size: 12px; }
            QGroupBox {
                border: 1px solid #d0d8e0; border-radius: 6px;
                margin-top: 10px; padding-top: 15px; font-weight: bold;
                background-color: #ffffff;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; color: #333; }
            QListWidget { background-color: #ffffff; border: 1px solid #d0d8e0; border-radius: 4px; }
            QTreeView { background-color: #ffffff; border: 1px solid #d0d8e0; border-radius: 4px; }
            QSlider::groove:horizontal { height: 4px; background: #d0d8e0; border-radius: 2px; }
            QSlider::handle:horizontal { width: 14px; margin: -5px 0; background: #555; border-radius: 7px; }
            QSlider::groove:vertical { width: 6px; background: #d0d8e0; border-radius: 3px; }
            QSlider::handle:vertical { height: 14px; margin: 0 -4px; background: #555; border-radius: 7px; }
            QSlider::add-page:vertical { background: #1565c0; border-radius: 3px; }
            QSlider::sub-page:horizontal { background: #1565c0; border-radius: 2px; }
            QLineEdit { background-color: #ffffff; border: 1px solid #d0d8e0; border-radius: 4px; padding: 5px; color: #333; }
            QComboBox { background-color: #ffffff; border: 1px solid #d0d8e0; border-radius: 4px; padding: 4px; color: #333; }
            QPushButton { background-color: #ffffff; border: 1px solid #d0d8e0; border-radius: 4px; padding: 6px 12px; color: #333333; }
            QPushButton:hover { background-color: #f0f0f0; border: 1px solid #1565c0; }
            QPushButton:pressed { background-color: #e0e0e0; }
            QTabWidget::pane { border: 1px solid #d0d8e0; border-radius: 4px; background: #ffffff; }
            QTabWidget > QWidget { background: #ffffff; }
            QTabBar::tab { padding: 6px 16px; font-weight: bold; background: #e8ecf0; color: #555; border: 1px solid #d0d8e0; border-bottom: none; border-radius: 3px 3px 0 0; }
            QTabBar::tab:selected { background: #f5f5f5; color: #333; border-bottom: 2px solid #1565c0; }
            QTabBar::tab:hover { background: #dde3e8; }
            QProgressBar { background: #e0e0e0; border-radius: 3px; }
            QProgressBar::chunk { background: #1565c0; border-radius: 3px; }
            QTextEdit { background-color: #ffffff; border: 1px solid #d0d8e0; border-radius: 4px; padding: 6px; color: #333; }
            QSpinBox { background-color: #ffffff; border: 1px solid #d0d8e0; border-radius: 4px; padding: 3px; color: #333; }
            QMenuBar { background-color: #ffffff; color: #333; border-bottom: 1px solid #d0d8e0; }
            QMenuBar::item:selected { background-color: #e8ecf0; }
            QMenu { background-color: #ffffff; color: #333; border: 1px solid #d0d8e0; }
            QMenu::item:selected { background-color: #1565c0; color: white; }
            QCheckBox { color: #333; }
            QLabel { color: #333; }
            QSplitter::handle { background-color: #d0d8e0; }
        """

    def _toggle_theme(self):
        from PySide6.QtCore import QSize
        if self._dark_mode:
            self.setStyleSheet(self._light_theme())
            self._dark_mode = False
            # Cambiar icono a tema oscuro (luna)
            tema_icon = os.path.join(self._icons_path, "tema_oscuro.png")
            if os.path.exists(tema_icon):
                self.btn_theme.setIcon(QIcon(tema_icon))
                self.btn_theme.setIconSize(QSize(20, 20))
                self.btn_theme.setText("")
            else:
                self.btn_theme.setText("🌙")
            self.btn_theme.setToolTip("Cambiar a tema oscuro")
        else:
            self.setStyleSheet(self._dark_theme())
            self._dark_mode = True
            # Cambiar icono a tema claro (sol)
            tema_icon = os.path.join(self._icons_path, "tema_claro.png")
            if os.path.exists(tema_icon):
                self.btn_theme.setIcon(QIcon(tema_icon))
                self.btn_theme.setIconSize(QSize(20, 20))
                self.btn_theme.setText("")
            else:
                self.btn_theme.setText("☀️")
            self.btn_theme.setToolTip("Cambiar a tema claro")


class LiveWindow(QWidget):
    """Ventana desprendida para ver el vivo en grande"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GBSturio - VIVO")
        self.setMinimumSize(640, 480)
        self.setStyleSheet("background-color: black;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel("VIVO")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("background-color: black; color: white;")
        self.label.setScaledContents(True)
        layout.addWidget(self.label)

    def update_frame(self, pixmap):
        self.label.setPixmap(pixmap)
