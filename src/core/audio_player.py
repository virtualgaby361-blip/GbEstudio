import os
from PySide6.QtCore import QUrl, Signal, QObject
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaDevices


class AudioChannel(QObject):
    """Un canal de audio independiente con su propio player y dispositivo de salida"""
    position_changed = Signal(int)
    duration_changed = Signal(int)
    playback_started = Signal(str)

    def __init__(self, name="", parent=None):
        super().__init__(parent)
        self.name = name
        self.player = QMediaPlayer(parent)
        self.audio_output = QAudioOutput(parent)
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(1.0)
        self.current_file = ""
        self._muted = False
        self._volume = 1.0

        self.player.positionChanged.connect(self.position_changed.emit)
        self.player.durationChanged.connect(self.duration_changed.emit)

    def play(self, file_path):
        self.player.stop()
        self.current_file = file_path
        self.player.setSource(QUrl.fromLocalFile(file_path))
        self.player.play()
        name = os.path.basename(file_path)
        self.playback_started.emit(name)

    def stop(self):
        self.player.stop()
        self.current_file = ""

    def set_volume(self, volume):
        """Volumen de 0.0 a 1.0"""
        self._volume = volume
        if not self._muted:
            self.audio_output.setVolume(volume)

    def mute(self, muted):
        self._muted = muted
        if muted:
            self.audio_output.setVolume(0.0)
        else:
            self.audio_output.setVolume(self._volume)

    def is_muted(self):
        return self._muted

    def is_playing(self):
        return self.player.playbackState() == QMediaPlayer.PlayingState

    def pause(self):
        self.player.pause()

    def resume(self):
        self.player.play()

    def set_device(self, device):
        """Cambia el dispositivo de salida de audio"""
        self.audio_output.setDevice(device)

    def seek(self, position_ms):
        self.player.setPosition(position_ms)


class AudioMixer(QObject):
    """Mezclador con 3 canales independientes: Pre A, Pre B, Master"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.channel_a = AudioChannel("Pre A", parent)
        self.channel_b = AudioChannel("Pre B", parent)
        self.channel_master = AudioChannel("Master", parent)
        self.channel_samples = AudioChannel("Samples", parent)

    def get_channel(self, target):
        if target == "A":
            return self.channel_a
        elif target == "B":
            return self.channel_b
        else:
            return self.channel_master

    def stop_all(self):
        self.channel_a.stop()
        self.channel_b.stop()
        self.channel_master.stop()
        self.channel_samples.stop()

    @staticmethod
    def get_audio_devices():
        return QMediaDevices.audioOutputs()
