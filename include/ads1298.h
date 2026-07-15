#pragma once
#include <Arduino.h>
#include <SPI.h>
#include "hal.h"


extern SemaphoreHandle_t mutexSerial;

enum spi_command {
    WAKEUP = 0x02,
    STANDBY = 0x04,
    RESET = 0x06,
    START = 0x08,
    STOP = 0x0A,
    RDATAC = 0x10,
    SDATAC = 0x11,
    RDATA = 0x12,
    RREG = 0x20,
    WREG = 0x40
};

enum reg {
    ID = 0x00,
    CONFIG1 = 0x01,
    CONFIG2 = 0x02,
    CONFIG3 = 0x03,
    LOFF = 0x04,
    CHnSET = 0x04,
    CH1SET = CHnSET + 1,
    CH2SET = CHnSET + 2,
    CH3SET = CHnSET + 3,
    CH4SET = CHnSET + 4,
    CH5SET = CHnSET + 5,
    CH6SET = CHnSET + 6,
    CH7SET = CHnSET + 7,
    CH8SET = CHnSET + 8,
    RLD_SENSP = 0x0D,
    RLD_SENSN = 0x0E,
    LOFF_SENSP = 0x0F,
    LOFF_SENSN = 0x10,
    LOFF_FLIP = 0x11,
    LOFF_STATP = 0x12,
    LOFF_STATN = 0x13,
    ADSGPIO = 0x14,
    PACE = 0x15,
    RESP = 0x16,
    CONFIG4 = 0x17,
    WCT1 = 0x18,
    WCT2 = 0x19
};

class ADS1298 {
private:
    uint8_t _cs;
    uint8_t _reset;
    uint8_t _pwdn;
    uint8_t _start;
    uint8_t _drdy;
    SPISettings _spiConfig{1000000, MSBFIRST, SPI_MODE1};

    static int32_t combine24bit(uint8_t b0, uint8_t b1, uint8_t b2) {
        int32_t value = ((int32_t)b0 << 16) | ((int32_t)b1 << 8) | b2;
        if (value & 0x00800000) {
            value |= 0xFF000000;
        }
        return value;
    }

public:
    ADS1298(uint8_t cs, uint8_t reset, uint8_t pwdn, uint8_t start, uint8_t DRDY_n) {
        _cs = cs;
        _reset = reset;
        _pwdn = pwdn;
        _start = start;
        _drdy = DRDY_n;
    }

    bool begin();

    void sendCommand(uint8_t cmd) {
        SPI.beginTransaction(_spiConfig);
        digitalWrite(_cs, LOW);
        delayMicroseconds(2);
        SPI.transfer(cmd);
        delayMicroseconds(2);
        digitalWrite(_cs, HIGH);
        SPI.endTransaction();
    }

    void reset() {
        sendCommand(RESET);
    }

    void wakeup() {
        sendCommand(WAKEUP);
    }

    void stopReadDataContinuous() {
        sendCommand(SDATAC);
    }

    void startReadDataContinuous() {
        sendCommand(RDATAC);
    }

    void startConversion() {
        digitalWrite(_start, HIGH);
        delayMicroseconds(5);
        digitalWrite(_start, LOW);
        delayMicroseconds(5);
        sendCommand(START);
    }

    void writeRegister(uint8_t reg, uint8_t value) {
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

    uint8_t readRegister(uint8_t reg) {
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

    bool waitForDRDY(uint32_t timeoutMs = 20) {
        uint32_t start = millis();
        while (digitalRead(DRDY_n) == HIGH) {
            if (millis() - start > timeoutMs) {
                return false;
            }
            vTaskDelay(pdMS_TO_TICKS(1));
        }
        return true;
    }

    bool readChannels(int32_t canales[8]) {
        if (!waitForDRDY()) {
            return false;
        }

        uint8_t frame[25] = {0};
        SPI.beginTransaction(_spiConfig);
        digitalWrite(_cs, LOW);
        delayMicroseconds(2);
        SPI.transfer(RDATA);

        for (int i = 0; i < 25; ++i) {
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

    void conversion() {
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
};
