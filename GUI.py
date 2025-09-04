# t12_updated.py
import sys
import threading
import time
import os
from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QProgressBar, QFrame,
    QPushButton, QHBoxLayout, QTabWidget, QListWidget, QListWidgetItem,
    QStyle, QStyleFactory
)
from PyQt5.QtGui import QFont, QPixmap, QWindow, QGuiApplication, QIcon, QPalette, QColor
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QProcess, QTimer

# Optional imports / platform-specific
try:
    import serial
except Exception:
    serial = None

import subprocess
import psutil

# pycaw for Windows volume control
try:
    from ctypes import POINTER, cast
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    pycaw_available = True
except Exception:
    pycaw_available = False

# pywin32 for window embedding (Windows)
try:
    import win32gui
    import win32process
    win32_available = True
except Exception:
    win32_available = False

# Import del monitor della batteria (se presente)
try:
    from can_monitor import create_battery_monitor
except Exception:
    create_battery_monitor = None

# Variabile per la modalità test (0 = normale, 1 = testing grafico)
test = 1  # Imposta a 1 per testing grafico senza connessioni reali

# Inizializzazione della comunicazione seriale con modulo esterno per trip (solo se non in modalità test)
ser = None
if test == 0 and serial is not None:
    try:
        ser = serial.Serial('COM201', 9600, timeout=1)
    except Exception as e:
        print(f"Errore connessione seriale: {e}")
        ser = None

# Variabili globali per la gestione del viaggio e autonomia
inizializzato = 0
inizio = 100
media = 0
last = 0
trip_km = 0.0
start_time = None

# Creazione e avvio del monitor della batteria (solo se non in modalità test)
monitorBAT = None
if test == 0 and create_battery_monitor is not None:
    try:
        monitorBAT = create_battery_monitor()
        monitorBAT.start()
    except Exception as e:
        print(f"Errore inizializzazione monitor batteria: {e}")
        monitorBAT = None


def algokm(attuale):
    """
    Calcola l'autonomia residua basata sul consumo della batteria e le statistiche del viaggio.
    """
    global inizializzato, inizio, media, trip_km, start_time

    if test == 1:
        time.sleep(1)
        import random
        trip_km = random.uniform(5.0, 50.0)
        media = random.uniform(30.0, 80.0)
        if inizializzato == 0 and attuale > 0:
            inizializzato = 1
            inizio = attuale
            start_time = datetime.now()
        percento = inizio - attuale
        if percento > 1:
            kmrim = (trip_km / percento) * attuale
        else:
            kmrim = 0.0
        return round(kmrim, 1)

    trip_distance_km = 0
    trip_avg_speed_kmh = 0
    trip_speed_kmh = 0

    if (inizializzato == 0) and attuale > 0:
        if ser is not None:
            try:
                ser.write(b'R')
            except Exception:
                pass
        inizializzato = 1
        inizio = attuale
        start_time = datetime.now()

    time.sleep(1)

    if ser is not None:
        try:
            line = ser.readline().decode().strip()
            if line.startswith("STATS"):
                parts = line.split(',')
                trip_distance_km = float(parts[2]) / 1000
                trip_avg_speed_kmh = float(parts[4]) * 3.6
                trip_km = trip_distance_km
                trip_speed_kmh = trip_avg_speed_kmh
        except Exception:
            pass

    media = trip_speed_kmh
    percento = inizio - attuale
    if percento > 1:
        kmrim = (trip_km / percento) * attuale
    else:
        kmrim = 0.0

    return round(kmrim, 1)


class DataSignals(QObject):
    updated = pyqtSignal()


