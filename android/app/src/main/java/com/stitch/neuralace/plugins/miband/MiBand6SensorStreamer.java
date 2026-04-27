package com.stitch.neuralace.plugins.miband;

import android.bluetooth.BluetoothGatt;
import android.bluetooth.BluetoothGattCharacteristic;
import android.bluetooth.BluetoothGattDescriptor;
import android.util.Log;

import org.json.JSONException;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

/**
 * Subscribes to raw IMU sensor notifications from Mi Band 6 and parses
 * the binary data into structured accelerometer + gyroscope samples.
 *
 * Binary format per notification (from Gadgetbridge reverse-engineering):
 *   [counter_lo, counter_hi, sample_1, sample_2, ...]
 *   Each sample = 6 bytes: [x_lo, x_hi, y_lo, y_hi, z_lo, z_hi]
 *   Axis format: ttssvvvvvvvvvvvv  (tt=type, ss=sign, v=12-bit value)
 *
 * For 6-axis IMU, samples alternate: accel, gyro, accel, gyro, ...
 */
public class MiBand6SensorStreamer {

    private static final String TAG = "MiBand6Sensor";

    public interface SensorCallback {
        void onSensorData(JSONObject data);
        void onHeartRate(int bpm);
        void onError(String message);
    }

    private final BluetoothGatt gatt;
    private SensorCallback callback;
    private boolean streaming = false;
    private long sampleCounter = 0;

    public MiBand6SensorStreamer(BluetoothGatt gatt) {
        this.gatt = gatt;
    }

    public void setCallback(SensorCallback callback) {
        this.callback = callback;
    }

    /**
     * Mi Band 6 raw sensor protocol — comprehensive approach:
     * Step 1: Subscribe to SENSOR_CONTROL (0x0001) notifications (for responses)
     * Step 2: Subscribe to SENSOR_DATA (0x0002) notifications (for data)
     * Step 3: Write enable {0x01,0x01,0x19} to SENSOR_CONTROL
     * Step 4: Wait for response on 0x0001 → then write start {0x02}
     * Step 5: Wait for response on 0x0001 → sensor data should flow on 0x0001 or 0x0002
     *
     * Also tries alternate enable commands if the first doesn't produce data.
     */
    private int sensorSetupStep = 0;
    private boolean gotSensorData = false;

    // ── Start sensor data streaming ────────────────────────────────
    public boolean startSensorStream() {
        BluetoothGattCharacteristic controlChar = getSensorControlChar();
        if (controlChar == null) {
            Log.e(TAG, "Sensor control characteristic not found");
            if (callback != null) callback.onError("Sensor control characteristic not found on device");
            return false;
        }

        streaming = true;
        sampleCounter = 0;
        gotSensorData = false;
        sensorSetupStep = 1;

        // Step 1: Subscribe to SENSOR_CONTROL (0x0001) for responses
        Log.i(TAG, "Sensor Step 1: Subscribing to SENSOR_CONTROL (0x0001) notifications");
        gatt.setCharacteristicNotification(controlChar, true);
        BluetoothGattDescriptor desc = controlChar.getDescriptor(MiBand6Constants.DESC_CCC);
        if (desc != null) {
            desc.setValue(BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE);
            gatt.writeDescriptor(desc);
        } else {
            Log.w(TAG, "No CCC on control char — skipping to data subscription");
            onControlDescriptorWritten();
        }
        return true;
    }

    // Step 1 done → subscribe to 0x0002
    public void onControlDescriptorWritten() {
        if (!streaming) return;
        sensorSetupStep = 2;
        Log.i(TAG, "Sensor Step 2: Subscribing to SENSOR_DATA (0x0002) notifications");

        BluetoothGattCharacteristic dataChar = getSensorDataChar();
        if (dataChar == null) {
            Log.e(TAG, "Sensor data char not found");
            return;
        }
        gatt.setCharacteristicNotification(dataChar, true);
        BluetoothGattDescriptor desc = dataChar.getDescriptor(MiBand6Constants.DESC_CCC);
        if (desc != null) {
            desc.setValue(BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE);
            gatt.writeDescriptor(desc);
        } else {
            Log.w(TAG, "No CCC on data char — send enable anyway");
            onSensorDescriptorWritten();
        }
    }

