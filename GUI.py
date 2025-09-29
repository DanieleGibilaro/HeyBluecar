import sys
import threading
import time
import os
from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QProgressBar, QFrame,
    QPushButton, QHBoxLayout, QTabWidget, QListWidget, QListWidgetItem,
    QStyle, QStyleFactory, QMdiArea, QMdiSubWindow
)
from PyQt5.QtGui import QFont, QPixmap, QWindow, QGuiApplication, QIcon, QPalette, QColor, QLinearGradient
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
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)
        
        # Sfondo con gradiente automotive
        self.setAutoFillBackground(True)
        palette = self.palette()
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0, QColor(20, 30, 40))
        gradient.setColorAt(1, QColor(10, 15, 25))
        palette.setBrush(QPalette.Window, gradient)
        self.setPalette(palette)

        left_column = QVBoxLayout()
        left_column.setContentsMargins(0, 0, 0, 0)
        left_column.setSpacing(15)

        battery_frame = QFrame()
        battery_frame.setFixedWidth(100)
        battery_frame.setObjectName("batteryFrame")
        battery_frame.setStyleSheet("""
            QFrame#batteryFrame {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #2a3b4d, stop: 1 #1e2a38);
                border: 2px solid #3a5066;
                border-radius: 12px;
                padding: 5px;
            }
        """)
        battery_layout = QVBoxLayout(battery_frame)
        battery_layout.setContentsMargins(8, 8, 8, 8)
        battery_layout.setSpacing(10)

        battery_label = QLabel("BATTERIA")
        battery_label.setFont(QFont("Arial", 10,5, QFont.Bold))
        battery_label.setAlignment(Qt.AlignCenter)
        battery_label.setStyleSheet("color: #e0e0e0; background: transparent;")

        self.battery_progress = QProgressBar()
        self.battery_progress.setOrientation(Qt.Vertical)
        self.battery_progress.setTextVisible(True)
        self.battery_progress.setFixedSize(70, 220)
        self.battery_progress.setFormat("%p%")
        self.battery_progress.setStyleSheet("""
            QProgressBar {
                background: #1a2530;
                border: 2px solid #3a5066;
                border-radius: 8px;
                text-align: center;
                color: white;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #00ff88, stop: 0.5 #00cc66, stop: 1 #00aa44);
                border-radius: 6px;
                margin: 2px;
            }
        """)

        battery_layout.addWidget(battery_label)
        battery_layout.addWidget(self.battery_progress, 0, Qt.AlignCenter)
        battery_layout.addStretch()

        left_column.addWidget(battery_frame)
        left_column.addStretch()

        center_column = QVBoxLayout()
        center_column.setContentsMargins(0, 0, 0, 0)
        center_column.setSpacing(15)

        title = QLabel("BLUECAR MONITOR")
        title.setFont(QFont("Arial", 24, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            color: #00ccff;
            background: transparent;
            text-shadow: 1px 1px 2px #000000;
        """)

        car_image = QLabel()
        if test == 1:
            car_image.setText("🚗 BLUECAR\n(Modalità Test)")
            car_image.setAlignment(Qt.AlignCenter)
            car_image.setFixedSize(240, 140)
            car_image.setStyleSheet("""
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #3a5066, stop: 1 #2a3b4d);
                color: #00ccff;
                border: 2px solid #4a6580;
                border-radius: 12px;
                font-weight: bold;
                font-size: 14px;
            """)
        else:
            try:
                pixmap = QPixmap("bluecar_icon.png").scaled(240, 140, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                car_image.setPixmap(pixmap)
                car_image.setAlignment(Qt.AlignCenter)
                car_image.setStyleSheet("background: transparent;")
            except Exception:
                car_image.setText("🚗 BLUECAR")
                car_image.setStyleSheet("""
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #3a5066, stop: 1 #2a3b4d);
                    color: #00ccff;
                    border: 2px solid #4a6580;
                    border-radius: 12px;
                    font-weight: bold;
                """)

        center_column.addWidget(title)
        center_column.addWidget(car_image)
        center_column.addStretch()

        right_column = QVBoxLayout()
        right_column.setContentsMargins(0, 0, 0, 0)
        right_column.setSpacing(15)

        range_frame = QFrame()
        range_frame.setObjectName("rangeFrame")
        range_frame.setStyleSheet("""
            QFrame#rangeFrame {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #2a3b4d, stop: 1 #1e2a38);
                border: 2px solid #3a5066;
                border-radius: 12px;
                padding: 10px;
            }
        """)
        range_layout = QVBoxLayout(range_frame)
        range_layout.setContentsMargins(8, 8, 8, 8)
        range_layout.setSpacing(10)

        range_title = QLabel("AUTONOMIA")
        range_title.setFont(QFont("Arial", 16, QFont.Bold))
        range_title.setAlignment(Qt.AlignCenter)
        range_title.setStyleSheet("color: #00ccff; background: transparent;")

        self.range_km = QLabel("-- km")
        self.range_km.setFont(QFont("Arial", 28, QFont.Bold))
        self.range_km.setAlignment(Qt.AlignCenter)
        self.range_km.setStyleSheet("color: #00ff88; background: transparent;")

        range_wltp_label = QLabel("WLTP: -- km")
        range_wltp_label.setFont(QFont("Arial", 12))
        range_wltp_label.setAlignment(Qt.AlignCenter)
        range_wltp_label.setStyleSheet("color: #a0a0a0; background: transparent;")

        range_calc_label = QLabel("Calcolato: -- km")
        range_calc_label.setFont(QFont("Arial", 12, QFont.Bold))
        range_calc_label.setAlignment(Qt.AlignCenter)
        range_calc_label.setStyleSheet("color: #00ccff; background: transparent;")

        range_layout.addWidget(range_title)
        range_layout.addWidget(self.range_km)
        range_layout.addWidget(range_wltp_label)
        range_layout.addWidget(range_calc_label)
        range_layout.addStretch()

        info_frame = QFrame()
        info_frame.setObjectName("infoFrame")
        info_frame.setStyleSheet("""
            QFrame#infoFrame {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #006633, stop: 1 #004422);
                border: 2px solid #008855;
                border-radius: 12px;
                padding: 10px;
            }
        """)
        info_layout = QVBoxLayout(info_frame)
        info_layout.setContentsMargins(8, 8, 8, 8)
        info_layout.setSpacing(10)

        info_title = QLabel("INFO VIAGGIO")
        info_title.setFont(QFont("Arial", 14, QFont.Bold))
        info_title.setAlignment(Qt.AlignCenter)
        info_title.setStyleSheet("color: #ffffff; background: transparent;")

        self.info_text = QLabel()
        self.info_text.setFont(QFont("Arial", 12))
        self.info_text.setAlignment(Qt.AlignLeft)
        self.info_text.setWordWrap(True)
        self.info_text.setStyleSheet("color: #e0ffe0; background: transparent;")

        info_layout.addWidget(info_title)
        info_layout.addWidget(self.info_text)
        info_layout.addStretch()

        reset_button = QPushButton("🔄 RESET TRIP")
        reset_button.setFixedHeight(45)
        reset_button.setFont(QFont("Arial", 12, QFont.Bold))
        reset_button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #ff5555, stop: 1 #cc3333);
                color: white;
                border: 2px solid #ff7777;
                border-radius: 8px;
                padding: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #ff7777, stop: 1 #dd5555);
                border: 2px solid #ff9999;
            }
            QPushButton:pressed {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #cc3333, stop: 1 #aa2222);
            }
        """)
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
            text=True,
            encoding='utf-8',  # Aggiungi encoding esplicito
            errors='ignore'    # Ignora errori di decoding
        )
        try:
            output, error = proc.communicate(timeout=5)  # Aumenta timeout a 5 secondi
        except subprocess.TimeoutExpired:
            proc.kill()
            output, error = proc.communicate()

        # Debug: stampa l'output per vedere cosa viene ricevuto
        print(f"Output completo: {repr(output)}")
        print(f"Errori: {repr(error)}")

        for riga in output.splitlines():
            riga = riga.strip()
            print(f"Riga elaborata: {repr(riga)}")  # Debug
            
            # Salta righe vuote o di stato
            if not riga or riga.startswith("Ricerca dispositivi"):
                continue
            
            # Cerca il formato nome@id
            if '@' in riga:
                try:
                    # Dividi al primo @
                    parts = riga.split('@', 1)
                    nome = parts[0].strip()
                    dev_id = '@' + parts[1].strip()  # Aggiungi @ all'inizio dell'ID
                    
                    # Filtra dispositivi non validi
                    if nome and dev_id and len(dev_id) > 1:
                        dispositivi_rilevati.append((nome, dev_id))
                        print(f"Dispositivo trovato: {nome} -> {dev_id}")  # Debug
                except Exception as e:
                    print(f"Errore parsing riga '{riga}': {e}")
                    continue
            
            # Alternative: potrebbero esserci altri formati
            elif '\\' in riga and any(keyword in riga for keyword in ['BTHENUM', 'VID', 'PID']):
                # Probabilmente è un ID dispositivo diretto
                nome = "Dispositivo Sconosciuto"
                dev_id = riga.strip()
                dispositivi_rilevati.append((nome, dev_id))
                print(f"Dispositivo trovato (formato alternativo): {nome} -> {dev_id}")

    except FileNotFoundError:
        print("⚠️ bluetoothc.exe non trovato!")
    except Exception as e:
        print(f"Errore rileva_dispositivi: {e}")
    
    print(f"Dispositivi finali: {dispositivi_rilevati}")  # Debug
    return dispositivi_rilevati







