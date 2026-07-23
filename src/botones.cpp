#include "botones.h"
#include"hal.h"
 
volatile bool grabando = false;
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

        EventoBLE evento;   
        if (grabando){
            contadorMuestras = 0;
            evento =
            {
                EVENT_START,contadorMuestras, ahora
            };
        } else{
            evento =
            {
                EVENT_STOP, contadorMuestras, ahora
            };
        }
        xQueueSend(queueEventos, &evento, 0);
    }
    
    if(prevMark == HIGH && actualMark == LOW && ahora-ultimoMark > debounce_ms){

        ultimoMark = ahora;
        if(grabando){
            EventoBLE evento = {
                EVENT_MARK,contadorMuestras, ahora
            };
            xQueueSend(queueEventos, &evento,0);
        }
    }
    prevStartStop = actualStartStop;
    prevMark = actualMark;

    vTaskDelay(pdMS_TO_TICKS(20));
}
}
void setupBotones () {
    queueEventos = xQueueCreate(10,sizeof(EventoBLE));

    pinMode (START_STOP, INPUT_PULLUP);
    pinMode (MARK,INPUT_PULLUP);

    xTaskCreate(taskButtons,"taskButtons",2048,NULL,1,NULL);
};
