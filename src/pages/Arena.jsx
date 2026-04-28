import React, {
    useCallback, useEffect, useRef, useState,
} from 'react';
import {
    Upload,
    Activity,
    Shield,
    Zap,
    Camera,
    Video,
    TriangleAlert,
    Sparkles,
    Gauge,
    BrainCircuit,
    Radar,
    Siren,
    CircleAlert,
    Route,
    ScrollText,
    Swords,
    GitBranch,
    Flag,
    Target,
    Watch,
    Bluetooth,
    Wifi,
    Heart,
    Cloud,
    Smartphone,
    Mic,
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import Webcam from 'react-webcam';
import { api } from '../utils/api';
import { useGame } from '../context/GameContext';
import { soundManager } from '../utils/SoundManager';
import ttsEngine from '../utils/tts';
import '../styles/Arena.css';

const getModeLabel = (mode) => (mode === 'doubles' ? '双打' : '单打');

const getConfidenceLabel = (label) => {
    if (label === 'high') return '高置信度';
    if (label === 'low') return '探索中';
    return '均衡';
};

const getResultLabel = (result) => {
    if (result === 'LOSS') return '负';
    return '胜';
};

const normalizeAutoResult = (result) => {
    if (result === 'LOSS') return 'LOSS';
    return 'WIN';
};

const getQualityLabel = (quality) => {
    if (quality === 'high') return '高';
    if (quality === 'medium') return '中';
    if (quality === 'low') return '低';
    if (quality === 'warming') return '预热中';
    if (quality === 'offline') return '离线';
    return String(quality || '未知').toUpperCase();
};

const formatGyroAxis = (value) => {
    const numericValue = Number(value);
    if (!Number.isFinite(numericValue)) {
        return '--';
    }
    return numericValue.toFixed(2);
};

const getGyroLevel = (value) => {
    const numericValue = Number(value);
    if (!Number.isFinite(numericValue)) {
        return 0;
    }

    const NORMALIZED_MAX = 8;
    return Math.min(100, Math.round((Math.abs(numericValue) / NORMALIZED_MAX) * 100));
};

const getRiskLabel = (label) => {
    if (label === 'high') return '高对抗风险';
    if (label === 'medium') return '对抗预警';
    return '对抗稳定';
};

const SIGNAL_LABEL_MAP = {
    'absorb-and-redirect': '吸收反击',
    'reset-and-rebuild': '重置重建',
    'front-court-trap': '前场陷阱',
    'attritional-pressure': '消耗压力',
    'compression-attack': '压缩进攻',
    'deception': '假动作',
    'interception': '截击',
    'managed-pressure': '控制压力',
    'topspin-attack': '上旋进攻',
    'short-game': '短球',
    'serve-variation': '发球变化',
    'balanced': '均衡',
    'control': '控制',
    'attack': '进攻',
    'defense': '防守',
    'surging': '上升势头',
    'neutral': '中性',
    'under-pressure': '被动',
    'releasing-pressure': '压力释放',
    'increasing': '上升',
    'steady': '平稳',
    'weaponize': '武器化',
    'refine': '精炼',
    'probe': '探索',
    'stabilize': '稳固',
    'first-two-shots': '前两拍',
    'fourth-ball': '第四板',
    'opening': '开局',
    'turn': '转折',
    'adapt': '适应',
    'closing': '收官',
    'duel': '对抗',
    'topspin-loop': '弧圈球',
    'direct-pressure': '直接施压',
    'soft-control': '轻柔控制',
    'flat-drive': '平抽',
    'releasing-pressure-streak': '压力释放连胜',
    'surging-streak': '上升连胜',
    'adaptation-live': '适应进行中',
    'spin-rally': '旋转相持',
    'control-phase': '控制阶段',
    'rear_channel': '后场通道',
    'front_channel': '前场通道',
    'mid_channel': '中场通道',
    'A_deep_wide': 'A侧深远',
    'B_deep_wide': 'B侧深远',
    'center': '中心',
    'unknown': '未知',
    'advantage': '优势',
    'under_pressure': '被动',
    'transition': '过渡',
    'exploit': '利用',
    'balanced': '均衡',
    'strong': '强',
    'medium': '中',
    'low': '低',
    'high': '高',
    'fast': '快',
    'slow': '慢',
    'clean': '干净',
};

const formatSignalLabel = (value) => {
    if (!value) {
        return '未知';
    }

    const key = String(value);
    if (SIGNAL_LABEL_MAP[key]) {
        return SIGNAL_LABEL_MAP[key];
    }

    return key
        .split(/[_-]/)
        .filter(Boolean)
        .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
        .join(' ');
};

const toPercentLabel = (value) => `${Math.round((Number(value) || 0) * 100)}%`;

const toSignedPercentLabel = (value) => {
    const numericValue = Number(value) || 0;
    const prefix = numericValue > 0 ? '+' : '';
    return `${prefix}${Math.round(numericValue * 100)}%`;
};

const toFeedbackItems = (value) => {
    if (!value || typeof value !== 'string') {
        return [];
    }

    return value
        .split('|')
        .map((item) => item.trim())
        .filter(Boolean);
};

const toArray = (value) => (Array.isArray(value) ? value : []);

const WEARABLE_TELEMETRY_EVENT = 'neuralace:wearable-telemetry';
const EVENT_WINDOW_MS = 30000;

const WEARABLE_STATUS_LABELS = {
    disconnected: '离线',
    scanning: '搜索中',
    connecting: '连接中',
    connected: '在线',
    streaming: '实时监测',
};

const DEMO_INERTIAL_LABELS = [
    '恢复步伐',
    '中强度对抗',
    '连续攻防',
    '节奏回稳',
];

const buildFusionAdvice = ({ result, wearableStatus, inertialTag, demoAugmentedEnabled }) => {
    const pressure = Number(result?.physics?.pressure_index) || 0;
    const autoResult = normalizeAutoResult(result?.auto_result || result?.summary?.verdict || 'UNKNOWN');

    let advice = '当前训练节奏稳定，建议保持启动速度并提前完成还原。';

    if (pressure >= 0.72) {
        advice = '当前训练负荷上升、节奏波动，建议先恢复步伐，再进入下一拍衔接。';
    } else if (autoResult === 'LOSS') {
        advice = '当前回合压力偏高，建议先稳住重心，再通过节奏变化争取主动。';
    }

    if (wearableStatus === 'disconnected') {
        advice = `${advice} 当前为降级模式，建议连接手环以启用多源状态融合。`;
    }

    if (demoAugmentedEnabled && inertialTag) {
        advice = `${advice} 增强模式状态：${inertialTag}。`;
    }

    return advice;
};

const metricCards = (analysisResult) => {
    const policyUpdate = analysisResult?.diagnostics?.policy_update || {};
    const rallyState = analysisResult?.physics?.rally_state || {};

    return [
        {
            label: '裁决置信度',
            value: toPercentLabel(analysisResult?.physics?.referee_confidence),
            icon: Gauge,
            tone: 'cyan',
        },
        {
            label: '落点置信度',
            value: toPercentLabel(rallyState?.landing_confidence),
            icon: Shield,
            tone: 'green',
        },
        {
            label: '方向一致性',
            value: toPercentLabel(rallyState?.direction_consistency),
            icon: Activity,
            tone: 'amber',
        },
        {
            label: '轨迹质量',
            value: toPercentLabel(analysisResult?.physics?.trajectory_quality),
            icon: Radar,
            tone: 'cyan',
        },
        {
            label: '分析质量',
            value: getQualityLabel(analysisResult?.diagnostics?.analysis_quality || 'medium'),
            icon: BrainCircuit,
            tone: 'amber',
        },
        {
            label: '策略适配等级',
            value: (policyUpdate?.adaptation_level || 'n/a').toUpperCase(),
            icon: Sparkles,
            tone: 'violet',
        },
    ];
};

const Arena = () => {
    const { addMatchRecord, debugMode } = useGame();
    const [mode, setMode] = useState('singles');
    const [sportType, setSportType] = useState('badminton');
    const [status, setStatus] = useState('idle');
    const [analysisResult, setAnalysisResult] = useState(null);
    const [videoUrl, setVideoUrl] = useState(null);
    const [isCameraMode, setIsCameraMode] = useState(false);
    const [isRecording, setIsRecording] = useState(false);
    const [timeLeft, setTimeLeft] = useState(0);
    const [demoAugmentedEnabled, setDemoAugmentedEnabled] = useState(false);
    const [demoModeTick, setDemoModeTick] = useState(0);
    const [wearableTelemetry, setWearableTelemetry] = useState({
        status: 'disconnected',
        heartRate: 0,
        latestIMU: null,
        physicalState: null,
        alerts: [],
        wsConnected: false,
        timestamp: 0,
    });
    const [iotEvents, setIotEvents] = useState([]);
    const [iotKpi, setIotKpi] = useState({
        connectionAttempts: 0,
        connectionSuccesses: 0,
        reportFrequency: 0,
        alertTriggers: 0,
    });

    const fileInputRef = useRef(null);
    const webcamRef = useRef(null);
    const timerRef = useRef(null);
    const mediaRecorderRef = useRef(null);
    const recordedChunksRef = useRef([]);
    const isMountedRef = useRef(true);
    const telemetryCounterRef = useRef({ count: 0, windowStart: Date.now() });
    const wearableStateRef = useRef({ status: 'disconnected', heartRate: 0, alertCount: 0 });

    const pushIotEvent = useCallback((message, kind = 'system') => {
        const item = {
            id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
            ts: Date.now(),
            kind,
            message,
        };

        setIotEvents((prev) => [item, ...prev].filter((event) => item.ts - event.ts <= EVENT_WINDOW_MS).slice(0, 12));
    }, []);

    const speakAdvice = useCallback((text) => {
        if (!text || !('speechSynthesis' in window) || !ttsEngine.enabled) {
            return;
        }

        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = 'zh-CN';
        utterance.rate = 1.03;
        window.speechSynthesis.speak(utterance);
    }, []);

    useEffect(() => {
        const onTelemetry = (event) => {
            const detail = event.detail || {};
            setWearableTelemetry((previous) => ({ ...previous, ...detail }));

            setIotEvents((previous) => {
                const now = Date.now();
                return previous.filter((item) => now - item.ts <= EVENT_WINDOW_MS);
            });

            const previousState = wearableStateRef.current;
            const nextStatus = detail.status || previousState.status;

            if (nextStatus !== previousState.status) {
                pushIotEvent(`设备状态: ${WEARABLE_STATUS_LABELS[nextStatus] || nextStatus}`, 'device');

                if (nextStatus === 'connecting' || nextStatus === 'scanning') {
                    setIotKpi((prev) => ({ ...prev, connectionAttempts: prev.connectionAttempts + 1 }));
                }

                if ((nextStatus === 'connected' || nextStatus === 'streaming')
                    && previousState.status !== 'connected'
                    && previousState.status !== 'streaming') {
                    setIotKpi((prev) => ({ ...prev, connectionSuccesses: prev.connectionSuccesses + 1 }));
                }
            }

            const nextHeartRate = Number(detail.heartRate) || 0;
            if (nextHeartRate > 0 && Math.abs(nextHeartRate - previousState.heartRate) >= 8) {
                pushIotEvent(`心率状态更新: ${nextHeartRate} BPM`, 'vitals');
            }

            const alertCount = Array.isArray(detail.alerts) ? detail.alerts.length : previousState.alertCount;
            if (alertCount > previousState.alertCount) {
                const latestAlert = detail.alerts?.[alertCount - 1];
                setIotKpi((prev) => ({ ...prev, alertTriggers: prev.alertTriggers + 1 }));
                pushIotEvent(`告警触发: ${latestAlert?.message || '状态告警'}`, 'alert');
            }

            wearableStateRef.current = {
                status: nextStatus,
                heartRate: nextHeartRate,
                alertCount,
            };

            const now = Date.now();
            const counter = telemetryCounterRef.current;
            counter.count += 1;
            const elapsed = now - counter.windowStart;

            if (elapsed >= 6000) {
                const frequency = Math.round((counter.count * 1000) / elapsed);
                setIotKpi((prev) => ({ ...prev, reportFrequency: frequency }));
                telemetryCounterRef.current = { count: 0, windowStart: now };
            }
        };

        window.addEventListener(WEARABLE_TELEMETRY_EVENT, onTelemetry);
        return () => {
            window.removeEventListener(WEARABLE_TELEMETRY_EVENT, onTelemetry);
        };
    }, [pushIotEvent]);

    useEffect(() => {
        if (!demoAugmentedEnabled) {
            return undefined;
        }

        const timer = setInterval(() => {
            setDemoModeTick((tick) => tick + 1);
        }, 1200);

        return () => clearInterval(timer);
    }, [demoAugmentedEnabled]);

    useEffect(() => {
        pushIotEvent('IoT 指挥舱已就绪，等待设备接入。', 'system');
    }, [pushIotEvent]);

    const clearTimer = useCallback(() => {
        if (timerRef.current) {
            clearInterval(timerRef.current);
            timerRef.current = null;
        }
    }, []);

    const revokeVideoUrl = useCallback((url) => {
        if (url?.startsWith('blob:')) {
            URL.revokeObjectURL(url);
        }
    }, []);

    const processAnalysis = useCallback(async (file) => {
        if (!isMountedRef.current) {
            return;
        }

        setStatus('analyzing');
        pushIotEvent('分析任务启动: 视频数据上云处理。', 'pipeline');

        try {
            const result = await api.uploadVideo(file, { isDebug: debugMode, matchType: mode, sportType });
            if (!isMountedRef.current) {
                revokeVideoUrl(result.videoUrl);
                return;
            }

            const normalizedResult = {
                ...result,
                auto_result: normalizeAutoResult(result?.auto_result || result?.summary?.verdict || 'UNKNOWN'),
            };

            setAnalysisResult(normalizedResult);
            setVideoUrl((previousUrl) => {
                revokeVideoUrl(previousUrl);
                return result.videoUrl;
            });
            setStatus('complete');

            const inertialTag = demoAugmentedEnabled
                ? DEMO_INERTIAL_LABELS[Math.floor(demoModeTick / 2) % DEMO_INERTIAL_LABELS.length]
                : '';

            const fusionAdvice = buildFusionAdvice({
                result,
                wearableStatus: wearableTelemetry.status,
                inertialTag,
                demoAugmentedEnabled,
            });
            speakAdvice(fusionAdvice);

            pushIotEvent('分析完成: 边端云反馈闭环已更新。', 'pipeline');

            addMatchRecord({
                video: result.videoUrl,
                type: result.physics?.event || '训练片段',
                result: normalizedResult.auto_result,
                duration: result.physics?.duration ? `${result.physics.duration}s` : '片段',
                tactics: result.tactics,
                sportType: result.sport_type || sportType,
            });
            soundManager.playSuccess();
        } catch (error) {
            console.error(error);
            setStatus('idle');
            pushIotEvent('分析失败: 请检查后端服务与设备状态。', 'alert');
            const errorMessage = error?.message || '未知错误';
            alert(`分析失败。\n错误详情: ${errorMessage}\n\n请检查后端服务、网络连通性和视频格式是否可解析。`);
        }
    }, [addMatchRecord, debugMode, demoAugmentedEnabled, demoModeTick, mode, pushIotEvent, revokeVideoUrl, speakAdvice, sportType, wearableTelemetry.status]);

    const handleFileSelect = async (event) => {
        soundManager.playConfirm();
        const file = event.target.files?.[0];
        if (!file) {
            return;
        }

        await processAnalysis(file);
        event.target.value = '';
    };

    const handleCameraCapture = useCallback(() => {
        soundManager.playConfirm();

        if (typeof MediaRecorder === 'undefined') {
            alert('当前浏览器不支持摄像头录制。');
            return;
        }

        if (isRecording) {
            mediaRecorderRef.current?.stop();
            return;
        }

        const stream = webcamRef.current?.stream || webcamRef.current?.video?.srcObject;
        if (!stream) {
            alert('摄像头流尚未就绪，请稍后重试。');
            return;
        }

        const preferredTypes = [
            'video/webm;codecs=vp9',
            'video/webm;codecs=vp8',
            'video/webm',
        ];
        const mimeType = preferredTypes.find((type) => MediaRecorder.isTypeSupported(type)) || '';

        try {
            const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);

            recordedChunksRef.current = [];
            mediaRecorderRef.current = recorder;

            recorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    recordedChunksRef.current.push(event.data);
                }
            };

            recorder.onstop = async () => {
                clearTimer();
                setIsRecording(false);

                const recordedBlob = recordedChunksRef.current.length
                    ? new Blob(recordedChunksRef.current, { type: recorder.mimeType || 'video/webm' })
                    : null;

                recordedChunksRef.current = [];

                if (!recordedBlob) {
                    alert('未捕获到录像片段，请重新录制。');
                    return;
                }

                await processAnalysis(recordedBlob);
            };

            recorder.start();
            setIsRecording(true);
            setTimeLeft(0);
            clearTimer();
            timerRef.current = setInterval(() => {
                setTimeLeft((previous) => previous + 1);
            }, 1000);
        } catch (error) {
            console.error(error);
            alert('当前浏览器不支持摄像头录制。');
        }
    }, [clearTimer, isRecording, processAnalysis]);

    useEffect(() => {
        isMountedRef.current = true;

        return () => {
            isMountedRef.current = false;
            clearTimer();
            if (mediaRecorderRef.current) {
                mediaRecorderRef.current.onstop = null;
            }
            if (mediaRecorderRef.current?.state === 'recording') {
                mediaRecorderRef.current.stop();
            }
            window.speechSynthesis?.cancel?.();
            revokeVideoUrl(videoUrl);
        };
    }, [clearTimer, revokeVideoUrl, videoUrl]);

    const handleReset = () => {
        clearTimer();
        window.speechSynthesis?.cancel?.();
        setStatus('idle');
        setAnalysisResult(null);
        setIsRecording(false);
        setTimeLeft(0);
        setVideoUrl((previousUrl) => {
            revokeVideoUrl(previousUrl);
            return null;
        });
    };

    const toggleResult = () => {
        soundManager.playClick();
        if (!analysisResult) {
            return;
        }

        const currentResult = normalizeAutoResult(analysisResult.auto_result);
        const newResult = currentResult === 'WIN' ? 'LOSS' : 'WIN';
        setAnalysisResult({
            ...analysisResult,
            auto_result: newResult,
        });
    };

    const diagnostics = analysisResult?.diagnostics || {};
    const report = analysisResult?.report || {};
    const replayStory = analysisResult?.replay_story || {};
    const motionFeedbackItems = toFeedbackItems(diagnostics?.motion_feedback);
    const policyUpdate = diagnostics?.policy_update || {};
    const rewardComponents = policyUpdate?.reward_components || {};
    const rallyState = analysisResult?.physics?.rally_state || {};
    const courtContext = analysisResult?.physics?.court_context || rallyState?.court_context;
    const hasTrajectorySignals = Boolean(courtContext) || rallyState?.landing_confidence !== undefined || rallyState?.direction_consistency !== undefined;

    const sequenceContext = diagnostics?.sequence_context || {};
    const duelProjection = diagnostics?.duel_projection || report?.duel_snapshot || {};
    const trainingPlan = report?.training_plan || {};

    const sequenceTactics = toArray(sequenceContext?.recent_tactics);
    const sequenceTransitions = toArray(sequenceContext?.tactic_transitions);
    const sequenceSignals = [
        ...toArray(sequenceContext?.adaptation_signals),
        ...toArray(sequenceContext?.player_adjustment_signals),
    ];
    const sequenceTags = toArray(sequenceContext?.sequence_tags);

    const counterTactics = toArray(duelProjection?.counter_tactics);
    const exchangeScript = toArray(duelProjection?.exchange_script);

    const storyCards = toArray(replayStory?.storyline_cards);
    const turningPoints = toArray(replayStory?.turning_points);
    const adaptationCycles = toArray(replayStory?.adaptation_cycles);
    const criticalRallies = toArray(replayStory?.critical_rallies);
    const trainingBlocks = toArray(trainingPlan?.blocks);

    const hasSequencePanel = Boolean(sequenceContext?.has_content);
    const hasDuelPanel = Boolean(duelProjection?.has_content);
    const hasReplayPanel = Boolean(replayStory?.has_content);

    const wearableStatus = wearableTelemetry.status || 'disconnected';
    const wearableConnected = wearableStatus === 'connected' || wearableStatus === 'streaming';
    const wearableStreaming = wearableStatus === 'streaming';
    const heartRate = Number(wearableTelemetry.heartRate) || 0;
    const imuTimestamp = Number(wearableTelemetry.latestIMU?.timestamp) || Number(wearableTelemetry.timestamp) || 0;
    const estimatedLatency = imuTimestamp > 0 ? Math.max(0, Date.now() - imuTimestamp) : null;
    const gyroRawX = wearableTelemetry.latestIMU?.gyroX;
    const gyroRawY = wearableTelemetry.latestIMU?.gyroY;
    const gyroRawZ = wearableTelemetry.latestIMU?.gyroZ;
    const gyroX = formatGyroAxis(gyroRawX);
    const gyroY = formatGyroAxis(gyroRawY);
    const gyroZ = formatGyroAxis(gyroRawZ);
    const gyroLevelX = getGyroLevel(gyroRawX);
    const gyroLevelY = getGyroLevel(gyroRawY);
    const gyroLevelZ = getGyroLevel(gyroRawZ);
    const hasGyroData = [gyroRawX, gyroRawY, gyroRawZ]
        .some((value) => Number.isFinite(Number(value)));
    const dataQuality = !wearableConnected
        ? 'offline'
        : estimatedLatency === null
            ? 'warming'
            : estimatedLatency < 160
                ? 'high'
                : estimatedLatency < 380
                    ? 'medium'
                    : 'low';

    const batteryLabel = wearableConnected ? '心率服务' : '--';
    const connectionRate = iotKpi.connectionAttempts > 0
        ? Math.round((iotKpi.connectionSuccesses / iotKpi.connectionAttempts) * 100)
        : 0;

    const demoInertialLabel = demoAugmentedEnabled
        ? DEMO_INERTIAL_LABELS[Math.floor(demoModeTick / 2) % DEMO_INERTIAL_LABELS.length]
        : (wearableTelemetry.physicalState?.recent_intensities?.[0] || '待检测');

    const modeDescription = demoAugmentedEnabled
        ? '增强模式: 真机心率 + 演示数据流（可复现场景）'
        : '实时模式: 真机心率 + 视频分析（真实训练）';

    return (
        <div className="arena-container">
            <AnimatePresence mode="wait">
                {status === 'idle' && (
                    <motion.div
                        key="idle"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="arena-idle"
                    >
                        {isCameraMode && (
                            <div className="webcam-bg">
                                <Webcam
                                    audio={false}
                                    ref={webcamRef}
                                    screenshotFormat="image/jpeg"
                                    style={{ width: '100%', height: '100%', objectFit: 'cover', opacity: 0.6 }}
                                    videoConstraints={{ facingMode: { ideal: 'environment' } }}
                                />
                            </div>
                        )}

                        <header className={`arena-header ${isCameraMode ? 'overlay-mode' : ''}`}>
                            <h1 className="glitch-text">Neural<span className="text-warning">Ace</span></h1>
                            <p className="subtitle">物联网指挥舱 · 视觉+穿戴闭环训练系统</p>
                        </header>

                        <section className="iot-cockpit-grid">
                            <div className="iot-device-card" data-status={wearableStatus}>
                                <div className="iot-card-header">
                                    <span>
                                        <Watch size={14} />
                                        设备节点
                                        <span className="iot-status-indicator" />
                                    </span>
                                    <span className={`iot-status ${wearableConnected ? 'online' : 'offline'}`}>
                                        {WEARABLE_STATUS_LABELS[wearableStatus] || '离线'}
                                    </span>
                                </div>
                                <div className="iot-device-metrics">
                                    <div><Bluetooth size={14} /> 延迟 {estimatedLatency !== null ? `${estimatedLatency}ms` : '--'}</div>
                                    <div><Heart size={14} /> 心率 {heartRate > 0 ? `${heartRate} BPM` : '--'}</div>
                                    <div><Gauge size={14} /> 数据质量 {getQualityLabel(dataQuality)}</div>
                                    <div><Activity size={14} /> 电量 {batteryLabel}</div>
                                </div>
                                <div className="iot-gyro-panel">
                                    <div className="iot-gyro-header">
                                        <Activity size={13} />
                                        陀螺仪
                                    </div>
                                    <div className={`iot-gyro-grid ${hasGyroData ? 'online' : 'offline'}`}>
                                        <div>
                                            <small>Gx</small>
                                            <strong>{gyroX}</strong>
                                            <div className="iot-gyro-meter"><span style={{ width: `${gyroLevelX}%` }} /></div>
                                        </div>
                                        <div>
                                            <small>Gy</small>
                                            <strong>{gyroY}</strong>
                                            <div className="iot-gyro-meter"><span style={{ width: `${gyroLevelY}%` }} /></div>
                                        </div>
                                        <div>
                                            <small>Gz</small>
                                            <strong>{gyroZ}</strong>
                                            <div className="iot-gyro-meter"><span style={{ width: `${gyroLevelZ}%` }} /></div>
                                        </div>
                                    </div>
                                    <p className="iot-gyro-hint">
                                        {hasGyroData ? '单位：rad/s（实时更新）' : '暂无陀螺仪数据，开始监测后显示'}
                                    </p>
                                </div>
                            </div>

                            <div className="iot-kpi-panel">
                                <div className="iot-card-header">
                                    <span><Radar size={14} /> 物联指标</span>
                                </div>
                                <div className="iot-kpi-grid">
                                    <div><small>连接成功率</small><strong>{connectionRate}%</strong></div>
                                    <div><small>上报频率</small><strong>{iotKpi.reportFrequency} Hz</strong></div>
                                    <div><small>端到端延迟</small><strong>{estimatedLatency !== null ? `${estimatedLatency} ms` : '--'}</strong></div>
                                    <div><small>告警次数</small><strong>{iotKpi.alertTriggers}</strong></div>
                                    <div><small>边端云同步</small><strong>{wearableTelemetry.wsConnected ? '已同步' : '等待中'}</strong></div>
                                </div>
                            </div>

                            <div className="iot-event-panel">
                                <div className="iot-card-header">
                                    <span><ScrollText size={14} /> 最近 30 秒事件流</span>
                                </div>
                                <div className="iot-event-list">
                                    {iotEvents.length === 0 && <p className="iot-empty">暂无事件，等待设备数据...</p>}
                                    {iotEvents.map((event) => (
                                        <div key={event.id} className={`iot-event-item ${event.kind}`}>
                                            <small>{new Date(event.ts).toLocaleTimeString()}</small>
                                            <span>{event.message}</span>
                                        </div>
                                    ))}
                                </div>
                            </div>

                            <div className="iot-control-card">
                                <div className="iot-card-header">
                                    <span><Zap size={14} /> 数据链路与模式</span>
                                </div>
                                <div className="pipeline-track compact static">
                                    <div className="pipeline-node" title="蓝牙链路"><Bluetooth size={14} /><span>蓝牙链路</span></div>
                                    <span className="pipeline-arrow">-&gt;</span>
                                    <div className="pipeline-node" title="手机边缘端"><Smartphone size={14} /><span>手机边缘端</span></div>
                                    <span className="pipeline-arrow">-&gt;</span>
                                    <div className="pipeline-node" title="云端引擎"><Cloud size={14} /><span>云端引擎</span></div>
                                    <span className="pipeline-arrow">-&gt;</span>
                                    <div className="pipeline-node" title="语音教练"><Mic size={14} /><span>语音教练</span></div>
                                </div>
                                <div className="iot-mode-row compact">
                                    <button
                                        className={`demo-toggle ${demoAugmentedEnabled ? 'active' : ''}`}
                                        onClick={() => {
                                            soundManager.playClick();
                                            const nextValue = !demoAugmentedEnabled;
                                            setDemoAugmentedEnabled(nextValue);
                                            pushIotEvent(
                                                nextValue
                                                    ? '增强模式已开启'
                                                    : '增强模式已关闭，切回实时模式',
                                                'mode',
                                            );
                                        }}
                                    >
                                        {demoAugmentedEnabled ? <Wifi size={14} /> : <Siren size={14} />}
                                        {demoAugmentedEnabled ? '关闭增强模式' : '开启增强模式'}
                                    </button>
                                </div>
                            </div>
                        </section>

                        <div className="sport-type-switch">
                            <button onClick={() => { soundManager.playClick(); setSportType('badminton'); }} className={sportType === 'badminton' ? 'active' : ''}>羽毛球</button>
                            <button onClick={() => { soundManager.playClick(); setSportType('table_tennis'); }} className={sportType === 'table_tennis' ? 'active' : ''}>乒乓球</button>
                        </div>
                        <div className="mode-switch">
                            <button onClick={() => { soundManager.playClick(); setMode('singles'); }} className={mode === 'singles' ? 'active' : ''}>单打</button>
                            <button onClick={() => { soundManager.playClick(); setMode('doubles'); }} className={mode === 'doubles' ? 'active' : ''}>双打</button>
                        </div>

                        <div className="input-toggle">
                            <button
                                className={!isCameraMode ? 'active' : ''}
                                onClick={() => { soundManager.playClick(); setIsCameraMode(false); }}
                            >
                                <Upload size={14} /> 上传视频
                            </button>
                            <button
                                className={isCameraMode ? 'active' : ''}
                                onClick={() => { soundManager.playClick(); setIsCameraMode(true); }}
                            >
                                <Camera size={14} /> 实时摄像
                            </button>
                        </div>

                        <motion.div
                            className={`upload-trigger ${isRecording ? 'recording' : ''}`}
                            onClick={isCameraMode ? handleCameraCapture : () => { soundManager.playClick(); fileInputRef.current?.click(); }}
                            whileHover={{ scale: 1.05 }}
                            whileTap={{ scale: 0.95 }}
                        >
                            <div className="trigger-ring"></div>
                            <div className="trigger-icon">
                                {isCameraMode ? <Video size={48} /> : <Upload size={48} />}
                            </div>
                            <span className="trigger-text">
                                {isRecording
                                    ? `停止录制 ${timeLeft < 10 ? '0' : ''}${timeLeft}s`
                                    : isCameraMode
                                        ? '开始录制'
                                        : '上传片段'}
                            </span>
                            <span className={`analysis-mode-chip ${wearableStreaming ? 'enhanced' : 'degraded'}`}>
                                {wearableStreaming
                                    ? '多源模式已启用（穿戴增强）'
                                    : '降级模式（仅视频）'}
                            </span>
                        </motion.div>

                        <input
                            type="file"
                            ref={fileInputRef}
                            onChange={handleFileSelect}
                            accept="video/*"
                            style={{ display: 'none' }}
                        />

                        <div className="capability-badges">
                            <div className="badge"><Activity size={16} /><span>动作分析</span></div>
                            <div className="badge"><Zap size={16} /><span>速度追踪</span></div>
                            <div className="badge"><Shield size={16} /><span>战术指导</span></div>
                        </div>
                    </motion.div>
                )}

                {status === 'analyzing' && (
                    <motion.div
                        key="analyzing"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="arena-analyzing"
                    >
                        <motion.div
                            className="scanner"
                            animate={{ y: [-100, 100, -100], opacity: [0.5, 1, 0.5] }}
                            transition={{ repeat: Infinity, duration: 2 }}
                        ></motion.div>
                        <p>{sportType === 'table_tennis' ? '正在解析球路与落台轨迹...' : '正在解析球路与人体动作轨迹...'}</p>
                    </motion.div>
                )}

                {status === 'complete' && videoUrl && (
                    <motion.div
                        key="complete"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="arena-hud"
                    >
                        <video
                            src={videoUrl}
                            className="hud-video"
                            autoPlay
                            loop
                            muted
                            playsInline
                            controls
                        />

                        <div className="hud-overlay">
                            {analysisResult?.physics && (
                                <div className="hud-top-bar">
                                    <div className="hud-stat">
                                        <span className="hud-label">最高速度</span>
                                        <span className="hud-value text-primary">
                                            {Math.round(analysisResult.physics.max_speed_kmh || 0)} <span style={{ fontSize: '0.8rem' }}>KM/H</span>
                                        </span>
                                    </div>
                                    
                                    {analysisResult.sport_type === 'table_tennis' && analysisResult.physics.mean_speed_kmh !== undefined && (
                                        <div className="hud-stat">
                                            <span className="hud-label">平均速度</span>
                                            <span className="hud-value">
                                                {Math.round(analysisResult.physics.mean_speed_kmh)} <span style={{ fontSize: '0.8rem' }}>KM/H</span>
                                            </span>
                                        </div>
                                    )}
                                    
                                    {analysisResult.sport_type === 'table_tennis' && analysisResult.physics.bounce_count !== undefined && (
                                        <div className="hud-stat">
                                            <span className="hud-label">触台次数</span>
                                            <span className="hud-value">{analysisResult.physics.bounce_count}</span>
                                        </div>
                                    )}
                                    
                                    {analysisResult.sport_type === 'table_tennis' && analysisResult.physics.shot_shape && (
                                        <div className="hud-stat">
                                            <span className="hud-label">击球类型</span>
                                            <span className="hud-value">{formatSignalLabel(analysisResult.physics.shot_shape)}</span>
                                        </div>
                                    )}

                                    <div className="hud-stat" onClick={toggleResult}>
                                        <span className="hud-label">判定结果</span>
                                        <div className={`result-badge ${normalizeAutoResult(analysisResult.auto_result)}`}>
                                            {getResultLabel(analysisResult.auto_result)}
                                        </div>
                                    </div>
                                </div>
                            )}

                            {analysisResult && (
                                <div className="hud-tags-bar">
                                    <div className="hud-tag-chip highlight">
                                        <Activity size={12} />
                                        <span>{getModeLabel(analysisResult.match_type)}</span>
                                    </div>
                                    {analysisResult.physics?.event && (
                                        <div className="hud-tag-chip">
                                            <Video size={12} />
                                            <span>{analysisResult.physics.event}</span>
                                        </div>
                                    )}
                                    {courtContext && (
                                        <div className="hud-tag-chip">
                                            <Radar size={12} />
                                            <span>{formatSignalLabel(courtContext)}</span>
                                        </div>
                                    )}
                                    {analysisResult.physics?.max_speed_kmh > 200 && (
                                        <div className="hud-tag-chip highlight">
                                            <Zap size={12} />
                                            <span>重杀进攻</span>
                                        </div>
                                    )}
                                    {sequenceTags.slice(0, 2).map((tag) => (
                                        <div key={tag} className="hud-tag-chip accent">
                                            <GitBranch size={12} />
                                            <span>{formatSignalLabel(tag)}</span>
                                        </div>
                                    ))}
                                </div>
                            )}

                            {analysisResult?.summary && (
                                <motion.section
                                    className="hud-summary-panel"
                                    initial={{ opacity: 0, y: 18 }}
                                    animate={{ opacity: 1, y: 0 }}
                                >
                                    <div className="hud-summary-header">
                                        <div>
                                            <p className="hud-summary-kicker">回合总结</p>
                                            <h2>{analysisResult.summary.headline}</h2>
                                        </div>
                                        <span className={`intel-confidence ${analysisResult.summary.confidence_label || 'medium'}`}>
                                            {getConfidenceLabel(analysisResult.summary.confidence_label)}
                                        </span>
                                    </div>
                                    <p className="hud-summary-copy">{analysisResult.summary.key_takeaway}</p>
                                </motion.section>
                            )}

                            {analysisResult?.diagnostics && (
                                <motion.section
                                    className="hud-diagnostics-panel"
                                    initial={{ opacity: 0, y: 18 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    transition={{ delay: 0.05 }}
                                >
                                    <div className="hud-diagnostics-header">
                                        <p className="hud-summary-kicker">诊断信息</p>
                                        <span>{getQualityLabel(analysisResult.diagnostics.analysis_quality || 'medium')} 信号</span>
                                    </div>

                                    <div className="hud-metric-grid">
                                        {metricCards(analysisResult).map((metric) => {
                                            const Icon = metric.icon;
                                            return (
                                                <div key={metric.label} className={`hud-metric-card ${metric.tone}`}>
                                                    <div className="hud-metric-icon"><Icon size={16} /></div>
                                                    <span className="hud-metric-label">{metric.label}</span>
                                                    <strong>{metric.value}</strong>
                                                </div>
                                            );
                                        })}
                                    </div>

                                    <div className="hud-notes-grid">
                                        <div className="hud-note-card">
                                            <strong><Siren size={14} /> 裁决依据</strong>
                                            <p>{analysisResult.physics?.referee_reason || '暂无裁决依据说明。'}</p>
                                        </div>

                                        <div className="hud-note-card">
                                            <strong><BrainCircuit size={14} /> 动作反馈</strong>
                                            {motionFeedbackItems.length > 0 ? (
                                                <ul className="hud-note-list">
                                                    {motionFeedbackItems.map((item, index) => (
                                                        <li key={`${item}-${index}`}>{item}</li>
                                                    ))}
                                                </ul>
                                            ) : (
                                                <p>暂无动作反馈。</p>
                                            )}
                                        </div>

                                        {hasTrajectorySignals && (
                                            <div className="hud-note-card">
                                                <strong><Radar size={14} /> 轨迹信号</strong>
                                                <div className="hud-note-meta">
                                                    {courtContext && <span>{formatSignalLabel(courtContext)}</span>}
                                                    {rallyState?.landing_confidence !== undefined && (
                                                        <span>落点 {toPercentLabel(rallyState.landing_confidence)}</span>
                                                    )}
                                                    {rallyState?.direction_consistency !== undefined && (
                                                        <span>方向 {toPercentLabel(rallyState.direction_consistency)}</span>
                                                    )}
                                                </div>
                                                <p>
                                                    {analysisResult.physics?.description || '该回合已生成轨迹层分析。'}
                                                </p>
                                            </div>
                                        )}

                                        {policyUpdate?.policy_update_reason && (
                                            <div className="hud-note-card emphasis">
                                                <strong><Sparkles size={14} /> 策略更新</strong>
                                                <p>{policyUpdate.policy_update_reason}</p>
                                                <div className="hud-note-inline">
                                                    {rewardComponents?.raw_reward !== undefined && <span>奖励 {rewardComponents.raw_reward}</span>}
                                                    {rewardComponents?.trajectory_quality !== undefined && (
                                                        <span>轨迹 {toPercentLabel(rewardComponents.trajectory_quality)}</span>
                                                    )}
                                                    {rewardComponents?.referee_confidence !== undefined && (
                                                        <span>裁决 {toPercentLabel(rewardComponents.referee_confidence)}</span>
                                                    )}
                                                    {rewardComponents?.retrieval_confidence !== undefined && (
                                                        <span>检索 {toPercentLabel(rewardComponents.retrieval_confidence)}</span>
                                                    )}
                                                </div>
                                            </div>
                                        )}

                                        {analysisResult.diagnostics?.warnings?.length > 0 && (
                                            <div className="hud-note-card warning">
                                                <strong><CircleAlert size={14} /> 风险提示</strong>
                                                <ul>
                                                    {analysisResult.diagnostics.warnings.map((warning, index) => (
                                                        <li key={`${warning}-${index}`}>{warning}</li>
                                                    ))}
                                                </ul>
                                            </div>
                                        )}
                                    </div>
                                </motion.section>
                            )}

                            {(hasSequencePanel || hasDuelPanel) && (
                                <section className="hud-intelligence-grid">
                                    {hasSequencePanel && (
                                        <motion.article
                                            className="hud-intel-panel sequence-panel"
                                            initial={{ opacity: 0, y: 18 }}
                                            animate={{ opacity: 1, y: 0 }}
                                            transition={{ delay: 0.08 }}
                                        >
                                            <div className="hud-intel-header-row">
                                                <div>
                                                    <p className="hud-summary-kicker">序列记忆</p>
                                                    <h3>多回合战术漂移</h3>
                                                </div>
                                                <span className="intel-badge neutral">
                                                    <Route size={12} />
                                                    {toPercentLabel(sequenceContext?.adaptation_score)}
                                                </span>
                                            </div>

                                            <p className="hud-intel-copy">
                                                {sequenceContext?.memory_summary || '该片段尚未生成多回合记忆。'}
                                            </p>

                                            {sequenceTags.length > 0 && (
                                                <div className="hud-chip-row">
                                                    {sequenceTags.map((tag) => (
                                                        <span key={tag} className="hud-chip">
                                                            {formatSignalLabel(tag)}
                                                        </span>
                                                    ))}
                                                </div>
                                            )}

                                            <div className="hud-sequence-stats">
                                                <div className="hud-mini-stat">
                                                    <span>连胜/连失</span>
                                                    <strong>{formatSignalLabel(sequenceContext?.streak_context?.state)}</strong>
                                                </div>
                                                <div className="hud-mini-stat">
                                                    <span>压力波动</span>
                                                    <strong>{formatSignalLabel(sequenceContext?.pressure_swing?.label)}</strong>
                                                    <small>{toSignedPercentLabel(sequenceContext?.pressure_swing?.delta)}</small>
                                                </div>
                                                <div className="hud-mini-stat">
                                                    <span>偏好流派</span>
                                                    <strong>{formatSignalLabel(sequenceContext?.preferred_style_family)}</strong>
                                                </div>
                                            </div>

                                            {sequenceTactics.length > 0 && (
                                                <div className="memory-lane">
                                                    {sequenceTactics.map((snapshot, index) => (
                                                        <div key={`${snapshot.name}-${index}`} className="memory-rally-card">
                                                            <span className="memory-rally-index">R{snapshot.rally_index}</span>
                                                            <strong>{snapshot.name}</strong>
                                                            <small>{formatSignalLabel(snapshot.style_family)}</small>
                                                            <span>{toPercentLabel(snapshot.score)}</span>
                                                        </div>
                                                    ))}
                                                </div>
                                            )}

                                            {sequenceTransitions.length > 0 && (
                                                <div className="transition-rail">
                                                    {sequenceTransitions.map((transition, index) => (
                                                        <div key={`${transition.from}-${transition.to}-${index}`} className="transition-item">
                                                            <div className="transition-route">
                                                                <span>{transition.from}</span>
                                                                <GitBranch size={14} />
                                                                <span>{transition.to}</span>
                                                            </div>
                                                            <small>{formatSignalLabel(transition.style_shift)}</small>
                                                        </div>
                                                    ))}
                                                </div>
                                            )}

                                            {sequenceSignals.length > 0 && (
                                                <ul className="intel-signal-list">
                                                    {sequenceSignals.map((signal, index) => (
                                                        <li key={`${signal}-${index}`}>{signal}</li>
                                                    ))}
                                                </ul>
                                            )}
                                        </motion.article>
                                    )}

                                    {hasDuelPanel && (
                                        <motion.article
                                            className="hud-intel-panel duel-panel"
                                            initial={{ opacity: 0, y: 18 }}
                                            animate={{ opacity: 1, y: 0 }}
                                            transition={{ delay: 0.1 }}
                                        >
                                            <div className="hud-intel-header-row">
                                                <div>
                                                    <p className="hud-summary-kicker">战术对抗</p>
                                                    <h3>{duelProjection?.primary_plan || '中性重置'}</h3>
                                                </div>
                                                <span className={`intel-badge ${duelProjection?.duel_risk_label || 'low'}`}>
                                                    <Swords size={12} />
                                                    {getRiskLabel(duelProjection?.duel_risk_label)}
                                                </span>
                                            </div>

                                            <p className="hud-intel-copy">
                                                {duelProjection?.duel_explanation || duelProjection?.likely_response || '该片段暂无对抗推演结果。'}
                                            </p>

                                            <div className="hud-chip-row">
                                                <span className="hud-chip emphasis">{formatSignalLabel(duelProjection?.counter_window)}</span>
                                                <span className="hud-chip">{toPercentLabel(duelProjection?.duel_risk)}</span>
                                            </div>

                                            {exchangeScript.length > 0 && (
                                                <ol className="exchange-script">
                                                    {exchangeScript.map((step, index) => (
                                                        <li key={`${step}-${index}`}>{step}</li>
                                                    ))}
                                                </ol>
                                            )}

                                            {counterTactics.length > 0 && (
                                                <div className="duel-counter-grid">
                                                    {counterTactics.map((counter, index) => (
                                                        <div key={`${counter.name}-${index}`} className="duel-counter-card">
                                                            <div className="duel-counter-topline">
                                                                <strong>{counter.name}</strong>
                                                                <span>{toPercentLabel(counter.fit_score)}</span>
                                                            </div>
                                                            <small>{formatSignalLabel(counter.family)}</small>
                                                            <p>{counter.reason}</p>
                                                        </div>
                                                    ))}
                                                </div>
                                            )}

                                            {duelProjection?.pressure_gate && (
                                                <div className="duel-pressure-gate">
                                                    <TriangleAlert size={14} />
                                                    <span>{duelProjection.pressure_gate}</span>
                                                </div>
                                            )}
                                        </motion.article>
                                    )}
                                </section>
                            )}

                            {analysisResult?.tactics?.length > 0 && (
                                <div className="hud-tactics-panel">
                                    {analysisResult.tactics.map((tactic, index) => (
                                        <motion.article
                                            key={`${tactic.name}-${index}`}
                                            className={`tactic-intel-card ${tactic.confidence_label || 'medium'}`}
                                            initial={{ opacity: 0, y: 16 }}
                                            animate={{ opacity: 1, y: 0 }}
                                            transition={{ delay: 0.08 * index }}
                                        >
                                            <div className="tactic-intel-header">
                                                <div>
                                                    <p className="tactic-intel-kicker">战术方案 {index + 1}</p>
                                                    <h3>{tactic.name}</h3>
                                                </div>
                                                <span className={`intel-confidence ${tactic.confidence_label || 'medium'}`}>
                                                    {getConfidenceLabel(tactic.confidence_label)}
                                                </span>
                                            </div>

                                            <div className="tactic-intel-action">
                                                <Sparkles size={14} />
                                                <span>{tactic.recommended_action || tactic.content}</span>
                                            </div>

                                            <div className="tactic-intel-metrics">
                                                <span>重排分 {toPercentLabel(tactic.rerank_score)}</span>
                                                <span>连续性 {toPercentLabel(tactic.continuity_score)}</span>
                                                <span>覆盖度 {toPercentLabel(tactic.coverage_score)}</span>
                                            </div>

                                            {tactic.why_this_tactic && (
                                                <div className="tactic-intel-copy">
                                                    <strong>战术理由</strong>
                                                    <p>{tactic.why_this_tactic}</p>
                                                </div>
                                            )}

                                            {tactic.rank_reason && (
                                                <div className="tactic-intel-copy subdued">
                                                    <strong><Target size={14} /> 选择逻辑</strong>
                                                    <p>{tactic.rank_reason}</p>
                                                </div>
                                            )}

                                            {tactic.frontier_hint && (
                                                <div className="tactic-intel-copy subdued">
                                                    <strong><GitBranch size={14} /> 前沿提示</strong>
                                                    <p>{tactic.frontier_hint}</p>
                                                </div>
                                            )}

                                            {tactic.evolution_replay?.development_stage && (
                                                <div className="tactic-evolution-panel">
                                                    <div className="tactic-evolution-header">
                                                        <strong><Route size={14} /> 进化回放</strong>
                                                        <span>{formatSignalLabel(tactic.evolution_replay.development_stage)}</span>
                                                    </div>
                                                    <p>{tactic.evolution_replay.why_now}</p>
                                                    {toArray(tactic.evolution_replay.upgrade_path).length > 0 && (
                                                        <ul className="tactic-evolution-steps">
                                                            {toArray(tactic.evolution_replay.upgrade_path).map((step, stepIndex) => (
                                                                <li key={`${step}-${stepIndex}`}>{step}</li>
                                                            ))}
                                                        </ul>
                                                    )}
                                                </div>
                                            )}

                                            {tactic.risk_note && (
                                                <div className="tactic-intel-copy caution">
                                                    <strong><TriangleAlert size={14} /> 风险说明</strong>
                                                    <p>{tactic.risk_note}</p>
                                                </div>
                                            )}
                                        </motion.article>
                                    ))}
                                </div>
                            )}

                            {hasReplayPanel && (
                                <motion.section
                                    className="hud-replay-panel"
                                    initial={{ opacity: 0, y: 18 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    transition={{ delay: 0.16 }}
                                >
                                    <div className="hud-replay-header">
                                        <div>
                                            <p className="hud-summary-kicker">回放故事线</p>
                                            <h3>{replayStory?.opening_phase?.headline || '回放分镜'}</h3>
                                        </div>
                                        <span className="intel-badge neutral">
                                            <ScrollText size={12} />
                                            时间线
                                        </span>
                                    </div>

                                    <p className="hud-intel-copy">
                                        {replayStory?.replay_summary || '该片段暂无回放故事线。'}
                                    </p>

                                    {storyCards.length > 0 && (
                                        <div className="storyline-grid">
                                            {storyCards.map((card, index) => (
                                                <div key={`${card.title}-${index}`} className={`storyline-card ${card.stage || 'neutral'}`}>
                                                    <span className="storyline-stage">{formatSignalLabel(card.stage || 'stage')}</span>
                                                    <strong>{card.title}</strong>
                                                    <p>{card.body}</p>
                                                </div>
                                            ))}
                                        </div>
                                    )}

                                    <div className="replay-columns">
                                        {turningPoints.length > 0 && (
                                            <div className="replay-column">
                                                <div className="replay-column-header">
                                                    <Flag size={14} />
                                                    <strong>转折点</strong>
                                                </div>
                                                <div className="replay-list">
                                                    {turningPoints.map((turn, index) => (
                                                        <div key={`${turn.rally_index}-${index}`} className="replay-list-item">
                                                            <span>R{turn.rally_index}</span>
                                                            <div>
                                                                <strong>{turn.summary || '回合转折'}</strong>
                                                                <p>{turn.trigger}</p>
                                                            </div>
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>
                                        )}

                                        {adaptationCycles.length > 0 && (
                                            <div className="replay-column">
                                                <div className="replay-column-header">
                                                    <GitBranch size={14} />
                                                    <strong>适应循环</strong>
                                                </div>
                                                <div className="replay-list">
                                                    {adaptationCycles.map((cycle, index) => (
                                                        <div key={`${cycle.from}-${cycle.to}-${index}`} className="replay-list-item">
                                                            <span>{index + 1}</span>
                                                            <div>
                                                                <strong>{cycle.from} {'→'} {cycle.to}</strong>
                                                                <p>{cycle.summary}</p>
                                                            </div>
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>
                                        )}

                                        {criticalRallies.length > 0 && (
                                            <div className="replay-column">
                                                <div className="replay-column-header">
                                                    <Target size={14} />
                                                    <strong>关键回合</strong>
                                                </div>
                                                <div className="replay-critical-grid">
                                                    {criticalRallies.map((critical) => (
                                                        <div key={critical.rally_index} className="critical-rally-card">
                                                            <span>R{critical.rally_index}</span>
                                                            <strong>{critical.headline}</strong>
                                                            <p>{critical.takeaway}</p>
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>
                                        )}
                                    </div>

                                    {replayStory?.closing_state?.summary && (
                                        <div className="closing-state-card">
                                            <div className="replay-column-header">
                                                <Flag size={14} />
                                                <strong>收官状态</strong>
                                            </div>
                                            <p>{replayStory.closing_state.summary}</p>
                                        </div>
                                    )}
                                </motion.section>
                            )}

                            {analysisResult?.advice && (
                                <div className="hud-coach-section">
                                    {trainingBlocks.length > 0 && (
                                        <div className="hud-training-strip">
                                            {trainingBlocks.map((block, index) => (
                                                <div key={`${block.label}-${index}`} className="hud-training-block">
                                                    <span>{block.label}</span>
                                                    <strong>{block.duration_min} 分钟</strong>
                                                    <small>{block.goal}</small>
                                                </div>
                                            ))}
                                        </div>
                                    )}

                                    <motion.div
                                        className="hud-coach-bubble"
                                        initial={{ y: 50, opacity: 0 }}
                                        animate={{ y: 0, opacity: 1 }}
                                    >
                                        <div className="avatar-circle">AI</div>
                                        <div className="coach-text">
                                            <p>{analysisResult.advice.text}</p>
                                            <small>{report?.coach_takeaway || analysisResult.physics?.description}</small>
                                        </div>
                                    </motion.div>

                                    <div className="hud-actions">
                                        <button className="close-btn" onClick={handleReset}>返回采集页</button>
                                    </div>
                                </div>
                            )}

                            {!analysisResult && (
                                <div className="hud-actions solo">
                                    <button className="close-btn" onClick={handleReset}>返回采集页</button>
                                </div>
                            )}
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
};

export default Arena;
