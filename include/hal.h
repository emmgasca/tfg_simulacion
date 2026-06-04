#pragma once
#include <Arduino.h>
#include <cstdint>
#include <hal/gpio_types.h>

// ==========================================
// SELECCIÓN DE HARDWARE
// ==========================================
#define BOARD_DEV_KIT      // placa de pruebas actual
// #define BOARD_RIGIDA_V1 // PCB definitiva (descomentar el martes)

// ==========================================
// MAPEO DE PINES SEGÚN LA PLACA
// ==========================================
#if defined(BOARD_DEV_KIT)
    constexpr uint8_t LED_PIN_RGB_White = GPIO_NUM_4;
    constexpr uint8_t LED_PIN_RGB_Green = GPIO_NUM_5;
    constexpr uint8_t LED_PIN_RGB_Red   = GPIO_NUM_6;
    constexpr uint8_t LED_PIN_RGB_Blue  = GPIO_NUM_7;
    constexpr uint8_t LED_PIN_Orange    = GPIO_NUM_1;
    constexpr uint8_t BOOT_BTN          = GPIO_NUM_0;

    // SPI e I2C — no conectados físicamente, solo para compilar en simulación
    constexpr uint8_t PIN_SPI_MOSI = GPIO_NUM_11;
    constexpr uint8_t PIN_SPI_MISO = GPIO_NUM_13;
    constexpr uint8_t PIN_SPI_SCK  = GPIO_NUM_12;
    constexpr uint8_t ADS1298_CS   = GPIO_NUM_10;
    constexpr uint8_t IMU_SDA      = GPIO_NUM_8;
    constexpr uint8_t IMU_SCL      = GPIO_NUM_9;

#elif defined(BOARD_RIGIDA_V1)
    // LED verde = alimentación, siempre encendido, no controlable
    constexpr uint8_t LED_PIN_RGB_Red   = GPIO_NUM_16;
    constexpr uint8_t LED_PIN_RGB_Blue  = GPIO_NUM_15;
    constexpr uint8_t BOOT_BTN          = GPIO_NUM_17;  // KEY1
    constexpr uint8_t BTN2              = GPIO_NUM_21;  // KEY2

    constexpr uint8_t PIN_SPI_MOSI = GPIO_NUM_19;
    constexpr uint8_t PIN_SPI_MISO = GPIO_NUM_21;
    constexpr uint8_t PIN_SPI_SCK  = GPIO_NUM_20;
    constexpr uint8_t ADS1298_CS   = GPIO_NUM_18;
    constexpr uint8_t IMU_SDA      = GPIO_NUM_2;
    constexpr uint8_t IMU_SCL      = GPIO_NUM_3;

#else
    #error "Define una placa válida: BOARD_DEV_KIT o BOARD_RIGIDA_V1"
#endif