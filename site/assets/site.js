const numberFormat = new Intl.NumberFormat("en-US");
const bytesFormat = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 1,
});

const fileRows = document.getElementById("fileRows");
const dataUpdatedAt = document.getElementById("dataUpdatedAt");
const totalRecords = document.getElementById("totalRecords");
const recordsByCountry = {
  de: document.getElementById("recordsDe"),
  at: document.getElementById("recordsAt"),
  ch: document.getElementById("recordsCh"),
};

const formatBytes = (bytes) => {
  if (!Number.isFinite(bytes)) return "Manifest";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${bytesFormat.format(value)} ${units[unitIndex]}`;
};

const shortHash = (value) => {
  if (typeof value !== "string" || value.length < 12) return "Manifest";
  return `${value.slice(0, 12)}...`;
};

const formatGeneratedAt = (value) => {
  if (!value) return "Manifest unavailable";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
};

const formatKind = (path) => path.split(".").pop().toUpperCase();

const updateManifestSummary = (manifest) => {
  dataUpdatedAt.textContent = formatGeneratedAt(
    manifest.data_refreshed_at || manifest.generated_at,
  );
  const countryTotals = { de: 0, at: 0, ch: 0 };
  for (const file of manifest.files || []) {
    if (!file.path || !file.path.endsWith(".csv")) continue;
    const country = file.path.slice(0, 2);
    if (country in countryTotals) {
      countryTotals[country] += Number(file.records || 0);
    }
  }

  let total = 0;
  for (const [country, records] of Object.entries(countryTotals)) {
    total += records;
    if (recordsByCountry[country]) {
      recordsByCountry[country].textContent = numberFormat.format(records);
    }
  }
  if (total > 0) {
    totalRecords.textContent = numberFormat.format(total);
  }
};

const renderFileRows = (manifest) => {
  const files = (manifest.files || []).filter((file) =>
    /post_code\.(csv|json|xml)$/.test(file.path || ""),
  );
  if (!files.length) return;

  fileRows.innerHTML = files
    .map(
      (file) => `
        <tr>
          <td><a href="${file.url}">${file.path}</a></td>
          <td>${formatKind(file.path)}</td>
          <td>${numberFormat.format(file.records || 0)}</td>
          <td>${formatBytes(file.bytes)}</td>
          <td><a href="${file.gzip_url}">${formatBytes(file.gzip_bytes)}</a></td>
          <td class="mono" title="${file.sha256 || ""}">${shortHash(file.sha256)}</td>
        </tr>
      `,
    )
    .join("");
};

fetch("api/v1/index.json")
  .then((response) => {
    if (!response.ok) throw new Error(`Manifest returned ${response.status}`);
    return response.json();
  })
  .then((manifest) => {
    updateManifestSummary(manifest);
    renderFileRows(manifest);
  })
  .catch(() => {
    dataUpdatedAt.textContent = "Manifest unavailable";
  });

document.querySelectorAll("[data-copy]").forEach((button) => {
  button.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(button.dataset.copy || "");
      const label = button.textContent;
      button.textContent = "Copied";
      window.setTimeout(() => {
        button.textContent = label;
      }, 1200);
    } catch {
      button.textContent = "Copy failed";
    }
  });
});

const themeToggle = document.getElementById("themeToggle");
const applyThemeLabel = () => {
  const isDark = document.documentElement.dataset.theme === "dark";
  themeToggle.setAttribute("aria-pressed", String(isDark));
  const [label, icon] = themeToggle.querySelectorAll("span");
  label.textContent = isDark ? "Dark mode" : "Light mode";
  icon.textContent = isDark ? "D" : "L";
};
themeToggle.addEventListener("click", () => {
  const isDark = document.documentElement.dataset.theme === "dark";
  const nextTheme = isDark ? "light" : "dark";
  document.documentElement.dataset.theme = nextTheme;
  try {
    localStorage.setItem("open-postal-codes-theme", nextTheme);
  } catch {
    /* Theme persistence is optional. */
  }
  applyThemeLabel();
});
applyThemeLabel();
