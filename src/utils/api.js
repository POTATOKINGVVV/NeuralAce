const API_BASE_URL = 'http://10.241.96.164:8000';

const ensureArray = (value) => (Array.isArray(value) ? value : []);
const hasText = (value) => typeof value === 'string' && value.trim().length > 0;
const hasObjectKeys = (value) => Boolean(value) && typeof value === 'object' && !Array.isArray(value) && Object.keys(value).length > 0;

const normalizeAdvice = (advice, fallbackTactics = []) => {
    const text = typeof advice === 'string' ? advice : advice?.text;
    const fallbackAction = fallbackTactics[0]?.recommended_action || '准备下一拍。';

    return {
        text: text || '保持平衡，提前准备。',
        headline: advice?.headline || '保持冷静',
        focus: advice?.focus || '恢复',
        next_step: advice?.next_step || fallbackAction,
        confidence_label: advice?.confidence_label || fallbackTactics[0]?.confidence_label || 'medium',
        source: advice?.source || 'fallback',
    };
};

const normalizeTactics = (tactics = []) =>
    tactics.map((tactic, index) => {
        const name =
            tactic?.name
            || tactic?.metadata?.name
            || tactic?.content
            || `战术 ${index + 1}`;

        return {
            ...tactic,
            name,
            content: tactic?.content || name,
            score: tactic?.score || 0,
            semantic_score: tactic?.semantic_score || 0,
            bayesian_score: tactic?.bayesian_score || 0,
            context_score: tactic?.context_score || 0,
            quality_weight: tactic?.quality_weight || 1,
            expected_win_rate: tactic?.expected_win_rate || 50,
            confidence_label: tactic?.confidence_label || 'medium',
            recommended_action: tactic?.recommended_action || tactic?.content || name,
            reason: tactic?.reason || '',
            why_this_tactic: tactic?.why_this_tactic || '',
            risk_note: tactic?.risk_note || '',
            rerank_score: tactic?.rerank_score || tactic?.score || 0,
            continuity_score: tactic?.continuity_score || 0,
            coverage_score: tactic?.coverage_score || 0,
            volatility_guard: tactic?.volatility_guard || 0,
            novelty_bonus: tactic?.novelty_bonus || 0,
            rank_reason: tactic?.rank_reason || '',
            frontier_hint: tactic?.frontier_hint || '',
            evolution_replay: tactic?.evolution_replay || {},
        };
    });

const normalizeSequenceContext = (sequenceContext = {}) => {
    const recentTactics = ensureArray(sequenceContext?.recent_tactics).map((snapshot, index) => ({
        rally_index: snapshot?.rally_index ?? index + 1,
        name: snapshot?.name || `战术 ${index + 1}`,
        tactic_id: snapshot?.tactic_id || 'unknown',
        style_family: snapshot?.style_family || 'balanced',
        phase_preference: snapshot?.phase_preference || 'neutral',
        risk_level: snapshot?.risk_level || 'medium',
        score: snapshot?.score ?? 0,
    }));
    const tacticTransitions = ensureArray(sequenceContext?.tactic_transitions).map((transition) => ({
        from: transition?.from || '未知',
        to: transition?.to || '未知',
        style_shift: transition?.style_shift || 'balanced -> balanced',
    }));
    const adaptationSignals = ensureArray(sequenceContext?.adaptation_signals);
    const playerAdjustmentSignals = ensureArray(sequenceContext?.player_adjustment_signals);
    const sequenceTags = ensureArray(sequenceContext?.sequence_tags);

    return {
        match_type: sequenceContext?.match_type || 'singles',
        window_size: sequenceContext?.window_size || 0,
        recent_events: ensureArray(sequenceContext?.recent_events),
        recent_results: ensureArray(sequenceContext?.recent_results),
        recent_pressures: ensureArray(sequenceContext?.recent_pressures),
        recent_phases: ensureArray(sequenceContext?.recent_phases),
        recent_tactics: recentTactics,
        event_distribution: sequenceContext?.event_distribution || {},
        tactic_distribution: sequenceContext?.tactic_distribution || {},
        style_distribution: sequenceContext?.style_distribution || {},
        tactic_transitions: tacticTransitions,
        streak_context: sequenceContext?.streak_context || {
            state: 'neutral',
            length: 0,
            last_result: 'UNKNOWN',
        },
        pressure_swing: sequenceContext?.pressure_swing || {
            label: 'steady',
            delta: 0,
            mean_pressure: 0,
            volatility: 0,
        },
        adaptation_signals: adaptationSignals,
        player_adjustment_signals: playerAdjustmentSignals,
        sequence_tags: sequenceTags,
        preferred_style_family: sequenceContext?.preferred_style_family || 'balanced',
        continuity_anchor: sequenceContext?.continuity_anchor || {},
        adaptation_score: sequenceContext?.adaptation_score ?? 0,
        memory_summary: sequenceContext?.memory_summary || '',
        retrieval_context: sequenceContext?.retrieval_context || {},
        has_content: Boolean(
            hasText(sequenceContext?.memory_summary)
            || recentTactics.length > 0
            || tacticTransitions.length > 0
            || adaptationSignals.length > 0
            || playerAdjustmentSignals.length > 0
            || sequenceTags.length > 0
            || Number(sequenceContext?.adaptation_score) > 0
            || hasObjectKeys(sequenceContext?.continuity_anchor)
        ),
    };
};

