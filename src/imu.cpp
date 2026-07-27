#include "imu.h"
#include "hal.h"
#include <Wire.h>

// Direccion I2C del ISM330DLC: depende de como este cableado el pin SDO/SA0
// (a GND -> 0x6A, a VDD -> 0x6B). Si WHO_AM_I no coincide al arrancar,
// revisar el esquematico y cambiar aqui.
static constexpr uint8_t IMU_I2C_ADDR = 0x6A;

static constexpr uint8_t REG_WHO_AM_I    = 0x0F;
static constexpr uint8_t WHO_AM_I_ESPERADO = 0x6A;
static constexpr uint8_t REG_CTRL1_XL    = 0x10;
static constexpr uint8_t REG_OUTX_L_A    = 0x28;

// Sensibilidad del acelerometro a fondo de escala +/-2g (datasheet ISM330DLC).
static constexpr float SENSIBILIDAD_G = 0.000061f;

static uint8_t leerRegistro(uint8_t reg) {
    Wire.beginTransmission(IMU_I2C_ADDR);
    Wire.write(reg);
    Wire.endTransmission(false);  // repeated start, sin soltar el bus
    Wire.requestFrom(IMU_I2C_ADDR, (uint8_t)1);
    return Wire.available() ? Wire.read() : 0xFF;
}

static void escribirRegistro(uint8_t reg, uint8_t valor) {
    Wire.beginTransmission(IMU_I2C_ADDR);
    Wire.write(reg);
    Wire.write(valor);
    Wire.endTransmission();
}

bool imuBegin() {
    Wire.begin(IMU_SDA, IMU_SCL);
    Wire.setClock(400000);  // I2C fast mode, soportado por el ISM330DLC

    uint8_t whoAmI = leerRegistro(REG_WHO_AM_I);
    if (whoAmI != WHO_AM_I_ESPERADO) {
        Serial.printf("IMU: WHO_AM_I = 0x%02X (se esperaba 0x%02X) -- revisar direccion I2C/cableado\n",
                      whoAmI, WHO_AM_I_ESPERADO);
        return false;
    }

    // CTRL1_XL: ODR_XL = 0100 (104 Hz), FS_XL = 00 (+/-2g), filtro por defecto -> 0x40
    escribirRegistro(REG_CTRL1_XL, 0x40);
    return true;
}

bool imuLeerAcelerometro(float &x, float &y, float &z) {
    Wire.beginTransmission(IMU_I2C_ADDR);
    Wire.write(REG_OUTX_L_A);
    if (Wire.endTransmission(false) != 0) {
        return false;
    }
    // Lectura en rafaga de los 6 bytes (X,Y,Z, 2 bytes cada uno): el ISM330DLC
    // autoincrementa la direccion de registro por defecto (IF_INC=1 de fabrica).
    if (Wire.requestFrom(IMU_I2C_ADDR, (uint8_t)6) != 6) {
        return false;
    }

    uint8_t buf[6];
    for (uint8_t i = 0; i < 6; i++) {
        buf[i] = Wire.read();
    }

    int16_t rawX = (int16_t)((buf[1] << 8) | buf[0]);
    int16_t rawY = (int16_t)((buf[3] << 8) | buf[2]);
    int16_t rawZ = (int16_t)((buf[5] << 8) | buf[4]);

    x = rawX * SENSIBILIDAD_G;
    y = rawY * SENSIBILIDAD_G;
    z = rawZ * SENSIBILIDAD_G;
    return true;
}