    // ── Brute-force enable commands to find one Mi Band 6 accepts ──
    // Response status 0x01 = success, anything else = fail.
    // We try multiple enable variants until one succeeds.
    private static final byte[][] ENABLE_VARIANTS = {
        {0x01, 0x01, 0x19},       // Classic Mi Band 2/3/4 (accel+gyro)
        {0x01, 0x01, 0x01},       // Accelerometer only
        {0x01, 0x01, 0x09},       // Accel(0x01) + Gyro(0x08)
        {0x01, 0x01, 0x03},       // Accel(0x01) + ?(0x02)
        {0x01, 0x01, (byte)0xff}, // All sensors
        {0x01, 0x03, 0x19},       // Different sub-command
        {0x01, 0x02, 0x01},       // Sub-command 2
        {0x01, 0x01},             // 2-byte variant
        {0x12, 0x01},             // Alt command prefix (Gadgetbridge alt)
        {0x01, 0x01, 0x00},       // Zero config
    };
    private int enableVariantIndex = 0;
    private boolean enableAccepted = false;

    // Step 2 done → start trying enable variants
    public void onSensorDescriptorWritten() {
        if (!streaming) return;
        sensorSetupStep = 3;
        enableVariantIndex = 0;
        enableAccepted = false;
        trySendNextEnableVariant();
    }

    private void trySendNextEnableVariant() {
        if (enableVariantIndex >= ENABLE_VARIANTS.length) {
            Log.e(TAG, "ALL enable variants REJECTED by band. Raw sensor not supported.");
            return;
        }

        byte[] cmd = ENABLE_VARIANTS[enableVariantIndex];
        StringBuilder hex = new StringBuilder();
        for (byte b : cmd) hex.append(String.format("%02x ", b));
        Log.i(TAG, "Sensor Step 3: Trying enable variant #" + enableVariantIndex + " [" + hex.toString().trim() + "]");

        BluetoothGattCharacteristic controlChar = getSensorControlChar();
        if (controlChar == null) return;

        controlChar.setWriteType(BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE);
        controlChar.setValue(cmd);
        gatt.writeCharacteristic(controlChar);
    }

    // Called after characteristic write completes — but we now wait for the
    // notification response on 0x0001 to know if it succeeded.
    public void onSensorEnableWritten() {
        // Do nothing here — wait for response notification
    }

    public void onSensorStartWritten() {
        if (!streaming) return;
        sensorSetupStep = 5;
        Log.i(TAG, "Sensor Step 5: Start command sent — monitoring for data");
    }

    /**
     * Called when a notification arrives on SENSOR_CONTROL (0x0001).
     */
    public void onSensorControlNotification(byte[] value) {
        if (value == null || value.length == 0) return;

        StringBuilder hex = new StringBuilder();
        for (byte b : value) hex.append(String.format("%02x ", b));
        Log.i(TAG, "SENSOR_CONTROL notification: len=" + value.length + " hex=[" + hex.toString().trim() + "]");

        if (value[0] == 0x10 && value.length >= 3) {
            int cmdType = value[1] & 0xFF;
            int status = value[2] & 0xFF;
            boolean success = (status == 0x01);
            Log.i(TAG, "  → Response to cmd 0x" + String.format("%02x", cmdType)
                    + " status=0x" + String.format("%02x", status)
                    + (success ? " (SUCCESS)" : " (FAIL)"));

            if (cmdType == 0x01) {
                // Response to enable command
                if (success) {
                    enableAccepted = true;
                    Log.i(TAG, "  ★ ENABLE ACCEPTED with variant #" + enableVariantIndex + "!");
                    // Now send start command
                    sensorSetupStep = 4;
                    Log.i(TAG, "Sensor Step 4: Sending start {0x02}");
                    BluetoothGattCharacteristic controlChar = getSensorControlChar();
                    if (controlChar != null) {
                        controlChar.setWriteType(BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE);
                        controlChar.setValue(MiBand6Constants.CMD_SENSOR_START);
                        gatt.writeCharacteristic(controlChar);
                    }
                } else {
                    // Try next variant
                    enableVariantIndex++;
                    Log.i(TAG, "  → Rejected. Trying next variant...");
                    // Small delay before next attempt
                    new android.os.Handler(android.os.Looper.getMainLooper()).postDelayed(() -> {
                        trySendNextEnableVariant();
                    }, 100);
                }
            } else if (cmdType == 0x02) {
                // Response to start command
                if (success) {
                    Log.i(TAG, "  ★ START ACCEPTED — sensor data should now be streaming!");
                } else {
                    Log.e(TAG, "  Start command failed with status 0x" + String.format("%02x", status));
                }
            }
        } else if (value[0] != 0x10) {
            // Not a response — might be actual sensor data!
            Log.i(TAG, "  → NON-RESPONSE data on CONTROL char! Possible sensor data.");
            gotSensorData = true;
            if (value.length >= 8) {
                onSensorDataNotification(value);
            }
        }
    }