class MediaTab(QWidget):
    """Tab per la gestione dei media e del Bluetooth"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.connected_process = None
        self.volume = None
        
        # Sfondo con gradiente automotive
        self.setAutoFillBackground(True)
        palette = self.palette()
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0, QColor(20, 30, 40))
        gradient.setColorAt(1, QColor(10, 15, 25))
        palette.setBrush(QPalette.Window, gradient)
        self.setPalette(palette)
        
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        title = QLabel("🎵 MEDIA & BLUETOOTH")
        title.setFont(QFont("Arial", 10, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            color: #00ccff;
            background: transparent;
            text-shadow: 1px 1px 2px #000000;
        """)
        layout.addWidget(title)

        devices_label = QLabel("Dispositivi Bluetooth:")
        devices_label.setFont(QFont("Arial", 12, QFont.Bold))
        devices_label.setStyleSheet("color: #e0e0e0; background: transparent;")
        layout.addWidget(devices_label)

        self.devices_list = QListWidget()
        self.devices_list.setFont(QFont("Arial", 10))
        self.devices_list.setStyleSheet("""
            QListWidget {
                background: #1a2530;
                color: #e0e0e0;
                border: 2px solid #3a5066;
                border-radius: 8px;
                padding: 5px;
            }
            QListWidget::item {
                padding: 6px;
                border-bottom: 1px solid #2a3b4d;
            }
            QListWidget::item:selected {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #00ccff, stop: 1 #0088cc);
                color: white;
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.devices_list)

        refresh_btn = QPushButton("🔄 AGGIORNA")
        refresh_btn.setFixedHeight(50)
        refresh_btn.setFont(QFont("Arial", 14, QFont.Bold))
        refresh_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #3a5066, stop: 1 #2a3b4d);
                color: #00ccff;
                border: 2px solid #4a6580;
                border-radius: 8px;
                padding: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #4a6580, stop: 1 #3a5066);
                border: 2px solid #5a7590;
            }
            QPushButton:pressed {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #2a3b4d, stop: 1 #1e2a38);
            }
        """)
        refresh_btn.clicked.connect(self.refresh_devices)
        layout.addWidget(refresh_btn)

        bt_buttons_layout = QHBoxLayout()
        bt_buttons_layout.setSpacing(15)
        self.connect_btn = QPushButton("📱 CONNETTI")
        self.disconnect_btn = QPushButton("❌ DISCONNETTI")
        for btn in [self.connect_btn, self.disconnect_btn]:
            btn.setFixedHeight(50)
            btn.setFont(QFont("Arial", 14, QFont.Bold))
            btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #00cc66, stop: 1 #00aa44);
                    color: white;
                    border: 2px solid #00ee77;
                    border-radius: 8px;
                    padding: 5px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #00ee77, stop: 1 #00cc66);
                    border: 2px solid #00ff88;
                }
                QPushButton:pressed {
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #00aa44, stop: 1 #008833);
                }
            """)
        bt_buttons_layout.addWidget(self.connect_btn)
        bt_buttons_layout.addWidget(self.disconnect_btn)
        layout.addLayout(bt_buttons_layout)

        self.connect_btn.clicked.connect(self.connect_device)
        self.disconnect_btn.clicked.connect(self.disconnect_device)

        # Volume UI
        volume_label = QLabel("🔊 VOLUME")
        volume_label.setFont(QFont("Arial", 18, QFont.Bold))
        volume_label.setAlignment(Qt.AlignCenter)
        volume_label.setStyleSheet("color: #00ccff; background: transparent;")
        layout.addWidget(volume_label)

        volume_layout = QHBoxLayout()
        volume_layout.setSpacing(30)
        self.volume_down = QPushButton("🔉 -")
        self.volume_up = QPushButton("🔊 +")
        for btn in [self.volume_down, self.volume_up]:
            btn.setFixedSize(80, 80)
            btn.setFont(QFont("Arial", 18, QFont.Bold))
            btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #3a5066, stop: 1 #2a3b4d);
                    color: #00ccff;
                    border: 2px solid #4a6580;
                    border-radius: 40px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #4a6580, stop: 1 #3a5066);
                    border: 2px solid #5a7590;
                }
                QPushButton:pressed {
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #2a3b4d, stop: 1 #1e2a38);
                }
            """)
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
            # Pulisci il nome da caratteri speciali
            nome_pulito = nome.replace('@', '').replace('\\', '').strip()
            if not nome_pulito:
                nome_pulito = "Dispositivo Sconosciuto"
        
            item = QListWidgetItem(f"📱 {nome_pulito}")
            item.setFont(QFont("Arial", 12))
            item.setData(Qt.UserRole, dev_id)
            self.devices_list.addItem(item)
            print(f"Aggiunto alla lista: {nome_pulito} -> {dev_id}")  # Debug

    def connect_device(self):
        item = self.devices_list.currentItem()
        if item:
            dev_id = item.data(Qt.UserRole)[1:]
           
            try:
                proc = subprocess.Popen(
                    ["bluetoothc.exe", "dispositivi", "connetti", dev_id]
                )
                self.connected_process = proc
                print(f"✅ Connesso a {item.text()} ({dev_id})")
            except Exception as e:
                print("Errore nella connessione:", e)

    def disconnect_device(self):
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
    """Tab per la visualizzazione della mappa di navigazione con MDI"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.process = None
        self.container = None
        self.sub_window = None
        
        # Sfondo nero per contrasto con la mappa
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor(0, 0, 0))
        self.setPalette(palette)
        
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Area MDI per contenere la mappa
        self.mdi_area = QMdiArea()
        self.mdi_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.mdi_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.mdi_area.setViewMode(QMdiArea.SubWindowView)
        self.mdi_area.setStyleSheet("""
            QMdiArea {
                background-color: #000000;
                border: none;
            }
            QMdiSubWindow {
                background: transparent;
                border: none;
            }
        """)
        
        layout.addWidget(self.mdi_area)
        self.setLayout(layout)

        # Avvia automaticamente MSPaint invece della mappa
        if test == 0:
            QTimer.singleShot(1000, self.start_map)

    def start_map(self):
        """Avvia mspaint.exe e lo integra nell'area MDI"""
        exe_path = "mspaint.exe"

        if not win32_available:
            try:
                subprocess.Popen([exe_path])
            except Exception:
                pass
            return

        try:
            if self.process is not None:
                try:
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
        except Exception:
            pass

    def _on_process_started(self):
        """Dopo lo start, prova a trovare la window handle e integrarla in MDI"""
        QTimer.singleShot(1000, self._try_embed_window)

    def _find_hwnd_for_pid(self, pid, timeout=5.0):
        """Cerca una finestra top-level per il PID specificato"""
        end = time.time() + timeout
        found = []

        def enum_cb(hwnd, _):
            try:
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
            return

        hwnd = self._find_hwnd_for_pid(pid, timeout=3.0)
        if not hwnd:
            return

        # Crea un QWindow dal native handle
        try:
            app_window = QWindow.fromWinId(hwnd)
            
            # Crea un widget container per la finestra
            container = QWidget.createWindowContainer(app_window)
            container.setMinimumSize(780, 430)
            
            # Crea una subwindow MDI e aggiungi il container
            self.sub_window = QMdiSubWindow()
            self.sub_window.setWidget(container)
            self.sub_window.setWindowFlags(Qt.FramelessWindowHint)
            self.sub_window.setWindowState(Qt.WindowMaximized)
            
            # Rimuovi bordi e titolo dalla subwindow
            self.sub_window.setStyleSheet("""
                QMdiSubWindow {
                    background: transparent;
                    border: none;
                }
            """)
            
            # Aggiungi la subwindow all'area MDI
            self.mdi_area.addSubWindow(self.sub_window)
            self.sub_window.showMaximized()
            
        except Exception:
            pass

    def close_map(self):
        """Chiude il processo della mappa"""
        try:
            if self.process:
                try:
                    pid = int(self.process.processId())
                    for p in psutil.process_iter(['pid', 'name']):
                        if p.info['pid'] == pid:
                            p.kill()
                except Exception:
                    pass
                self.process = None
            
            # Rimuovi tutte le subwindows
            for sub_window in self.mdi_area.subWindowList():
                self.mdi_area.removeSubWindow(sub_window)
                sub_window.deleteLater()
                
        except Exception:
            pass


