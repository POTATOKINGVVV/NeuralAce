/**
 * WearableHUD — real-time overlay showing Mi Band 6 sensor data,
 * heart rate, swing detection, fatigue, and AI coaching alerts.
 */
import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
    Bluetooth, BluetoothOff, Heart, Activity, Zap,
    Volume2, VolumeX, Wifi, WifiOff, Watch,
} from 'lucide-react';
import { useWearable } from '../utils/useWearable';
import '../styles/WearableHUD.css';

const HR_ZONE_COLORS = {
    recovery:  'var(--color-secondary)',
    aerobic:   'var(--color-primary)',
    threshold: 'var(--color-warning)',
    anaerobic: '#ff6600',
    redline:   'var(--color-danger)',
};

const HR_ZONE_LABELS = {
    recovery:  '恢复',
    aerobic:   '有氧',
    threshold: '乳酸阈',
    anaerobic: '无氧',
    redline:   '极限',
};

const STATUS_LABELS = {
    disconnected: '未连接',
    scanning:     '搜索中...',
    connecting:   '连接中...',
    connected:    '已连接',
    streaming:    '实时监测',
};

export default function WearableHUD() {
    const {
        status, devices, heartRate, hrZone, latestIMU,
        alerts, physicalState, ttsEnabled, setTtsEnabled,
        scan, connect, startStreaming, stopStreaming, disconnect,
    } = useWearable();

    const [expanded, setExpanded] = useState(false);
    const [authKey, setAuthKey] = useState('4f1529dd161fb27b100449a90b1e469f');
    const [showConnect, setShowConnect] = useState(false);

    const isStreaming = status === 'streaming';
    const isConnected = status === 'connected' || isStreaming;

    // Latest alert for banner display
    const latestAlert = alerts.length > 0 ? alerts[alerts.length - 1] : null;

    return (
        <div className="wearable-hud">
            {/* ── Floating indicator ──────────────────────────────────── */}
            <motion.button
                className={`wearable-indicator ${isConnected ? 'connected' : ''}`}
                onClick={() => setExpanded(!expanded)}
                whileTap={{ scale: 0.95 }}
            >
                <Watch size={16} />
                {isStreaming && heartRate > 0 && (
                    <span className="hr-badge" style={{ color: HR_ZONE_COLORS[hrZone] }}>
                        {heartRate}
                    </span>
                )}
                {!isConnected && <BluetoothOff size={12} className="status-icon" />}
            </motion.button>

            {/* ── Alert banner ────────────────────────────────────────── */}
            <AnimatePresence>
                {latestAlert && isStreaming && (
                    <motion.div
                        className={`alert-banner priority-${latestAlert.priority}`}
                        initial={{ opacity: 0, y: -20 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -20 }}
                        key={latestAlert.tag + latestAlert.timestamp}
                    >
                        <Zap size={14} />
                        <span>{latestAlert.message}</span>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* ── Expanded panel ──────────────────────────────────────── */}
            <AnimatePresence>
                {expanded && (
                    <motion.div
                        className="wearable-panel"
                        initial={{ opacity: 0, scale: 0.9, y: -10 }}
                        animate={{ opacity: 1, scale: 1, y: 0 }}
                        exit={{ opacity: 0, scale: 0.9, y: -10 }}
                    >
                        <div className="panel-header">
                            <span className="panel-title">
                                <Watch size={14} /> Mi Band 6
                            </span>
                            <span className={`status-label ${status}`}>
                                {STATUS_LABELS[status]}
                            </span>
                        </div>

                        {/* ── Not connected state ───────────────────── */}
                        {!isConnected && !showConnect && (
                            <div className="panel-section">
                                <button className="hud-btn primary" onClick={() => { scan(); setShowConnect(true); }}>
                                    <Bluetooth size={14} /> 搜索手环
                                </button>
                            </div>
                        )}

                        {/* ── Device list + auth key ────────────────── */}
                        {showConnect && !isConnected && (
                            <div className="panel-section">
                                <div className="device-list">
                                    {devices.length === 0 && (
                                        <div className="scanning-hint">正在搜索附近的 Mi Band 6...</div>
                                    )}
                                    {devices.map(d => (
                                        <div key={d.address} className="device-item">
                                            <span>{d.name}</span>
                                            <span className="rssi">{d.rssi}dBm</span>
                                        </div>
                                    ))}
                                </div>
                                {devices.length > 0 && (
                                    <>
                                        <input
                                            className="auth-input"
                                            placeholder="Auth Key (32位十六进制)"
                                            value={authKey}
                                            onChange={e => setAuthKey(e.target.value)}
                                            maxLength={32}
                                        />
                                        <button
                                            className="hud-btn primary"
                                            onClick={() => connect(devices[0].address, authKey)}
                                            disabled={authKey.length !== 32 || status === 'connecting'}
                                        >
                                            {status === 'connecting' ? '认证中...' : '连接'}
                                        </button>
                                    </>
                                )}
                            </div>
                        )}

                        {/* ── Connected controls ────────────────────── */}
                        {isConnected && (
                            <>
                                <div className="panel-section controls-row">
                                    {!isStreaming ? (
                                        <button className="hud-btn primary" onClick={startStreaming}>
                                            <Activity size={14} /> 开始监测
                                        </button>
                                    ) : (
                                        <button className="hud-btn warning" onClick={stopStreaming}>
                                            <WifiOff size={14} /> 暂停
                                        </button>
                                    )}
                                    <button
                                        className={`hud-btn icon-btn ${ttsEnabled ? 'active' : ''}`}
                                        onClick={() => setTtsEnabled(!ttsEnabled)}
                                        title={ttsEnabled ? '关闭语音' : '开启语音'}
                                    >
                                        {ttsEnabled ? <Volume2 size={14} /> : <VolumeX size={14} />}
                                    </button>
                                    <button className="hud-btn danger" onClick={disconnect}>
                                        <BluetoothOff size={14} />
                                    </button>
                                </div>

                                {/* ── Live data ─────────────────────── */}
                                {isStreaming && (
                                    <div className="panel-section live-data">
                                        {/* Heart rate */}
                                        <div className="data-card hr-card">
                                            <Heart
                                                size={20}
                                                className="hr-icon pulsing"
                                                style={{ color: HR_ZONE_COLORS[hrZone] }}
                                            />
                                            <div className="data-value" style={{ color: HR_ZONE_COLORS[hrZone] }}>
                                                {heartRate > 0 ? heartRate : '--'}
                                            </div>
                                            <div className="data-label">BPM</div>
                                            <div className="zone-badge" style={{ background: HR_ZONE_COLORS[hrZone] + '33', color: HR_ZONE_COLORS[hrZone] }}>
                                                {HR_ZONE_LABELS[hrZone]}
                                            </div>
                                        </div>

                                        {/* IMU overview */}
                                        {latestIMU && (
                                            <div className="data-card imu-card">
                                                <Activity size={16} className="imu-icon" />
                                                <div className="imu-axes">
                                                    <span>X: {latestIMU.accelX?.toFixed(1)}</span>
                                                    <span>Y: {latestIMU.accelY?.toFixed(1)}</span>
                                                    <span>Z: {latestIMU.accelZ?.toFixed(1)}</span>
                                                </div>
                                                {latestIMU.hasGyro && (
                                                    <div className="imu-axes gyro">
                                                        <span>Gx: {latestIMU.gyroX?.toFixed(1)}</span>
                                                        <span>Gy: {latestIMU.gyroY?.toFixed(1)}</span>
                                                        <span>Gz: {latestIMU.gyroZ?.toFixed(1)}</span>
                                                    </div>
                                                )}
                                            </div>
                                        )}

                                        {/* Physical state from backend */}
                                        {physicalState && (
                                            <div className="data-card stats-card">
                                                <div className="stat-row">
                                                    <span className="stat-label">总挥拍</span>
                                                    <span className="stat-value">{physicalState.total_swings || 0}</span>
                                                </div>
                                                <div className="stat-row">
                                                    <span className="stat-label">疲劳度</span>
                                                    <span className="stat-value" style={{
                                                        color: (physicalState.fatigue_index || 0) > 0.3
                                                            ? 'var(--color-danger)' : 'var(--color-secondary)'
                                                    }}>
                                                        {Math.round((physicalState.fatigue_index || 0) * 100)}%
                                                    </span>
                                                </div>
                                                {physicalState.recent_intensities && physicalState.recent_intensities.length > 0 && (
                                                    <div className="stat-row">
                                                        <span className="stat-label">近期动作</span>
                                                        <span className="stat-value tags">
                                                            {physicalState.recent_intensities.map((t, i) => (
                                                                <span key={i} className={`intensity-tag ${t}`}>{t}</span>
                                                            ))}
                                                        </span>
                                                    </div>
                                                )}
                                            </div>
                                        )}
                                    </div>
                                )}
                            </>
                        )}
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}