    // ── Stop sensor data streaming ─────────────────────────────────────
    public void stopSensorStream() {
        streaming = false;
        BluetoothGattCharacteristic controlChar = getSensorControlChar();
        if (controlChar != null) {
            controlChar.setValue(MiBand6Constants.CMD_SENSOR_STOP);
            gatt.writeCharacteristic(controlChar);
        }

        BluetoothGattCharacteristic dataChar = getSensorDataChar();
        if (dataChar != null) {
            gatt.setCharacteristicNotification(dataChar, false);
        }
        Log.i(TAG, "Sensor stream stopped");
    }

    // ── Start continuous heart rate monitoring ─────────────────────────
    public boolean startHeartRateStream() {
        BluetoothGattCharacteristic hrMeasure = getHrMeasureChar();
        BluetoothGattCharacteristic hrControl = getHrControlChar();
        if (hrMeasure == null || hrControl == null) {
            Log.e(TAG, "HR characteristics not found");
            return false;
        }

        gatt.setCharacteristicNotification(hrMeasure, true);
        BluetoothGattDescriptor desc = hrMeasure.getDescriptor(MiBand6Constants.DESC_CCC);
        if (desc != null) {
            desc.setValue(BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE);
            gatt.writeDescriptor(desc);
            Log.i(TAG, "HR notifications enabling — waiting for descriptor callback");
        } else {
            // No CCC descriptor, write control directly
            sendHrStartCommand();
        }
        return true;
    }

    // Called after HR measure CCC descriptor is written
    public void onHrDescriptorWritten() {
        Log.i(TAG, "HR descriptor written — sending start command");
        sendHrStartCommand();
    }

    private void sendHrStartCommand() {
        BluetoothGattCharacteristic hrControl = getHrControlChar();
        if (hrControl == null) {
            Log.e(TAG, "HR control characteristic not found");
            return;
        }
        hrControl.setValue(MiBand6Constants.CMD_HR_CONTINUOUS_START);
        gatt.writeCharacteristic(hrControl);
        Log.i(TAG, "Heart rate continuous monitoring start command sent");
    }

    public void stopHeartRateStream() {
        BluetoothGattCharacteristic hrControl = getHrControlChar();
        if (hrControl != null) {
            hrControl.setValue(MiBand6Constants.CMD_HR_CONTINUOUS_STOP);
            gatt.writeCharacteristic(hrControl);
        }
        Log.i(TAG, "Heart rate monitoring stopped");
    }

    // ── Handle raw sensor notification ─────────────────────────────────
    public void onSensorDataNotification(byte[] value) {
        if (value == null || value.length < 2) return;

        List<double[]> rawSamples = parseSensorPacket(value);
        long now = System.currentTimeMillis();

        // Determine if we have 6-axis (accel+gyro) or 3-axis (accel only) data
        // 6-axis: samples come in pairs (even=accel, odd=gyro)
        // 3-axis: every sample is accelerometer
        boolean sixAxis = rawSamples.size() >= 2 && rawSamples.size() % 2 == 0;

        if (sixAxis) {
            for (int i = 0; i + 1 < rawSamples.size(); i += 2) {
                double[] accel = rawSamples.get(i);
                double[] gyro  = rawSamples.get(i + 1);
                sampleCounter++;
                emitSample(now, accel, gyro);
            }
        } else {
            for (double[] accel : rawSamples) {
                sampleCounter++;
                emitSample(now, accel, null);
            }
        }
    }

    // ── Handle heart rate notification ─────────────────────────────────
    public void onHeartRateNotification(byte[] value) {
        if (value == null || value.length < 2) return;
        int bpm = value[1] & 0xFF;
        if (bpm > 0 && callback != null) {
            callback.onHeartRate(bpm);
        }
    }

