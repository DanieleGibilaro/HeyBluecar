"""
Dual serial GPS bridge + stats (COM12 → COM100, STATS → COM101)

Prerequisiti Windows:
1. Installare com0com (o VSPE) e creare due coppie di porte:
      CNCA0 ↔ CNCB0   → rinominare CNCA0 = COM100, CNCB0 = COM200
      CNCA1 ↔ CNCB1   → rinominare CNCA1 = COM101, CNCB1 = COM201
2. Collegare il vostro software di navigazione a COM200
   e il monitor delle statistiche a COM201.
3. Avviare questo script con i privilegi di amministratore se necessario.
"""

import serial, threading, time, pynmea2
from math import radians, sin, cos, sqrt, atan2
from queue import Queue

BAUDRATE = 9600
SOURCE   = 'COM4'
GPS_OUT  = 'COM100'
STATS_PT = 'COM101'

SER_CFG = dict(
    baudrate = BAUDRATE,
    bytesize = serial.EIGHTBITS,
    parity   = serial.PARITY_NONE,
    stopbits = serial.STOPBITS_ONE,
    timeout  = 0
)

class GPSTracker:
    def __init__(self):
        self.gps_q   = Queue()
        self.stats_q = Queue()
        self.last_pos = None
        self.tot_dist = self.trip_dist = 0.0
        self.speeds = self.trip_speeds = []
        self.last_t  = time.time()
        self.running = True

        try:
            self.ser_src   = serial.Serial(SOURCE,  **SER_CFG)
            self.ser_gps   = serial.Serial(GPS_OUT, **SER_CFG)
            self.ser_stats = serial.Serial(STATS_PT,**SER_CFG)
        except Exception as e:
            raise SystemExit(f"Impossibile aprire le seriali: {e}")

        self.t_read  = threading.Thread(target=self._reader,  daemon=True)
        self.t_write = threading.Thread(target=self._gps_writer, daemon=True)
        self.t_stat  = threading.Thread(target=self._stats_srv, daemon=True)

    @staticmethod
    def haversine(lat1, lon1, lat2, lon2):
        R = 6371000
        φ1, λ1, φ2, λ2 = map(radians, (lat1, lon1, lat2, lon2))
        dφ, dλ = φ2 - φ1, λ2 - λ1
        a = sin(dφ/2)**2 + cos(φ1)*cos(φ2)*sin(dλ/2)**2
        return 2 * R * atan2(sqrt(a), sqrt(1 - a))

    def _update_stats(self, lat, lon):
        now = time.time()
        if self.last_pos:
            d = self.haversine(*self.last_pos, lat, lon)
            dt = now - self.last_t or 1e-6
            v = d / dt
            self.tot_dist  += d
            self.trip_dist += d
            self.speeds.append(v)
            self.trip_speeds.append(v)
        self.last_pos = (lat, lon)
        self.last_t = now

        msg = ("STATS,{:.2f},{:.2f},{:.2f},{:.2f},{:.3f},{:.6f},{:.6f}\n"
               .format(self.tot_dist,
                       self.trip_dist,
                       sum(self.speeds)/len(self.speeds) if self.speeds else 0,
                       sum(self.trip_speeds)/len(self.trip_speeds) if self.trip_speeds else 0,
                       now, lat, lon))
        self.stats_q.put(msg)

    def _reader(self):
        while self.running:
            try:
                raw = self.ser_src.read_all()
                if raw:
                    self.gps_q.put(raw)
                    for line in raw.split(b'\r\n'):
                        if line[3:6] == b'GGA':
                            try:
                                msg = pynmea2.parse(line.decode(errors='ignore'))
                                if hasattr(msg, "latitude") and hasattr(msg, "longitude"):
                                    if msg.latitude and msg.longitude:
                                        self._update_stats(msg.latitude, msg.longitude)
                            except (pynmea2.ParseError, ValueError) as e:
                                print(f"[parse error] {e}")
            except Exception as e:
                print(f"[reader] {e}")
                self.running = False
            time.sleep(0.005)

    def _gps_writer(self):
        while self.running:
            try:
                while not self.gps_q.empty():
                    data = self.gps_q.get_nowait()
                    if self.ser_gps and self.ser_gps.is_open:
                        self.ser_gps.write(data)
            except Exception as e:
                print(f"[gps_writer] {e}")
                self.running = False
            time.sleep(0.005)

    def _stats_srv(self):
        while self.running:
            try:
                while not self.stats_q.empty():
                    msg = self.stats_q.get_nowait().encode()
                    if self.ser_stats and self.ser_stats.is_open:
                        self.ser_stats.write(msg)

                cmd = self.ser_stats.read_all().decode().strip().upper()
                if 'R' in cmd:
                    self.trip_dist = 0
                    self.trip_speeds = []
                    self.stats_q.put("TRIP RESET\n")
            except Exception as e:
                print(f"[stats_srv] {e}")
                self.running = False
            time.sleep(0.1)

    def start(self):
        print("Tracker avviato. Stats su COM101, dati GPS mirroring su COM100.")
        self.t_read.start()
        self.t_write.start()
        self.t_stat.start()
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.running = False
        finally:
            print("Chiusura in corso...")
            for s in (self.ser_src, self.ser_gps, self.ser_stats):
                if s and s.is_open:
                    try:
                        s.close()
                    except:
                        pass
            print("Chiuso.")

if __name__ == "__main__":
    GPSTracker().start()
