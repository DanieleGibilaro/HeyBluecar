# can_monitor.py
import ctypes
import time
import threading
from datetime import datetime
import os

class CANBusManager:
    """Gestisce la connessione e comunicazione CAN"""
    
    def __init__(self):
        self._load_dll()
        self._setup_functions()
        
    def _load_dll(self):
        """Carica la DLL CAN"""
        try:
            self.can_dll = ctypes.WinDLL("./VIT7_CANbus_DLL.dll")
        except Exception as e:
            raise RuntimeError(f"Errore nel caricamento DLL: {e}")
    
    def _setup_functions(self):
        """Configura le funzioni della DLL"""
        # Struttura dati
        class ReturnData(ctypes.Structure):
            _fields_ = [
                ("nType", ctypes.c_int),
                ("nResult", ctypes.c_int),
                ("nID", ctypes.c_int),
                ("nIDE", ctypes.c_int),
                ("nRTR", ctypes.c_int),
                ("nDLC", ctypes.c_int),
                ("cData", ctypes.c_ubyte * 8)
            ]
        self.ReturnData = ReturnData
        
        # Funzioni
        self.VIT7_Connect = self.can_dll.VIT7_Connect
        self.VIT7_Connect.restype = ctypes.c_int
        
        self.VIT7_Disconnect = self.can_dll.VIT7_Disconnect
        
        self.VIT7_ReceiveMessage = self.can_dll.VIT7_ReceiveMessage
        self.VIT7_ReceiveMessage.argtypes = [ctypes.POINTER(ReturnData)]
        self.VIT7_ReceiveMessage.restype = ctypes.c_int
        
        self.VIT7_ClrReceiveFIFO = self.can_dll.VIT7_ClrReceiveFIFO
        self.VIT7_ClrReceiveFIFO.restype = ctypes.c_int
    
    def connect(self):
        """Stabilisce la connessione CAN"""
        if self.VIT7_Connect() != 1:
            raise ConnectionError("Connessione CAN fallita")
        return True
    
    def disconnect(self):
        """Chiude la connessione CAN"""
        self.VIT7_Disconnect()
    
    def receive_message(self):
        """Riceve un messaggio CAN"""
        msg = self.ReturnData()
        if self.VIT7_ReceiveMessage(ctypes.byref(msg)) == 1:
            return msg
        return None
    
    def clear_fifo(self):
        """Pulisce il buffer di ricezione"""
        return self.VIT7_ClrReceiveFIFO() == 1


class BatteryMonitor:
    """Monitora lo stato della batteria dal bus CAN"""
    
    def __init__(self, can_manager):
        self.can = can_manager
        self.current_charge = 0  # 0-100%
        self.running = False
        self.lock = threading.Lock()
        self._setup_logging()
        
    def _setup_logging(self):
        """Configura il sistema di logging"""
        os.makedirs("can_logs", exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = open(f"can_logs/battery_{timestamp}.csv", "a")
        self.log_file.write("timestamp,charge%\n")
    
    def start(self):
        """Avvia il monitoraggio"""
        if self.running:
            return
            
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
    
    def stop(self):
        """Ferma il monitoraggio"""
        self.running = False
        if hasattr(self, 'thread'):
            self.thread.join()
        self.log_file.close()
    
    def get_charge(self):
        """Restituisce la percentuale di carica"""
        with self.lock:
            return self.current_charge
    
    def _monitor_loop(self):
        timeout = 1.0            # svuota FIFO se non arriva nulla per 1 s
        last_msg = time.time()

        while self.running:
            msg = self.can.ReturnData()
            ret = self.can.VIT7_ReceiveMessage(ctypes.byref(msg))

            if ret == 1:
                if msg.nType == 4:
                    self._process_message(msg)
                    last_msg = time.time()
                elif msg.nType == -999:      # overflow FIFO
                    self.can.clear_fifo()
            else:
                # niente ricevuto: se superato il timeout ⇒ pulizia
                if time.time() - last_msg > timeout:
                    self.can.clear_fifo()
                    last_msg = time.time()
                time.sleep(0.001)
    
    def _process_message(self, msg):
        """Elabora un messaggio CAN"""
        if (msg.nID == 0x638 and    # ID corretto
            msg.nDLC == 8 and       # DLC corretto
            not msg.nRTR):          # Non è remote frame
            
            charge_byte = msg.cData[3]  # Quarto byte
            charge = min(100, max(0, charge_byte))
            
            with self.lock:
                self.current_charge = charge
            
            
    
    


# Funzioni pubbliche per semplificare l'uso
def create_battery_monitor():
    """Factory per creare un monitor batteria pronto all'uso"""
    can = CANBusManager()
    can.connect()
    return BatteryMonitor(can)

if __name__ == "__main__":
    # Esempio di utilizzo diretto
    try:
        monitor = create_battery_monitor()
        monitor.start()
        
        print("Monitoraggio batteria avviato (CTRL+C per fermare)")
        while True:
            print(f"\rCarica: {monitor.get_charge()}%", end="")
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nInterruzione ricevuta...")
    finally:
        monitor.stop()
        monitor.can.disconnect()