const normalizeDuelProjection = (duelProjection = {}) => {
    const counterTactics = ensureArray(duelProjection?.counter_tactics).map((counter, index) => ({
        name: counter?.name || `反击 ${index + 1}`,
        family: counter?.family || 'balanced',
        fit_score: counter?.fit_score ?? 0,
        reason: counter?.reason || '没有可用的反击说明。',
    }));
    const exchangeScript = ensureArray(duelProjection?.exchange_script);

    return {
        primary_plan: duelProjection?.primary_plan || '中性重置',
        likely_response: duelProjection?.likely_response || '',
        counter_window: duelProjection?.counter_window || '',
        duel_risk: duelProjection?.duel_risk ?? 0,
        duel_risk_label: duelProjection?.duel_risk_label || 'low',
        counter_tactics: counterTactics,
        exchange_script: exchangeScript,
        duel_explanation: duelProjection?.duel_explanation || '',
        pressure_gate: duelProjection?.pressure_gate || '',
        has_content: Boolean(
            hasText(duelProjection?.likely_response)
            || hasText(duelProjection?.duel_explanation)
            || hasText(duelProjection?.pressure_gate)
            || hasText(duelProjection?.primary_plan)
            || hasText(duelProjection?.counter_window)
            || counterTactics.length > 0
            || exchangeScript.length > 0
            || Number(duelProjection?.duel_risk) > 0
        ),
    };
};

const normalizeTrainingPlan = (trainingPlan = {}) => {
    const blocks = ensureArray(trainingPlan?.blocks).map((block, index) => ({
        label: block?.label || `训练块 ${index + 1}`,
        duration_min: block?.duration_min ?? 0,
        intensity: block?.intensity || 'medium',
        goal: block?.goal || '',
    }));

    return {
        theme: trainingPlan?.theme || trainingPlan?.match_theme || '适应性训练块',
        priority: trainingPlan?.priority || 'pattern-reinforcement',
        micro_goal: trainingPlan?.micro_goal || '',
        guardrail: trainingPlan?.guardrail || '',
        focus_queue: ensureArray(trainingPlan?.focus_queue),
        phase_distribution: ensureArray(trainingPlan?.phase_distribution),
        blocks,
        has_content: Boolean(
            hasText(trainingPlan?.theme)
            || hasText(trainingPlan?.match_theme)
            || hasText(trainingPlan?.micro_goal)
            || hasText(trainingPlan?.guardrail)
            || ensureArray(trainingPlan?.focus_queue).length > 0
            || ensureArray(trainingPlan?.phase_distribution).length > 0
            || blocks.length > 0
        ),
    };
};

const normalizeReplayStory = (replayStory = {}) => {
    const turningPoints = ensureArray(replayStory?.turning_points);
    const adaptationCycles = ensureArray(replayStory?.adaptation_cycles);
    const criticalRallies = ensureArray(replayStory?.critical_rallies);
    const storylineCards = ensureArray(replayStory?.storyline_cards);
    const timelineDigest = ensureArray(replayStory?.timeline_digest);

    return {
        opening_phase: replayStory?.opening_phase || {},
        turning_points: turningPoints,
        adaptation_cycles: adaptationCycles,
        critical_rallies: criticalRallies,
        closing_state: replayStory?.closing_state || {},
        storyline_cards: storylineCards,
        timeline_digest: timelineDigest,
        replay_summary: replayStory?.replay_summary || '',
        has_content: Boolean(
            hasText(replayStory?.replay_summary)
            || turningPoints.length > 0
            || adaptationCycles.length > 0
            || criticalRallies.length > 0
            || storylineCards.length > 0
            || timelineDigest.length > 0
            || hasObjectKeys(replayStory?.opening_phase)
            || hasObjectKeys(replayStory?.closing_state)
        ),
    };
};

const normalizeDiagnostics = (diagnostics = {}) => ({
    warnings: diagnostics?.warnings || [],
    pipeline: diagnostics?.pipeline || {},
    motion_feedback: diagnostics?.motion_feedback || '不可用',
    trajectory_points: diagnostics?.trajectory_points || 0,
    analysis_quality: diagnostics?.analysis_quality || 'medium',
    retrieval_summary: diagnostics?.retrieval_summary || {},
    physics_profile: diagnostics?.physics_profile || {},
    tracker_diagnostics: diagnostics?.tracker_diagnostics || {},
    motion_profile: diagnostics?.motion_profile || {},
    rally_quality: diagnostics?.rally_quality || {},
    confidence_report: diagnostics?.confidence_report || {},
    referee_audit: diagnostics?.referee_audit || {},
    sequence_context: normalizeSequenceContext(diagnostics?.sequence_context),
    duel_projection: normalizeDuelProjection(diagnostics?.duel_projection),
    policy_update: diagnostics?.policy_update || {},
});

const normalizeSummary = (summary = {}) => ({
    headline: summary?.headline || '回合已捕获',
    verdict: summary?.verdict || 'UNKNOWN',
    confidence_label: summary?.confidence_label || 'medium',
    key_takeaway: summary?.key_takeaway || '查看建议并为下一次交换做准备。',
});

