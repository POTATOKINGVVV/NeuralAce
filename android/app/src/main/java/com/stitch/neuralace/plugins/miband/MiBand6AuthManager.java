package com.stitch.neuralace.plugins.miband;

import android.bluetooth.BluetoothGatt;
import android.bluetooth.BluetoothGattCallback;
import android.bluetooth.BluetoothGattCharacteristic;
import android.bluetooth.BluetoothGattDescriptor;
import android.util.Log;

import javax.crypto.Cipher;
import javax.crypto.spec.SecretKeySpec;
import java.util.Arrays;

/**
 * Handles the 3-step AES-ECB authentication handshake with Mi Band 6.
 *
 * Flow:
 *   Step 1  →  Send auth key to band
 *   Step 2  ←  Receive encrypted random nonce from band
 *   Step 3  →  Encrypt nonce with AES-ECB(authKey) and send back
 *   Done    ←  Band responds with AUTH_OK
 */
public class MiBand6AuthManager {

    private static final String TAG = "MiBand6Auth";

    public interface AuthCallback {
        void onAuthSuccess();
        void onAuthFailed(String reason);
    }

    private final BluetoothGatt gatt;
    private final byte[] authKey;          // 16-byte secret key
    private AuthCallback callback;
    private int authStep = 0;

    public MiBand6AuthManager(BluetoothGatt gatt, byte[] authKey) {
        this.gatt = gatt;
        this.authKey = authKey;
    }

    public void setCallback(AuthCallback callback) {
        this.callback = callback;
    }

    private boolean triedKeyRegister = false;

    // ── Initiate authentication ────────────────────────────────────────
    public void startAuth() {
        authStep = 2;  // Try requesting nonce directly (key already registered)
        Log.i(TAG, "Auth: Enabling notifications on AUTH characteristic");

        BluetoothGattCharacteristic authChar = getAuthCharacteristic();
        if (authChar == null) {
            fail("AUTH characteristic not found");
            return;
        }

        // Enable notifications for auth responses
        gatt.setCharacteristicNotification(authChar, true);
        BluetoothGattDescriptor desc = authChar.getDescriptor(MiBand6Constants.DESC_CCC);
        if (desc != null) {
            desc.setValue(BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE);
            gatt.writeDescriptor(desc);
        } else {
            // Some firmware versions don't require CCC; proceed directly
            requestNonce();
        }
    }

    // Called after CCC descriptor is written successfully
    public void onDescriptorWritten() {
        if (authStep == 2) {
            requestNonce();
        } else if (authStep == 1) {
            sendAuthKey();
        }
    }

    // ── Handle notification from AUTH characteristic ───────────────────
    public void onAuthNotification(byte[] value) {
        if (value == null || value.length < 3) {
            fail("Empty auth notification");
            return;
        }

        Log.i(TAG, "Auth notification: step=" + authStep + " len=" + value.length
                + " prefix=" + String.format("%02x %02x %02x", value[0], value[1], value[2]));

        if (authStep == 1) {
            // Expect key-accepted response, then request nonce
            if (value[0] == 0x10 && value[1] == 0x01 && value[2] == 0x01) {
                Log.i(TAG, "Auth Step 1 OK — key accepted, requesting nonce");
                authStep = 2;
                requestNonce();
            } else {
                fail("Key registration rejected: " + bytesToHex(value));
            }
        } else if (authStep == 2) {
            // Expect nonce response (0x10 0x02 0x01 + 16 bytes of challenge)
            if (value[0] == 0x10 && value[1] == 0x02 && value[2] == 0x01 && value.length >= 19) {
                byte[] nonce = Arrays.copyOfRange(value, 3, 19);
                Log.i(TAG, "Auth Step 2 OK — nonce received, encrypting");
                authStep = 3;
                sendEncryptedNonce(nonce);
            } else if (value[0] == 0x10 && value[1] == 0x02 && value[2] == 0x04) {
                // 0x04 = key not registered yet, need to send key first
                Log.i(TAG, "Key not registered — sending auth key first");
                if (!triedKeyRegister) {
                    triedKeyRegister = true;
                    authStep = 1;
                    sendAuthKey();
                } else {
                    fail("Key registration failed after retry");
                }
            } else {
                // Unknown response — try sending key as fallback
                Log.w(TAG, "Unexpected nonce response: " + bytesToHex(value) + " — trying key registration");
                if (!triedKeyRegister) {
                    triedKeyRegister = true;
                    authStep = 1;
                    sendAuthKey();
                } else {
                    fail("Auth failed: " + bytesToHex(value));
                }
            }
        } else if (authStep == 3) {
            // Expect auth-success (0x10 0x03 0x01)
            if (value[0] == 0x10 && value[1] == 0x03 && value[2] == 0x01) {
                Log.i(TAG, "Auth Step 3 OK — authentication successful!");
                authStep = 0;
                if (callback != null) callback.onAuthSuccess();
            } else {
                fail("Auth failed at final step: " + bytesToHex(value));
            }
        }
    }

    // ── Internal helpers ───────────────────────────────────────────────

    private void sendAuthKey() {
        Log.i(TAG, "Auth Step 1: Sending auth key");
        byte[] payload = new byte[2 + authKey.length];
        System.arraycopy(MiBand6Constants.AUTH_SEND_KEY_CMD, 0, payload, 0, 2);
        System.arraycopy(authKey, 0, payload, 2, authKey.length);
        writeAuthChar(payload);
    }

    private void requestNonce() {
        Log.i(TAG, "Auth Step 2: Requesting nonce");
        writeAuthChar(MiBand6Constants.AUTH_REQUEST_NONCE_CMD);
    }

    private void sendEncryptedNonce(byte[] nonce) {
        try {
            Cipher cipher = Cipher.getInstance("AES/ECB/NoPadding");
            SecretKeySpec keySpec = new SecretKeySpec(authKey, "AES");
            cipher.init(Cipher.ENCRYPT_MODE, keySpec);
            byte[] encrypted = cipher.doFinal(nonce);

            byte[] payload = new byte[2 + encrypted.length];
            System.arraycopy(MiBand6Constants.AUTH_SEND_ENCRYPTED_CMD, 0, payload, 0, 2);
            System.arraycopy(encrypted, 0, payload, 2, encrypted.length);

            Log.i(TAG, "Auth Step 3: Sending encrypted nonce");
            writeAuthChar(payload);
        } catch (Exception e) {
            fail("AES encryption failed: " + e.getMessage());
        }
    }

    private void writeAuthChar(byte[] value) {
        BluetoothGattCharacteristic authChar = getAuthCharacteristic();
        if (authChar == null) {
            fail("AUTH characteristic not found during write");
            return;
        }
        authChar.setValue(value);
        gatt.writeCharacteristic(authChar);
    }

    private BluetoothGattCharacteristic getAuthCharacteristic() {
        if (gatt.getService(MiBand6Constants.SERVICE_AUTH) == null) return null;
        return gatt.getService(MiBand6Constants.SERVICE_AUTH)
                .getCharacteristic(MiBand6Constants.CHAR_AUTH);
    }

    private void fail(String reason) {
        Log.e(TAG, "Auth failed: " + reason);
        authStep = 0;
        if (callback != null) callback.onAuthFailed(reason);
    }

    private static String bytesToHex(byte[] bytes) {
        StringBuilder sb = new StringBuilder();
        for (byte b : bytes) sb.append(String.format("%02x ", b));
        return sb.toString().trim();
    }
}
