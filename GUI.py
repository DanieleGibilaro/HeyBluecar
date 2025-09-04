import sys, threading, time, os
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout,
    QProgressBar, QFrame, QPushButton, QHBoxLayout,
    QTabWidget, QListWidget, QListWidgetItem
)
from PyQt5.QtGui import QFont, QPixmap
from PyQt5.QtCore import Qt, pyqtSignal, QObject
from can_monitor import create_battery_monitor
import serial
import subprocess
import psutil
from ctypes import POINTER, cast
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
# Variabile per la modalità test (0 = normale, 1 = testing grafico)
test = 1  # Imposta a 1 per testing grafico senza connessioni reali

# Inizializzazione della comunicazione seriale con modulo esterno per trip (solo se non in modalità test)
ser = None
if test == 0:
    try:
        ser = serial.Serial('COM201', 9600, timeout=1)
    except Exception as e:
        print(f"Errore connessione seriale: {e}")
        ser = None

# Variabili globali per la gestione del viaggio e autonomia
inizializzato = 0      # Flag per indicare se il sistema è stato inizializzato
inizio = 100           # Livello di carica iniziale della batteria
media = 0              # Velocità media calcolata
last = 0               # Ultimo valore di autonomia calcolato
trip_km = 0.0          # Chilometraggio del viaggio corrente
start_time = None      # Timestamp di inizio viaggio

# Creazione e avvio del monitor della batteria (solo se non in modalità test)
monitorBAT = None
if test == 0:
    try:
        monitorBAT = create_battery_monitor()
        monitorBAT.start()
    except Exception as e:
        print(f"Errore inizializzazione monitor batteria: {e}")
        monitorBAT = None

def algokm(attuale):
    """
    Calcola l'autonomia residua basata sul consumo della batteria e le statistiche del viaggio.
    
    Args:
        attuale: Livello attuale di carica della batteria
        
    Returns:
        float: Autonomia residua in chilometri
    """
    global inizializzato, inizio, media, trip_km, start_time

    # Se in modalità test, simula dati invece di leggere dalla seriale
    if test == 1:
        time.sleep(1)  # Simula ritardo di lettura
        # Simula dati casuali per testing
        import random
        trip_km = random.uniform(5.0, 50.0)
        media = random.uniform(30.0, 80.0)
        
        # Calcola autonomia basata su consumo simulato
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

    # CODICE NORMALE (quando test = 0)
    trip_distance_km = 0
    trip_avg_speed_kmh = 0
    trip_speed_kmh = 0

    # Inizializza il sistema al primo valore di carica valido
    if (inizializzato == 0) and attuale > 0:
        if ser is not None:
            ser.write(b'R')  # Invia comando di reset al dispositivo
        inizializzato = 1
        print("inizializzato")
        print(attuale)
        inizio = attuale
        start_time = datetime.now()  # Salva il timestamp di inizio viaggio
    
    time.sleep(1)  # Attendi 1 secondo tra le letture

    # Leggi i dati dalla porta seriale (se disponibile)
    if ser is not None:
        line = ser.readline().decode().strip()
        print(line)
        
        # Elabora le statistiche ricevute
        if line.startswith("STATS"):
            parts = line.split(',')
            trip_distance_km = float(parts[2]) / 1000  # Converti metri in km
            trip_avg_speed_kmh = float(parts[4]) * 3.6  # Converti m/s in km/h
            print("stat ricevute")
            trip_km = trip_distance_km
            trip_speed_kmh = trip_avg_speed_kmh
            print(trip_km)
    
    media = trip_speed_kmh
    percento = inizio - attuale  # Calcola la percentuale di batteria consumata

    # Calcola l'autonomia residua
    if percento > 1:
        kmrim = (trip_km / percento) * attuale
        print("krim")
        print(kmrim)
    else:
        kmrim = 0.0

    return round(kmrim, 1)  # Arrotonda a 1 decimale

class DataSignals(QObject):
    """Classe per gestire i segnali tra thread per l'aggiornamento dell'interfaccia"""
    updated = pyqtSignal()  # Segnale emesso quando i dati vengono aggiornati