const normalizeReport = (report = {}, diagnostics = {}) => ({
    ...report,
    technical_snapshot: report?.technical_snapshot || {},
    confidence_snapshot: report?.confidence_snapshot || diagnostics?.confidence_report || {},
    tracking_snapshot: report?.tracking_snapshot || diagnostics?.tracker_diagnostics || {},
    referee_snapshot: report?.referee_snapshot || diagnostics?.referee_audit || {},
    sequence_snapshot: report?.sequence_snapshot || diagnostics?.sequence_context || {},
    duel_snapshot: normalizeDuelProjection(report?.duel_snapshot || diagnostics?.duel_projection),
    tactic_snapshot: report?.tactic_snapshot || {},
    training_plan: normalizeTrainingPlan(report?.training_plan),
    replay_story: normalizeReplayStory(report?.replay_story),
    coach_takeaway: report?.coach_takeaway || '专注下一次交换中的稳定执行。',
});

const buildFallbackReplayStory = (result, diagnostics, report) => {
    const sequenceContext = diagnostics?.sequence_context || {};
    const duelProjection = diagnostics?.duel_projection || {};
    const topTactic = result?.tactics?.[0]?.name || report?.top_tactic || '中性重置';
    const eventName = result?.physics?.event || '回合';
    const verdict = result?.auto_result || result?.summary?.verdict || 'UNKNOWN';

    return normalizeReplayStory({
        opening_phase: {
            headline: '单回合回放',
            events: [eventName],
            tactics: [topTactic],
            average_pressure: result?.physics?.pressure_index ?? 0,
            summary: `本次回放以 ${eventName} 为中心，${topTactic} 为主要战术支点。`,
        },
        turning_points: duelProjection?.duel_explanation
            ? [
                {
                    rally_index: 1,
                    trigger: duelProjection.duel_explanation,
                    summary: result?.summary?.headline || '回合转折',
                },
            ]
            : [],
        adaptation_cycles: ensureArray(sequenceContext?.tactic_transitions).length > 0
            ? ensureArray(sequenceContext?.tactic_transitions).map((transition) => ({
                from: transition?.from || '未知',
                to: transition?.to || '未知',
                style_shift: transition?.style_shift || 'balanced -> balanced',
                summary: `战术判断从 ${transition?.from || '未知'} 转向 ${transition?.to || '未知'}。`,
            }))
            : [
                {
                    from: '初始判断',
                    to: topTactic,
                    style_shift: 'single-anchor',
                    summary: report?.coach_takeaway || '片段围绕一个主要战术支点展开。',
                },
            ],
        critical_rallies: [
            {
                rally_index: 1,
                score: result?.auto_reward ?? 0,
                headline: result?.summary?.headline || '关键回合',
                takeaway: result?.summary?.key_takeaway || report?.coach_takeaway || '',
            },
        ],
        closing_state: {
            last_rally_index: 1,
            verdict,
            tactic_anchor: topTactic,
            momentum_state: sequenceContext?.streak_context?.state || 'neutral',
            dominant_duel: duelProjection?.primary_plan || topTactic,
            summary: `回放以 ${verdict.toLowerCase()} 判定结束，${topTactic} 为战术支点。`,
        },
        storyline_cards: [
            {
                stage: 'opening',
                title: eventName,
                body: sequenceContext?.memory_summary || result?.summary?.key_takeaway || '回放摘要不可用。',
            },
            {
                stage: 'duel',
                title: duelProjection?.primary_plan || topTactic,
                body: duelProjection?.likely_response || '未生成对抗响应。',
            },
            {
                stage: 'closing',
                title: '教练总结',
                body: report?.coach_takeaway || result?.summary?.key_takeaway || '回顾交换并准备下一次应对。',
            },
        ],
        timeline_digest: [
            {
                rally_index: 1,
                event: eventName,
                verdict,
                top_tactic: topTactic,
                pressure: result?.physics?.pressure_index ?? 0,
            },
        ],
        replay_summary: report?.coach_takeaway || result?.summary?.key_takeaway || '本片段的回放故事不可用。',
    });
};

const normalizeAnalysisResult = (result) => {
    const diagnostics = normalizeDiagnostics(result?.diagnostics);
    const report = normalizeReport(result?.report, diagnostics);
    const tactics = normalizeTactics(result?.tactics).map((tactic, index) => {
        if (index !== 0) {
            return tactic;
        }

        const reportTacticSnapshot = report?.tactic_snapshot || {};

        return {
            ...tactic,
            why_this_tactic: tactic?.why_this_tactic || reportTacticSnapshot?.why_this_tactic || '',
            risk_note: tactic?.risk_note || reportTacticSnapshot?.risk_note || '',
            rank_reason: tactic?.rank_reason || reportTacticSnapshot?.rank_reason || '',
            frontier_hint: tactic?.frontier_hint || reportTacticSnapshot?.frontier_hint || '',
            evolution_replay: hasObjectKeys(tactic?.evolution_replay)
                ? tactic.evolution_replay
                : (reportTacticSnapshot?.evolution_replay || {}),
        };
    });
    const replayStory = normalizeReplayStory(
        result?.replay_story
        || result?.match_summary?.replay_story
        || report?.replay_story
        || buildFallbackReplayStory(
            {
                ...result,
                tactics,
            },
            diagnostics,
            report,
        ),
    );

    const normalized = {
        ...result,
        match_type: result?.match_type || diagnostics?.sequence_context?.match_type || 'singles',
        sport_type: result?.sport_type || 'badminton',
        advice: normalizeAdvice(result?.advice, tactics),
        tactics,
        summary: normalizeSummary(result?.summary),
        diagnostics,
        report,
        replay_story: replayStory,
        physics: {
            ...result?.physics,
            description: result?.physics?.description || '无可用的分析详情。',
            referee_confidence: result?.physics?.referee_confidence ?? 0.72,
            trajectory_quality: result?.physics?.trajectory_quality ?? 0.78,
            referee_reason: result?.physics?.referee_reason || '裁判解释不可用。',
        },
    };

    return normalized;
};

