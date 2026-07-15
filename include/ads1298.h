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

    void sendCommand(uint8_t cmd);

    void reset() ;

    void wakeup();

    void stopReadDataContinuous() ;

    void startReadDataContinuous();

    void startConversion();

    void writeRegister(uint8_t reg, uint8_t value);

    uint8_t readRegister(uint8_t reg);

    bool waitForDRDY(uint32_t timeoutMs = 20);

    bool readChannels(int32_t canales[8]);
    void conversion();
};
