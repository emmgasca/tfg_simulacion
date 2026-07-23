#pragma once
#include <Arduino.h>

enum TipoEvento : uint8_t {
    EVENT_START = 0, 
    EVENT_STOP = 1, 
    EVENT_MARK = 2
};

struct  EventoBLE{
    uint8_t tipo;
    uint32_t muestra;
    uint32_t timestamp_ms;

};

extern volatile bool grabando;
extern volatile uint32_t contadorMuestras;
extern QueueHandle_t queueEventos;

void setupBotones();