const createBadmintonDebugResponse = (videoUrl, matchType) => ({
    videoUrl,
    physics: {
        event: '重力杀球',
        max_speed_kmh: 235,
        duration: 4.5,
        description: `模式: ${matchType === 'doubles' ? '双打' : '单打'}。事件: 重力杀球。最高球速 235 km/h。判定: 得分。`,
        trajectory_quality: 0.84,
        referee_confidence: 0.87,
        referee_reason: '最后击球方被推断为用户，具有稳定的下压结束，落点舒适地在场内。',
        court_context: 'rear_channel',
        attack_phase: 'advantage',
        tempo_profile: 'fast',
        pressure_index: 0.47,
        rally_state: {
            trajectory_quality: 0.84,
            landing_confidence: 0.9,
            direction_consistency: 0.82,
            speed_profile: {
                mean_speed_kmh: 118.4,
                max_speed_kmh: 235,
                end_speed_kmh: 58.2,
            },
            court_context: 'rear_channel',
        },
    },
    sport_type: 'badminton',
});

const createTableTennisDebugResponse = (videoUrl, matchType) => ({
    videoUrl,
    physics: {
        auto_result: 'FAULT',
        referee_confidence: 0.672,
        referee_reason: '球在A侧最后一次有效弹跳后落在界外。',
        bounces: [{frame_index: 12, x: 280, y: 190, side: 'A', in_bounds: true, confidence: 0.8}],
        bounce_count: 19,
        court_context: 'A_deep_wide',
        last_hitter: 'OPPONENT',
        winning_side: 'B',
        is_in: false,
        landing_point: [415.2, 310.8],
        direction_consistency: 0.743,
        event: '多拍相持',
        max_speed_kmh: 45.95,
        mean_speed_kmh: 28.73,
        end_speed_kmh: 15.42,
        pressure_index: 0.803,
        trajectory_quality: 0.625,
        attack_phase: 'under_pressure',
        tempo_profile: 'fast',
        shot_shape: 'topspin-loop',
        last_bounce_side: 'OUT',
        description: '检测到 19 次弹跳，自动结果为 FAULT 的乒乓球回合。',
        referee_trace: {
            decision: 'fault',
            rule_chain: '球在A侧最后一次有效弹跳后落在界外。',
            bounce_sides: ['A','B','A','B','A','B','OUT']
        }
    },
    sport_type: 'table_tennis',
    auto_result: 'FAULT',
    auto_reward: -3.169,
});

