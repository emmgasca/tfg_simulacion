#include <Arduino.h>
#include <SPI.h>
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
bool ADS1298 :: waitForDRDY(uint32_t timeoutMs = 20) {
        uint32_t start = millis();
        while (digitalRead(DRDY_n) == HIGH) {
            if (millis() - start > timeoutMs) {
                return false;
            }
            vTaskDelay(pdMS_TO_TICKS(1));
        }
        return true;
    }
bool ADS1298 :: readChannels(int32_t canales[8]) {
        if (!waitForDRDY()) {
            return false;
        }

        uint8_t frame[27] = {0};
        SPI.beginTransaction(_spiConfig);
        digitalWrite(_cs, LOW);
        delayMicroseconds(2);
        SPI.transfer(RDATA);

        for (int i = 0; i < 27; ++i) {
            frame[i] = SPI.transfer(0x00);
        }

        delayMicroseconds(2);
        digitalWrite(_cs, HIGH);
        SPI.endTransaction();

        if (frame[0] == 0x00 || frame[0] == 0xFF) {
            return false;
        }

        bool hasMeaningfulData = false;
        for (int ch = 0; ch < 8; ++ch) {
            if (frame[1 + ch * 3] != 0x00 || frame[2 + ch * 3] != 0x00 || frame[3 + ch * 3] != 0x00) {
                hasMeaningfulData = true;
                break;
            }
        }
        if (!hasMeaningfulData) {
            return false;
        }

        for (int ch = 0; ch < 8; ++ch) {
            uint8_t b0 = frame[1 + ch * 3];
            uint8_t b1 = frame[2 + ch * 3];
            uint8_t b2 = frame[3 + ch * 3];
            canales[ch] = combine24bit(b0, b1, b2);
        }

        static uint32_t debugCount = 0;
        if ((debugCount++ % 5) == 0) {
            if (mutexSerial != NULL) {
                xSemaphoreTake(mutexSerial, portMAX_DELAY);
            }
            Serial.print("[ADS] RAW:");
            for (int i = 0; i < 25; ++i) {
                Serial.printf(" %02X", frame[i]);
            }
            Serial.print(" | CH:");
            for (int ch = 0; ch < 8; ++ch) {
                Serial.printf(" %ld", (long)canales[ch]);
            }
            Serial.println();
            if (mutexSerial != NULL) {
                xSemaphoreGive(mutexSerial);
            }
        }

        return true;
    }
void ADS1298:: conversion() {
        writeRegister(CONFIG1, 0x96);
        uint8_t comprobar = readRegister(CONFIG1);
        Serial.print("CONFIG1 leído: ");
        Serial.println(comprobar, HEX);

        writeRegister(CONFIG2, 0xC0);
        comprobar = readRegister(CONFIG2);
        Serial.print("CONFIG2 leído: ");
        Serial.println(comprobar, HEX);

        writeRegister(CONFIG3, 0xE0);
        comprobar = readRegister(CONFIG3);
        Serial.print("CONFIG3 leído: ");
        Serial.println(comprobar, HEX);

        writeRegister(LOFF, 0x00);
        writeRegister(ADSGPIO, 0x00);

        for (uint8_t ch = 0; ch < 8; ch++) {
            writeRegister(CH1SET + ch, 0x60);
        }
    }