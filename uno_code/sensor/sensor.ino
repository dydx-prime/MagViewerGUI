// =====================================================
// OPTIMIZATIONS APPLIED:
//   1. Timer1 ISR for step pulses      — smooth motor regardless of loop time
//   2. Direct port writes for CLK/CLR/CS — ~20x faster than digitalWrite
//   3. Rate-limited live mode           — ~30fps cap prevents serial flood
//   4. Original Serial.print() output  — proven stable on Uno
//
// HARDWARE ASSUMPTIONS (Uno/Nano pinout):
//   stepPin = 5  → PORTD bit 5
//   dirPin  = 6  → PORTD bit 6
//   enblPin = 7  → PORTD bit 7
//   PIN_CLR = 8  → PORTB bit 0
//   PIN_CLK = 9  → PORTB bit 1
//   ADC_CS  = 10 → PORTB bit 2
// =====================================================

#include <SPI.h>
#include <TimerOne.h>   // Library Manager: search "TimerOne"

// =====================================================
// PORT MACROS  (Uno/Nano)
// =====================================================
#define STEP_HIGH()  (PORTD |=  (1 << 5))
#define STEP_LOW()   (PORTD &= ~(1 << 5))


// #define DIR_HIGH()   (PORTD |=  (1 << 6))
// #define DIR_LOW()    (PORTD &= ~(1 << 6))
#define DIR_LOW()    (PORTD &= ~(1 << 7))  
#define DIR_HIGH()   (PORTD |=  (1 << 7))  
#define ENBL_LOW()   (PORTD &= ~(1 << 6))
#define ENBL_HIGH()  (PORTD |= (1 << 6))

#define CLR_HIGH()   (PORTB |=  (1 << 0))
#define CLR_LOW()    (PORTB &= ~(1 << 0))
#define CLK_HIGH()   (PORTB |=  (1 << 1))
#define CLK_LOW()    (PORTB &= ~(1 << 1))
#define CS_HIGH()    (PORTB |=  (1 << 2))
#define CS_LOW()     (PORTB &= ~(1 << 2))

// =====================================================
// STEP MOTOR
// =====================================================
const int stepPin = 5;
const int dirPin  = 7;
const int enblPin = 6;

const int pulsesPerRev = 6400;
float leadPerRev = 8.0;
float stepsPerMM = (float)pulsesPerRev / leadPerRev;

volatile long currentPosition = 0;
volatile long targetPosition  = 0;
volatile bool isMoving        = false;
volatile int  stepDelay       = 20;

// =====================================================
// MODES
// =====================================================
bool liveMode  = true;
bool snakeMode = false;

// =====================================================
// SCAN TABLE
// =====================================================
const int scanSteps = 8;
long scanMin = 0;
long scanMax = 6400 * 10;

int  scanIndex   = 0;
bool scanForward = true;

// =====================================================
// SAMPLING
// =====================================================
long lastSampleStep = 0;
const int sampleIntervalSteps = 800;

// =====================================================
// ADC / TILE
// =====================================================
const byte PIN_CLR = 8;
const byte PIN_CLK = 9;
const byte ADC_CS  = 10;

uint16_t frame[64];

int pixelOrder[]    = {26,27,18,19,10,11,2,3,1,0,9,8,17,16,25,24};
int subtileOrder[]  = {0,2,1,3};
int subtileOffset[] = {0,4,32,36};

// =====================================================
// POSITION TABLE
// =====================================================
const float posMM[9] = {0,10,20,30,40,50,60,70,180};
long targetSteps[9];

// =====================================================
// TIMER1 ISR — fires every stepDelay µs
// Motor steps completely independently of loop()
// =====================================================
void stepISR()
{
  if (!isMoving) return;

  static bool stepState = false;
  stepState = !stepState;

  if (stepState) STEP_LOW();
  else           STEP_HIGH();

  if (stepState)
  {
    if (targetPosition > currentPosition)      currentPosition++;
    else if (targetPosition < currentPosition) currentPosition--;

    if (currentPosition == targetPosition)
      isMoving = false;
  }
}

// =====================================================
// ADC
// =====================================================
uint16_t readAD7680()
{
  CS_LOW();

  byte b0 = SPI.transfer(0x00);
  byte b1 = SPI.transfer(0x00);
  byte b2 = SPI.transfer(0x00);

  CS_HIGH();

  uint32_t raw = ((uint32_t)b0 << 16) | ((uint32_t)b1 << 8) | b2;
  return (raw >> 4) & 0xFFFF;
}

// =====================================================
// TILE FRAME — port writes replace digitalWrite
// =====================================================
void clearCounter()
{
  CLR_LOW();
  CLR_HIGH();
}