const createDebugResponse = (videoUrl, matchType, sportType) => {
    if (sportType === 'table_tennis') {
        return {
            ...createTableTennisDebugResponse(videoUrl, matchType),
            advice: {
                text: '识别旋转，保持紧凑，控制落点。',
                headline: '保持冷静',
                focus: '恢复',
                next_step: '准备下一拍。',
                confidence_label: 'medium',
                source: 'heuristic'
            },
            tactics: [
                {
                    name: '第三板进攻',
                    content: '发球后用第三板建立主动进攻。',
                    score: 0.92,
                    semantic_score: 0.88,
                    bayesian_score: 0.95,
                    context_score: 0.89,
                    quality_weight: 0.94,
                    expected_win_rate: 78.5,
                    confidence_label: 'high',
                    recommended_action: '发球后用第三板建立主动进攻。',
                    reason: '第三板进攻非常匹配当前回合场景，战术连贯性强。',
                    why_this_tactic: '该战术利用对手还在调整时的早期回合机会。',
                    risk_note: '确保第三板落点精准，避免丧失主动权。',
                    rank_reason: '第三板进攻因战术匹配度和连贯性强而排名最高。',
                    frontier_hint: '继续为不同接发情景精炼第三板变化。',
                    evolution_replay: {
                        development_stage: 'refine',
                        policy_mode: 'balanced',
                        replay_score: 0.91,
                        risk_axis: 'medium',
                        training_block: '第三板进攻变化',
                        why_now: '第三板进攻能建立早期回合控制，现在很合适。',
                        upgrade_path: [
                            '从不同接发位置练习第三板进攻。',
                            '发展上旋和下旋两种变化。',
                            '注重落点而不仅仅是力量。'
                        ]
                    },
                    metadata: {tactic_id: 'TT006', alpha: 1.0, beta: 1.0}
                }
            ],
            summary: {
                headline: '多拍相持回合捕获',
                verdict: 'FAULT',
                confidence_label: 'medium',
                key_takeaway: '专注于多拍相持中的旋转识别和落点控制。'
            },
            match_type: matchType,
            diagnostics: {
                warnings: [],
                pipeline: {
                    court_detection: 'ok',
                    tracking: 'ok',
                    pose: 'ok',
                    physics: 'ok',
                    retrieval: 'ok',
                    coach: 'ok',
                },
                motion_feedback: '保持紧凑注意旋转。 | 专注步法提前到位。',
                trajectory_points: 22,
                analysis_quality: 'medium',
                sequence_context: {
                    match_type: matchType,
                    window_size: 2,
                    recent_events: ['网前控制', '多拍相持'],
                    recent_results: ['WIN', 'FAULT'],
                    recent_pressures: [0.65, 0.80],
                    recent_phases: ['neutral', 'under_pressure'],
                    recent_tactics: [
                        {
                            rally_index: 1,
                            name: '推挡控制',
                            tactic_id: 'TT003',
                            style_family: 'control',
                            phase_preference: 'neutral',
                            risk_level: 'low',
                            score: 0.75,
                        },
                        {
                            rally_index: 2,
                            name: '第三板进攻',
                            tactic_id: 'TT006',
                            style_family: 'attack',
                            phase_preference: 'advantage',
                            risk_level: 'medium',
                            score: 0.92,
                        },
                    ],
                    tactic_transitions: [
                        {
                            from: '推挡控制',
                            to: '第三板进攻',
                            style_shift: 'control -> attack',
                        },
                    ],
                    streak_context: {
                        state: 'neutral',
                        length: 1,
                        last_result: 'FAULT',
                    },
                    pressure_swing: {
                        label: 'increasing',
                        delta: 0.15,
                        mean_pressure: 0.72,
                        volatility: 0.12,
                    },
                    adaptation_signals: [
                        '回合时长增加，需要保持稳定性。',
                        '检测到旋转变化，相应调整拍面角度。',
                    ],
                    player_adjustment_signals: [
                        '因FAULT攻击阶段转为被动。',
                        '压力负荷略微增加，专注控制。',
                    ],
                    sequence_tags: ['spin-rally', 'control-phase'],
                    preferred_style_family: 'control',
                    continuity_anchor: {
                        name: 'Push Control',
                        style_family: 'control',
                    },
                    adaptation_score: 0.68,
                    memory_summary: '序列记忆显示多拍旋转相持以FAULT结束，专注控制和落点。',
                },
                duel_projection: {
                    primary_plan: '第三板进攻',
                    likely_response: '对手可能会尝试快速反攻。',
                    counter_window: 'fourth-ball',
                    duel_risk: 0.62,
                    duel_risk_label: 'medium',
                    counter_tactics: [
                        {
                            name: '挡球控制',
                            family: 'control',
                            fit_score: 0.85,
                            reason: '挡球控制通过降低节奏有效应对快速反攻。',
                        },
                    ],
                    exchange_script: [
                        '多拍相持中专注控制和落点。',
                        '准备好改变节奏和旋转变化。',
                        '如果对手进攻，用控制性挡球重置回合。',
                    ],
                    duel_explanation: '第三板进攻是不错的选择，但在多拍旋转相持中风险中等。',
                    pressure_gate: '保持控制，避免在压力下强行进攻。',
                },
                policy_update: {
                    weighted_increment: 0.72,
                    quality_weight: 0.88,
                    confidence_weight: 0.82,
                    exploration_guard: 0.78,
                    adaptation_level: 'medium',
                    policy_update_reason: '根据多拍旋转相持动态和FAULT结果更新策略。',
                    reward_components: {
                        raw_reward: -3.169,
                        trajectory_quality: 0.625,
                        referee_confidence: 0.672,
                        retrieval_confidence: 0.85,
                    },
                },
            },
            report: {
                headline: '多拍旋转相持',
                verdict: 'FAULT',
                top_tactic: '第三板进攻',
                technical_snapshot: {
                    event: '多拍相持',
                    pressure_index: 0.803,
                    attack_phase: 'under_pressure',
                    tempo_profile: 'fast',
                },
                confidence_snapshot: {
                    calibrated_confidence: 0.74,
                    volatility: 0.15,
                    caution_level: 'medium',
                },
                tracking_snapshot: {
                    signal_integrity: 0.85,
                    repaired_points: 2,
                    spike_count: 1,
                },
                referee_snapshot: {
                    audit_level: 'clean',
                    verdict_stability: 0.72,
                    recommended_action: 'FAULT判定可靠，可用于训练目的。',
                },
                sequence_snapshot: {
                    memory_summary: '序列记忆显示多拍旋转相持以FAULT结束，专注控制和落点。',
                    sequence_tags: ['spin-rally', 'control-phase'],
                    streak_context: {
                        state: 'neutral',
                        length: 1,
                        last_result: 'FAULT',
                    },
                },
                duel_snapshot: {
                    primary_plan: '第三板进攻',
                    likely_response: '对手可能会尝试快速反攻。',
                    counter_window: 'fourth-ball',
                    duel_risk: 0.62,
                    duel_risk_label: 'medium',
                    counter_tactics: [
                        {
                            name: '挡球控制',
                            family: 'control',
                            fit_score: 0.85,
                            reason: '挡球控制通过降低节奏有效应对快速反攻。',
                        },
                    ],
                    exchange_script: [
                        '多拍相持中专注控制和落点。',
                        '准备好改变节奏和旋转变化。',
                        '如果对手进攻，用控制性挡球重置回合。',
                    ],
                    duel_explanation: '第三板进攻是不错的选择，但在多拍旋转相持中风险中等。',
                    pressure_gate: '保持控制，避免在压力下强行进攻。',
                },
                tactic_snapshot: {
                    why_this_tactic: '第三板进攻通过创造进攻机会匹配多拍相持模式。',
                    risk_note: '多拍旋转相持中注意落点，避免可预测的进攻。',
                    rank_reason: '第三板进攻因战术连贯性和适应性排名最高。',
                    frontier_hint: '为不同接发情景发展更多第三板变化。',
                    evolution_replay: {
                        development_stage: 'refine',
                        policy_mode: 'balanced',
                        replay_score: 0.91,
                        risk_axis: 'medium',
                        training_block: '第三板进攻变化',
                        why_now: '第三板进攻能建立早期回合控制，现在很合适。',
                        upgrade_path: [
                            '从不同接发位置练习第三板进攻。',
                            '发展上旋和下旋两种变化。',
                            '注重落点而不仅仅是力量。'
                        ]
                    },
                },
                training_plan: {
                    theme: '多拍旋转相持控制',
                    priority: 'control-consistency',
                    micro_goal: '提高多拍相持中的落点稳定性和旋转识别能力。',
                    guardrail: '多拍相持中被动时避免强行进攻。',
                    focus_queue: ['旋转识别', '落点稳定性', '步法'],
                    phase_distribution: ['neutral', 'under_pressure'],
                    blocks: [
                        {
                            label: '旋转识别训练',
                            duration_min: 10,
                            intensity: 'medium',
                            goal: '提高识别和应对不同旋转类型的能力。',
                        },
                        {
                            label: '多拍相持练习',
                            duration_min: 15,
                            intensity: 'medium',
                            goal: '建立长回合中的稳定性和控制力。',
                        },
                    ],
                },
                coach_takeaway: '专注于多拍相持中的控制、落点和旋转识别。',
            },
        };
    }
    return {
        ...createBadmintonDebugResponse(videoUrl, matchType),
        advice: {
            text: '继续利用反手挡网，接触后立即向前恢复。',
            headline: '反击回球',
            focus: '过渡速度',
            next_step: '轻柔挡网到前场，然后积极上前。',
            confidence_label: 'high',
            source: 'debug',
        },
        tactics: [
            {
                name: '反手挡网',
                content: '重杀后用轻柔的反手挡网迫使攻击方上前。',
                metadata: {
                    tactic_id: 'T001',
                    name: '反手挡网',
                    alpha: 5,
                    beta: 1,
                    style_family: 'absorb-and-redirect',
                    phase_preference: 'under_pressure',
                    risk_level: 'medium',
                },
                score: 0.91,
                semantic_score: 0.83,
                bayesian_score: 0.95,
                context_score: 0.88,
                quality_weight: 0.97,
                expected_win_rate: 83.3,
                confidence_label: 'high',
                recommended_action: '重杀后用轻柔的反手挡网迫使攻击方上前。',
                reason: '反手挡网是首选推荐，因为它匹配235.0 km/h的重杀场景，且预期胜率很高。',
                why_this_tactic: '这是后场重攻的最佳匹配，因为它将对手的速度转化为前场压迫机会。',
                risk_note: '球速非常快，挡网只有在拍面保持柔和稳定时才有效。',
                rerank_score: 0.94,
                continuity_score: 0.89,
                coverage_score: 0.84,
                rank_reason: '反手挡网保持领先，因为连贯性和波动性防护在序列中始终强劲。',
                frontier_hint: '该分支足够稳定，可以在被动交换中继续强化。',
                evolution_replay: {
                    development_stage: 'refine',
                    policy_mode: 'exploit',
                    replay_score: 0.94,
                    risk_axis: 'medium',
                    training_block: '压力吸收 + 反击释放',
                    why_now: '反手挡网现在很合适，因为它在压力缓解时保持了强排名值。',
                    upgrade_path: [
                        '从被动情景演练反手挡网的进入方式。',
                        '跟踪第一次进攻触球是创造了空间还是引发了混乱。',
                        '强化最可重复的变体，剪除噪声分支。',
                    ],
                },
            },
            {
                name: '深区挑球重置',
                content: '快速挑球到后场角落重置回合，争取恢复时间。',
                metadata: {
                    tactic_id: 'T002',
                    name: '深区挑球重置',
                    alpha: 3,
                    beta: 2,
                    style_family: 'reset-and-rebuild',
                    phase_preference: 'neutral',
                    risk_level: 'low',
                },
                score: 0.74,
                semantic_score: 0.71,
                bayesian_score: 0.69,
                context_score: 0.72,
                quality_weight: 0.94,
                expected_win_rate: 60,
                confidence_label: 'medium',
                recommended_action: '快速挑球到后场角落重置回合，争取恢复时间。',
                reason: '深区挑球重置仍然可行，因为它减缓交换节奏并重建场地平衡。',
                why_this_tactic: '当无法干净地控制挡网且需要额外恢复时间时，这是更安全的备选方案。',
                risk_note: '如果挑球偏短，可能给攻击方提供另一个全力球。',
                rerank_score: 0.76,
                continuity_score: 0.61,
                coverage_score: 0.7,
                rank_reason: '深区挑球重置作为低风险备选保留在列表中，适用于对抗紧张时。',
                frontier_hint: '当挡网时机偏晚时，保持该分支作为备用变化。',
                evolution_replay: {
                    development_stage: 'stabilize',
                    policy_mode: 'balanced',
                    replay_score: 0.71,
                    risk_axis: 'low',
                    training_block: '节奏控制和结构保持',
                    why_now: '深区挑球重置在无法在网前干净地缓和交换时始终适用。',
                    upgrade_path: [
                        '从防守位置演练高远挑球。',
                        '跟踪重置是否买到了足够的恢复时间。',
                        '当主要对抗变得不稳定时作为备用分支。',
                    ],
                },
            },
        ],
        summary: {
            headline: '检测到获胜模式',
            verdict: 'WIN',
            confidence_label: 'high',
            key_takeaway: '主要战术方向：反手挡网。下一次交换中专注过渡速度。',
        },
        diagnostics: {
            warnings: [],
            pipeline: {
                court_detection: 'ok',
                tracking: 'ok',
                pose: 'ok',
                physics: 'ok',
                retrieval: 'ok',
                coach: 'ok',
            },
            motion_feedback: '重心控制稳定，但防守站姿还有下降空间。 | 击球点伸展充分，击球结构良好。',
            trajectory_points: 18,
            analysis_quality: 'high',
            sequence_context: {
                match_type: matchType,
                window_size: 3,
                recent_events: ['陡压杀球', '抽球交换', '重力杀球'],
                recent_results: ['LOSS', 'WIN', 'WIN'],
                recent_pressures: [0.72, 0.58, 0.47],
                recent_phases: ['under_pressure', 'transition', 'advantage'],
                recent_tactics: [
                    {
                        rally_index: 1,
                        name: '直线解围高远',
                        tactic_id: 'T004',
                        style_family: 'reset-and-rebuild',
                        phase_preference: 'under_pressure',
                        risk_level: 'low',
                        score: 0.69,
                    },
                    {
                        rally_index: 2,
                        name: '身体抽球压迫',
                        tactic_id: 'T006',
                        style_family: 'compression-attack',
                        phase_preference: 'neutral',
                        risk_level: 'medium',
                        score: 0.81,
                    },
                    {
                        rally_index: 3,
                        name: '反手挡网',
                        tactic_id: 'T001',
                        style_family: 'absorb-and-redirect',
                        phase_preference: 'under_pressure',
                        risk_level: 'medium',
                        score: 0.91,
                    },
                ],
                tactic_transitions: [
                    {
                        from: '直线解围高远',
                        to: '身体抽球压迫',
                        style_shift: 'reset-and-rebuild -> compression-attack',
                    },
                    {
                        from: '身体抽球压迫',
                        to: '反手挡网',
                        style_shift: 'compression-attack -> absorb-and-redirect',
                    },
                ],
                streak_context: {
                    state: 'surging',
                    length: 2,
                    last_result: 'WIN',
                },
                pressure_swing: {
                    label: 'releasing-pressure',
                    delta: -0.25,
                    mean_pressure: 0.59,
                    volatility: 0.1,
                },
                adaptation_signals: [
                    '近期序列不断回到杀球压力模式。',
                    '反手挡网已被反复重新使用作为首选答案。',
                ],
                player_adjustment_signals: [
                    '攻击阶段从被动转为优势。',
                    '最新战术调整后压力负荷下降。',
                ],
                sequence_tags: ['releasing-pressure', 'surging-streak', 'adaptation-live'],
                preferred_style_family: 'absorb-and-redirect',
                continuity_anchor: {
                    name: '反手挡网',
                    style_family: 'absorb-and-redirect',
                },
                adaptation_score: 0.68,
                memory_summary: '序列记忆显示近几次交换中压力正在释放，反手挡网成为最稳定的战术支点。',
            },
            duel_projection: {
                primary_plan: '反手挡网',
                likely_response: '对手可能会缩短交换并攻击第一个松动的回球。',
                counter_window: 'first-two-shots',
                duel_risk: 0.58,
                duel_risk_label: 'medium',
                counter_tactics: [
                    {
                        name: '身体抽球压迫',
                        family: 'compression-attack',
                        fit_score: 0.81,
                        reason: '身体抽球压迫适合过渡交换，对手过早前压时可惩罚柔和的前场挡网。',
                    },
                    {
                        name: '中场截击扫压',
                        family: 'interception',
                        fit_score: 0.77,
                        reason: '如果下一个球在中场保持平坦和松动，中场截击扫压将变得危险。',
                    },
                ],
                exchange_script: [
                    '以稳定的基础开始反手挡网。',
                    '对手可能会攻击第一个松动的回球。',
                    '如果交换转向，身体抽球压迫是最干净的反击通道。',
                ],
                duel_explanation: '反手挡网进入中等风险对抗，因为压力正在缓解，但如果挡网偏高对手仍有快速交换反击机会。',
                pressure_gate: '仅在第一次接触后基础保持平衡时才进入对抗。',
            },
            policy_update: {
                weighted_increment: 0.87,
                quality_weight: 0.91,
                confidence_weight: 0.96,
                exploration_guard: 0.85,
                adaptation_level: 'strong',
                policy_update_reason: '使用强轨迹质量、高裁判置信度和高检索置信度更新alpha。',
                reward_components: {
                    raw_reward: 10,
                    trajectory_quality: 0.84,
                    referee_confidence: 0.87,
                    retrieval_confidence: 0.91,
                },
            },
        },
        report: {
            headline: '检测到获胜模式',
            verdict: 'WIN',
            top_tactic: '反手挡网',
            technical_snapshot: {
                event: '重力杀球',
                pressure_index: 0.47,
                attack_phase: 'advantage',
                tempo_profile: 'fast',
            },
            confidence_snapshot: {
                calibrated_confidence: 0.89,
                volatility: 0.18,
                caution_level: 'low',
            },
            tracking_snapshot: {
                signal_integrity: 0.92,
                repaired_points: 1,
                spike_count: 0,
            },
            referee_snapshot: {
                audit_level: 'clean',
                verdict_stability: 0.86,
                recommended_action: '重杀判定足够稳定，可作为训练信号使用。',
            },
            sequence_snapshot: {
                memory_summary: '序列记忆显示近几次交换中压力正在释放，反手挡网成为最稳定的战术支点。',
                sequence_tags: ['releasing-pressure', 'surging-streak', 'adaptation-live'],
                streak_context: {
                    state: 'surging',
                    length: 2,
                    last_result: 'WIN',
                },
            },
            duel_snapshot: {
                primary_plan: '反手挡网',
                likely_response: '对手可能会缩短交换并攻击第一个松动的回球。',
                counter_window: 'first-two-shots',
                duel_risk: 0.58,
                duel_risk_label: 'medium',
                counter_tactics: [
                    {
                        name: '身体抽球压迫',
                        family: 'compression-attack',
                        fit_score: 0.81,
                        reason: '身体抽球压迫适合过渡交换，对手过早前压时可惩罚柔和的前场挡网。',
                    },
                ],
                exchange_script: [
                    '以稳定的基础开始反手挡网。',
                    '对手可能会攻击第一个松动的回球。',
                    '如果交换转向，身体抽球压迫是最干净的反击通道。',
                ],
                duel_explanation: '反手挡网进入中等风险对抗，因为压力正在缓解，但如果挡网偏高对手仍有快速交换反击机会。',
                pressure_gate: '仅在第一次接触后基础保持平衡时才进入对抗。',
            },
            tactic_snapshot: {
                why_this_tactic: '反手挡网将对手的速度转化为前场恢复难题。',
                risk_note: '保持拍面柔和。浮起的挡网会立即重新打开攻击。',
                rank_reason: '反手挡网保持领先，因为连贯性和波动性防护在序列中始终强劲。',
                frontier_hint: '该分支足够稳定，可以在被动交换中继续强化。',
                evolution_replay: {
                    development_stage: 'refine',
                    policy_mode: 'exploit',
                    replay_score: 0.94,
                    risk_axis: 'medium',
                    training_block: '压力吸收 + 反击释放',
                    why_now: '反手挡网现在很合适，因为它在压力缓解时保持了强排名值。',
                    upgrade_path: [
                        '从被动情景演练反手挡网的进入方式。',
                        '跟踪第一次进攻触球是创造了空间还是引发了混乱。',
                        '强化最可重复的变体，剪除噪声分支。',
                    ],
                },
            },
            training_plan: {
                theme: '反手挡网被动执行',
                priority: 'pattern-reinforcement',
                micro_goal: '先保持结构，然后将柔和的前场挡网转化为向前恢复。',
                guardrail: '仅在接触后基础保持平衡时才进入对抗。',
                blocks: [
                    {
                        label: '影子演练',
                        duration_min: 8,
                        intensity: 'low',
                        goal: '在不急于拍面的情况下模拟反手挡网的进入。',
                    },
                    {
                        label: '约束喂球',
                        duration_min: 12,
                        intensity: 'medium',
                        goal: '仅在稳定的第一次防守判断后触发挡网。',
                    },
                ],
            },
            coach_takeaway: '用回放注意当挡网停止喂给攻击方后压力如何缓解。',
        },
        match_type: matchType,
        auto_result: 'WIN',
        auto_reward: 10,
    };
};

