import React from 'react';
import {
    Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer,
} from 'recharts';
import { useGame } from '../context/GameContext';
import '../styles/Evolution.css';

const Evolution = () => {
    const { tactics, skills } = useGame();

    return (
        <div className="evolution-container">
            <header className="page-header">
                <h2>进化 <span className="text-secondary">基因图谱</span></h2>
            </header>

            <div className="chart-section">
                <div className="hex-bg"></div>
                <ResponsiveContainer width="100%" height={300}>
                    <RadarChart cx="50%" cy="50%" outerRadius="80%" data={skills}>
                        <PolarGrid stroke="#333" />
                        <PolarAngleAxis dataKey="subject" tick={{ fill: '#aaa', fontSize: 12 }} />
                        <PolarRadiusAxis angle={30} domain={[0, 150]} tick={false} axisLine={false} />
                        <Radar
                            name="能力画像"
                            dataKey="A"
                            stroke="#0aff00"
                            strokeWidth={3}
                            fill="#0aff00"
                            fillOpacity={0.3}
                        />
                    </RadarChart>
                </ResponsiveContainer>
            </div>

            <div className="tactics-section">
                <h3>战术基因库</h3>
                <div className="tactics-list">
                    {tactics.map((tactic) => {
                        const total = tactic.alpha + tactic.beta;
                        const winRate = total > 0 ? (tactic.alpha / total) * 100 : 0;
                        const statusLabel = tactic.status === 'proven' ? '已验证' : '探索中';

                        return (
                            <div key={tactic.id} className="tactic-card">
                                <div className="tactic-header">
                                    <span className="tactic-name">{tactic.name}</span>
                                    <span className={`status-badge ${tactic.status}`}>{statusLabel}</span>
                                </div>

                                <div className="progress-container">
                                    <div
                                        className="progress-bar win"
                                        style={{ width: `${winRate}%` }}
                                    ></div>
                                </div>

                                <div className="tactic-meta">
                                    <small className="text-muted">样本数：{total}</small>
                                    <small className="text-secondary">胜率：{Math.round(winRate)}%</small>
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>
        </div>
    );
};

export default Evolution;
