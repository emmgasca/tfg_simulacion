// TFG_simulacion_v4
// Estado: cola entre tareaSimulacion y tareaSerial, un solo canal
#include <Arduino.h>
#include "pins.h"

enum Estado { STANDBY, GRABANDO, ENVIANDO };
Estado estadoActual = STANDBY;
SemaphoreHandle_t mutexSerial;
QueueHandle_t colaEMG;

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
                    case STANDBY:  estadoActual = GRABANDO; xSemaphoreTake(mutexSerial, portMAX_DELAY); Serial.println("→ GRABANDO"); xSemaphoreGive(mutexSerial); break;
                    case GRABANDO: estadoActual = ENVIANDO; xSemaphoreTake(mutexSerial, portMAX_DELAY); Serial.println("→ ENVIANDO"); xSemaphoreGive(mutexSerial); break;
                    case ENVIANDO: estadoActual = STANDBY;  xSemaphoreTake(mutexSerial, portMAX_DELAY); Serial.println("→ STANDBY");  xSemaphoreGive(mutexSerial); break;
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
            int muestra = random(-1000, 1000);
            xQueueSend(colaEMG, &muestra, 0);
        }
        vTaskDelay(pdMS_TO_TICKS(500));
    }
}

void tareaSerial(void* params) {
    int muestra;
    while (true) {
        if (xQueueReceive(colaEMG, &muestra, pdMS_TO_TICKS(100))) {
            xSemaphoreTake(mutexSerial, portMAX_DELAY);
            Serial.println("EMG: " + String(muestra));
            xSemaphoreGive(mutexSerial);
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
    colaEMG = xQueueCreate(10, sizeof(int));
    xTaskCreate(tareaBoton,      "Boton",      2048, NULL, 1, NULL);
    xTaskCreate(tareaSimulacion, "Simulacion", 2048, NULL, 1, NULL);
    xTaskCreate(tareaSerial,     "Serial",     2048, NULL, 1, NULL);
    actualizarLED();
    Serial.println("Sistema iniciado — STANDBY");
}

void loop() {
    vTaskDelay(pdMS_TO_TICKS(1000));
}