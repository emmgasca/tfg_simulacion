#include <Arduino.h>
#include <SPI.h>
#include <cstring>
#include "ads1298.h"
#include "hal.h"

// Esta función se ejecuta sola cada vez que el ADS1298 avisa (bajando el
// pin DRDY) de que tiene un dato nuevo listo -- miles de veces por
// segundo. Por eso tiene que ser mínima: aquí solo se avisa a la tarea
// que está esperando ese dato (más abajo), nada más de trabajo.
//
// Detalle técnico: tiene que estar marcada IRAM_ATTR, es decir, vivir en
// una zona de memoria especial en vez de en la flash normal. Si no lo
// estuviera, y la interrupción saltara justo cuando la flash está
// momentáneamente desactivada (pasa a veces mientras el Bluetooth
// escribe datos), el ESP32 se reiniciaría solo con un error críptico
// ("Guru Meditation Error").
static void IRAM_ATTR ads1298_drdy_isr() {
    ads.onDrdyInterrupt();
}

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

        // Semáforo dado por la ISR de DRDY (flanco de bajada). waitForDRDY()
        // bloquea sobre él en vez de hacer polling activo: la tarea cede la
        // CPU de verdad entre muestras (permite que IDLE corra y alimente el
        // watchdog) sin necesidad de un delay artificial que descartaría
        // conversiones del ADC, que no tiene FIFO propio.
        _drdySemaphore = xSemaphoreCreateBinary();
        attachInterrupt(digitalPinToInterrupt(_drdy), ads1298_drdy_isr, FALLING);

        startConversion();
        delay(5);

        // Descarta cualquier flanco espurio capturado antes de que el ADC
        // empezara a convertir de verdad.
        xSemaphoreTake(_drdySemaphore, 0);
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
        return xSemaphoreTake(_drdySemaphore, pdMS_TO_TICKS(timeoutMs)) == pdTRUE;
    }

void IRAM_ATTR ADS1298::onDrdyInterrupt() {
    BaseType_t higherPriorityTaskWoken = pdFALSE;
    if (xSemaphoreGiveFromISR(_drdySemaphore, &higherPriorityTaskWoken) != pdTRUE) {
        // El semaforo ya estaba dado: la tarea no llego a consumir el flanco
        // anterior, asi que este se pierde (ver comentario en Estadisticas).
        estadisticas.perdidasDRDY++;
    }
    portYIELD_FROM_ISR(higherPriorityTaskWoken);
}
bool ADS1298 :: readChannels(uint8_t muestra[BYTES_POR_MUESTRA]) {
        // Bloquea aquí hasta que la ISR de DRDY dé el semáforo (o timeout).
        // Sin esta espera, este bucle no está sincronizado con el ADC en
        // absoluto: se dispara a la velocidad máxima del bus SPI, ajena a
        // que haya o no una conversión nueva lista.
        if (!waitForDRDY()) {
            estadisticas.timeoutsDRDY++;
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
            estadisticas.fallosSincronismo++;
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
            estadisticas.descartesCeros++;
            return false;
        }

        // Se descartan los 3 bytes de status; se conservan los 24 bytes de canales tal cual.
        memcpy(muestra, frame + 3, BYTES_POR_MUESTRA);
        estadisticas.exitos++;

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
            writeRegister(CH1SET + ch, 0x00     );
        }

        writeRegister(RLD_SENSN, 0x00);
        writeRegister(RLD_SENSP, 0x00);
    }