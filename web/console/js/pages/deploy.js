// Deployment data page — paper evidence from the anonymous telemetry store.
// Self-contained on purpose: it issues its own tokened fetch and carries its
// own bilingual labels, so it does not depend on api.js/i18n.js edits and can
// be registered in app.js with a single nav entry.

import { store, toast } from "../store.js";

const { ref, computed, onMounted } = Vue;

const LABELS = {
  en: {
    title: "Deployment Data",
    sub: "Anonymous client telemetry — TTFR, bytes, frame rate and failures, aggregated for the paper.",
    refresh: "Refresh",
    evidence: "Download evidence.md",
    loads: "Scene loads",
    loadsHint: "all serving_load events",
    failRate: "Failure rate",
    failRateHint: "failed / all loads",
    clients: "Unique clients",
    clientsHint: "distinct anonymous ids",
    bench: "Benchmark loads",
    benchHint: "harness runs, kept separate",
    quality: "Experience metrics",
    metric: "Metric",
    adminOnly: "Deployment data is served by the developer admin instance only (start the server with --admin on a separate port).",
    samples: "n",
    stage: "Load stages",
    dist: "Distributions",
    visitors: "Client mix & HTTP",
    httpTitle: "HTTP",
    recent: "Recent failures",
    noFailures: "No 4xx/5xx recorded.",
    policy: "Policy",
    profile: "Client profile",
    capability: "Capability",
    sceneScale: "Scene scale",
    failStages: "Failure stages",
    browser: "Browser",
    os: "OS",
    device: "Device",
    requests: "Requests",
    bytesServed: "Bytes served",
    latency: "Latency ms",
    status: "Status",
    time: "Time",
    path: "Path",
    mTTFR: "TTFR ms",
    mFps: "FPS",
    mP95: "P95 frame ms",
    mBytes: "Bytes / load",
    exportsTitle: "Exports",
    exportsOk: "ok",
    loadFailed: "Could not load telemetry summary",
    stageFirstFrame: "First frame",
    stageComplete: "Complete",
    stageFailed: "Failed",
  },
  zh: {
    title: "部署数据",
    sub: "匿名客户端遥测——首帧时间、字节、帧率与失败，聚合后作为论文证明材料。",
    refresh: "刷新",
    evidence: "下载 evidence.md",
    loads: "场景加载",
    loadsHint: "全部加载事件",
    failRate: "失败率",
    failRateHint: "失败 / 全部加载",
    clients: "独立客户端",
    clientsHint: "去重后的匿名编号",
    bench: "基准测试加载",
    benchHint: "采集壳运行，单独统计",
    quality: "体验指标",
    metric: "指标",
    adminOnly: "部署数据只在开发者实例开放：用 --admin 参数在另一个端口启动服务即可进入。",
    samples: "次数",
    stage: "加载阶段",
    dist: "分布",
    visitors: "访问者与 HTTP",
    httpTitle: "HTTP",
    recent: "最近失败",
    noFailures: "没有记录到 4xx/5xx。",
    policy: "传输策略",
    profile: "客户端档位",
    capability: "能力等级",
    sceneScale: "场景规模",
    failStages: "失败阶段",
    browser: "浏览器",
    os: "系统",
    device: "设备",
    requests: "请求数",
    bytesServed: "下发字节",
    latency: "延迟（毫秒）",
    status: "状态码",
    time: "时间",
    path: "路径",
    mTTFR: "首帧时间（毫秒）",
    mFps: "帧率",
    mP95: "P95 帧时间（毫秒）",
    mBytes: "单次加载字节",
    exportsTitle: "导出",
    exportsOk: "成功",
    loadFailed: "遥测汇总加载失败",
    stageFirstFrame: "首帧",
    stageComplete: "完整加载",
    stageFailed: "失败",
  },
};

const SCALE_LABELS = { lt_1m: "<1M", "1m_to_5m": "1M–5M", gt_5m: ">5M", unknown: "?" };
const STAGE_LABEL_KEYS = { first_frame: "stageFirstFrame", complete: "stageComplete", failed: "stageFailed" };