class SettingsTab(QWidget):
    """Tab per le impostazioni del sistema"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.dark_mode_enabled = False
        
        # Sfondo con gradiente automotive
        self.setAutoFillBackground(True)
        palette = self.palette()
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0, QColor(20, 30, 40))
        gradient.setColorAt(1, QColor(10, 15, 25))
        palette.setBrush(QPalette.Window, gradient)
        self.setPalette(palette)
        
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        title = QLabel("⚙️ IMPOSTAZIONI")
        title.setFont(QFont("Arial", 22, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            color: #00ccff;
            background: transparent;
            text-shadow: 1px 1px 2px #000000;
        """)
        layout.addWidget(title)

        # Pulsanti principali
        test_pl_btn = QPushButton("🧪 TEST PL")
        close_app_btn = QPushButton("⏹️ CHIUDI APP")
        mod_ice_btn = QPushButton("❄️ MOD ICE")
        restart_btn = QPushButton("🔄 RIAVVIA")
        

        buttons = [test_pl_btn, close_app_btn, mod_ice_btn, restart_btn,]

        for btn in buttons:
            btn.setFixedHeight(60)
            btn.setFont(QFont("Arial", 16, QFont.Bold))
            btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #3a5066, stop: 1 #2a3b4d);
                    color: #00ccff;
                    border: 2px solid #4a6580;
                    border-radius: 10px;
                    padding: 5px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #4a6580, stop: 1 #3a5066);
                    border: 2px solid #5a7590;
                }
                QPushButton:pressed {
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #2a3b4d, stop: 1 #1e2a38);
                }
            """)
            layout.addWidget(btn)

        close_app_btn.clicked.connect(self.close_app)
        restart_btn.clicked.connect(self.restart_app)
        

        layout.addStretch()
        self.setLayout(layout)

    def close_app(self):
        QApplication.quit()

    def restart_app(self):
        try:
            python = sys.executable
            os.execv(python, [python] + sys.argv)
        except Exception as e:
            print("Errore restart:", e)

    def toggle_dark_mode(self):
        app = QApplication.instance()
        if not self.dark_mode_enabled:
            self.apply_dark_style()
            self.dark_mode_btn.setText("☀️ LIGHT MODE")
            self.dark_mode_enabled = True
        else:
            self.apply_light_style()
            self.dark_mode_btn.setText("🌙 DARK MODE")
            self.dark_mode_enabled = False
            
    def apply_dark_style(self):
        dark_palette = QPalette()
        dark_palette.setColor(QPalette.Window, QColor(20, 30, 40))
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
        
        dark_stylesheet = """
            QTabWidget::pane {
                border: 1px solid #3a5066;
                background: #1e2a38;
            }
            QTabBar::tab {
                background: #2a3b4d;
                color: #00ccff;
                padding: 12px 20px;
                font-size: 16px;
                font-weight: bold;
                border: 1px solid #3a5066;
                border-bottom: none;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }
            QTabBar::tab:selected {
                background: #1e2a38;
                color: #00ff88;
            }
        """
        app.setStyleSheet(dark_stylesheet)
        
    def apply_light_style(self):
        app = QApplication.instance()
        app.setPalette(app.style().standardPalette())
        
        light_stylesheet = """
            QTabWidget::pane {
                border: 1px solid #3a5066;
                background: #c8f5ff;
            }
            QTabBar::tab {
                background: #2a3b4d;
                color: #00ccff;
                padding: 12px 20px;
                font-size: 16px;
                font-weight: bold;
                border: 1px solid #3a5066;
                border-bottom: none;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }
            QTabBar::tab:selected {
                background: #c8f5ff;
                color: #0057a8;
            }
        """
        app.setStyleSheet(light_stylesheet)


class BluecarMonitor(QWidget):
    """Classe principale dell'applicazione Bluecar Monitor"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bluecar Monitor")
        self.setFixedSize(800, 480)
        self.setWindowFlags(Qt.FramelessWindowHint)
        
        # Sfondo principale con gradiente automotive
        self.setAutoFillBackground(True)
        palette = self.palette()
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0, QColor(20, 30, 40))
        gradient.setColorAt(1, QColor(10, 15, 25))
        palette.setBrush(QPalette.Window, gradient)
        self.setPalette(palette)

        self.battery_value = 80 if test == 1 else 0
        self.est_range_km = 120 if test == 1 else 0
        self.wltp_range_km = 160
        self.avg_speed = 45 if test == 1 else 43
        self.trip_km = 15.5 if test == 1 else 0.0

        self.signals = DataSignals()
        self.signals.updated.connect(self.refresh_ui)

        self.init_ui()

        if test == 0:
            self.start_recalc_thread()
        else:
            self.start_test_thread()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        self.tabs = QTabWidget()
        self.tabs.setFont(QFont("Arial", 14, QFont.Bold))
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #3a5066;
                background: #1e2a38;
            }
            QTabBar::tab {
                background: #2a3b4d;
                color: #00ccff;
                padding: 12px 20px;
                font-size: 16px;
                font-weight: bold;
                border: 1px solid #3a5066;
                border-bottom: none;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }
            QTabBar::tab:selected {
                background: #1e2a38;
                color: #00ff88;
            }
        """)

        self.trip_tab = TripTab(self)
        self.media_tab = MediaTab(self)
        #self.map_tab = MapTab(self)
        self.settings_tab = SettingsTab(self)

        self.tabs.addTab(self.trip_tab, "🚗 Trip")
        self.tabs.addTab(self.media_tab, "🎵 Media")
        #self.tabs.addTab(self.map_tab, "🗺️ Mappa")
        self.tabs.addTab(self.settings_tab, "⚙️ Impostazioni")

        layout.addWidget(self.tabs)
        self.setLayout(layout)
        self.refresh_ui()

    def refresh_ui(self):
        self.trip_tab.refresh_ui(self.battery_value, self.est_range_km,
                                 self.wltp_range_km, self.avg_speed, self.trip_km)

    def start_recalc_thread(self):
        thread = threading.Thread(target=self.ricalcolo, daemon=True)
        thread.start()

    def start_test_thread(self):
        thread = threading.Thread(target=self.simula_dati, daemon=True)
        thread.start()

    def ricalcolo(self):
        global last, trip_km
        while True:
            if monitorBAT is not None:
                charge = monitorBAT.get_charge()
                self.battery_value = charge
                rimanente = algokm(charge)
                self.trip_km = trip_km
                if rimanente == 0.0 and last != 0:
                    self.est_range_km = last
                else:
                    self.est_range_km = rimanente
                    last = rimanente
                self.avg_speed = media
                self.signals.updated.emit()
            else:
                time.sleep(1)

    def simula_dati(self):
        import random
        while True:
            self.battery_value = max(5, min(100, self.battery_value + random.randint(-2, 1)))
            self.est_range_km = max(0, self.est_range_km + random.uniform(-1, 0.5))
            self.avg_speed = max(0, self.avg_speed + random.uniform(-2, 2))
            self.trip_km = max(0, self.trip_km + random.uniform(0, 0.2))
            self.signals.updated.emit()
            time.sleep(2)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle(QStyleFactory.create("Fusion"))
    
    # non viene piu realmente caricato il light poiché attualmente lo stile é bloccato a dark perché dopo test é stato scoperto che veniva scelto e usato solo lui , é anche piu bellino
    settings = SettingsTab()
    settings.apply_light_style()
    
    monitor = BluecarMonitor()
    monitor.show()
    sys.exit(app.exec_())


