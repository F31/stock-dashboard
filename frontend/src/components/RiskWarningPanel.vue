<template>
  <div class="rw-panel">
    <!-- ── 风险雷达 ── -->
    <RiskRadarChart />

    <!-- ── 第一行：情绪温度 + 宏观联动 ── -->
    <div class="rw-row">
      <!-- 情绪温度计 -->
      <section class="rw-card rw-sentiment">
        <div class="rw-card-hdr">
          <span class="rw-card-title">📊 市场情绪</span>
          <span class="rw-date">{{ sentiment?.date || '—' }}</span>
        </div>
        <div v-if="loadingSent" class="rw-loading">加载中（全市场快照约10-35s）…</div>
        <template v-else-if="sentiment">
          <!-- 全市场数据可用 -->
          <template v-if="sentiment.data_source === 'full_market'">
            <div class="sent-gauge-wrap">
              <svg class="sent-gauge" viewBox="0 0 120 70">
                <path d="M10,65 A55,55 0 0,1 110,65" fill="none" stroke="#e5e7eb" stroke-width="10" stroke-linecap="round"/>
                <path d="M10,65 A55,55 0 0,1 110,65" fill="none"
                  :stroke="gaugeColor" stroke-width="10" stroke-linecap="round"
                  :stroke-dasharray="`${sentiment.up_ratio * 1.728} 200`"/>
                <text x="60" y="58" text-anchor="middle" font-size="13" font-weight="700" :fill="gaugeColor">
                  {{ sentiment.up_ratio }}%
                </text>
              </svg>
            </div>
            <div class="sent-label" :style="{ color: gaugeColor }">{{ sentiment.label }}</div>
            <div class="sent-breadth">
              <div class="sent-breadth-bar">
                <div class="sent-bar-up"   :style="{ flex: sentiment.up_count }"></div>
                <div class="sent-bar-flat" :style="{ flex: sentiment.flat_count }"></div>
                <div class="sent-bar-dn"   :style="{ flex: sentiment.dn_count }"></div>
              </div>
              <div class="sent-breadth-nums">
                <span class="sent-up-n">↑{{ sentiment.up_count }}</span>
                <span class="sent-flat-n">—{{ sentiment.flat_count }}</span>
                <span class="sent-dn-n">↓{{ sentiment.dn_count }}</span>
              </div>
            </div>
          </template>

          <!-- 降级：pool_only — 用涨跌停比作为情绪代理 -->
          <template v-else-if="sentiment.data_source === 'pool_only'">
            <div class="sent-pool-bar-wrap">
              <div class="sent-pool-bar">
                <div class="sent-bar-up" :style="{ flex: sentiment.zt_sealed || 1 }"></div>
                <div class="sent-bar-dn" :style="{ flex: sentiment.dt_pool || 1 }"></div>
              </div>
              <div class="sent-pool-nums">
                <span class="sent-up-n">涨停封 {{ sentiment.zt_sealed }}</span>
                <span class="sent-dn-n">跌停池 {{ sentiment.dt_pool }}</span>
              </div>
            </div>
            <div class="sent-label" :style="{ color: gaugeColor }">{{ sentiment.label }}</div>
            <div class="sent-pool-notice">全市场快照暂不可用，以涨跌停池为代理指标</div>
          </template>

          <!-- 数据完全不可用 -->
          <template v-else>
            <div class="sent-pool-notice">数据暂不可用，请稍后重试</div>
          </template>

          <!-- 涨跌停家数（始终显示）-->
          <div class="sent-counts">
            <span class="sent-zt">涨停 {{ sentiment.zt_limit || sentiment.zt_count }}
              <span v-if="sentiment.zt_sealed" class="sent-sub">封{{ sentiment.zt_sealed }}+炸{{ sentiment.zt_broken }}</span>
            </span>
            <span class="sent-dt">跌停 {{ sentiment.dt_limit || sentiment.dt_count }}</span>
          </div>
        </template>
        <div v-else class="rw-error">获取失败
          <button class="rw-retry" @click="load(fetchRiskSentiment, sentiment, loadingSent)">↻ 重试</button>
        </div>
      </section>

      <!-- 宏观风险 -->
      <section class="rw-card rw-macro">
        <div class="rw-card-hdr">
          <span class="rw-card-title">🌐 宏观联动</span>
          <span class="rw-date">{{ macro?.bonds?.date || '—' }}</span>
        </div>
        <div v-if="loadingMacro" class="rw-loading">加载中…</div>
        <template v-else-if="macro">
          <!-- 黄金 -->
          <div v-if="macro.gold" class="macro-item">
            <span class="macro-label">🥇 黄金(Au99.99)</span>
            <span class="macro-val">{{ macro.gold.price }}元/克</span>
            <span class="macro-chg" :class="macro.gold.chg5 >= 0 ? 'up' : 'dn'">
              {{ macro.gold.chg5 >= 0 ? '+' : '' }}{{ macro.gold.chg5 }}% (5日)
            </span>
          </div>
          <!-- 国债 -->
          <div v-if="macro.bonds" class="macro-item">
            <span class="macro-label">🇨🇳 中债10年</span>
            <span class="macro-val">{{ macro.bonds.cn10 }}%</span>
            <span class="macro-chg" :class="macro.bonds.cn10_chg5 >= 0 ? 'up' : 'dn'">
              {{ macro.bonds.cn10_chg5 >= 0 ? '+' : '' }}{{ macro.bonds.cn10_chg5 }}BP (5日)
            </span>
          </div>
          <div v-if="macro.bonds" class="macro-item" :class="macro.bonds.us10_level">
            <span class="macro-label">🇺🇸 美债10年</span>
            <span class="macro-val">{{ macro.bonds.us10 }}%</span>
            <span class="macro-chg" :class="macro.bonds.us10_chg5 >= 0 ? 'up' : 'dn'">
              {{ macro.bonds.us10_chg5 >= 0 ? '+' : '' }}{{ macro.bonds.us10_chg5 }}BP (5日)
            </span>
          </div>
          <!-- 汇率 -->
          <div v-if="macro.cny" class="macro-item">
            <span class="macro-label">💱 {{ macro.cny.pair }}</span>
            <span class="macro-val">{{ macro.cny.rate }}</span>
          </div>
        </template>
        <div v-else class="rw-error">获取失败
          <button class="rw-retry" @click="load(fetchRiskMacro, macro, loadingMacro)">↻ 重试</button>
        </div>
      </section>
    </div>

    <!-- ── 第二行：融资余额 ── -->
    <section class="rw-card rw-margin">
      <div class="rw-card-hdr">
        <span class="rw-card-title">💳 融资余额（上交所）</span>
        <span class="rw-date">{{ margin?.date || '—' }} · T+1</span>
        <span v-if="margin" class="margin-chg" :class="margin.level">
          {{ margin.chg >= 0 ? '+' : '' }}{{ margin.chg }}亿 日变动
        </span>
        <span v-if="margin?.is_stale" class="margin-stale">⚠️ 数据滞后{{ margin.days_lag }}天</span>
      </div>
      <div v-if="loadingMargin" class="rw-loading">加载中…</div>
      <template v-else-if="margin">
        <div class="margin-latest">{{ margin.latest.toLocaleString() }}亿</div>
        <div class="margin-bar-wrap">
          <div
            v-for="pt in margin.trend" :key="pt.date"
            class="margin-bar-col"
            :title="`${pt.date}: ${pt.balance}亿`"
          >
            <div class="margin-bar" :style="{ height: barHeight(pt.balance, margin.trend) + 'px' }"></div>
            <div class="margin-bar-label">{{ pt.date.slice(4, 8) }}</div>
          </div>
        </div>
      </template>
      <div v-else class="rw-error">获取失败
        <button class="rw-retry" @click="load(fetchRiskMargin, margin, loadingMargin)">↻ 重试</button>
      </div>
    </section>

    <!-- ── 第三行：大宗交易折价 + 龙虎榜 ── -->
    <div class="rw-row-2">
      <!-- 大宗交易折价 -->
      <section class="rw-card rw-block rw-half">
        <div class="rw-card-hdr">
          <span class="rw-card-title">🏦 大宗交易折价榜</span>
          <span class="rw-date">T+1</span>
        </div>
        <div v-if="loadingBlock" class="rw-loading">加载中…</div>
        <template v-else-if="blockTrades">
          <div v-if="!blockTrades.items.length" class="rw-empty">暂无数据</div>
          <table v-else class="rw-table">
            <thead>
              <tr><th>名称</th><th>折溢价率</th><th>成交额(万)</th><th>涨跌</th></tr>
            </thead>
            <tbody>
              <tr
                v-for="item in blockTrades.items" :key="item.code + item.date"
                :class="{ 'row-warn': item.discount < -5 }"
              >
                <td class="td-name">{{ item.name }}</td>
                <td class="td-discount" :class="item.discount < 0 ? 'negative' : 'positive'">
                  {{ item.discount >= 0 ? '+' : '' }}{{ item.discount }}%
                </td>
                <td>{{ item.amount }}</td>
                <td :class="item.change_pct >= 0 ? 'up' : 'dn'">
                  {{ item.change_pct >= 0 ? '+' : '' }}{{ item.change_pct.toFixed(2) }}%
                </td>
              </tr>
            </tbody>
          </table>
        </template>
        <div v-else class="rw-error">获取失败
          <button class="rw-retry" @click="load(fetchRiskBlockTrades, blockTrades, loadingBlock)">↻ 重试</button>
        </div>
      </section>

      <!-- 龙虎榜 -->
      <section class="rw-card rw-lhb rw-half">
        <div class="rw-card-hdr">
          <span class="rw-card-title">🐉 龙虎榜异动</span>
          <span class="rw-date">T+1</span>
        </div>
        <div v-if="loadingLhb" class="rw-loading">加载中…</div>
        <template v-else-if="lhb">
          <div v-if="!lhb.items.length" class="rw-empty">暂无数据</div>
          <table v-else class="rw-table">
            <thead>
              <tr><th>名称</th><th>涨跌</th><th>解读</th></tr>
            </thead>
            <tbody>
              <tr v-for="item in lhb.items" :key="item.code + item.date">
                <td class="td-name">{{ item.name }}</td>
                <td :class="item.change_pct >= 0 ? 'up' : 'dn'">
                  {{ item.change_pct >= 0 ? '+' : '' }}{{ item.change_pct.toFixed(2) }}%
                </td>
                <td class="td-reason">{{ item.reason }}</td>
              </tr>
            </tbody>
          </table>
        </template>
        <div v-else class="rw-error">获取失败
          <button class="rw-retry" @click="load(fetchRiskLhb, lhb, loadingLhb)">↻ 重试</button>
        </div>
      </section>
    </div>

    <!-- ── 第四行：近期解禁压力 ── -->
    <section class="rw-card rw-restricted">
      <div class="rw-card-hdr">
        <span class="rw-card-title">🔓 近期解禁压力</span>
        <div class="rst-tabs">
          <button :class="['rst-tab', restrictedTab === 'future' && 'rst-tab-active']"
                  @click="restrictedTab = 'future'">未来 21 天</button>
          <button :class="['rst-tab', restrictedTab === 'history' && 'rst-tab-active']"
                  @click="restrictedTab = 'history'">历史公告</button>
        </div>
        <span class="rw-date">T+1</span>
      </div>
      <div v-if="loadingRestricted" class="rw-loading">加载中…</div>
      <template v-else-if="restricted">

        <!-- ── Tab: 未来压力 ── -->
        <template v-if="restrictedTab === 'future'">
          <div v-if="restricted.summary.length" class="rst-bar-wrap">
            <div
              v-for="s in restricted.summary" :key="s.date"
              class="rst-bar-col"
              :title="`${s.date}：${s.count}只 / ${s.market_value}亿`"
            >
              <div
                class="rst-bar"
                :style="{ height: rstBarH(s.market_value) + 'px' }"
                :class="s.market_value >= 100 ? 'rst-bar-high' : s.market_value >= 20 ? 'rst-bar-mid' : 'rst-bar-low'"
              ></div>
              <div class="rst-bar-val">{{ s.market_value > 0 ? s.market_value + '亿' : '' }}</div>
              <div class="rst-bar-date">{{ s.date.slice(5) }}</div>
            </div>
          </div>
          <div v-if="restricted.detail.length" class="rst-detail">
            <div class="rst-detail-title">7日解禁明细</div>
            <table class="rw-table">
              <thead>
                <tr><th>名称</th><th>解禁日</th><th>类型</th><th>市值(亿)</th><th>占流通比</th></tr>
              </thead>
              <tbody>
                <tr
                  v-for="item in restricted.detail" :key="item.code + item.date"
                  :class="{ 'row-warn': item.market_value >= 10 }"
                >
                  <td class="td-name">{{ item.name }}</td>
                  <td style="white-space:nowrap;font-size:0.9em">{{ item.date.slice(5) }}</td>
                  <td class="td-reason">{{ item.type }}</td>
                  <td :class="item.market_value >= 10 ? 'negative' : ''">{{ item.market_value }}</td>
                  <td>{{ item.ratio }}%</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-else class="rw-empty">近期无解禁数据</div>
        </template>

        <!-- ── Tab: 历史公告（懒加载，切换Tab时按需请求）── -->
        <template v-else>
          <div v-if="loadingRestrictedHist" class="rw-loading">加载历史数据…</div>
          <div v-else-if="restrictedHistory?.history?.length" class="rst-detail">
            <table class="rw-table">
              <thead>
                <tr>
                  <th>名称</th><th>解禁日</th><th>类型</th>
                  <th>市值(亿)</th><th>占流通比</th>
                  <th title="解禁前20个交易日涨跌幅">前20日%</th>
                  <th title="解禁后20个交易日涨跌幅">后20日%</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="item in restrictedHistory.history" :key="item.code + item.date"
                  :class="{ 'row-warn': item.market_value >= 10 }"
                >
                  <td class="td-name">{{ item.name }}</td>
                  <td style="white-space:nowrap;font-size:0.9em">{{ item.date.slice(5) }}</td>
                  <td class="td-reason">{{ item.type }}</td>
                  <td :class="item.market_value >= 10 ? 'negative' : ''">{{ item.market_value }}</td>
                  <td>{{ item.ratio }}%</td>
                  <td :class="item.pre20_chg >= 0 ? 'positive' : 'negative'">
                    {{ item.pre20_chg != null ? (item.pre20_chg >= 0 ? '+' : '') + item.pre20_chg + '%' : '—' }}
                  </td>
                  <td :class="item.post20_chg != null ? (item.post20_chg >= 0 ? 'positive' : 'negative') : ''">
                    {{ item.post20_chg != null ? (item.post20_chg >= 0 ? '+' : '') + item.post20_chg + '%' : '—' }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-else-if="restrictedHistory !== null" class="rw-empty">近21个交易日暂无解禁数据</div>
          <div v-else class="rw-error">获取失败
            <button class="rw-retry" @click="load(fetchRiskRestrictedHistory, restrictedHistory, loadingRestrictedHist)">↻ 重试</button>
          </div>
        </template>

      </template>
      <div v-else class="rw-error">获取失败
        <button class="rw-retry" @click="load(fetchRiskRestricted, restricted, loadingRestricted)">↻ 重试</button>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import {
  fetchRiskSentiment, fetchRiskMargin,
  fetchRiskBlockTrades, fetchRiskLhb, fetchRiskMacro,
  fetchRiskRestricted, fetchRiskRestrictedHistory,
} from '../api'
import RiskRadarChart from './RiskRadarChart.vue'

const sentiment   = ref(null)
const margin      = ref(null)
const blockTrades = ref(null)
const lhb         = ref(null)
const macro       = ref(null)
const restricted         = ref(null)
const restrictedHistory  = ref(null)
const restrictedTab      = ref('future')

const loadingSent            = ref(false)
const loadingMargin          = ref(false)
const loadingBlock           = ref(false)
const loadingLhb             = ref(false)
const loadingMacro           = ref(false)
const loadingRestricted      = ref(false)
const loadingRestrictedHist  = ref(false)

const gaugeColor = computed(() => {
  if (!sentiment.value) return '#6b7280'
  const r = sentiment.value.up_ratio
  if (r === null || r === undefined) return '#6b7280'
  if (r >= 75) return '#dc2626'
  if (r >= 58) return '#f59e0b'
  if (r >= 42) return '#6b7280'
  if (r >= 25) return '#f59e0b'
  return '#16a34a'
})

async function load(fn, target, loadingRef) {
  loadingRef.value = true
  try {
    const res = await fn()
    target.value = res.data
  } catch (e) {
    console.error(e)
    target.value = null
  } finally {
    loadingRef.value = false
  }
}

// 每次调用错开 delay ms，避免同时触发多个重量级请求
function loadT1Staggered() {
  load(fetchRiskMargin,      margin,      loadingMargin)
  setTimeout(() => load(fetchRiskBlockTrades, blockTrades, loadingBlock), 200)
  setTimeout(() => load(fetchRiskLhb,         lhb,         loadingLhb),   400)
  setTimeout(() => load(fetchRiskMacro,       macro,       loadingMacro),  600)
  setTimeout(() => load(fetchRiskRestricted,  restricted,  loadingRestricted), 800)
}

// 历史解禁：仅在切换到「历史公告」Tab 时懒加载，避免首屏耗时
watch(restrictedTab, (tab) => {
  if (tab === 'history' && !restrictedHistory.value && !loadingRestrictedHist.value) {
    load(fetchRiskRestrictedHistory, restrictedHistory, loadingRestrictedHist)
  }
})

function barHeight(val, trend) {
  const vals = trend.map(t => t.balance)
  const min = Math.min(...vals)
  const max = Math.max(...vals)
  const range = max - min || 1
  return Math.max(4, Math.round(((val - min) / range) * 48))
}

function rstBarH(val) {
  if (!restricted.value?.summary?.length) return 4
  const max = Math.max(...restricted.value.summary.map(s => s.market_value)) || 1
  return Math.max(4, Math.round((val / max) * 56))
}

onMounted(() => {
  load(fetchRiskSentiment, sentiment, loadingSent)
  loadT1Staggered()
})
</script>

<style scoped>
/* ── 面板根节点：不设 max-width，让 .main 的 clamp padding 生效 ── */
.rw-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px 0 24px;
  width: 100%;
  box-sizing: border-box;
}