void incCounter()
{
  CLK_HIGH();
  CLK_LOW();
}

void readTileFrame()
{
  clearCounter();
  incCounter();

  for (int s = 0; s < 4; s++)
  {
    for (int p = 0; p < 16; p++)
    {
      uint16_t value = readAD7680();
      int offset = pixelOrder[p] + subtileOffset[subtileOrder[s]];
      frame[offset] = value;
      incCounter();
    }
  }
}

// =====================================================
// SERIAL OUTPUT — original Serial.print per value
// =====================================================
void streamFrame()
{
  for (int i = 0; i < 64; i++)
  {
    Serial.print(frame[i]);
    if (i < 63) Serial.print(",");
  }
  Serial.println();
}

// =====================================================
// MOTION CONTROL
// =====================================================
void startMove(long target, int speedDelay)
{
  // Disable ISR while setting up direction + target atomically
  Timer1.stop();

  long diff = target - currentPosition;   // use local target, not volatile

  if (diff > 0) DIR_HIGH();
  else          DIR_LOW();

  targetPosition = target;
  stepDelay      = speedDelay;

  Timer1.setPeriod(speedDelay);
  Timer1.start();
  isMoving = true;
}

// =====================================================
// SAMPLING WHILE MOVING
// =====================================================
void updateSampling()
{
  if (!isMoving || liveMode) return;

  long pos = currentPosition;  // snapshot volatile

  if (abs(pos - lastSampleStep) >= sampleIntervalSteps)
  {
    lastSampleStep = pos;
    readTileFrame();
    streamFrame();
  }
}

// =====================================================
// SNAKE SCAN
// =====================================================
void updateSnakeScan()
{
  if (!snakeMode) return;

  if (!isMoving)
  {
    long stepSize = (scanMax - scanMin) / (scanSteps - 1);
    long target;

    if (scanForward)
      target = scanMin + scanIndex * stepSize;
    else
      target = scanMin + (scanSteps - 1 - scanIndex) * stepSize;

    startMove(target, 20);

    scanIndex++;

    if (scanIndex >= scanSteps)
    {
      scanIndex   = 0;
      scanForward = !scanForward;
    }
  }
}

// =====================================================
// LIVE MODE — rate limited to ~30fps
// =====================================================
unsigned long lastLiveFrame = 0;
const unsigned long liveFrameInterval = 33000; // µs — 16667=60fps, 50000=20fps

void updateLiveMode()
{
  if (!liveMode || isMoving || snakeMode) return;

  unsigned long now = micros();
  if (now - lastLiveFrame < liveFrameInterval) return;
  lastLiveFrame = now;

  readTileFrame();
  streamFrame();
}

// =====================================================
// SETUP
// =====================================================
void setup()
{
  pinMode(stepPin, OUTPUT);
  pinMode(dirPin,  OUTPUT);
  pinMode(enblPin, OUTPUT);

  ENBL_HIGH();

  pinMode(PIN_CLR, OUTPUT);
  pinMode(PIN_CLK, OUTPUT);
  pinMode(ADC_CS,  OUTPUT);

  CS_HIGH();

  SPI.begin();
  SPI.beginTransaction(SPISettings(8000000, MSBFIRST, SPI_MODE0));

  Serial.begin(921600);
  while (!Serial);

  for (int i = 0; i <= 8; i++)
    targetSteps[i] = (long)(posMM[i] * stepsPerMM);

  clearCounter();
  incCounter();

  Timer1.initialize(stepDelay);
  Timer1.attachInterrupt(stepISR);

  Serial.println("READY");
}

// =====================================================
// LOOP — motor runs via ISR, loop handles everything else
// =====================================================
void loop()
{
  if (Serial.available())
  {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    cmd.toUpperCase();

    if (cmd == "L") liveMode = true;

    if (cmd == "S")
    {
      liveMode  = false;
      snakeMode = false;
    }

    if (cmd == "SCAN_SNAKE")
    {
      snakeMode = true;
      liveMode  = false;
    }

    if (cmd == "STOP")
    {
      snakeMode = false;
      isMoving  = false;
    }

    if (cmd == "HOME")
      startMove(0, 20);

    if (cmd.startsWith("A"))
    {
      int idx = cmd.substring(1).toInt();
      if (idx >= 0 && idx <= 8)
      {
        liveMode  = false;
        snakeMode = false;
        startMove(targetSteps[idx], 20);
      }
    }
  }

  // Motor stepping handled entirely by Timer1 ISR
  updateSnakeScan();
  updateSampling();
  updateLiveMode();
}