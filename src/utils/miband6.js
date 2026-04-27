/**
 * MiBand6 — Capacitor JS bridge for the native MiBand6Plugin.
 *
 * On native Android:  communicates through the real BLE plugin.
 * On web (dev):        provides a mock that emits simulated sensor data.
 */
import { registerPlugin } from '@capacitor/core';
import { Capacitor } from '@capacitor/core';

const MiBand6Native = registerPlugin('MiBand6');

// ── Detect platform ────────────────────────────────────────────────────────
const isNative = Capacitor.isNativePlatform();

// ── Mock for web development ───────────────────────────────────────────────
class MiBand6Mock {
    _listeners = {};
    _sensorInterval = null;
    _hrInterval = null;

    async scan() {
        setTimeout(() => {
            this._emit('bandFound', {
                name: 'Mi Smart Band 6 [MOCK]',
                address: 'AA:BB:CC:DD:EE:FF',
                rssi: -55,
            });
        }, 1000);
        return { scanning: true };
    }

    async connect() {
        setTimeout(() => {
            this._emit('authStatus', { success: true, message: 'Mock auth OK' });
        }, 500);
        return { connected: true, authenticated: true };
    }

    async startSensorStream() {
        let counter = 0;
        this._sensorInterval = setInterval(() => {
            counter++;
            const baseAccel = 9.81;
            // Simulate occasional swings (spikes)
            const isSwing = Math.random() < 0.03;
            const swingBoost = isSwing ? 30 + Math.random() * 40 : 0;
            this._emit('sensorData', {
                counter,
                timestamp: Date.now(),
                accelX: (Math.random() - 0.5) * 4 + swingBoost * 0.6,
                accelY: (Math.random() - 0.5) * 4 + swingBoost * 0.3,
                accelZ: baseAccel + (Math.random() - 0.5) * 2 + swingBoost * 0.4,
                gyroX: (Math.random() - 0.5) * 10 + (isSwing ? 5 : 0),
                gyroY: (Math.random() - 0.5) * 10,
                gyroZ: (Math.random() - 0.5) * 10,
                hasGyro: true,
            });
        }, 40); // ~25Hz
        return { streaming: true };
    }

    async stopSensorStream() {
        if (this._sensorInterval) clearInterval(this._sensorInterval);
        this._sensorInterval = null;
        return { streaming: false };
    }

    async startHeartRate() {
        let bpm = 85;
        this._hrInterval = setInterval(() => {
            // Slowly drift HR up and down
            bpm += (Math.random() - 0.45) * 3;
            bpm = Math.max(60, Math.min(195, bpm));
            this._emit('heartRate', {
                bpm: Math.round(bpm),
                timestamp: Date.now(),
            });
        }, 2000);
        return { heartRateMonitoring: true };
    }

    async stopHeartRate() {
        if (this._hrInterval) clearInterval(this._hrInterval);
        this._hrInterval = null;
        return { heartRateMonitoring: false };
    }

    async disconnect() {
        this.stopSensorStream();
        this.stopHeartRate();
        this._emit('disconnected', {});
        return { disconnected: true };
    }

    addListener(event, fn) {
        if (!this._listeners[event]) this._listeners[event] = [];
        this._listeners[event].push(fn);
        return { remove: () => { this._listeners[event] = this._listeners[event].filter(f => f !== fn); } };
    }

    _emit(event, data) {
        (this._listeners[event] || []).forEach(fn => fn(data));
    }
}

// ── Export the right implementation ────────────────────────────────────────
const MiBand6 = isNative ? MiBand6Native : new MiBand6Mock();

export default MiBand6;
