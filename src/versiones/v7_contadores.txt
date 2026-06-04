// TFG_simulacion_v7
// Estado: sistema completo con contadores y ENVIANDO funcional
#include <Arduino.h>
#include "pins.h"

enum Estado { STANDBY, GRABANDO, ENVIANDO };
Estado estadoActual = STANDBY;
SemaphoreHandle_t mutexSerial;
QueueHandle_t colaEMG;
QueueHandle_t colaIMU;
uint32_t contadorEMG = 0;
uint32_t contadorIMU = 0;

struct MuestraEMG {
    int32_t canal[8];
    uint32_t timestamp;
};
struct MuestraIMU {
    int16_t acc[3];
    int16_t gyr[3];
    uint32_t timestamp;
};

void actualizarLED() {
    digitalWrite(LED_PIN_RGB_Red,   LOW);
    digitalWrite(LED_PIN_RGB_Green, LOW);
    digitalWrite(LED_PIN_RGB_Blue,  LOW);
    switch (estadoActual) {
        case STANDBY:  digitalWrite(LED_PIN_RGB_Green, HIGH); break;
        case GRABANDO: digitalWrite(LED_PIN_RGB_Blue,  HIGH); break;
        case ENVIANDO: digitalWrite(LED_PIN_RGB_Red,   HIGH); break;
    }
}

void tareaBoton(void* params) {
    while (true) {
        if (digitalRead(BOOT_BTN) == LOW) {
            delay(50);
            if (digitalRead(BOOT_BTN) == LOW) {
                while (digitalRead(BOOT_BTN) == LOW);
                switch (estadoActual) {
                    case STANDBY:
                        estadoActual = GRABANDO;
                        xSemaphoreTake(mutexSerial, portMAX_DELAY);
                        Serial.println("==================");
                        Serial.println("→ GRABANDO");
                        Serial.println("==================");
                        xSemaphoreGive(mutexSerial);
                        break;
                    case GRABANDO:
                        estadoActual = ENVIANDO;
                        xSemaphoreTake(mutexSerial, portMAX_DELAY);
                        Serial.println("==================");
                        Serial.println("→ ENVIANDO");
                        Serial.println("Muestras EMG: " + String(contadorEMG));
                        Serial.println("Muestras IMU: " + String(contadorIMU));
                        Serial.println("==================");
                        xSemaphoreGive(mutexSerial);
                        break;
                    case ENVIANDO:
                        estadoActual = STANDBY;
                        contadorEMG = 0;
                        contadorIMU = 0;
                        xSemaphoreTake(mutexSerial, portMAX_DELAY);
                        Serial.println("==================");
                        Serial.println("→ STANDBY");
                        Serial.println("==================");
                        xSemaphoreGive(mutexSerial);
                        break;
                }
                actualizarLED();
            }
        }
        vTaskDelay(pdMS_TO_TICKS(10));
    }
}

void tareaSimulacion(void* params) {
    while (true) {
        if (estadoActual == GRABANDO) {
            MuestraEMG muestra;
            for (int i = 0; i < 8; i++)
                muestra.canal[i] = random(-1000, 1000);
            muestra.timestamp = millis();
            xQueueSend(colaEMG, &muestra, 0);
        }
        vTaskDelay(pdMS_TO_TICKS(500));
    }
}

void tareaIMU(void* params) {
    while (true) {
        if (estadoActual == GRABANDO) {
            MuestraIMU muestra;
            for (int i = 0; i < 3; i++) {
                muestra.acc[i] = random(-2000, 2000);
                muestra.gyr[i] = random(-500, 500);
            }
            muestra.timestamp = millis();
            xQueueSend(colaIMU, &muestra, 0);
        }
        vTaskDelay(pdMS_TO_TICKS(10));
    }
}

void tareaSerial(void* params) {
    MuestraEMG muestra;
    MuestraIMU muestraIMU;
    while (true) {
        if (xQueueReceive(colaEMG, &muestra, pdMS_TO_TICKS(100))) {
            xSemaphoreTake(mutexSerial, portMAX_DELAY);
            Serial.print("EMG: ");
            for (int i = 0; i < 8; i++) {
                Serial.print(muestra.canal[i]);
                Serial.print(" ");
            }
            Serial.println();
            xSemaphoreGive(mutexSerial);
            contadorEMG++;
        }
        if (xQueueReceive(colaIMU, &muestraIMU, pdMS_TO_TICKS(100))) {
            xSemaphoreTake(mutexSerial, portMAX_DELAY);
            Serial.print("IMU: ");
            for (int i = 0; i < 3; i++) {
                Serial.print(muestraIMU.acc[i]);
                Serial.print(" ");
            }
            Serial.print(" | ");
            for (int i = 0; i < 3; i++) {
                Serial.print(muestraIMU.gyr[i]);
                Serial.print(" ");
            }
            Serial.println();
            xSemaphoreGive(mutexSerial);
            contadorIMU++;
        }
    }
}

void setup() {
    Serial.begin(115200);
    pinMode(LED_PIN_RGB_Red,   OUTPUT);
    pinMode(LED_PIN_RGB_Green, OUTPUT);
    pinMode(LED_PIN_RGB_Blue,  OUTPUT);
    pinMode(BOOT_BTN, INPUT_PULLUP);
    mutexSerial = xSemaphoreCreateMutex();
    colaEMG = xQueueCreate(10, sizeof(MuestraEMG));
    colaIMU = xQueueCreate(5,  sizeof(MuestraIMU));
    xTaskCreate(tareaBoton,      "Boton",      2048, NULL, 1, NULL);
    xTaskCreate(tareaSimulacion, "Simulacion", 2048, NULL, 1, NULL);
    xTaskCreate(tareaIMU,        "IMU",        2048, NULL, 1, NULL);
    xTaskCreate(tareaSerial,     "Serial",     2048, NULL, 1, NULL);
    actualizarLED();
    Serial.println("Sistema iniciado — STANDBY");
}

void loop() {
    vTaskDelay(pdMS_TO_TICKS(1000));
}