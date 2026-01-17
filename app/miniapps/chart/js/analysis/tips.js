/**
 * Tips system for trend analysis education
 */

/**
 * Tips library with educational messages
 */
export const TIPS_LIBRARY = {
    TOUCH_TL: '📍 线是区，不是点：用 ATR 给线留呼吸空间。',
    BREAK_TL: '⚡ 突破 ≠ 延续；接受（回踩不破）才算数。',
    BREAKOUT_ACCEPTED: '✅ 回踩确认！突破已被市场接受。',
    FAILED_BREAKDOWN: '🔥 失败跌破！假突破=最集中的错误仓位。',
    FAILED_BREAKOUT: '⚠️ 上破失败！假突破=最集中的错误仓位。',
    RISKY_NTH_TOUCH: '⚠️ 第 N 次触碰同一条线，风险显著上升。',
    TIMEFRAME_CHANGE: '🔄 周期不是让你看得更清楚，而是让错误更少地发生。',
    VOLUME_PULLBACK: '📉 回踩缩量是健康，回踩放量是危险。',
    NO_VOLUME_BREAKOUT: '⚠️ 缩量突破，谨慎对待。',
    STRUCTURE_BREAK: '🚨 结构破坏！止损基于结构失效，不是基于线。',

    // Downtrend Tips
    DOWNTREND_KNIFE: '🔪 下跌趋势不言底，左侧交易是接飞刀。',
    DOWNTREND_WAIT: '🛑 下跌不言底，等待结构破坏再进场。',
    DOWNTREND_RETEST: '📉 下跌趋势中的反弹往往是诱多，关注压力位。',

    // Uptrend Tips
    UPTREND_CHASE: '🚀 上涨不言顶，但连续大涨后切勿追高。',
    UPTREND_PULLBACK: '⏳ 强势股回调是机会，但不要在加速赶顶时接盘。',
    UPTREND_RISK: '⚠️ 乖离率过大，此时追高盈亏比极差。',
};

export const PERMANENT_TIP = '趋势线不是进场按钮，反应才是信号。';

/**
 * Tips Engine class for managing tip display
 */
export class TipsEngine {
    constructor() {
        this.lastTipTime = {};
        this.cooldownMs = 60000;
        this.tipContainer = null;
        this.permanentTipEl = null;
    }

    /**
     * Initialize the tips container
     */
    init() {
        this.tipContainer = document.createElement('div');
        this.tipContainer.id = 'tips-container';
        this.tipContainer.style.cssText = `
            position: absolute; top: 40px; right: 10px; z-index: 30;
            max-width: 280px; font-size: 11px; pointer-events: none;
        `;
        document.getElementById('main-chart').appendChild(this.tipContainer);

        this.permanentTipEl = document.createElement('div');
        this.permanentTipEl.style.cssText = `
            background: rgba(236, 72, 153, 0.15); color: #ec4899;
            padding: 6px 10px; border-radius: 6px; margin-bottom: 6px;
            border-left: 3px solid #ec4899;
        `;
        this.permanentTipEl.textContent = PERMANENT_TIP;
        this.tipContainer.appendChild(this.permanentTipEl);
    }

    /**
     * Check if a tip should be shown (cooldown check)
     * @param {string} tipKey 
     * @returns {boolean}
     */
    shouldShowTip(tipKey) {
        const now = Date.now();
        const lastTime = this.lastTipTime[tipKey] || 0;
        if (now - lastTime > this.cooldownMs) {
            this.lastTipTime[tipKey] = now;
            return true;
        }
        return false;
    }

    /**
     * Show a tip for the given event type
     * @param {string} eventType 
     */
    showTip(eventType) {
        if (!this.tipContainer) return;
        if (!this.shouldShowTip(eventType)) return;

        const text = TIPS_LIBRARY[eventType];
        if (!text) return;

        const tipEl = document.createElement('div');
        tipEl.style.cssText = `
            background: rgba(41, 98, 255, 0.2); color: #60a5fa;
            padding: 8px 12px; border-radius: 6px; margin-bottom: 6px;
            animation: tipFadeIn 0.3s ease-out;
            border-left: 3px solid #2962ff;
        `;
        tipEl.textContent = text;
        this.tipContainer.appendChild(tipEl);

        // Auto remove after 8 seconds
        setTimeout(() => {
            tipEl.style.opacity = '0';
            tipEl.style.transition = 'opacity 0.5s';
            setTimeout(() => tipEl.remove(), 500);
        }, 8000);
    }

    /**
     * Show a random tip from a list of keys
     * @param {string[]} keys 
     */
    showRandomTip(keys) {
        const key = keys[Math.floor(Math.random() * keys.length)];
        this.showTip(key);
    }
}

// Singleton instance
export const tipsEngine = new TipsEngine();
