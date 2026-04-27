package com.stitch.neuralace.plugins.miband;

import android.Manifest;
import android.annotation.SuppressLint;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothGatt;
import android.bluetooth.BluetoothGattCallback;
import android.bluetooth.BluetoothGattCharacteristic;
import android.bluetooth.BluetoothGattDescriptor;
import android.bluetooth.BluetoothManager;
import android.bluetooth.le.BluetoothLeScanner;
import android.bluetooth.le.ScanCallback;
import android.bluetooth.le.ScanFilter;
import android.bluetooth.le.ScanResult;
import android.bluetooth.le.ScanSettings;
import android.content.Context;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;

import androidx.core.app.ActivityCompat;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.UUID;

/**
 * Capacitor plugin that exposes Mi Band 6 BLE communication to the JS layer.
 *
 * JS API:
 *   MiBand6.scan()                         → scans for nearby Mi Band 6 devices
 *   MiBand6.connect({ address, authKey })  → connects + authenticates
 *   MiBand6.startSensorStream()            → starts raw IMU streaming
 *   MiBand6.stopSensorStream()             → stops raw IMU streaming
 *   MiBand6.startHeartRate()               → starts continuous HR monitoring
 *   MiBand6.stopHeartRate()                → stops HR monitoring
 *   MiBand6.disconnect()                   → disconnects from band
 *
 * Events emitted to JS:
 *   "sensorData"   → { counter, timestamp, accelX/Y/Z, gyroX/Y/Z, hasGyro }
 *   "heartRate"    → { bpm, timestamp }
 *   "bandFound"    → { name, address }
 *   "connected"    → { address }
 *   "disconnected" → {}
 *   "authStatus"   → { success, message }
 */
@CapacitorPlugin(
    name = "MiBand6",
    permissions = {
        @Permission(strings = { Manifest.permission.BLUETOOTH_SCAN }, alias = "bluetooth_scan"),
        @Permission(strings = { Manifest.permission.BLUETOOTH_CONNECT }, alias = "bluetooth_connect"),
        @Permission(strings = { Manifest.permission.ACCESS_FINE_LOCATION }, alias = "location"),
    }
)
public class MiBand6Plugin extends Plugin {

    private static final String TAG = "MiBand6Plugin";
    private static final long SCAN_TIMEOUT_MS = 15000;

    private BluetoothAdapter bluetoothAdapter;
    private BluetoothLeScanner bleScanner;
    private BluetoothGatt gatt;
    private MiBand6AuthManager authManager;
    private MiBand6SensorStreamer sensorStreamer;
    private Handler mainHandler = new Handler(Looper.getMainLooper());

    private PluginCall pendingConnectCall;
    private PluginCall pendingSensorCall;
    private PluginCall pendingHrCall;
    private byte[] authKeyBytes;
    private boolean authenticated = false;

    // Track write queue (BLE allows only one write at a time)
    private enum WriteState { IDLE, AUTH_DESC, AUTH_CHAR, SENSOR_DESC, SENSOR_ENABLE, SENSOR_START, HR_DESC, HR_CTRL }
    private WriteState writeState = WriteState.IDLE;

    // ── Lifecycle ──────────────────────────────────────────────────────

    @Override
    public void load() {
        BluetoothManager btManager = (BluetoothManager) getContext().getSystemService(Context.BLUETOOTH_SERVICE);
        if (btManager != null) {
            bluetoothAdapter = btManager.getAdapter();
        }
    }

    // ── Scan for Mi Band 6 ─────────────────────────────────────────────

