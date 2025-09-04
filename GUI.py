import sys, threading, time
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout,
    QProgressBar, QFrame, QPushButton
)
from PyQt5.QtGui import QFont, QPixmap
from PyQt5.QtCore import Qt, pyqtSignal, QObject
from can_monitor import create_battery_monitor
import serial

ser = serial.Serial('COM201', 9600, timeout=1)
inizializzato=0
inizio=100
media=0



monitorBAT = create_battery_monitor()
monitorBAT.start()



def algokm(attuale):
    global inizializzato
    global inizio
    global media
    trip_distance_km=0
    trip_avg_speed_kmh=0
    trip_speed_kmh=0
    trip_km=0
    
    
    ser.reset_input_buffer()  # Svuota il buffer
    if inizializzato==0:
        ser.write(b'R')
        inizializzato=1
        inizio=attuale
    time.sleep(0.1)
    
    line = ser.readline().decode().strip()
    print(line)
   # Legge l'ultimo dato disponibile
    if line.startswith("STATS"):
        # Dividi i valori separati da virgola
        parts = line.split(',')
            
        # Estrai i dati necessari (indici basati sul formato STATS)
        trip_distance_km = float(parts[2]) / 1000  # Converti metri -> km
        trip_avg_speed_kmh = float(parts[4]) * 3.6  # Converti m/s -> km/h
            
        # Assegna alle variabili
        trip_km = trip_distance_km
        trip_speed_kmh = trip_avg_speed_kmh
    
    media=trip_speed_kmh
    percento=inizio-attuale
    if percento>1: 
        kmrim=(trip_km/percento)*attuale
    else: kmrim="000"
    return kmrim
    
    
    





class DataSignals(QObject):
    updated = pyqtSignal()

class BluecarMonitor(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bluecar Monitor")
        self.setGeometry(100, 100, 800, 480)
        self.setStyleSheet("background-color: #c8f5ff;")

        # Initial values
        self.battery_value = 00
        self.est_range_km = 00
        self.wltp_range_km = 160
        self.avg_speed = 43  # km/h

        # threading signal
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

        

        main_layout.addWidget(title)
        main_layout.addWidget(car_image)
        main_layout.addWidget(self.range_km)
        main_layout.addWidget(self.battery_progress)
        
        main_layout.addStretch()
        main_layout.addWidget(info_bar)

        self.setLayout(main_layout)
        self.refresh_ui()

    def refresh_ui(self):
        self.range_km.setText(f"{self.est_range_km} km ({int((self.battery_value/100)*self.wltp_range_km)} km WLTP)")
        self.battery_progress.setValue(self.battery_value)
        self.battery_progress.setStyleSheet(f"""
            QProgressBar {{border:2px solid #0057a8;border-radius:10px;text-align:center;}}
            QProgressBar::chunk {{background-color:{self.get_battery_color(self.battery_value)};}}
        """)
        self.info_text.setText(
            f" Velocità media: {self.avg_speed} km/h "
        )

    # manual simulate button
    def update_values(self):
        self.battery_value = (self.battery_value - 10) % 101
        self.est_range_km = max(0, int((self.battery_value/100)*self.wltp_range_km))
        self.avg_speed = (self.avg_speed + 5) % 120
        self.refresh_ui()

    # separate recalculation thread
    def start_recalc_thread(self):
        thread = threading.Thread(target=self.ricalcolo, daemon=True)
        thread.start()

    def ricalcolo(self):
        """Threaded loop – update variables every 5 s (placeholder logic)."""
        while True:
            # placeholder for external-controlled logic
            # here just increment speed and decrement battery for demo
            charge = monitorBAT.get_charge()
            self.battery_value = charge
            self.est_range_km = algokm(charge)
            self.avg_speed = 0
            self.signals.updated.emit()
            time.sleep(5)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    monitor = BluecarMonitor()
    monitor.show()
    sys.exit(app.exec_())
