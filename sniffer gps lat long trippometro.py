"""
Dual serial GPS bridge + stats (COM12 → COM100, STATS → COM101)
con migliorie al calcolo della distanza e gestione perdita segnale

Prerequisiti Windows:
1. Installare com0com (o VSPE) e creare due coppie di porte:
      CNCA0 ↔ CNCB0   → rinominare CNCA0 = COM100, CNCB0 = COM200
      CNCA1 ↔ CNCB1   → rinominare CNCA1 = COM101, CNCB1 = COM201
2. Collegare il vostro software di navigazione a COM200
   e il monitor delle statistiche a COM201.

"""

import serial
import threading
import time
import pynmea2
from math import radians, sin, cos, sqrt, atan2
from queue import Queue
from collections import deque
import numpy as np

BAUDRATE = 9600
SOURCE = 'COM4'
GPS_OUT = 'COM100'
STATS_PT = 'COM101'

SER_CFG = dict(
    baudrate=BAUDRATE,
    bytesize=serial.EIGHTBITS,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    timeout=0
)

class GPSTracker:
    def __init__(self):
        self.gps_q = Queue()
        self.stats_q = Queue()
        self.last_pos = None
        self.last_valid_pos = None
        self.tot_dist = self.trip_dist = 0.0
        self.speeds = []
        self.trip_speeds = []
        self.last_t = time.time()
        self.running = True
        self.signal_lost_time = None
        self.error_count = 0
        self.stats_log = []
        self.position_history = deque(maxlen=10)

        # Configurazione
        self.config = {
            'min_distance': 2.0,  # Metri minimi per considerare movimento
            'max_speed': 55.0,    # m/s (~200 km/h) per filtrare outlier
            'signal_timeout': 30,  # Secondi prima di considerare segnale perso
            'reuse_position_max_age': 5  # Secondi massimi per riusare posizione
        }

        try:
            self.ser_src = serial.Serial(SOURCE, **SER_CFG)
            self.ser_gps = serial.Serial(GPS_OUT, **SER_CFG)
            self.ser_stats = serial.Serial(STATS_PT, **SER_CFG)
            print(f"Porte seriali aperte: {SOURCE}, {GPS_OUT}, {STATS_PT}")
        except Exception as e:
            raise SystemExit(f"Impossibile aprire le seriali: {e}")

        self.t_read = threading.Thread(target=self._reader, daemon=True)
        self.t_write = threading.Thread(target=self._gps_writer, daemon=True)
        self.t_stat = threading.Thread(target=self._stats_srv, daemon=True)

    @staticmethod
    def haversine(lat1, lon1, lat2, lon2):
        """Calcola distanza in metri tra due coordinate"""
        if None in (lat1, lon1, lat2, lon2):
            return 0.0

        R = 6371000  # Raggio terrestre in metri
        φ1, λ1, φ2, λ2 = map(radians, (lat1, lon1, lat2, lon2))
        dφ, dλ = φ2 - φ1, λ2 - λ1

        a = sin(dφ/2)**2 + cos(φ1)*cos(φ2)*sin(dλ/2)**2
        return 2 * R * atan2(sqrt(a), sqrt(1 - a))

    def _is_valid_position(self, lat, lon, speed=None):
        """Verifica se la posizione è valida"""
        if lat is None or lon is None:
            return False
        if abs(lat) > 90 or abs(lon) > 180:
            return False
        if speed and speed > self.config['max_speed']:
            return False  # Filtra velocità impossibili
        return True

    def _smooth_position(self, lat, lon):
        """Applica smoothing alle coordinate usando media mobile"""
        self.position_history.append((lat, lon))
        
        if len(self.position_history) >= 3:
            # Media mobile delle ultime posizioni
            lats = [p[0] for p in self.position_history]
            lons = [p[1] for p in self.position_history]
            return np.mean(lats), np.mean(lons)
        return lat, lon

    def _handle_low_signal_quality(self):
        """Gestisce situazioni di segnale scarso"""
        current_time = time.time()
        if (self.last_valid_pos and 
            current_time - self.last_t < self.config['reuse_position_max_age']):
            # Usa l'ultima posizione valida per brevi periodi
            self._update_stats(*self.last_valid_pos)

    def _format_stats_message(self, timestamp, lat, lon):
        """Formatta il messaggio di statistiche"""
        avg_speed = np.mean(self.speeds) if self.speeds else 0
        trip_avg_speed = np.mean(self.trip_speeds) if self.trip_speeds else 0
        signal_status = "VALID" if self.signal_lost_time is None else "LOST"

        return ("STATS,{:.2f},{:.2f},{:.2f},{:.2f},{:.3f},{:.6f},{:.6f},{}\n"
               .format(self.tot_dist,
                       self.trip_dist,
                       avg_speed,
                       trip_avg_speed,
                       timestamp,
                       lat, lon,
                       signal_status))

    def _update_stats(self, lat, lon):
        now = time.time()
        
        if not self._is_valid_position(lat, lon):
            # Segnale perso - gestione speciale
            if self.signal_lost_time is None:
                self.signal_lost_time = now
                print("Segnale GPS perso")
            elif now - self.signal_lost_time > self.config['signal_timeout']:
                self.last_pos = None  # Reset per evitare calcoli errati
            return
        
        # Reset timer perdita segnale
        if self.signal_lost_time is not None:
            print(f"Segnale GPS recuperato dopo {now - self.signal_lost_time:.1f}s")
            self.signal_lost_time = None
        
        # Applica smoothing alla posizione
        lat, lon = self._smooth_position(lat, lon)
        
        if self.last_pos:
            # Calcola distanza e velocità
            d = self.haversine(*self.last_pos, lat, lon)
            dt = max(0.1, now - self.last_t)  # Evita divisioni per zero
            
            # Filtra movimenti minimi e outlier
            if (d > self.config['min_distance'] and 
                d/dt < self.config['max_speed']):
                
                self.tot_dist += d
                self.trip_dist += d
                current_speed = d / dt
                self.speeds.append(current_speed)
                self.trip_speeds.append(current_speed)
                
                # Aggiorna ultima posizione valida
                self.last_valid_pos = (lat, lon)
                
                # Mantieni liste di dimensioni ragionevoli
                if len(self.speeds) > 1000:
                    self.speeds = self.speeds[-500:]
                if len(self.trip_speeds) > 1000:
                    self.trip_speeds = self.trip_speeds[-500:]
        
        self.last_pos = (lat, lon)
        self.last_t = now
        
        # Invia statistiche
        msg = self._format_stats_message(now, lat, lon)
        self.stats_q.put(msg)
        
        # Log per debugging (mantieni solo ultimi 100 record)
        if len(self.stats_log) < 100:
            self.stats_log.append({
                'timestamp': now,
                'position': (lat, lon),
                'distance': self.tot_dist,
                'signal_status': 'VALID' if self.signal_lost_time is None else 'LOST'
            })

    def _reader(self):
        buffer = b''
        while self.running:
            try:
                raw = self.ser_src.read_all()
                if raw:
                    buffer += raw
                    lines = buffer.split(b'\r\n')
                    buffer = lines[-1]  # Mantieni l'ultimo frammento incompleto
                    
                    for line in lines[:-1]:
                        if len(line) > 6 and line[3:6] == b'GGA':
                            try:
                                decoded_line = line.decode(errors='ignore').strip()
                                msg = pynmea2.parse(decoded_line)
                                
                                if (hasattr(msg, "latitude") and 
                                    hasattr(msg, "longitude") and 
                                    hasattr(msg, "gps_qual")):
                                    
                                    # Controlla qualità del segnale
                                    if (msg.gps_qual is not None and 
                                        msg.gps_qual > 0 and 
                                        msg.latitude is not None and 
                                        msg.longitude is not None):
                                        
                                        self._update_stats(msg.latitude, msg.longitude)
                                    else:
                                        # Segnale di bassa qualità
                                        self._handle_low_signal_quality()
                                        
                            except (pynmea2.ParseError, ValueError, UnicodeDecodeError) as e:
                                if self.error_count < 10:  # Limita messaggi di errore
                                    print(f"[parse error] {e}")
                                self.error_count += 1
                                
            except Exception as e:
                print(f"[reader error] {e}")
                time.sleep(1)  # Pausa più lunga in caso di errore grave
                
            time.sleep(0.01)

    def _gps_writer(self):
        while self.running:
            try:
                if not self.gps_q.empty():
                    data = self.gps_q.get_nowait()
                    if self.ser_gps and self.ser_gps.is_open:
                        self.ser_gps.write(data)
                time.sleep(0.001)  # Pausa più breve per migliore responsività
            except Exception as e:
                print(f"[gps_writer error] {e}")
                time.sleep(0.1)

    def _stats_srv(self):
        while self.running:
            try:
                # Invia messaggi statistici
                while not self.stats_q.empty():
                    msg = self.stats_q.get_nowait().encode()
                    if self.ser_stats and self.ser_stats.is_open:
                        self.ser_stats.write(msg)
                
                # Gestisci comandi di reset
                cmd = self.ser_stats.read_all().decode().strip().upper()
                if 'R' in cmd:
                    self.trip_dist = 0
                    self.trip_speeds = []
                    self.stats_q.put("TRIP RESET\n")
                    print("Reset viaggio effettuato")
                    
            except Exception as e:
                print(f"[stats_srv error] {e}")
                time.sleep(0.5)
                
            time.sleep(0.1)

    def start(self):
        print("Tracker GPS avviato.")
        print("Stats disponibili su COM101, dati GPS mirroring su COM100.")
        print("Premere Ctrl+C per fermare.")
        
        self.t_read.start()
        self.t_write.start()
        self.t_stat.start()
        
        try:
            while self.running:
                # Log periodico dello stato
                if int(time.time()) % 30 == 0:  # Ogni 30 secondi
                    status = "OK" if self.signal_lost_time is None else f"NO SIGNAL ({time.time() - self.signal_lost_time:.0f}s)"
                    print(f"Stato: {status} | Distanza totale: {self.tot_dist:.1f}m | Viaggio: {self.trip_dist:.1f}m")
                time.sleep(1)
                
        except KeyboardInterrupt:
            self.running = False
            print("\nInterruzione da tastiera ricevuta...")
            
        finally:
            print("Chiusura in corso...")
            for s in (self.ser_src, self.ser_gps, self.ser_stats):
                if s and s.is_open:
                    try:
                        s.close()
                    except Exception as e:
                        print(f"Errore chiusura porta: {e}")
            
            # Statistiche finali
            print(f"\nStatistiche finali:")
            print(f"Distanza totale percorsa: {self.tot_dist:.2f} metri")
            print(f"Distanza ultimo viaggio: {self.trip_dist:.2f} metri")
            print(f"Velocità media: {np.mean(self.speeds) if self.speeds else 0:.2f} m/s")
            print("Chiuso.")

if __name__ == "__main__":
    try:
        GPSTracker().start()
    except Exception as e:
        print(f"Errore durante l'avvio: {e}")
        print("Verificare che:")
        print("1. Le porte seriali siano disponibili")
        print("2. Il GPS sia collegato e funzionante")
        print("3. I driver virtuali siano configurati correttamente")
