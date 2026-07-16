#include <Arduino.h>
#include "ads1298.h"
#include "hal.h"
#include "BLE.h"

// Mutex para proteger Serial entre tareas (lo usa ads1298.cpp)
SemaphoreHandle_t mutexSerial = NULL;

// Instancia del ADS1298 con los pines de hal.h (PLACA)
ADS1298 ads(FSSPI_CSO_n, ADS_Reset_n, PWDN_n, Start_Data, DRDY_n);

void setup() {
    Serial.begin(115200);
    delay(3000);
    Serial.println("=== Arranque firmware ===");

  
    mutexSerial = xSemaphoreCreateMutex();

    // Inicializar el ADS1298 (reset, config, arranque)
    bool arranqueCorrecto = ads.begin();
    if (arranqueCorrecto) {
        Serial.println("ADS1298 begin() OK");
    } else {
        Serial.println("ADS1298 begin() FALLO");
    }

    // Arrancar BLE + tareas FreeRTOS
    bleSetup();
}

void loop() {
    int32_t canales[8];
    bool leido = ads.readChannels(canales);

    if (leido) {
        Serial.print("Canales:");
        for (int ch = 0; ch < 8; ch++) {
            Serial.print(" ");
            Serial.print(canales[ch]);
        }
        Serial.println();
    } else {
        Serial.println("Lectura fallida");
    }

    delay(200);
}