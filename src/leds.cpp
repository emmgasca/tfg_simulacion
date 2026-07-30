// Configura el LED RGB de estado: rojo = enviando datos por BLE en ese
// instante, azul = hay un cliente BLE conectado (ver taskBLE en BLE.cpp,
// que es quien enciende/apaga estos pines mientras corre).
#include "hal.h"

void setupLeds() {
    pinMode(LED_PIN_RGB_Red, OUTPUT);       
    pinMode(LED_PIN_RGB_Blue, OUTPUT);     

    digitalWrite(LED_PIN_RGB_Red, LOW);     
    digitalWrite(LED_PIN_RGB_Blue, HIGH);   
                                             
}