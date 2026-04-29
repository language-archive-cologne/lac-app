(function () {
  const MULTIPART_THRESHOLD =
    (window.UPLOAD_CONFIG && window.UPLOAD_CONFIG.multipartThreshold) ||
    window.MULTIPART_THRESHOLD ||
    5 * 1024 * 1024 * 1024;

  let dashboardPlayer = null;
  let modalSelectedFiles = [];

  function qs(selector, root) {
    return (root || document).querySelector(selector);
  }

  function cleanupMedia() {
    const modal = qs("#file-viewer-modal");
    if (!modal) return;

    const audio = modal.querySelector("#audioPlayer");
    if (audio) {
      audio.pause();
      audio.currentTime = 0;
    }

    const video = modal.querySelector("#videoPlayer");
    if (video) {
      video.pause();
      video.currentTime = 0;
    }

    if (dashboardPlayer) {
      dashboardPlayer.destroy();
      dashboardPlayer = null;
    }
  }

  function openFileViewer() {
    qs("#file-viewer-modal")?.showModal();
  }

  function closeFileViewer() {
    cleanupMedia();
    qs("#file-viewer-modal")?.close();
  }

  function initialiseWaveform(container) {
    const playerContainer =
      container.querySelector("[data-audio-url]") ||
      container.closest("[data-audio-url]");

    if (!playerContainer || !window.AudioPlayer) {
      if (dashboardPlayer) {
        dashboardPlayer.destroy();
        dashboardPlayer = null;
      }
      const audioElement = container.querySelector("#audioPlayer");
      if (audioElement) {
        audioElement.controls = true;
        audioElement.classList.remove("hidden");
      }
      return;
    }

    if (dashboardPlayer) {
      dashboardPlayer.destroy();
      dashboardPlayer = null;
    }
    dashboardPlayer = new AudioPlayer(playerContainer);
  }

  function highlightViewerCode(container) {
    if (!window.Prism) return;
    const code = container.querySelector("#file-viewer-code");
    if (code) {
      Prism.highlightElement(code);
    }
  }

  function updateActiveBucketInput() {
    const targetInput = qs("#current-active-bucket-input");
    const dropdownButton = qs("#bucket-tabs .btn");
    const bucketName = dropdownButton
      ?.querySelector(".font-semibold")
      ?.textContent?.trim();

    if (targetInput && bucketName && bucketName !== "Select Bucket") {
      targetInput.value = bucketName;
    }
  }

  function normalizeFolderPath(path) {
    return path ? path.replace(/^\/+|\/+$/g, "") : "";
  }

  function setCurrentFolderPath(path) {
    const input = qs("#current-folder-path-input");
    if (input) {
      input.value = normalizeFolderPath(path);
    }
  }

  function getCurrentFolderPath() {
    const input = qs("#current-folder-path-input");
    return input ? input.value.trim() : "";
  }

  function showMessage(level, message) {
    const messageContainer = qs("#message-container");
    const messageContent = qs("#message-content");
    if (!messageContainer || !messageContent) return;

    messageContent.textContent = message;
    messageContent.className =
      level === "error"
        ? "bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded relative"
        : "bg-green-100 border border-green-400 text-green-700 px-4 py-3 rounded relative";
    messageContainer.classList.remove("hidden");
    setTimeout(() => messageContainer.classList.add("hidden"), 5000);
  }

  function switchModalToFiles() {
    const input = qs("#modal-file-picker");
    if (!input) return;

    input.setAttribute("multiple", "");
    input.removeAttribute("webkitdirectory");
    input.value = "";

    qs("#modal-files-btn")?.classList.add("btn-active");
    qs("#modal-files-btn")?.classList.remove("btn-outline");
    qs("#modal-folder-btn")?.classList.remove("btn-active");
    qs("#modal-folder-btn")?.classList.add("btn-outline");
  }

  function switchModalToFolder() {
    const input = qs("#modal-file-picker");
    if (!input) return;

    input.setAttribute("webkitdirectory", "");
    input.removeAttribute("multiple");
    input.value = "";

    qs("#modal-folder-btn")?.classList.add("btn-active");
    qs("#modal-folder-btn")?.classList.remove("btn-outline");
    qs("#modal-files-btn")?.classList.remove("btn-active");
    qs("#modal-files-btn")?.classList.add("btn-outline");
  }

  function formatFileSize(bytes) {
    const units = ["B", "KB", "MB", "GB", "TB"];
    let size = bytes;
    let unitIndex = 0;

    while (size >= 1024 && unitIndex < units.length - 1) {
      size /= 1024;
      unitIndex += 1;
    }

    return unitIndex === 0
      ? `${size} ${units[unitIndex]}`
      : `${size.toFixed(2)} ${units[unitIndex]}`;
  }

  function displayModalFileInfo() {
    const filesInfo = qs("#modal-files-info");
    const filesList = qs("#modal-files-list");
    const fileCount = qs("#modal-file-count");
    const totalSize = qs("#modal-total-size");
    const multipartCount = qs("#modal-multipart-count");
    if (!filesInfo || !filesList || !fileCount || !totalSize || !multipartCount) return;

    filesInfo.classList.remove("hidden");
    filesList.innerHTML = "";

    let total = 0;
    let multipart = 0;
    modalSelectedFiles.forEach((file) => {
      total += file.size;
      if (file.size > MULTIPART_THRESHOLD) multipart += 1;

      const item = document.createElement("div");
      item.className = "text-sm py-1 flex justify-between";

      const name = document.createElement("span");
      name.className = "truncate flex-1";
      name.textContent = file.webkitRelativePath || file.name;
      item.appendChild(name);

      const size = document.createElement("span");
      size.className = "text-gray-500 ml-2";
      size.textContent = formatFileSize(file.size);
      item.appendChild(size);

      if (file.size > MULTIPART_THRESHOLD) {
        const badge = document.createElement("span");
        badge.className = "text-blue-600 ml-2";
        badge.textContent = "MP";
        item.appendChild(badge);
      }

      filesList.appendChild(item);
    });

    fileCount.textContent = `${modalSelectedFiles.length} files`;
    totalSize.textContent = formatFileSize(total);
    multipartCount.textContent = `${multipart} require multipart`;
  }

  function updateModalProgress(percent, status) {
    const progressBar = qs("#modal-progress-bar");
    const percentage = qs("#modal-upload-percentage");
    const uploadStatus = qs("#modal-upload-status");
    if (progressBar) progressBar.value = percent;
    if (percentage) percentage.textContent = `${Math.round(percent)}%`;
    if (uploadStatus) uploadStatus.textContent = status;
  }

  function showModalMessage(type, message) {
    const container = qs("#modal-status-messages");
    if (!container) return;

    const alertClass = type === "success" ? "alert-success" : "alert-error";
    container.replaceChildren();

    const alert = document.createElement("div");
    alert.className = `alert ${alertClass}`;
    const text = document.createElement("span");
    text.textContent = message;
    alert.appendChild(text);
    container.appendChild(alert);

    setTimeout(() => container.replaceChildren(), 5000);
  }

  function getCookie(name) {
    if (!document.cookie) return null;

    const cookies = document.cookie.split(";");
    for (const rawCookie of cookies) {
      const cookie = rawCookie.trim();
      if (cookie.startsWith(`${name}=`)) {
        return decodeURIComponent(cookie.substring(name.length + 1));
      }
    }
    return null;
  }

  function getCsrfToken() {
    const csrfInput = qs("[name=csrfmiddlewaretoken]");
    const csrfMeta = qs('meta[name="csrf-token"]');
    return csrfInput?.value || csrfMeta?.content || getCookie("csrftoken") || "";
  }

  async function markModalUploadsComplete(s3Keys, uploadSessionId) {
    try {
      const response = await fetch("/storage/mark-uploads-complete/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCsrfToken(),
        },
        body: JSON.stringify({
          s3_keys: s3Keys,
          upload_session_id: uploadSessionId,
        }),
      });

      if (!response.ok) {
        console.warn("Failed to mark uploads complete:", response.status);
        return false;
      }

      const result = await response.json();
      if (!result.success) {
        console.warn("Upload verification failed:", result);
        return false;
      }
      return true;
    } catch (error) {
      console.warn("Error marking uploads complete:", error);
      return false;
    }
  }

  async function uploadModalSingleFile(file, config) {
    const formData = new FormData();
    Object.entries(config.presigned_post.fields).forEach(([key, value]) => {
      formData.append(key, value);
    });
    formData.append("file", file);

    const response = await fetch(config.presigned_post.url, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) throw new Error(`S3 upload failed: ${response.status}`);
  }

  async function uploadModalMultipartFile(file, config, fileIndex, totalFiles, bucketName) {
    const handler = new MultipartUploadHandler(file, {
      bucketName,
      onProgress: (progress) => {
        const overallProgress =
          (fileIndex / totalFiles) * 100 + progress.percent / totalFiles;
        updateModalProgress(
          overallProgress,
          `Uploading ${file.name} (part ${progress.loaded}/${progress.total})...`,
        );
      },
    });

    await handler.upload(config);
  }

  async function uploadModalFiles(files, presignedPosts, bucketName, uploadSessionId) {
    const uploadedKeys = [];

    for (let i = 0; i < files.length; i += 1) {
      const file = files[i];
      const config = presignedPosts[i];
      const fileName = file.webkitRelativePath || file.name;

      updateModalProgress((i / files.length) * 100, `Uploading ${fileName}...`);

      if (config.upload_type === "multipart") {
        await uploadModalMultipartFile(file, config, i, files.length, bucketName);
      } else {
        await uploadModalSingleFile(file, config);
      }

      if (config.s3_key) {
        uploadedKeys.push(config.s3_key);
        if (uploadSessionId) {
          await markModalUploadsComplete([config.s3_key], uploadSessionId);
        }
      }
      updateModalProgress(
        ((i + 1) / files.length) * 100,
        `Completed ${i + 1} of ${files.length} files`,
      );
    }
    return uploadedKeys;
  }

  async function startModalUpload() {
    const bucket = qs("#modal-bucket-select")?.value;
    let folder = qs("#modal-folder-input")?.value.trim() || "";
    const currentFolderPath = getCurrentFolderPath();

    if (modalSelectedFiles.length === 0) {
      showModalMessage("error", "Please select files to upload");
      return;
    }

    const isUploadingFolder =
      modalSelectedFiles.length > 0 && modalSelectedFiles[0].webkitRelativePath;
    if (!folder && currentFolderPath && !isUploadingFolder) {
      folder = currentFolderPath;
    }

    const uploadBtn = qs("#modal-upload-btn");
    const progressContainer = qs("#modal-upload-progress");
    if (uploadBtn) {
      uploadBtn.disabled = true;
      uploadBtn.textContent = "Uploading...";
    }
    progressContainer?.classList.remove("hidden");

    try {
      const filesMetadata = modalSelectedFiles.map((file) => ({
        file_name: file.name,
        file_type: file.type || "application/octet-stream",
        file_size: file.size,
        path: file.webkitRelativePath || file.name,
      }));

      const response = await fetch("/storage/presigned-urls/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCsrfToken(),
        },
        body: JSON.stringify({
          folder_name: folder,
          bucket_name: bucket,
          files_metadata: filesMetadata,
        }),
      });

      if (!response.ok) throw new Error(`Server error: ${response.status}`);

      const result = await response.json();
      if (!result.success) throw new Error(result.error || "Failed to get upload URLs");

      const uploadedKeys = await uploadModalFiles(
        modalSelectedFiles,
        result.presigned_posts,
        bucket,
        result.upload_session_id,
      );

      if (result.upload_session_id && uploadedKeys.length) {
        await markModalUploadsComplete(uploadedKeys, result.upload_session_id);
      }

      showModalMessage("success", `Successfully uploaded ${modalSelectedFiles.length} files`);

      const picker = qs("#modal-file-picker");
      if (picker) picker.value = "";
      modalSelectedFiles = [];
      qs("#modal-files-info")?.classList.add("hidden");
      const folderInput = qs("#modal-folder-input");
      if (folderInput) folderInput.value = "";

      setTimeout(() => {
        const activeBucketInput = qs("#current-active-bucket-input");
        if (activeBucketInput) activeBucketInput.value = bucket;
        if (bucket && window.htmx) {
          htmx.ajax("GET", `/storage/htmx/bucket-content/${bucket}/?force_fresh=true`, {
            target: "#bucket-content",
            swap: "innerHTML",
          });
        }
        const uploadModal = qs("#upload-modal");
        if (uploadModal) uploadModal.checked = false;
      }, 1500);
    } catch (error) {
      showModalMessage("error", `Upload failed: ${error.message}`);
    } finally {
      if (uploadBtn) {
        uploadBtn.disabled = false;
        uploadBtn.textContent = "Upload Files";
      }
      progressContainer?.classList.add("hidden");
    }
  }

  function handleClick(event) {
    const stopToggle = event.target.closest("[data-stop-folder-toggle]");
    if (stopToggle) {
      event.stopPropagation();
    }

    if (event.target.closest("[data-refresh-bucket-select]") && window.htmx) {
      htmx.trigger(document.body, "refreshBucketSelect");
    }

    if (event.target.closest("[data-modal-upload-mode='files']")) {
      switchModalToFiles();
    }
    if (event.target.closest("[data-modal-upload-mode='folder']")) {
      switchModalToFolder();
    }
    if (event.target.closest("[data-modal-file-picker-trigger]")) {
      qs("#modal-file-picker")?.click();
    }
    if (event.target.closest("[data-start-modal-upload]")) {
      startModalUpload();
    }
    if (event.target.closest("[data-open-file-viewer]")) {
      openFileViewer();
    }
    if (event.target.closest("[data-close-file-viewer]")) {
      closeFileViewer();
    }
    if (event.target.closest("[data-blur-active-element]")) {
      document.activeElement?.blur();
    }

    const summary = event.target.closest("summary");
    const details = summary?.closest("details[data-folder-path]");
    if (details) {
      setCurrentFolderPath(details.dataset.folderPath || "");
    }

    const bucketLink = event.target.closest("#bucket-tabs .dropdown-content a[hx-get]");
    if (bucketLink) {
      setCurrentFolderPath("");
      const name = bucketLink.querySelector(".font-semibold")?.textContent?.trim();
      const targetInput = qs("#current-active-bucket-input");
      if (targetInput && name) targetInput.value = name;
    }
  }

  function bindFilePicker() {
    const picker = qs("#modal-file-picker");
    if (!picker || picker.dataset.storageDashboardBound === "true") return;
    picker.dataset.storageDashboardBound = "true";

    picker.addEventListener("change", (event) => {
      modalSelectedFiles = Array.from(event.target.files);
      if (modalSelectedFiles.length > 0) {
        displayModalFileInfo();
        const uploadBtn = qs("#modal-upload-btn");
        if (uploadBtn) uploadBtn.disabled = false;
      } else {
        qs("#modal-files-info")?.classList.add("hidden");
        const uploadBtn = qs("#modal-upload-btn");
        if (uploadBtn) uploadBtn.disabled = true;
      }
    });
  }

  document.body.addEventListener("htmx:beforeSend", (event) => {
    event.detail.xhr.setRequestHeader("X-HTMX-Indicator", "none");
  });

  document.body.addEventListener("htmx:afterOnLoad", (event) => {
    const messageData = event.detail?.triggerSpec?.showMessage;
    if (messageData) {
      showMessage(messageData.level, messageData.message);
    }
  });

  document.addEventListener("showMessage", (event) => {
    if (event.detail) {
      showMessage(event.detail.level, event.detail.message);
    }
  });

  document.addEventListener("htmx:afterSwap", (event) => {
    if (event.target.id === "file-viewer-content") {
      initialiseWaveform(event.target);
      highlightViewerCode(event.target);
    }
    if (event.target.id === "bucket-tabs" || event.target.closest?.("#bucket-tabs")) {
      updateActiveBucketInput();
    }
  });

  document.addEventListener("htmx:afterRequest", (event) => {
    const xhr = event.detail?.xhr;
    if (xhr && xhr.status === 200) {
      const triggerHeader = xhr.getResponseHeader("HX-Trigger");
      if (triggerHeader) {
        try {
          const data = JSON.parse(triggerHeader);
          if (data.closeModal) {
            const modalToggle = document.getElementById(data.closeModal);
            if (modalToggle) modalToggle.checked = false;
          }
          if (data.refreshBucketContent) {
            qs('button[hx-get*="archivist_dashboard"]')?.click();
          }
        } catch (error) {
          console.warn("Unable to parse HX-Trigger header", error);
        }
      }
    }

    if (event.detail?.successful) {
      event.detail.elt?.closest("[data-remove-on-success]")?.closest("li")?.remove();
    }

    if (event.detail?.elt?.id === "bucket-tabs" || event.detail?.elt?.closest?.("#bucket-tabs")) {
      updateActiveBucketInput();
    }
  });

  document.addEventListener("toggle", (event) => {
    const details = event.target;
    if (!details?.matches?.("details[data-folder-path]")) return;
    if (details.open) {
      setCurrentFolderPath(details.dataset.folderPath || "");
    }
  });

  document.addEventListener("click", handleClick);
  document.addEventListener("DOMContentLoaded", bindFilePicker);
  bindFilePicker();

  qs("#file-viewer-modal")?.addEventListener("close", cleanupMedia);

  window.openFileViewer = openFileViewer;
  window.closeFileViewer = closeFileViewer;
})();