/* ── 网格行：桌面 2 列，手机 1 列 ── */
.rw-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.7fr);
  gap: 12px;
}

.rw-row-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.rw-card {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 14px 16px;
  min-width: 0;        /* 防止 grid 子项溢出 */
  box-sizing: border-box;
}

/* 融资余额占满整行 */
.rw-margin { width: 100%; }

.rw-card-hdr {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.rw-card-title { font-size: 0.82em; font-weight: 700; color: #111827; white-space: nowrap; }
.rw-date { font-size: 0.7em; color: #9ca3af; margin-left: auto; }

.rw-loading { font-size: 0.78em; color: #9ca3af; padding: 20px 0; text-align: center; }
.rw-error   { font-size: 0.78em; color: #dc2626; padding: 20px 0; text-align: center; }
.rw-empty   { font-size: 0.78em; color: #9ca3af; padding: 12px 0; text-align: center; }
.rw-retry   {
  display: inline-block; margin-top: 6px;
  padding: 3px 10px; font-size: 0.8em; font-weight: 600;
  background: #fee2e2; border: 1px solid #fca5a5; color: #dc2626;
  border-radius: 5px; cursor: pointer; font-family: inherit;
}
.rw-retry:hover { background: #fecaca; }

/* ── 情绪温度计 ── */
.sent-gauge-wrap { display: flex; justify-content: center; }
.sent-gauge { width: 140px; height: 80px; }
.sent-label { text-align: center; font-size: 0.85em; font-weight: 700; margin-bottom: 6px; }
.sent-counts { display: flex; justify-content: space-around; font-size: 0.72em; }
.sent-zt { color: #dc2626; font-weight: 600; }
.sent-dt { color: #16a34a; font-weight: 600; }
.sent-sub { font-size: 0.78em; color: #9ca3af; font-weight: 400; margin-left: 2px; }
.sent-pool-notice { font-size: 0.72em; color: #9ca3af; text-align: center; padding: 4px 4px 2px; }
.sent-pool-bar-wrap { margin: 4px 0 2px; }
.sent-pool-bar { display: flex; height: 8px; border-radius: 4px; overflow: hidden; gap: 1px; }
.sent-pool-nums { display: flex; justify-content: space-between; font-size: 0.7em; margin-top: 3px; }

/* ── 全市场涨跌家数进度条 ── */
.sent-breadth { margin: 6px 0 4px; }
.sent-breadth-bar {
  display: flex;
  height: 8px;
  border-radius: 4px;
  overflow: hidden;
  gap: 1px;
}
.sent-bar-up   { background: #dc2626; border-radius: 4px 0 0 4px; min-width: 2px; }
.sent-bar-flat { background: #d1d5db; min-width: 1px; }
.sent-bar-dn   { background: #16a34a; border-radius: 0 4px 4px 0; min-width: 2px; }
.sent-breadth-nums {
  display: flex;
  justify-content: space-between;
  font-size: 0.7em;
  margin-top: 2px;
}
.sent-up-n   { color: #dc2626; font-weight: 600; }
.sent-flat-n { color: #9ca3af; }
.sent-dn-n   { color: #16a34a; font-weight: 600; }

/* ── 解禁压力 Tab ── */
.rst-tabs {
  display: flex;
  gap: 2px;
  background: #f3f4f6;
  border-radius: 6px;
  padding: 2px;
  margin-left: 8px;
}
.rst-tab {
  font-size: 0.72em;
  font-weight: 600;
  padding: 2px 9px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  background: transparent;
  color: #6b7280;
  white-space: nowrap;
  transition: background 0.15s, color 0.15s;
}
.rst-tab:hover { color: #374151; }
.rst-tab-active { background: #fff; color: #111827; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }

/* ── 解禁压力 ── */
.rst-bar-wrap {
  display: flex;
  align-items: flex-end;
  gap: 3px;
  height: 72px;
  margin-bottom: 10px;
  padding-top: 4px;
}
.rst-bar-col  { display: flex; flex-direction: column; align-items: center; flex: 1; gap: 1px; }
.rst-bar      { width: 100%; border-radius: 3px 3px 0 0; min-height: 4px; }
.rst-bar-high { background: #dc2626; }
.rst-bar-mid  { background: #f59e0b; }
.rst-bar-low  { background: #93c5fd; }
.rst-bar-val  { font-size: 0.55em; color: #6b7280; white-space: nowrap; }
.rst-bar-date { font-size: 0.58em; color: #9ca3af; white-space: nowrap; }
.rst-detail-title { font-size: 0.72em; font-weight: 700; color: #374151; margin-bottom: 4px; }
.rst-detail { margin-top: 4px; }

/* ── 融资余额滞后警告 ── */
.margin-stale { font-size: 0.7em; color: #f59e0b; font-weight: 600; }

/* ── 宏观 ── */
.macro-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 0;
  border-bottom: 1px solid #f3f4f6;
  font-size: 0.78em;
  flex-wrap: wrap;
}
.macro-item:last-child { border-bottom: none; }
.macro-label { flex: 1; color: #374151; min-width: 120px; }
.macro-val   { font-weight: 700; font-family: monospace; }
.macro-chg   { font-family: monospace; font-size: 0.9em; }

/* ── 融资余额 ── */
.margin-latest { font-size: 1.3em; font-weight: 700; color: #111827; margin-bottom: 8px; }
.margin-chg    { font-size: 0.75em; font-weight: 600; }
.margin-bar-wrap {
  display: flex;
  align-items: flex-end;
  gap: 4px;
  height: 70px;
  padding-top: 4px;
}
.margin-bar-col {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex: 1;
  gap: 2px;
}
.margin-bar {
  width: 100%;
  background: #3b82f6;
  border-radius: 3px 3px 0 0;
  min-height: 4px;
}
.margin-bar-label { font-size: 0.6em; color: #9ca3af; white-space: nowrap; }

/* ── 表格 ── */
.rw-table { width: 100%; border-collapse: collapse; font-size: 0.75em; }
.rw-table th {
  text-align: left;
  color: #9ca3af;
  font-weight: 600;
  padding: 4px 6px;
  border-bottom: 1px solid #e5e7eb;
  white-space: nowrap;
}
.rw-table td { padding: 5px 6px; border-bottom: 1px solid #f3f4f6; vertical-align: middle; }
.rw-table tbody tr:hover { background: #f9fafb; }
.td-name     { font-weight: 600; color: #111827; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 110px; }
.td-discount { font-weight: 700; font-family: monospace; white-space: nowrap; }
.td-reason   { color: #6b7280; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 200px; }
.row-warn    { background: #fef9f0; }

/* ── 通用颜色 ── */
.positive { color: #dc2626; }
.negative { color: #16a34a; }
.neutral  { color: #6b7280; }
.warning  { color: #f59e0b; }
.danger   { color: #dc2626; }
.normal   { color: #374151; }
.up { color: #dc2626; }
.dn { color: #16a34a; }

/* ── 响应式：手机（≤600px）→ 1 列 ── */
@media (max-width: 600px) {
  .rw-row,
  .rw-row-2 {
    grid-template-columns: 1fr;
  }
  .td-reason { display: none; }    /* 龙虎榜"解读"列手机隐藏 */
}
</style>
