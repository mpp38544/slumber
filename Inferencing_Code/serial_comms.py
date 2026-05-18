import serial
import json
import mysql.connector
import time
 
# Serial port configuration
SERIAL_PORT = "/dev/cu.usbmodem101"  # Find this (see below)
BAUD_RATE = 115200
 
# Database configuration
DB_CONFIG = {
    "host": "127.0.0.1",
    "user": "Arduino",
    "password": "password",
    "database": "db_health"
}
 
def find_serial_ports():
    """List available serial ports"""
    import subprocess
    result = subprocess.run(['ls', '/dev/cu.*'], capture_output=True, text=True)
    print("Available serial ports:")
    print(result.stdout)
 
def connect_to_esp32():
    """Connect to ESP32 via serial"""
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        print(f"Connected to ESP32 on {SERIAL_PORT}")
        return ser
    except Exception as e:
        print(f"Failed to connect: {e}")
        print("Available ports:")
        find_serial_ports()
        return None
 
def insert_to_database(hr, spo2, flex=None):
    """Insert sensor data into MySQL database"""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Insert data (flex column doesn't exist yet, so we skip it)
        query = "INSERT INTO tbl_vitals (hr, spo2, flex_voltage) VALUES (%s, %s, %s)"
        # Using flex value as temp for now (you may want to add flex column)
        cursor.execute(query, (hr, spo2, flex if flex else 0))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return True
    except Exception as e:
        print(f"Database error: {e}")
        return False
 
def main():
    print("Starting Serial to Database Bridge...")
    print("Make sure ESP32 is connected via USB\n")
    
    ser = connect_to_esp32()
    if not ser:
        return
    
    print("Waiting for data from ESP32...")
    print("Press Ctrl+C to exit\n")
    
    try:
        while True:
            if ser.in_waiting > 0:
                try:
                    line = ser.readline().decode('utf-8').strip()
                    
                    # Skip init messages
                    if "init" in line.lower() or "READY" in line:
                        print(f"ESP32: {line}")
                        continue
                    
                    # Parse JSON data
                    if line.startswith("{"):
                        data = json.loads(line)
                        hr = data.get('hr', 0)
                        spo2 = data.get('spo2', 0)
                        flex = data.get('flex', 0)
                        
                        print(f"Received: HR={hr}, SpO2={spo2}, Flex={flex:.2f}")
                        
                        # Insert into database
                        if insert_to_database(hr, spo2, flex):
                            print("✓ Inserted into database")
                        else:
                            print("✗ Failed to insert")
                    
                except json.JSONDecodeError:
                    print(f"Invalid data: {line}")
                except Exception as e:
                    print(f"Error: {e}")
            
            time.sleep(0.1)
    
    except KeyboardInterrupt:
        print("\nShutting down...")
        ser.close()
        print("Done!")
 
if __name__ == "__main__":
    main()