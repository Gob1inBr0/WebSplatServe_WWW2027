// Algorithms page — install status of every catalog algorithm on the GPU
// server: one-click install (clone → venv → compile → patch → deps → smoke →
// wrapper → registry), live step progress, failure reasons with retry, log
// drawer, server repo scan, and custom https repo installs.

import { store, navigate, remoteConfig, hasPassword, toast } from "../store.js";
import { t } from "../i18n.js";
import {
  getAlgorithmsCatalog,
  scanAlgorithmsCatalog,
  installAlgorithm,
  retryAlgorithmInstall,
  uninstallAlgorithm,
  getJobLogDelta,
} from "../api.js";

const { computed, onMounted, onBeforeUnmount, ref, watch } = Vue;

const TERMINAL = new Set(["completed", "failed", "canceled", "partial_success",
  "training_success_render_failed", "training_success_metrics_failed", "training_success_postprocess_failed"]);

function isTerminal(job) {
  return TERMINAL.has(String(job?.status || "").toLowerCase());
}

export default {
  name: "AlgorithmsPage",
  setup() {
    const catalog = ref([]);
    const counts = ref({});
    const loading = ref(true);
    const scanning = ref(false);
    const filter = ref("all");
    const search = ref("");
    const customOpen = ref(false);
    const custom = Vue.ref({ name: "", repoUrl: "", entry: "train.py" });
    const installingAll = ref(false);
    const logDrawer = Vue.ref({ open: false, jobId: "", name: "", lines: [], cursor: 0 });

    async function loadCatalog() {
      loading.value = true;
      try {
        const data = await getAlgorithmsCatalog();
        catalog.value = data.algorithms || [];
        counts.value = data.counts || {};
      } catch (err) {
        toast(`${t("alg.loadFailed")}: ${err.message}`, "error");
      } finally {
        loading.value = false;
      }
    }

    async function scanServer() {
      if (!hasPassword() && !remoteConfig().key_path) {
        toast(t("alg.needProfile"), "error");
        return;
      }
      scanning.value = true;
      try {
        const data = await scanAlgorithmsCatalog(remoteConfig());
        catalog.value = data.algorithms || [];
        counts.value = data.counts || {};
        toast(t("alg.scanDone"), "success");
      } catch (err) {
        toast(`${t("alg.scanFailed")}: ${err.message}`, "error", 8000);
      } finally {
        scanning.value = false;
      }
    }

    function liveJob(entry) {
      const jobId = String(entry.active_job_id || "");
      if (!jobId) return null;
      const job = store.jobs.find((j) => j.id === jobId);
      return job && !isTerminal(job) ? job : null;
    }

    function entrySteps(entry) {
      const job = liveJob(entry);
      const steps = (job && job.setup_steps) || entry.setup_steps || [];
      return Array.isArray(steps) ? steps : [];
    }

    function stepCount(entry, status) {
      return entrySteps(entry).filter((s) => s.status === status).length;
    }

    function progressPct(entry) {
      const steps = entrySteps(entry);
      if (!steps.length) return 0;
      return Math.round((steps.filter((s) => s.status === "success").length / steps.length) * 100);
    }

    function currentStepDetail(entry) {
      const steps = entrySteps(entry);
      const active = steps.find((s) => s.status === "running") || steps[steps.length - 1];
      if (!active) return "";
      return `${t(`alg.step.${active.name}`) || active.name}${active.detail ? ` · ${active.detail}` : ""}`;
    }

    function statusMeta(entry) {
      const live = liveJob(entry);
      if (live || entry.status === "installing") {
        return { kind: "info", label: `${t("alg.status.installing")} ${progressPct(entry)}%`, icon: "loader", spin: true };
      }
      switch (entry.status) {
        case "ready":
          return { kind: "success", label: entry.manual ? t("alg.status.readyManual") : t("alg.status.ready"), icon: "check-circle", spin: false };
        case "failed":
          return { kind: "danger", label: t("alg.status.failed"), icon: "x-circle", spin: false };
        case "discovered":
          return { kind: "neutral", label: t("alg.status.discovered"), icon: "eye", spin: false };
        default:
          return { kind: "neutral", label: t("alg.status.notInstalled"), icon: "download", spin: false };
      }
    }

    async function install(name, { repoUrl = "", entry = "", label = "" } = {}) {
      if (!hasPassword() && !remoteConfig().key_path) {
        toast(t("alg.needProfile"), "error");
        return;
      }
      try {
        await installAlgorithm({ name, repo_url: repoUrl, entry, label, remote: remoteConfig() });
        toast(`${t("alg.installQueued")}: ${name}`, "success");
      } catch (err) {
        toast(`${name}: ${err.message}`, "error", 9000);
        return;
      }
      await loadCatalog();
    }

    async function retry(name) {
      try {
        await retryAlgorithmInstall(name, remoteConfig());
        toast(`${t("alg.installQueued")}: ${name}`, "success");
      } catch (err) {
        toast(`${name}: ${err.message}`, "error", 9000);
        return;
      }
      await loadCatalog();
    }

    async function uninstall(entry) {
      // The repo directory is kept by default (user data safety); only the
      // venv, step markers, and registry entry are removed.
      if (!window.confirm(t("alg.uninstallConfirm").replace("{name}", entry.name))) return;
      try {
        await uninstallAlgorithm(entry.name, remoteConfig(), false);
        toast(`${t("alg.uninstalled")}: ${entry.name}`, "success");
      } catch (err) {
        toast(`${entry.name}: ${err.message}`, "error", 9000);
        return;
      }
      await loadCatalog();
    }

    async function installAllMissing() {
      const missing = catalog.value.filter(
        (e) => (e.status === "not_installed" || e.status === "discovered") && e.repo_url && !liveJob(e),
      );
      if (!missing.length) {
        toast(t("alg.noneMissing"), "info");
        return;
      }
      if (!hasPassword() && !remoteConfig().key_path) {
        toast(t("alg.needProfile"), "error");
        return;
      }
      installingAll.value = true;
      // Sequential on purpose: the server caps concurrent installs at 2 and
      // each install is heavy (clone + CUDA compile); one at a time keeps the
      // machine responsive and the log readable.
      let queued = 0;
      for (const entry of missing) {
        try {
          await installAlgorithm({ name: entry.name, remote: remoteConfig() });
          queued += 1;
          await new Promise((resolve) => setTimeout(resolve, 500));
        } catch (err) {
          toast(`${entry.name}: ${err.message}`, "error", 9000);
        }
      }
      installingAll.value = false;
      if (queued) {
        toast(t("alg.installAllQueued").replace("{n}", String(queued)), "success", 6000);
        await loadCatalog();
      }
    }

    async function submitCustom() {
      const name = String(custom.value.name || "").trim();
      const repoUrl = String(custom.value.repoUrl || "").trim();
      const entry = String(custom.value.entry || "").trim() || "train.py";
      if (!name || !repoUrl) {
        toast(t("alg.customRequired"), "error");
        return;
      }
      if (!/^https:\/\//.test(repoUrl)) {
        toast(t("alg.customHttps"), "error");
        return;
      }
      await install(name, { repoUrl, entry });
      custom.value = { name: "", repoUrl: "", entry: "train.py" };
      customOpen.value = false;
    }

    /* ---------- log drawer ---------- */

    let logTimer = null;

    async function pollLog() {
      const drawer = logDrawer.value;
      if (!drawer.open || !drawer.jobId) return;
      try {
        const data = await getJobLogDelta(drawer.jobId, drawer.cursor);
        drawer.cursor = data.cursor || drawer.cursor;
        if (data.log_lines?.length) drawer.lines.push(...data.log_lines);
        if (drawer.lines.length > 2000) drawer.lines.splice(0, drawer.lines.length - 2000);
      } catch { /* transient — next tick retries */ }
    }

    function openLog(entry) {
      const job = liveJob(entry) || store.jobs.find(
        (j) => j.job_type === "env_setup" && j.algorithm_family === entry.name,
      );
      if (!job) {
        toast(t("alg.noLogYet"), "info");
        return;
      }
      logDrawer.value = { open: true, jobId: job.id, name: entry.name, lines: [], cursor: 0 };
      clearInterval(logTimer);
      pollLog();
      logTimer = setInterval(pollLog, 2000);
    }

    function closeLog() {
      logDrawer.value = { ...logDrawer.value, open: false };
      clearInterval(logTimer);
      logTimer = null;
    }

    onBeforeUnmount(() => {
      clearInterval(logTimer);
      logTimer = null;
    });

    /* ---------- derived list ---------- */

    const filtered = computed(() => {
      const text = search.value.trim().toLowerCase();
      return catalog.value.filter((entry) => {
        if (filter.value === "ready" && entry.status !== "ready") return false;
        if (filter.value === "missing" && !["not_installed", "discovered", "failed"].includes(entry.status)) return false;
        if (filter.value === "installing" && !liveJob(entry)) return false;
        if (text && !`${entry.name} ${entry.label}`.toLowerCase().includes(text)) return false;
        return true;
      }).sort((a, b) => {
        const rank = (e) => (liveJob(e) ? 0 : e.status === "failed" ? 1 : e.status === "ready" ? 2 : 3);
        const diff = rank(a) - rank(b);
        return diff !== 0 ? diff : String(a.name).localeCompare(String(b.name));
      });
    });

    // Refresh the catalog when an install job settles (the snapshot registry
    // and adapter overrides change at that moment).
    watch(
      () => store.jobs
        .filter((j) => j.job_type === "env_setup")
        .map((j) => `${j.id}:${j.status}`)
        .join("|"),
      (next, prev) => {
        if (prev === undefined) return;
        const finished = next.split("|").some((part) => {
          const [id, status] = part.split(":");
          const before = (prev || "").split("|").find((p) => p.startsWith(`${id}:`));
          return before && before.split(":")[1] !== status && isTerminal({ status });
        });
        if (finished) loadCatalog();
      },
    );

    onMounted(loadCatalog);

    return {
      store, navigate, catalog, counts, loading, scanning, filter, search,
      customOpen, custom, installingAll, logDrawer,
      filtered, liveJob, entrySteps, stepCount, progressPct, currentStepDetail, statusMeta,
      loadCatalog, scanServer, install, retry, uninstall, installAllMissing, submitCustom,
      openLog, closeLog,
    };
  },
  template: `
    <div class="page">
      <div class="page-head">
        <div>
          <div class="page-title">{{ $t("alg.title") }}</div>
          <div class="page-sub">{{ $t("alg.sub") }}</div>
        </div>
        <div class="row" style="gap:8px;flex-wrap:wrap">
          <ui-button size="sm" icon="refresh" :loading="loading" @click="loadCatalog">{{ $t("alg.refresh") }}</ui-button>
          <ui-button size="sm" icon="eye" :loading="scanning" @click="scanServer">{{ $t("alg.scan") }}</ui-button>
          <ui-button size="sm" variant="primary" icon="download" :loading="installingAll" @click="installAllMissing">{{ $t("alg.installAll") }}</ui-button>
        </div>
      </div>

      <div class="row" style="gap:8px;flex-wrap:wrap;margin-bottom:14px">
        <button v-for="f in ['all','ready','installing','missing']" :key="f"
                class="btn btn-sm" :class="filter === f ? 'btn-primary' : 'btn-ghost'"
                @click="filter = f">{{ $t("alg.filter." + f) }}</button>
        <span class="small muted" style="margin-left:auto">
          {{ $t("alg.counts").replace("{ready}", counts.ready || 0).replace("{installing}", counts.installing || 0)
             .replace("{failed}", counts.failed || 0).replace("{missing}", counts.not_installed || 0) }}
        </span>
        <input class="input" style="width:180px" :placeholder="$t('alg.search')" v-model="search" />
      </div>

      <ui-spinner v-if="loading && !catalog.length"></ui-spinner>

      <ui-empty v-else-if="!catalog.length" icon="cpu" :title="$t('alg.none')" :hint="$t('alg.noneHint')">
        <ui-button variant="primary" size="sm" icon="eye" :loading="scanning" @click="scanServer">{{ $t("alg.scan") }}</ui-button>
      </ui-empty>

      <div v-else class="stack">
        <div v-for="entry in filtered" :key="entry.name" class="card">
          <div class="card-body" style="padding:14px 16px">
            <div class="spread" style="gap:12px;flex-wrap:wrap">
              <div class="row" style="gap:10px;min-width:0">
                <icon :name="statusMeta(entry).icon" :class="{ 'up-spin': statusMeta(entry).spin }"
                      style="width:16px;height:16px;flex:none"
                      :style="{ color: statusMeta(entry).kind === 'success' ? 'var(--ok)' : statusMeta(entry).kind === 'danger' ? 'var(--bad)' : 'var(--text-3)' }"></icon>
                <div style="min-width:0">
                  <div class="ellipsis" style="font-weight:650">{{ entry.label || entry.name }}</div>
                  <div class="small faint ellipsis mono" style="max-width:420px">{{ entry.name }}<span v-if="entry.repo_dir"> · {{ entry.repo_dir }}</span></div>
                </div>
              </div>
              <div class="row" style="gap:6px;flex-wrap:wrap">
                <ui-badge :kind="statusMeta(entry).kind">{{ statusMeta(entry).label }}</ui-badge>
                <ui-button v-if="liveJob(entry) || entry.active_job_id" size="sm" variant="ghost" icon="terminal" @click="openLog(entry)">{{ $t("alg.viewLog") }}</ui-button>
                <ui-button v-if="entry.status === 'ready' && entry.trainable" size="sm" variant="ghost" icon="play" @click="navigate('wizard')">{{ $t("alg.train") }}</ui-button>
                <ui-button v-if="entry.status === 'failed'" size="sm" variant="primary" icon="rotate" @click="retry(entry.name)">{{ $t("alg.retry") }}</ui-button>
                <ui-button v-if="['not_installed','discovered'].includes(entry.status) && (entry.repo_url || entry.repo_dir)" size="sm" variant="primary" icon="download" @click="install(entry.name)">{{ $t("alg.install") }}</ui-button>
                <ui-button v-if="entry.status === 'ready' && entry.source === 'registry'" size="sm" variant="ghost" icon="trash" @click="uninstall(entry)">{{ $t("alg.uninstall") }}</ui-button>
              </div>
            </div>

            <div v-if="liveJob(entry)" style="margin-top:10px">
              <div class="spread small">
                <span class="muted">{{ currentStepDetail(entry) }}</span>
                <span class="muted">{{ progressPct(entry) }}%</span>
              </div>
              <ui-progress :value="progressPct(entry)"></ui-progress>
            </div>

            <div v-if="entry.status === 'failed'" class="small" style="margin-top:8px;color:var(--bad)">
              <icon name="alert" style="width:12px;height:12px;vertical-align:-2px"></icon>
              {{ entry.failure_reason || $t("alg.failedGeneric") }}
              <ui-button size="sm" variant="ghost" icon="terminal" @click="openLog(entry)">{{ $t("alg.viewLog") }}</ui-button>
            </div>

            <div v-if="entry.status === 'ready' && entry.installed_at" class="small faint" style="margin-top:6px">
              {{ $t("alg.installedAt") }}: {{ entry.installed_at }}<span v-if="entry.entry"> · {{ $t("alg.entry") }}: {{ entry.entry }}</span><span v-if="entry.wrapper"> · wrapper: {{ entry.wrapper }}</span>
            </div>
            <div v-else-if="entry.status === 'ready'" class="small faint" style="margin-top:6px">{{ $t("alg.manualHint") }}</div>
          </div>
        </div>

        <div class="card">
          <div class="card-head" style="cursor:pointer" @click="customOpen = !customOpen">
            <div class="row" style="gap:10px">
              <icon :name="customOpen ? 'chevron-down' : 'chevron-right'" style="width:15px;height:15px;color:var(--text-3)"></icon>
              <div class="card-title">{{ $t("alg.customTitle") }}</div>
            </div>
          </div>
          <div v-if="customOpen" class="card-body">
            <div class="small muted" style="margin-bottom:10px">{{ $t("alg.customHint") }}</div>
            <div class="grid-3">
              <ui-field :label="$t('alg.customName')" :hint="$t('alg.customNameHint')"><input class="input mono" v-model="custom.name" placeholder="my-3dgs" /></ui-field>
              <ui-field :label="$t('alg.customUrl')" :hint="$t('alg.customHttps')"><input class="input mono" v-model="custom.repoUrl" placeholder="https://github.com/org/repo" /></ui-field>
              <ui-field :label="$t('alg.customEntry')" :hint="$t('alg.customEntryHint')"><input class="input mono" v-model="custom.entry" placeholder="train.py" /></ui-field>
            </div>
            <div class="row" style="margin-top:12px">
              <ui-button variant="primary" size="sm" icon="download" @click="submitCustom">{{ $t("alg.customSubmit") }}</ui-button>
            </div>
          </div>
        </div>
      </div>

      <ui-drawer v-if="logDrawer.open" :title="$t('alg.logTitle').replace('{name}', logDrawer.name)" :subtitle="logDrawer.jobId" @close="closeLog">
        <pre class="mono small" style="white-space:pre-wrap;word-break:break-all;margin:0">{{
          logDrawer.lines.length ? logDrawer.lines.join("") : $t("alg.logEmpty")
        }}</pre>
      </ui-drawer>
    </div>
  `,
};
