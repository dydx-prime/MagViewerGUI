






#include <SPI.h>

// === STEP MOTOR ===
const int stepPin = 5;
const int dirPin  = 6;
const int enblPin = 7;

const int pulsesPerRev = 6400;
float leadPerRev = 8.0;
float stepsPerMM = (float)pulsesPerRev / leadPerRev;

// Motion state
long currentPosition = 0;
long targetPosition = 0;
bool isMoving = false;
unsigned long lastStepTime = 0;
int stepDelay = 20;
bool stepState = LOW;

// === MODES & SWEEP STATE ===
bool liveMode = true;
bool snakeMode = false;
bool sweepMode = false;      // New: Tracks if the automatic A1-A8 sweep is active
int sweepIndex = 1;          // Start at A1
unsigned long sweepTimer = 0;
const long sweepWaitTime = 3000; // 3 seconds between stops

// === SCAN TABLE (Existing) ===
const int scanSteps = 8;
long scanMin = 0;
long scanMax = 6400 * 10;
int scanIndex = 0;
bool scanForward = true;

// === SAMPLING ===
long lastSampleStep = 0;
const int sampleIntervalSteps = 800;

// === ADC / TILE ===
const byte PIN_CLR = 8;
const byte PIN_CLK = 9;
const byte ADC_CS  = 10;
uint16_t frame[64];
int pixelOrder[]    = {26,27,18,19,10,11,2,3,1,0,9,8,17,16,25,24};
int subtileOrder[]  = {0,2,1,3};
int subtileOffset[] = {0,4,32,36};

// === POSITION TABLE ===
const float posMM[9] = {0,10,20,30,40,50,60,70,80};
long targetSteps[9];

// =====================================================
// ADC & TILE FUNCTIONS (No Changes Needed)
// =====================================================
uint16_t readAD7680() {
  digitalWrite(ADC_CS, LOW);
  byte b0 = SPI.transfer(0x00);
  byte b1 = SPI.transfer(0x00);
  byte b2 = SPI.transfer(0x00);
  digitalWrite(ADC_CS, HIGH);
  uint32_t raw = ((uint32_t)b0 << 16) | ((uint32_t)b1 << 8) | b2;
  return (raw >> 4) & 0xFFFF;
}

void clearCounter() { digitalWrite(PIN_CLR, LOW); digitalWrite(PIN_CLR, HIGH); }
void incCounter()   { digitalWrite(PIN_CLK, HIGH); digitalWrite(PIN_CLK, LOW); }

void readTileFrame() {
  clearCounter();
  incCounter();
  for (int s = 0; s < 4; s++) {
    for (int p = 0; p < 16; p++) {
      uint16_t value = readAD7680();
      int offset = pixelOrder[p] + subtileOffset[subtileOrder[s]];
      frame[offset] = value;
      incCounter();
    }
  }
}

void streamFrame() {
  for (int i = 0; i < 64; i++) {
    Serial.print(frame[i]);
    if (i < 63) Serial.print(",");
  }
  Serial.println();
}

// =====================================================
// MOTION & SWEEP LOGIC (The New Engine)
// =====================================================
void startMove(long target, int speedDelay) {
  targetPosition = target;
  stepDelay = speedDelay;
  isMoving = true;
  long diff = targetPosition - currentPosition;
  digitalWrite(dirPin, diff > 0 ? HIGH : LOW);
}

void updateMotor() {
  if (!isMoving) return;
  unsigned long now = micros();
  if (now - lastStepTime >= stepDelay) {
    lastStepTime = now;
    stepState = !stepState;
    digitalWrite(stepPin, stepState);
    if (stepState == HIGH) {
      if (targetPosition > currentPosition) currentPosition++;
      else if (targetPosition < currentPosition) currentPosition--;
      if (currentPosition == targetPosition) isMoving = false;
    }
  }
}

void updateSweep() {
  if (!sweepMode) return;

  // If the motor is currently moving, do nothing
  if (isMoving) {
    sweepTimer = millis(); // Keep resetting timer while moving
    return;
  }

  // If we arrived at a point, check if 3 seconds have passed
  if (millis() - sweepTimer >= sweepWaitTime) {
    if (sweepIndex <= 8) {
      Serial.print(F("Moving to A")); Serial.println(sweepIndex);
      startMove(targetSteps[sweepIndex], 50); // Slower sweep speed
      sweepIndex++;
      sweepTimer = millis();
    } else {
      // Completed A1-A8, return home
      Serial.println(F("Sweep Complete. Returning HOME..."));
      startMove(0, 50);
      sweepMode = false; // Sweep finished
    }
  }
}

void updateSampling() {
  if (!isMoving || liveMode) return;
  if (abs(currentPosition - lastSampleStep) >= sampleIntervalSteps) {
    lastSampleStep = currentPosition;
    readTileFrame();
    streamFrame();
  }
}

void updateLiveMode() {
  if (!liveMode || isMoving || snakeMode || sweepMode) return;
  readTileFrame();
  streamFrame();
}

// =====================================================
// SETUP & LOOP
// =====================================================
void setup() {
  pinMode(stepPin, OUTPUT);
  pinMode(dirPin, OUTPUT);
  pinMode(enblPin, OUTPUT);
  digitalWrite(enblPin, HIGH);

  pinMode(PIN_CLR, OUTPUT);
  pinMode(PIN_CLK, OUTPUT);
  pinMode(ADC_CS, OUTPUT);
  digitalWrite(ADC_CS, HIGH);

  SPI.begin();
  SPI.beginTransaction(SPISettings(8000000, MSBFIRST, SPI_MODE0));

  Serial.begin(460800);
  while (!Serial);

  for (int i = 0; i <= 8; i++)
    targetSteps[i] = (long)(posMM[i] * stepsPerMM);

  Serial.println("READY");
}

void loop() {
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    cmd.toUpperCase();

    if (cmd == "L") { liveMode = true; snakeMode = false; sweepMode = false; }
    if (cmd == "S") { liveMode = false; snakeMode = false; sweepMode = false; }
    if (cmd == "STOP") { snakeMode = false; sweepMode = false; isMoving = false; }
    if (cmd == "HOME") { sweepMode = false; startMove(0, 20); }

    if (cmd == "SWEEP") {
      Serial.println(F("Starting Sweep sequence..."));
      sweepMode = true;
      liveMode = false;
      snakeMode = false;
      sweepIndex = 1;
      sweepTimer = millis(); // Start the timer for the first move
    }

    if (cmd.startsWith("A")) {
      int idx = cmd.substring(1).toInt();
      if (idx >= 0 && idx <= 8) {
        liveMode = false;
        snakeMode = false;
        sweepMode = false;
        startMove(targetSteps[idx], 20);
      }
    }
  }

  updateMotor();
  updateSweep();    // New sweep state machine
  updateSampling(); // Records data while moving
  updateLiveMode(); // Streams data while idle
}