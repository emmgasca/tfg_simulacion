#pragma once
#include <Arduino.h>
#include <cstdint>
#include <hal/gpio_types.h>

// ==========================================
// SELECCIÓN DE HARDWARE
// ==========================================
//#define BOARD_DEV_KIT      // placa de pruebas actual
//#define PLACA // PCB definitiva (descomentar el martes)
#define PLACA_2
// ==========================================
// MAPEO DE PINES SEGÚN LA PLACA
// ==========================================
#if defined(BOARD_DEV_KIT)
    constexpr uint8_t LED_PIN_RGB_White = GPIO_NUM_4;   
    constexpr uint8_t LED_PIN_RGB_Green = GPIO_NUM_5;
    constexpr uint8_t LED_PIN_RGB_Red   = GPIO_NUM_6;
    constexpr uint8_t LED_PIN_RGB_Blue  = GPIO_NUM_7;
    constexpr uint8_t BOOT_BTN          = GPIO_NUM_0;
    constexpr uint8_t BTN2              = GPIO_NUM_2;
    constexpr uint8_t BTN3              = GPIO_NUM_15;
    #define HAS_BOOT_BTN 1

    // SPI e I2C — no conectados físicamente, solo para compilar en simulación
    constexpr uint8_t PIN_SPI_MOSI = GPIO_NUM_11;
    constexpr uint8_t PIN_SPI_MISO = GPIO_NUM_13;
    constexpr uint8_t PIN_SPI_SCK  = GPIO_NUM_12;
    constexpr uint8_t ADS1298_CS   = GPIO_NUM_10;
    constexpr uint8_t IMU_SDA      = GPIO_NUM_8;
    constexpr uint8_t IMU_SCL      = GPIO_NUM_9;

#elif defined(PLACA)
    constexpr uint8_t LED_PIN_RGB_Green = GPIO_NUM_14;
    constexpr uint8_t LED_PIN_RGB_Red   = GPIO_NUM_16;
    constexpr uint8_t LED_PIN_RGB_Blue  = GPIO_NUM_15;
    constexpr uint8_t START_STOP        = GPIO_NUM_17;  // KEY1
    constexpr uint8_t MARK              = GPIO_NUM_21;  // KEY2

    #define HAS_BOOT_BTN 1

    constexpr uint8_t PIN_SPI_MOSI = GPIO_NUM_11;
    constexpr uint8_t PIN_SPI_MISO = GPIO_NUM_13;
    constexpr uint8_t PIN_SPI_SCK  = GPIO_NUM_12;
    constexpr uint8_t IMU_SCL      = GPIO_NUM_2;
    constexpr uint8_t IMU_SDA      = GPIO_NUM_3;
  
    constexpr uint8_t FSSPI_CSO_n    = GPIO_NUM_10;
    constexpr uint8_t ADS_Reset_n    = GPIO_NUM_6;
    constexpr uint8_t PWDN_n         = GPIO_NUM_7;
    constexpr uint8_t Start_Data     = GPIO_NUM_8;   
    constexpr uint8_t DRDY_n         = GPIO_NUM_5;

#elif defined(PLACA_2)

    constexpr uint8_t LED_PIN_RGB_Green = GPIO_NUM_18; // Pin del LED RGB Status
    constexpr uint8_t LED_PIN_RGB_Red = GPIO_NUM_16;   // Pin del LED RGB Status
    constexpr uint8_t LED_PIN_RGB_Blue = GPIO_NUM_17;  // Pin del LED RGB Status
    #define HAS_BOOT_BTN 0
    
    // Definiciones de pines del ADS1298
    constexpr uint8_t FSSPI_HD = GPIO_NUM_9;     // Pin de Hardware Data para el SPI
    constexpr uint8_t FSSPI_CSO_n = GPIO_NUM_10; // Pin de Chip Select (CS) activo bajo para el SPI
    constexpr uint8_t FSSPI_MISO = GPIO_NUM_13;  // Pin de Master In Slave Out (MISO) para el SPI
    constexpr uint8_t FSSPI_CLK = GPIO_NUM_12;   // Pin de reloj (SCK) para el SPI
    constexpr uint8_t FSSPI_MOSI = GPIO_NUM_11;  // Pin de Master Out Slave In (MOSI) para el SPI
    constexpr uint8_t FSSPI_WP = GPIO_NUM_14;    // Pin de Write Protect (WP) para el SPI

    constexpr uint8_t Start_Data = GPIO_NUM_15; // Comando para detener la transmisión continua de datos en el ADS1298
    constexpr uint8_t ADS_Reset_n = GPIO_NUM_2; // Pin de reset para el ADS1298
    constexpr uint8_t PWDN_n = GPIO_NUM_1;      // Pin de Power Down (PWDN) para el ADS1298
    constexpr uint8_t DRDY_n = GPIO_NUM_5;      // Pin de Data Ready (DRDY) para el ADS1298
    constexpr uint8_t StartConversion = GPIO_NUM_8; // Pin para iniciar la conversión en el ADS1298

#else
    #error "Define una placa válida: BOARD_DEV_KIT o BOARD_RIGIDA_V1"
#endif

