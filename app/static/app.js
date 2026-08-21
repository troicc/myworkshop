const $ = (selector) => document.querySelector(selector);

function lines(value) {
  return value.split(/\n+/).map((item) => item.trim()).filter(Boolean);
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
  })[char]);
}

async function loadProjects() {
  const container = $("#projects");
  container.innerHTML = '<div class="empty">正在读取项目…</div>';
  try {
    const response = await fetch("/api/projects");
    const projects = await response.json();
    if (!projects.length) {
      container.innerHTML = '<div class="empty">还没有项目。先用 Mock 模式生成第一套样张。</div>';
      return;
    }
    container.innerHTML = projects.map((project) => {
      const images = (project.output_files || []).map((path) =>
        `<a href="/files/${project.project_id}/${encodeURI(path)}" target="_blank"><img loading="lazy" src="/files/${project.project_id}/${encodeURI(path)}" alt="${escapeHtml(project.title)}"></a>`
      ).join("");
      const failed = project.status === "failed" ? " failed" : "";
      return `<article class="project">
        <div class="project-head">
          <div><h3>${escapeHtml(project.title)}</h3><div class="meta">${escapeHtml(project.project_id)} · ${escapeHtml(project.created_at)}</div></div>
          <span class="badge${failed}">${escapeHtml(project.status)}</span>
        </div>
        ${images ? `<div class="preview-row">${images}</div>` : '<div class="empty">尚无成品图片，查看 manifest 或错误记录。</div>'}
        <div class="actions">
          <a href="/files/${project.project_id}/manifest.json" target="_blank">Manifest</a>
          <a href="/files/${project.project_id}/plan.json" target="_blank">内容计划</a>
          <a href="/files/${project.project_id}/caption.md" target="_blank">发布文案</a>
          <a href="/files/${project.project_id}/export.zip">下载导出包</a>
          <button data-rerender="${project.project_id}">重新排版</button>
        </div>
      </article>`;
    }).join("");
    document.querySelectorAll("[data-rerender]").forEach((button) => {
      button.addEventListener("click", async () => {
        button.disabled = true;
        button.textContent = "排版中…";
        await fetch(`/api/projects/${button.dataset.rerender}/rerender`, {method: "POST"});
        await loadProjects();
      });
    });
  } catch (error) {
    container.innerHTML = `<div class="empty">读取失败：${escapeHtml(error.message)}</div>`;
  }
}

$("#generate-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("button[type=submit]");
  const status = $("#generate-status");
  const data = new FormData(form);
  const payload = {
    title: data.get("title"),
    audience: data.get("audience"),
    scenario: data.get("scenario"),
    objective: data.get("objective"),
    slide_count: Number(data.get("slide_count")),
    source_notes: lines(data.get("source_notes") || ""),
    avoid_claims: lines(data.get("avoid_claims") || ""),
    call_to_action: "收藏备用，下次照着做",
    locale: "zh-CN"
  };
  button.disabled = true;
  status.className = "status-note";
  status.textContent = "正在规划、生成、审查和排版。真实图片 API 可能需要数分钟，请不要重复提交。";
  try {
    const response = await fetch("/api/generate", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || result.detail || "生成失败");
    status.className = "status-note success";
    status.textContent = `完成：${result.project_id}`;
    await loadProjects();
  } catch (error) {
    status.className = "status-note error";
    status.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

$("#reference-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const status = $("#reference-status");
  try {
    const response = await fetch("/api/references", {method: "POST", body: new FormData(form)});
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "上传失败");
    status.textContent = `已保存：${result.saved}`;
    form.reset();
  } catch (error) {
    status.textContent = error.message;
  }
});

$("#refresh-projects").addEventListener("click", loadProjects);
loadProjects();
