#include <Arduino.h>
#include <ESP32Servo.h>
#include <Adafruit_NeoPixel.h>

Servo leftServo;
Servo rightServo;

constexpr int LEFT_PIN = 18;
constexpr int RIGHT_PIN = 19;
constexpr int LED_LEFT_1_PIN = 25;
constexpr int LED_LEFT_2_PIN = 26;
constexpr int LED_RIGHT_1_PIN = 27;
constexpr int LED_RIGHT_2_PIN = 33;
constexpr int LED_ALWAYS_ON_1_PIN = 16;
constexpr int LED_ALWAYS_ON_2_PIN = 17;
constexpr int SERIAL_BAUD = 115200;
constexpr unsigned long DEFAULT_LED_SIGNAL_LOSS_FADE_OUT_MS = 3000;

// ================= NeoPixel 設定 =================
#define NUM_LEDS 30  // ★請改成你每一條燈條實際的燈珠數量★
constexpr int SIDE_CONTROL_LEDS = 15;
constexpr int CONTROL_LED_COUNT = SIDE_CONTROL_LEDS * 2;

Adafruit_NeoPixel ledsLeft1(NUM_LEDS, LED_LEFT_1_PIN, NEO_GRB + NEO_KHZ800);
Adafruit_NeoPixel ledsLeft2(NUM_LEDS, LED_LEFT_2_PIN, NEO_GRB + NEO_KHZ800);
Adafruit_NeoPixel ledsRight1(NUM_LEDS, LED_RIGHT_1_PIN, NEO_GRB + NEO_KHZ800);
Adafruit_NeoPixel ledsRight2(NUM_LEDS, LED_RIGHT_2_PIN, NEO_GRB + NEO_KHZ800);
Adafruit_NeoPixel ledsAlwaysOn1(NUM_LEDS, LED_ALWAYS_ON_1_PIN, NEO_GRB + NEO_KHZ800);
Adafruit_NeoPixel ledsAlwaysOn2(NUM_LEDS, LED_ALWAYS_ON_2_PIN, NEO_GRB + NEO_KHZ800);

constexpr uint8_t STRIP_RED = 255;
constexpr uint8_t STRIP_GREEN = 0;
constexpr uint8_t STRIP_BLUE = 0;
// ================================================

float currentLeft = 87.0f;
float currentRight = 96.0f;
float currentLedLeftPct = 0.0f;
float currentLedRightPct = 0.0f;
float lastCommandLedLeftPct = 0.0f;
float lastCommandLedRightPct = 0.0f;
float currentLedValuesPct[CONTROL_LED_COUNT] = {0.0f};
float lastCommandLedValuesPct[CONTROL_LED_COUNT] = {0.0f};
bool hasIndividualLedValues = false;
unsigned long lastCommandAt = 0;
unsigned long ledSignalLossFadeOutMs = DEFAULT_LED_SIGNAL_LOSS_FADE_OUT_MS;

void applyServo(float leftDeg, float rightDeg) {
  currentLeft = constrain(leftDeg, 45.0f, 135.0f);
  currentRight = constrain(rightDeg, 45.0f, 135.0f);
  leftServo.write(currentLeft);
  rightServo.write(currentRight);
}

int brightnessPctToDuty(float pct) {
  return static_cast<int>(roundf(constrain(pct, 0.0f, 100.0f) * 255.0f / 100.0f));
}

uint32_t scaledStripColor(Adafruit_NeoPixel& strip, uint8_t brightness) {
  return strip.Color(
      static_cast<uint8_t>((static_cast<uint16_t>(STRIP_RED) * brightness) / 255),
      static_cast<uint8_t>((static_cast<uint16_t>(STRIP_GREEN) * brightness) / 255),
      static_cast<uint8_t>((static_cast<uint16_t>(STRIP_BLUE) * brightness) / 255));
}

void fillStrip(Adafruit_NeoPixel& strip, uint8_t brightness) {
  strip.fill(scaledStripColor(strip, brightness));
  strip.show();
}

