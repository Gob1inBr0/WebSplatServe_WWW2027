// Settings — connection profiles (multi, ssh-command paste), password per
// session, notifications, access info.

import { store, persistProfiles, persistPrefs, defaultProfile, activeProfile, sessionPasswords, toast, navigate, deriveDataPaths } from "../store.js";
import { parseSshCommand } from "../ssh-parse.js";
import { getSshConfigHosts, probeRemoteDisk, resetRemoteGpu, clearJobHistory } from "../api.js";
import { t } from "../i18n.js";

const { ref, computed } = Vue;

export default {
  name: "SettingsPage",
  setup() {
    const editing = ref(null);       // profile being edited (copy)
    const pasteSsh = ref("");
    const passwordInput = ref("");
    const passwordVersion = ref(0);  // sessionStorage is not reactive; bump to re-evaluate
    const notifySupported = typeof Notification !== "undefined";
    const notifyGranted = notifySupported && Notification.permission === "granted";

    const active = computed(() => activeProfile());
    const hasPassword = computed(() => {
      passwordVersion.value;  // track manual invalidation
      return Boolean(active.value && sessionPasswords.get(active.value.id));
    });

    function newProfile() {
      editing.value = defaultProfile();
    }

    function editProfile(profile) {
      editing.value = { ...profile };
    }

    function applyPaste() {
      const parsed = parseSshCommand(pasteSsh.value);
      if (!parsed || !parsed.host) {
        toast(t("set.parseFail"), "error");
        return;
      }
      if (!editing.value) newProfile();
      if (parsed.host) editing.value.host = parsed.host;
      if (parsed.port) editing.value.port = parsed.port;
      if (parsed.username) editing.value.username = parsed.username;
      if (!editing.value.label) editing.value.label = parsed.host;
      pasteSsh.value = "";
      toast(t("wiz.profileCreated"), "success");
    }

    /* import a host straight from the server machine's ~/.ssh/config */
    const sshHosts = ref([]);
    const sshHostsLoading = ref(false);
    const sshHostsLoaded = ref(false);
    const pickedSshHost = ref("");
    async function loadSshHosts() {
      sshHostsLoading.value = true;
      try {
        const data = await getSshConfigHosts();
        sshHosts.value = data.hosts || [];
        sshHostsLoaded.value = true;
        pickedSshHost.value = "";
        if (!sshHosts.value.length) toast(t("set.sshConfigEmpty"), "info");
      } catch (err) {
        toast(`${t("set.sshConfigFail")} ${err.message}`, "error");
      } finally {
        sshHostsLoading.value = false;
      }
    }
    function applySshHost() {
      const entry = sshHosts.value.find((h) => h.alias === pickedSshHost.value);
      if (!entry) { toast(t("set.sshConfigPick"), "error"); return; }
      if (!editing.value) newProfile();
      editing.value.host = entry.hostname || entry.alias;
      if (entry.port) editing.value.port = entry.port;
      if (entry.user) editing.value.username = entry.user;
      if (entry.identity_file) editing.value.key_path = entry.identity_file;
      editing.value.label = entry.alias;
      pickedSshHost.value = "";
      toast(`${t("set.sshConfigImported")}: ${entry.alias}`, "success");
    }

    function saveProfile() {
      const profile = editing.value;
      if (!profile.host.trim()) { toast(t("set.hostRequired"), "error"); return; }
      if (!profile.label.trim()) profile.label = profile.host;
      const index = store.profiles.findIndex((p) => p.id === profile.id);
      if (index >= 0) store.profiles[index] = profile;
      else store.profiles.push(profile);
      store.activeProfileId = profile.id;
      persistProfiles();
      editing.value = null;
      toast(`${t("set.profileSaved")}: ${profile.label}`, "success");
    }

    function removeProfile(profile) {
      if (!confirm(`${t("set.profileRemovedConfirm")}: ${profile.label || profile.host}?`)) return;
      store.profiles = store.profiles.filter((p) => p.id !== profile.id);
      if (store.activeProfileId === profile.id) {
        store.activeProfileId = store.profiles[0]?.id || "";
      }
      persistProfiles();
    }

    function switchProfile(profile) {
      store.activeProfileId = profile.id;
      persistProfiles();
      toast(`${t("set.switchedTo")} "${profile.label || profile.host}"`, "info");
    }

    /* Re-derive the suggested data paths when the username changes, but only
       while the fields still hold derived values — custom paths stay put. */
    const DERIVED_PATH_RE = /^\/(?:root|home\/[A-Za-z0-9._-]+)\/websplatserve\/(?:workspaces|outputs)$/;
    function onUsernameInput() {
      if (!editing.value) return;
      const paths = deriveDataPaths(editing.value.username);
      if (DERIVED_PATH_RE.test(editing.value.workspace_root || "")) editing.value.workspace_root = paths.workspace_root;
      if (DERIVED_PATH_RE.test(editing.value.output_root || "")) editing.value.output_root = paths.output_root;
    }

    const pathWarnings = computed(() => {
      if (!editing.value) return [];
      const unsafe = (p) => /^\/(?:tmp|dev\/shm)(?:\/|$)/.test(String(p || ""));
      const hits = [];
      if (unsafe(editing.value.workspace_root)) hits.push(`${t("set.pathUnsafeWarn")}: ${editing.value.workspace_root}`);
      if (unsafe(editing.value.output_root)) hits.push(`${t("set.pathUnsafeWarn")}: ${editing.value.output_root}`);
      return hits;
    });

    /* Ask the remote machine where its biggest local disk is, then suggest
       (or silently adopt, when the fields still hold derived values) that
       data root. Never overrides user-customized paths. */
    const probingDisk = ref(false);
    const diskProbe = ref(null);
    async function probeDataDisk() {
      const profile = editing.value;
      if (!profile || !profile.host.trim() || !profile.username.trim()) {
        toast(t("set.probeNeedHost"), "error");
        return;
      }
      if (!sessionPasswords.get(profile.id) && !String(profile.key_path || "").trim()) {
        toast(t("set.probeNeedAuth"), "error");
        return;
      }
      probingDisk.value = true;
      try {
        const data = await probeRemoteDisk({
          host: profile.host,
          port: Number(profile.port) || 22,
          username: profile.username,
          password: sessionPasswords.get(profile.id),
          key_path: String(profile.key_path || "").trim(),
        });
        const disk = data.disk || {};
        diskProbe.value = disk;
        if (!disk.suggested_workspace_root) {
          toast(t("set.probeNone"), "info");
          return;
        }
        const stillDerived = !String(profile.workspace_root || "").trim()
          || DERIVED_PATH_RE.test(profile.workspace_root);
        if (stillDerived) {
          profile.workspace_root = disk.suggested_workspace_root;
          profile.output_root = disk.suggested_output_root;
          toast(`${t("set.probeApplied")}: ${disk.suggested_data_root}`, "success", 8000);
        } else {
          toast(`${t("set.probeKeptCustom")}: ${disk.suggested_data_root}`, "info", 9000);
        }
      } catch (err) {
        toast(`${t("set.probeFailed")} ${err.message}`, "error", 9000);
      } finally {
        probingDisk.value = false;
      }
    }

    /* Force-kill every GPU compute process on the active server (keeper
       included) and clear leftover tmux sessions. Destructive on purpose —
       it also stops other projects' jobs sharing the cards. */
    const resettingGpu = ref(false);
    const gpuResetReport = ref(null);
    const gpuResetSummary = computed(() => {
      const gpus = gpuResetReport.value && gpuResetReport.value.gpus_after;
      if (!Array.isArray(gpus) || !gpus.length) return "";
      return gpus
        .map((g) => "#" + g.index + " " + (g.memory_used_mib ?? "?") + "MiB/" + (g.utilization_percent ?? "?") + "%")
        .join(" · ");
    });
    async function resetGpu() {
      const profile = active.value;
      if (!profile || !profile.host.trim()) {
        toast(t("set.resetNeedProfile"), "error");
        return;
      }
      if (!sessionPasswords.get(profile.id) && !String(profile.key_path || "").trim()) {
        toast(t("set.resetNeedAuth"), "error");
        return;
      }
      if (!window.confirm(t("set.resetConfirm"))) return;
      resettingGpu.value = true;
      gpuResetReport.value = null;
      try {
        const data = await resetRemoteGpu({
          host: profile.host,
          port: Number(profile.port) || 22,
          username: profile.username,
          password: sessionPasswords.get(profile.id),
          key_path: String(profile.key_path || "").trim(),
        });
        gpuResetReport.value = data.reset || {};
        toast(t("set.resetDone"), "success", 8000);
      } catch (err) {
        toast(`${t("set.resetFailed")} ${err.message}`, "error", 9000);
      } finally {
        resettingGpu.value = false;
      }
    }

    /* Clear the local training history — logical delete, like clearing
       browser history: lists go empty, files on disk are untouched. */
    const clearingHistory = ref(false);
    async function clearHistory() {
      if (!window.confirm(t("set.clearConfirm"))) return;
      clearingHistory.value = true;
      try {
        const data = await clearJobHistory();
        toast(`${t("set.clearDone")}: ${data.cleared ?? 0}`, "success", 8000);
      } catch (err) {
        toast(`${t("set.clearFailed")} ${err.message}`, "error", 9000);
      } finally {
        clearingHistory.value = false;
      }
    }

    function savePassword() {
      if (!active.value) { toast(t("set.needProfileFirst"), "error"); return; }
      sessionPasswords.set(active.value.id, passwordInput.value);
      passwordInput.value = "";
      passwordVersion.value += 1;
      toast(t("set.passwordStored"), "success");
    }

    async function askNotifyPermission() {
      if (!notifySupported) return;
      if (Notification.permission !== "granted") {
        const result = await Notification.requestPermission();
        if (result !== "granted") { toast(t("set.notifyDenied"), "error"); return; }
      }
      store.prefs.notifyOnDone = true;
      persistPrefs();
      toast(t("set.notifyEnabled"), "success");
    }

    return {
      store, editing, pasteSsh, passwordInput, notifySupported, active, hasPassword,
      newProfile, editProfile, applyPaste, saveProfile, removeProfile, switchProfile,
      savePassword, askNotifyPermission, persistPrefs, navigate,
      sshHosts, sshHostsLoading, sshHostsLoaded, pickedSshHost, loadSshHosts, applySshHost,
      onUsernameInput, pathWarnings, probingDisk, diskProbe, probeDataDisk,
      resettingGpu, gpuResetReport, gpuResetSummary, resetGpu,
      clearingHistory, clearHistory,
    };
  },
  template: `
    <div class="page" style="max-width: 860px">
      <div class="page-head">
        <div>
          <div class="page-title">{{ $t("set.title") }}</div>
          <div class="page-sub">{{ $t("set.sub") }}</div>
        </div>
        <div class="page-actions">
          <ui-button variant="primary" icon="plus" @click="newProfile">{{ $t("set.newProfile") }}</ui-button>
        </div>
      </div>

      <!-- profiles -->
      <ui-card :title="$t('set.profiles')" style="margin-bottom:20px">
        <template #actions>
          <span class="faint small">{{ store.profiles.length }} {{ $t("set.saved") }}</span>
        </template>

        <div style="display:flex;flex-direction:column;gap:8px;margin-bottom:14px">
          <div v-for="profile in store.profiles" :key="profile.id"
               class="check-item" :style="profile.id === store.activeProfileId ? 'border-color:var(--accent-border)' : ''">
            <icon :name="profile.id === store.activeProfileId ? 'check-circle' : 'link'"
                  :style="profile.id === store.activeProfileId ? 'color:var(--accent)' : ''"></icon>
            <div style="flex:1;min-width:0">
              <div class="ci-name">{{ profile.label || profile.host }}
                <ui-badge v-if="profile.id === store.activeProfileId" kind="accent" style="margin-left:6px">{{ $t("set.activeBadge") }}</ui-badge>
              </div>
              <div class="ci-msg mono">{{ profile.username }}@{{ profile.host }}:{{ profile.port }}</div>
            </div>
            <ui-button v-if="profile.id !== store.activeProfileId" size="sm" variant="ghost" @click="switchProfile(profile)">{{ $t("set.use") }}</ui-button>
            <ui-button size="sm" variant="ghost" icon="settings" @click="editProfile(profile)">{{ $t("set.edit") }}</ui-button>
            <ui-button size="sm" variant="ghost" icon="trash" @click="removeProfile(profile)"></ui-button>
          </div>
          <div v-if="!store.profiles.length" class="small muted">{{ $t("set.noProfiles") }}</div>
        </div>

        <template v-if="editing">
          <div class="card" style="background:var(--bg-inset);padding:16px">
            <ui-field :label="$t('set.pasteSsh')" :hint="$t('set.pasteSshHint')"
                      style="margin-bottom:12px">
              <div class="row" style="gap:8px">
                <input class="input mono" style="flex:1" v-model="pasteSsh" placeholder="ssh -p 22 root@your.server" @keydown.enter="applyPaste" />
                <ui-button icon="zap" @click="applyPaste">{{ $t("set.parse") }}</ui-button>
              </div>
            </ui-field>
            <ui-field :label="$t('set.sshConfig')" :hint="$t('set.sshConfigHint')"
                      style="margin-bottom:12px">
              <div class="row" style="gap:8px">
                <select class="input" style="flex:1" v-model="pickedSshHost" :disabled="!sshHosts.length">
                  <option value="">{{ sshHosts.length ? $t("set.sshConfigPick") : $t("set.sshConfigNone") }}</option>
                  <option v-for="h in sshHosts" :key="h.alias" :value="h.alias">
                    {{ h.alias }} — {{ h.user ? h.user + "@" : "" }}{{ h.hostname || h.alias }}{{ h.port && h.port !== 22 ? ":" + h.port : "" }}
                  </option>
                </select>
                <ui-button icon="download" :disabled="sshHostsLoading" @click="loadSshHosts">{{ sshHostsLoaded ? $t("set.reload") : $t("set.sshConfigLoad") }}</ui-button>
                <ui-button variant="primary" icon="check" :disabled="!pickedSshHost" @click="applySshHost">{{ $t("set.sshConfigImport") }}</ui-button>
              </div>
            </ui-field>
            <div class="grid-3" style="margin-bottom:12px">
              <ui-field :label="$t('set.label')"><input class="input" v-model="editing.label" placeholder="My GPU box" /></ui-field>
              <ui-field :label="$t('set.host')" required><input class="input" v-model="editing.host" placeholder="connect.gpu-cloud.com" /></ui-field>
              <div class="grid-2" style="gap:8px">
                <ui-field :label="$t('set.port')"><input class="input num" type="number" v-model.number="editing.port" /></ui-field>
                <ui-field :label="$t('set.user')" :hint="$t('set.userDeriveHint')"><input class="input" v-model="editing.username" @input="onUsernameInput" /></ui-field>
              </div>
            </div>
            <div class="grid-2" style="margin-bottom:12px">
              <ui-field :label="$t('set.repoPath')" :hint="$t('set.repoPathHint')"><input class="input mono" v-model="editing.repo_path" placeholder="/root/autodl-tmp/WebSplatServe" /></ui-field>
              <ui-field :label="$t('set.python')" :hint="$t('set.pythonHint')"><input class="input mono" v-model="editing.python" /></ui-field>
            </div>
            <div class="grid-2" style="margin-bottom:8px">
              <ui-field :label="$t('set.workspaceRoot')" :hint="$t('set.workspaceHint')"><input class="input mono" v-model="editing.workspace_root" /></ui-field>
              <ui-field :label="$t('set.outputRoot')" :hint="$t('set.outputHint')"><input class="input mono" v-model="editing.output_root" /></ui-field>
            </div>
            <div v-if="pathWarnings.length" class="small" style="color:var(--warn,#e6b450);margin-bottom:8px">
              <div v-for="w in pathWarnings" :key="w">⚠ {{ w }}</div>
            </div>
            <div class="row" style="gap:8px;margin-bottom:14px">
              <ui-button size="sm" icon="hard-drive" :disabled="probingDisk" @click="probeDataDisk">{{ probingDisk ? $t("set.probeDisking") : $t("set.probeDisk") }}</ui-button>
              <span v-if="diskProbe && diskProbe.candidates && diskProbe.candidates.length" class="small muted">
                {{ diskProbe.candidates.length }} {{ $t("set.probeFound") }}
              </span>
            </div>
            <ui-field :label="$t('set.keyPath')" :hint="$t('set.keyPathHint')"
                      style="margin-bottom:12px">
              <input class="input mono" v-model="editing.key_path" placeholder="~/.ssh/id_ed25519" />
            </ui-field>
            <ui-field :label="$t('set.activateCmd')" :hint="$t('set.activateHint')"
                      style="margin-bottom:14px">
              <input class="input mono" v-model="editing.activate_cmd" placeholder="source … && conda activate env" />
            </ui-field>
            <div class="row" style="justify-content:flex-end;gap:8px">
              <ui-button variant="ghost" @click="editing = null">{{ $t("wiz.cancel") }}</ui-button>
              <ui-button variant="primary" icon="check" @click="saveProfile">{{ $t("set.save") }}</ui-button>
            </div>
          </div>
        </template>
      </ui-card>

      <!-- password for active profile -->
      <!-- training history -->
      <ui-card :title="$t('set.clearTitle')" style="margin-bottom:20px">
        <div class="card-body" style="padding-top:2px">
          <p class="small muted" style="margin-bottom:10px">{{ $t("set.clearDesc") }}</p>
          <div class="row" style="gap:8px">
            <ui-button size="sm" icon="trash" :disabled="clearingHistory"
                       @click="clearHistory">{{ clearingHistory ? $t("set.clearWorking") : $t("set.clearButton") }}</ui-button>
          </div>
        </div>
      </ui-card>

      <!-- server training reset -->
      <ui-card :title="$t('set.resetTitle')" style="margin-bottom:20px;border-color:var(--warn,#e6b450)">
        <div class="card-body" style="padding-top:2px">
          <p class="small muted" style="margin-bottom:10px">{{ $t("set.resetDesc") }}</p>
          <div class="row" style="gap:8px;margin-bottom:10px">
            <ui-button size="sm" icon="rotate" :disabled="resettingGpu || !active"
                       @click="resetGpu">{{ resettingGpu ? $t("set.resetWorking") : $t("set.resetButton") }}</ui-button>
            <span v-if="active" class="small muted">{{ active.label || active.host }}</span>
          </div>
          <div v-if="gpuResetReport" class="small mono">
            <div>{{ $t("set.resetKilled") }}: {{ gpuResetReport.killed_count }}</div>
            <div>{{ $t("set.resetKeeper") }}: {{ gpuResetReport.keeper_patterns_matched }}</div>
            <div>{{ $t("set.resetSessions") }}: {{ gpuResetReport.wgsc_sessions_left }}</div>
            <div v-if="gpuResetSummary">GPU: {{ gpuResetSummary }}</div>
          </div>
        </div>
      </ui-card>

      <ui-card :title="$t('set.password')" style="margin-bottom:20px">
        <p class="small muted" style="margin-bottom:12px">
          {{ $t("set.passwordFor") }} <strong>{{ active ? (active.label || active.host) : "—" }}</strong>.
          {{ $t("set.passwordBody") }}
        </p>
        <div class="row" style="gap:8px;max-width:440px">
          <input class="input" type="password" v-model="passwordInput" :placeholder="$t('set.passwordPlaceholder')"
                 @keydown.enter="savePassword" />
          <ui-button variant="primary" @click="savePassword" :disabled="!passwordInput">{{ $t("set.save") }}</ui-button>
        </div>
        <div class="row" style="gap:6px;margin-top:10px">
          <span class="dot" :class="{ on: hasPassword, warn: !hasPassword }"></span>
          <span class="small" :class="hasPassword ? 'muted' : 'faint'">
            {{ hasPassword ? $t("set.passwordReady") : $t("set.passwordMissing") }}
          </span>
        </div>
      </ui-card>

      <!-- notifications -->
      <ui-card :title="$t('set.notifications')" style="margin-bottom:20px">
        <div class="spread">
          <div>
            <div style="font-weight:650" class="small">{{ $t("set.notifyOnDone") }}</div>
            <div class="small muted">{{ $t("set.notifyHint") }}</div>
          </div>
          <template v-if="!notifySupported">
            <ui-badge kind="neutral">{{ $t("set.notSupported") }}</ui-badge>
          </template>
          <template v-else>
            <ui-button v-if="notifySupported && !notifyGranted" size="sm" icon="bell" @click="askNotifyPermission">{{ $t("set.enable") }}</ui-button>
            <label v-else class="checkbox-row">
              <input type="checkbox" v-model="store.prefs.notifyOnDone" @change="persistPrefs" />
              {{ store.prefs.notifyOnDone ? $t("set.on") : $t("set.off") }}
            </label>
          </template>
        </div>
      </ui-card>

      <!-- access -->
      <ui-card :title="$t('set.access')">
        <dl class="kv">
          <dt>{{ $t("set.consoleUrl") }}</dt><dd class="mono">{{ $t("set.consoleUrlValue") }}</dd>
          <dt>{{ $t("set.accessToken") }}</dt><dd>{{ $t("set.accessTokenValue") }}</dd>
          <dt>{{ $t("set.lan") }}</dt><dd>{{ $t("set.lanValue") }}</dd>
          <dt>{{ $t("set.oldUi") }}</dt><dd>{{ $t("set.oldUiValue") }}</dd>
        </dl>
      </ui-card>
    </div>
  `,
};