class TripTab(QWidget):
    """Tab per visualizzare le informazioni sul viaggio e l'autonomia"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.init_ui()

    def init_ui(self):
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(15)
        
        left_column = QVBoxLayout()
        left_column.setContentsMargins(0, 0, 0, 0)
        left_column.setSpacing(10)

        battery_frame = QFrame()
        battery_frame.setFixedWidth(100)
        battery_frame.setObjectName("batteryFrame")
        battery_layout = QVBoxLayout(battery_frame)
        battery_layout.setContentsMargins(5, 5, 5, 5)
        battery_layout.setSpacing(10)

        battery_label = QLabel("BATTERIA")
        battery_label.setFont(QFont("Segoe UI", 12, QFont.Bold))
        battery_label.setAlignment(Qt.AlignCenter)
        battery_label.setObjectName("batteryLabel")

        self.battery_progress = QProgressBar()
        self.battery_progress.setOrientation(Qt.Vertical)
        self.battery_progress.setTextVisible(True)
        self.battery_progress.setFixedSize(70, 250)
        self.battery_progress.setFormat("%p%")
        self.battery_progress.setObjectName("batteryProgress")

        battery_layout.addWidget(battery_label)
        battery_layout.addWidget(self.battery_progress, 0, Qt.AlignCenter)
        battery_layout.addStretch()

        left_column.addWidget(battery_frame)
        left_column.addStretch()

        center_column = QVBoxLayout()
        center_column.setContentsMargins(0, 0, 0, 0)
        center_column.setSpacing(15)

        title = QLabel("BLUECAR MONITOR")
        title.setFont(QFont("Segoe UI", 28, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setObjectName("mainTitle")

        car_image = QLabel()
        if test == 1:
            car_image.setText("IMMAGINE BLUECAR\n(Modalità Test)")
            car_image.setAlignment(Qt.AlignCenter)
            car_image.setFixedSize(280, 150)
            car_image.setObjectName("carImagePlaceholder")
        else:
            try:
                pixmap = QPixmap("bluecar_icon.png").scaled(280, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                car_image.setPixmap(pixmap)
                car_image.setAlignment(Qt.AlignCenter)
                car_image.setObjectName("carImage")
            except Exception:
                car_image.setText("IMMAGINE BLUECAR")
                car_image.setObjectName("carImagePlaceholder")

        center_column.addWidget(title)
        center_column.addWidget(car_image)
        center_column.addStretch()

        right_column = QVBoxLayout()
        right_column.setContentsMargins(0, 0, 0, 0)
        right_column.setSpacing(15)

        range_frame = QFrame()
        range_frame.setObjectName("rangeFrame")
        range_layout = QVBoxLayout(range_frame)
        range_layout.setContentsMargins(10, 10, 10, 10)
        range_layout.setSpacing(10)

        range_title = QLabel("AUTONOMIA")
        range_title.setFont(QFont("Segoe UI", 18, QFont.Bold))
        range_title.setAlignment(Qt.AlignCenter)
        range_title.setObjectName("rangeTitle")

        self.range_km = QLabel("-- km")
        self.range_km.setFont(QFont("Segoe UI", 28, QFont.Bold))
        self.range_km.setAlignment(Qt.AlignCenter)
        self.range_km.setObjectName("rangeValue")

        range_wltp_label = QLabel("WLTP: -- km")
        range_wltp_label.setFont(QFont("Segoe UI", 14))
        range_wltp_label.setAlignment(Qt.AlignCenter)
        range_wltp_label.setObjectName("wltpLabel")

        range_calc_label = QLabel("Calcolato: -- km")
        range_calc_label.setFont(QFont("Segoe UI", 14, QFont.Bold))
        range_calc_label.setAlignment(Qt.AlignCenter)
        range_calc_label.setObjectName("calcLabel")

        range_layout.addWidget(range_title)
        range_layout.addWidget(self.range_km)
        range_layout.addWidget(range_wltp_label)
        range_layout.addWidget(range_calc_label)
        range_layout.addStretch()

        info_frame = QFrame()
        info_frame.setObjectName("infoFrame")
        info_layout = QVBoxLayout(info_frame)
        info_layout.setContentsMargins(10, 10, 10, 10)
        info_layout.setSpacing(10)

        info_title = QLabel("INFORMAZIONI VIAGGIO")
        info_title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        info_title.setAlignment(Qt.AlignCenter)
        info_title.setObjectName("infoTitle")

        self.info_text = QLabel()
        self.info_text.setFont(QFont("Segoe UI", 14))
        self.info_text.setAlignment(Qt.AlignLeft)
        self.info_text.setWordWrap(True)
        self.info_text.setObjectName("infoText")

        info_layout.addWidget(info_title)
        info_layout.addWidget(self.info_text)
        info_layout.addStretch()

        reset_button = QPushButton("RESET TRIP")
        reset_button.setFixedHeight(50)
        reset_button.setFont(QFont("Segoe UI", 14, QFont.Bold))
        reset_button.setObjectName("resetButton")
        reset_button.clicked.connect(self.reset_trip)

        right_column.addWidget(range_frame)
        right_column.addWidget(info_frame)
        right_column.addWidget(reset_button, 0, Qt.AlignCenter)
        right_column.addStretch()

        main_layout.addLayout(left_column)
        main_layout.addLayout(center_column)
        main_layout.addLayout(right_column)

        self.setLayout(main_layout)

    def refresh_ui(self, battery_value, est_range_km, wltp_range_km, avg_speed, trip_km):
        self.range_km.setText(f"{est_range_km:.1f} km")
        self.battery_progress.setValue(int(battery_value))
        self.info_text.setText(f"Velocità media: {avg_speed:.1f} km/h\nTrip km: {trip_km:.2f} km\nWLTP: {int((battery_value/100)*wltp_range_km)} km")

    @staticmethod
    def get_battery_color(value):
        if value > 70:
            return "#00cc66"
        elif value > 30:
            return "#ffcc00"
        return "#ff3300"

    def reset_trip(self):
        global inizializzato, inizio, trip_km, start_time
        end_time = datetime.now()
        if start_time is not None and trip_km > 0:
            percent_consumed = inizio - self.parent.battery_value
            self.log_trip(start_time, end_time, trip_km, percent_consumed)
        inizializzato = 0
        trip_km = 0.0
        self.parent.trip_km = 0.0
        self.parent.est_range_km = 0
        start_time = None
        self.refresh_ui(self.parent.battery_value, self.parent.est_range_km,
                        self.parent.wltp_range_km, self.parent.avg_speed, self.parent.trip_km)

    def log_trip(self, start, end, km, percent):
        os.makedirs("logtrip", exist_ok=True)
        with open("logtrip/oldtrip.txt", "a") as f:
            line = f"{start.strftime('%Y-%m-%d %H:%M')} | {end.strftime('%Y-%m-%d %H:%M')} | {km:.2f} km | {percent:.1f}% consumati\n"
            f.write(line)


def rileva_dispositivi():
    """
    Chiama bluetoothc.exe dispositivi e restituisce lista di (nome, id).
    Legge output iniziale con timeout per evitare blocco.
    """
    dispositivi_rilevati = []
    try:
        proc = subprocess.Popen(
            ["bluetoothc.exe", "dispositivi"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        try:
            output, error = proc.communicate(timeout=1)
        except subprocess.TimeoutExpired:
            proc.kill()
            output, error = proc.communicate()

        for riga in output.splitlines():
            riga = riga.strip()
            if not riga or riga.startswith("Ricerca dispositivi"):
                continue
            if '@' in riga:
                nome, dev_id = riga.split('@', 1)
                dispositivi_rilevati.append((nome, dev_id))
    except FileNotFoundError:
        print("⚠️ bluetoothc.exe non trovato!")
    except Exception as e:
        print("Errore rileva_dispositivi:", e)
    return dispositivi_rilevati


class MediaTab(QWidget):
    """Tab per la gestione dei media e del Bluetooth"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.connected_process = None
        self.volume = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        title = QLabel("MEDIA E BLUETOOTH")
        title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setObjectName("mediaTitle")
        layout.addWidget(title)

        devices_label = QLabel("Dispositivi Bluetooth disponibili:")
        devices_label.setFont(QFont("Segoe UI", 16))
        devices_label.setObjectName("devicesLabel")
        layout.addWidget(devices_label)

        self.devices_list = QListWidget()
        self.devices_list.setFont(QFont("Segoe UI", 14))
        self.devices_list.setObjectName("devicesList")
        layout.addWidget(self.devices_list)

        refresh_btn = QPushButton("AGGIORNA DISPOSITIVI")
        refresh_btn.setFixedHeight(60)
        refresh_btn.setFont(QFont("Segoe UI", 16, QFont.Bold))
        refresh_btn.setObjectName("refreshButton")
        refresh_btn.clicked.connect(self.refresh_devices)
        layout.addWidget(refresh_btn)

        bt_buttons_layout = QHBoxLayout()
        bt_buttons_layout.setSpacing(15)
        self.connect_btn = QPushButton("CONNETTI")
        self.disconnect_btn = QPushButton("DISCONNETTI")
        for btn in [self.connect_btn, self.disconnect_btn]:
            btn.setFixedHeight(60)
            btn.setFont(QFont("Segoe UI", 16, QFont.Bold))
            btn.setObjectName("btButton")
        bt_buttons_layout.addWidget(self.connect_btn)
        bt_buttons_layout.addWidget(self.disconnect_btn)
        layout.addLayout(bt_buttons_layout)

        self.connect_btn.clicked.connect(self.connect_device)
        self.disconnect_btn.clicked.connect(self.disconnect_device)

        # Volume UI
        volume_label = QLabel("VOLUME")
        volume_label.setFont(QFont("Segoe UI", 20, QFont.Bold))
        volume_label.setAlignment(Qt.AlignCenter)
        volume_label.setObjectName("volumeTitle")
        layout.addWidget(volume_label)

        volume_layout = QHBoxLayout()
        volume_layout.setSpacing(30)
        self.volume_down = QPushButton("-")
        self.volume_up = QPushButton("+")
        for btn in [self.volume_down, self.volume_up]:
            btn.setFixedSize(100, 100)
            btn.setFont(QFont("Segoe UI", 32, QFont.Bold))
            btn.setObjectName("volumeButton")
        volume_layout.addStretch()
        volume_layout.addWidget(self.volume_down)
        volume_layout.addWidget(self.volume_up)
        volume_layout.addStretch()
        layout.addLayout(volume_layout)

        self.setLayout(layout)

        # Setup
        self.refresh_devices()
        self.init_volume_control()
        self.volume_down.clicked.connect(self.decrease_volume)
        self.volume_up.clicked.connect(self.increase_volume)

    def refresh_devices(self):
        self.devices_list.clear()
        dispositivi = rileva_dispositivi()
        for nome, dev_id in dispositivi:
            item = QListWidgetItem(nome)
            item.setFont(QFont("Segoe UI", 14))
            item.setData(Qt.UserRole, dev_id)
            self.devices_list.addItem(item)

    def connect_device(self):
        item = self.devices_list.currentItem()
        if item:
            dev_id = item.data(Qt.UserRole)
            try:
                # avvia il processo e lo mantiene aperto (così la connessione rimane)
                proc = subprocess.Popen(
                    ["bluetoothc.exe", "dispositivi", "connetti", dev_id]
                )
                self.connected_process = proc
                print(f"✅ Connesso a {item.text()} ({dev_id})")
            except Exception as e:
                print("Errore nella connessione:", e)

    def disconnect_device(self):
        # uccidi tutti i processi bluetoothc.exe
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if proc.info['name'] and proc.info['name'].lower() == "bluetoothc.exe":
                    proc.kill()
            except Exception:
                pass
        self.connected_process = None
        print("💥 Disconnesso (processo bluetoothc.exe chiuso)")

    def init_volume_control(self):
        if not pycaw_available:
            print("pycaw non disponibile: controllo volume disabilitato")
            self.volume = None
            return
        try:
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            self.volume = cast(interface, POINTER(IAudioEndpointVolume))
        except Exception as e:
            print("Impossibile inizializzare controllo volume:", e)
            self.volume = None

    def increase_volume(self):
        if self.volume is None:
            return
        try:
            current = self.volume.GetMasterVolumeLevelScalar()
            self.volume.SetMasterVolumeLevelScalar(min(current + 0.05, 1.0), None)
        except Exception:
            pass

    def decrease_volume(self):
        if self.volume is None:
            return
        try:
            current = self.volume.GetMasterVolumeLevelScalar()
            self.volume.SetMasterVolumeLevelScalar(max(current - 0.05, 0.0), None)
        except Exception:
            pass