float averageLedSide(const float values[], int startIndex) {
  float total = 0.0f;
  for (int i = 0; i < SIDE_CONTROL_LEDS; i += 1) {
    total += constrain(values[startIndex + i], 0.0f, 100.0f);
  }
  return total / static_cast<float>(SIDE_CONTROL_LEDS);
}

void renderLedValues(const float values[]) {
  for (int i = 0; i < NUM_LEDS; i += 1) {
    uint8_t leftVal = 0;
    uint8_t rightVal = 0;
    if (i < SIDE_CONTROL_LEDS) {
      leftVal = brightnessPctToDuty(values[i]);
      rightVal = brightnessPctToDuty(values[SIDE_CONTROL_LEDS + i]);
    }
    ledsLeft1.setPixelColor(i, scaledStripColor(ledsLeft1, leftVal));
    ledsLeft2.setPixelColor(i, scaledStripColor(ledsLeft2, leftVal));
    ledsRight1.setPixelColor(i, scaledStripColor(ledsRight1, rightVal));
    ledsRight2.setPixelColor(i, scaledStripColor(ledsRight2, rightVal));
  }
  ledsLeft1.show();
  ledsLeft2.show();
  ledsRight1.show();
  ledsRight2.show();
  fillStrip(ledsAlwaysOn1, 255);
  fillStrip(ledsAlwaysOn2, 255);

  currentLedLeftPct = averageLedSide(values, 0);
  currentLedRightPct = averageLedSide(values, SIDE_CONTROL_LEDS);
  for (int i = 0; i < CONTROL_LED_COUNT; i += 1) {
    currentLedValuesPct[i] = constrain(values[i], 0.0f, 100.0f);
  }
}

void renderLedBrightness(float leftPct, float rightPct) {
  currentLedLeftPct = constrain(leftPct, 0.0f, 100.0f);
  currentLedRightPct = constrain(rightPct, 0.0f, 100.0f);
  
  // 取得 0-255 的亮度數值
  uint8_t leftVal = brightnessPctToDuty(currentLedLeftPct);
  uint8_t rightVal = brightnessPctToDuty(currentLedRightPct);

  fillStrip(ledsLeft1, leftVal);
  fillStrip(ledsLeft2, leftVal);
  fillStrip(ledsRight1, rightVal);
  fillStrip(ledsRight2, rightVal);
  fillStrip(ledsAlwaysOn1, 255);
  fillStrip(ledsAlwaysOn2, 255);
}

void applyLedBrightness(float leftPct, float rightPct) {
  hasIndividualLedValues = false;
  lastCommandLedLeftPct = constrain(leftPct, 0.0f, 100.0f);
  lastCommandLedRightPct = constrain(rightPct, 0.0f, 100.0f);
  renderLedBrightness(lastCommandLedLeftPct, lastCommandLedRightPct);
}

void applyLedValues(const float values[]) {
  hasIndividualLedValues = true;
  for (int i = 0; i < CONTROL_LED_COUNT; i += 1) {
    lastCommandLedValuesPct[i] = constrain(values[i], 0.0f, 100.0f);
  }
  lastCommandLedLeftPct = averageLedSide(lastCommandLedValuesPct, 0);
  lastCommandLedRightPct = averageLedSide(lastCommandLedValuesPct, SIDE_CONTROL_LEDS);
  renderLedValues(lastCommandLedValuesPct);
}

float extractFloatField(const String& line, const char* key, float fallback) {
  String needle = String("\"") + key + "\":";
  int start = line.indexOf(needle);
  if (start < 0) {
    return fallback;
  }
  start += needle.length();
  int end = start;
  while (end < line.length()) {
    const char c = line.charAt(end);
    const bool isNumberChar = (c >= '0' && c <= '9') || c == '-' || c == '.';
    if (!isNumberChar) {
      break;
    }
    end += 1;
  }
  return line.substring(start, end).toFloat();
}

