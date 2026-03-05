/*
  Magnetic Imaging Tile - Optimized Streaming Version
  Target: Arduino Uno (low RAM)
  ADC: AD7940 (SPI hardware)
  Mode: Real-time streaming (CSV or Binary-ready)

  Commands:
    L = Live streaming
    1 = Burst 50 frames (max speed)
    2 = Burst 50 frames (1ms delay)
    S = Idle
*/

#include <SPI.h>

#define terminal Serial

// -------------------- Hardware Pins --------------------
const byte PIN_CLR = 8;
const byte PIN_CLK = 9; // this is real SCK
const byte ADC_CS  = 10;   // AD7940 CS
const byte ADC_MISO = 12;
const byte ADC_SCK  = 13; // this is real CLK

// -------------------- Frame Buffer --------------------
uint16_t frame[64];   // Single frame only (Uno safe)

// Pixel ordering
int pixelOrder[]   = {26,27,18,19,10,11,2,3,1,0,9,8,17,16,25,24};
int subtileOrder[] = {0,2,1,3};
int subtileOffset[]= {0,4,32,36};

// -------------------- Modes --------------------
#define MODE_IDLE 0
#define MODE_LIVE 1
#define MODE_BURST_FAST 2
#define MODE_BURST_1MS 3

int curMode = MODE_LIVE;


uint16_t readAD7940()
{
  digitalWrite(ADC_CS, LOW);
  uint16_t value = SPI.transfer16(0x0000);
  digitalWrite(ADC_CS, HIGH);
  return value;
}


void clearCounter()
{
  digitalWrite(PIN_CLR, LOW);
  digitalWrite(PIN_CLR, HIGH);
}

void incrementCounter()
{
  digitalWrite(PIN_CLK, HIGH);
  digitalWrite(PIN_CLK, LOW);
}

// frame builder
void readTileFrame()
{
  clearCounter();
  incrementCounter();

  for (int s = 0; s < 4; s++)
  {
    for (int p = 0; p < 16; p++)
    {
      uint16_t value = readAD7940();

      int offset = pixelOrder[p] + 
                   subtileOffset[subtileOrder[s]];

      frame[offset] = value;

      incrementCounter();
    }
  }
}


// output stream
void streamFrameCSV()
{
  for (int i = 0; i < 64; i++)
  {
    terminal.print(frame[i]);
    if (i < 63) terminal.print(",");
  }
  terminal.println();
  //delay(500);
}

// fast, ig
void streamBurst(int framesToSend, int frameDelayMs)
{
  unsigned long start = millis();

  for (int f = 0; f < framesToSend; f++)
  {
    readTileFrame();
    streamFrameCSV();

    if (frameDelayMs > 0)
      delay(frameDelayMs);
  }

  float elapsed = (millis() - start) / 1000.0;
  terminal.print("FPS: ");
  terminal.println(framesToSend / elapsed);
}


void setup()
{
  pinMode(PIN_CLR, OUTPUT);
  pinMode(PIN_CLK, OUTPUT);
  pinMode(ADC_CS, OUTPUT);
  pinMode(ADC_MISO, INPUT);
  pinMode(ADC_SCK, OUTPUT);

  digitalWrite(ADC_CS, HIGH);

  SPI.begin();
  SPI.beginTransaction(
    SPISettings(8000000, MSBFIRST, SPI_MODE0)
  );

  terminal.begin(250000);
  while (!terminal);

  clearCounter();
  incrementCounter();

  terminal.println("Ready. L=Live, 1=Fast Burst, 2=1ms Burst, S=Idle");
}


void loop()
{
  if (terminal.available())
  {
    char cmd = terminal.read();

    if (cmd == 'L') {
      curMode = MODE_LIVE;
      terminal.println("Live Mode");
    }
    else if (cmd == '1') {
      curMode = MODE_BURST_FAST;
    }
    else if (cmd == '2') {
      curMode = MODE_BURST_1MS;
    }
    else if (cmd == 'S') {
      curMode = MODE_IDLE;
      terminal.println("Idle");
    }
  }

  switch (curMode)
  {
    case MODE_LIVE:
      readTileFrame();
      streamFrameCSV();   // No delay = max FPS
      break;

    case MODE_BURST_FAST:
      streamBurst(50, 0);
      curMode = MODE_IDLE;
      break;

    case MODE_BURST_1MS:
      streamBurst(50, 1);
      curMode = MODE_IDLE;
      break;

    case MODE_IDLE:
      break;
  }
}