class TripTab(QWidget):
    """Tab per visualizzare le informazioni sul viaggio e l'autonomia"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent  # Riferimento alla finestra principale
        self.init_ui()  # Inizializza l'interfaccia
        
    def init_ui(self):
        """Inizializza l'interfaccia della tab Trip"""
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
        # Usa un'immagine placeholder se in modalità test
        if test == 1:
            car_image.setText("IMMAGINE BLUECAR\n(Modalità Test)")
            car_image.setStyleSheet("background-color: #e0e0e0; border: 1px dashed #999;")
            car_image.setAlignment(Qt.AlignCenter)
            car_image.setFixedSize(250, 120)
        else:
            pixmap = QPixmap("bluecar_icon.png").scaled(250, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            car_image.setPixmap(pixmap)
            car_image.setAlignment(Qt.AlignCenter)

        center_column.addWidget(title)
        center_column.addWidget(car_image)
        center_column.addStretch()

        # Colonna destra con informazioni viaggio e range
        right_column = QVBoxLayout()
        right_column.setContentsMargins(10, 10, 10, 10)

        # Sezione range (autonomia)
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

        # Pulsante per resettare il viaggio
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

        # Aggiungi tutte le colonne al layout principale
        main_layout.addLayout(left_column)
        main_layout.addLayout(center_column)
        main_layout.addLayout(right_column)

        self.setLayout(main_layout)

    def refresh_ui(self, battery_value, est_range_km, wltp_range_km, avg_speed, trip_km):
        """
        Aggiorna l'interfaccia con i nuovi valori
        
        Args:
            battery_value: Valore percentuale della batteria
            est_range_km: Autonomia stimata in km
            wltp_range_km: Autonomia WLTP in km
            avg_speed: Velocità media in km/h
            trip_km: Chilometri percorsi nel viaggio corrente
        """
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
        """
        Restituisce il colore in base al livello della batteria
        
        Args:
            value: Valore percentuale della batteria
            
        Returns:
            str: Codice colore esadecimale
        """
        if value > 70:
            return "#00cc66"  # Verde per batteria carica
        elif value > 30:
            return "#ffcc00"  # Giallo per batteria media
        return "#ff3300"      # Rosso per batteria scarica

    def reset_trip(self):
        """Resetta le statistiche del viaggio corrente"""
        global inizializzato, inizio, trip_km, start_time

        end_time = datetime.now()
        # Registra il viaggio completato nel file di log
        if start_time is not None and trip_km > 0:
            percent_consumed = inizio - self.parent.battery_value
            self.log_trip(start_time, end_time, trip_km, percent_consumed)

        # Resetta tutte le variabili del viaggio
        inizializzato = 0
        trip_km = 0.0
        self.parent.trip_km = 0.0
        self.parent.est_range_km = 0
        start_time = None
        # Aggiorna l'interfaccia con i valori resettati
        self.refresh_ui(self.parent.battery_value, self.parent.est_range_km, 
                       self.parent.wltp_range_km, self.parent.avg_speed, self.parent.trip_km)

    def log_trip(self, start, end, km, percent):
        """
        Registra i dettagli del viaggio in un file di log
        
        Args:
            start: Timestamp di inizio viaggio
            end: Timestamp di fine viaggio
            km: Chilometri percorsi
            percent: Percentuale di batteria consumata
        """
        os.makedirs("logtrip", exist_ok=True)
        with open("logtrip/oldtrip.txt", "a") as f:
            line = f"{start.strftime('%Y-%m-%d %H:%M')} | {end.strftime('%Y-%m-%d %H:%M')} | {km:.2f} km | {percent:.1f}% consumati\n"
            f.write(line)



def rileva_dispositivi():
    """Chiama app.exe dispositivi e restituisce lista di (nome, id)."""
    dispositivi_rilevati = []

    try:
        proc = subprocess.Popen(
            ["bluetoothc.exe", "dispositivi"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        # Leggi l’output iniziale e chiudi
        try:
            output, error = proc.communicate(timeout=1)
        except subprocess.TimeoutExpired:
            proc.kill()
            output, error = proc.communicate()

        # Filtra le righe
        for riga in output.splitlines():
            riga = riga.strip()
            if not riga or riga.startswith("Ricerca dispositivi"):
                continue
            if '@' in riga:
                nome, dev_id = riga.split('@', 1)
                dispositivi_rilevati.append((nome, dev_id))

    except FileNotFoundError:
        print("⚠️ app.exe non trovato!")

    return dispositivi_rilevati


class MediaTab(QWidget):
    """Tab per la gestione dei media e del Bluetooth"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.connected_process = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        title = QLabel("Media e Bluetooth")
        title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        devices_label = QLabel("Dispositivi Bluetooth disponibili:")
        devices_label.setFont(QFont("Segoe UI", 12))
        layout.addWidget(devices_label)

        self.devices_list = QListWidget()
        layout.addWidget(self.devices_list)

        # Pulsante Aggiorna
        refresh_btn = QPushButton("Aggiorna")
        refresh_btn.clicked.connect(self.refresh_devices)
        layout.addWidget(refresh_btn)

        # Pulsanti connessione
        bt_buttons_layout = QHBoxLayout()
        self.connect_btn = QPushButton("Connetti")
        self.disconnect_btn = QPushButton("Disconnetti")
        bt_buttons_layout.addWidget(self.connect_btn)
        bt_buttons_layout.addWidget(self.disconnect_btn)
        layout.addLayout(bt_buttons_layout)

        self.connect_btn.clicked.connect(self.connect_device)
        self.disconnect_btn.clicked.connect(self.disconnect_device)

        self.setLayout(layout)

        # Aggiorna subito l’elenco
        self.refresh_devices()

    def refresh_devices(self):
        """Aggiorna lista dispositivi chiamando rileva_dispositivi()."""
        self.devices_list.clear()
        dispositivi = rileva_dispositivi()
        for nome, dev_id in dispositivi:
            item = QListWidgetItem(nome)
            item.setData(Qt.UserRole, dev_id)
            self.devices_list.addItem(item)

    def connect_device(self):
        """Connetti al dispositivo selezionato."""
        item = self.devices_list.currentItem()
        if item:
            dev_id = item.data(Qt.UserRole)
            try:
                # Lascio app.exe in esecuzione
                self.connected_process = subprocess.Popen(
                    ["bluetoothc.exe", "dispositivi", "connetti", dev_id]
                )
                print(f"✅ Connesso a {item.text()} ({dev_id})")
            except Exception as e:
                print("Errore nella connessione:", e)

    def disconnect_device(self):
        """Disconnetti chiudendo ogni processo app.exe attivo."""
        for proc in psutil.process_iter(['pid', 'name']):
            if proc.info['name'] == "bluetoothc.exe":
                proc.kill()
        self.connected_process = None
        print("💥 Disconnesso (processo app.exe chiuso)")

class MapTab(QWidget):
    """Tab per la visualizzazione della mappa di navigazione"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        
    def init_ui(self):
        """Inizializza l'interfaccia della tab Mappa"""
        layout = QVBoxLayout()
        
        # Titolo della tab
        title = QLabel("Mappa di Navigazione")
        title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Area placeholder per l'integrazione dell'app di mappe
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
        
        # Tentativo di avviare l'app di mappe esterna (solo se non in modalità test)
        if test == 0:
            try:
                # Sostituisci con il percorso corretto della tua app
                subprocess.Popen(["./avit12/avit.exe"])
            except Exception as e:
                print(f"Impossibile avviare l'app di mappe: {e}")


class SettingsTab(QWidget):
    """Tab per le impostazioni del sistema"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.init_ui()
        
    def init_ui(self):
        """Inizializza l'interfaccia della tab Impostazioni"""
        layout = QVBoxLayout()
        
        # Titolo della tab
        title = QLabel("Impostazioni")
        title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Pulsanti per le varie impostazioni
        test_pl_btn = QPushButton("TestPL")
        close_app_btn = QPushButton("Chiudi App")
        mod_ice_btn = QPushButton("MOD ICE")
        restart_btn = QPushButton("Restart")
        
        buttons = [test_pl_btn, close_app_btn, mod_ice_btn, restart_btn]
        
        # Stile dei pulsanti delle impostazioni
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
        
        # Connessione dei pulsanti alle relative funzioni
        close_app_btn.clicked.connect(self.close_app)
        restart_btn.clicked.connect(self.restart_app)
        
        self.setLayout(layout)
    
    def close_app(self):
        """Chiude l'applicazione"""
        QApplication.quit()
    
    def restart_app(self):
        """Riavvia l'applicazione (funzionalità da implementare)"""
        print("Funzione di restart non implementata")


class DashcamTab(QWidget):
    """Tab per la gestione della dashcam"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        
    def init_ui(self):
        """Inizializza l'interfaccia della tab Dashcam"""
        layout = QVBoxLayout()
        
        # Titolo della tab
        title = QLabel("Dashcam")
        title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Area per lo streaming video dalla webcam
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
        
        # Pulsante per iniziare/fermare la registrazione
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
        
        self.is_recording = False  # Stato della registrazione
        
        self.setLayout(layout)
    
    def toggle_recording(self):
        """Attiva o disattiva la registrazione video"""
        if self.is_recording:
            self.stop_recording()
        else:
            self.start_recording()
    
    def start_recording(self):
        """Avvia la registrazione video"""
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
        """Ferma la registrazione video"""
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
    """Classe principale dell'applicazione Bluecar Monitor"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bluecar Monitor")
        self.setGeometry(0, 0, 800, 480)  # Imposta la risoluzione a 800x480
        self.setWindowFlags(Qt.FramelessWindowHint)  # Rimuove i bordi della finestra
        self.setStyleSheet("background-color: #c8f5ff;")

        # Inizializzazione delle variabili di stato
        self.battery_value = 80 if test == 1 else 0  # Valore simulato in modalità test
        self.est_range_km = 120 if test == 1 else 0  # Valore simulato in modalità test
        self.wltp_range_km = 160
        self.avg_speed = 45 if test == 1 else 43     # Valore simulato in modalità test
        self.trip_km = 15.5 if test == 1 else 0.0    # Valore simulato in modalità test

        # Inizializzazione del sistema di segnali per l'aggiornamento dell'UI
        self.signals = DataSignals()
        self.signals.updated.connect(self.refresh_ui)

        self.init_ui()  # Inizializza l'interfaccia
        
        # Avvia il thread di calcolo solo se non in modalità test
        if test == 0:
            self.start_recalc_thread()
        else:
            # In modalità test, simula l'aggiornamento dei dati
            self.start_test_thread()

    def init_ui(self):
        """Inizializza l'interfaccia principale con il sistema a tab"""
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
        
        # Aggiorna l'interfaccia con i valori iniziali
        self.refresh_ui()

    def refresh_ui(self):
        """Aggiorna l'interfaccia utente con i dati correnti"""
        self.trip_tab.refresh_ui(self.battery_value, self.est_range_km, 
                               self.wltp_range_km, self.avg_speed, self.trip_km)

    def start_recalc_thread(self):
        """Avvia il thread per il ricalcolo dei dati in background (modalità normale)"""
        thread = threading.Thread(target=self.ricalcolo, daemon=True)
        thread.start()

    def start_test_thread(self):
        """Avvia il thread per simulare l'aggiornamento dei dati (modalità test)"""
        thread = threading.Thread(target=self.simula_dati, daemon=True)
        thread.start()

    def ricalcolo(self):
        """
        Thread per il calcolo continuo dell'autonomia e aggiornamento dei dati.
        Questo viene eseguito in background per non bloccare l'interfaccia.
        (Modalità normale - test = 0)
        """
        global last, trip_km
        while True:
            # Ottieni il livello di carica della batteria
            if monitorBAT is not None:
                charge = monitorBAT.get_charge()
                self.battery_value = charge
                print("mandato")
                
                # Calcola l'autonomia residua
                rimanente = algokm(charge)
                self.trip_km = trip_km
                
                # Gestisci il caso in cui l'autonomia sia zero
                if rimanente == 0.0 and last != 0:
                    self.est_range_km = last
                else:
                    self.est_range_km = rimanente
                    last = rimanente
                
                # Aggiorna la velocità media
                self.avg_speed = media
                
                # Segnala l'aggiornamento dell'interfaccia
                self.signals.updated.emit()
            else:
                time.sleep(1)  # Attendi se il monitor batteria non è disponibile

    def simula_dati(self):
        """
        Simula l'aggiornamento dei dati per testing grafico.
        (Modalità test - test = 1)
        """
        import random
        while True:
            # Simula variazioni casuali nei dati
            self.battery_value = max(5, min(100, self.battery_value + random.randint(-2, 1)))
            self.est_range_km = max(0, self.est_range_km + random.uniform(-1, 0.5))
            self.avg_speed = max(0, self.avg_speed + random.uniform(-2, 2))
            self.trip_km = max(0, self.trip_km + random.uniform(0, 0.2))
            
            # Aggiorna l'interfaccia
            self.signals.updated.emit()
            
            # Attendi prima del prossimo aggiornamento
            time.sleep(2)
        

if __name__ == "__main__":
    # Punto di ingresso dell'applicazione
    app = QApplication(sys.argv)
    monitor = BluecarMonitor()
    monitor.show()
    sys.exit(app.exec_())
