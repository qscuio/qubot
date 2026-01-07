"""
Market Keywords Library

Comprehensive keyword database for market information detection and categorization.
Covers: Crypto, A-Stock (China), US Stock, HK Stock, Futures, Forex.
"""

from typing import List, Set


class MarketKeywords:
    """Market-specific keywords for content categorization and scoring."""
    
    # ═══════════════════════════════════════════════════════════════
    # 加密货币 / Cryptocurrency
    # ═══════════════════════════════════════════════════════════════
    CRYPTO = [
        # 主流币种
        "btc", "eth", "sol", "bnb", "xrp", "ada", "doge", "avax", "dot", "matic",
        "bitcoin", "ethereum", "solana", "比特币", "以太坊", "狗狗币",
        "ltc", "atom", "near", "apt", "sui", "arb", "op", "link", "uni",
        # 交易术语
        "多头", "空头", "爆仓", "清算", "杠杆", "合约", "永续", "现货",
        "开多", "开空", "平仓", "止损", "止盈", "挂单", "吃单", "滑点",
        "long", "short", "liquidation", "leverage", "futures", "spot", "perp",
        "maker", "taker", "funding rate", "资金费率",
        # DeFi / Web3
        "defi", "nft", "dao", "dex", "cex", "swap", "stake", "质押", "挖矿",
        "流动性", "池子", "tvl", "apy", "apr", "yield", "farming", "lp",
        "gas", "gas fee", "链上", "on-chain", "钱包", "wallet",
        "layer2", "l2", "rollup", "跨链", "bridge",
        # 项目动态
        "空投", "airdrop", "上线", "listing", "解锁", "unlock", "销毁", "burn",
        "白名单", "whitelist", "ido", "ico", "ieo", "launchpad", "presale",
        "主网", "mainnet", "测试网", "testnet", "升级", "分叉", "fork",
        # 交易所
        "binance", "okx", "bybit", "coinbase", "kraken", "bitget",
        "币安", "欧易", "火币", "huobi",
    ]
    
    # ═══════════════════════════════════════════════════════════════
    # A股 / 中国股市
    # ═══════════════════════════════════════════════════════════════
    A_STOCK = [
        # 指数
        "上证", "深证", "沪指", "深成指", "创业板", "科创板", "北交所",
        "上证50", "沪深300", "中证500", "中证1000", "中证2000",
        "a股", "a shares",
        # 交易术语
        "涨停", "跌停", "打板", "排板", "炸板", "封板", "一字板", "t字板",
        "龙头", "妖股", "连板", "断板", "反包", "卡位", "接力", "换手",
        "主力", "游资", "北向资金", "南向资金", "融资融券", "两融",
        "大单", "主力资金", "净流入", "净流出", "筹码", "成本", "浮盈", "浮亏",
        "集合竞价", "尾盘", "早盘", "午盘", "盘中", "竞价",
        # 技术分析
        "均线", "macd", "kdj", "rsi", "布林", "缺口", "跳空", "补缺",
        "金叉", "死叉", "顶背离", "底背离", "放量", "缩量", "天量", "地量",
        "突破", "回踩", "站稳", "跌破", "压力位", "支撑位",
        # 基本面
        "市盈率", "市净率", "pe", "pb", "roe", "eps", "营收", "净利润",
        "业绩预告", "业绩快报", "年报", "季报", "中报", "分红", "送转",
        "增持", "减持", "回购", "定增", "配股",
        # 题材/概念
        "板块", "概念", "题材", "热点", "赛道", "风口", "龙头股",
        "新能源", "光伏", "锂电", "芯片", "半导体", "ai", "算力", "机器人",
        "军工", "医药", "消费", "白酒", "银行", "券商", "保险", "地产",
        "国企改革", "央企", "国资", "并购重组",
        # 政策/事件
        "降准", "降息", "lpr", "mlf", "逆回购", "国常会", "政策",
        "ipo", "注册制", "退市", "st", "*st", "停牌", "复牌",
        "问询函", "监管", "证监会", "交易所",
        # 机构
        "公募", "私募", "社保", "险资", "外资", "qfii", "陆股通",
        "基金", "etf", "lof", "reits",
        # 俚语/黑话
        "韭菜", "割肉", "套牢", "解套", "抄底", "追高", "站岗", "接盘",
        "满仓", "半仓", "空仓", "加仓", "减仓", "清仓", "建仓", "补仓",
        "绿油油", "红彤彤", "吃面", "吃肉", "躺平", "躺赢", "核按钮",
        "镰刀", "大阴线", "大阳线", "十字星", "墓碑线",
    ]
    
    # ═══════════════════════════════════════════════════════════════
    # 美股 / 美国市场
    # ═══════════════════════════════════════════════════════════════
    US_STOCK = [
        # 指数
        "道琼斯", "纳斯达克", "标普500", "罗素2000",
        "dow jones", "nasdaq", "s&p 500", "s&p500", "russell",
        "美股", "us stock",
        # 科技股
        "aapl", "msft", "googl", "goog", "amzn", "meta", "tsla", "nvda", "amd",
        "apple", "microsoft", "google", "alphabet", "amazon", "tesla", "nvidia",
        "magnificent 7", "mag7", "七巨头", "科技七姐妹",
        "nflx", "netflix", "crm", "intc", "intel", "mu", "qcom",
        # 中概股
        "中概股", "baba", "jd", "pdd", "bidu", "ntes", "bili",
        "阿里", "京东", "拼多多", "百度", "网易", "哔哩哔哩",
        # 交易术语
        "盘前", "盘后", "premarket", "afterhours", "after hours",
        "earnings", "财报", "业绩", "eps", "guidance", "指引",
        "期权", "options", "call", "put", "看涨", "看跌", "行权", "到期",
        "gamma squeeze", "short squeeze", "轧空", "逼空", "空头回补",
        "meme stock", "散户", "retail", "wsb", "wallstreetbets", "reddit",
        # 宏观经济
        "fed", "fomc", "powell", "鲍威尔", "美联储", "联储",
        "cpi", "ppi", "pce", "非农", "nfp", "就业", "失业率",
        "gdp", "利率", "加息", "降息", "缩表", "扩表", "qe", "qt",
        "通胀", "衰退", "recession", "软着陆", "硬着陆", "滞胀",
        # 债券/汇率
        "美债", "国债", "treasury", "yield", "收益率", "倒挂",
        "美元", "dxy", "美元指数",
        "10年期", "2年期", "30年期",
        # 重要时间节点
        "jackson hole", "杰克逊霍尔", "议息会议", "点阵图", "褐皮书",
    ]
    
    # ═══════════════════════════════════════════════════════════════
    # 港股 / 香港市场
    # ═══════════════════════════════════════════════════════════════
    HK_STOCK = [
        # 指数
        "恒生", "恒指", "国企指数", "红筹", "h股",
        "hang seng", "hsi", "hscei",
        "港股", "港股通",
        # 交易术语
        "窝轮", "牛熊证", "权证", "涡轮",
        "碎股", "手数", "t+0",
        # 重要公司
        "腾讯", "阿里", "美团", "小米", "京东", "比亚迪",
        "汇丰", "友邦", "中国移动", "中国海油",
        "00700", "09988", "03690", "01810", "09618",
        # 市场术语
        "北水", "南下资金", "港股通", "沪港通", "深港通",
        "ipo", "暗盘", "招股", "超购", "冻资",
        "除净日", "派息", "拆股", "合股",
    ]
    
    # ═══════════════════════════════════════════════════════════════
    # 期货 / Futures
    # ═══════════════════════════════════════════════════════════════
    FUTURES = [
        # 商品期货
        "原油", "黄金", "白银", "铜", "铁矿石", "螺纹钢",
        "crude oil", "gold", "silver", "copper",
        "wti", "brent", "布伦特",
        # 农产品
        "大豆", "玉米", "小麦", "棉花", "白糖", "豆粕",
        "soybeans", "corn", "wheat",
        # 期货术语
        "期货", "主力合约", "交割", "移仓", "换月",
        "升水", "贴水", "基差", "持仓量", "仓单",
        "多单", "空单", "净多", "净空",
        "futures", "contract", "delivery",
        # 股指期货
        "股指期货", "if", "ih", "ic", "im",
        "沪深300期货", "上证50期货", "中证500期货",
        # 交易所
        "上期所", "大商所", "郑商所", "中金所",
        "cme", "comex", "nymex", "lme",
    ]
    
    # ═══════════════════════════════════════════════════════════════
    # 外汇 / Forex
    # ═══════════════════════════════════════════════════════════════
    FOREX = [
        # 主要货币对
        "外汇", "汇率", "forex", "fx",
        "美元", "欧元", "日元", "英镑", "人民币", "港币",
        "usd", "eur", "jpy", "gbp", "cny", "cnh", "hkd",
        "eur/usd", "usd/jpy", "gbp/usd", "usd/cnh",
        # 汇率术语
        "升值", "贬值", "在岸", "离岸",
        "中间价", "即期", "远期", "掉期",
        "点差", "pip", "basis point", "基点",
        # 央行
        "央行", "美联储", "欧央行", "日央行", "英央行",
        "fed", "ecb", "boj", "boe", "pboc",
        # 指数
        "美元指数", "dxy",
    ]
    
    # ═══════════════════════════════════════════════════════════════
    # 通用市场术语
    # ═══════════════════════════════════════════════════════════════
    GENERAL = [
        # 行情
        "突破", "回调", "反弹", "回撤", "震荡", "盘整", "趋势",
        "牛市", "熊市", "多头市场", "空头市场", "横盘",
        "支撑", "阻力", "压力位", "支撑位", "颈线", "趋势线",
        "新高", "新低", "历史新高", "ath",
        # 数据
        "成交量", "换手率", "市值", "流通", "总市值",
        "涨幅", "跌幅", "振幅", "最高", "最低", "开盘", "收盘",
        "k线", "分时", "日线", "周线", "月线",
        # 操作
        "做多", "做空", "对冲", "套利", "搬砖",
        "买入", "卖出", "持有", "观望",
        # 情绪
        "恐慌", "贪婪", "fomo", "fud", "看多", "看空", "观望",
        "恐慌指数", "vix", "情绪",
        # 事件
        "财经", "快讯", "突发", "重磅", "独家", "紧急",
    ]
    
    # ═══════════════════════════════════════════════════════════════
    # 看多/看空情绪关键词
    # ═══════════════════════════════════════════════════════════════
    BULLISH_KEYWORDS = [
        "涨", "突破", "新高", "利好", "牛市", "多头", "做多", "看涨",
        "上涨", "拉升", "暴涨", "飙升", "反弹", "回暖", "复苏",
        "超预期", "超额", "翻倍", "暴利", "盈利", "增长",
        "bullish", "rally", "surge", "pump", "moon", "ath", "breakout",
        "买入", "加仓", "抄底", "入场", "布局",
    ]
    
    BEARISH_KEYWORDS = [
        "跌", "下跌", "暴跌", "崩盘", "熊市", "空头", "做空", "看跌",
        "利空", "下挫", "跳水", "闪崩", "腰斩", "血崩",
        "清算", "爆仓", "割肉", "止损", "亏损", "亏钱",
        "bearish", "crash", "dump", "plunge", "correction", "sell-off",
        "卖出", "减仓", "清仓", "离场", "逃顶",
    ]
    
    _all_keywords_cache: Set[str] = None
    
    @classmethod
    def all_keywords(cls) -> List[str]:
        """Get all keywords from all categories."""
        return (cls.CRYPTO + cls.A_STOCK + cls.US_STOCK + 
                cls.HK_STOCK + cls.FUTURES + cls.FOREX + cls.GENERAL)
    
    @classmethod
    def all_keywords_set(cls) -> Set[str]:
        """Get all keywords as a set for fast lookup."""
        if cls._all_keywords_cache is None:
            cls._all_keywords_cache = {kw.lower() for kw in cls.all_keywords()}
        return cls._all_keywords_cache
    
    @classmethod
    def categorize(cls, text: str) -> List[str]:
        """Return matching market categories for the text."""
        if not text:
            return ["general"]
        
        categories = []
        lower = text.lower()
        
        if any(kw.lower() in lower for kw in cls.CRYPTO):
            categories.append("crypto")
        if any(kw.lower() in lower for kw in cls.A_STOCK):
            categories.append("a_stock")
        if any(kw.lower() in lower for kw in cls.US_STOCK):
            categories.append("us_stock")
        if any(kw.lower() in lower for kw in cls.HK_STOCK):
            categories.append("hk_stock")
        if any(kw.lower() in lower for kw in cls.FUTURES):
            categories.append("futures")
        if any(kw.lower() in lower for kw in cls.FOREX):
            categories.append("forex")
        
        return categories or ["general"]
    
    @classmethod
    def detect_sentiment(cls, text: str) -> str:
        """Detect sentiment: bullish, bearish, or neutral."""
        if not text:
            return "neutral"
        
        lower = text.lower()
        bullish_count = sum(1 for kw in cls.BULLISH_KEYWORDS if kw.lower() in lower)
        bearish_count = sum(1 for kw in cls.BEARISH_KEYWORDS if kw.lower() in lower)
        
        if bullish_count > bearish_count:
            return "bullish"
        elif bearish_count > bullish_count:
            return "bearish"
        return "neutral"
    
    @classmethod
    def extract_matched_keywords(cls, text: str) -> List[str]:
        """Extract all market keywords found in the text."""
        if not text:
            return []
        
        lower = text.lower()
        matched = []
        all_kws = cls.all_keywords_set()
        
        # Check each keyword
        for kw in all_kws:
            if kw in lower:
                matched.append(kw)
        
        return matched[:20]  # Limit to avoid too many
    
    @classmethod
    def is_market_relevant(cls, text: str) -> bool:
        """Check if text contains any market-related keywords."""
        if not text:
            return False
        lower = text.lower()
        return any(kw.lower() in lower for kw in cls.all_keywords())
    
    # ═══════════════════════════════════════════════════════════════
    # 频道分类关键词 / Channel Category Keywords
    # ═══════════════════════════════════════════════════════════════
    
    # 新闻相关 - 需要AI分析
    NEWS_KEYWORDS = [
        "新闻", "快讯", "突发", "头条", "要闻", "速报", "资讯", "早报", "晚报",
        "日报", "周报", "简报", "动态", "热点", "焦点", "独家", "重磅",
        "breaking", "news", "headline", "update", "alert", "report",
        "财经", "金融", "经济", "政策", "监管", "央行", "政府",
    ]
    
    # 技术/VPS相关 - 跳过AI分析
    TECH_KEYWORDS = [
        "vps", "服务器", "server", "云服务", "云主机", "linux", "windows",
        "机场", "节点", "订阅", "v2ray", "trojan", "clash", "shadowsocks", "ss",
        "梯子", "翻墙", "科学上网", "proxy", "vpn",
        "docker", "kubernetes", "k8s", "nginx", "apache",
        "域名", "dns", "cdn", "ssl", "https", "证书",
        "宽带", "带宽", "流量", "ip", "端口",
        "优惠码", "促销", "折扣", "coupon", "promo",
    ]
    
    # 资源分享相关 - 跳过AI分析
    RESOURCE_KEYWORDS = [
        "资源", "分享", "免费", "白嫖", "福利", "羊毛",
        "网盘", "百度云", "阿里云盘", "夸克", "115", "迅雷",
        "下载", "download", "磁力", "种子", "torrent", "bt",
        "破解", "激活", "注册机", "序列号", "crack", "keygen",
        "软件", "工具", "app", "apk", "安装包",
        "教程", "教学", "课程", "视频", "电影", "电视剧", "动漫",
        "账号", "共享", "合租", "车票", "拼车",
        "抽奖", "红包", "返利", "薅羊毛",
    ]
    
    @classmethod
    def detect_channel_category(cls, messages: list) -> str:
        """
        Detect channel category based on message content.
        
        Args:
            messages: List of message texts to analyze
            
        Returns:
            Category string: 'market', 'news', 'tech', 'resource'
        """
        if not messages:
            return "market"  # Default
        
        # Combine messages for analysis (sample up to 50)
        sample = messages[:50]
        combined = " ".join(str(m) for m in sample).lower()
        
        # Count keyword hits for each category
        scores = {
            "market": 0,
            "news": 0,
            "tech": 0,
            "resource": 0,
        }
        
        # Market keywords (use existing)
        for kw in cls.all_keywords():
            if kw.lower() in combined:
                scores["market"] += 1
        
        # News keywords
        for kw in cls.NEWS_KEYWORDS:
            if kw.lower() in combined:
                scores["news"] += 1
        
        # Tech keywords
        for kw in cls.TECH_KEYWORDS:
            if kw.lower() in combined:
                scores["tech"] += 2  # Higher weight
        
        # Resource keywords
        for kw in cls.RESOURCE_KEYWORDS:
            if kw.lower() in combined:
                scores["resource"] += 2  # Higher weight
        
        # Find category with highest score
        max_cat = max(scores, key=scores.get)
        
        # If tech/resource score is significantly higher, use it
        # Otherwise default to market/news (which get AI analysis)
        tech_resource_score = scores["tech"] + scores["resource"]
        market_news_score = scores["market"] + scores["news"]
        
        if tech_resource_score > market_news_score * 1.5:
            # More tech/resource content
            return "tech" if scores["tech"] > scores["resource"] else "resource"
        elif scores["news"] > scores["market"]:
            return "news"
        else:
            return "market"


# Convenience instance
market_keywords = MarketKeywords()

