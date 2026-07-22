"""Parametros de captura compartidos por guardar.py, analizar.py y snr.py.

Mantenerlos en un unico sitio evita que la Fs asumida en el analisis
diverja de la tasa real configurada en el firmware.

IMPORTANTE: CONFIG1 en ads1298.cpp esta puesto a 0x84 (HR=1, DR[2:0]=100),
que segun el datasheet del ADS1298 corresponde a 4000 SPS nominales en el
ADC. La tasa que realmente llega por BLE puede ser distinta (overhead de
notificacion, cola, etc.) -- usa el "Tasa real EMG" que imprime el
firmware por Serial (BLE.cpp, taskEMG) para confirmar el valor correcto.
"""

FRECUENCIA_MUESTREO_EMG = 2000  # Hz -- verificar contra el log de Serial
