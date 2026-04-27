import React, { createContext, useContext, useState, useEffect } from 'react';

const GameContext = createContext();

export const useGame = () => useContext(GameContext);

export const GameProvider = ({ children }) => {
    const initialTactics = [
        { id: 'T001', name: '反击封挡', alpha: 15, beta: 3, status: 'proven' },
        { id: 'T002', name: '后场高远重置', alpha: 8, beta: 12, status: 'exploring' },
        { id: 'T003', name: '斜线吊球终结', alpha: 5, beta: 2, status: 'exploring' },
        { id: 'T004', name: '平抽快压', alpha: 20, beta: 5, status: 'proven' },
    ];

    const initialSkills = [
        { subject: '进攻', A: 120, fullMark: 150 },
        { subject: '防守', A: 98, fullMark: 150 },
        { subject: '网前', A: 86, fullMark: 150 },
        { subject: '步法', A: 99, fullMark: 150 },
        { subject: '稳定性', A: 85, fullMark: 150 },
    ];

    const [tactics, setTactics] = useState(initialTactics);
    const [skills, setSkills] = useState(initialSkills);
    const [history, setHistory] = useState([]);
    const [debugMode, setDebugMode] = useState(false);
    const [theme, setTheme] = useState('light');

    const addMatchRecord = (record) => {
        const newRecord = {
            ...record,
            id: Date.now(),
            date: new Date().toISOString().split('T')[0],
        };
        setHistory((prev) => [newRecord, ...prev]);
    };

    const updateMatchResult = (id, newResult) => {
        setHistory((prev) =>
            prev.map((item) => {
                if (item.id === id) {
                    return { ...item, auto_result: newResult };
                }
                return item;
            }),
        );
    };

    const loadMockData = () => {
        const mockHistory = [
            { id: 1, date: '2023-11-20', type: '杀球', result: 'WIN', duration: '0:15', auto_reward: 120, tactics: [{ name: '反击封挡' }], thumbnail: '/samples/smash.png', video: '/samples/demo.mp4' },
            { id: 2, date: '2023-11-21', type: '防守', result: 'LOSS', duration: '0:22', auto_reward: 50, tactics: [{ name: '后场高远重置' }], thumbnail: '/samples/defense.png', video: '/samples/demo.mp4' },
            { id: 3, date: '2023-11-22', type: '平抽', result: 'WIN', duration: '0:08', auto_reward: 90, tactics: [{ name: '平抽快压' }], thumbnail: '/samples/smash.png', video: '/samples/demo.mp4' },
            { id: 4, date: '2023-11-23', type: '网前', result: 'WIN', duration: '0:05', auto_reward: 150, tactics: [{ name: '斜线吊球终结' }], thumbnail: '/samples/defense.png', video: '/samples/demo.mp4' },
            { id: 5, date: '2023-11-24', type: '杀球', result: 'WIN', duration: '0:12', auto_reward: 130, tactics: [{ name: '反击封挡' }], thumbnail: '/samples/smash.png', video: '/samples/demo.mp4' },
        ];

        setHistory(mockHistory);
    };

    const clearData = () => {
        setHistory([]);
        setTactics(initialTactics);
        setSkills(initialSkills);
    };

    // Apply theme to document
    useEffect(() => {
        document.documentElement.setAttribute('data-theme', theme);
    }, [theme]);

    const value = {
        tactics,
        skills,
        history,
        debugMode,
        setDebugMode,
        theme,
        setTheme,
        addMatchRecord,
        updateMatchResult,
        loadMockData,
        clearData,
    };

    return <GameContext.Provider value={value}>{children}</GameContext.Provider>;
};
