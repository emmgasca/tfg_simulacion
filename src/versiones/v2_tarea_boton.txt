// TFG_simulacion_v2
// Estado: botón movido a tareaBoton, loop() vacío
#include <Arduino.h>
#include "pins.h"

enum Estado { STANDBY, GRABANDO, ENVIANDO };
Estado estadoActual = STANDBY;

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
                    case STANDBY:  estadoActual = GRABANDO; Serial.println("→ GRABANDO"); break;
                    case GRABANDO: estadoActual = ENVIANDO; Serial.println("→ ENVIANDO"); break;
                    case ENVIANDO: estadoActual = STANDBY;  Serial.println("→ STANDBY");  break;
                }
                actualizarLED();
            }
        }
        vTaskDelay(pdMS_TO_TICKS(10));
    }
}

void setup() {
    Serial.begin(115200);
    pinMode(LED_PIN_RGB_Red,   OUTPUT);
    pinMode(LED_PIN_RGB_Green, OUTPUT);
    pinMode(LED_PIN_RGB_Blue,  OUTPUT);
    pinMode(BOOT_BTN, INPUT_PULLUP);
    xTaskCreate(tareaBoton, "Boton", 2048, NULL, 1, NULL);
    actualizarLED();
    Serial.println("Sistema iniciado — STANDBY");
}

void loop() {
    vTaskDelay(pdMS_TO_TICKS(1000));
}