    // ── Binary parsing (ported from Gadgetbridge handleSensorData) ────
    private List<double[]> parseSensorPacket(byte[] value) {
        List<double[]> samples = new ArrayList<>();

        if ((value.length - 2) % 6 != 0) {
            Log.w(TAG, "Unexpected sensor packet length: " + value.length);
            return samples;
        }

        int numSamples = (value.length - 2) / 6;
        for (int idx = 0; idx < numSamples; idx++) {
            int offset = 2 + idx * 6;
            double x = decodeAxis(value, offset);
            double y = decodeAxis(value, offset + 2);
            double z = decodeAxis(value, offset + 4);
            samples.add(new double[]{x, y, z});
        }
        return samples;
    }

    /**
     * Decode one axis value from the raw 16-bit encoding.
     * Format: ttssvvvvvvvvvvvv
     *   tt  (bit 15-14): data type (00=x, 01=y, 10=z, 11=temp)
     *   ss  (bit 13-12): sign
     *   v   (bit 11-0) : 12-bit value, two's complement
     */
    private double decodeAxis(byte[] data, int offset) {
        int raw = (data[offset] & 0xFF) | ((data[offset + 1] & 0xFF) << 8);
        int sign = (data[offset + 1] & 0x30) >> 4;
        double value;
        if (sign == 0) {
            value = raw & 0xFFF;
        } else {
            value = (raw & 0xFFF) - 4097;
        }
        return value;
    }

    private void emitSample(long timestamp, double[] accel, double[] gyro) {
        if (callback == null) return;
        try {
            JSONObject obj = new JSONObject();
            obj.put("counter", sampleCounter);
            obj.put("timestamp", timestamp);
            // Accelerometer in m/s²
            obj.put("accelX", accel[0] / MiBand6Constants.ACCEL_SCALE_FACTOR * MiBand6Constants.GRAVITY);
            obj.put("accelY", accel[1] / MiBand6Constants.ACCEL_SCALE_FACTOR * MiBand6Constants.GRAVITY);
            obj.put("accelZ", accel[2] / MiBand6Constants.ACCEL_SCALE_FACTOR * MiBand6Constants.GRAVITY);
            // Gyroscope in °/s (if available)
            if (gyro != null) {
                obj.put("gyroX", gyro[0] / MiBand6Constants.GYRO_SCALE_FACTOR);
                obj.put("gyroY", gyro[1] / MiBand6Constants.GYRO_SCALE_FACTOR);
                obj.put("gyroZ", gyro[2] / MiBand6Constants.GYRO_SCALE_FACTOR);
                obj.put("hasGyro", true);
            } else {
                obj.put("gyroX", 0.0);
                obj.put("gyroY", 0.0);
                obj.put("gyroZ", 0.0);
                obj.put("hasGyro", false);
            }
            callback.onSensorData(obj);
        } catch (JSONException e) {
            Log.e(TAG, "JSON error: " + e.getMessage());
        }
    }

    // ── Characteristic getters ─────────────────────────────────────────

    private BluetoothGattCharacteristic getSensorControlChar() {
        if (gatt.getService(MiBand6Constants.SERVICE_MAIN) == null) return null;
        return gatt.getService(MiBand6Constants.SERVICE_MAIN)
                .getCharacteristic(MiBand6Constants.CHAR_SENSOR_CONTROL);
    }

    private BluetoothGattCharacteristic getSensorDataChar() {
        if (gatt.getService(MiBand6Constants.SERVICE_MAIN) == null) return null;
        return gatt.getService(MiBand6Constants.SERVICE_MAIN)
                .getCharacteristic(MiBand6Constants.CHAR_SENSOR_DATA);
    }

    private BluetoothGattCharacteristic getHrControlChar() {
        if (gatt.getService(MiBand6Constants.SERVICE_HEART_RATE) == null) return null;
        return gatt.getService(MiBand6Constants.SERVICE_HEART_RATE)
                .getCharacteristic(MiBand6Constants.CHAR_HR_CONTROL);
    }

    private BluetoothGattCharacteristic getHrMeasureChar() {
        if (gatt.getService(MiBand6Constants.SERVICE_HEART_RATE) == null) return null;
        return gatt.getService(MiBand6Constants.SERVICE_HEART_RATE)
                .getCharacteristic(MiBand6Constants.CHAR_HR_MEASURE);
    }

    public boolean isStreaming() {
        return streaming;
    }
}
