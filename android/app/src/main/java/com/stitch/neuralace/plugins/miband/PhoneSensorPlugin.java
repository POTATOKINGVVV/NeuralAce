package com.stitch.neuralace.plugins.miband;

import android.content.Context;
import android.hardware.Sensor;
import android.hardware.SensorEvent;
import android.hardware.SensorEventListener;
import android.hardware.SensorManager;
import android.util.Log;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

/**
 * Capacitor plugin that streams the phone's built-in accelerometer and gyroscope
 * data to the JS layer. This is used as the IMU data source because Mi Band 6
 * does not expose raw sensor streaming via BLE.
 *
 * JS API:
 *   PhoneSensor.startSensorStream()   → starts accel + gyro streaming
 *   PhoneSensor.stopSensorStream()    → stops streaming
 *
 * Events emitted to JS:
 *   "sensorData" → { counter, timestamp, accelX/Y/Z, gyroX/Y/Z, hasGyro }
 */
@CapacitorPlugin(name = "PhoneSensor")
public class PhoneSensorPlugin extends Plugin implements SensorEventListener {

    private static final String TAG = "PhoneSensor";

    private SensorManager sensorManager;
    private Sensor accelerometer;
    private Sensor gyroscope;
    private boolean streaming = false;
    private long counter = 0;

    // Latest values (accel and gyro arrive on separate callbacks)
    private final float[] latestAccel = new float[3];
    private final float[] latestGyro = new float[3];
    private boolean hasGyro = false;
    private long lastEmitTime = 0;
    private static final long EMIT_INTERVAL_MS = 20; // ~50 Hz

    @Override
    public void load() {
        sensorManager = (SensorManager) getContext().getSystemService(Context.SENSOR_SERVICE);
        if (sensorManager != null) {
            accelerometer = sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER);
            gyroscope = sensorManager.getDefaultSensor(Sensor.TYPE_GYROSCOPE);
        }
        Log.i(TAG, "PhoneSensor loaded. Accel=" + (accelerometer != null) + " Gyro=" + (gyroscope != null));
    }

    @PluginMethod
    public void startSensorStream(PluginCall call) {
        if (sensorManager == null || accelerometer == null) {
            call.reject("Accelerometer not available on this device");
            return;
        }

        streaming = true;
        counter = 0;
        hasGyro = gyroscope != null;

        // SENSOR_DELAY_GAME ≈ 20ms interval (50 Hz)
        sensorManager.registerListener(this, accelerometer, SensorManager.SENSOR_DELAY_GAME);
        if (gyroscope != null) {
            sensorManager.registerListener(this, gyroscope, SensorManager.SENSOR_DELAY_GAME);
        }

        Log.i(TAG, "Phone sensor streaming started (accel + gyro=" + hasGyro + ")");
        call.resolve(new JSObject().put("streaming", true).put("hasGyro", hasGyro));
    }

    @PluginMethod
    public void stopSensorStream(PluginCall call) {
        streaming = false;
        if (sensorManager != null) {
            sensorManager.unregisterListener(this);
        }
        Log.i(TAG, "Phone sensor streaming stopped");
        call.resolve(new JSObject().put("streaming", false));
    }

    @Override
    public void onSensorChanged(SensorEvent event) {
        if (!streaming) return;

        if (event.sensor.getType() == Sensor.TYPE_ACCELEROMETER) {
            latestAccel[0] = event.values[0];
            latestAccel[1] = event.values[1];
            latestAccel[2] = event.values[2];
        } else if (event.sensor.getType() == Sensor.TYPE_GYROSCOPE) {
            latestGyro[0] = event.values[0];
            latestGyro[1] = event.values[1];
            latestGyro[2] = event.values[2];
        }

        // Throttle emission to ~50 Hz
        long now = System.currentTimeMillis();
        if (now - lastEmitTime < EMIT_INTERVAL_MS) return;
        lastEmitTime = now;

        counter++;
        JSObject data = new JSObject();
        data.put("counter", counter);
        data.put("timestamp", now);
        // Accelerometer in m/s²
        data.put("accelX", (double) latestAccel[0]);
        data.put("accelY", (double) latestAccel[1]);
        data.put("accelZ", (double) latestAccel[2]);
        // Gyroscope in rad/s
        data.put("gyroX", (double) latestGyro[0]);
        data.put("gyroY", (double) latestGyro[1]);
        data.put("gyroZ", (double) latestGyro[2]);
        data.put("hasGyro", hasGyro);
        data.put("source", "phone");

        notifyListeners("sensorData", data);
    }

    @Override
    public void onAccuracyChanged(Sensor sensor, int accuracy) {
        // Not needed
    }

    @Override
    public void handleOnDestroy() {
        streaming = false;
        if (sensorManager != null) {
            sensorManager.unregisterListener(this);
        }
        super.handleOnDestroy();
    }
}
