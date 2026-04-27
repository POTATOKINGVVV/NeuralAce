package com.stitch.neuralace.plugins.miband;

import java.util.UUID;

/**
 * BLE UUIDs and protocol constants for Xiaomi Mi Band 6 NFC.
 * Derived from Gadgetbridge reverse-engineering (HuamiSupport / MiBand6Support).
 */
public final class MiBand6Constants {

    private MiBand6Constants() {}

    // ── BLE Service UUIDs ──────────────────────────────────────────────
    public static final UUID SERVICE_MAIN =
            UUID.fromString("0000fee0-0000-1000-8000-00805f9b34fb");
    public static final UUID SERVICE_AUTH =
            UUID.fromString("0000fee1-0000-1000-8000-00805f9b34fb");
    public static final UUID SERVICE_HEART_RATE =
            UUID.fromString("0000180d-0000-1000-8000-00805f9b34fb");

    // ── Auth Characteristic ────────────────────────────────────────────
    public static final UUID CHAR_AUTH =
            UUID.fromString("00000009-0000-3512-2118-0009af100700");

    // ── Sensor Characteristics ─────────────────────────────────────────
    public static final UUID CHAR_SENSOR_CONTROL =
            UUID.fromString("00000001-0000-3512-2118-0009af100700");
    public static final UUID CHAR_SENSOR_DATA =
            UUID.fromString("00000002-0000-3512-2118-0009af100700");

    // ── Heart Rate Characteristics ─────────────────────────────────────
    public static final UUID CHAR_HR_CONTROL =
            UUID.fromString("00002a39-0000-1000-8000-00805f9b34fb");
    public static final UUID CHAR_HR_MEASURE =
            UUID.fromString("00002a37-0000-1000-8000-00805f9b34fb");

    // ── Standard BLE Descriptor (CCC for enabling notifications) ──────
    public static final UUID DESC_CCC =
            UUID.fromString("00002902-0000-1000-8000-00805f9b34fb");

    // ── Auth Protocol Commands ─────────────────────────────────────────
    public static final byte[] AUTH_SEND_KEY_CMD       = {0x01, 0x00};
    public static final byte[] AUTH_REQUEST_NONCE_CMD  = {0x02, 0x00};
    public static final byte[] AUTH_SEND_ENCRYPTED_CMD = {0x03, 0x00};

    // Expected auth response prefixes
    public static final byte[] AUTH_RESPONSE_KEY_OK    = {0x10, 0x01, 0x01};
    public static final byte[] AUTH_RESPONSE_NONCE     = {0x10, 0x01, 0x01};
    public static final byte[] AUTH_RESPONSE_AUTH_OK   = {0x10, 0x03, 0x01};

    // ── Sensor Control Commands ────────────────────────────────────────
    public static final byte[] CMD_SENSOR_ENABLE  = {0x01, 0x01, 0x19};
    public static final byte[] CMD_SENSOR_START   = {0x02};
    public static final byte[] CMD_SENSOR_STOP    = {0x03};

    // ── Heart Rate Control Commands ────────────────────────────────────
    public static final byte[] CMD_HR_CONTINUOUS_START  = {0x15, 0x01, 0x01};
    public static final byte[] CMD_HR_CONTINUOUS_STOP   = {0x15, 0x01, 0x00};
    public static final byte[] CMD_HR_MANUAL_START      = {0x15, 0x02, 0x01};

    // ── Device Name Prefix (for scanning) ──────────────────────────────
    public static final String DEVICE_NAME_PREFIX = "Mi Smart Band 6";
    public static final String DEVICE_NAME_ALT    = "Mi Band 6";

    // ── Sensor Data Parsing ────────────────────────────────────────────
    public static final double ACCEL_SCALE_FACTOR = 1000.0;
    public static final double GRAVITY            = 9.81;
    public static final double GYRO_SCALE_FACTOR  = 16.4;   // LSB/°/s for ±2000°/s range (typical)
}
