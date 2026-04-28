export const mockAnalyzeRally = (file, matchType) => {
    return new Promise((resolve) => {
        setTimeout(() => {
            resolve({
                physics: {
                    event: '重力杀球',
                    max_speed_kmh: 214.5,
                    description: `模式: ${matchType === 'doubles' ? '双打' : '单打'}。对手施加强烈压力。 [动作: 站姿过于竗直]`,
                },
                advice: {
                    text: '触球时降低重心。轻柔的反手挡网是最高价值的应对。',
                },
                auto_result: 'WIN',
                auto_reward: 10.0,
                session_id: 'T001',
                tactics: [
                    {
                        name: '反手挡网',
                        content: '用轻柔的反手挡网将进攻者拉向前场。',
                        metadata: {
                            tactic_id: 'T001',
                            name: '反手挡网',
                            alpha: 5.0,
                            beta: 1.0,
                        },
                        score: 0.85,
                    },
                    {
                        name: '高远球重置',
                        content: '将球挑高打深至底线以恢复场地平衡。',
                        metadata: {
                            tactic_id: 'T002',
                            name: '高远球重置',
                            alpha: 2.0,
                            beta: 3.0,
                        },
                        score: 0.45,
                    },
                ],
                match_type: matchType,
            });
        }, 2000);
    });
};
