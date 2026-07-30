// Punto de entrada del firmware. Aqui solo se inicializa cada modulo (ADC,
// IMU, LEDs, botones) y se arranca BLE; la logica de cada uno vive en su
// propio archivo (ads1298.cpp, imu.cpp, botones.cpp, BLE.cpp).
#include <Arduino.h>
#include "ads1298.h"
#include "hal.h"
#include "BLE.h"
#include "botones.h"
#include "imu.h"

// Mutex para proteger Serial entre tareas (lo usa ads1298.cpp)
SemaphoreHandle_t mutexSerial = NULL;

// Instancia del ADS1298 con los pines de hal.h (PLACA)
ADS1298 ads(FSSPI_CSO_n, ADS_Reset_n, PWDN_n, Start_Data, DRDY_n);

void setup() {
    Serial.begin(115200);
    delay(3000);
    Serial.println("=== Arranque firmware ===");

    mutexSerial = xSemaphoreCreateMutex();

    setupLeds();
    setupBotones();

    // Inicializar el ADS1298 (reset, config, arranque)
    bool arranqueCorrecto = ads.begin();
    if (arranqueCorrecto) {
        Serial.println("ADS1298 begin() OK");
    } else {
        Serial.println("ADS1298 begin() FALLO");
    }

    // Inicializar el IMU (I2C) - si falla, taskIMU simplemente no encontrará
    // muestras nuevas y no se enviará nada por esa característica.
    if (imuBegin()) {
        Serial.println("IMU begin() OK");
    } else {
        Serial.println("IMU begin() FALLO");
    }

    // Arrancar BLE + tareas FreeRTOS
    bleSetup();
}

void loop() {
    delay(1000);
}