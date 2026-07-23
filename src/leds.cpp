#include "hal.h"              

void setupLeds() {
    pinMode(LED_PIN_RGB_Red, OUTPUT);       
    pinMode(LED_PIN_RGB_Blue, OUTPUT);     

    digitalWrite(LED_PIN_RGB_Red, LOW);     
    digitalWrite(LED_PIN_RGB_Blue, HIGH);   
                                             
}