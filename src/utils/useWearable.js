/**
 * useWearable — React hook managing Mi Band 6 BLE connection,
 * real-time sensor data, WebSocket coaching, and TTS output.
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import MiBand6 from './miband6';
import { registerPlugin } from '@capacitor/core';
import { Capacitor } from '@capacitor/core';
import ttsEngine from './tts';

const PhoneSensor = Capacitor.isNativePlatform()
    ? registerPlugin('PhoneSensor')
    : null;

const WS_URL = 'ws://10.241.96.164:8000/ws/wearable';
const SENSOR_SEND_INTERVAL = 80; // ms, throttle WebSocket sends
const WEARABLE_TELEMETRY_EVENT = 'neuralace:wearable-telemetry';

export function useWearable() {
    // ── State ──────────────────────────────────────────────────────────
    const [status, setStatus] = useState('disconnected'); // disconnected | scanning | connecting | connected | streaming
    const [devices, setDevices] = useState([]);
    const [heartRate, setHeartRate] = useState(0);
    const [hrZone, setHrZone] = useState('recovery');
    const [latestIMU, setLatestIMU] = useState(null);
    const [alerts, setAlerts] = useState([]);
    const [physicalState, setPhysicalState] = useState(null);
    const [ttsEnabled, setTtsEnabled] = useState(true);
    const [wsConnected, setWsConnected] = useState(false);

    const wsRef = useRef(null);
    const listenersRef = useRef([]);
    const lastSendRef = useRef(0);

    // ── TTS sync ───────────────────────────────────────────────────────
    useEffect(() => { ttsEngine.enabled = ttsEnabled; }, [ttsEnabled]);

    // ── Broadcast lightweight telemetry to other UI surfaces ──────────
    useEffect(() => {
        if (typeof window === 'undefined') return;

        window.dispatchEvent(new CustomEvent(WEARABLE_TELEMETRY_EVENT, {
            detail: {
                status,
                heartRate,
                hrZone,
                latestIMU,
                physicalState,
                alerts,
                wsConnected,
                timestamp: Date.now(),
            },
        }));
    }, [status, heartRate, hrZone, latestIMU, physicalState, alerts, wsConnected]);

    // ── WebSocket connection ───────────────────────────────────────────
    const connectWS = useCallback(() => {
        if (wsRef.current && wsRef.current.readyState <= 1) return;
        const ws = new WebSocket(WS_URL);
        ws.onopen = () => {
            setWsConnected(true);
        };
        ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                if (msg.alerts && msg.alerts.length > 0) {
                    setAlerts(msg.alerts);
                    ttsEngine.speakAlerts(msg.alerts);
                }
                if (msg.physical_state) {
                    setPhysicalState(msg.physical_state);
                    if (msg.physical_state.hr_zone) {
                        setHrZone(msg.physical_state.hr_zone);
                    }
                }
            } catch (e) { /* ignore parse errors */ }
        };
        ws.onclose = () => {
            wsRef.current = null;
            setWsConnected(false);
        };
        wsRef.current = ws;
    }, []);

    const sendToBackend = useCallback((data) => {
        const now = Date.now();
        if (now - lastSendRef.current < SENSOR_SEND_INTERVAL) return;
        lastSendRef.current = now;
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify(data));
        }
    }, []);

    // ── Scan ───────────────────────────────────────────────────────────
    const scan = useCallback(async () => {
        setDevices([]);
        setStatus('scanning');
        const handler = MiBand6.addListener('bandFound', (device) => {
            setDevices(prev => {
                if (prev.some(d => d.address === device.address)) return prev;
                return [...prev, device];
            });
        });
        listenersRef.current.push(handler);
        await MiBand6.scan();
    }, []);

    // ── Connect ────────────────────────────────────────────────────────
    const connect = useCallback(async (address, authKey) => {
        setStatus('connecting');
        try {
            await MiBand6.connect({ address, authKey });
            setStatus('connected');
            connectWS();
        } catch (e) {
            setStatus('disconnected');
            throw e;
        }
    }, [connectWS]);

    // ── Start all streams ──────────────────────────────────────────────
    const startStreaming = useCallback(async () => {
        // IMU data from phone sensors (accel + gyro)
        if (PhoneSensor) {
            const sensorHandler = PhoneSensor.addListener('sensorData', (data) => {
                setLatestIMU(data);
                sendToBackend({ type: 'imu', ...data, heartRate: heartRate });
            });
            listenersRef.current.push(sensorHandler);
        }

        // Heart rate from Mi Band 6
        const hrHandler = MiBand6.addListener('heartRate', (data) => {
            setHeartRate(data.bpm);
            sendToBackend({ type: 'heartRate', bpm: data.bpm, timestamp: data.timestamp });
        });
        listenersRef.current.push(hrHandler);

        // Disconnection listener
        const dcHandler = MiBand6.addListener('disconnected', () => {
            setStatus('disconnected');
            setHeartRate(0);
        });
        listenersRef.current.push(dcHandler);

        // Start phone IMU stream (accel + gyro from phone's built-in sensors)
        if (PhoneSensor) {
            await PhoneSensor.startSensorStream();
        }
        // Start Mi Band 6 heart rate only (raw IMU not supported by Mi Band 6 firmware)
        await MiBand6.startHeartRate();
        setStatus('streaming');
    }, [heartRate, sendToBackend]);

    // ── Stop ───────────────────────────────────────────────────────────
    const stopStreaming = useCallback(async () => {
        if (PhoneSensor) {
            await PhoneSensor.stopSensorStream();
        }
        await MiBand6.stopHeartRate();
        setStatus('connected');
    }, []);

    // ── Disconnect ─────────────────────────────────────────────────────
    const disconnect = useCallback(async () => {
        ttsEngine.stop();
        await MiBand6.disconnect();
        if (wsRef.current) wsRef.current.close();
        wsRef.current = null;
        setWsConnected(false);
        setStatus('disconnected');
        setHeartRate(0);
        setLatestIMU(null);
        setAlerts([]);
        setPhysicalState(null);
    }, []);

    // ── Cleanup on unmount ─────────────────────────────────────────────
    useEffect(() => {
        return () => {
            listenersRef.current.forEach(h => { if (h && h.remove) h.remove(); });
            listenersRef.current = [];
            ttsEngine.stop();
            if (wsRef.current) wsRef.current.close();
        };
    }, []);

    return {
        status,
        devices,
        heartRate,
        hrZone,
        latestIMU,
        alerts,
        physicalState,
        ttsEnabled,
        setTtsEnabled,
        scan,
        connect,
        startStreaming,
        stopStreaming,
        disconnect,
    };
}