    @PluginMethod
    public void scan(PluginCall call) {
        // Request permissions first on Android 12+
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            if (!hasPermission(Manifest.permission.BLUETOOTH_SCAN) ||
                !hasPermission(Manifest.permission.BLUETOOTH_CONNECT)) {
                Log.i(TAG, "Requesting BLE permissions");
                requestAllPermissions(call, "handleScanPermissionResult");
                return;
            }
        } else {
            if (!hasPermission(Manifest.permission.ACCESS_FINE_LOCATION)) {
                Log.i(TAG, "Requesting location permission for BLE scan");
                requestAllPermissions(call, "handleScanPermissionResult");
                return;
            }
        }
        executeScan(call);
    }

    @PermissionCallback
    private void handleScanPermissionResult(PluginCall call) {
        boolean granted;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            granted = hasPermission(Manifest.permission.BLUETOOTH_SCAN);
        } else {
            granted = hasPermission(Manifest.permission.ACCESS_FINE_LOCATION);
        }
        if (granted) {
            executeScan(call);
        } else {
            call.reject("BLE permissions denied by user");
        }
    }

    @SuppressLint("MissingPermission")
    private void executeScan(PluginCall call) {
        if (!checkBleAvailable(call)) return;

        bleScanner = bluetoothAdapter.getBluetoothLeScanner();
        if (bleScanner == null) {
            call.reject("BLE scanner not available");
            return;
        }

        Log.i(TAG, "Starting BLE scan for Mi Band 6");

        ScanSettings settings = new ScanSettings.Builder()
                .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
                .build();

        bleScanner.startScan(null, settings, scanCallback);

        // Auto-stop after timeout
        mainHandler.postDelayed(() -> {
            try { bleScanner.stopScan(scanCallback); } catch (Exception ignored) {}
        }, SCAN_TIMEOUT_MS);

        call.resolve(new JSObject().put("scanning", true));
    }

    private final ScanCallback scanCallback = new ScanCallback() {
        @Override
        public void onScanResult(int callbackType, ScanResult result) {
            BluetoothDevice device = result.getDevice();
            @SuppressLint("MissingPermission")
            String name = device.getName();
            if (name != null && (name.contains(MiBand6Constants.DEVICE_NAME_PREFIX)
                    || name.contains(MiBand6Constants.DEVICE_NAME_ALT)
                    || name.contains("Mi Band 6"))) {
                JSObject data = new JSObject();
                data.put("name", name);
                data.put("address", device.getAddress());
                data.put("rssi", result.getRssi());
                notifyListeners("bandFound", data);
            }
        }
    };

    // ── Connect + Authenticate ─────────────────────────────────────────

    @SuppressLint("MissingPermission")
    @PluginMethod
    public void connect(PluginCall call) {
        String address = call.getString("address");
        String authKeyHex = call.getString("authKey");

        if (address == null || authKeyHex == null) {
            call.reject("address and authKey are required");
            return;
        }

        authKeyBytes = hexStringToBytes(authKeyHex);
        if (authKeyBytes == null || authKeyBytes.length != 16) {
            call.reject("authKey must be a 32-char hex string (16 bytes)");
            return;
        }

        if (!checkBleAvailable(call)) return;

        // Stop scanning if active
        if (bleScanner != null) {
            try { bleScanner.stopScan(scanCallback); } catch (Exception ignored) {}
        }

        BluetoothDevice device = bluetoothAdapter.getRemoteDevice(address);
        pendingConnectCall = call;
        authenticated = false;

        Log.i(TAG, "Connecting to " + address);
        gatt = device.connectGatt(getContext(), false, gattCallback, BluetoothDevice.TRANSPORT_LE);
    }

    // ── Sensor Stream Control ──────────────────────────────────────────

    @PluginMethod
    public void startSensorStream(PluginCall call) {
        if (!ensureConnected(call)) return;
        Log.i(TAG, "startSensorStream called");
        pendingSensorCall = call;
        boolean ok = sensorStreamer.startSensorStream();
        if (!ok) {
            pendingSensorCall = null;
            call.reject("Failed to start sensor stream");
        }
    }

    @PluginMethod
    public void stopSensorStream(PluginCall call) {
        if (sensorStreamer != null) {
            sensorStreamer.stopSensorStream();
        }
        call.resolve(new JSObject().put("streaming", false));
    }

    @PluginMethod
    public void startHeartRate(PluginCall call) {
        if (!ensureConnected(call)) return;
        Log.i(TAG, "startHeartRate called");
        pendingHrCall = call;
        boolean ok = sensorStreamer.startHeartRateStream();
        if (!ok) {
            pendingHrCall = null;
            call.reject("Failed to start heart rate");
        }
    }

    @PluginMethod
    public void stopHeartRate(PluginCall call) {
        if (sensorStreamer != null) {
            sensorStreamer.stopHeartRateStream();
        }
        call.resolve(new JSObject().put("heartRateMonitoring", false));
    }

    // ── Disconnect ─────────────────────────────────────────────────────

    @SuppressLint("MissingPermission")
    @PluginMethod
    public void disconnect(PluginCall call) {
        if (sensorStreamer != null) {
            sensorStreamer.stopSensorStream();
            sensorStreamer.stopHeartRateStream();
        }
        if (gatt != null) {
            gatt.disconnect();
            gatt.close();
            gatt = null;
        }
        authenticated = false;
        notifyListeners("disconnected", new JSObject());
        call.resolve(new JSObject().put("disconnected", true));
    }

    // ── GATT Callback (central BLE event handler) ──────────────────────

    private final BluetoothGattCallback gattCallback = new BluetoothGattCallback() {

        @SuppressLint("MissingPermission")
        @Override
        public void onConnectionStateChange(BluetoothGatt g, int status, int newState) {
            Log.i(TAG, "onConnectionStateChange status=" + status + " newState=" + newState);
            if (status != BluetoothGatt.GATT_SUCCESS && newState == BluetoothGatt.STATE_DISCONNECTED) {
                Log.e(TAG, "Connection failed with GATT status " + status + " — retrying with createBond");
                // status 133 = common issue, retry once
                if (status == 133) {
                    mainHandler.postDelayed(() -> {
                        Log.i(TAG, "Retrying connectGatt after status 133");
                        try { g.close(); } catch (Exception ignored) {}
                        BluetoothDevice device = bluetoothAdapter.getRemoteDevice(g.getDevice().getAddress());
                        gatt = device.connectGatt(getContext(), false, gattCallback, BluetoothDevice.TRANSPORT_LE);
                    }, 1000);
                    return;
                }
                authenticated = false;
                notifyListeners("disconnected", new JSObject());
                if (pendingConnectCall != null) {
                    pendingConnectCall.reject("Connection failed (GATT status " + status + ")");
                    pendingConnectCall = null;
                }
                return;
            }
            if (newState == BluetoothGatt.STATE_CONNECTED) {
                Log.i(TAG, "Connected — requesting higher MTU then discovering services");
                g.requestMtu(512);
            } else if (newState == BluetoothGatt.STATE_DISCONNECTED) {
                Log.i(TAG, "Disconnected normally");
                authenticated = false;
                notifyListeners("disconnected", new JSObject());
                if (pendingConnectCall != null) {
                    pendingConnectCall.reject("Connection lost");
                    pendingConnectCall = null;
                }
            }
        }

        @Override
        public void onMtuChanged(BluetoothGatt g, int mtu, int status) {
            Log.i(TAG, "MTU changed to " + mtu + " status=" + status);
            g.discoverServices();
        }

        @Override
        public void onServicesDiscovered(BluetoothGatt g, int status) {
            if (status != BluetoothGatt.GATT_SUCCESS) {
                Log.e(TAG, "Service discovery failed: " + status);
                if (pendingConnectCall != null) {
                    pendingConnectCall.reject("Service discovery failed");
                    pendingConnectCall = null;
                }
                return;
            }

            Log.i(TAG, "Services discovered — starting authentication");
            // Dump all services and characteristics for debugging
            for (android.bluetooth.BluetoothGattService svc : g.getServices()) {
                Log.i(TAG, "Service: " + svc.getUuid());
                for (BluetoothGattCharacteristic ch : svc.getCharacteristics()) {
                    Log.i(TAG, "  Char: " + ch.getUuid() + " props=" + ch.getProperties());
                }
            }
            authManager = new MiBand6AuthManager(g, authKeyBytes);
            sensorStreamer = new MiBand6SensorStreamer(g);
            sensorStreamer.setCallback(sensorCallback);

            authManager.setCallback(new MiBand6AuthManager.AuthCallback() {
                @Override
                public void onAuthSuccess() {
                    authenticated = true;
                    JSObject authData = new JSObject();
                    authData.put("success", true);
                    authData.put("message", "Authentication successful");
                    notifyListeners("authStatus", authData);

                    if (pendingConnectCall != null) {
                        JSObject result = new JSObject();
                        result.put("connected", true);
                        result.put("authenticated", true);
                        pendingConnectCall.resolve(result);
                        pendingConnectCall = null;
                    }
                }

                @Override
                public void onAuthFailed(String reason) {
                    JSObject authData = new JSObject();
                    authData.put("success", false);
                    authData.put("message", reason);
                    notifyListeners("authStatus", authData);

                    if (pendingConnectCall != null) {
                        pendingConnectCall.reject("Auth failed: " + reason);
                        pendingConnectCall = null;
                    }
                }
            });

            authManager.startAuth();
        }

        @Override
        public void onDescriptorWrite(BluetoothGatt g, BluetoothGattDescriptor descriptor, int status) {
            if (status != BluetoothGatt.GATT_SUCCESS) {
                Log.w(TAG, "Descriptor write failed: " + status);
                return;
            }
            UUID charUuid = descriptor.getCharacteristic().getUuid();
            Log.i(TAG, "onDescriptorWrite charUuid=" + charUuid + " status=" + status);
            if (charUuid.equals(MiBand6Constants.CHAR_AUTH)) {
                authManager.onDescriptorWritten();
            } else if (charUuid.equals(MiBand6Constants.CHAR_HR_MEASURE)) {
                sensorStreamer.onHrDescriptorWritten();
            } else if (charUuid.equals(MiBand6Constants.CHAR_SENSOR_CONTROL)) {
                sensorStreamer.onControlDescriptorWritten();
            } else if (charUuid.equals(MiBand6Constants.CHAR_SENSOR_DATA)) {
                sensorStreamer.onSensorDescriptorWritten();
            }
        }

        @Override
        public void onCharacteristicWrite(BluetoothGatt g, BluetoothGattCharacteristic characteristic, int status) {
            UUID charUuid = characteristic.getUuid();
            byte[] value = characteristic.getValue();

            Log.i(TAG, "onCharacteristicWrite charUuid=" + charUuid + " status=" + status);
            if (charUuid.equals(MiBand6Constants.CHAR_SENSOR_CONTROL) && value != null) {
                if (Arrays.equals(value, MiBand6Constants.CMD_SENSOR_START)) {
                    sensorStreamer.onSensorStartWritten();
                } else {
                    // Any other write to sensor control is an enable variant
                    sensorStreamer.onSensorEnableWritten();
                }
                // Resolve pending call — actual success determined by notification response
                if (pendingSensorCall != null) {
                    pendingSensorCall.resolve(new JSObject().put("streaming", true));
                    pendingSensorCall = null;
                }
            } else if (charUuid.equals(MiBand6Constants.CHAR_HR_CONTROL)) {
                Log.i(TAG, "HR control written — heart rate monitoring active");
                if (pendingHrCall != null) {
                    pendingHrCall.resolve(new JSObject().put("heartRateMonitoring", true));
                    pendingHrCall = null;
                }
            }
        }

        @SuppressLint("MissingPermission")
        @Override
        public void onCharacteristicChanged(BluetoothGatt g, BluetoothGattCharacteristic characteristic) {
            UUID charUuid = characteristic.getUuid();
            byte[] value = characteristic.getValue();

            StringBuilder hex = new StringBuilder();
            if (value != null) {
                for (int i = 0; i < Math.min(value.length, 20); i++) {
                    hex.append(String.format("%02x ", value[i]));
                }
            }
            Log.d(TAG, "onCharacteristicChanged uuid=" + charUuid + " len=" + (value != null ? value.length : 0) + " hex=[" + hex.toString().trim() + "]");

            if (charUuid.equals(MiBand6Constants.CHAR_AUTH)) {
                authManager.onAuthNotification(value);
            } else if (charUuid.equals(MiBand6Constants.CHAR_SENSOR_CONTROL)) {
                sensorStreamer.onSensorControlNotification(value);
            } else if (charUuid.equals(MiBand6Constants.CHAR_SENSOR_DATA)) {
                sensorStreamer.onSensorDataNotification(value);
            } else if (charUuid.equals(MiBand6Constants.CHAR_HR_MEASURE)) {
                sensorStreamer.onHeartRateNotification(value);
            }
        }
    };

    // ── Sensor data callback → emit to JS ──────────────────────────────

    private final MiBand6SensorStreamer.SensorCallback sensorCallback = new MiBand6SensorStreamer.SensorCallback() {
        @Override
        public void onSensorData(JSONObject data) {
            JSObject jsData = new JSObject();
            try {
                jsData.put("counter",   data.getLong("counter"));
                jsData.put("timestamp", data.getLong("timestamp"));
                jsData.put("accelX",    data.getDouble("accelX"));
                jsData.put("accelY",    data.getDouble("accelY"));
                jsData.put("accelZ",    data.getDouble("accelZ"));
                jsData.put("gyroX",     data.getDouble("gyroX"));
                jsData.put("gyroY",     data.getDouble("gyroY"));
                jsData.put("gyroZ",     data.getDouble("gyroZ"));
                jsData.put("hasGyro",   data.getBoolean("hasGyro"));
            } catch (Exception e) {
                Log.e(TAG, "Error converting sensor data: " + e.getMessage());
                return;
            }
            notifyListeners("sensorData", jsData);
        }

        @Override
        public void onHeartRate(int bpm) {
            JSObject hrData = new JSObject();
            hrData.put("bpm", bpm);
            hrData.put("timestamp", System.currentTimeMillis());
            notifyListeners("heartRate", hrData);
        }

        @Override
        public void onError(String message) {
            Log.e(TAG, "Sensor error: " + message);
        }
    };

    // ── Helpers ────────────────────────────────────────────────────────

    private boolean checkBleAvailable(PluginCall call) {
        if (bluetoothAdapter == null || !bluetoothAdapter.isEnabled()) {
            call.reject("Bluetooth is not available or not enabled");
            return false;
        }
        return true;
    }

    private boolean ensureConnected(PluginCall call) {
        if (gatt == null || !authenticated) {
            call.reject("Not connected or not authenticated. Call connect() first.");
            return false;
        }
        return true;
    }

    private static byte[] hexStringToBytes(String hex) {
        if (hex == null) return null;
        hex = hex.replaceAll("[^0-9a-fA-F]", "");
        if (hex.length() % 2 != 0) return null;
        byte[] bytes = new byte[hex.length() / 2];
        for (int i = 0; i < bytes.length; i++) {
            bytes[i] = (byte) Integer.parseInt(hex.substring(i * 2, i * 2 + 2), 16);
        }
        return bytes;
    }
}
