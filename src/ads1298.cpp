#include <Arduino.h>
#include <SPI.h>
#include "ads1298.h"

bool ADS1298::begin() {
    pinMode(_cs, OUTPUT);
        pinMode(_reset, OUTPUT);
        pinMode(_pwdn, OUTPUT);
        pinMode(_start, OUTPUT);
        pinMode(_drdy, INPUT);

        digitalWrite(_cs, HIGH);
        digitalWrite(_pwdn, HIGH);
        digitalWrite(_start, LOW);

        digitalWrite(_reset, LOW);
        delayMicroseconds(10);
        digitalWrite(_reset, HIGH);
        delay(4);

        SPI.begin(FSSPI_CLK, FSSPI_MISO, FSSPI_MOSI, FSSPI_CSO_n);
        reset();
        delay(2);
        wakeup();
        delay(2);
        stopReadDataContinuous();
        conversion();
        startConversion();
        delay(5);
        return true;
}

void ADS1298::sendCommand(uint8_t cmd){
        SPI.beginTransaction(_spiConfig);
        digitalWrite(_cs, LOW);
        delayMicroseconds(2);
        SPI.transfer(cmd);
        delayMicroseconds(2);
        digitalWrite(_cs, HIGH);
        SPI.endTransaction();
    }