export default {
  name: "DeployPage",
  setup() {
    const summary = ref(null);
    const loading = ref(false);
    // Deep-link guard: on a user-facing instance the endpoint does not exist,
    // so show the notice instead of a fetch error.
    const notAdmin = window.__WEBSCAN_ADMIN__ !== true;
    const L = (key) => (LABELS[store.locale === "zh" ? "zh" : "en"] || LABELS.en)[key] || key;

    async function load() {
      if (notAdmin) return;
      loading.value = true;
      try {
        const headers = {};
        const token = String(window.__WEBSCAN_API_TOKEN__ || "");
        if (token) headers["X-Auth-Token"] = token;
        const response = await fetch("/api/telemetry/summary", { headers });
        const data = await response.json();
        if (!response.ok || !data.ok) throw new Error(data.error || `${response.status}`);
        summary.value = data.summary;
      } catch (err) {
        toast(`${L("loadFailed")}: ${err.message}`, "error", 7000);
      } finally {
        loading.value = false;
      }
    }

    function openEvidence() {
      const token = String(window.__WEBSCAN_API_TOKEN__ || "");
      const url = "/api/telemetry/evidence.md" + (token ? `?access_token=${encodeURIComponent(token)}` : "");
      window.open(url, "_blank");
    }

    function dist(obj, labels) {
      const entries = Object.entries(obj || {});
      const total = entries.reduce((sum, [, value]) => sum + value, 0) || 1;
      return entries
        .sort((a, b) => b[1] - a[1])
        .map(([key, value]) => ({
          key: (labels && labels[key]) || key,
          count: value,
          pct: Math.round((100 * value) / total),
        }));
    }

    const stageRows = computed(() => dist(summary.value && summary.value.serving.loads_by_stage,
      Object.fromEntries(Object.entries(STAGE_LABEL_KEYS).map(([key, labelKey]) => [key, L(labelKey)]))));
    const failRows = computed(() => dist(summary.value && summary.value.serving.failures_by_stage));
    const policyRows = computed(() => dist(summary.value && summary.value.serving.by_policy));
    const profileRows = computed(() => dist(summary.value && summary.value.serving.by_client_profile));
    const capabilityRows = computed(() => dist(summary.value && summary.value.serving.by_capability));
    const scaleRows = computed(() => dist(summary.value && summary.value.serving.by_scene_scale, SCALE_LABELS));
    const browserRows = computed(() => dist(summary.value && summary.value.clients.browser));
    const osRows = computed(() => dist(summary.value && summary.value.clients.os));
    const deviceRows = computed(() => dist(summary.value && summary.value.clients.device));

    function fmtStat(stat) {
      if (!stat || !stat.count) return "–";
      return `n=${stat.count} · p50=${stat.p50} · p95=${stat.p95} · max=${stat.max}`;
    }

    function fmtBytes(value) {
      const bytes = Number(value || 0);
      if (bytes <= 0) return "0";
      const units = ["B", "KB", "MB", "GB", "TB"];
      let index = 0;
      let shown = bytes;
      while (shown >= 1024 && index < units.length - 1) { shown /= 1024; index += 1; }
      return `${shown >= 100 ? Math.round(shown) : shown.toFixed(1)} ${units[index]}`;
    }

    function fmtTime(iso) {
      if (!iso) return "-";
      return String(iso).replace("T", " ").slice(5, 19);
    }

    function pctText(value) {
      const rate = Number(value || 0);
      return `${(rate * 100).toFixed(rate > 0 && rate < 0.01 ? 2 : 1)}%`;
    }

    const metricRows = computed(() => {
      const serving = summary.value && summary.value.serving;
      if (!serving) return [];
      return [
        { label: L("mTTFR"), stat: serving.ttfr_ms },
        { label: L("mFps"), stat: serving.fps },
        { label: L("mP95"), stat: serving.p95_frame_ms },
        { label: L("mBytes"), stat: serving.bytes },
      ];
    });

    const http = computed(() => (summary.value && summary.value.http) || {});
    const serving = computed(() => (summary.value && summary.value.serving) || {});
    const recentFailures = computed(() => (http.value.recent_failures || []).slice(-8).reverse());

    onMounted(load);

    return {
      store, summary, loading, load, openEvidence, notAdmin, L,
      stageRows, failRows, policyRows, profileRows, capabilityRows, scaleRows,
      browserRows, osRows, deviceRows, metricRows, http, serving, recentFailures,
      fmtStat, fmtBytes, fmtTime, pctText,
    };
  },
  template: `
    <div class="page">
      <div class="page-head">
        <div>
          <div class="page-title">{{ L("title") }}</div>
          <div class="page-sub">{{ L("sub") }}</div>
        </div>
        <div class="page-actions">
          <ui-button icon="refresh" :disabled="loading" @click="load">{{ L("refresh") }}</ui-button>
          <ui-button variant="primary" icon="download" @click="openEvidence">{{ L("evidence") }}</ui-button>
        </div>
      </div>

      <div class="card" v-if="notAdmin" style="margin-bottom:20px;border-color:var(--accent-border)">
        <div class="card-body row-wrap" style="justify-content:space-between">
          <div class="row" style="gap:12px">
            <icon name="info" style="width:18px;height:18px;color:var(--accent)"></icon>
            <div class="small">{{ L("adminOnly") }}</div>
          </div>
        </div>
      </div>

      <div class="grid-4" style="margin-bottom:20px" v-if="!notAdmin">
        <ui-stat :label="L('loads')" :value="serving.loads ?? '–'" :hint="L('loadsHint')" />
        <ui-stat :label="L('failRate')" :value="summary ? pctText(serving.failure_rate) : '–'" :hint="L('failRateHint')" />
        <ui-stat :label="L('clients')" :value="serving.unique_clients ?? '–'" :hint="L('clientsHint')" />
        <ui-stat :label="L('bench')" :value="serving.benchmark_loads ?? '–'" :hint="L('benchHint')" />
      </div>

      <div class="grid-2" style="margin-bottom:20px" v-if="!notAdmin">
        <ui-card :title="L('quality')" dense>
          <table class="tbl" v-if="summary">
            <thead>
              <tr><th>{{ L('metric') }}</th><th style="text-align:right">{{ L('samples') }}</th><th style="text-align:right">p50</th><th style="text-align:right">p95</th><th style="text-align:right">max</th></tr>
            </thead>
            <tbody>
              <tr v-for="row in metricRows" :key="row.label">
                <td class="cell-main">{{ row.label }}</td>
                <td class="faint" style="text-align:right">{{ row.stat && row.stat.count ? row.stat.count : '–' }}</td>
                <td style="text-align:right">{{ row.stat && row.stat.count ? row.stat.p50 : '–' }}</td>
                <td style="text-align:right">{{ row.stat && row.stat.count ? row.stat.p95 : '–' }}</td>
                <td style="text-align:right">{{ row.stat && row.stat.count ? row.stat.max : '–' }}</td>
              </tr>
            </tbody>
          </table>
        </ui-card>

        <div class="stack">
          <ui-card :title="L('stage')" dense>
            <div class="card-body" style="padding-top:2px">
              <div v-for="row in stageRows" :key="row.key" style="margin-bottom:10px">
                <div class="row" style="justify-content:space-between;margin-bottom:3px">
                  <span class="small">{{ row.key }}</span>
                  <span class="small faint">{{ row.count }} · {{ row.pct }}%</span>
                </div>
                <ui-progress :value="row.pct" :success="row.key !== L('stageFailed')"></ui-progress>
              </div>
              <template v-if="failRows.length">
                <div class="small muted" style="margin:10px 0 4px">{{ L('failStages') }}</div>
                <div v-for="row in failRows" :key="row.key" class="row" style="justify-content:space-between">
                  <span class="small">{{ row.key }}</span>
                  <span class="small faint">{{ row.count }}</span>
                </div>
              </template>
            </div>
          </ui-card>
        </div>
      </div>

      <div class="grid-2" style="margin-bottom:20px" v-if="!notAdmin">
        <ui-card :title="L('dist')" dense>
          <div class="card-body" style="padding-top:2px">
            <div class="small muted" style="margin-bottom:4px">{{ L('policy') }}</div>
            <div v-for="row in policyRows" :key="'p' + row.key" class="row" style="justify-content:space-between">
              <span class="small">{{ row.key }}</span><span class="small faint">{{ row.count }}</span>
            </div>
            <div class="small muted" style="margin:10px 0 4px">{{ L('profile') }}</div>
            <div v-for="row in profileRows" :key="'pr' + row.key" class="row" style="justify-content:space-between">
              <span class="small">{{ row.key }}</span><span class="small faint">{{ row.count }}</span>
            </div>
            <div class="small muted" style="margin:10px 0 4px">{{ L('sceneScale') }}</div>
            <div v-for="row in scaleRows" :key="'sc' + row.key" class="row" style="justify-content:space-between">
              <span class="small">{{ row.key }}</span><span class="small faint">{{ row.count }}</span>
            </div>
            <div class="small muted" style="margin:10px 0 4px">{{ L('capability') }}</div>
            <div v-for="row in capabilityRows" :key="'ca' + row.key" class="row" style="justify-content:space-between">
              <span class="small">{{ row.key }}</span><span class="small faint">{{ row.count }}</span>
            </div>
          </div>
        </ui-card>

        <div class="stack">
          <ui-card :title="L('visitors')" dense>
            <div class="card-body" style="padding-top:2px">
              <div class="row-wrap" style="gap:24px">
                <div>
                  <div class="small muted" style="margin-bottom:4px">{{ L('browser') }}</div>
                  <div v-for="row in browserRows" :key="'b' + row.key" class="row" style="justify-content:space-between;gap:16px">
                    <span class="small">{{ row.key }}</span><span class="small faint">{{ row.count }}</span>
                  </div>
                </div>
                <div>
                  <div class="small muted" style="margin-bottom:4px">{{ L('os') }}</div>
                  <div v-for="row in osRows" :key="'o' + row.key" class="row" style="justify-content:space-between;gap:16px">
                    <span class="small">{{ row.key }}</span><span class="small faint">{{ row.count }}</span>
                  </div>
                </div>
                <div>
                  <div class="small muted" style="margin-bottom:4px">{{ L('device') }}</div>
                  <div v-for="row in deviceRows" :key="'d' + row.key" class="row" style="justify-content:space-between;gap:16px">
                    <span class="small">{{ row.key }}</span><span class="small faint">{{ row.count }}</span>
                  </div>
                </div>
              </div>
            </div>
          </ui-card>
          <ui-card :title="L('httpTitle')" dense>
            <div class="card-body" style="padding-top:2px" v-if="summary">
              <div class="row-wrap" style="gap:24px">
                <span class="small">{{ L('requests') }}: <b>{{ http.requests ?? 0 }}</b></span>
                <span class="small">2xx: <b>{{ http.status && http.status['2xx'] || 0 }}</b></span>
                <span class="small">4xx: <b>{{ http.status && http.status['4xx'] || 0 }}</b></span>
                <span class="small">5xx: <b>{{ http.status && http.status['5xx'] || 0 }}</b></span>
                <span class="small">{{ L('bytesServed') }}: <b>{{ fmtBytes(http.bytes_served) }}</b></span>
                <span class="small">{{ L('latency') }} p95: <b>{{ http.latency_ms && http.latency_ms.count ? http.latency_ms.p95 + ' ms' : '–' }}</b></span>
              </div>
            </div>
          </ui-card>
        </div>
      </div>

      <ui-card :title="L('recent')" dense v-if="!notAdmin">
        <div class="card-body" style="padding-top:2px">
          <div v-if="!recentFailures.length" class="small muted">{{ L('noFailures') }}</div>
          <table v-else class="tbl">
            <thead>
              <tr><th>{{ L('time') }}</th><th>{{ L('path') }}</th><th style="text-align:right">{{ L('status') }}</th></tr>
            </thead>
            <tbody>
              <tr v-for="(item, index) in recentFailures" :key="index">
                <td class="faint small nowrap">{{ fmtTime(item.t) }}</td>
                <td class="small ellipsis">{{ item.path }}</td>
                <td class="small" style="text-align:right">{{ item.status }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </ui-card>
    </div>
  `,
};
