# -------------------- CONFIG --------------------
MAX_SIZE = 8
COM_PORT = "COM4"
BAUD_RATE = 460800
PRINT_ADC_MT_IN_TERMINAL = 0
GRID_ROWS = 10
GRID_COLS = 10
SCAN_MODE_DURATION = 60      # seconds
SCAN_TIMING_INTERVAL = 1000  # ms
DEMO_MODE = False

# AD7680 16-bit ADC + DRV5053 Hall sensor constants
ADC_QUIESCENT = 0            # counts at zero field (~1V on 3.3V ref)
ADC_COUNTS_PER_MT = 400      # counts per millitesla (23mV/mT / 76uV per count)
ADC_MAX = 42000
ADC_MIN = 0

# Display range in mT
MT_MIN = -140.0
MT_MAX = -45.0