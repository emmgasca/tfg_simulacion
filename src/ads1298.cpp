#include <Arduino.h>
#include <SPI.h>
#include <cstring>
#include "ads1298.h"
#include "hal.h"

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
void ADS1298::reset() {
        sendCommand(RESET);
    }

void ADS1298::wakeup() {
    sendCommand(WAKEUP);
}

void ADS1298::stopReadDataContinuous() {
    sendCommand(SDATAC);
}

void ADS1298::startReadDataContinuous() {
    sendCommand(RDATAC);
    }

void ADS1298 :: startConversion () {
        digitalWrite(_start, HIGH);
        delayMicroseconds(5);
        digitalWrite(_start, LOW);
        delayMicroseconds(5);
        sendCommand(START);
    }
void ADS1298 :: writeRegister(uint8_t reg, uint8_t value) {
        SPI.beginTransaction(_spiConfig);
        digitalWrite(_cs, LOW);
        delayMicroseconds(2);
        SPI.transfer(WREG | (reg & 0x1F));
        SPI.transfer(0x00);
        SPI.transfer(value);
        delayMicroseconds(2);
        digitalWrite(_cs, HIGH);
        SPI.endTransaction();
    }
uint8_t ADS1298::readRegister(uint8_t reg) {
        uint8_t respuesta = 0x00;
        for (int attempt = 0; attempt < 3; ++attempt) {
            SPI.beginTransaction(_spiConfig);
            digitalWrite(_cs, LOW);
            delayMicroseconds(2);
            SPI.transfer(RREG | (reg & 0x1F));
            SPI.transfer(0x00);
            delayMicroseconds(10);
            respuesta = SPI.transfer(0x00);
            delayMicroseconds(2);
            digitalWrite(_cs, HIGH);
            SPI.endTransaction();
            if (respuesta != 0x00) {
                break;
            }
            delay(1);
        }
        return respuesta;
    }
bool ADS1298:: waitForDRDY (uint32_t timeoutMs) {
        uint32_t start = millis();
        while (digitalRead(_drdy) == HIGH) {
            if (millis() - start > timeoutMs) {
                return false;
            }
            delayMicroseconds(100);
        }
        return true;
    }
bool ADS1298 :: readChannels(uint8_t muestra[BYTES_POR_MUESTRA]) {
        if (!waitForDRDY()) {
            return false;
        }

        // Frame SPI completo: 3 bytes de status + 8 canales x 3 bytes = 27 bytes.
        uint8_t frame[3 + BYTES_POR_MUESTRA] = {0};
        SPI.beginTransaction(_spiConfig);
        digitalWrite(_cs, LOW);
        delayMicroseconds(2);
        SPI.transfer(RDATA);

        for (int i = 0; i < 3 + BYTES_POR_MUESTRA; ++i) {
            frame[i] = SPI.transfer(0x00);
        }

        delayMicroseconds(2);
        digitalWrite(_cs, HIGH);
        SPI.endTransaction();

        // Sincronismo de trama: el status word siempre empieza en "1100" (nibble alto
        // de frame[0] = 0xC), según la Figura 61 del datasheet del ADS1298. Si no es así,
        // la trama SPI está desalineada (o son datos basura) y se descarta.
        if ((frame[0] & 0xF0) != 0xC0) {
            return false;
        }

        bool hasMeaningfulData = false;
        for (int i = 3; i < 3 + BYTES_POR_MUESTRA; ++i) {
            if (frame[i] != 0x00) {
                hasMeaningfulData = true;
                break;
            }
        }
        if (!hasMeaningfulData) {
            return false;
        }

        // Se descartan los 3 bytes de status; se conservan los 24 bytes de canales tal cual.
        memcpy(muestra, frame + 3, BYTES_POR_MUESTRA);

        static uint32_t debugCount = 0;
        if ((debugCount++ % 200) == 0) {
            if (mutexSerial != NULL) {
                xSemaphoreTake(mutexSerial, portMAX_DELAY);
            }
            Serial.print("Bytes crudos:");
            for (int i = 0; i < 3 + BYTES_POR_MUESTRA; ++i) {
                Serial.printf(" %02X", frame[i]);
            }
            Serial.print(" | CH:");
            for (int ch = 0; ch < NUM_CANALES; ++ch) {
                int32_t valor = combine24bit(muestra[ch * 3], muestra[ch * 3 + 1], muestra[ch * 3 + 2]);
                Serial.printf(" %ld", (long)valor);
            }
            Serial.println();
            if (mutexSerial != NULL) {
                xSemaphoreGive(mutexSerial);
            }
        }

        return true;
    }
void ADS1298:: conversion() {
        writeRegister(CONFIG1, 0x84);
        uint8_t comprobar = readRegister(CONFIG1);
        Serial.print("CONFIG1 leído: ");
        Serial.println(comprobar, HEX);

        //apago generador de test
        writeRegister(CONFIG2, 0x00);
        comprobar = readRegister(CONFIG2);
        Serial.print("CONFIG2 leído: ");
        Serial.println(comprobar, HEX);

        writeRegister(CONFIG3, 0b11001001);
        comprobar = readRegister(CONFIG3);
        Serial.print("CONFIG3 leído: ");
        Serial.println(comprobar, HEX);

        writeRegister(LOFF, 0x00);
        writeRegister(ADSGPIO, 0x00);

        for (uint8_t ch = 0; ch < 8; ch++) {
            writeRegister(CH1SET + ch, 0x00);
        }

        writeRegister(RLD_SENSN, 0x00);
        writeRegister(RLD_SENSP, 0x00);
    }