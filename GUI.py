import sys, threading, time, os
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout,
    QProgressBar, QFrame, QPushButton
)
from PyQt5.QtGui import QFont, QPixmap
from PyQt5.QtCore import Qt, pyqtSignal, QObject
from can_monitor import create_battery_monitor
import serial

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
        inizio = attuale
        start_time = datetime.now()  # salva inizio trip
    time.sleep(10)

    line = ser.readline().decode().strip()

    if line.startswith("STATS"):
        parts = line.split(',')
        trip_distance_km = float(parts[2]) / 1000
        trip_avg_speed_kmh = float(parts[4]) * 3.6

        trip_km = trip_distance_km
        trip_speed_kmh = trip_avg_speed_kmh

    media = trip_speed_kmh
    percento = inizio - attuale

    if percento > 1:
        kmrim = (trip_km / percento) * attuale
    else:
        kmrim = 0.0

    ser.reset_input_buffer()#svuota il buffer per rendere il piu nuova possibile l'informazione la prossima volta (idea in beta)
    return round(kmrim, 1)

class DataSignals(QObject):
    updated = pyqtSignal()

class BluecarMonitor(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bluecar Monitor")
        self.setGeometry(100, 100, 800, 480)
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

    @staticmethod
    def get_battery_color(value):
        if value > 70:
            return "#00cc66"
        elif value > 30:
            return "#ffcc00"
        return "#ff3300"

    def init_ui(self):
        main_layout = QVBoxLayout()

        title = QLabel("Bluecar Monitor")
        title.setFont(QFont("Segoe UI", 28, QFont.Bold))
        title.setStyleSheet("color: #0057a8;")
        title.setAlignment(Qt.AlignCenter)

        car_image = QLabel()
        pixmap = QPixmap("bluecar_icon.png").scaled(300, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        car_image.setPixmap(pixmap)
        car_image.setAlignment(Qt.AlignCenter)

        self.range_km = QLabel()
        self.range_km.setFont(QFont("Segoe UI", 26, QFont.Bold))
        self.range_km.setAlignment(Qt.AlignCenter)
        self.range_km.setStyleSheet("color: #007744;")

        self.battery_progress = QProgressBar()
        self.battery_progress.setTextVisible(True)
        self.battery_progress.setFixedHeight(30)

        info_bar = QFrame()
        info_bar.setStyleSheet("background-color: #00cc66; padding: 10px;")
        info_layout = QVBoxLayout()

        info_title = QLabel("Informazioni viaggio")
        info_title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        info_title.setStyleSheet("color: white;")
        info_title.setAlignment(Qt.AlignCenter)

        self.info_text = QLabel()
        self.info_text.setFont(QFont("Segoe UI", 14))
        self.info_text.setStyleSheet("color: white;")
        self.info_text.setAlignment(Qt.AlignCenter)

        info_layout.addWidget(info_title)
        info_layout.addWidget(self.info_text)
        info_bar.setLayout(info_layout)

        reset_button = QPushButton("Reset Trip")
        reset_button.setStyleSheet(
            "background-color: #ff6666; color: white; font-size: 16px; padding: 10px; border-radius: 8px;"
        )
        reset_button.clicked.connect(self.reset_trip)

        main_layout.addWidget(title)
        main_layout.addWidget(car_image)
        main_layout.addWidget(self.range_km)
        main_layout.addWidget(self.battery_progress)
        main_layout.addStretch()
        main_layout.addWidget(info_bar)
        main_layout.addWidget(reset_button, alignment=Qt.AlignCenter)

        self.setLayout(main_layout)
        self.refresh_ui()

    def refresh_ui(self):
        self.range_km.setText(f"{self.est_range_km:.1f} km ({int((self.battery_value/100)*self.wltp_range_km)} km WLTP)")
        self.battery_progress.setValue(self.battery_value)
        self.battery_progress.setStyleSheet(f"""
            QProgressBar {{border:2px solid #0057a8;border-radius:10px;text-align:center;}}
            QProgressBar::chunk {{background-color:{self.get_battery_color(self.battery_value)};}}
        """)
        self.info_text.setText(
            f"Velocità media: {self.avg_speed:.1f} km/h\nTrip km: {self.trip_km:.2f} km"
        )

    def reset_trip(self):
        global inizializzato, inizio, trip_km, start_time

        end_time = datetime.now()
        if start_time is not None and trip_km > 0:
            percent_consumed = inizio - self.battery_value
            self.log_trip(start_time, end_time, trip_km, percent_consumed)

        inizializzato = 0
        trip_km = 0.0
        self.trip_km = 0.0
        self.est_range_km = 0
        start_time = None
        self.refresh_ui()

    def log_trip(self, start, end, km, percent):
        os.makedirs("logtrip", exist_ok=True)
        with open("logtrip/oldtrip.txt", "a") as f:
            line = f"{start.strftime('%Y-%m-%d %H:%M')} | {end.strftime('%Y-%m-%d %H:%M')} | {km:.2f} km | {percent:.1f}% consumati\n"
            f.write(line)

    def start_recalc_thread(self):
        thread = threading.Thread(target=self.ricalcolo, daemon=True)
        thread.start()

    def ricalcolo(self):
        global last, trip_km
        while True:
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
            time.sleep(5)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    monitor = BluecarMonitor()
    monitor.show()
    sys.exit(app.exec_())