export const api = {
    async uploadVideo(videoFile, options = {}) {
        const { isDebug = false, matchType = 'singles', sportType = 'badminton' } = options;

        if (isDebug) {
            const debugVideoUrl = videoFile ? URL.createObjectURL(videoFile) : '/samples/after.mp4';

            return new Promise((resolve) => {
                window.setTimeout(() => {
                    resolve(normalizeAnalysisResult(createDebugResponse(debugVideoUrl, matchType, sportType)));
                }, 1200);
            });
        }

        if (!videoFile) {
            throw new Error('请在开始分析前选择或录制一个片段。');
        }

        const formData = new FormData();
        formData.append('file', videoFile);
        formData.append('match_type', matchType);
        formData.append('sport_type', sportType);

        try {
            const localVideoUrl = URL.createObjectURL(videoFile);
            const response = await fetch(`${API_BASE_URL}/analyze_rally`, {
                method: 'POST',
                body: formData,
            });

            if (!response.ok) {
                let detail = '';
                try {
                    const errorPayload = await response.json();
                    detail = errorPayload?.detail || JSON.stringify(errorPayload);
                } catch {
                    try {
                        detail = await response.text();
                    } catch {
                        detail = '';
                    }
                }
                const reason = detail ? `: ${detail}` : '';
                throw new Error(`分析失败 (HTTP ${response.status})${reason}`);
            }

            const data = await response.json();

            return normalizeAnalysisResult({
                videoUrl: localVideoUrl,
                ...data,
            });
        } catch (error) {
            console.error('[API] Upload failed:', error);
            throw error;
        }
    },
};
