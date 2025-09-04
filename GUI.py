import sys, threading, time, os
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout,
    QProgressBar, QFrame, QPushButton, QHBoxLayout,
    QTabWidget, QListWidget, QListWidgetItem, QSlider
)
from PyQt5.QtGui import QFont, QPixmap
from PyQt5.QtCore import Qt, pyqtSignal, QObject
from can_monitor import create_battery_monitor
import serial
import subprocess

ser = serial.Serial('COM201', 9600, timeout=1)

# Variabili globali
inizializzato = 0
inizio = 100
media = 0
last = 0
trip_km = 0.0
start_time = None  # Data inizio trip

monitorBAT = create_battery_monitor()
monitorBAT.start()

def algokm(attuale):
    global inizializzato, inizio, media, trip_km, start_time

    trip_distance_km = 0
    trip_avg_speed_kmh = 0
    trip_speed_kmh = 0

    if (inizializzato == 0) and attuale>0:
        ser.write(b'R')
        inizializzato = 1
        print("inizializzato")
        print(attuale)
        inizio = attuale
        start_time = datetime.now()  # salva inizio trip
    time.sleep(1)

    line = ser.readline().decode().strip()
    print(line)
    if line.startswith("STATS"):
        parts = line.split(',')
        trip_distance_km = float(parts[2]) / 1000
        trip_avg_speed_kmh = float(parts[4]) * 3.6
        print("stat ricevute")
        trip_km = trip_distance_km
        trip_speed_kmh = trip_avg_speed_kmh
        print(trip_km)
    media = trip_speed_kmh
    percento = inizio - attuale

    if percento > 1:
        kmrim = (trip_km / percento) * attuale
        print("krim")
        print(kmrim)
    else:
        kmrim = 0.0

    #ser.reset_input_buffer()#svuota il buffer per rendere il piu nuova possibile l'informazione la prossima volta (idea in beta)
    return round(kmrim, 1)

class DataSignals(QObject):
    updated = pyqtSignal()

class TripTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.init_ui()
        
    def init_ui(self):
        main_layout = QHBoxLayout()  # Layout principale orizzontale

        # Colonna sinistra con la batteria verticale
        left_column = QVBoxLayout()
        left_column.setContentsMargins(10, 10, 10, 10)

        # Progress bar della batteria verticale
        battery_frame = QFrame()
        battery_frame.setFixedWidth(80)
        battery_layout = QVBoxLayout(battery_frame)

        battery_label = QLabel("Batteria")
        battery_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
        battery_label.setAlignment(Qt.AlignCenter)

        self.battery_progress = QProgressBar()
        self.battery_progress.setOrientation(Qt.Vertical)
        self.battery_progress.setTextVisible(True)
        self.battery_progress.setFixedSize(60, 200)
        self.battery_progress.setFormat("%p%")
        self.battery_progress.setStyleSheet("""
            QProgressBar {
                border: 2px solid #0057a8;
                border-radius: 5px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #007744;
                width: 1px;
            }
        """)

        battery_layout.addWidget(battery_label)
        battery_layout.addWidget(self.battery_progress, 0, Qt.AlignCenter)
        battery_layout.addStretch()

        left_column.addWidget(battery_frame)
        left_column.addStretch()

        # Colonna centrale con titolo e immagine
        center_column = QVBoxLayout()
        center_column.setContentsMargins(0, 10, 0, 10)

        title = QLabel("Bluecar Monitor")
        title.setFont(QFont("Segoe UI", 28, QFont.Bold))
        title.setStyleSheet("color: #0057a8;")
        title.setAlignment(Qt.AlignCenter)

        car_image = QLabel()
        pixmap = QPixmap("bluecar_icon.png").scaled(250, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        car_image.setPixmap(pixmap)
        car_image.setAlignment(Qt.AlignCenter)

        center_column.addWidget(title)
        center_column.addWidget(car_image)
        center_column.addStretch()

        # Colonna destra con informazioni viaggio e range
        right_column = QVBoxLayout()
        right_column.setContentsMargins(10, 10, 10, 10)

        # Sezione range
        range_frame = QFrame()
        range_frame.setStyleSheet("background-color: #f0f0f0; border-radius: 5px;")
        range_layout = QVBoxLayout(range_frame)

        range_title = QLabel("Autonomia")
        range_title.setFont(QFont("Segoe UI", 18, QFont.Bold))
        range_title.setAlignment(Qt.AlignCenter)

        self.range_km = QLabel("-- km")
        self.range_km.setFont(QFont("Segoe UI", 24, QFont.Bold))
        self.range_km.setStyleSheet("color: #007744;")
        self.range_km.setAlignment(Qt.AlignCenter)

        range_wltp_label = QLabel("WLTP: -- km")
        range_wltp_label.setFont(QFont("Segoe UI", 12))
        range_wltp_label.setAlignment(Qt.AlignCenter)

        range_calc_label = QLabel("Calcolato: -- km")
        range_calc_label.setFont(QFont("Segoe UI", 12, QFont.Bold))
        range_calc_label.setAlignment(Qt.AlignCenter)

        range_layout.addWidget(range_title)
        range_layout.addWidget(self.range_km)
        range_layout.addWidget(range_wltp_label)
        range_layout.addWidget(range_calc_label)
        range_layout.addStretch()

        # Sezione informazioni viaggio
        info_frame = QFrame()
        info_frame.setStyleSheet("""
            background-color: #00cc66;
            border-radius: 5px;
            padding: 5px;
        """)
        info_layout = QVBoxLayout(info_frame)

        info_title = QLabel("Informazioni viaggio")
        info_title.setFont(QFont("Segoe UI", 18, QFont.Bold))
        info_title.setStyleSheet("color: white;")
        info_title.setAlignment(Qt.AlignCenter)

        self.info_text = QLabel()
        self.info_text.setFont(QFont("Segoe UI", 12))
        self.info_text.setStyleSheet("color: white;")
        self.info_text.setAlignment(Qt.AlignLeft)
        self.info_text.setWordWrap(True)

        info_layout.addWidget(info_title)
        info_layout.addWidget(self.info_text)
        info_layout.addStretch()

        reset_button = QPushButton("Reset Trip")
        reset_button.setStyleSheet("""
            QPushButton {
                background-color: #ff6666;
                color: white;
                font-size: 15px;
                padding: 3px;
                border-radius: 3px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #ff4444;
            }
        """)
        reset_button.clicked.connect(self.reset_trip)

        right_column.addWidget(range_frame)
        right_column.addWidget(info_frame)
        right_column.addWidget(reset_button, 0, Qt.AlignCenter)
        right_column.addStretch()

        # Aggiungiamo tutte le colonne al layout principale
        main_layout.addLayout(left_column)
        main_layout.addLayout(center_column)
        main_layout.addLayout(right_column)

        self.setLayout(main_layout)

    def refresh_ui(self, battery_value, est_range_km, wltp_range_km, avg_speed, trip_km):
        self.range_km.setText(f"{est_range_km:.1f} km ({int((battery_value/100)*wltp_range_km)} km WLTP)")
        self.battery_progress.setValue(battery_value)
        self.battery_progress.setStyleSheet(f"""
            QProgressBar {{border:2px solid #0057a8;border-radius:10px;text-align:center;}}
            QProgressBar::chunk {{background-color:{self.get_battery_color(battery_value)};}}
        """)
        self.info_text.setText(
            f"Velocità media: {avg_speed:.1f} km/h\nTrip km: {trip_km:.2f} km"
        )

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


class MediaTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Titolo
        title = QLabel("Media e Bluetooth")
        title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Lista dispositivi Bluetooth
        devices_label = QLabel("Dispositivi Bluetooth disponibili:")
        devices_label.setFont(QFont("Segoe UI", 12))
        layout.addWidget(devices_label)
        
        self.devices_list = QListWidget()
        # Aggiungi alcuni dispositivi di esempio (dovresti sostituire con una scansione reale)
        devices = ["Telefono di Mario", "Cuffie JBL", "Auto Stereo", "Altoparlante Sony"]
        for device in devices:
            item = QListWidgetItem(device)
            self.devices_list.addItem(item)
        layout.addWidget(self.devices_list)
        
        # Pulsanti Bluetooth
        bt_buttons_layout = QHBoxLayout()
        connect_btn = QPushButton("Connetti")
        disconnect_btn = QPushButton("Disconnetti")
        
        connect_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-size: 16px;
                padding: 10px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        
        disconnect_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                font-size: 16px;
                padding: 10px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
        """)
        
        bt_buttons_layout.addWidget(connect_btn)
        bt_buttons_layout.addWidget(disconnect_btn)
        layout.addLayout(bt_buttons_layout)
        
        # Controllo volume
        volume_label = QLabel("Volume:")
        volume_label.setFont(QFont("Segoe UI", 14))
        volume_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(volume_label)
        
        volume_buttons_layout = QHBoxLayout()
        volume_down_btn = QPushButton("-")
        volume_up_btn = QPushButton("+")
        
        for btn in [volume_down_btn, volume_up_btn]:
            btn.setFixedSize(80, 80)
            btn.setFont(QFont("Segoe UI", 24, QFont.Bold))
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #2196F3;
                    color: white;
                    border-radius: 40px;
                }
                QPushButton:hover {
                    background-color: #0b7dda;
                }
            """)
        
        volume_buttons_layout.addWidget(volume_down_btn)
        volume_buttons_layout.addWidget(volume_up_btn)
        layout.addLayout(volume_buttons_layout)
        
        self.setLayout(layout)


class MapTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Titolo
        title = QLabel("Mappa di Navigazione")
        title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Nota: qui dovresti integrare la tua app di mappe
        # Per ora aggiungiamo un placeholder
        map_placeholder = QLabel("Integrazione Mappa (app.exe)")
        map_placeholder.setAlignment(Qt.AlignCenter)
        map_placeholder.setStyleSheet("""
            QLabel {
                background-color: #e0e0e0;
                border: 2px dashed #999;
                min-height: 300px;
            }
        """)
        layout.addWidget(map_placeholder)
        
        self.setLayout(layout)
        
        # Avvia l'app di mappe (se disponibile)
        try:
            # Sostituisci con il percorso corretto della tua app
            subprocess.Popen(["app.exe"])
        except Exception as e:
            print(f"Impossibile avviare l'app di mappe: {e}")


class SettingsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Titolo
        title = QLabel("Impostazioni")
        title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Pulsanti impostazioni
        test_pl_btn = QPushButton("TestPL")
        close_app_btn = QPushButton("Chiudi App")
        mod_ice_btn = QPushButton("MOD ICE")
        restart_btn = QPushButton("Restart")
        
        buttons = [test_pl_btn, close_app_btn, mod_ice_btn, restart_btn]
        
        for btn in buttons:
            btn.setFixedHeight(60)
            btn.setFont(QFont("Segoe UI", 16))
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #2196F3;
                    color: white;
                    border-radius: 5px;
                    margin: 5px;
                }
                QPushButton:hover {
                    background-color: #0b7dda;
                }
            """)
            layout.addWidget(btn)
        
        # Connessioni dei pulsanti
        close_app_btn.clicked.connect(self.close_app)
        restart_btn.clicked.connect(self.restart_app)
        
        self.setLayout(layout)
    
    def close_app(self):
        QApplication.quit()
    
    def restart_app(self):
        # Qui potresti implementare un riavvio dell'applicazione
        print("Funzione di restart non implementata")


class DashcamTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Titolo
        title = QLabel("Dashcam")
        title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Video dalla webcam
        self.video_label = QLabel("Streaming Webcam")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setStyleSheet("""
            QLabel {
                background-color: #000;
                color: #fff;
                min-height: 300px;
            }
        """)
        layout.addWidget(self.video_label)
        
        # Pulsante registrazione
        self.record_btn = QPushButton("Inizia Registrazione")
        self.record_btn.setFixedHeight(60)
        self.record_btn.setFont(QFont("Segoe UI", 16))
        self.record_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
        """)
        self.record_btn.clicked.connect(self.toggle_recording)
        layout.addWidget(self.record_btn)
        
        self.is_recording = False
        
        self.setLayout(layout)
    
    def toggle_recording(self):
        if self.is_recording:
            self.stop_recording()
        else:
            self.start_recording()
    
    def start_recording(self):
        self.is_recording = True
        self.record_btn.setText("Ferma Registrazione")
        self.record_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        print("Registrazione iniziata")
        # Qui implementa l'avvio della registrazione video
    
    def stop_recording(self):
        self.is_recording = False
        self.record_btn.setText("Inizia Registrazione")
        self.record_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
        """)
        print("Registrazione fermata")
        # Qui implementa l'arresto della registrazione video


class BluecarMonitor(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bluecar Monitor")
        self.setGeometry(0, 0, 800, 480)
        self.setWindowFlags(Qt.FramelessWindowHint)  # Rimuove i bordi della finestra
        self.setStyleSheet("background-color: #c8f5ff;")

        self.battery_value = 0
        self.est_range_km = 0
        self.wltp_range_km = 160
        self.avg_speed = 43
        self.trip_km = 0.0

        self.signals = DataSignals()
        self.signals.updated.connect(self.refresh_ui)

        self.init_ui()
        self.start_recalc_thread()

    def init_ui(self):
        layout = QVBoxLayout()
        
        # Creazione del widget a tab
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #ccc;
                background: white;
            }
            QTabBar::tab {
                background: #e0e0e0;
                padding: 10px;
                margin: 2px;
                border: 1px solid #ccc;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background: white;
                margin-bottom: -1px;
            }
        """)
        
        # Creazione delle tab
        self.trip_tab = TripTab(self)
        self.media_tab = MediaTab(self)
        self.map_tab = MapTab(self)
        self.settings_tab = SettingsTab(self)
        self.dashcam_tab = DashcamTab(self)
        
        # Aggiunta delle tab al tab widget
        self.tabs.addTab(self.trip_tab, "Trip")
        self.tabs.addTab(self.media_tab, "Media")
        self.tabs.addTab(self.map_tab, "MAP")
        self.tabs.addTab(self.settings_tab, "Settings")
        self.tabs.addTab(self.dashcam_tab, "Dashcam")
        
        layout.addWidget(self.tabs)
        self.setLayout(layout)

    def refresh_ui(self):
        # Aggiorna la tab Trip
        self.trip_tab.refresh_ui(self.battery_value, self.est_range_km, 
                               self.wltp_range_km, self.avg_speed, self.trip_km)

    def start_recalc_thread(self):
        thread = threading.Thread(target=self.ricalcolo, daemon=True)
        thread.start()

    def ricalcolo(self):
        global last, trip_km
        while True:
            charge = monitorBAT.get_charge()
            self.battery_value = charge
            print("mandato")
            rimanente = algokm(charge)
            self.trip_km = trip_km
            if rimanente == 0.0 and last != 0:
                self.est_range_km = last
            else:
                self.est_range_km = rimanente
                last = rimanente
            self.avg_speed = media
            self.signals.updated.emit()
        

if __name__ == "__main__":
    app = QApplication(sys.argv)
    monitor = BluecarMonitor()
    monitor.show()
    sys.exit(app.exec_())