bool extractLedValuesField(const String& line, float values[], int count) {
  String needle = "\"led_values_pct\":[";
  int pos = line.indexOf(needle);
  if (pos < 0) {
    return false;
  }
  pos += needle.length();
  for (int i = 0; i < count; i += 1) {
    while (pos < line.length()) {
      char c = line.charAt(pos);
      if (c != ' ' && c != ',') {
        break;
      }
      pos += 1;
    }
    int start = pos;
    while (pos < line.length()) {
      char c = line.charAt(pos);
      bool isNumberChar = (c >= '0' && c <= '9') || c == '-' || c == '+' || c == '.';
      if (!isNumberChar) {
        break;
      }
      pos += 1;
    }
    if (pos == start) {
      return false;
    }
    values[i] = constrain(line.substring(start, pos).toFloat(), 0.0f, 100.0f);
  }
  return true;
}

void sendStatus(const char* type, const char* mode) {
  Serial.print("{\"type\":\"");
  Serial.print(type);
  Serial.print("\",\"mode\":\"");
  Serial.print(mode);
  Serial.print("\",\"left_deg\":");
  Serial.print(currentLeft, 2);
  Serial.print(",\"right_deg\":");
  Serial.print(currentRight, 2);
  Serial.print(",\"led_left_pct\":");
  Serial.print(currentLedLeftPct, 2);
  Serial.print(",\"led_right_pct\":");
  Serial.print(currentLedRightPct, 2);
  Serial.println("}");
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  leftServo.attach(LEFT_PIN);
  rightServo.attach(RIGHT_PIN);
  
  ledsLeft1.begin();
  ledsLeft2.begin();
  ledsRight1.begin();
  ledsRight2.begin();
  ledsAlwaysOn1.begin();
  ledsAlwaysOn2.begin();
  
  applyServo(90.0f, 90.0f);
  applyLedBrightness(0.0f, 0.0f);
  sendStatus("status", "boot");
}

void loop() {
  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (line.indexOf("\"type\":\"servo\"") >= 0) {
      if (line.indexOf("\"left_deg\":") >= 0 && line.indexOf("\"right_deg\":") >= 0) {
        float left = extractFloatField(line, "left_deg", currentLeft);
        float right = extractFloatField(line, "right_deg", currentRight);
        float ledLeftPct = extractFloatField(line, "led_left_pct", currentLedLeftPct);
        float ledRightPct = extractFloatField(line, "led_right_pct", currentLedRightPct);
        float ledValues[CONTROL_LED_COUNT] = {0.0f};
        bool hasLedValues = extractLedValuesField(line, ledValues, CONTROL_LED_COUNT);
        ledSignalLossFadeOutMs = static_cast<unsigned long>(
            max(0.0f, extractFloatField(line, "led_signal_loss_fade_out_ms", static_cast<float>(ledSignalLossFadeOutMs))));
        
        applyServo(left, right);
        if (hasLedValues) {
          applyLedValues(ledValues);
        } else {
          applyLedBrightness(ledLeftPct, ledRightPct);
        }
        
        lastCommandAt = millis();
        sendStatus("ack", "track");
      }
    }
  }

  if (lastCommandAt > 0) {
    unsigned long silentMs = millis() - lastCommandAt;
    if (ledSignalLossFadeOutMs == 0 || silentMs >= ledSignalLossFadeOutMs) {
      applyServo(87.0f, 96.0f);
      renderLedBrightness(0.0f, 0.0f);
    } else {
      float fadeRatio = static_cast<float>(silentMs) / static_cast<float>(ledSignalLossFadeOutMs);
      if (hasIndividualLedValues) {
        float fadedValues[CONTROL_LED_COUNT] = {0.0f};
        for (int i = 0; i < CONTROL_LED_COUNT; i += 1) {
          fadedValues[i] = lastCommandLedValuesPct[i] * (1.0f - fadeRatio);
        }
        renderLedValues(fadedValues);
      } else {
        renderLedBrightness(lastCommandLedLeftPct * (1.0f - fadeRatio), lastCommandLedRightPct * (1.0f - fadeRatio));
      }
    }
  }
}
