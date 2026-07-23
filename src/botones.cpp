#include "botones.h"
#include "hal.h"
extern SemaphoreHandle_t mutexSerial;

// true por defecto: los datos EMG fluyen desde el arranque sin tener que
// pulsar ningún botón. START/STOP es un complemento opcional para pausar o
// reanudar manualmente, no un requisito para que haya datos.
volatile bool grabando = true;
volatile uint32_t contadorMuestras = 0;

QueueHandle_t queueEventos;

static void taskButtons(void* param){
    uint32_t ultimoStartStop = 0;
    uint32_t ultimoMark = 0;
    const uint32_t debounce_ms = 200;

    bool prevStartStop = HIGH;
    bool prevMark = HIGH;

    while (true) {
        bool actualStartStop = digitalRead(START_STOP);
        bool actualMark = digitalRead(MARK);
        uint32_t ahora = millis();

        if (prevStartStop == HIGH && actualStartStop == LOW && ahora - ultimoStartStop > debounce_ms){

            ultimoStartStop = ahora;
            grabando = !grabando;

            if (mutexSerial != NULL) xSemaphoreTake(mutexSerial, portMAX_DELAY);
            Serial.printf("START/STOP pulsado -> grabando = %s\n", grabando ? "true" : "false");
            if (mutexSerial != NULL) xSemaphoreGive(mutexSerial);

            EventoBLE evento;
            if (grabando){
                contadorMuestras = 0;
                evento = { EVENT_START, contadorMuestras, ahora };
            } else{
                evento = { EVENT_STOP, contadorMuestras, ahora };
            }
            xQueueSend(queueEventos, &evento, 0);
        }

        if(prevMark == HIGH && actualMark == LOW && ahora - ultimoMark > debounce_ms){

            ultimoMark = ahora;
            if(grabando){
                if (mutexSerial != NULL) xSemaphoreTake(mutexSerial, portMAX_DELAY);
                Serial.printf("MARK registrado en muestra %lu\n", (unsigned long)contadorMuestras);
                if (mutexSerial != NULL) xSemaphoreGive(mutexSerial);

                EventoBLE evento = { EVENT_MARK, contadorMuestras, ahora };
                xQueueSend(queueEventos, &evento, 0);
            } else {
                Serial.println("MARK ignorado: no hay grabacion activa");
            }
        }

        prevStartStop = actualStartStop;
        prevMark = actualMark;

        vTaskDelay(pdMS_TO_TICKS(5));
    }
}

void setupBotones () {
    queueEventos = xQueueCreate(10, sizeof(EventoBLE));

    pinMode(START_STOP, INPUT_PULLUP);
    pinMode(MARK, INPUT_PULLUP);

    xTaskCreate(taskButtons, "taskButtons", 2048, NULL, 1, NULL);
}