class MapTab(QWidget):
    """Tab per la visualizzazione della mappa di navigazione (tentativo di embed su Windows)"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.process = None
        self.container = None
        self.placeholder = None
        self.init_ui()

    def init_ui(self):
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(15, 15, 15, 15)
        self.layout.setSpacing(15)

        title = QLabel("MAPPA DI NAVIGAZIONE")
        title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setObjectName("mapTitle")
        self.layout.addWidget(title)

        self.placeholder = QLabel("Integrazione Mappa (app.exe)")
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.placeholder.setObjectName("mapPlaceholder")
        self.layout.addWidget(self.placeholder)

        # pulsante per aprire / riavviare la mappa dentro la tab
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(15)
        self.open_map_btn = QPushButton("APRI MAPPA INTERNA")
        self.open_map_btn.setFixedHeight(60)
        self.open_map_btn.setFont(QFont("Segoe UI", 16, QFont.Bold))
        self.open_map_btn.setObjectName("mapButton")
        self.open_map_btn.clicked.connect(self.start_map)
        btn_layout.addWidget(self.open_map_btn)

        self.close_map_btn = QPushButton("CHIUDI MAPPA")
        self.close_map_btn.setFixedHeight(60)
        self.close_map_btn.setFont(QFont("Segoe UI", 16, QFont.Bold))
        self.close_map_btn.setObjectName("mapButton")
        self.close_map_btn.clicked.connect(self.close_map)
        btn_layout.addWidget(self.close_map_btn)

        self.layout.addLayout(btn_layout)
        self.setLayout(self.layout)

        # Se in test -> non avvia la mappa
        if test == 0:
            # puoi avviarla automaticamente se vuoi
            pass

    def start_map(self):
        """Avvia avit.exe e prova ad embedderlo nella tab (solo Windows)."""
        exe_path = os.path.join(".", "avit12", "avit.exe")
        if not os.path.exists(exe_path):
            # tenta percorso alternativo relativo
            exe_path = os.path.join(".", "avit.exe")
        if not os.path.exists(exe_path):
            self.placeholder.setText("avit.exe non trovato nel percorso atteso.")
            return

        # Se pywin32 non disponibile -> fallback: apri esternamente e mostra info
        if not win32_available:
            try:
                subprocess.Popen([exe_path])
                self.placeholder.setText("avvio mappa esternamente (pywin32 non installato).")
            except Exception as e:
                self.placeholder.setText(f"Errore avvio mappa esterna: {e}")
            return

        # Use QProcess to start so we can get PID
        try:
            if self.process is not None:
                try:
                    # se già in esecuzione, uccidi e riavvia
                    pid_running = int(self.process.processId()) if self.process.processId() else None
                    if pid_running:
                        for p in psutil.process_iter(['pid', 'name']):
                            if p.info['pid'] == pid_running:
                                p.kill()
                except Exception:
                    pass

            self.process = QProcess(self)
            self.process.started.connect(self._on_process_started)
            self.process.start(exe_path)
        except Exception as e:
            self.placeholder.setText(f"Errore avvio processo: {e}")

    def _on_process_started(self):
        """Dopo lo start, prova a trovare la window handle e embedderla."""
        # attendi un pochino che la finestra venga creata dall'app esterna
        QTimer.singleShot(400, self._try_embed_window)

    def _find_hwnd_for_pid(self, pid, timeout=5.0):
        """
        Cerca una finestra top-level per el PID specificato (usa win32).
        """
        end = time.time() + timeout
        found = []

        def enum_cb(hwnd, _):
            try:
                # consider only visible top-level windows
                if not win32gui.IsWindowVisible(hwnd):
                    return
                _, wid_pid = win32process.GetWindowThreadProcessId(hwnd)
                if wid_pid == pid:
                    found.append(hwnd)
            except Exception:
                pass

        while time.time() < end and not found:
            try:
                win32gui.EnumWindows(enum_cb, None)
            except Exception:
                pass
            if found:
                return found[0]
            time.sleep(0.15)
        return None

    def _try_embed_window(self):
        try:
            pid = int(self.process.processId())
        except Exception:
            pid = None

        if not pid:
            self.placeholder.setText("Impossibile ottenere PID del processo mappa.")
            return

        hwnd = self._find_hwnd_for_pid(pid, timeout=5.0)
        if not hwnd:
            self.placeholder.setText("Impossibile trovare la finestra della mappa; è stata avviata esternamente.")
            return

        # Create QWindow from native handle and embed
        try:
            app_window = QWindow.fromWinId(hwnd)
            container = QWidget.createWindowContainer(app_window, self)
            container.setMinimumSize(640, 360)
            # Remove placeholder and insert container
            try:
                self.layout.removeWidget(self.placeholder)
                self.placeholder.deleteLater()
            except Exception:
                pass
            self.layout.insertWidget(1, container)
            self.container = container
            self.placeholder = None
        except Exception as e:
            self.placeholder.setText(f"Errore embedding finestra: {e}")

    def close_map(self):
        """Chiude e/uccide il processo della mappa e rimuove il container."""
        try:
            if self.container:
                self.layout.removeWidget(self.container)
                self.container.deleteLater()
                self.container = None
            # kill process if exists
            if self.process:
                try:
                    pid = int(self.process.processId())
                    for p in psutil.process_iter(['pid', 'name']):
                        if p.info['pid'] == pid:
                            p.kill()
                except Exception:
                    pass
                self.process = None
            # restore placeholder
            if self.placeholder is None:
                self.placeholder = QLabel("Integrazione Mappa (app.exe)")
                self.placeholder.setAlignment(Qt.AlignCenter)
                self.placeholder.setObjectName("mapPlaceholder")
                self.layout.insertWidget(1, self.placeholder)
        except Exception as e:
            print("Errore close_map:", e)


class SettingsTab(QWidget):
    """Tab per le impostazioni del sistema"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.dark_mode_enabled = False
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        title = QLabel("IMPOSTAZIONI")
        title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setObjectName("settingsTitle")
        layout.addWidget(title)

        # Pulsanti principali
        test_pl_btn = QPushButton("TEST PL")
        close_app_btn = QPushButton("CHIUDI APP")
        mod_ice_btn = QPushButton("MOD ICE")
        restart_btn = QPushButton("RIAVVIA")
        self.dark_mode_btn = QPushButton("DARK MODE")

        buttons = [test_pl_btn, close_app_btn, mod_ice_btn, restart_btn, self.dark_mode_btn]

        for btn in buttons:
            btn.setFixedHeight(70)
            btn.setFont(QFont("Segoe UI", 18, QFont.Bold))
            btn.setObjectName("settingsButton")
            layout.addWidget(btn)

        close_app_btn.clicked.connect(self.close_app)
        restart_btn.clicked.connect(self.restart_app)
        self.dark_mode_btn.clicked.connect(self.toggle_dark_mode)

        layout.addStretch()
        self.setLayout(layout)

    def close_app(self):
        QApplication.quit()

    def restart_app(self):
        # semplice restart (riavvia lo script)
        try:
            python = sys.executable
            os.execv(python, [python] + sys.argv)
        except Exception as e:
            print("Errore restart:", e)

    def toggle_dark_mode(self):
        app = QApplication.instance()
        if not self.dark_mode_enabled:
            # Attiva dark mode
            self.apply_dark_style()
            self.dark_mode_btn.setText("LIGHT MODE")
            self.dark_mode_enabled = True
        else:
            # Disattiva dark mode
            self.apply_light_style()
            self.dark_mode_btn.setText("DARK MODE")
            self.dark_mode_enabled = False
            
    def apply_dark_style(self):
        """Applica uno stile dark mode completo all'applicazione"""
        dark_palette = QPalette()
        dark_palette.setColor(QPalette.Window, QColor(30, 30, 30))
        dark_palette.setColor(QPalette.WindowText, QColor(220, 220, 220))
        dark_palette.setColor(QPalette.Base, QColor(25, 25, 25))
        dark_palette.setColor(QPalette.AlternateBase, QColor(45, 45, 45))
        dark_palette.setColor(QPalette.ToolTipBase, QColor(220, 220, 220))
        dark_palette.setColor(QPalette.ToolTipText, QColor(220, 220, 220))
        dark_palette.setColor(QPalette.Text, QColor(220, 220, 220))
        dark_palette.setColor(QPalette.Button, QColor(50, 50, 50))
        dark_palette.setColor(QPalette.ButtonText, QColor(220, 220, 220))
        dark_palette.setColor(QPalette.BrightText, Qt.red)
        dark_palette.setColor(QPalette.Link, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.HighlightedText, Qt.black)
        
        app = QApplication.instance()
        app.setPalette(dark_palette)
        
        # Stile aggiuntivo per componenti specifici
        dark_stylesheet = """
            QWidget {
                background-color: #1e1e1e;
                color: #eaeaea;
                border: none;
            }
            QTabWidget::pane {
                border: 1px solid #444;
                background: #2d2d2d;
            }
            QTabBar::tab {
                background: #333;
                color: #eaeaea;
                padding: 14px 22px;
                font-size: 18px;
                border: 1px solid #444;
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
            }
            QTabBar::tab:selected {
                background: #2d2d2d;
                margin-bottom: -1px;
            }
            QFrame#batteryFrame, QFrame#rangeFrame, QFrame#infoFrame {
                background-color: #2d2d2d;
                border: 1px solid #444;
                border-radius: 8px;
            }
            QLabel#mainTitle, QLabel#mediaTitle, QLabel#mapTitle, QLabel#settingsTitle {
                color: #42a5f5;
            }
            QLabel#batteryLabel, QLabel#rangeTitle, QLabel#infoTitle {
                color: #eaeaea;
            }
            QLabel#rangeValue {
                color: #4caf50;
            }
            QLabel#wltpLabel, QLabel#calcLabel, QLabel#infoText {
                color: #bbb;
            }
            QLabel#carImagePlaceholder, QLabel#mapPlaceholder {
                background-color: #333;
                color: #bbb;
                border: 2px dashed #666;
            }
            QProgressBar#batteryProgress {
                border: 2px solid #555;
                border-radius: 5px;
                text-align: center;
                color: white;
            }
            QProgressBar#batteryProgress::chunk {
                background-color: #4caf50;
            }
            QPushButton#resetButton, QPushButton#refreshButton, 
            QPushButton#btButton, QPushButton#volumeButton,
            QPushButton#mapButton, QPushButton#settingsButton {
                background-color: #424242;
                color: white;
                border-radius: 6px;
                border: 1px solid #555;
            }
            QPushButton#resetButton:hover, QPushButton#refreshButton:hover, 
            QPushButton#btButton:hover, QPushButton#volumeButton:hover,
            QPushButton#mapButton:hover, QPushButton#settingsButton:hover {
                background-color: #555;
            }
            QListWidget#devicesList {
                background-color: #2d2d2d;
                color: #eaeaea;
                border: 1px solid #444;
                border-radius: 5px;
            }
        """
        app.setStyleSheet(dark_stylesheet)
        
    def apply_light_style(self):
        """Ripristina lo stile light mode"""
        app = QApplication.instance()
        app.setPalette(app.style().standardPalette())
        
        # Stile light mode
        light_stylesheet = """
            QWidget {
                background-color: #c8f5ff;
                color: black;
                border: none;
            }
            QTabWidget::pane {
                border: 1px solid #ccc;
                background: white;
            }
            QTabBar::tab {
                background: #e0e0e0;
                color: black;
                padding: 14px 22px;
                font-size: 18px;
                border: 1px solid #ccc;
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
            }
            QTabBar::tab:selected {
                background: white;
                margin-bottom: -1px;
            }
            QFrame#batteryFrame, QFrame#rangeFrame {
                background-color: #f0f0f0;
                border-radius: 8px;
            }
            QFrame#infoFrame {
                background-color: #00cc66;
                border-radius: 8px;
            }
            QLabel#mainTitle {
                color: #0057a8;
            }
            QLabel#mediaTitle, QLabel#mapTitle, QLabel#settingsTitle {
                color: #333;
            }
            QLabel#rangeValue {
                color: #007744;
            }
            QLabel#infoTitle, QLabel#infoText {
                color: white;
            }
            QLabel#carImagePlaceholder, QLabel#mapPlaceholder {
                background-color: #e0e0e0;
                color: #666;
                border: 2px dashed #999;
            }
            QProgressBar#batteryProgress {
                border: 2px solid #0057a8;
                border-radius: 5px;
                text-align: center;
            }
            QProgressBar#batteryProgress::chunk {
                background-color: #007744;
            }
            QPushButton#resetButton {
                background-color: #ff6666;
                color: white;
                border-radius: 6px;
            }
            QPushButton#resetButton:hover {
                background-color: #ff3333;
            }
            QPushButton#refreshButton, QPushButton#btButton {
                background-color: #0057a8;
                color: white;
                border-radius: 6px;
            }
            QPushButton#refreshButton:hover, QPushButton#btButton:hover {
                background-color: #003d7a;
            }
            QPushButton#volumeButton {
                background-color: #f0f0f0;
                color: #333;
                border-radius: 50px;
                border: 2px solid #ccc;
            }
            QPushButton#volumeButton:hover {
                background-color: #e0e0e0;
            }
            QPushButton#mapButton {
                background-color: #00cc66;
                color: white;
                border-radius: 6px;
            }
            QPushButton#mapButton:hover {
                background-color: #00aa44;
            }
            QPushButton#settingsButton {
                background-color: #666;
                color: white;
                border-radius: 6px;
            }
            QPushButton#settingsButton:hover {
                background-color: #444;
            }
            QListWidget#devicesList {
                background-color: white;
                color: black;
                border: 1px solid #ccc;
                border-radius: 5px;
            }
        """
        app.setStyleSheet(light_stylesheet)


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.battery_value = 0
        self.est_range_km = 0
        self.wltp_range_km = 200
        self.avg_speed = 0
        self.trip_km = 0
        self.signals = DataSignals()
        self.signals.updated.connect(self.update_ui)
        self.init_ui()
        self.start_data_thread()

    def init_ui(self):
        self.setWindowTitle("Bluecar Monitor")
        self.setGeometry(100, 100, 1200, 700)
        self.setMinimumSize(1000, 600)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.tabs = QTabWidget()
        self.tabs.setFont(QFont("Segoe UI", 18))
        self.tabs.setObjectName("mainTabs")

        self.trip_tab = TripTab(self)
        self.media_tab = MediaTab(self)
        self.map_tab = MapTab(self)
        self.settings_tab = SettingsTab(self)

        self.tabs.addTab(self.trip_tab, "Trip")
        self.tabs.addTab(self.media_tab, "Media")
        self.tabs.addTab(self.map_tab, "Mappa")
        self.tabs.addTab(self.settings_tab, "Impostazioni")

        main_layout.addWidget(self.tabs)
        self.setLayout(main_layout)

    def start_data_thread(self):
        self.data_thread = threading.Thread(target=self.data_loop, daemon=True)
        self.data_thread.start()

    def data_loop(self):
        while True:
            if test == 1:
                import random
                self.battery_value = random.randint(20, 100)
                self.avg_speed = random.uniform(30.0, 80.0)
                self.trip_km = random.uniform(5.0, 50.0)
                self.est_range_km = algokm(self.battery_value)
            else:
                if monitorBAT is not None:
                    self.battery_value = monitorBAT.get_battery_percentage()
                    self.est_range_km = algokm(self.battery_value)
                else:
                    self.battery_value = 0
                    self.est_range_km = 0

            self.signals.updated.emit()
            time.sleep(2)

    def update_ui(self):
        self.trip_tab.refresh_ui(
            self.battery_value,
            self.est_range_km,
            self.wltp_range_km,
            self.avg_speed,
            self.trip_km
        )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle(QStyleFactory.create("Fusion"))
    
    # Applica stile iniziale (light mode)
    settings = SettingsTab()
    settings.apply_light_style()
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
