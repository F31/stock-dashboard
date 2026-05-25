<template>
  <div class="quan-wrap">
    <!-- Header -->
    <div class="quan-hdr">
      <div class="quan-hdr-l">
        <span class="quan-title clickable-title" @click="rulesModal = true"
              title="点击查看规则说明">⚡ 量化分析评分</span>
        <span class="model-badge">FACTOR</span>
        <span v-if="tradeDate" class="date-badge">📅 {{ tradeDate }}</span>
      </div>
      <div class="quan-hdr-r">
        <span v-if="!hasData && !loading" class="no-data-hint">暂无数据，请先运行量化模型</span>
        <input
          v-if="hasData"
          v-model="searchQuery"
          class="search-input"
          placeholder="代码 / 名称搜索..."
          @input="currentPage = 0"
        />
        <button class="refresh-btn" :class="{ spinning: loading }" @click="load" title="刷新">↻</button>
      </div>
    </div>

    <div v-if="loading && !hasData" class="loading-tip">量化数据加载中...</div>

    <template v-else-if="hasData">
      <!-- Chain filter dropdown -->
      <div class="chain-bar">
        <span class="chain-label">产业链</span>
        <div class="chain-select-wrap">
          <select v-model="selectedChainId" class="chain-select" @change="currentPage = 0">
            <option :value="null">全部股票</option>
            <option v-for="c in chainList" :key="c.id" :value="c.id">
              {{ c.name }}（{{ c.count }} 只A股）
            </option>
          </select>
        </div>
        <span v-if="selectedChainId !== null" class="chain-match-tip"
              :title="`产业链 ${chainList.find(c=>c.id===selectedChainId)?.count||0} 只 + 自选股合并去重`">
          命中 {{ filteredActiveScores.length }} 只
        </span>
      </div>

      <!-- Universe tabs (between header and stats) -->
      <div class="universe-tabs h-scroll">
        <button
          v-for="tab in universeTabs" :key="tab.key"
          :class="['utab no-shrink', { active: activeUniverse === tab.key }]"
          @click="activeUniverse = tab.key; currentPage = 0; searchQuery = ''"
        >
          {{ tab.label }}
          <span class="utab-cnt">{{ tab.count }}</span>
        </button>
      </div>

      <!-- Stats row (clickable) -->
      <div class="stats-row">
        <div class="stat-card" @click="showStockList('all')">
          <div class="stat-val c-dark">{{ activeStats.total }}</div>
          <div class="stat-lbl">覆盖股票</div>
        </div>
        <div class="stat-card stat-card--strong" @click="showStockList('strong')">
          <div class="stat-val c-green">{{ activeStats.strongBuy }}</div>
          <div class="stat-lbl">强烈推荐 ≥90</div>
        </div>
        <div class="stat-card stat-card--buy" @click="showStockList('buy')">
          <div class="stat-val c-lime">{{ activeStats.buy }}</div>
          <div class="stat-lbl">推荐 75–90</div>
        </div>
        <div class="stat-card stat-card--neutral" @click="showStockList('neutral')">
          <div class="stat-val c-sky">{{ activeStats.neutral }}</div>
          <div class="stat-lbl">中性 50–75</div>
        </div>
        <div class="stat-card stat-card--avoid" @click="showStockList('avoid')">
          <div class="stat-val c-red">{{ activeStats.avoid }}</div>
          <div class="stat-lbl">回避 &lt;50</div>
        </div>
      </div>

      <!-- Full list (paginated) -->
      <div class="section">
        <div class="section-hdr">
          <span class="section-title">🏆 {{ activeUniverse === 'star50' ? '科创50' : '沪深300' }}全量评分</span>
          <span class="section-sub">{{ filteredActiveScores.length }} 只符合条件</span>
          <div class="page-nav" v-if="totalPages > 1">
            <button class="page-btn" :disabled="currentPage === 0" @click="currentPage--">‹</button>
            <span class="page-info">{{ currentPage + 1 }}/{{ totalPages }}</span>
            <button class="page-btn" :disabled="currentPage >= totalPages - 1" @click="currentPage++">›</button>
          </div>
        </div>
        <div class="tbl-head">
          <span>排名</span><span>代码 / 名称</span><span>行业</span>
          <span>股价 / 涨跌</span><span>百分位</span><span>评级</span>
        </div>
        <div v-for="row in pagedScores" :key="row.stock_code"
             class="tbl-row" :class="labelCls(row.label)" @click="openDetail(row)" style="cursor:pointer">
          <span class="rank-num">#{{ row.rank }}</span>
          <div class="code-col">
            <span class="code-text">{{ row.stock_code }}</span>
            <span class="name-text">{{ row.stock_name || '—' }}</span>
          </div>
          <span class="industry-col" :title="row.industry || ''">{{ row.industry || '—' }}</span>
          <div class="price-col">
            <span class="price-val">{{ row.price != null ? row.price.toFixed(2) : '—' }}</span>
            <span :class="['chg-val', chgCls(row.change_pct)]">{{ fmtChg(row.change_pct) }}</span>
          </div>
          <div class="pct-col">
            <div class="pct-bar-wrap">
              <div class="pct-bar" :class="barCls(row.percentile_score)"
                   :style="{ width: row.percentile_score + '%' }"></div>
            </div>
            <span class="pct-val">{{ row.percentile_score.toFixed(1) }}</span>
          </div>
          <div class="label-col">
            <span :class="['label-tag', labelCls(row.label)]">{{ row.label }}</span>
            <span v-if="row.opportunity_tag === '成长窗口'"
                  :class="['opp-tag', row.stock_code?.startsWith('688') ? 'opp-tag--star' : '']"
                  :title="oppTagTip(row)">
              {{ row.stock_code?.startsWith('688') ? '⚡ 科创成长' : '⚡ 成长窗口' }}
            </span>
            <span v-if="row.sector_warning" :class="['warn-tag', warnCls(row.sector_warning)]"
                  :title="warnTip(row.sector_warning)">
              {{ row.sector_warning === '板块拥挤' ? '⚠ 拥挤' : '🔥 过热' }}
            </span>
          </div>
        </div>
        <div v-if="filteredActiveScores.length === 0" class="empty-tip">
          {{ searchQuery ? '无匹配结果' : '暂无数据' }}
        </div>
      </div>
    </template>

    <!-- Rules explanation modal -->
    <Teleport to="body">
      <div v-if="rulesModal" class="modal-overlay" @click.self="rulesModal = false">
        <div class="modal rules-modal">
          <div class="modal-hdr">
            <span class="modal-title">📊 量化分析规则说明</span>
            <a href="/quan-rules.html" target="_blank" class="rules-ext-link" title="在新标签页打开">↗ 独立页面</a>
            <button class="close-btn" @click="rulesModal = false">×</button>
          </div>
          <div class="rules-iframe-wrap">
            <iframe src="/quan-rules.html" class="rules-iframe" title="量化分析规则说明"></iframe>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Stock list modal (white card style matching dashboard) -->
    <Teleport to="body">
      <div v-if="listModal.show" class="modal-overlay" @click.self="listModal.show = false">
        <div class="modal">
          <div class="modal-hdr">
            <span class="modal-title">{{ listModal.title }}</span>
            <input v-model="modalSearch" class="modal-search" placeholder="搜索..." />
            <button class="close-btn" @click="listModal.show = false">×</button>
          </div>
          <div class="modal-body">
            <div class="tbl-head modal-tbl-head">
              <span>排名</span><span>代码 / 名称</span><span>行业</span>
              <span>股价 / 涨跌</span><span>百分位</span><span>评级</span>
            </div>
            <div v-for="row in filteredModalStocks" :key="row.stock_code"
                 class="tbl-row modal-tbl-row" :class="labelCls(row.label)" @click="openDetail(row)" style="cursor:pointer">
              <span class="rank-num">#{{ row.rank }}</span>
              <div class="code-col">
                <span class="code-text code-text--dark">{{ row.stock_code }}</span>
                <span class="name-text name-text--dark">{{ row.stock_name || '—' }}</span>
              </div>
              <span class="industry-col industry-col--dark" :title="row.industry || ''">{{ row.industry || '—' }}</span>
              <div class="price-col">
                <span class="price-val">{{ row.price != null ? row.price.toFixed(2) : '—' }}</span>
                <span :class="['chg-val', chgCls(row.change_pct)]">{{ fmtChg(row.change_pct) }}</span>
              </div>
              <div class="pct-col">
                <div class="pct-bar-wrap">
                  <div class="pct-bar" :class="barCls(row.percentile_score)"
                       :style="{ width: row.percentile_score + '%' }"></div>
                </div>
                <span class="pct-val pct-val--dark">{{ row.percentile_score.toFixed(1) }}</span>
              </div>
              <div class="label-col">
                <span :class="['label-tag', labelCls(row.label)]">{{ row.label }}</span>
                <span v-if="row.opportunity_tag === '成长窗口'"
                      :class="['opp-tag', row.stock_code?.startsWith('688') ? 'opp-tag--star' : '']"
                      :title="oppTagTip(row)">
                  {{ row.stock_code?.startsWith('688') ? '⚡ 科创成长' : '⚡ 成长窗口' }}
                </span>
                <span v-if="row.sector_warning" :class="['warn-tag', warnCls(row.sector_warning)]"
                      :title="warnTip(row.sector_warning)">
                  {{ row.sector_warning === '板块拥挤' ? '⚠ 拥挤' : '🔥 过热' }}
                </span>
              </div>
            </div>
            <div v-if="filteredModalStocks.length === 0" class="empty-tip empty-tip--dark">无匹配结果</div>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Stock detail / buy-sell levels modal -->
    <Teleport to="body">
      <div v-if="detailModal.show" class="modal-overlay" @click.self="detailModal.show = false">
        <div class="modal detail-modal">
          <div class="modal-hdr">
            <div class="detail-hdr-info">
              <span class="detail-name">{{ detailModal.stock?.stock_name || detailModal.stock?.stock_code }}</span>
              <span class="detail-code">{{ detailModal.stock?.stock_code }}</span>
              <span v-if="detailModal.stock?.label" :class="['label-tag', labelCls(detailModal.stock.label)]">
                {{ detailModal.stock.label }}
              </span>
              <span v-if="detailModal.stock?.opportunity_tag === '成长窗口'"
                    :class="['opp-tag', detailModal.stock?.stock_code?.startsWith('688') ? 'opp-tag--star' : '']"
                    :title="oppTagTip(detailModal.stock)">
                {{ detailModal.stock?.stock_code?.startsWith('688') ? '⚡ 科创成长' : '⚡ 成长窗口' }}
              </span>
              <span v-if="detailModal.stock?.sector_warning"
                    :class="['warn-tag', warnCls(detailModal.stock.sector_warning)]">
                {{ detailModal.stock.sector_warning === '板块拥挤' ? '⚠ 拥挤' : '🔥 过热' }}
              </span>
            </div>
            <button class="close-btn" @click="detailModal.show = false">×</button>
          </div>

          <div class="modal-body detail-body">
            <!-- Factor score breakdown (always shown when stock data available) -->
            <div v-if="detailModal.stock && (detailModal.stock.growth_score || detailModal.stock.quality_score || detailModal.stock.valuation_score || detailModal.stock.momentum_score)"
                 class="factor-breakdown">
              <div class="detail-sec-title">因子得分 <span class="fb-total">综合 {{ detailModal.stock.percentile_score?.toFixed(0) }} 分</span></div>
              <div class="fb-bars">
                <template v-for="f in [
                  { key: 'growth_score',    label: '成长', w: 35, tip: '利润/营收YoY增速 + 加速度 + Capex周期 + 业绩超预期（含10%超预期权重）' },
                  { key: 'quality_score',   label: '质量', w: 22, tip: 'ROE / 毛利率 / 现金利润率' },
                  { key: 'valuation_score', label: '估值', w: 20, tip: 'PEG + 行业相对PE；PE>150且营收增长时用PB/ROE前瞻PE替代TTM PE；科创板早期成长期TTM PE结构性偏高' },
                  { key: 'momentum_score',  label: '动量', w: 13, tip: 'Alpha158多周期趋势+量价确认' },
                  { key: 'sentiment_score', label: '情绪', w: 10, tip: '换手率异动（成交量/MA20）× 60% + 成交额截面排名 × 40%' },
                ]" :key="f.key">
                  <div class="fb-row">
                    <span class="fb-label" :title="f.tip">
                      {{ f.label }}
                      <span class="fb-weight">×{{ f.w }}%</span>
                    </span>
                    <div class="fb-bar-bg">
                      <div :class="['fb-bar-fill', fbCls(detailModal.stock[f.key])]"
                           :style="{ width: (detailModal.stock[f.key] || 0) + '%' }"></div>
                    </div>
                    <span :class="['fb-val', fbCls(detailModal.stock[f.key])]">
                      {{ detailModal.stock[f.key]?.toFixed(0) ?? '—' }}
                    </span>
                  </div>
                  <!-- Surprise sub-row: indented under growth (it's 10% of growth weight) -->
                  <div v-if="f.key === 'growth_score' && detailModal.stock?.surprise_score != null"
                       class="fb-subrow"
                       title="业绩超预期子项：实际增速 vs 历史趋势预测 + 业绩预告事件（预增/扭亏加分）。在成长因子内占10%权重。">
                    <span class="fb-sublabel">└ 超预期</span>
                    <div class="fb-bar-bg">
                      <div :class="['fb-bar-fill', fbCls(detailModal.stock.surprise_score)]"
                           :style="{ width: (detailModal.stock.surprise_score || 0) + '%' }"></div>
                    </div>
                    <span :class="['fb-val', 'fb-subval', fbCls(detailModal.stock.surprise_score)]">
                      {{ detailModal.stock.surprise_score?.toFixed(0) }}
                    </span>
                  </div>
                  <!-- Valuation suppression note: 科创板 high-PE structural warning -->
                  <div v-if="f.key === 'valuation_score'
                             && detailModal.stock?.valuation_score < 25
                             && detailModal.stock?.stock_code?.startsWith('688')"
                       class="fb-val-note">
                    ↑ 科创板早期成长期TTM PE偏高·已用PB/ROE前瞻PE参与估值
                  </div>
                  <!-- Valuation suppression note: non-科创板 high PE -->
                  <div v-else-if="f.key === 'valuation_score'
                                  && detailModal.stock?.valuation_score < 20
                                  && !detailModal.stock?.stock_code?.startsWith('688')"
                       class="fb-val-note">
                    ↑ PE偏高，估值分受抑·若处于困境反转期可参考动量和超预期信号
                  </div>
                </template>
              </div>
            </div>

            <!-- Loading -->
            <div v-if="detailModal.loading" class="detail-state">
              <div class="detail-spinner"></div>
              <span>正在获取技术指标（首次约5秒，已缓存1小时）…</span>
            </div>

            <!-- Error -->
            <div v-else-if="detailModal.error" class="detail-state detail-err">
              {{ detailModal.error }}
            </div>

            <template v-else-if="detailModal.levels">
              <!-- Quote strip -->
              <div class="detail-quote">
                <div class="dq-item">
                  <span class="dq-val" :class="chgCls(detailModal.levels.change_pct)">
                    {{ detailModal.levels.price?.toFixed(2) ?? '—' }}
                  </span>
                  <span class="dq-lbl">当前价</span>
                </div>
                <div class="dq-item">
                  <span class="dq-val" :class="chgCls(detailModal.levels.change_pct)">
                    {{ fmtChg(detailModal.levels.change_pct) }}
                  </span>
                  <span class="dq-lbl">涨跌幅</span>
                </div>
                <div class="dq-item" v-if="detailModal.levels.pe">
                  <span class="dq-val">{{ detailModal.levels.pe?.toFixed(1) }}x</span>
                  <span class="dq-lbl">动态PE</span>
                </div>
                <div class="dq-item" v-if="detailModal.levels.pb">
                  <span class="dq-val">{{ detailModal.levels.pb?.toFixed(2) }}x</span>
                  <span class="dq-lbl">PB</span>
                </div>
                <div class="dq-item" v-if="detailModal.levels.mktcap">
                  <span class="dq-val">{{ detailModal.levels.mktcap?.toFixed(0) }}亿</span>
                  <span class="dq-lbl">市值</span>
                </div>
                <div class="dq-item" v-if="detailModal.levels.fundamentals?.profit_yoy != null">
                  <span class="dq-val" :class="detailModal.levels.fundamentals.profit_yoy >= 0 ? 'c-up' : 'c-dn'">
                    {{ (detailModal.levels.fundamentals.profit_yoy >= 0 ? '+' : '') + detailModal.levels.fundamentals.profit_yoy?.toFixed(1) + '%' }}
                  </span>
                  <span class="dq-lbl">净利润同比</span>
                </div>
              </div>

              <!-- Sector valuation comparison -->
              <template v-if="detailModal.levels.sector_valuation?.peer_count >= 3">
                <div class="detail-sec-title">
                  板块估值对比
                  <span class="fund-period">{{ detailModal.levels.sector_valuation.industry }} · {{ detailModal.levels.sector_valuation.peer_count }} 只同业</span>
                </div>
                <div class="sector-val-row">
                  <div class="sv-item">
                    <span class="sv-val">{{ detailModal.levels.sector_valuation.stock_pe?.toFixed(1) ?? '—' }}x</span>
                    <span class="sv-lbl">本股PE</span>
                  </div>
                  <div class="sv-divider">vs</div>
                  <div class="sv-item">
                    <span class="sv-val">{{ detailModal.levels.sector_valuation.sector_median_pe?.toFixed(1) }}x</span>
                    <span class="sv-lbl">行业中位PE</span>
                  </div>
                  <div class="sv-item">
                    <span class="sv-val">{{ detailModal.levels.sector_valuation.sector_mean_pe?.toFixed(1) }}x</span>
                    <span class="sv-lbl">行业平均PE</span>
                  </div>
                  <div class="sv-verdict" :class="`sv-${detailModal.levels.sector_valuation.verdict_level}`"
                       v-if="detailModal.levels.sector_valuation.verdict">
                    <span class="sv-prem">
                      {{ detailModal.levels.sector_valuation.pe_premium_pct >= 0 ? '+' : '' }}{{ detailModal.levels.sector_valuation.pe_premium_pct }}%
                    </span>
                    <span class="sv-tag">{{ detailModal.levels.sector_valuation.verdict }}</span>
                  </div>
                </div>
              </template>

              <!-- Sentiment bar -->
              <div class="detail-sentiment" :class="`senti-${detailModal.levels.sentiment_level}`">
                <span class="senti-icon">
                  {{ detailModal.levels.sentiment_level === 'warn' ? '⚠️' :
                     detailModal.levels.sentiment_level === 'buy'  ? '✅' : '⏳' }}
                </span>
                <span class="senti-text">{{ detailModal.levels.sentiment }}</span>
                <span class="senti-sub">
                  RSI {{ detailModal.levels.rsi14 }} · {{ detailModal.levels.rsi_tag }} &nbsp;|&nbsp; ATR {{ detailModal.levels.atr14 }} 元/日
                </span>
              </div>

              <!-- MA grid -->
              <div class="detail-sec-title">
                均线位置
                <span v-if="detailModal.levels.ma?.ma60 == null" class="fund-period" title="上市时间较短，60/120日均线暂无数据">（上市较短，长期均线暂缺）</span>
              </div>
              <div class="ma-grid">
                <div v-for="(val, key) in detailModal.levels.ma" :key="key"
                     v-if="val != null" class="ma-item">
                  <div class="ma-row">
                    <span class="ma-name">{{ key.toUpperCase() }}</span>
                    <span class="ma-val">{{ val?.toFixed(2) }}</span>
                    <span :class="['ma-dev', maPct(val) >= 0 ? 'dev-above' : 'dev-below']">
                      {{ (maPct(val) >= 0 ? '+' : '') + maPct(val) }}%
                    </span>
                  </div>
                  <div class="ma-bar-bg">
                    <div class="ma-bar-fill" :class="maBarCls(maPct(val))"
                         :style="{ width: Math.min(Math.abs(maPct(val)) * 3, 100) + '%' }"></div>
                  </div>
                </div>
              </div>

              <!-- Buy zones -->
              <div class="detail-sec-title">买入区间参考</div>
              <div v-if="!detailModal.levels.buy_zones?.length" class="detail-state" style="padding:8px 0;font-size:0.8em;">数据不足，无法计算买入区间</div>
              <div class="zones-list">
                <div v-for="z in detailModal.levels.buy_zones" :key="z.tier"
                     class="zone-card" :class="`zone-t${z.tier}`">
                  <div class="zone-hdr">
                    <span class="zone-num">{{ ['①','②','③'][z.tier-1] }}</span>
                    <span class="zone-label">{{ z.label }}</span>
                    <span class="zone-range">{{ z.low?.toFixed(2) }} ~ {{ z.high?.toFixed(2) }}</span>
                  </div>
                  <div class="zone-detail">{{ z.basis }} · <em>{{ z.note }}</em></div>
                </div>
              </div>

              <!-- Targets & Stop in 2 cols -->
              <div class="ts-row">
                <div class="ts-col">
                  <div class="detail-sec-title">目标价</div>
                  <div v-for="t in detailModal.levels.targets" :key="t.tier" class="ts-item target-item">
                    <span class="ts-num">{{ ['①','②'][t.tier-1] }}</span>
                    <span class="ts-price target-price">{{ t.price?.toFixed(2) }}</span>
                    <span class="ts-basis">{{ t.basis }}</span>
                  </div>
                </div>
                <div class="ts-col">
                  <div class="detail-sec-title">止损线</div>
                  <div v-for="s in detailModal.levels.stop_loss" :key="s.label" class="ts-item stop-item">
                    <span class="ts-num stop-dot">·</span>
                    <span class="ts-price stop-price">{{ s.price?.toFixed(2) }}</span>
                    <span class="ts-basis">{{ s.basis }}</span>
                  </div>
                </div>
              </div>

              <!-- Fundamentals -->
              <template v-if="detailModal.levels.fundamentals && Object.keys(detailModal.levels.fundamentals).length > 1">
                <div class="detail-sec-title">
                  基本面
                  <span v-if="detailModal.levels.fundamentals.report_date" class="fund-period">
                    {{ detailModal.levels.fundamentals.report_date }}
                  </span>
                </div>
                <div class="fund-grid">
                  <div class="fund-item" v-if="detailModal.levels.fundamentals.profit_yoy != null">
                    <span class="fund-val" :class="detailModal.levels.fundamentals.profit_yoy >= 0 ? 'c-up' : 'c-dn'">
                      {{ (detailModal.levels.fundamentals.profit_yoy >= 0 ? '+' : '') + detailModal.levels.fundamentals.profit_yoy?.toFixed(1) + '%' }}
                    </span>
                    <span class="fund-lbl">净利润同比</span>
                  </div>
                  <div class="fund-item" v-if="detailModal.levels.fundamentals.revenue_yoy != null">
                    <span class="fund-val" :class="detailModal.levels.fundamentals.revenue_yoy >= 0 ? 'c-up' : 'c-dn'">
                      {{ (detailModal.levels.fundamentals.revenue_yoy >= 0 ? '+' : '') + detailModal.levels.fundamentals.revenue_yoy?.toFixed(1) + '%' }}
                    </span>
                    <span class="fund-lbl">营收同比</span>
                  </div>
                  <div class="fund-item" v-if="detailModal.levels.fundamentals.roe != null">
                    <span class="fund-val">{{ detailModal.levels.fundamentals.roe?.toFixed(2) + '%' }}</span>
                    <span class="fund-lbl">ROE</span>
                  </div>
                  <div class="fund-item" v-if="detailModal.levels.fundamentals.gross_margin != null">
                    <span class="fund-val">{{ detailModal.levels.fundamentals.gross_margin?.toFixed(1) + '%' }}</span>
                    <span class="fund-lbl">毛利率</span>
                  </div>
                  <div class="fund-item" v-if="detailModal.levels.fundamentals.cash_profit_ratio != null">
                    <span class="fund-val" :class="detailModal.levels.fundamentals.cash_profit_ratio >= 0 ? '' : 'c-dn'">
                      {{ detailModal.levels.fundamentals.cash_profit_ratio?.toFixed(1) + '%' }}
                    </span>
                    <span class="fund-lbl">TTM现金利润率</span>
                  </div>
                </div>
              </template>

              <div class="detail-disclaimer">以上建议基于量化模型计算，不构成投资建议，仅供参考。</div>
            </template>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { fetchQuanScores, fetchQuanChainFilters, fetchQuanStockLevels } from '../api/index.js'

const props = defineProps({
  watchlistCodes:  { type: Array, default: () => [] },
  watchlistStocks: { type: Array, default: () => [] },
})

const PAGE_SIZE = 30

const tradeDate      = ref(null)
const allScores      = ref([])
const star50Scores   = ref([])
const loading        = ref(false)
const searchQuery    = ref('')
const currentPage    = ref(0)
const activeUniverse = ref('csi300')
const modalSearch    = ref('')
const listModal      = ref({ show: false, title: '', stocks: [] })
const rulesModal     = ref(false)
const detailModal    = ref({ show: false, stock: null, levels: null, loading: false, error: null })

// Chain filter
const chainList      = ref([])   // [{id, name, count, codes: []}]
const selectedChainId = ref(null) // null = show all

const watchMap = computed(() => {
  const m = {}
  for (const s of props.watchlistStocks) {
    if (s.stock_code && s.data) m[s.stock_code] = s.data
  }
  return m
})

function enrich(rows) {
  return rows.map((r, i) => {
    const live = watchMap.value[r.stock_code]
    return {
      ...r,
      rank:       r.rank ?? i + 1,
      stock_name: r.stock_name || live?.stock_name || '',
      industry:   r.industry || '',
      price:      r.price      ?? live?.price      ?? null,
      change_pct: r.change_pct ?? live?.change_pct ?? null,
    }
  })
}

const hasData = computed(() => allScores.value.length > 0)

const activeScores = computed(() =>
  enrich(activeUniverse.value === 'star50' ? star50Scores.value : allScores.value)
)

// Set of A-share codes for the current filter = chain codes ∪ watchlist codes (deduped).
// Returns null when "全部" is selected (no filter applied).
const chainCodeSet = computed(() => {
  const watchlistSet = new Set(props.watchlistCodes)
  if (selectedChainId.value === null) {
    // "全部" — but if there's a watchlist, still show all; return null = no filter
    return null
  }
  const chain = chainList.value.find(c => c.id === selectedChainId.value)
  const chainCodes = chain ? chain.codes : []
  // Union: chain stocks + all watchlist stocks, deduplicated
  return new Set([...chainCodes, ...watchlistSet])
})

const filteredActiveScores = computed(() => {
  let rows = activeScores.value
  // Chain filter first
  if (chainCodeSet.value) {
    rows = rows.filter(r => chainCodeSet.value.has(r.stock_code))
  }
  // Then text search
  const q = searchQuery.value.trim().toLowerCase()
  if (q) {
    rows = rows.filter(r =>
      r.stock_code.includes(q) || r.stock_name.toLowerCase().includes(q)
    )
  }
  return rows
})

const totalPages = computed(() =>
  Math.max(1, Math.ceil(filteredActiveScores.value.length / PAGE_SIZE))
)
const pagedScores = computed(() =>
  filteredActiveScores.value.slice(currentPage.value * PAGE_SIZE, (currentPage.value + 1) * PAGE_SIZE)
)

const activeStats = computed(() => {
  const src = activeScores.value
  return {
    total:     src.length,
    strongBuy: src.filter(r => r.percentile_score >= 90).length,
    buy:       src.filter(r => r.percentile_score >= 75 && r.percentile_score < 90).length,
    neutral:   src.filter(r => r.percentile_score >= 50 && r.percentile_score < 75).length,
    avoid:     src.filter(r => r.percentile_score < 50).length,
  }
})

const universeTabs = computed(() => [
  { key: 'csi300', label: '沪深300', count: allScores.value.length },
  { key: 'star50', label: '科创50',  count: star50Scores.value.length },
])

const filteredModalStocks = computed(() => {
  const q = modalSearch.value.trim().toLowerCase()
  if (!q) return listModal.value.stocks
  return listModal.value.stocks.filter(r =>
    r.stock_code.includes(q) || (r.stock_name || '').toLowerCase().includes(q)
  )
})

function showStockList(kind) {
  const src = activeScores.value
  modalSearch.value = ''
  let stocks, title
  if (kind === 'all')     { stocks = src; title = '全部覆盖股票' }
  else if (kind === 'strong') { stocks = src.filter(r => r.percentile_score >= 90); title = '强烈推荐 (≥90)' }
  else if (kind === 'buy')    { stocks = src.filter(r => r.percentile_score >= 75 && r.percentile_score < 90); title = '推荐 (75–90)' }
  else if (kind === 'neutral'){ stocks = src.filter(r => r.percentile_score >= 50 && r.percentile_score < 75); title = '中性 (50–75)' }
  else                        { stocks = src.filter(r => r.percentile_score < 50); title = '回避 (<50)' }
  listModal.value = { show: true, title, stocks }
}

function labelCls(label) {
  if (label === '强烈推荐') return 'lbl-strong'
  if (label === '推荐')     return 'lbl-buy'
  if (label === '中性')     return 'lbl-neutral'
  return 'lbl-avoid'
}
function barCls(pct) {
  if (pct >= 90) return 'bar-strong'
  if (pct >= 75) return 'bar-buy'
  if (pct >= 50) return 'bar-neutral'
  return 'bar-avoid'
}
function warnCls(w)  { return w === '板块拥挤' ? 'warn-crowded' : 'warn-hot' }
function warnTip(w)  {
  if (w === '板块拥挤') return '该股3月涨幅远超行业均值（>3×），且行业整体已过热，追高风险高'
  if (w === '板块过热') return '所属行业3月平均涨幅>50%或趋势强度过高，板块整体处于过热区间'
  return ''
}
function chgCls(v) { return v == null ? '' : v >= 0 ? 'c-up' : 'c-dn' }
function fmtChg(v) {
  if (v == null) return '—'
  return (v >= 0 ? '+' : '') + v.toFixed(2) + '%'
}

// ── Detail modal helpers ────────────────────────────────────────────────────
function fbCls(v) {
  if (v == null) return ''
  if (v >= 75) return 'fb-high'
  if (v >= 50) return 'fb-mid'
  return 'fb-low'
}
function maPct(val) {
  const price = detailModal.value.levels?.price
  if (!price || !val) return 0
  return Math.round((price - val) / val * 1000) / 10   // 1 decimal
}
function maBarCls(pct) {
  if (pct > 20) return 'bar-far-above'
  if (pct > 5)  return 'bar-above'
  if (pct > -5) return 'bar-near'
  return 'bar-below'
}

async function openDetail(row) {
  detailModal.value = { show: true, stock: row, levels: null, loading: true, error: null }
  try {
    const res = await fetchQuanStockLevels(row.stock_code)
    if (res.data?.error) {
      detailModal.value.error = res.data.error
    } else {
      detailModal.value.levels = res.data
    }
  } catch (err) {
    const isTimeout = err?.code === 'ECONNABORTED' || err?.message?.includes('timeout')
    detailModal.value.error = isTimeout
      ? '技术指标获取超时，请稍候重试'
      : '获取数据失败，请检查网络后重试'
  } finally {
    detailModal.value.loading = false
  }
}

async function loadChains() {
  try {
    const res = await fetchQuanChainFilters()
    chainList.value = res.data.chains || []
    // Auto-select the active framework (defaults to "AI产业链")
    if (selectedChainId.value === null) {
      const active = chainList.value.find(c => c.is_active)
      if (active) selectedChainId.value = active.id
    }
  } catch {
    chainList.value = []
  }
}

async function load() {
  loading.value = true
  try {
    const [res, resStar] = await Promise.all([
      fetchQuanScores({ model: 'factor', min_percentile: 0 }),
      fetchQuanScores({ model: 'factor_star50', min_percentile: 0 }),
    ])
    tradeDate.value    = res.data.trade_date
    allScores.value    = (res.data.scores    || []).map((r, i) => ({ ...r, rank: i + 1 }))
    star50Scores.value = (resStar.data.scores || []).map((r, i) => ({ ...r, rank: i + 1 }))
  } catch {
    allScores.value = []
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  load()
  loadChains()
})

function oppTagTip(row) {
  if (row?.stock_code?.startsWith('688')) {
    return '科创板成长窗口：TTM PE偏高属早期成长期结构性特征，系统已用PB/ROE前瞻PE参与估值评分。超预期+动量信号显著，关注后续季度营收兑现。（科创板专项宽松标准：综合分<68、超预期>55、营收增速>5%）'
  }
  return '成长动能强但估值偏高：超预期信号+营收加速。综合评分受高估值拖累，但成长催化因子显著，关注后续季度业绩兑现情况。'
}
</script>

<style scoped>
.quan-wrap {
  display: flex; flex-direction: column; gap: 16px;
  padding: 0 0 28px; color: #1f2937;
}

/* ── Header ── */
.quan-hdr {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 18px 12px;
  border-bottom: 1px solid #e5e7eb;
  background: #fff;
}
.quan-hdr-l { display: flex; align-items: center; gap: 10px; }
.quan-title  { font-size: 0.92em; font-weight: 800; color: #111827; letter-spacing: .4px; }
.clickable-title {
  cursor: pointer; border-bottom: 1px dashed #a5b4fc;
  transition: color 0.15s;
}
.clickable-title:hover { color: #4f46e5; }
.model-badge {
  font-size: 0.67em; background: #eff6ff; color: #2563eb;
  border: 1px solid #bfdbfe; border-radius: 6px; padding: 2px 8px; font-weight: 700;
}
.date-badge {
  font-size: 0.7em; color: #6b7280;
  background: #f3f4f6; border-radius: 6px; padding: 2px 8px;
}
.quan-hdr-r { display: flex; align-items: center; gap: 8px; }
.no-data-hint { font-size: 0.72em; color: #9ca3af; }
.search-input {
  background: #fff; border: 1px solid #d1d5db;
  border-radius: 7px; color: #374151; font-size: 0.78em;
  padding: 5px 12px; width: 160px; outline: none; transition: border-color 0.15s;
}
.search-input::placeholder { color: #9ca3af; }
.search-input:focus { border-color: #6366f1; }
.refresh-btn {
  background: #f3f4f6; border: 1px solid #d1d5db;
  color: #374151; border-radius: 7px; padding: 4px 12px; cursor: pointer;
  font-size: 15px; transition: background 0.15s;
}
.refresh-btn:hover { background: #e5e7eb; }
.refresh-btn.spinning { animation: spin 0.7s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.loading-tip { text-align: center; color: #9ca3af; font-size: 0.82em; padding: 48px; }

/* ── Chain filter bar ── */
.chain-bar {
  display: flex; align-items: center; gap: 10px;
  padding: 0 18px;
}
.chain-label {
  font-size: 0.75em; font-weight: 700; color: #374151;
  white-space: nowrap;
}
.chain-select-wrap {
  position: relative; display: flex; align-items: center;
}
.chain-select-wrap::after {
  content: '▾'; position: absolute; right: 10px; top: 50%;
  transform: translateY(-50%); pointer-events: none;
  font-size: 0.72em; color: #6b7280;
}
.chain-select {
  appearance: none; -webkit-appearance: none;
  background: #fff; border: 1px solid #d1d5db;
  border-radius: 8px; color: #374151; font-size: 0.78em;
  padding: 5px 30px 5px 12px; cursor: pointer;
  outline: none; min-width: 180px;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.chain-select:focus { border-color: #6366f1; box-shadow: 0 0 0 2px #e0e7ff; }
.chain-match-tip {
  font-size: 0.70em; color: #2563eb;
  background: #eff6ff; border: 1px solid #bfdbfe;
  border-radius: 6px; padding: 2px 8px; white-space: nowrap;
}

/* ── Universe tabs ── */
.universe-tabs {
  display: flex; gap: 6px; padding: 0 18px;
}
.utab {
  background: #f9fafb; border: 1px solid #e5e7eb;
  border-radius: 8px; color: #374151; font-size: 0.78em; font-weight: 600;
  padding: 6px 16px; cursor: pointer; display: flex; align-items: center; gap: 6px;
  transition: all 0.15s;
}
.utab:hover { background: #f3f4f6; }
.utab.active {
  background: #eff6ff; border-color: #bfdbfe; color: #2563eb;
}
.utab-cnt {
  font-size: 0.85em; background: #e5e7eb;
  border-radius: 10px; padding: 1px 7px; color: #6b7280;
}
.utab.active .utab-cnt { background: #dbeafe; color: #1d4ed8; }

/* ── Stats ── */
.stats-row { display: flex; gap: 10px; padding: 0 18px; flex-wrap: wrap; }
.stat-card {
  flex: 1; min-width: 72px; text-align: center;
  background: #fff; border: 1px solid #e5e7eb;
  border-radius: 12px; padding: 12px 8px;
  cursor: pointer; transition: background 0.15s, transform 0.1s, box-shadow 0.15s;
}
.stat-card:hover { background: #f9fafb; transform: translateY(-1px); box-shadow: 0 2px 8px rgba(0,0,0,.06); }
.stat-val       { font-size: 1.6em; font-weight: 800; line-height: 1; margin-bottom: 4px; }
.stat-val.c-dark  { color: #111827; }
.stat-val.c-green { color: #16a34a; }
.stat-val.c-lime  { color: #65a30d; }
.stat-val.c-sky   { color: #0284c7; }
.stat-val.c-red   { color: #dc2626; }
.stat-lbl         { font-size: 0.61em; color: #6b7280; }

/* ── Section ── */
.section { padding: 0 18px; }
.section-hdr { display: flex; align-items: baseline; gap: 10px; margin-bottom: 10px; flex-wrap: wrap; }
.section-title { font-size: 0.83em; font-weight: 700; color: #374151; }
.section-sub   { font-size: 0.67em; color: #9ca3af; }
.page-nav { display: flex; align-items: center; gap: 6px; margin-left: auto; }
.page-btn {
  background: #f3f4f6; border: 1px solid #e5e7eb;
  color: #374151; border-radius: 6px; padding: 2px 8px; cursor: pointer; font-size: 0.85em;
}
.page-btn:hover:not(:disabled) { background: #e5e7eb; }
.page-btn:disabled { opacity: 0.35; cursor: default; }
.page-info { font-size: 0.7em; color: #9ca3af; }
.empty-tip { text-align: center; color: #9ca3af; font-size: 0.8em; padding: 24px; }

/* ── Table ── */
.tbl-head {
  display: grid;
  grid-template-columns: 44px 160px 100px 100px 1fr 120px;
  font-size: 0.63em; color: #6b7280;
  padding: 3px 10px 5px; font-weight: 600; letter-spacing: .3px;
  border-bottom: 1px solid #e5e7eb; margin-bottom: 4px;
}
.tbl-row {
  display: grid;
  grid-template-columns: 44px 160px 100px 100px 1fr 120px;
  align-items: center;
  padding: 7px 10px; border-radius: 8px;
  background: #f9fafb;
  border-left: 3px solid transparent;
  margin-bottom: 3px; transition: background 0.12s;
}
.tbl-row:hover { background: #f3f4f6; }
.tbl-row.lbl-strong { border-left-color: #16a34a; background: #f0fdf4; }
.tbl-row.lbl-buy    { border-left-color: #65a30d; background: #f7fee7; }
.tbl-row.lbl-neutral{ border-left-color: #2563eb; background: #eff6ff; }
.tbl-row.lbl-avoid  { border-left-color: #dc2626; background: #fef2f2; }
.tbl-row.lbl-strong:hover { background: #dcfce7; }
.tbl-row.lbl-buy:hover    { background: #ecfccb; }
.tbl-row.lbl-neutral:hover{ background: #dbeafe; }
.tbl-row.lbl-avoid:hover  { background: #fee2e2; }

.rank-num    { font-size: 0.75em; color: #9ca3af; font-weight: 700; }
.code-col    { display: flex; flex-direction: column; gap: 2px; overflow: hidden; }
.code-text   { font-size: 0.8em; font-weight: 700; color: #111827; font-family: monospace; }
.name-text   { font-size: 0.68em; color: #374151; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.industry-col {
  font-size: 0.68em; color: #6b7280;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  cursor: default;
}
.price-col   { display: flex; flex-direction: column; gap: 2px; }
.price-val   { font-size: 0.82em; font-weight: 600; color: #111827; }
.chg-val     { font-size: 0.72em; font-weight: 700; }
.c-up        { color: #dc2626; }
.c-dn        { color: #16a34a; }
.pct-col     { display: flex; align-items: center; gap: 7px; }
.pct-bar-wrap{ flex: 1; height: 7px; background: #e5e7eb; border-radius: 4px; overflow: hidden; min-width: 40px; }
.pct-bar     { height: 100%; border-radius: 4px; transition: width 0.4s ease; }
.pct-val     { font-size: 0.77em; color: #111827; min-width: 36px; text-align: right; font-weight: 700; }
.bar-strong  { background: linear-gradient(90deg, #16a34a, #4ade80); }
.bar-buy     { background: linear-gradient(90deg, #65a30d, #a3e635); }
.bar-neutral { background: linear-gradient(90deg, #2563eb, #60a5fa); }
.bar-avoid   { background: linear-gradient(90deg, #dc2626, #f87171); }
.label-col   { display: flex; align-items: center; flex-wrap: wrap; gap: 4px; }
.label-tag {
  font-size: 0.71em; font-weight: 700; border-radius: 6px; padding: 2px 8px; white-space: nowrap;
}
.label-tag.lbl-strong { background: #dcfce7; color: #15803d; border: 1px solid #86efac; }
.label-tag.lbl-buy    { background: #d9f99d; color: #3f6212; border: 1px solid #bef264; }
.label-tag.lbl-neutral{ background: #dbeafe; color: #1d4ed8; border: 1px solid #93c5fd; }
.label-tag.lbl-avoid  { background: #fee2e2; color: #dc2626; border: 1px solid #fca5a5; }

/* ── Warning badges ── */
.warn-tag {
  font-size: 0.65em; font-weight: 700; border-radius: 5px;
  padding: 1px 6px; white-space: nowrap; cursor: default;
}
.warn-tag.warn-hot     { background: #fef3c7; color: #b45309; border: 1px solid #fcd34d; }
.warn-tag.warn-crowded { background: #ffedd5; color: #c2410c; border: 1px solid #fdba74; }

/* ── Rules modal ── */
.rules-modal {
  max-width: 860px; width: 100%; max-height: 90vh;
}
.rules-iframe-wrap {
  flex: 1; overflow: hidden;
}
.rules-iframe {
  width: 100%; height: 100%; min-height: 520px;
  border: none; display: block;
}
.rules-ext-link {
  font-size: 0.75em; color: #4f46e5; text-decoration: none;
  padding: 3px 10px; border: 1px solid #c7d2fe; border-radius: 6px;
  background: #eff6ff; white-space: nowrap; transition: background 0.15s;
}
.rules-ext-link:hover { background: #e0e7ff; }

/* ── Modal (white card) ── */
.modal-overlay {
  position: fixed; inset: 0;
  background: rgba(0,0,0,.45);
  display: flex; align-items: center; justify-content: center;
  z-index: 600; padding: 16px;
}
.modal {
  background: #fff; border-radius: 14px;
  width: 100%; max-width: 720px; max-height: 88vh;
  display: flex; flex-direction: column;
  box-shadow: 0 20px 60px rgba(0,0,0,.2); overflow: hidden;
}
.modal-hdr {
  display: flex; align-items: center; gap: 12px;
  padding: 16px 20px; border-bottom: 1px solid #e5e7eb; flex-shrink: 0;
}
.modal-title { font-size: 16px; font-weight: 800; color: #111827; flex: 1; }
.modal-search {
  border: 1px solid #d1d5db; border-radius: 8px; font-size: 13px;
  padding: 5px 10px; color: #374151; outline: none; width: 150px;
}
.modal-search:focus { border-color: #6366f1; }
.close-btn {
  background: none; border: none; font-size: 22px; color: #9ca3af;
  cursor: pointer; width: 32px; height: 32px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 6px; flex-shrink: 0;
}
.close-btn:hover { background: #f3f4f6; color: #374151; }
.modal-body { overflow-y: auto; padding: 12px 16px 20px; }

/* Modal table */
.modal-tbl-head {
  grid-template-columns: 44px 160px 100px 90px 1fr 120px;
  color: #6b7280; border-bottom-color: #e5e7eb;
}
.modal-tbl-row {
  grid-template-columns: 44px 160px 100px 90px 1fr 120px;
  background: #f9fafb;
}
.modal-tbl-row:hover { background: #f3f4f6; }
.modal-tbl-row.lbl-strong { border-left-color: #16a34a; background: #f0fdf4; }
.modal-tbl-row.lbl-buy    { border-left-color: #65a30d; background: #f7fee7; }
.modal-tbl-row.lbl-neutral{ border-left-color: #2563eb; background: #eff6ff; }
.modal-tbl-row.lbl-avoid  { border-left-color: #dc2626; background: #fef2f2; }
.modal-tbl-row.lbl-strong:hover { background: #dcfce7; }
.modal-tbl-row.lbl-buy:hover    { background: #ecfccb; }
.modal-tbl-row.lbl-neutral:hover{ background: #dbeafe; }
.modal-tbl-row.lbl-avoid:hover  { background: #fee2e2; }

/* these modifier classes are now redundant (same values as base), kept for compat */
.code-text--dark    { color: #111827; }
.name-text--dark    { color: #374151; }
.industry-col--dark { color: #6b7280; }
.pct-val--dark      { color: #111827; }
.empty-tip--dark    { color: #9ca3af; }

.modal-tbl-row .rank-num    { color: #9ca3af; }
.modal-tbl-row .pct-bar-wrap { background: #e5e7eb; }

@media (max-width: 640px) {
  /* Condensed 4-col layout: rank | code+name | score | label */
  .tbl-head, .tbl-row { grid-template-columns: 32px 1fr 48px 82px; }
  .tbl-head span:nth-child(3),
  .tbl-head span:nth-child(4) { display: none; }
  .modal-tbl-head, .modal-tbl-row { grid-template-columns: 32px 1fr 48px 82px; }
  .modal-tbl-head span:nth-child(3),
  .modal-tbl-head span:nth-child(4) { display: none; }
  .industry-col { display: none; }
  .price-col    { display: none; }
  .pct-bar-wrap { display: none; }
  .pct-val      { min-width: unset; font-size: 0.72em; }
  /* Stats */
  .stats-row { gap: 6px; }
  .stat-card { min-width: 60px; padding: 10px 4px; }
  .stat-val  { font-size: 1.3em; }
  /* Header controls */
  .quan-hdr   { flex-wrap: wrap; gap: 6px; padding: 10px 14px; }
  .quan-hdr-l { flex-wrap: wrap; }
  .search-input { width: 110px; }
  .chain-select { min-width: 140px; }
  .warn-tag { font-size: 0.60em; padding: 1px 4px; }
}

/* ── Detail modal ─────────────────────────────────────────────────────── */
.detail-modal {
  max-width: 580px;
}
.detail-hdr-info {
  display: flex; align-items: center; gap: 8px; flex: 1; flex-wrap: wrap;
}
.detail-name {
  font-size: 1em; font-weight: 800; color: #111827;
}
.detail-code {
  font-size: 0.75em; font-family: monospace; color: #6b7280;
  background: #f3f4f6; border-radius: 5px; padding: 1px 7px;
}
.detail-body { display: flex; flex-direction: column; gap: 14px; }

/* Loading/error */
.detail-state {
  display: flex; align-items: center; gap: 10px; justify-content: center;
  padding: 32px 0; color: #6b7280; font-size: 0.85em;
}
.detail-err { color: #dc2626; }
.detail-spinner {
  width: 18px; height: 18px; border: 2px solid #e5e7eb;
  border-top-color: #6366f1; border-radius: 50%;
  animation: spin 0.7s linear infinite; flex-shrink: 0;
}

/* Quote strip */
.detail-quote {
  display: flex; gap: 6px; flex-wrap: wrap;
  background: #f9fafb; border: 1px solid #e5e7eb;
  border-radius: 10px; padding: 10px 14px;
}
.dq-item {
  display: flex; flex-direction: column; align-items: center;
  min-width: 64px; flex: 1;
}
.dq-val { font-size: 1.05em; font-weight: 800; color: #111827; }
.dq-lbl { font-size: 0.6em; color: #9ca3af; margin-top: 2px; }

/* Sentiment bar */
.detail-sentiment {
  display: flex; align-items: center; gap: 10px;
  border-radius: 10px; padding: 10px 14px; flex-wrap: wrap;
}
.senti-warn { background: #fef3c7; border: 1px solid #fcd34d; }
.senti-buy  { background: #dcfce7; border: 1px solid #86efac; }
.senti-neutral { background: #eff6ff; border: 1px solid #bfdbfe; }
.senti-icon { font-size: 1.1em; }
.senti-text { font-size: 0.9em; font-weight: 800; color: #111827; }
.senti-sub  { font-size: 0.72em; color: #6b7280; margin-left: auto; }

/* Section titles */
/* ── Factor breakdown ── */
.factor-breakdown {
  background: #f8fafc; border: 1px solid #e5e7eb; border-radius: 8px;
  padding: 12px 14px; display: flex; flex-direction: column; gap: 8px;
}
.fb-total { font-size: 0.85em; font-weight: 600; color: #4f46e5; text-transform: none; letter-spacing: 0; }
.fb-bars  { display: flex; flex-direction: column; gap: 6px; }
.fb-row   { display: grid; grid-template-columns: 72px 1fr 36px; align-items: center; gap: 8px; }
.fb-label { font-size: 0.75em; font-weight: 600; color: #374151; white-space: nowrap; }
.fb-weight  { font-size: 0.82em; font-weight: 400; color: #9ca3af; margin-left: 2px; }
.fb-sub-tag { font-size: 0.72em; font-weight: 400; color: #a78bfa; margin-left: 3px; background: #f5f3ff; padding: 1px 4px; border-radius: 3px; }
.fb-subrow   { display: grid; grid-template-columns: 72px 1fr 36px; align-items: center; gap: 8px; margin-top: -2px; }
.fb-sublabel { font-size: 0.68em; font-weight: 500; color: #a78bfa; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding-left: 8px; }
.fb-subval   { font-size: 0.68em; }
.opp-tag    { font-size: 0.72em; font-weight: 600; color: #d97706; background: #fef3c7; border: 1px solid #fcd34d; padding: 1px 5px; border-radius: 4px; margin-left: 4px; cursor: default; white-space: nowrap; }
.opp-tag--star { color: #0e7490; background: #ecfeff; border-color: #67e8f9; }
.fb-val-note { font-size: 0.63em; color: #9ca3af; padding-left: 8px; margin-top: -2px; }
.fb-bar-bg { height: 8px; background: #e5e7eb; border-radius: 4px; overflow: hidden; }
.fb-bar-fill { height: 100%; border-radius: 4px; transition: width 0.4s ease; background: linear-gradient(90deg,#22c55e,#4ade80); }
.fb-bar-fill.fb-high { background: linear-gradient(90deg,#22c55e,#4ade80); }
.fb-bar-fill.fb-mid  { background: linear-gradient(90deg,#f59e0b,#fbbf24); }
.fb-bar-fill.fb-low  { background: linear-gradient(90deg,#ef4444,#f87171); }
.fb-val { font-size: 0.75em; font-weight: 700; text-align: right; }
.fb-val.fb-high { color: #16a34a; }
.fb-val.fb-mid  { color: #d97706; }
.fb-val.fb-low  { color: #dc2626; }

.detail-sec-title {
  font-size: 0.72em; font-weight: 700; color: #374151;
  letter-spacing: .4px; text-transform: uppercase;
  display: flex; align-items: center; gap: 8px;
}
.fund-period {
  font-size: 0.9em; font-weight: 400; color: #9ca3af;
  text-transform: none; letter-spacing: 0;
}

/* MA grid */
.ma-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 8px;
}
.ma-item { display: flex; flex-direction: column; gap: 4px; }
.ma-row  { display: flex; align-items: baseline; gap: 6px; }
.ma-name { font-size: 0.72em; font-weight: 700; color: #374151; min-width: 42px; }
.ma-val  { font-size: 0.85em; font-weight: 600; color: #111827; }
.ma-dev  { font-size: 0.72em; font-weight: 700; margin-left: auto; }
.dev-above { color: #dc2626; }
.dev-below { color: #16a34a; }
.ma-bar-bg { height: 5px; background: #e5e7eb; border-radius: 3px; overflow: hidden; }
.ma-bar-fill { height: 100%; border-radius: 3px; transition: width 0.4s ease; }
.bar-far-above { background: #dc2626; }
.bar-above     { background: #f97316; }
.bar-near      { background: #22c55e; }
.bar-below     { background: #3b82f6; }

/* Buy zones */
.zones-list { display: flex; flex-direction: column; gap: 6px; }
.zone-card {
  border-radius: 9px; padding: 9px 12px;
  border-left: 3px solid transparent;
}
.zone-t1 { background: #fefce8; border-left-color: #eab308; }
.zone-t2 { background: #eff6ff; border-left-color: #3b82f6; }
.zone-t3 { background: #f0fdf4; border-left-color: #16a34a; }
.zone-hdr { display: flex; align-items: center; gap: 8px; margin-bottom: 3px; }
.zone-num { font-size: 1em; }
.zone-label { font-size: 0.8em; font-weight: 700; color: #374151; flex: 1; }
.zone-range { font-size: 0.88em; font-weight: 800; color: #111827; font-family: monospace; }
.zone-detail { font-size: 0.7em; color: #6b7280; }
.zone-detail em { font-style: normal; color: #374151; font-weight: 600; }

/* Targets & Stop */
.ts-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.ts-col { display: flex; flex-direction: column; gap: 6px; }
.ts-item { display: flex; align-items: baseline; gap: 6px; }
.ts-num  { font-size: 0.95em; flex-shrink: 0; }
.ts-price {
  font-size: 0.95em; font-weight: 800; font-family: monospace; flex-shrink: 0;
}
.ts-basis { font-size: 0.67em; color: #6b7280; }
.target-price { color: #16a34a; }
.stop-price   { color: #dc2626; }
.stop-dot { color: #dc2626; font-weight: 900; }

/* Fundamentals */
.fund-grid {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px;
}
.fund-item { display: flex; flex-direction: column; align-items: center; gap: 2px; }
.fund-val  { font-size: 0.95em; font-weight: 800; color: #111827; }
.fund-lbl  { font-size: 0.62em; color: #9ca3af; }

/* Disclaimer */
.detail-disclaimer {
  font-size: 0.63em; color: #9ca3af; border-top: 1px solid #f3f4f6;
  padding-top: 10px; text-align: center;
}

/* ── Sector valuation comparison ── */
.sector-val-row {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  background: #f9fafb; border: 1px solid #e5e7eb;
  border-radius: 10px; padding: 10px 14px; margin-bottom: 4px;
}
.sv-item { display: flex; flex-direction: column; align-items: center; min-width: 64px; }
.sv-val  { font-size: 1.05em; font-weight: 800; color: #111827; font-family: 'SF Mono', monospace; }
.sv-lbl  { font-size: 0.66em; color: #6b7280; margin-top: 1px; }
.sv-divider { font-size: 0.78em; color: #9ca3af; font-weight: 600; padding: 0 2px; }
.sv-verdict {
  display: flex; flex-direction: column; align-items: center;
  margin-left: auto; padding: 5px 12px; border-radius: 8px;
}
.sv-prem {
  font-size: 0.88em; font-weight: 800; font-family: 'SF Mono', monospace;
}
.sv-tag  { font-size: 0.66em; font-weight: 700; margin-top: 1px; }

.sv-cheap     { background: #dcfce7; color: #16a34a; }
.sv-fair      { background: #f0fdf4; color: #15803d; }
.sv-pricey    { background: #fff7ed; color: #c2410c; }
.sv-expensive { background: #fee2e2; color: #dc2626; }

/* ── 移动端：所有弹窗改为底部弹出 (bottom sheet) ── */
@media (max-width: 640px) {
  .modal-overlay { padding: 0; align-items: flex-end; }
  .modal {
    max-width: 100vw !important; width: 100%;
    border-radius: 16px 16px 0 0; max-height: 92dvh;
  }
  .detail-modal { border-radius: 20px 20px 0 0; max-height: 96dvh; }
  .rules-modal  { border-radius: 0; max-height: 100dvh; max-width: 100vw; }
  .fund-grid { grid-template-columns: repeat(2, 1fr); }
  .sector-val-row { gap: 6px; padding: 8px 10px; }
  .sv-verdict { margin-left: 0; }
}
</style>
