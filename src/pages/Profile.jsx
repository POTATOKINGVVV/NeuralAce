import React, { useState } from 'react';
import {
    User, Divide as Device, Settings, LogOut, ToggleLeft, ToggleRight, Database, Sun, Moon,
} from 'lucide-react';
import { useGame } from '../context/GameContext';
import '../styles/Profile.css';

const Profile = () => {
    const { loadMockData, clearData, debugMode, setDebugMode, theme, setTheme } = useGame();
    const [height, setHeight] = useState(175);

    return (
        <div className="profile-container">
            <div className="profile-header">
                <div className="profile-avatar">
                    <User size={40} />
                </div>
                <div className="profile-name">
                    <h3>一号选手</h3>
                    <span>竞技业余球员</span>
                </div>
            </div>

            <div className="settings-section">
                <label className="section-label">选手参数</label>

                <div className="setting-item">
                    <div className="setting-icon"><User size={18} /></div>
                    <div className="setting-info">
                        <span className="setting-title">身高（cm）</span>
                        <span className="setting-desc">用于校准动作与物理估计。</span>
                    </div>
                    <input
                        type="number"
                        className="setting-input"
                        value={height}
                        onChange={(e) => setHeight(e.target.value)}
                        min="100"
                        max="240"
                    />
                </div>
            </div>

            <div className="settings-section">
                <label className="section-label">系统设置</label>

                <div className="setting-item" onClick={() => setDebugMode(!debugMode)}>
                    <div className="setting-icon"><Device size={18} /></div>
                    <div className="setting-info">
                        <span className="setting-title">HUD 调试模式</span>
                        <span className="setting-desc">无需实时后端即可快速演示分析。</span>
                    </div>
                    <div className={`toggle-switch ${debugMode ? 'on' : ''}`}>
                        {debugMode ? <ToggleRight size={24} color="var(--color-primary)" /> : <ToggleLeft size={24} color="#666" />}
                    </div>
                </div>

                {debugMode && (
                    <div className="debug-panel">
                        <button className="debug-btn" onClick={() => { loadMockData(); alert('已加载 5 条示例回合片段。'); }}>
                            <Database size={14} style={{ marginRight: 4 }} /> 加载示例数据
                        </button>
                        <button className="debug-btn destructive" onClick={() => { clearData(); alert('本地示例数据已清空。'); }}>
                            清空数据
                        </button>
                    </div>
                )}

                <div className="setting-item">
                    <div className="setting-icon"><Sun size={18} /></div>
                    <div className="setting-info">
                        <span className="setting-title">主题外观</span>
                        <span className="setting-desc">在浅色与深色模式之间切换。</span>
                    </div>
                    <div className="theme-selector">
                        <button
                            className={`theme-btn ${theme === 'light' ? 'active' : ''}`}
                            onClick={() => setTheme('light')}
                        >
                            <Sun size={16} />
                            <span>浅色</span>
                        </button>
                        <button
                            className={`theme-btn ${theme === 'dark' ? 'active' : ''}`}
                            onClick={() => setTheme('dark')}
                        >
                            <Moon size={16} />
                            <span>深色</span>
                        </button>
                    </div>
                </div>
            </div>

            <button className="logout-btn">
                <LogOut size={16} /> 退出登录
            </button>

            <div className="app-version">
                NeuralAce v1.0.0(Build 2026.4)
            </div>
        </div>
    );
};

export default Profile;
